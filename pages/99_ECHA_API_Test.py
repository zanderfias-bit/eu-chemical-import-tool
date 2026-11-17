import glob
import json
import os
from typing import Any, Optional

import pandas as pd
import requests
import streamlit as st


# ============================================================
# CONFIGURATION
# ============================================================

APP_VERSION = "ECHA_REST_API_TEST_V2"

ECHA_BASE_URL = "https://chem.echa.europa.eu"

# Working substance endpoint from the previous successful test
ECHA_SUBSTANCE_URL = (
    ECHA_BASE_URL
    + "/api-substance-regulatory-context/v1/substance"
)

# REACH dossier-list endpoint
ECHA_DOSSIER_URL = (
    ECHA_BASE_URL
    + "/api-dossier-list/v1/dossier"
)

REQUEST_TIMEOUT = 30


# ============================================================
# STREAMLIT
# ============================================================

st.set_page_config(
    page_title="ECHA API Test",
    page_icon="🧪",
    layout="wide",
)

st.title("ECHA API Test")
st.subheader("ECHA REST API diagnostic")

st.caption(f"Version: {APP_VERSION}")

st.write(
    "This test uses the local ECHA registrations export to resolve "
    "a CAS number to an ECHA rmlId, then queries the substance and "
    "dossier REST endpoints in real time."
)


# ============================================================
# HELPERS
# ============================================================

def normalize_column_name(value: Any) -> str:
    """
    Normalize a DataFrame column name for flexible matching.
    """
    return (
        str(value)
        .strip()
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
        .replace(".", "")
    )


def normalize_value(value: Any) -> str:
    """
    Convert an Excel/CSV value into a clean string.
    """
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    text = str(value).strip()

    # Excel can occasionally convert integer-like values to 123.0
    if text.endswith(".0"):
        left = text[:-2]
        if left.isdigit():
            return left

    return text


def find_column(
    dataframe: pd.DataFrame,
    candidates: list[str],
) -> Optional[str]:
    """
    Find a column using a number of possible names.
    """
    normalized_columns = {
        normalize_column_name(column): column
        for column in dataframe.columns
    }

    for candidate in candidates:
        normalized_candidate = normalize_column_name(candidate)

        if normalized_candidate in normalized_columns:
            return normalized_columns[normalized_candidate]

    return None


def locate_local_export() -> Optional[str]:
    """
    Locate a likely ECHA registrations export in the project directory.
    """

    preferred_names = [
        "echa_registrations.xlsx",
        "echa_registration.xlsx",
        "reach_registrations.xlsx",
        "reach_registration.xlsx",
        "echa_registrations.csv",
        "reach_registrations.csv",
    ]

    for filename in preferred_names:
        if os.path.exists(filename):
            return filename

    candidates = []

    for pattern in ("*.xlsx", "*.xls", "*.csv"):
        candidates.extend(glob.glob(pattern))

    # Ignore temporary Excel lock files
    candidates = [
        path
        for path in candidates
        if not os.path.basename(path).startswith("~$")
    ]

    # Prefer filenames containing ECHA / REACH / registration
    scored = []

    for path in candidates:
        name = os.path.basename(path).lower()

        score = 0

        if "echa" in name:
            score += 5

        if "reach" in name:
            score += 4

        if "registration" in name:
            score += 3

        if "substance" in name:
            score += 1

        scored.append((score, path))

    if not scored:
        return None

    scored.sort(
        key=lambda item: (
            item[0],
            item[1],
        ),
        reverse=True,
    )

    return scored[0][1]


@st.cache_data(show_spinner=False)
def load_local_export(path: str) -> pd.DataFrame:
    """
    Load the local Excel or CSV export.
    """

    extension = os.path.splitext(path)[1].lower()

    if extension == ".csv":

        # First try automatic separator detection
        try:
            return pd.read_csv(
                path,
                sep=None,
                engine="python",
                dtype=str,
            )
        except Exception:
            return pd.read_csv(
                path,
                dtype=str,
            )

    if extension in (".xlsx", ".xls"):
        return pd.read_excel(
            path,
            dtype=str,
        )

    raise ValueError(
        f"Unsupported local export format: {extension}"
    )


