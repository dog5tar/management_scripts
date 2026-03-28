#!/usr/bin/env python3
import os
import sys

# Enforce running in the correct conda environment at the highest point
REQUIRED_ENV = "management_scripts"
current_env = os.environ.get("CONDA_DEFAULT_ENV")
if current_env != REQUIRED_ENV:
    print(f"❌ Error: Please activate the '{REQUIRED_ENV}' conda environment.")
    print(f"Current environment: {current_env or 'None'}")
    print(f"Activate with: conda activate {REQUIRED_ENV}")
    sys.exit(1)

"""
CSV Column → TXT

- Accepts a CSV path via CLI or interactive prompt
- Shows header columns and lets you pick one (case-sensitive)
- Extracts non-empty, trimmed values from that column
- Preserves original order and removes duplicates
- Writes comma-separated values to a .txt file alongside the CSV

Works with Python 3.6+ and uses UTF-8 for I/O.
"""

import sys
import os
import csv
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

# ----- Logging setup -----
def setup_logger(log_dir: Path, debug: bool) -> logging.Logger:
    """
    Configure a multi-level logger that outputs to console and a timestamped log file.
    """
    log_dir = log_dir.resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"csv_column_to_txt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger("csv_column_to_txt")
    logger.setLevel(logging.DEBUG)  # capture everything; handlers will filter
    # Clear existing handlers to avoid duplicates if re-run in same process
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if debug else logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.debug(f"Logger initialized. Log file: {log_file}")
    return logger

# ----- Input helpers (folder + file resolution) -----
def prompt_for_folder_path() -> Path:
    """
    Prompt the user to enter a folder path and validate it exists.
    """
    while True:
        raw = input("Enter the folder path where the script should operate (or 'q' to quit): ").strip()
        if raw.lower() in {"q", "quit", "exit"}:
            print("Exiting.")
            sys.exit(0)
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print(f"Path does not exist: {p}")
            continue
        if not p.is_dir():
            print(f"Path is not a directory: {p}")
            continue
        return p

def resolve_input_file(folder: Path, filename_override: Optional[str]) -> Path:
    """
    Resolve the input CSV within the given folder. Defaults to 'keywords.csv'.
    """
    name = filename_override.strip() if filename_override else "keywords.csv"
    csv_path = (folder / name).resolve()
    return csv_path

# ----- Existing constants/helpers for auto-processing -----
REQUIRED_COLUMNS = ["Keyword", "Competition", "Search volume"]

def has_required_columns(header: List[str]) -> bool:
    return all(col in header for col in REQUIRED_COLUMNS)

def coerce_float(value: str) -> Optional[float]:
    # Accept numbers like "1,234.56", "45%", " 0.35 "
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except ValueError:
        return None

def coerce_int_or_float(value: str) -> Optional[float]:
    # Search volume may be int-like with commas or floats
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None

