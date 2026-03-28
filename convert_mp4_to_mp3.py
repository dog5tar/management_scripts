#!/usr/bin/env python

import os
import sys
import json
import argparse
from pathlib import Path
import subprocess

def check_conda_environment():
    """Check if we're running in the correct conda environment."""
    required_env = "management_scripts"
    
    # Check CONDA_DEFAULT_ENV environment variable
    current_env = os.environ.get('CONDA_DEFAULT_ENV')
    
    if current_env != required_env:
        print(f"Error: This script must be run in the '{required_env}' conda environment.")
        print(f"Current environment: {current_env or 'None'}")
        print(f"\nPlease activate the correct environment with:")
        print(f"conda activate {required_env}")
        sys.exit(1)
    
    # Only show success message in verbose mode or remove it entirely
    # print(f"✓ Running in correct conda environment: {current_env}")

def load_tracking_data(tracking_file):
    """Load tracking data from the hidden file."""
    if tracking_file.exists():
        try:
            with open(tracking_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            print(f"Warning: Could not read tracking file {tracking_file}. Starting fresh.")
    return {}

def save_tracking_data(tracking_file, data):
    """Save tracking data to the hidden file."""
    try:
        with open(tracking_file, 'w') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save tracking data: {e}")

def convert_mp4_to_mp3(mp4_path, mp3_path):
    """Convert MP4 file to MP3 using ffmpeg."""
    try:
        # Use ffmpeg to convert MP4 to MP3
        cmd = [
            'ffmpeg',
            '-i', str(mp4_path),
            '-vn',  # No video
            '-acodec', 'libmp3lame',
            '-ab', '192k',  # Audio bitrate
            '-ar', '44100',  # Audio sample rate
            '-y',  # Overwrite output file if it exists
            str(mp3_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return True, "Success"
        else:
            return False, f"ffmpeg error: {result.stderr}"
            
    except FileNotFoundError:
        return False, "ffmpeg not found. Please install ffmpeg first."
    except Exception as e:
        return False, f"Conversion error: {str(e)}"

def find_mp4_files(directory):
    """Recursively find all MP4 and MOV files in the directory."""
    mp4_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            # Support both .mp4 and .mov
            if file.lower().endswith(('.mp4', '.mov')):
                mp4_files.append(Path(root) / file)
    return mp4_files

def get_tracking_key(mp4_path):
    """Generate a unique tracking key for the file."""
    return str(mp4_path.resolve())

def main():
    # Check conda environment first
    check_conda_environment()
    
    parser = argparse.ArgumentParser(description='Convert MP4/MOV files to MP3 recursively')
    parser.add_argument('directory', nargs='?', help='Directory to search for MP4/MOV files')
    parser.add_argument('--reset-tracking', action='store_true', 
                       help='Reset tracking file and start fresh')
    
    args = parser.parse_args()
    
    # Get directory from user if not provided
    if not args.directory:
        directory = input("Enter the directory to search for MP4/MOV files: ").strip()
        if not directory:
            print("No directory specified. Exiting.")
            sys.exit(1)
    else:
        directory = args.directory
    
    # Validate directory
    directory_path = Path(directory)
    if not directory_path.exists():
        print(f"Error: Directory '{directory}' does not exist.")
        sys.exit(1)
    
    if not directory_path.is_dir():
        print(f"Error: '{directory}' is not a directory.")
        sys.exit(1)
    
    # Set up tracking file
    tracking_file = directory_path / '.convert_mp4_to_mp3_tracking.json'
    
    # Reset tracking if requested
    if args.reset_tracking:
        if tracking_file.exists():
            tracking_file.unlink()
            print("Tracking file reset.")
        else:
            print("No tracking file found to reset.")
    
    # Load tracking data
    tracking_data = load_tracking_data(tracking_file)
    
    # Find all MP4/MOV files
    print(f"Searching for MP4/MOV files in '{directory_path}'...")
    mp4_files = find_mp4_files(directory_path)
    
    if not mp4_files:
        print("No MP4/MOV files found.")
        return
    
    print(f"Found {len(mp4_files)} video file(s).")
    
    converted_count = 0
    skipped_count = 0
    error_count = 0
    
    for mp4_file in mp4_files:
        mp3_file = mp4_file.with_suffix('.mp3')
        tracking_key = get_tracking_key(mp4_file)
        
        # Check if already processed
        if tracking_key in tracking_data:
            print(f"SKIPPED (already processed): {mp4_file.name}")
            skipped_count += 1
            continue
        
        # Check if MP3 already exists
        if mp3_file.exists():
            print(f"SKIPPED (MP3 exists): {mp4_file.name} -> {mp3_file.name}")
            # Mark as processed in tracking
            tracking_data[tracking_key] = {
                'mp4_path': str(mp4_file),
                'mp3_path': str(mp3_file),
                'status': 'skipped_existing',
                'timestamp': str(Path(mp3_file).stat().st_mtime)
            }
            skipped_count += 1
            continue
        
        print(f"Converting: {mp4_file.name} -> {mp3_file.name}")
        
        # Convert the file
        success, message = convert_mp4_to_mp3(mp4_file, mp3_file)
        
        if success:
            print(f"SUCCESS: {mp3_file.name}")
            tracking_data[tracking_key] = {
                'mp4_path': str(mp4_file),
                'mp3_path': str(mp3_file),
                'status': 'converted',
                'timestamp': str(Path(mp3_file).stat().st_mtime)
            }
            converted_count += 1
        else:
            print(f"ERROR: {mp4_file.name} - {message}")
            tracking_data[tracking_key] = {
                'mp4_path': str(mp4_file),
                'mp3_path': str(mp3_file),
                'status': 'error',
                'error_message': message,
                'timestamp': None
            }
            error_count += 1
        
        # Save tracking data after each file
        save_tracking_data(tracking_file, tracking_data)
    
    # Summary
    print("\n" + "="*50)
    print("CONVERSION SUMMARY")
    print("="*50)
    print(f"Total MP4 files found: {len(mp4_files)}")
    print(f"Successfully converted: {converted_count}")
    print(f"Skipped (already done): {skipped_count}")
    print(f"Errors: {error_count}")
    print(f"\nTracking file: {tracking_file}")
    
    if error_count > 0:
        print("\nNote: Some files failed to convert. Check the error messages above.")
        print("Make sure ffmpeg is installed and the MP4 files are not corrupted.")

if __name__ == '__main__':
    main()