def find_local_substance(
    dataframe: pd.DataFrame,
    cas_number: str,
) -> dict[str, str]:
    """
    Find CAS -> EC number -> ECHA rmlId in the local export.
    """

    cas_column = find_column(
        dataframe,
        [
            "CAS number",
            "CAS Number",
            "CAS",
            "CASNUMBER",
            "casNumber",
            "rmlCas",
        ],
    )

    ec_column = find_column(
        dataframe,
        [
            "EC number",
            "EC Number",
            "EC",
            "ECNUMBER",
            "ecNumber",
            "rmlEc",
        ],
    )

    rml_column = find_column(
        dataframe,
        [
            "rmlId",
            "RML ID",
            "RMLID",
            "RML Id",
            "ECHA rmlId",
            "substanceId",
        ],
    )

    name_column = find_column(
        dataframe,
        [
            "Name",
            "Substance name",
            "Substance Name",
            "rmlName",
            "Chemical name",
            "Chemical Name",
        ],
    )

    if cas_column is None:
        raise ValueError(
            "No CAS-number column could be found in the local export."
        )

    if rml_column is None:
        raise ValueError(
            "No rmlId column could be found in the local export."
        )

    normalized_cas = cas_number.strip()

    mask = (
        dataframe[cas_column]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq(normalized_cas)
    )

    matches = dataframe.loc[mask]

    if matches.empty:
        raise LookupError(
            f"CAS number {normalized_cas} was not found "
            "in the local ECHA export."
        )

    row = matches.iloc[0]

    result = {
        "cas": normalized_cas,
        "ec": (
            normalize_value(row[ec_column])
            if ec_column is not None
            else ""
        ),
        "rml_id": normalize_value(row[rml_column]),
        "name": (
            normalize_value(row[name_column])
            if name_column is not None
            else ""
        ),
    }

    if not result["rml_id"]:
        raise ValueError(
            f"CAS {normalized_cas} was found, "
            "but the rmlId is empty."
        )

    return result


def build_headers(
    rml_id: Optional[str] = None,
) -> dict[str, str]:
    """
    Headers used for ECHA CHEM REST requests.
    """

    headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        ),
    }

    if rml_id:
        headers["Referer"] = (
            f"{ECHA_BASE_URL}/{rml_id}/overview"
        )

    return headers


def parse_response(
    response: requests.Response,
) -> dict[str, Any]:
    """
    Safely parse an ECHA HTTP response.
    """

    result = {
        "status_code": response.status_code,
        "request_url": response.url,
    }

    try:
        result["data"] = response.json()

    except ValueError:
        result["data"] = None
        result["text"] = response.text[:10000]

    return result


# ============================================================
# SUBSTANCE API
# ============================================================

def get_echa_substance(
    rml_id: str,
) -> dict[str, Any]:
    """
    Query the ECHA CHEM substance endpoint.

    The successful previous diagnostic demonstrated that the
    substance endpoint can resolve the supplied rmlId.
    """

    rml_id = str(rml_id).strip()

    if not rml_id:
        raise ValueError("rmlId is empty.")

    # Keep this isolated so changing the dossier parameters
    # cannot break the already-working substance lookup.
    candidate_parameter_sets = [
        {
            "rmlId": rml_id,
        },
    ]

    last_result = None

    for params in candidate_parameter_sets:

        response = requests.get(
            ECHA_SUBSTANCE_URL,
            params=params,
            headers=build_headers(rml_id),
            timeout=REQUEST_TIMEOUT,
        )

        result = parse_response(response)

        result["request_params"] = params

        last_result = result

        if response.status_code == 200:
            return result

    return last_result


# ============================================================
# DOSSIER API
# ============================================================

def get_echa_dossiers(
    rml_id: str,
    registration_status: Optional[str] = None,
) -> dict[str, Any]:
    """
    Retrieve REACH dossiers for an ECHA rmlId.

    registration_status:
        None       -> no status filter
        Active     -> active registrations
        Inactive   -> inactive registrations
    """

    rml_id = str(rml_id).strip()

    if not rml_id:
        raise ValueError("rmlId is empty.")

    #
    # IMPORTANT
    #
    # All required parameters are created in ONE dictionary.
    #
    # This prevents a later assignment such as:
    #
    # params = {"legislation": "..."}
    #
    # from accidentally deleting rmlId.
    #

    params = {
        "rmlId": rml_id,
        "legislation": "REACH",
        "pageIndex": 1,
        "pageSize": 100,
    }

    if registration_status:
        params["registrationStatuses"] = registration_status

    response = requests.get(
        ECHA_DOSSIER_URL,
        params=params,
        headers=build_headers(rml_id),
        timeout=REQUEST_TIMEOUT,
    )

    result = parse_response(response)

    result["request_params"] = params
    result["registration_status"] = registration_status

    return result


