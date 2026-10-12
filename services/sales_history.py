import re
from pathlib import Path

import pandas as pd
import streamlit as st


def normalize_cas(value):
    """Extract a valid CAS number."""

    if pd.isna(value):
        return None

    value = str(value).strip()

    match = re.search(r"\d{2,7}-\d{2}-\d", value)

    if match:
        return match.group(0)

    return None


@st.cache_data
def load_sales_history(file_path):
    """
    Load sales history from Excel.
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Sales history file not found: {file_path}"
        )

    sheets = pd.read_excel(
        file_path,
        sheet_name=None
    )

    frames = []

    for sheet_name, df in sheets.items():

        if df is None or df.empty:
            continue

        df = df.copy()
        df["source_sheet"] = sheet_name

        frames.append(df)

    if not frames:
        return pd.DataFrame()

    sales_df = pd.concat(
        frames,
        ignore_index=True
    )

    sales_df.columns = [
        str(col).strip()
        for col in sales_df.columns
    ]

    sales_df["cas_normalized"] = sales_df[
        "CAS nummer"
    ].apply(normalize_cas)

    sales_df["customer_display"] = (
        sales_df["Bedrijfsref. (derde)"]
        .fillna("")
        .astype(str)
        + " | "
        + sales_df["Naam 1 derden"]
        .fillna("")
        .astype(str)
    )

    sales_df["Documentdatum"] = pd.to_datetime(
        sales_df["Documentdatum"],
        errors="coerce"
    )

    return sales_df


def get_customers_for_cas(
    sales_df,
    cas_number
):
    """
    Return customer list for CAS.
    """

    cas_number = normalize_cas(cas_number)

    if cas_number is None:
        return []

    matches = sales_df[
        sales_df["cas_normalized"] == cas_number
    ]

    customers = (
        matches["customer_display"]
        .dropna()
        .drop_duplicates()
        .sort_values()
        .tolist()
    )

    return customers


def get_sales_information(
    sales_df,
    cas_number,
    selected_customer=None
):
    """
    Return sales information.
    """

    cas_number = normalize_cas(cas_number)

    if cas_number is None:

        return {
            "sold": False,
            "history": pd.DataFrame(),
            "latest_sales": pd.DataFrame(),
            "sales_line_count": 0,
            "customer_count": 0,
            "last_sales_date": None,
        }

    matches = sales_df[
        sales_df["cas_normalized"] == cas_number
    ].copy()

    if selected_customer:

        matches = matches[
            matches["customer_display"]
            == selected_customer
        ]

    if matches.empty:

        return {
            "sold": False,
            "history": pd.DataFrame(),
            "latest_sales": pd.DataFrame(),
            "sales_line_count": 0,
            "customer_count": 0,
            "last_sales_date": None,
        }

    matches = matches.sort_values(
        "Documentdatum",
        ascending=False
    )

    last_sales_date = matches[
        "Documentdatum"
    ].max()

    latest_sales = matches[
        matches["Documentdatum"]
        == last_sales_date
    ]

    return {
        "sold": True,
        "history": matches,
        "latest_sales": latest_sales,
        "sales_line_count": len(matches),
        "customer_count": matches[
            "customer_display"
        ].nunique(),
        "last_sales_date": last_sales_date,
    }