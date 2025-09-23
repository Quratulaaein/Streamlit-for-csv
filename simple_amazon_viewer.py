# simple_amazon_viewer.py
import streamlit as st
import pandas as pd
from pathlib import Path

st.set_page_config(page_title="Amazon CSV Search", layout="wide")

# Map categories to CSV files (update paths if your CSVs are elsewhere)
CSV_FILES = {
    "Laptops": "amazon_results_laptops.csv",
    "Mobiles": "amazon_results_mobilephones.csv",
    "Headphones": "amazon_headphones.csv"
}

st.sidebar.title("Choose CSV")
category = st.sidebar.selectbox("Category", list(CSV_FILES.keys()))
csv_path = Path(CSV_FILES[category])

if not csv_path.exists():
    st.error(f"CSV file not found: {csv_path.resolve()}")
    st.stop()

# Load CSV
df = pd.read_csv(csv_path)

st.title(f"Search {category}")

query = st.text_input("Enter search term:")

# If query provided, filter rows where any cell contains the query (case-insensitive)
if query:
    mask = df.apply(lambda row: row.astype(str).str.contains(query, case=False, na=False).any(), axis=1)
    filtered = df[mask].reset_index(drop=True)
else:
    filtered = df.reset_index(drop=True)

st.write(f"Showing {len(filtered)} results")

# show table (use width='stretch' to replace deprecated use_container_width=True)
st.dataframe(filtered, width="stretch")

# Download filtered CSV
st.download_button(
    "Download results as CSV",
    data=filtered.to_csv(index=False).encode("utf-8"),
    file_name=f"{category}_filtered.csv",
    mime="text/csv",
)
