#!/usr/bin/env python
import os
import sys

if os.environ.get("CONDA_DEFAULT_ENV") != "management_scripts":
    print("❌ Error: Please activate the 'management_scripts' conda environment before running this script.")
    sys.exit(1)
"""
merge_keywords.py

This script merges all CSV files in a specified folder into a single CSV file named 'keywords.csv'.

Usage:
  1. Make the script executable:
     chmod +x ./merge_keywords.py
  2. Run the script:
     ./merge_keywords.py
  3. Follow the prompt to enter the full path to your folder containing CSV files.

The merged CSV will be saved in the same folder as 'keywords.csv'.
"""
import os
import glob
import pandas as pd

def merge_csv_files(input_folder, output_filename="keywords.csv"):
    # Get all CSV files in the directory
    csv_files = glob.glob(os.path.join(input_folder, "*.csv"))

    if not csv_files:
        print("❌ No CSV files found in that folder.")
        return

    print(f"🔍 Found {len(csv_files)} CSV files. Merging...")

    # Read and merge
    df_list = [pd.read_csv(file) for file in csv_files]
    merged_df = pd.concat(df_list, ignore_index=True)

    # Output path
    output_path = os.path.join(input_folder, output_filename)
    merged_df.to_csv(output_path, index=False)

    print(f"✅ Done! Merged file saved at:\n{os.path.abspath(output_path)}")

if __name__ == "__main__":
    folder_path = input("📁 Enter the full path to your folder with CSV files: ").strip()

    if not os.path.isdir(folder_path):
        print("❌ Invalid directory. Please check the path and try again.")
    else:
        merge_csv_files(folder_path)

