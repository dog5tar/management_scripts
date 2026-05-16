#!/usr/bin/env python

"""
Transcript from Videos Script

This script takes a folder path as input, scans for MP4/MOV files recursively,
extracts audio from each video file, and creates transcripts using OpenAI's Whisper.
Each transcript is saved in its own folder named after the video file.

Features:
- Conda environment check (requires 'management_scripts' environment)
- Recursive MP4/MOV file scanning
- Audio extraction using ffmpeg
- Transcription using Whisper
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
from tqdm import tqdm
import time
import re

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
    
    supported_extensions = {".mp4", ".mov"}
    for video_file in directory_path.rglob("*"):
        if video_file.is_file() and video_file.suffix.lower() in supported_extensions:
            video_files.append(video_file)
    
    return sorted(video_files)

def extract_audio_from_mp4(mp4_path, audio_path):
    """Extract audio from MP4 file using ffmpeg."""
    try:
        print(f"🎵 Extracting audio from: {mp4_path.name}")
        
        # Use ffmpeg to extract audio
        cmd = [
            'ffmpeg',
            '-i', str(mp4_path),
            '-vn',  # No video
            '-acodec', 'libmp3lame',  # Use MP3 codec
            '-ab', '192k',  # Audio bitrate
            '-ar', '44100',  # Sample rate
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
        
        print(f"✅ Audio extracted: {audio_path.name}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Audio extraction failed for {mp4_path.name}: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during audio extraction: {e}")
        return False

def transcribe_audio(audio_path, model_name="base"):
    """Transcribe audio file using Whisper and return full result"""
    try:
        # Import whisper here, after conda environment check
        import whisper
        
        print(f"🎤 Transcribing {audio_path.name} with {model_name} model...")
        
        # Load Whisper model
        model = whisper.load_model(model_name)
        
        # Transcribe the audio
        result = model.transcribe(str(audio_path))
        
        print(f"✅ Transcription completed: {audio_path.name}")
        return result
        
    except Exception as e:
        print(f"❌ Transcription failed for {audio_path.name}: {e}")
        return None

def save_transcription_formats(result, base_path):
    """Save transcription in multiple formats (txt, json, srt, vtt)"""
    try:
        # Save as plain text
        txt_path = Path(str(base_path) + '.txt')
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(result['text'])
        print(f"💾 Saved transcript: {txt_path.name}")
        
        # Save as JSON (full result with segments and metadata)
        json_path = Path(str(base_path) + '.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved JSON: {json_path.name}")
        
        # Save as SRT (SubRip subtitle format)
        srt_path = Path(str(base_path) + '.srt')
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(result['segments'], 1):
                start_time = format_timestamp(segment['start'])
                end_time = format_timestamp(segment['end'])
                f.write(f"{i}\n{start_time} --> {end_time}\n{segment['text'].strip()}\n\n")
        print(f"💾 Saved SRT: {srt_path.name}")
        
        # Save as VTT (WebVTT subtitle format)
        vtt_path = Path(str(base_path) + '.vtt')
        with open(vtt_path, 'w', encoding='utf-8') as f:
            f.write("WEBVTT\n\n")
            for segment in result['segments']:
                start_time = format_timestamp(segment['start'], vtt_format=True)
                end_time = format_timestamp(segment['end'], vtt_format=True)
                f.write(f"{start_time} --> {end_time}\n{segment['text'].strip()}\n\n")
        print(f"💾 Saved VTT: {vtt_path.name}")
        
        return True
        
    except Exception as e:
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
    """Sanitize filename for file system compatibility"""
    # Remove file extension
    name = Path(filename).stem
    
    # Replace problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    
    # Limit length
    if len(sanitized) > 200:
        sanitized = sanitized[:200].strip()
    
    return sanitized

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
        description="Extract audio from MP4/MOV files and create transcripts using Whisper",
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
        help='Path to folder containing MP4/MOV files'
    )
    
    parser.add_argument(
        '--model',
        default='base',
        choices=['tiny', 'base', 'small', 'medium', 'large'],
        help='Whisper model to use (default: base)'
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
    
    # Set up tracking file
    tracking_file = folder_path / '.transcript_from_mp4s_tracking.json'
    
    # Reset tracking if requested
    if args.reset_tracking:
        if tracking_file.exists():
            tracking_file.unlink()
            print("🔄 Tracking data reset.")
        else:
            print("ℹ️  No tracking data to reset.")
    
    # Load tracking data
    tracking_data = load_tracking_data(tracking_file)
    
    # Find all supported video files
    print(f"🔍 Scanning for MP4/MOV files in: {folder_path}")
    mp4_files = find_video_files(folder_path)
    
    if not mp4_files:
        print("❌ No MP4/MOV files found in the specified directory.")
        sys.exit(1)
    
    print(f"📁 Found {len(mp4_files)} video file(s)")
    
    # Process each MP4 file
    for i, mp4_path in enumerate(mp4_files, 1):
        print(f"\n{'='*60}")
        print(f"Processing {i}/{len(mp4_files)}: {mp4_path.name}")
        print(f"{'='*60}")
        
        tracking_key = get_tracking_key(mp4_path)
        
        # Check if already processed
        if tracking_key in tracking_data and tracking_data[tracking_key].get('completed', False):
            print(f"⏭️  Already processed: {mp4_path.name}")
            continue
        
        # Create output folder named after the MP4 file, next to the MP4
        sanitized_name = sanitize_filename(mp4_path.name)
        output_folder = mp4_path.parent / sanitized_name
        output_folder.mkdir(exist_ok=True)
        
        # Define file paths
        audio_path = output_folder / f"{sanitized_name}.mp3"
        transcript_base_path = output_folder / sanitized_name
        
        # Step 1: Extract audio (if not already done)
        audio_extracted = False
        if audio_path.exists():
            print(f"⏭️  Audio already exists: {audio_path.name}")
            audio_extracted = True
        else:
            audio_extracted = extract_audio_from_mp4(mp4_path, audio_path)
        
        if not audio_extracted:
            print(f"❌ Skipping transcription for {mp4_path.name} due to audio extraction failure")
            continue
        
        # Step 2: Transcribe audio (if not already done)
        transcript_txt_path = Path(str(transcript_base_path) + '.txt')
        if transcript_txt_path.exists():
            print(f"⏭️  Transcript already exists: {transcript_txt_path.name}")
        else:
            result = transcribe_audio(audio_path, args.model)
            if result:
                save_transcription_formats(result, transcript_base_path)
            else:
                print(f"❌ Skipping save for {mp4_path.name} due to transcription failure")
                continue
        
        # Mark as completed in tracking
        tracking_data[tracking_key] = {
            'mp4_path': str(mp4_path),
            'output_folder': str(output_folder),
            'completed': True,
            'processed_at': time.time()
        }
        
        # Save tracking data
        save_tracking_data(tracking_file, tracking_data)
        
        print(f"✅ Completed processing: {mp4_path.name}")
    
    print(f"\n{'='*60}")
    print("🎉 All video files processed successfully!")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()
