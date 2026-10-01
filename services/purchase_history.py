import re
from pathlib import Path

import pandas as pd
import streamlit as st


EXCLUDED_ARTICLE_REFERENCES = {
    "TRANSPORT",
    "PALLETS",
    "SAMPLESHIPMENT",
    "ADDITIONAL",
}


def normalize_cas(value):
    """
    Extract and normalize a CAS number.

    Examples:
    '98-29-3'       -> '98-29-3'
    ' 98-29-3 '     -> '98-29-3'
    'CAS 98-29-3'   -> '98-29-3'
    """

    if value is None or pd.isna(value):
        return None

    value = str(value).strip()

    match = re.search(
        r"\b\d{2,7}-\d{2}-\d\b",
        value,
    )

    if not match:
        return None

    return match.group(0)


@st.cache_data(ttl=86400)
def load_purchase_history(file_path):
    """
    Load and prepare the purchase-history Excel file.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Purchase-history file not found: {file_path}"
        )

    df = pd.read_excel(
        path,
        sheet_name=0,
    )

    required_columns = {
        "Artikelreferentie",
        "Omschrijving 1 artik",
        "CAS nummer",
        "Leverancier",
        "Naam 1 derden",
        "Documentdatum",
    }

    missing_columns = required_columns.difference(
        df.columns
    )

    if missing_columns:
        raise ValueError(
            "The purchase-history file is missing these columns: "
            + ", ".join(sorted(missing_columns))
        )

    df = df.rename(
        columns={
            "Artikelreferentie": "article_reference",
            "Omschrijving 1 artik": "product_description",
            "CAS nummer": "cas_number",
            "Leverancier": "supplier_code",
            "Naam 1 derden": "supplier_name",
            "Documentdatum": "purchase_date",
            "Dagboekcode": "journal_code",
            "Doc.nr.": "document_number",
        }
    )

    df["cas_normalized"] = (
        df["cas_number"]
        .apply(normalize_cas)
    )

    df["purchase_date"] = pd.to_datetime(
        df["purchase_date"],
        errors="coerce",
    )

    df["article_reference"] = (
        df["article_reference"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df = df[
        ~df["article_reference"]
        .str.upper()
        .isin(EXCLUDED_ARTICLE_REFERENCES)
    ].copy()

    # Rows without a usable CAS number cannot be matched
    # against the ECHA result.
    df = df[
        df["cas_normalized"].notna()
    ].copy()

    return df


def get_purchase_information(
    purchase_df,
    cas_number,
):
    """
    Find all purchases matching the supplied CAS number.

    The most recent document date is treated as the
    last purchase date.
    """

    normalized_cas = normalize_cas(
        cas_number
    )

    if not normalized_cas:
        return {
            "purchased": False,
            "cas_number": None,
            "message": (
                "No valid CAS number was available "
                "for the purchase-history search."
            ),
        }

    matches = purchase_df[
        purchase_df["cas_normalized"]
        == normalized_cas
    ].copy()

    matches = matches.dropna(
        subset=["purchase_date"]
    )

    matches = matches.sort_values(
        by="purchase_date",
        ascending=False,
    ).reset_index(drop=True)

    if matches.empty:
        return {
            "purchased": False,
            "cas_number": normalized_cas,
            "message": (
                "No purchase was found in the available "
                "purchase history for this CAS number."
            ),
        }

    latest_purchase_date = matches[
        "purchase_date"
    ].max()

    # There can be multiple lines on the most recent date,
    # especially when multiple packaging types were purchased.
    latest_purchases = matches[
        matches["purchase_date"]
        == latest_purchase_date
    ].copy()

    suppliers = (
        matches["supplier_name"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    suppliers = [
        supplier
        for supplier in suppliers.unique().tolist()
        if supplier
    ]

    latest_suppliers = (
        latest_purchases["supplier_name"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    latest_suppliers = [
        supplier
        for supplier
        in latest_suppliers.unique().tolist()
        if supplier
    ]

    return {
        "purchased": True,
        "cas_number": normalized_cas,
        "last_purchase_date": latest_purchase_date,
        "last_suppliers": latest_suppliers,
        "all_suppliers": suppliers,
        "latest_purchases": latest_purchases,
        "history": matches,
        "purchase_line_count": len(matches),
    }