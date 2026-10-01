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


def normalize_currency(value):
    """
    Normalize the currency code.

    Empty currency cells remain empty. No currency is assumed,
    because the Excel file contains rows where the currency is blank.
    """

    if value is None or pd.isna(value):
        return None

    value = str(value).strip().upper()

    if not value:
        return None

    return value


def normalize_purchase_price(value):
    """
    Convert the unit purchase price to a numeric value.

    Supports:
    - numeric Excel values
    - 15.40
    - 15,40
    - 1,234.56
    - 1.234,56
    """

    if value is None or pd.isna(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    value = str(value).strip().replace(" ", "")

    if not value:
        return None

    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            # European format: 1.234,56
            value = value.replace(".", "").replace(",", ".")
        else:
            # International format: 1,234.56
            value = value.replace(",", "")
    elif "," in value:
        # Decimal comma: 15,40
        value = value.replace(",", ".")

    return pd.to_numeric(
        value,
        errors="coerce",
    )


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

    df = df.rename(
        columns={
            "Artikelreferentie": "article_reference",
            "Omschrijving 1 artik": "product_description",
            "CAS nummer": "cas_number",
            "Bedrijfsref. (derde)": "supplier_code",
            "Leverancier": "supplier_code",
            "Naam 1 derden": "supplier_name",
            "Documentdatum": "purchase_date",
            "Valuta": "currency",
            "Eenheidsprijs": "purchase_price",
            "Dagboekcode": "journal_code",
            "Doc.nr.": "document_number",
        }
    )

    required_columns = {
        "article_reference",
        "product_description",
        "cas_number",
        "supplier_code",
        "supplier_name",
        "purchase_date",
        "currency",
        "purchase_price",
        "journal_code",
        "document_number",
    }

    missing_columns = required_columns.difference(
        df.columns
    )

    if missing_columns:
        raise ValueError(
            "The purchase-history file is missing these columns: "
            + ", ".join(sorted(missing_columns))
        )

    df["cas_normalized"] = (
        df["cas_number"]
        .apply(normalize_cas)
    )

    df["purchase_date"] = pd.to_datetime(
        df["purchase_date"],
        errors="coerce",
    )

    df["purchase_price"] = (
        df["purchase_price"]
        .apply(normalize_purchase_price)
    )

    df["currency"] = (
        df["currency"]
        .apply(normalize_currency)
    )

    df["article_reference"] = (
        df["article_reference"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df["supplier_name"] = (
        df["supplier_name"]
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
    last purchase date. Prices and currencies are taken
    from all purchase lines on that date.
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

    # Multiple lines can exist on the latest purchase date,
    # for example for different packaging types or suppliers.
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
        for supplier in latest_suppliers.unique().tolist()
        if supplier
    ]

    # Build a clean list containing the price and currency
    # for each line on the most recent purchase date.
    latest_price_details = []

    for _, row in latest_purchases.iterrows():
        purchase_price = row.get("purchase_price")
        currency = row.get("currency")

        latest_price_details.append(
            {
                "article_reference": row.get(
                    "article_reference"
                ),
                "product_description": row.get(
                    "product_description"
                ),
                "supplier_name": row.get(
                    "supplier_name"
                ),
                "purchase_price": (
                    None
                    if pd.isna(purchase_price)
                    else float(purchase_price)
                ),
                "currency": (
                    None
                    if pd.isna(currency)
                    else currency
                ),
                "purchase_date": row.get(
                    "purchase_date"
                ),
                "document_number": row.get(
                    "document_number"
                ),
            }
        )

    valid_prices = (
        latest_purchases["purchase_price"]
        .dropna()
        .tolist()
    )

    latest_currencies = (
        latest_purchases["currency"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    latest_currencies = [
        currency
        for currency in latest_currencies.unique().tolist()
        if currency
    ]

    return {
        "purchased": True,
        "cas_number": normalized_cas,
        "last_purchase_date": latest_purchase_date,
        "last_suppliers": latest_suppliers,
        "all_suppliers": suppliers,

        # New price and currency results
        "last_purchase_prices": valid_prices,
        "last_purchase_currencies": latest_currencies,
        "latest_price_details": latest_price_details,

        # Existing detailed results
        "latest_purchases": latest_purchases,
        "history": matches,
        "purchase_line_count": len(matches),
    }