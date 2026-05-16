# Management Scripts Collection

A comprehensive collection of Python scripts for content management, data processing, and media automation tasks. These scripts are designed to streamline workflows for podcast production, YouTube content creation, Reddit analysis, and keyword research.

## 📋 Table of Contents

- [Environment Setup](#environment-setup)
- [Core Scripts](#core-scripts)
  - [Audio Processing](#audio-processing)
  - [Video & Media Conversion](#video--media-conversion)
  - [Transcription & Content Analysis](#transcription--content-analysis)
  - [Data Processing & CSV Tools](#data-processing--csv-tools)
  - [Reddit Analysis Tools](#reddit-analysis-tools)
  - [YouTube Content Tools](#youtube-content-tools)
- [Directory Structure](#directory-structure)
- [Usage Guidelines](#usage-guidelines)
- [Dependencies](#dependencies)

## 🛠️ Environment Setup

**Required:** All scripts must be run within `management_scripts` conda environment.

```bash
conda activate management_scripts
```

Most scripts will automatically check for the correct environment and exit if not running in `management_scripts`.

## 🎯 Core Scripts

### 🎵 Audio Processing

#### `audacity_labels.py`
**Purpose:** Batch-create speech and non-speech labels for WAV files using AI voice activity detection.

**Features:**
- Uses PyAnnote audio VAD to detect speech segments
- Generates both speech and non-speech label files
- Configurable minimum segment durations and gap merging
- Optimized for Audacity workflow integration

**Usage:**
```bash
python audacity_labels.py
```

**Requirements:**
- Hugging Face token (set as `HF_TOKEN` environment variable)
- WAV files should be noise-gated in Audacity first for best results

**Outputs:**
- `<filename>_speech_labels.txt`
- `<filename>_nonspeech_labels.txt`

---

### 🎬 Video & Media Conversion

#### `convert_mp4_to_mp3.py`
**Purpose:** Convert MP4/MOV video files to MP3 audio format with progress tracking.

**Features:**
- Recursive directory scanning for video files
- Progress tracking with JSON state file
- Resumable conversion (skips already processed files)
- Supports both MP4 and MOV formats

**Usage:**
```bash
# Interactive mode
python convert_mp4_to_mp3.py

# Direct directory
python convert_mp4_to_mp3.py /path/to/videos

# Reset tracking
python convert_mp4_to_mp3.py --reset-tracking
```

**Requirements:**
- ffmpeg must be installed and accessible in PATH

---

#### `transcript_from_videos.py`
**Purpose:** Extract audio from MP4/MOV files and create transcriptions using OpenAI Whisper.

**Features:**
- Recursive MP4/MOV file scanning
- Audio extraction using ffmpeg with 192k bitrate
- Transcription using Whisper with multiple model options
- Multiple output formats (TXT, JSON, SRT, VTT)
- Progress tracking and resume capability
- Creates separate output folder for each video file

**Usage:**
```bash
# Basic usage
python transcript_from_videos.py /path/to/folder/with/videos

# With specific Whisper model
python transcript_from_videos.py /path/to/folder/with/videos --model large

# Reset tracking and start fresh
python transcript_from_videos.py /path/to/folder/with/videos --reset-tracking
```

**Available Flags:**
- `--model`: Whisper model size (tiny, base, small, medium, large) [default: base]
- `--reset-tracking`: Reset progress tracking and start fresh

**Outputs:**
- For each video file: creates `<filename>/` folder (sanitized) containing:
  - `<filename>.mp3` (extracted audio)
  - `<filename>.txt` (plain text transcript)
  - `<filename>.json` (full Whisper result with segments)
  - `<filename>.srt` (SRT subtitle format)
  - `<filename>.vtt` (WebVTT subtitle format)

**Requirements:**
- ffmpeg must be installed and accessible in PATH
- OpenAI Whisper installed
- `management_scripts` conda environment

**Tracking:**
- Uses `.transcript_from_mp4s_tracking.json` in source folder
- Resumable processing (skips already completed files)

---

### 📝 Transcription & Content Analysis

#### `create_transcription.py`
**Purpose:** Download podcast episodes from RSS feeds and transcribe them using OpenAI Whisper.

**Features:**
- RSS feed parsing and episode downloading
- Multi-format transcription output (TXT, JSON, SRT, VTT)
- Resumable processing with state tracking
- Support for different Whisper model sizes

**Usage:**
```bash
python create_transcription.py [--refresh]
```

**Outputs:**
- `podcast_transcriptions/` directory with:
  - MP3 files
  - Transcriptions in multiple formats
  - `podcast_data.json` with all episode data

**Requirements:**
- OpenAI Whisper installed
- Internet connection for RSS feed access

---

#### `speech_nonspeech_labels.py`
**Purpose:** Alternative speech/non-speech labeling tool with different configuration options.

**Usage:**
```bash
python speech_nonspeech_labels.py
```

---

### 📊 Data Processing & CSV Tools

#### `csv_column_to_txt.py`
**Purpose:** Extract columns from CSV files and save as comma-separated text files.

**Features:**
- Interactive column selection
- Automatic processing for keyword/competition/volume columns
- Duplicate removal and order preservation
- Comprehensive logging and error handling

**Usage:**
```bash
# Interactive mode
python csv_column_to_txt.py

# With specific file
python csv_column_to_txt.py --file mydata.csv

# Debug mode
python csv_column_to_txt.py --debug
```

**Auto-processing Mode:** Automatically detects and processes CSVs with "Keyword", "Competition", and "Search volume" columns.

---

#### `extract_keywords.py`
**Purpose:** Extract keywords from CSV columns, filtering out entries containing commas.

**Features:**
- Preview functionality before extraction
- Filters out keywords with commas (for compatibility)
- Simple, user-friendly interface

**Usage:**
```bash
python extract_keywords.py
```

---

#### `merge_keywords.py`
**Purpose:** Merge multiple CSV files in a directory into a single keywords.csv file.

**Usage:**
```bash
python merge_keywords.py
```

---

#### `combine_vidiq_csvs.py`
**Purpose:** Combine VidIQ CSV exports by suffix type (matching_terms, question_keywords, related_keywords).

**Features:**
- Validates CSV naming conventions
- Header consistency checking
- Creates three combined output files

**Usage:**
```bash
python combine_vidiq_csvs.py [folder_path]
```

**Outputs:**
- `combined_matching_terms.csv`
- `combined__question_keywords.csv`
- `combined_related_keywords.csv`

---

#### `semantic_clustering.py`
**Purpose:** Perform semantic clustering analysis on text data.

**Usage:**
```bash
python semantic_clustering.py
```

---

### 📰 Reddit Analysis Tools

#### `reddit_scraper.py`
**Purpose:** Scrape comments from Reddit posts using public JSON API (no authentication required).

**Features:**
- Batch processing of multiple URLs
- Recursive comment extraction
- JSON output with full comment threads
- Rate limiting for respectful scraping

**Usage:**
```bash
# Single URL
python reddit_scraper.py "https://reddit.com/r/subreddit/comments/post_id/title/"

# Multiple URLs
python reddit_scraper.py url1 url2 url3

# From file
python reddit_scraper.py -f urls.txt

# With output directory
python reddit_scraper.py -f urls.txt -o output_folder
```

**Outputs:**
- JSON files with post and comment data
- Preserves comment hierarchy and metadata

---

#### `podcast_questions_generator.py`
**Purpose:** Generate podcast questions from Reddit discussions by analyzing themes, controversies, and common questions.

**Features:**
- Thematic analysis of discussions
- Controversial topic identification
- Career stage categorization
- PDF output structured for AI agents

**Usage:**
```bash
# Process all JSON files in directory
python podcast_questions_generator.py

# Specific files
python podcast_questions_generator.py -f file1.json file2.json

# Custom output
python podcast_questions_generator.py -o my_podcast_guide.pdf
```

**Outputs:**
- `podcast_questions_guide.pdf` with:
  - Executive summary for podcast planning
  - Major themes for episode topics
  - Controversial topics for engaging discussions
  - Common questions and pain points
  - Career stage-specific questions
  - Detailed case studies

---

### 🎥 YouTube Content Tools

#### `youtube_videos_for_episode_outline.py`
**Purpose:** Comprehensive YouTube video analysis for podcast episode planning using yt-dlp.

**Features:**
- Extracts video metadata, descriptions, and transcripts
- Downloads all comments (no caps)
- Generates AI-friendly markdown packets
- Optional PDF conversion via Pandoc

**Usage:**
```bash
python youtube_videos_for_episode_outline.py input.csv [--sub-langs "en,en.*"]
```

**Input Format:** CSV with columns `title,link`

**Outputs:**
- `out/videos/` directory with per-video folders containing:
  - Video info JSON
  - Description text
  - Transcripts/subtitles (SRT format)
  - All comments JSON
- `AI_Packet_*.md` with structured analysis
- Optional PDF version

**Requirements:**
- yt-dlp must be installed and in PATH
- Optional: Pandoc for PDF conversion

---

### 📄 Document Generation

#### `merge_post_templates_to_pdf.py`
**Purpose:** Merge multiple text files into a single PDF document.

**Usage:**
```bash
python merge_post_templates_to_pdf.py
```

**Features:**
- Processes all .txt files in a directory
- Creates PDF with filename-based section headers
- A4 formatting with proper margins

---

#### `split_ask_the_public_to_500.py`
**Purpose:** Split large datasets into chunks of 500 items.

**Usage:**
```bash
python split_ask_the_public_to_500.py
```

---

## 📁 Directory Structure

```
management_scripts/
├── README.md                           # This file
├── .gitignore                          # Excludes large folders
├── audacity_labels.py                  # Audio labeling with PyAnnote
├── combine_vidiq_csvs.py               # VidIQ CSV combination
├── convert_mp4_to_mp3.py               # Video to audio conversion
├── create_transcription.py             # Podcast transcription
├── csv_column_to_txt.py                # CSV column extraction
├── extract_keywords.py                 # Keyword extraction
├── merge_keywords.py                   # CSV merging
├── merge_post_templates_to_pdf.py      # PDF generation
├── semantic_clustering.py              # Text clustering analysis
├── speech_nonspeech_labels.py          # Alternative audio labeling
├── split_ask_the_public_to_500.py     # Data splitting utility
├── transcript_from_videos.py           # MP4/MOV transcription
├── reddit-comments/                    # Reddit analysis tools & data
│   ├── podcast_questions_generator.py  # Podcast question generation
│   ├── reddit_scraper.py              # Reddit scraper
│   └── *.json                         # Scraped Reddit data
└── youtube/                           # YouTube analysis tools
    ├── youtube_videos_for_episode_outline.py  # YouTube video analysis
    ├── out/                           # Analysis outputs
    └── *.csv                          # Input data
```

## 📖 Usage Guidelines

### General Best Practices

1. **Environment:** Always activate `management_scripts` conda environment first
2. **Backups:** Create backups of important data before running processing scripts
3. **Testing:** Test scripts on small datasets first
4. **Monitoring:** Monitor script progress, especially for long-running operations

### Script Categories

- **Batch Processing:** Most scripts support batch operations on directories
- **Resumable Operations:** Many scripts include progress tracking and can be resumed
- **Interactive vs CLI:** Most scripts offer both interactive and command-line interfaces
- **Output Formats:** Scripts generate multiple output formats for different use cases

### Error Handling

- Scripts include comprehensive error handling and user-friendly messages
- Check dependencies before running (ffmpeg, yt-dlp, etc.)
- Verify input file formats and permissions
- Monitor log files for detailed debugging information

## 🔧 Dependencies

### Core Requirements
- Python 3.7+
- Conda environment `management_scripts`

### External Tools
- **ffmpeg:** Required for video/audio conversion
- **yt-dlp:** Required for YouTube video analysis
- **pandoc:** Optional for PDF conversion

### Python Packages
- pandas (CSV processing)
- requests (web scraping)
- feedparser (RSS parsing)
- whisper (speech recognition)
- pyannote.audio (voice activity detection)
- reportlab (PDF generation)
- torch/torchaudio (audio processing)
- tqdm (progress bars)

### API Keys
- **Hugging Face Token:** Required for PyAnnote audio processing
- Set as environment variable: `export HF_TOKEN=your_token_here`

---

## 🚀 Quick Start Examples

### Process YouTube Videos for Podcast Planning
```bash
conda activate management_scripts
python youtube/youtube_videos_for_episode_outline.py video_list.csv
```

### Extract Keywords from CSV
```bash
conda activate management_scripts
python csv_column_to_txt.py --file keywords.csv
```

### Scrape Reddit for Podcast Questions
```bash
conda activate management_scripts
python reddit-comments/reddit_scraper.py -f reddit_urls.txt -o reddit_data
python reddit-comments/podcast_questions_generator.py -d reddit_data
```

### Convert Videos to Audio
```bash
conda activate management_scripts
python convert_mp4_to_mp3.py /path/to/video/folder
```

---

## 📞 Support

For issues or questions:
1. Check script's help text (`python script.py --help`)
2. Verify all dependencies are installed
3. Ensure correct conda environment is active
4. Check file permissions and paths

---

*Last updated: March 2026*
