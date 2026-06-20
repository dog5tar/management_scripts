#!/usr/bin/env python

"""
Transcript from Videos Script

This script takes a folder path as input, scans for supported media files
recursively, extracts MP3 audio from each file when needed, and creates transcripts
using MLX Whisper on Apple Silicon. Each transcript is saved in its own folder
named after the video file.

Features:
- Conda environment check (requires 'management_scripts' environment)
- Recursive MP4/MOV/TS/MKV/M4A/WEBM/WAV file scanning
- MP3 audio extraction using ffmpeg when direct video is not used
- Fast transcription using MLX Whisper on Apple Silicon
- Multiple output formats (txt, json, srt, vtt)
- Progress tracking and resume capability
- Detailed debug messages for each processing step

Usage:
    python transcript_from_videos.py /path/to/folder/with/videos
    python transcript_from_videos.py /path/to/folder/with/videos --model large
    python transcript_from_videos.py /path/to/folder/with/videos --reset-tracking
"""

import os
import sys
import json
import argparse
from pathlib import Path
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import time
import re
import inspect
import shutil

MODEL_REPOS = {
    'tiny': 'mlx-community/whisper-tiny-mlx',
    'base': 'mlx-community/whisper-base-mlx',
    'small': 'mlx-community/whisper-small-mlx',
    'medium': 'mlx-community/whisper-medium-mlx',
    'large': 'mlx-community/whisper-large-v3-mlx',
}

_MLX_WHISPER_MODULE = None

def check_conda_environment():
    """Check if we're running in the correct conda environment."""
    required_env = "management_scripts"
    
    # Check CONDA_DEFAULT_ENV environment variable
    current_env = os.environ.get('CONDA_DEFAULT_ENV')
    
    if current_env != required_env:
        print(f"❌ Error: This script must be run in the '{required_env}' conda environment.")
        print(f"Current environment: {current_env or 'None'}")
        print(f"\nPlease activate the correct environment with:")
        print(f"conda activate {required_env}")
        sys.exit(1)

def load_tracking_data(tracking_file):
    """Load tracking data from the hidden file."""
    if tracking_file.exists():
        try:
            with open(tracking_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print(f"⚠️  Warning: Could not read tracking file {tracking_file}. Starting fresh.")
    return {}

def save_tracking_data(tracking_file, data):
    """Save tracking data to the hidden file."""
    try:
        with open(tracking_file, 'w') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"⚠️  Warning: Could not save tracking data: {e}")

def find_video_files(directory):
    """Recursively find all supported video files in the directory."""
    video_files = []
    directory_path = Path(directory)
    
    if not directory_path.exists():
        print(f"❌ Error: Directory {directory} does not exist.")
        return video_files
    
    supported_extensions = {".mp4", ".mov", ".ts", ".mkv", ".m4a", ".webm", ".wav"}
    for video_file in directory_path.rglob("*"):
        if video_file.is_file() and video_file.suffix.lower() in supported_extensions:
            video_files.append(video_file)
    
    return sorted(video_files)

def format_size_gb(size_bytes: int) -> str:
    return f"{size_bytes / (1024 ** 3):.2f} GB"

def format_elapsed(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def probe_video_duration(video_path: Path, ffprobe_available: bool) -> float | None:
    if not ffprobe_available:
        return None

    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(video_path)
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, OSError):
        return None

def collect_video_metadata(video_files, tracking_data):
    """Collect size and optional duration metadata for batch-level summaries."""
    ffprobe_available = shutil.which('ffprobe') is not None
    duration_available = ffprobe_available
    metadata = []

    for video_path in video_files:
        size_bytes = video_path.stat().st_size
        duration_seconds = probe_video_duration(video_path, ffprobe_available)
        if ffprobe_available and duration_seconds is None:
            duration_available = False

        tracking_key = get_tracking_key(video_path)
        is_completed = tracking_key in tracking_data and tracking_data[tracking_key].get('completed', False)
        metadata.append({
            'path': video_path,
            'size_bytes': size_bytes,
            'duration_seconds': duration_seconds,
            'tracking_key': tracking_key,
            'is_completed': is_completed,
        })

    if not ffprobe_available:
        duration_available = False
    elif duration_available:
        duration_available = all(item['duration_seconds'] is not None for item in metadata)

    return metadata, duration_available

