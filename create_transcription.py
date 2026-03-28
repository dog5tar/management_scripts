#!/usr/bin/env python
"""
Podcast Transcription Script

This script downloads podcast episodes from RSS feeds and transcribes them using OpenAI Whisper.
It maintains state for resuming interrupted sessions.

Usage:
    python create_transcription.py [--refresh]
    
Options:
    --refresh    Reset all progress and start fresh
"""

import os
import sys
import json
import requests
import feedparser
import whisper
from pathlib import Path
from urllib.parse import urlparse
from tqdm import tqdm
import time
import argparse
import re

# Check conda environment
if os.environ.get("CONDA_DEFAULT_ENV") != "management_scripts":
    print("❌ Error: Please activate the 'management_scripts' conda environment before running this script.")
    sys.exit(1)

def sanitize_filename(title):
    """Sanitize episode title for use as filename"""
    # Remove or replace invalid characters for filenames
    sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
    # Replace multiple spaces with single space
    sanitized = re.sub(r'\s+', ' ', sanitized)
    # Remove leading/trailing spaces
    sanitized = sanitized.strip()
    # Limit length to avoid filesystem issues
    if len(sanitized) > 100:
        sanitized = sanitized[:100].rsplit(' ', 1)[0]  # Cut at word boundary
    return sanitized

def load_or_create_state(state_file):
    """Load existing state or create new one"""
    if os.path.exists(state_file):
        with open(state_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"episodes": [], "processed_count": 0, "download_phase_complete": False}

def save_state(state, state_file):
    """Save current state to file"""
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def parse_rss_feed(rss_url):
    """Parse RSS feed and extract episode information"""
    print(f"🔍 Parsing RSS feed: {rss_url}")
    feed = feedparser.parse(rss_url)
    
    if feed.bozo:
        print("⚠️ Warning: RSS feed may have issues")
    
    episodes = []
    for i, entry in enumerate(feed.entries):
        title = getattr(entry, 'title', f'Unknown Title {i+1}')
        episode = {
            "title": title,
            "description": getattr(entry, 'description', ''),
            "published": getattr(entry, 'published', ''),
            "link": getattr(entry, 'link', ''),
            "mp3_url": None,
            "mp3_path": None,
            "transcription_paths": {},
            "transcription": None,
            "downloaded": False,
            "transcribed": False,
            "filename_base": sanitize_filename(title)
        }
        
        # Find MP3 URL
        for link in getattr(entry, 'links', []):
            if link.get('type', '').startswith('audio/'):
                episode["mp3_url"] = link.get('href')
                break
        
        # Fallback: check enclosures
        if not episode["mp3_url"] and hasattr(entry, 'enclosures'):
            for enclosure in entry.enclosures:
                if enclosure.get('type', '').startswith('audio/'):
                    episode["mp3_url"] = enclosure.get('href')
                    break
        
        if episode["mp3_url"]:
            episodes.append(episode)
    
    return episodes

def download_mp3(url, output_path):
    """Download MP3 file with progress bar"""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(output_path, 'wb') as f, tqdm(
            desc=f"Downloading {output_path.name}",
            total=total_size,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
        ) as pbar:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
        
        print(f"✅ Downloaded: {output_path.name}")
        return True
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return False

def transcribe_audio(audio_path, model_name="base"):
    """Transcribe audio file using Whisper and return full result"""
    try:
        print(f"🎤 Transcribing {audio_path.name} with {model_name} model...")
        model = whisper.load_model(model_name)
        result = model.transcribe(str(audio_path))
        return result
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        return None

def save_transcription_formats(result, base_path):
    """Save transcription in multiple formats"""
    formats_saved = {}
    
    try:
        # Save as plain text
        txt_path = f"{base_path}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(result["text"])
        formats_saved["txt"] = txt_path
        
        # Save as JSON (full Whisper result)
        json_path = f"{base_path}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        formats_saved["json"] = json_path
        
        # Save as SRT subtitles
        if "segments" in result:
            srt_path = f"{base_path}.srt"
            with open(srt_path, 'w', encoding='utf-8') as f:
                for i, segment in enumerate(result["segments"], 1):
                    start_time = format_timestamp(segment["start"])
                    end_time = format_timestamp(segment["end"])
                    f.write(f"{i}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{segment['text'].strip()}\n\n")
            formats_saved["srt"] = srt_path
            
            # Save as VTT subtitles
            vtt_path = f"{base_path}.vtt"
            with open(vtt_path, 'w', encoding='utf-8') as f:
                f.write("WEBVTT\n\n")
                for segment in result["segments"]:
                    start_time = format_timestamp(segment["start"], vtt_format=True)
                    end_time = format_timestamp(segment["end"], vtt_format=True)
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{segment['text'].strip()}\n\n")
            formats_saved["vtt"] = vtt_path
        
        return formats_saved
    except Exception as e:
        print(f"❌ Error saving transcription formats: {e}")
        return {}

