# simple_amazon_viewer.py
import streamlit as st
import pandas as pd
from pathlib import Path
from typing import Dict

st.set_page_config(page_title="Amazon CSV Search", layout="wide")

CSV_FILES: Dict[str, str] = {
    "Laptops": "amazon_results_laptops.csv",
    "Mobiles": "amazon_results_mobilephones.csv",
    "Headphones": "amazon_headphones.csv"
}

st.sidebar.title("Options")

# Keep category selector but default to Laptops (used only when NOT doing global search)
category = st.sidebar.selectbox(
    "Category (used when NOT doing a global search)",
    list(CSV_FILES.keys())
)

# <<< Make global search ON by default by setting value=True >>>
search_all = st.sidebar.checkbox(
    "Search across ALL categories (global search)",
    value=True
)

@st.cache_data
def load_csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path)

# Load CSVs and add Category column
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
        df["Category"] = cat
        dfs[cat] = df

if missing:
    st.error(f"CSV file(s) not found: {', '.join(missing)}")
    st.stop()

df_all = pd.concat(dfs.values(), ignore_index=True)

st.title("Amazon CSV Search (global or per-category)")
if search_all:
    st.caption("")
else:
    st.caption(f"Searching within category: {category}")

# Place single search box at top. Press Enter to apply.
query = st.text_input("Enter search term (leave blank to show all rows):").strip()

# Use global DF if search_all True; otherwise use selected category DF
if search_all:
    df_to_search = df_all.copy()
    download_name_prefix = "global"
else:
    df_to_search = dfs[category].copy()
    download_name_prefix = category.lower()

# Filter
if query:
    mask = df_to_search.apply(
        lambda row: row.astype(str).str.contains(query, case=False, na=False).any(),
        axis=1
    )
    filtered = df_to_search[mask].reset_index(drop=True)
else:
    filtered = df_to_search.reset_index(drop=True)

st.write(f"Showing {len(filtered)} results")

# Show breakdown if global
if search_all:
    counts = filtered['Category'].value_counts().rename_axis('Category').reset_index(name='Count')
    st.markdown("**Results by category (within filtered set):**")
    st.table(counts)

st.dataframe(filtered, width="stretch")

st.download_button(
    "Download results as CSV",
    data=filtered.to_csv(index=False).encode("utf-8"),
    file_name=f"{download_name_prefix}_filtered.csv",
    mime="text/csv",
)