def print_pre_scan_summary(metadata, duration_available: bool) -> None:
    total_files = len(metadata)
    total_size_bytes = sum(item['size_bytes'] for item in metadata)
    completed_count = sum(1 for item in metadata if item['is_completed'])
    remaining_items = [item for item in metadata if not item['is_completed']]
    remaining_count = len(remaining_items)
    remaining_size_bytes = sum(item['size_bytes'] for item in remaining_items)
    largest_file = max(metadata, key=lambda item: item['size_bytes'])
    smallest_file = min(metadata, key=lambda item: item['size_bytes'])

    print("\n📦 Batch summary")
    print(f"Total files: {total_files}")
    print(f"Total size: {format_size_gb(total_size_bytes)}")
    if duration_available:
        total_duration_seconds = sum(item['duration_seconds'] for item in metadata)
        print(f"Total duration: {format_elapsed(total_duration_seconds)}")
    else:
        print("Duration unavailable")
    print(f"Largest file: {largest_file['path'].name} ({format_size_gb(largest_file['size_bytes'])})")
    print(f"Smallest file: {smallest_file['path'].name} ({format_size_gb(smallest_file['size_bytes'])})")
    print(f"Already completed: {completed_count}")
    print(f"Remaining: {remaining_count}")
    print(f"Remaining size: {format_size_gb(remaining_size_bytes)}")

def print_batch_progress(
    total_files: int,
    already_completed_count: int,
    completed_this_run: int,
    elapsed_batch_seconds: float,
    processed_size_bytes: int,
    total_remaining_size_bytes: int,
    projected_remaining_seconds: float,
    processed_duration_seconds: float,
    total_remaining_duration_seconds: float | None,
) -> None:
    completed_total = already_completed_count + completed_this_run
    remaining_total = total_files - completed_total
    avg_per_file = elapsed_batch_seconds / completed_this_run
    avg_per_gb = elapsed_batch_seconds / (processed_size_bytes / (1024 ** 3)) if processed_size_bytes > 0 else 0.0

    print("\n📊 Batch progress")
    print(f"Completed: {completed_total}/{total_files}")
    print(f"Remaining: {remaining_total}")
    print(f"Processed size: {format_size_gb(processed_size_bytes)} / {format_size_gb(total_remaining_size_bytes)}")
    print(f"Elapsed: {format_elapsed(elapsed_batch_seconds)}")
    print(f"Avg/file: {format_elapsed(avg_per_file)}")
    print(f"Avg/GB: {format_elapsed(avg_per_gb)}")
    if total_remaining_duration_seconds is not None and processed_duration_seconds > 0:
        avg_per_video_minute = elapsed_batch_seconds / (processed_duration_seconds / 60)
        print(f"Avg/min video: {format_elapsed(avg_per_video_minute)}")
    print(f"ETA remaining: {format_elapsed(projected_remaining_seconds)}")
    finish_time = time.time() + projected_remaining_seconds
    print(f"Estimated finish: {time.strftime('%H:%M', time.localtime(finish_time))}")

