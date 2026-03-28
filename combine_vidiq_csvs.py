#!/usr/bin/env python

"""
Combine VidIQ CSVs by Suffix

This script prompts for (or accepts) a folder containing CSV files named using the VidIQ convention:
  <keyword_prefix>_(matching_terms|question_keywords|related_keywords).csv

It validates:
- The selected path exists and is a directory
- All top-level files in the folder are CSVs
- Filenames match one of the three allowed suffixes

It combines files per suffix into three outputs while preserving data integrity:
- combined_matching_terms.csv
- combined__question_keywords.csv
- combined_related_keywords.csv

Rules:
- Only CSV files are processed (top-level only; subfolders ignored).
- Files must end in one of:
    _matching_terms.csv
    _question_keywords.csv
    _related_keywords.csv
- For each suffix group, all files must share the same header (same columns, same order). If a mismatch is found, the script errors out for that group to avoid corrupting structure.

Usage:
- Interactive prompt:
    python combine_vidiq_csvs.py
- Pass a folder path directly:
    python combine_vidiq_csvs.py /path/to/Keywords

Optional:
- Set CONDA_DEFAULT_ENV=management_scripts in your environment to align with other scripts.
"""

import os
import sys
import csv
import re
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Optional: keep consistency with your other scripts
def check_conda_environment():
    required_env = "management_scripts"
    current_env = os.environ.get("CONDA_DEFAULT_ENV")
    if current_env != required_env:
        print(f"❌ Error: Please activate the '{required_env}' conda environment.")
        print(f"Current environment: {current_env or 'None'}")
        print(f"Activate with: conda activate {required_env}")
        sys.exit(1)

SUFFIX_TO_OUTPUT = {
    "matching_terms": "combined_matching_terms.csv",
    "question_keywords": "combined__question_keywords.csv",  # double underscore as requested
    "related_keywords": "combined_related_keywords.csv",
}

SUFFIX_PATTERNS = {
    # Allow optional " (number)" before the extension for duplicate files
    "matching_terms": re.compile(r".+_matching_terms(?:\s*\(\d+\))?\.csv$", re.IGNORECASE),
    "question_keywords": re.compile(r".+_question_keywords(?:\s*\(\d+\))?\.csv$", re.IGNORECASE),
    "related_keywords": re.compile(r".+_related_keywords(?:\s*\(\d+\))?\.csv$", re.IGNORECASE),
}

def prompt_for_directory() -> Path:
    # Always prompt via stdin; avoid GUI to prevent NSOpenPanel warnings/hangs
    while True:
        directory = input("Enter the path to the folder containing VidIQ CSV files (or 'q' to quit): ").strip()
        if directory.lower() in {"q", "quit", "exit"}:
            print("Exiting.")
            sys.exit(0)
        path = Path(directory)
        if not path.exists():
            print(f"Path does not exist: {path}")
            continue
        if not path.is_dir():
            print(f"Path is not a directory: {path}")
            continue
        return path

def validate_directory(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Selected path does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Selected path is not a directory: {path}")

def list_top_level_files(path: Path) -> List[Path]:
    return [p for p in path.iterdir() if p.is_file()]

def ensure_all_csv(files: List[Path]) -> List[Path]:
    # Silently filter: keep only CSV files; ignore others without reporting
    return [f for f in files if f.suffix.lower() == ".csv"]

def classify_file(file_name: str) -> Optional[str]:
    # Return group key or None if not matching convention
    for key, pattern in SUFFIX_PATTERNS.items():
        if pattern.match(file_name):
            return key
    return None

def read_csv_preserve_header(file_path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    try:
        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                raise ValueError(f"Empty CSV file: {file_path}")
            # Use DictReader with the captured header to preserve order
            f.seek(0)
            dict_reader = csv.DictReader(f, fieldnames=header)
            # Skip header row in data read
            next(dict_reader, None)
            rows = [row for row in dict_reader]
            return header, rows
    except PermissionError:
        raise PermissionError(f"Permission denied reading file: {file_path}")
    except OSError as e:
        raise OSError(f"OS error reading file '{file_path}': {e}")

def write_combined(output_path: Path, header: List[str], rows: List[Dict[str, str]]) -> None:
    try:
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            for row in rows:
                # Ensure keys exist; fill missing with empty string to preserve structure
                normalized = {h: row.get(h, "") for h in header}
                writer.writerow(normalized)
    except PermissionError:
        raise PermissionError(f"Permission denied writing file: {output_path}")
    except OSError as e:
        raise OSError(f"OS error writing file '{output_path}': {e}")

def combine_group(files: List[Path], output_path: Path) -> None:
    # Validate consistent header across all files in the group
    combined_rows: List[Dict[str, str]] = []
    group_header: Optional[List[str]] = None
    header_mismatches: List[str] = []

    for fp in files:
        header, rows = read_csv_preserve_header(fp)
        if group_header is None:
            group_header = header
        else:
            if header != group_header:
                header_mismatches.append(fp.name)
                continue
        combined_rows.extend(rows)

    if header_mismatches:
        mismatch_list = ", ".join(header_mismatches)
        raise ValueError(
            f"Header mismatch detected in files: {mismatch_list}. "
            f"All files in the group must share identical columns and order."
        )

    if group_header is None:
        # No valid files left to combine
        print(f"⚠️  No valid files to combine for {output_path.name}. Skipping.")
        return

    write_combined(output_path, group_header, combined_rows)
    print(f"✅ Wrote combined file: {output_path} ({len(combined_rows)} rows)")

def main():
    # Optional environment check; uncomment to enforce
    # check_conda_environment()

    # Always prompt for the folder; loop until valid
    while True:
        folder = prompt_for_directory()
        try:
            validate_directory(folder)
            break
        except (FileNotFoundError, NotADirectoryError) as e:
            print(f"❌ {e}")
            continue

    try:
        files = list_top_level_files(folder)
        # Filter out non-CSV files silently
        csv_files = ensure_all_csv(files)
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in directory: {folder}")

        # Classify files into groups
        groups: Dict[str, List[Path]] = {k: [] for k in SUFFIX_TO_OUTPUT.keys()}
        invalid_names: List[str] = []

        for fp in csv_files:
            classification = classify_file(fp.name)
            if classification is None:
                invalid_names.append(fp.name)
            else:
                groups[classification].append(fp)

        if invalid_names:
            names = "\n  - " + "\n  - ".join(invalid_names)
            raise ValueError(
                "Missing or malformed naming conventions for files:"
                f"{names}\nExpected endings: "
                "'_matching_terms.csv', '_question_keywords.csv', '_related_keywords.csv'"
            )

        # Create combined outputs
        for group_key, output_name in SUFFIX_TO_OUTPUT.items():
            group_files = groups.get(group_key, [])
            if not group_files:
                print(f"ℹ️  No files for group '{group_key}'. Skipping {output_name}.")
                continue
            output_path = folder / output_name
            print(f"➡️  Combining {len(group_files)} file(s) into {output_name} ...")
            combine_group(group_files, output_path)

        print("🎉 Completed combining VidIQ CSVs.")

    except (FileNotFoundError, NotADirectoryError, ValueError, PermissionError, OSError) as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()