def auto_process_required_columns(csv_path: Path, header: List[str], logger: logging.Logger) -> None:
    """
    Auto-process CSVs that include Keyword, Competition, and Search volume:
    - Sort by Competition asc, then Search volume desc
    - Write sorted keywords to a .txt file alongside the CSV
    """
    logger.info(f"Starting auto-processing for file: {csv_path}")
    rows: List[Tuple[str, float, float]] = []
    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            logger.debug("Opened CSV for reading (auto mode).")
            reader = csv.DictReader(f)  # uses header
            for idx, row in enumerate(reader, start=1):
                logger.debug(f"Row {idx} read: {row}")
                kw_raw = row.get("Keyword", "")
                if not str(kw_raw).strip():
                    logger.debug(f"Row {idx}: empty Keyword, skipping.")
                    continue
                comp = coerce_float(row.get("Competition"))
                vol = coerce_int_or_float(row.get("Search volume"))
                if comp is None or vol is None:
                    logger.debug(f"Row {idx}: invalid Competition/Volume, skipping (comp={row.get('Competition')}, vol={row.get('Search volume')}).")
                    continue
                rows.append((kw_raw, comp, vol))
                logger.debug(f"Row {idx}: accepted (Keyword='{kw_raw}', Competition={comp}, Volume={vol}).")
    except PermissionError:
        raise PermissionError(f"Permission denied reading file: {csv_path}. Try: chmod or run with appropriate permissions.")
    except OSError as e:
        raise OSError(f"OS error reading file '{csv_path}': {e}")

    if not rows:
        raise ValueError("No valid rows found with numeric Competition and Search volume.")

    logger.info(f"Collected {len(rows)} valid row(s). Sorting by Competition asc, Search volume desc.")
    rows.sort(key=lambda t: (t[1], -t[2]))
    sorted_keywords = [t[0] for t in rows]

    out_path = csv_path.with_suffix(".txt")
    logger.info(f"Writing {len(sorted_keywords)} keyword(s) to TXT: {out_path}")
    try:
        with out_path.open("w", encoding="utf-8", newline="\n") as f:
            logger.debug("Opened TXT file for writing.")
            text = ",".join(sorted_keywords)
            f.write(text)
            logger.debug("Finished writing TXT content.")
    except PermissionError:
        raise PermissionError(f"Permission denied writing file: {out_path}. Ensure the folder is writable.")
    except OSError as e:
        raise OSError(f"OS error writing file '{out_path}': {e}")

    msg = f"✅ Auto-processed {len(sorted_keywords)} keyword(s) to: {out_path}"
    print(msg)
    logger.info(msg)


def prompt_for_csv_path() -> Path:
    while True:
        raw = input("Enter path to the CSV file (or 'q' to quit): ").strip()
        if raw.lower() in {"q", "quit", "exit"}:
            print("Exiting.")
            sys.exit(0)
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            print(f"Path does not exist: {p}")
            continue
        if not p.is_file():
            print(f"Path is not a file: {p}")
            continue
        return p


def validate_csv_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() != ".csv":
        raise ValueError(f"File does not have '.csv' extension: {path.name}")

    # Basic CSV sanity: ensure at least one row and a non-empty header
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                raise ValueError("CSV is empty (no rows).")
            if not header or all((h or "").strip() == "" for h in header):
                raise ValueError("CSV appears to have no header or an empty header row.")
    except OSError as e:
        raise OSError(f"OS error reading file '{path}': {e}")