def process_single_video(task: dict) -> dict:
    """Process one video in isolation so the parent can manage tracking safely."""
    mp4_path = Path(task['mp4_path'])
    output_folder = Path(task['output_folder'])
    output_folder.mkdir(exist_ok=True)

    audio_path = Path(task['audio_path'])
    transcript_base_path = Path(task['transcript_base_path'])
    outputs = set(task['outputs'])
    desired_output_paths = output_paths_for_base(transcript_base_path, outputs)

    file_start_time = time.time()
    extraction_elapsed = 0.0
    transcription_elapsed = 0.0
    save_elapsed = 0.0

    transcribe_input_path = mp4_path if task['use_direct_video'] else audio_path

    if not task['use_direct_video']:
        audio_extracted = False
        if audio_path.exists():
            audio_extracted = True
        else:
            extraction_start_time = time.time()
            audio_extracted = extract_audio_from_mp4(mp4_path, audio_path, verbose=False)
            extraction_elapsed = time.time() - extraction_start_time

        if not audio_extracted:
            return {
                'success': False,
                'mp4_path': str(mp4_path),
                'tracking_key': task['tracking_key'],
                'error': f"Audio extraction failed for {mp4_path.name}",
            }

    outputs_exist = all(path.exists() for path in desired_output_paths.values())
    action = 'existing_outputs'

    if task['force_transcribe'] or not outputs_exist:
        mlx_whisper_module = import_mlx_whisper()
        if mlx_whisper_module is None:
            return {
                'success': False,
                'mp4_path': str(mp4_path),
                'tracking_key': task['tracking_key'],
                'error': "MLX Whisper is not installed.",
            }

        transcription_start_time = time.time()
        result = transcribe_audio(
            transcribe_input_path,
            mlx_whisper_module,
            task['hf_model'],
            task['model_name'],
            task['language'],
            task['supports_language'],
            verbose=False,
        )
        transcription_elapsed = time.time() - transcription_start_time

        if result is None:
            return {
                'success': False,
                'mp4_path': str(mp4_path),
                'tracking_key': task['tracking_key'],
                'error': f"Transcription failed for {mp4_path.name}",
            }

        save_start_time = time.time()
        saved_ok = save_transcription_formats(result, transcript_base_path, outputs, verbose=False)
        save_elapsed = time.time() - save_start_time
        if not saved_ok:
            return {
                'success': False,
                'mp4_path': str(mp4_path),
                'tracking_key': task['tracking_key'],
                'error': f"Saving outputs failed for {mp4_path.name}",
            }
        action = 'transcribed'

    return {
        'success': True,
        'mp4_path': str(mp4_path),
        'tracking_key': task['tracking_key'],
        'output_folder': str(output_folder),
        'action': action,
        'used_direct_video': task['use_direct_video'],
        'direct_video_fallback': task['direct_video_requested'] and not task['use_direct_video'],
        'extraction_elapsed': extraction_elapsed,
        'transcription_elapsed': transcription_elapsed,
        'save_elapsed': save_elapsed,
        'file_elapsed': time.time() - file_start_time,
    }

def extract_audio_from_mp4(mp4_path, audio_path, verbose=True):
    """Extract MP3 audio from a video file using ffmpeg."""
    try:
        if verbose:
            print(f"🎵 Extracting audio from: {mp4_path.name}")
        
        # Use MP3 extraction for the non-direct-video fallback path.
        cmd = [
            'ffmpeg',
            '-i', str(mp4_path),
            '-vn',  # No video
            '-acodec', 'libmp3lame',
            '-ab', '192k',
            '-ar', '44100',
            '-y',  # Overwrite output file
            str(audio_path)
        ]
        
        # Run ffmpeg with suppressed output
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        if verbose:
            print(f"✅ Audio extracted: {audio_path.name}")
        return True
        
    except subprocess.CalledProcessError as e:
        if verbose:
            print(f"❌ Audio extraction failed for {mp4_path.name}: {e}")
        return False
    except Exception as e:
        if verbose:
            print(f"❌ Unexpected error during audio extraction: {e}")
        return False

def import_mlx_whisper():
    """Import MLX Whisper once so batch runs do not repeat module setup."""
    global _MLX_WHISPER_MODULE
    if _MLX_WHISPER_MODULE is not None:
        return _MLX_WHISPER_MODULE

    try:
        import mlx_whisper
        _MLX_WHISPER_MODULE = mlx_whisper
        return _MLX_WHISPER_MODULE
    except ImportError:
        print("❌ MLX Whisper is not installed.")
        print("Install with:")
        print("pip install mlx-whisper")
        return None

def mlx_whisper_supports_language(mlx_whisper_module) -> bool:
    try:
        signature = inspect.signature(mlx_whisper_module.transcribe)
        return 'language' in signature.parameters
    except Exception:
        return False

def parse_outputs_arg(outputs_arg: str) -> set[str]:
    normalized = [part.strip().lower() for part in outputs_arg.split(',')]
    outputs = {part for part in normalized if part}
    allowed = {'txt', 'json', 'srt', 'vtt'}
    invalid = outputs - allowed
    if invalid:
        raise ValueError(f"Invalid output(s): {', '.join(sorted(invalid))}. Allowed: {', '.join(sorted(allowed))}")
    if not outputs:
        raise ValueError("No outputs selected. Use e.g. --outputs txt or --outputs txt,json")
    return outputs

def output_paths_for_base(base_path: Path, outputs: set[str]) -> dict[str, Path]:
    return {fmt: Path(str(base_path) + f'.{fmt}') for fmt in outputs}

