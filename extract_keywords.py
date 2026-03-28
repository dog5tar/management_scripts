#!/usr/bin/env python
"""
extract_keywords.py

This script extracts keywords from a specified column in a CSV file, skipping any keywords containing commas, and saves the valid keywords to a .txt file separated by commas.

Usage:
 1. Make the script executable:
    chmod +x ./extract_keywords.py
 2. Run the script:
    ./extract_keywords.py
 3. Follow the prompts to provide the CSV file path, keyword column name, and output file location.

Requirements:
 - Must be run inside the 'management_scripts' conda environment.
"""
import os
import sys
import pandas as pd

# Check conda environment
if os.environ.get("CONDA_DEFAULT_ENV") != "management_scripts":
    print("❌ Error: Please activate the 'management_scripts' conda environment before running this script.")
    sys.exit(1)

# Prompt for CSV file
csv_path = input("📄 Enter the full path to your CSV file: ").strip()
if not os.path.isfile(csv_path):
    print("❌ File does not exist. Exiting.")
    sys.exit(1)

# Prompt for keyword column
column_name = input("🔑 Enter the column name for keywords (default: 'Keyword'): ").strip()
if not column_name:
    column_name = "Keyword"

# Read CSV
try:
    df = pd.read_csv(csv_path)
except Exception as e:
    print(f"❌ Failed to read CSV: {e}")
    sys.exit(1)

if column_name not in df.columns:
    print(f"❌ Column '{column_name}' not found in CSV.")
    sys.exit(1)

keywords = df[column_name].dropna().astype(str).tolist()

# Preview first 3 keywords
preview = keywords[:3]
print("\nPreview of first 3 keywords:")
for i, kw in enumerate(preview, 1):
    print(f"  {i}. {kw}")
confirm = input("\nDo these look correct? (y/n): ").strip().lower()
if confirm != "y":
    print("❌ Aborted by user.")
    sys.exit(0)

# Extract valid keywords (no commas)
valid_keywords = []
skipped_keywords = []
for kw in keywords:
    if "," in kw:
        print(f"⚠️ Skipping keyword with comma: {kw}")
        skipped_keywords.append(kw)
    else:
        valid_keywords.append(kw)

if not valid_keywords:
    print("❌ No valid keywords found (without commas). Exiting.")
    sys.exit(1)

# Prompt for output folder
output_folder = input("💾 Enter the folder path to save 'keywords.txt': ").strip()
if not os.path.isdir(output_folder):
    print("❌ Output folder does not exist.")
    sys.exit(1)
output_path = os.path.join(output_folder, "keywords.txt")

try:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(",".join(valid_keywords))
    print(f"✅ Saved {len(valid_keywords)} keywords to {output_path}")
except Exception as e:
    print(f"❌ Failed to save file: {e}")
    sys.exit(1)