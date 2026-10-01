import pandas as pd
import re
from pathlib import Path


def normalize_cas(value):
    if pd.isna(value):
        return None

    value = str(value).strip()
    match = re.search(r"\b\d{2,7}-\d{2}-\d\b", value)

    return match.group(0) if match else None


@st.cache_data
def load_purchase_history(file_path: str) -> pd.DataFrame:
    df = pd.read_excel(file_path)

    df = df.rename(
        columns={
            "Artikelreferentie": "article_reference",
            "Omschrijving 1 artik": "product_description",
            "CAS nummer": "cas_number",
            "Leverancier": "supplier_code",
            "Naam 1 derden": "supplier_name",
            "Documentdatum": "purchase_date",
        }
    )

    df["cas_normalized"] = df["cas_number"].apply(normalize_cas)

    df["purchase_date"] = pd.to_datetime(
        df["purchase_date"],
        errors="coerce",
        dayfirst=False,
    )

    # Remove rows such as transport, pallets and sample-shipment costs
    excluded_references = {
        "TRANSPORT",
        "PALLETS",
        "SAMPLESHIPMENT",
        "ADDITIONAL",
    }

    df = df[
        ~df["article_reference"]
        .astype(str)
        .str.upper()
        .isin(excluded_references)
    ]

    return df


def get_purchase_information(
    purchase_df: pd.DataFrame,
    cas_number: str,
) -> dict:
    normalized_cas = normalize_cas(cas_number)

    if not normalized_cas:
        return {
            "purchased": False,
            "reason": "No valid CAS number available",
        }

    matches = purchase_df[
        purchase_df["cas_normalized"] == normalized_cas
    ].copy()

    matches = matches.dropna(subset=["purchase_date"])
    matches = matches.sort_values(
        "purchase_date",
        ascending=False,
    )

    if matches.empty:
        return {
            "purchased": False,
            "cas_number": normalized_cas,
        }

    latest = matches.iloc[0]

    suppliers = (
        matches["supplier_name"]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .tolist()
    )

    return {
        "purchased": True,
        "cas_number": normalized_cas,
        "last_purchase_date": latest["purchase_date"],
        "last_supplier": latest["supplier_name"],
        "supplier_code": latest["supplier_code"],
        "product_description": latest["product_description"],
        "article_reference": latest["article_reference"],
        "all_suppliers": suppliers,
        "purchase_count": len(matches),
        "history": matches,
    }