def transcribe_audio(input_path, mlx_whisper_module, hf_model, model_name="base", language: str | None = None, supports_language: bool = False, verbose=True):
    """Transcribe audio file using MLX Whisper and return full result."""
    try:
        if verbose:
            print(f"🎤 Transcribing {Path(input_path).name} with {model_name} model...")
        
        kwargs = {'path_or_hf_repo': hf_model}
        if language and supports_language:
            kwargs['language'] = language
        result = mlx_whisper_module.transcribe(str(input_path), **kwargs)
        
        if verbose:
            print(f"✅ Transcription completed: {Path(input_path).name}")
        return result
        
    except Exception as e:
        if verbose:
            print(f"❌ Transcription failed for {Path(input_path).name}: {e}")
        return None

def save_transcription_formats(result, base_path, outputs: set[str], verbose=True):
    """Save transcription in multiple formats (txt, json, srt, vtt)"""
    try:
        if 'txt' in outputs:
            txt_path = Path(str(base_path) + '.txt')
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(result['text'])
            if verbose:
                print(f"💾 Saved transcript: {txt_path.name}")
        
        if 'json' in outputs:
            json_path = Path(str(base_path) + '.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            if verbose:
                print(f"💾 Saved JSON: {json_path.name}")
        
        if 'srt' in outputs:
            srt_path = Path(str(base_path) + '.srt')
            with open(srt_path, 'w', encoding='utf-8') as f:
                for i, segment in enumerate(result['segments'], 1):
                    start_time = format_timestamp(segment['start'])
                    end_time = format_timestamp(segment['end'])
                    f.write(f"{i}\n{start_time} --> {end_time}\n{segment['text'].strip()}\n\n")
            if verbose:
                print(f"💾 Saved SRT: {srt_path.name}")
        
        if 'vtt' in outputs:
            vtt_path = Path(str(base_path) + '.vtt')
            with open(vtt_path, 'w', encoding='utf-8') as f:
                f.write("WEBVTT\n\n")
                for segment in result['segments']:
                    start_time = format_timestamp(segment['start'], vtt_format=True)
                    end_time = format_timestamp(segment['end'], vtt_format=True)
                    f.write(f"{start_time} --> {end_time}\n{segment['text'].strip()}\n\n")
            if verbose:
                print(f"💾 Saved VTT: {vtt_path.name}")
        
        return True
        
    except Exception as e:
        if verbose:
            print(f"❌ Failed to save transcription formats: {e}")
        return False

def format_timestamp(seconds, vtt_format=False):
    """Format timestamp for subtitle files"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    
    if vtt_format:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{milliseconds:03d}"
    else:
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"

def sanitize_filename(filename):
    """Preserve the original filename stem exactly for output folder naming."""
    return Path(filename).stem

def get_tracking_key(mp4_path):
    """Generate a unique tracking key for the MP4 file"""
    return str(mp4_path.resolve())

def ensure_parent_dir_writable(parent: Path) -> None:
    """Ensure the MP4 parent directory exists and is writable."""
    if not parent.exists() or not parent.is_dir():
        raise NotADirectoryError(f"Parent directory does not exist or is not a directory: {parent}")
    # Require execute (search) and write permissions on the parent to create subdirs/files
    if not os.access(parent, os.X_OK | os.W_OK):
        raise PermissionError(f"Parent directory is not writable: {parent}")

def get_output_folder_for_mp4(mp4_path: Path) -> Path:
    """Return the transcript output folder placed next to the MP4."""
    return mp4_path.parent / f"{mp4_path.stem}_transcript"

def main():
    # Check conda environment first
    check_conda_environment()
    
    parser = argparse.ArgumentParser(
        description="Extract audio from supported media files and create transcripts using MLX Whisper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python transcript_from_videos.py /path/to/videos
  python transcript_from_videos.py /path/to/videos --model large
  python transcript_from_videos.py /path/to/videos --reset-tracking
        """
    )
    
    parser.add_argument(
        'folder_path',
        help='Path to folder containing supported media files (mp4, mov, ts, mkv, m4a, webm, wav)'
    )
    
    parser.add_argument(
        '--model',
        default='base',
        choices=['tiny', 'base', 'small', 'medium', 'large'],
        help='MLX Whisper model size to use (default: base)'
    )
    
    parser.add_argument(
        '--language',
        default='en',
        help='Language code to hint MLX Whisper decoding (default: en)'
    )

    parser.add_argument(
        '--direct-video',
        action='store_true',
        help='Skip audio extraction and pass MP4 files directly to MLX Whisper; all other supported formats fall back to extracted MP3 audio'
    )

    parser.add_argument(
        '--outputs',
        default='txt,json,srt,vtt',
        help='Comma-separated output formats to generate (default: txt,json,srt,vtt)'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=1,
        help='Number of parallel workers to use [1-3] (default: 1)'
    )

    parser.add_argument(
        '--reset-tracking',
        action='store_true',
        help='Reset tracking data and start fresh'
    )
    
    args = parser.parse_args()
    
    # Validate folder path
    folder_path = Path(args.folder_path)
    if not folder_path.exists():
        print(f"❌ Error: Folder {folder_path} does not exist.")
        sys.exit(1)
    
    if not folder_path.is_dir():
        print(f"❌ Error: {folder_path} is not a directory.")
        sys.exit(1)

    if args.workers < 1 or args.workers > 3:
        print("❌ Error: --workers must be between 1 and 3.")
        sys.exit(1)
    
    # Set up tracking file
    tracking_file = folder_path / '.transcript_from_mp4s_tracking.json'
    
    # Reset tracking if requested
    if args.reset_tracking:
        if tracking_file.exists():
            tracking_file.unlink()
            print("🔄 Tracking data reset. Existing transcripts on disk will be re-generated and overwritten.")
        else:
            print("ℹ️  No tracking data to reset. Existing transcripts on disk will still be re-generated and overwritten.")
    
    # Load tracking data
    tracking_data = load_tracking_data(tracking_file)

    mlx_whisper_module = import_mlx_whisper()
    if mlx_whisper_module is None:
        sys.exit(1)

    hf_model = MODEL_REPOS[args.model]

    try:
        outputs = parse_outputs_arg(args.outputs)
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    supports_language = mlx_whisper_supports_language(mlx_whisper_module)
    if args.language and not supports_language:
        print("⚠️  Warning: Installed mlx-whisper does not appear to support the --language option. Continuing without it.")

    print(f"🤖 Using MLX Whisper model repo: {hf_model}")
    
    # Find all supported video files
    print(f"🔍 Scanning for supported media files in: {folder_path}")
    mp4_files = find_video_files(folder_path)
    
    if not mp4_files:
        print("❌ No supported media files found in the specified directory.")
        sys.exit(1)
    
    print(f"📁 Found {len(mp4_files)} video file(s)")

    metadata, duration_available = collect_video_metadata(mp4_files, tracking_data)
    print_pre_scan_summary(metadata, duration_available)

    total_files = len(metadata)
    already_completed_count = sum(1 for item in metadata if item['is_completed'])
    pending_metadata = [item for item in metadata if not item['is_completed']]
    pending_metadata_by_key = {item['tracking_key']: item for item in pending_metadata}
    total_remaining_size_bytes = sum(item['size_bytes'] for item in pending_metadata)
    total_remaining_duration_seconds = None
    if duration_available:
        total_remaining_duration_seconds = sum(item['duration_seconds'] for item in pending_metadata)
    
    batch_start_time = time.time()
    completed_this_run = 0
    failed_this_run = 0
    processed_size_bytes = 0
    processed_duration_seconds = 0.0
    print(f"👷 Workers: {args.workers}")

    tasks = []
    for item in pending_metadata:
        mp4_path = item['path']
        sanitized_name = sanitize_filename(mp4_path.name)
        output_folder = mp4_path.parent / sanitized_name
        use_direct_video = args.direct_video and mp4_path.suffix.lower() == '.mp4'
        tasks.append({
            'mp4_path': str(mp4_path),
            'tracking_key': item['tracking_key'],
            'output_folder': str(output_folder),
            'audio_path': str(output_folder / f"{sanitized_name}.mp3"),
            'transcript_base_path': str(output_folder / sanitized_name),
            'outputs': sorted(outputs),
            'direct_video_requested': args.direct_video,
            'use_direct_video': use_direct_video,
            'force_transcribe': args.reset_tracking,
            'hf_model': hf_model,
            'model_name': args.model,
            'language': args.language,
            'supports_language': supports_language,
        })

    def handle_result(result: dict) -> None:
        nonlocal completed_this_run, failed_this_run, processed_size_bytes, processed_duration_seconds, tracking_data

        mp4_path = Path(result['mp4_path'])
        tracking_key = result['tracking_key']
        print(f"\n{'='*60}")
        print(f"Finished: {mp4_path.name}")
        print(f"{'='*60}")

        if not result['success']:
            failed_this_run += 1
            print(f"❌ {result['error']}")
            return

        if result['action'] == 'existing_outputs':
            print("⏭️  Requested outputs already exist")
        elif result['direct_video_fallback']:
            print("⏭️  Requested --direct-video, but this file is not MP4. Falling back to extracted audio.")
        elif result['used_direct_video']:
            print("⏭️  Skipping audio extraction (--direct-video enabled)")

        tracking_data[tracking_key] = {
            'mp4_path': str(mp4_path),
            'output_folder': result['output_folder'],
            'completed': True,
            'processed_at': time.time()
        }
        save_tracking_data(tracking_file, tracking_data)

        print(f"✅ Completed processing: {mp4_path.name}")
        print(f"⏱️  Extraction time: {result['extraction_elapsed']:.2f}s")
        print(f"⏱️  Transcription time: {result['transcription_elapsed']:.2f}s")
        print(f"⏱️  Saving time: {result['save_elapsed']:.2f}s")
        print(f"⏱️  Total per-file time: {result['file_elapsed']:.2f}s")

        completed_this_run += 1
        metadata_item = pending_metadata_by_key.get(tracking_key)
        if metadata_item is not None:
            processed_size_bytes += metadata_item['size_bytes']
            if duration_available and metadata_item['duration_seconds'] is not None:
                processed_duration_seconds += metadata_item['duration_seconds']

        elapsed_batch_seconds = time.time() - batch_start_time
        remaining_files = len(pending_metadata) - completed_this_run
        remaining_size_bytes = max(0, total_remaining_size_bytes - processed_size_bytes)
        projected_remaining_seconds = 0.0

        if duration_available and processed_duration_seconds > 0 and total_remaining_duration_seconds is not None:
            avg_seconds_per_video_minute = elapsed_batch_seconds / (processed_duration_seconds / 60)
            remaining_duration_seconds = max(0.0, total_remaining_duration_seconds - processed_duration_seconds)
            projected_remaining_seconds = avg_seconds_per_video_minute * (remaining_duration_seconds / 60)
        elif processed_size_bytes > 0:
            avg_seconds_per_gb = elapsed_batch_seconds / (processed_size_bytes / (1024 ** 3))
            projected_remaining_seconds = avg_seconds_per_gb * (remaining_size_bytes / (1024 ** 3))
        elif completed_this_run > 0:
            avg_seconds_per_file = elapsed_batch_seconds / completed_this_run
            projected_remaining_seconds = avg_seconds_per_file * remaining_files

        print_batch_progress(
            total_files=total_files,
            already_completed_count=already_completed_count,
            completed_this_run=completed_this_run,
            elapsed_batch_seconds=elapsed_batch_seconds,
            processed_size_bytes=processed_size_bytes,
            total_remaining_size_bytes=total_remaining_size_bytes,
            projected_remaining_seconds=projected_remaining_seconds,
            processed_duration_seconds=processed_duration_seconds,
            total_remaining_duration_seconds=total_remaining_duration_seconds,
        )

    if args.workers == 1:
        for task in tasks:
            handle_result(process_single_video(task))
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            future_to_task = {executor.submit(process_single_video, task): task for task in tasks}
            for future in as_completed(future_to_task):
                try:
                    handle_result(future.result())
                except Exception as e:
                    failed_this_run += 1
                    task = future_to_task[future]
                    print(f"\n{'='*60}")
                    print(f"Finished: {Path(task['mp4_path']).name}")
                    print(f"{'='*60}")
                    print(f"❌ Worker crashed: {e}")
    
    total_elapsed = time.time() - batch_start_time
    print(f"\n{'='*60}")
    if failed_this_run:
        print("⚠️  Batch finished with some failures.")
    else:
        print("🎉 All video files processed successfully!")
    print(f"⏱️  Total batch processing time: {total_elapsed:.2f}s")
    print(f"✅ Completed this run: {completed_this_run}")
    if failed_this_run:
        print(f"⚠️  Failed this run: {failed_this_run}")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
