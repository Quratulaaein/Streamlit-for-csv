# simple_amazon_viewer.py
import streamlit as st
import pandas as pd
from pathlib import Path
from typing import Dict

st.set_page_config(page_title="Amazon CSV Search", layout="wide")

# Map categories to CSV files (update paths if your CSVs are elsewhere)
CSV_FILES: Dict[str, str] = {
    "Laptops": "amazon_results_laptops.csv",
    "Mobiles": "amazon_results_mobilephones.csv",
    "Headphones": "amazon_headphones.csv"
}

st.sidebar.title("Options")
category = st.sidebar.selectbox("Category (used when NOT doing a global search)", list(CSV_FILES.keys()))
search_all = st.sidebar.checkbox("Search across ALL categories (global search)", value=False)

# caching file loads so repeated UI interactions are faster
@st.cache_data
def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)

# Load either the selected CSV or all CSVs combined
missing = []
dfs = {}
for cat, path in CSV_FILES.items():
    p = Path(path)
    if not p.exists():
        missing.append(path)
    else:
        try:
            df = load_csv(str(p))
        except Exception as e:
            st.error(f"Error loading {path}: {e}")
            st.stop()
        # Add a Category column so we know which file each row came from
        df["Category"] = cat
        dfs[cat] = df

if missing:
    st.error(f"CSV file(s) not found: {', '.join(missing)}")
    st.stop()

# Combine all dataframes for global search
df_all = pd.concat(dfs.values(), ignore_index=True)

# Put a prominent title and a single search box at the top
st.title("Amazon CSV Search (global or per-category)")

query = st.text_input("Enter search term (leave blank to show all rows):").strip()

# decide which DataFrame to search
if search_all:
    st.subheader("Searching across ALL categories")
    df_to_search = df_all.copy()
    download_name_prefix = "global"
else:
    st.subheader(f"Searching within category: {category}")
    df_to_search = dfs[category].copy()
    download_name_prefix = category.lower()

# If query provided, filter rows where any cell contains the query (case-insensitive)
if query:
    # convert dataframe to strings and check each row
    mask = df_to_search.apply(
        lambda row: row.astype(str).str.contains(query, case=False, na=False).any(),
        axis=1
    )
    filtered = df_to_search[mask].reset_index(drop=True)
else:
    filtered = df_to_search.reset_index(drop=True)

st.write(f"Showing {len(filtered)} results")

# If global search is enabled show counts by category
if search_all:
    counts = filtered['Category'].value_counts().rename_axis('Category').reset_index(name='Count')
    st.markdown("**Results by category (within filtered set):**")
    st.table(counts)

# show table (use width='stretch' — this will let streamlit stretch the dataframe)
st.dataframe(filtered, width="stretch")

# Download filtered CSV
st.download_button(
    "Download results as CSV",
    data=filtered.to_csv(index=False).encode("utf-8"),
    file_name=f"{download_name_prefix}_filtered.csv",
    mime="text/csv",
)
