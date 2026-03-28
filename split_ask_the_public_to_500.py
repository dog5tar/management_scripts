import os
import pandas as pd
import shutil
from pathlib import Path
import chardet
import csv

def ask_user_for_header_line(lines, filename):
    print(f"\n📄 Scanning {filename} for header line:")
    for i, line in enumerate(lines):
        print(f"\nLine {i + 1}:")
        print(line.strip())
        user_input = input("🧠 Is this the header? (yes/no/skip file): ").strip().lower()
        if user_input == 'yes':
            delimiter = '\t' if '\t' in line else ','
            header = [col.strip().strip('"') for col in line.strip().split(delimiter)]
            return i, header, delimiter
        elif user_input == 'skip file':
            return None, None, None
    print("⚠️ No header selected.")
    return None, None, None

def split_csv_files():
    directory = input("Enter the path to the directory containing CSV files: ").strip()

    if not os.path.isdir(directory):
        print("Invalid directory. Please try again.")
        return

    parsed_folder = Path(directory) / "parsed"
    parsed_folder.mkdir(exist_ok=True)

    all_data = []
    final_header = None
    header_index = None
    header_selected = False
    detected_delimiter = ','

    csv_files = [f for f in os.listdir(directory) if f.endswith(".csv")]

    for idx, filename in enumerate(csv_files):
        file_path = Path(directory) / filename

        with open(file_path, 'rb') as f:
            raw_data = f.read()
            result = chardet.detect(raw_data)
            encoding = result['encoding']

        try:
            with open(file_path, 'r', encoding=encoding) as f:
                lines = f.readlines()

            if not header_selected:
                header_index, final_header, detected_delimiter = ask_user_for_header_line(lines, filename)
                if header_index is None or final_header is None:
                    print(f"⏭ Skipping {filename}")
                    continue
                header_selected = True
            else:
                # Validate header format
                candidate_header = [col.strip().strip('"') for col in lines[header_index].strip().split(detected_delimiter)]
                if candidate_header != final_header:
                    print(f"⚠️ Header mismatch in {filename}, skipping.")
                    continue

            # Save valid data to temp file
            temp_file = Path(directory) / f"temp_{filename}"
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(detected_delimiter.join(final_header) + "\n")
                f.writelines(lines[header_index + 1:])

            df = pd.read_csv(temp_file, delimiter=detected_delimiter)
            os.remove(temp_file)

            all_data.append(df)
            shutil.move(file_path, parsed_folder / filename)

        except Exception as e:
            print(f"❌ Failed to process {filename}: {e}")

    if not all_data:
        print("⚠️ No valid data found.")
        return

    combined_df = pd.concat(all_data, ignore_index=True)

    for i, chunk_start in enumerate(range(0, len(combined_df), 500)):
        chunk_df = combined_df.iloc[chunk_start:chunk_start + 500]
        output_path = Path(directory) / f"combined_part_{i + 1}.csv"
        chunk_df.to_csv(
            output_path,
            index=False,
            sep=',',
            quoting=csv.QUOTE_ALL,
            quotechar='"',
            lineterminator='\n',
            encoding='utf-8-sig'
        )

    print("✅ All files processed, combined, and split into 500-row CSVs.")

if __name__ == "__main__":
    split_csv_files()