# ============================================================
# CLEAN DISPLAY
# ============================================================

def clean_substance_for_display(
    data: Any,
) -> Any:
    """
    Remove very large fields such as img64 from the diagnostic output.
    """

    if not isinstance(data, dict):
        return data

    cleaned = data.copy()

    cleaned.pop("img64", None)

    return cleaned


def extract_dossier_items(
    data: Any,
) -> list[dict[str, Any]]:
    """
    Extract dossier items from common ECHA response structures.
    """

    if isinstance(data, list):
        return [
            item
            for item in data
            if isinstance(item, dict)
        ]

    if not isinstance(data, dict):
        return []

    items = data.get("items")

    if isinstance(items, list):
        return [
            item
            for item in items
            if isinstance(item, dict)
        ]

    content = data.get("content")

    if isinstance(content, list):
        return [
            item
            for item in content
            if isinstance(item, dict)
        ]

    results = data.get("results")

    if isinstance(results, list):
        return [
            item
            for item in results
            if isinstance(item, dict)
        ]

    return []


def dossier_summary(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Produce a compact dossier diagnostic summary while retaining
    the identifiers needed for the next development step.
    """

    summaries = []

    interesting_fields = [
        "assetExternalId",
        "dossierId",
        "uuid",
        "id",
        "registrationStatus",
        "status",
        "registrationType",
        "submissionType",
        "tonnageBand",
        "jointSubmission",
        "leadRegistrant",
        "registrant",
        "legalEntity",
        "companyName",
    ]

    for index, item in enumerate(items, start=1):

        row = {
            "item": index,
        }

        for field in interesting_fields:
            if field in item:
                row[field] = item[field]

        # If none of the expected identifiers are present,
        # show the complete item during diagnostics.
        if len(row) == 1:
            row["raw"] = item

        summaries.append(row)

    return summaries


# ============================================================
# USER INPUT
# ============================================================

cas_number = st.text_input(
    "CAS number",
    value="128-37-0",
    placeholder="e.g. 128-37-0",
).strip()


# ============================================================
# RUN TEST
# ============================================================

if cas_number:

    try:

        # --------------------------------------------------------
        # LOCAL LOOKUP
        # --------------------------------------------------------

        export_path = locate_local_export()

        if export_path is None:
            st.error(
                "No local ECHA registrations Excel/CSV export "
                "could be found in the app directory."
            )
            st.stop()

        local_data = load_local_export(export_path)

        substance = find_local_substance(
            local_data,
            cas_number,
        )

        rml_id = substance["rml_id"]

        st.success("ECHA API test completed.")

        st.subheader("1. Local substance match")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "CAS number",
                substance["cas"],
            )

        with col2:
            st.metric(
                "EC number",
                substance["ec"] or "Unknown",
            )

        with col3:
            st.metric(
                "ECHA rmlId",
                rml_id,
            )

        if substance["name"]:
            st.write(
                f"**Name:** {substance['name']}"
            )

        echa_overview_url = (
            f"{ECHA_BASE_URL}/{rml_id}/overview"
        )

        st.write(
            f"**ECHA URL:** {echa_overview_url}"
        )


        # --------------------------------------------------------
        # SUBSTANCE API
        # --------------------------------------------------------

        st.subheader("2. Substance API")

        try:

            substance_result = get_echa_substance(
                rml_id
            )

            substance_status = (
                substance_result["status_code"]
            )

            if substance_status == 200:

                st.success(
                    "The substance endpoint returned HTTP 200."
                )

                substance_data = (
                    substance_result.get("data")
                )

                cleaned_substance = (
                    clean_substance_for_display(
                        substance_data
                    )
                )

                # Small useful summary first
                if isinstance(substance_data, dict):

                    s1, s2, s3 = st.columns(3)

                    with s1:
                        st.metric(
                            "REACH status",
                            (
                                "Registered"
                                if "REACH REGISTERED"
                                in substance_data.get(
                                    "listParticipation",
                                    [],
                                )
                                else "Not confirmed"
                            ),
                        )

                    with s2:
                        st.metric(
                            "Tonnage band",
                            substance_data.get(
                                "tonnageBand"
                            )
                            or "Unknown",
                        )

                    with s3:
                        st.metric(
                            "rmlId",
                            substance_data.get(
                                "rmlId"
                            )
                            or rml_id,
                        )

                with st.expander(
                    "Substance API response",
                    expanded=False,
                ):
                    st.json(cleaned_substance)

            else:

                st.error(
                    "ECHA substance endpoint returned "
                    f"HTTP {substance_status}."
                )

                st.write("Parameters sent:")
                st.json(
                    substance_result.get(
                        "request_params",
                        {},
                    )
                )

                if (
                    substance_result.get("data")
                    is not None
                ):
                    st.json(
                        substance_result["data"]
                    )
                else:
                    st.code(
                        substance_result.get(
                            "text",
                            "No response body.",
                        )
                    )

        except requests.RequestException as exc:

            st.error(
                "ECHA substance request failed: "
                f"{exc}"
            )


        # --------------------------------------------------------
        # DOSSIER API
        # --------------------------------------------------------

        st.subheader("3. REACH dossier API")

        status_tests = [
            ("No filter", None),
            ("Active", "Active"),
            ("Inactive", "Inactive"),
        ]

        for label, registration_status in status_tests:

            with st.expander(
                f"Registration status: {label}",
                expanded=(
                    registration_status == "Active"
                ),
            ):

                try:

                    dossier_result = get_echa_dossiers(
                        rml_id=rml_id,
                        registration_status=(
                            registration_status
                        ),
                    )

                    st.caption(
                        "Request parameters actually sent "
                        "to ECHA"
                    )

                    st.json(
                        dossier_result[
                            "request_params"
                        ]
                    )

                    st.caption("Final request URL")
                    st.code(
                        dossier_result["request_url"]
                    )

                    dossier_status = (
                        dossier_result["status_code"]
                    )

                    if dossier_status == 200:

                        st.success(
                            "ECHA dossier endpoint "
                            "returned HTTP 200."
                        )

                        dossier_data = (
                            dossier_result.get(
                                "data"
                            )
                        )

                        items = extract_dossier_items(
                            dossier_data
                        )

                        st.metric(
                            "Dossiers returned",
                            len(items),
                        )

                        if items:

                            summaries = (
                              s)
                            

                            st.write(
                                "**Dossier summary**"
                            )

                            st.json(summaries)

                            # Explicitly surface assetExternalId
                            asset_ids = []

                            for item in items:
                                asset_id = item.get(
                                    "assetExternalId"
                                )

                                if asset_id:
                                    asset_ids.append(
                                        str(asset_id)
                                    )

                            if asset_ids:

                                st.success(
                                    "assetExternalId found."
                                )

                                for asset_id in asset_ids:
                                    st.code(asset_id)

                            else:

                                st.info(
                                    "The dossier call worked, "
                                    "but no assetExternalId was "
                                    "found in the returned items."
                                )

                        else:

                            st.info(
                                "The request succeeded, "
                                "but no dossier items were "
                                "returned for this filter."
                            )

                        with st.expander(
                            "Complete dossier API response",
                            expanded=False,
                        ):
                            st.json(dossier_data)

                    else:

                        st.error(
                            "ECHA dossier endpoint returned "
                            f"HTTP {dossier_status}."
                        )

                        if (
                            dossier_result.get("data")
                            is not None
                        ):
                            st.json(
                                dossier_result["data"]
                            )

                        else:
                            st.code(
                                dossier_result.get(
                                    "text",
                                    "No response body.",
                                )
                            )

                except requests.RequestException as exc:

                    st.error(
                        "ECHA dossier request failed: "
                        f"{exc}"
                    )

                except Exception as exc:

                    st.error(
                        "Unexpected ECHA dossier error: "
                        f"{exc}"
                    )


        # --------------------------------------------------------
        # NEXT STEP INFO
        # --------------------------------------------------------

        st.subheader("4. Diagnostic conclusion")

        st.info(
            "If the Active dossier request returns HTTP 200, "
            "the next step is to use the returned dossier "
            "identifier / assetExternalId to retrieve the "
            "published dossier information and identify the "
            "available registrant or legal-entity information."
        )


    except LookupError as exc:

        st.warning(str(exc))

    except ValueError as exc:

        st.error(str(exc))

    except requests.RequestException as exc:

        st.error(
            f"Network/API error: {exc}"
        )

    except Exception as exc:

        st.exception(exc)