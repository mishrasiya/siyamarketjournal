import csv
from datetime import datetime

input_file = "market_journal.csv"
output_file = "market_journal_sep5_2025_onwards.csv"

DATE_FORMAT = "%Y-%m-%d"
cutoff_date = datetime(2025, 9, 5).date()  # Keep September 5, 2025 onwards

filtered_data = []

with open(input_file, "r", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    
    # Detect the date column (case-insensitive, strips whitespace)
    date_column = None
    for col in fieldnames:
        if col.strip().lower() == "date":
            date_column = col
            break
    if date_column is None:
        raise ValueError("No 'Date' column found in CSV headers")

    for row in reader:
        try:
            date_value = row[date_column].strip()
            if date_value:
                row_date = datetime.strptime(date_value, DATE_FORMAT).date()
                if row_date >= cutoff_date:
                    filtered_data.append(row)
        except ValueError:
            pass  # Skip invalid dates

with open(output_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(filtered_data)

print(f"Filtered CSV saved as {output_file}")