def read_header(path: Path) -> List[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            raise ValueError("CSV is empty (no rows).")
        if not header or all((h or "").strip() == "" for h in header):
            raise ValueError("CSV appears to have no header or an empty header row.")
        return header


def prompt_for_column(header: List[str]) -> str:
    print("Available columns:")
    for i, col in enumerate(header, 1):
        print(f"  {i}. {col}")
    while True:
        col = input("Enter the column name (case-sensitive): ").strip()
        if col in header:
            return col
        print("Column not found. Please enter an exact, case-sensitive name from the list above.")


def extract_column_values(path: Path, column: str, header: List[str], logger: Optional[logging.Logger] = None) -> List[str]:
    # Use DictReader with explicit header to preserve column order and handle BOM
    if logger:
        logger.info(f"Extracting values from column '{column}' in file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        if logger:
            logger.debug("Opened CSV for reading (interactive mode).")
        dict_reader = csv.DictReader(f, fieldnames=header)
        # Skip header row in data
        next(dict_reader, None)

        values: List[str] = []
        seen = set()
        for idx, row in enumerate(dict_reader, start=1):
            if logger:
                logger.debug(f"Row {idx} read: {row}")
            raw_val = row.get(column, "")
            val = (raw_val or "").strip()
            if not val:
                if logger:
                    logger.debug(f"Row {idx}: empty value, skipping.")
                continue
            if val not in seen:
                seen.add(val)
                values.append(val)
                if logger:
                    logger.debug(f"Row {idx}: accepted value '{val}'.")
        return values


def output_path_for_csv(csv_path: Path) -> Path:
    return csv_path.with_suffix(".txt")


def write_values_to_txt(values: List[str], out_path: Path, logger: Optional[logging.Logger] = None) -> None:
    # Join with commas, preserve order, UTF-8 encoding
    if logger:
        logger.info(f"Writing {len(values)} value(s) to TXT: {out_path}")
    text = ",".join(values)
    try:
        with out_path.open("w", encoding="utf-8", newline="\n") as f:
            if logger:
                logger.debug("Opened TXT file for writing (interactive mode).")
            f.write(text)
            if logger:
                logger.debug("Finished writing TXT content.")
    except PermissionError:
        raise PermissionError(f"Permission denied writing file: {out_path}. Ensure the folder is writable.")
    except OSError as e:
        raise OSError(f"OS error writing file '{out_path}': {e}")


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Extract keywords or a column from a CSV and write comma-separated values to a .txt file.")
    ap.add_argument("--file", "-f", help="Input CSV filename inside the selected folder (default: keywords.csv)")
    ap.add_argument("--debug", "-d", action="store_true", help="Enable verbose DEBUG logging (per-row).")
    ap.add_argument("csv", nargs="?", help="Legacy: direct CSV path (if provided, folder prompt is skipped)")
    args = ap.parse_args(argv)

    # Choose input mode: legacy direct CSV or preferred folder + filename
    if args.csv:
        # Legacy path provided; operate directly on this file
        csv_path = Path(args.csv).expanduser().resolve()
        folder = csv_path.parent
        logger = setup_logger(folder, debug=args.debug)
        logger.info("Starting script execution (legacy direct CSV mode).")
    else:
        folder = prompt_for_folder_path()
        logger = setup_logger(folder, debug=args.debug)
        logger.info("Starting script execution (folder + filename mode).")
        csv_path = resolve_input_file(folder, args.file)

    try:
        # Validate folder and file
        if not folder.exists() or not folder.is_dir():
            raise NotADirectoryError(f"Selected path is not a valid directory: {folder}")
        logger.debug(f"Validated folder exists: {folder}")

        if not csv_path.exists():
            raise FileNotFoundError(f"Input file not found: {csv_path}. Tip: use --file to specify a different CSV name.")
        logger.info(f"Input CSV resolved: {csv_path}")

        # Validate CSV file and read header
        validate_csv_file(csv_path)
        logger.debug("CSV basic validation passed.")
        header = read_header(csv_path)
        logger.info(f"CSV header detected: {header}")

        # Auto mode when required columns are present
        if has_required_columns(header):
            auto_process_required_columns(csv_path, header, logger)
        else:
            logger.info("Required columns not found. Switching to interactive column selection.")
            column = prompt_for_column(header)
            values = extract_column_values(csv_path, column, header, logger)
            if not values:
                logger.warning("No non-empty values found in the selected column. Writing an empty file.")
            out_path = csv_path.with_suffix(".txt")
            write_values_to_txt(values, out_path, logger)
            msg = f"✅ Wrote {len(values)} value(s) to: {out_path}"
            print(msg)
            logger.info(msg)

        logger.info("Script completed successfully.")

    except (FileNotFoundError, NotADirectoryError) as e:
        print(f"❌ Error: {e}")
        logger.error(f"{e}. Troubleshooting: Verify the folder path and input filename exist and are accessible.")
        sys.exit(1)
    except PermissionError as e:
        print(f"❌ Error: {e}")
        logger.error(f"{e}. Troubleshooting: Check file/folder permissions or run with appropriate privileges.")
        sys.exit(1)
    except ValueError as e:
        print(f"❌ Error: {e}")
        logger.error(f"{e}. Troubleshooting: Ensure the CSV has a valid header and data types.")
        sys.exit(1)
    except OSError as e:
        print(f"❌ Error: {e}")
        logger.error(f"{e}. Troubleshooting: Inspect file system issues (disk space, path length, special characters).")
        sys.exit(1)


if __name__ == "__main__":
    main()