def format_timestamp(seconds, vtt_format=False):
    """Format timestamp for subtitle files"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    
    if vtt_format:
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    else:
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}".replace('.', ',')

def reset_progress(state_file, output_dir):
    """Reset all progress and clean up files"""
    print("🔄 Resetting progress...")
    
    # Remove state file
    if os.path.exists(state_file):
        os.remove(state_file)
        print("✅ Removed state file")
    
    # Remove podcast data file
    podcast_data_file = output_dir / "podcast_data.json"
    if os.path.exists(podcast_data_file):
        os.remove(podcast_data_file)
        print("✅ Removed podcast data file")
    
    # Optionally remove all downloaded files (ask user)
    response = input("🗑️ Do you want to delete all downloaded MP3 and transcription files? (y/N): ").strip().lower()
    if response in ['y', 'yes']:
        for file_path in output_dir.glob("*"):
            if file_path.is_file() and file_path.name not in ["podcast_data.json", "transcription_state.json"]:
                file_path.unlink()
        print("✅ Removed all downloaded files")
    
    print("🔄 Progress reset complete!")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Podcast Transcription Script')
    parser.add_argument('--refresh', action='store_true', 
                       help='Reset all progress and start fresh')
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path("podcast_transcriptions")
    output_dir.mkdir(exist_ok=True)
    
    state_file = output_dir / "transcription_state.json"
    
    # Handle refresh flag
    if args.refresh:
        reset_progress(state_file, output_dir)
    
    # Get RSS feed URL
    rss_url = input("🎙️ Enter podcast RSS feed URL: ").strip()
    if not rss_url:
        print("❌ RSS URL is required")
        sys.exit(1)
    
    # Load or create state
    state = load_or_create_state(state_file)
    
    # Parse RSS feed if starting fresh
    if not state["episodes"]:
        episodes = parse_rss_feed(rss_url)
        state["episodes"] = episodes
        save_state(state, state_file)
        print(f"✅ Found {len(episodes)} episodes with MP3 files")
    else:
        print(f"📂 Resuming from previous session")
    
    # Phase 1: Download all MP3 files
    if not state.get("download_phase_complete", False):
        print("\n🔽 Phase 1: Downloading all MP3 files...")
        
        for i, episode in enumerate(state["episodes"]):
            if episode.get("downloaded"):
                continue
            
            print(f"\n📻 Downloading episode {i+1}/{len(state['episodes'])}: {episode['title'][:50]}...")
            
            # Use episode title as filename
            filename_base = episode.get("filename_base", sanitize_filename(episode["title"]))
            mp3_filename = f"{filename_base}.mp3"
            mp3_path = output_dir / mp3_filename
            
            # Handle duplicate filenames
            counter = 1
            original_path = mp3_path
            while mp3_path.exists() and not episode.get("downloaded"):
                mp3_filename = f"{filename_base}_{counter}.mp3"
                mp3_path = output_dir / mp3_filename
                counter += 1
            
            # Download MP3
            if not mp3_path.exists():
                if not download_mp3(episode["mp3_url"], mp3_path):
                    continue
            
            episode["mp3_path"] = str(mp3_path)
            episode["downloaded"] = True
            
            # Save progress
            save_state(state, state_file)
        
        state["download_phase_complete"] = True
        save_state(state, state_file)
        print("\n✅ Download phase complete!")
    
    # Phase 2: Transcribe all downloaded files
    print("\n🎤 Phase 2: Transcribing all downloaded files...")
    whisper_model = input("\nWhisper model (tiny/base/small/medium/large) [base]: ").strip() or "base"
    
    for i, episode in enumerate(state["episodes"]):
        if episode.get("transcribed") or not episode.get("downloaded"):
            continue
        
        print(f"\n🎤 Transcribing episode {i+1}/{len(state['episodes'])}: {episode['title'][:50]}...")
        
        mp3_path = Path(episode["mp3_path"])
        base_transcription_path = output_dir / mp3_path.stem
        
        # Check if any transcription files exist
        existing_formats = {}
        for fmt in ["txt", "json", "srt", "vtt"]:
            fmt_path = f"{base_transcription_path}.{fmt}"
            if os.path.exists(fmt_path):
                existing_formats[fmt] = fmt_path
        
        if existing_formats:
            episode["transcription_paths"] = existing_formats
            # Load text transcription if available
            txt_path = existing_formats.get("txt")
            if txt_path:
                with open(txt_path, 'r', encoding='utf-8') as f:
                    episode["transcription"] = f.read()
        else:
            # Transcribe
            result = transcribe_audio(mp3_path, whisper_model)
            if result:
                # Save in multiple formats
                formats_saved = save_transcription_formats(result, str(base_transcription_path))
                episode["transcription_paths"] = formats_saved
                episode["transcription"] = result["text"]
        
        episode["transcribed"] = True
        state["processed_count"] += 1
        
        # Save progress
        save_state(state, state_file)
        print(f"✅ Completed transcription {i+1}")
    
    # Save final JSON
    final_output = output_dir / "podcast_data.json"
    with open(final_output, 'w', encoding='utf-8') as f:
        json.dump(state["episodes"], f, indent=2, ensure_ascii=False)
    
    print(f"\n🎉 All episodes processed! Data saved to {final_output}")
    print(f"📁 MP3 files and transcriptions in: {output_dir}")
    print("\n📄 Transcription formats saved:")
    print("   • .txt - Plain text transcription")
    print("   • .json - Full Whisper result with timestamps")
    print("   • .srt - SRT subtitle format")
    print("   • .vtt - WebVTT subtitle format")

if __name__ == "__main__":
    main()