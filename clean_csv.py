import pandas as pd

# Load the updated Excel file
df = pd.read_excel("Updated_Market_Journal_Fall_2025.xlsx")

# Save as CSV
df.to_csv("market_journal.csv", index=False)
