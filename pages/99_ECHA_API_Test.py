import re
from pathlib import Path

import pandas as pd
import requests
import streamlit as st


# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="ECHA REST API Test",
    page_icon="🧪",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_REST_API_TEST_V2"


# --------------------------------------------------
# PATHS
# --------------------------------------------------
# 99_ECHA_API_Test.py staat in de map pages.
# parent.parent verwijst daarom naar de projectmap.
BASE_DIR = Path(__file__).resolve().parent.parent

ECHA_DATA_FILE = (
    BASE_DIR
    / "data"
    / "reach_registrations.xlsx"
)

ECHA_SHEET_NAME = "Substances list"


# --------------------------------------------------
# EXCEL COLUMNS
# --------------------------------------------------
NAME_COLUMN = "Name"
EC_COLUMN = "EC Number"
CAS_COLUMN = "CAS Number"
URL_COLUMN = "Link to substance's overview page"


# --------------------------------------------------
# ECHA API
# --------------------------------------------------
ECHA_BASE_URL = "https://chem.echa.europa.eu"

SUBSTANCE_ENDPOINT = (
    ECHA_BASE_URL
    + "/api-substance/v1/substance/{rml_id}"
)

DOSSIER_ENDPOINT = (
    ECHA_BASE_URL
    + "/api-dossier-list/v1/dossier"
)


# --------------------------------------------------
# REQUEST CONFIGURATION
# --------------------------------------------------
CONNECT_TIMEOUT_SECONDS = 30
READ_TIMEOUT_SECONDS = 90

REQUEST_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


# --------------------------------------------------
# TEXT NORMALISATION
# --------------------------------------------------
def normalise_text(value):
    if value is None:
        return ""

    value = str(value).strip()

    if value.lower() in {
        "",
        "nan",
        "none",
    }:
        return ""

    if value == "-":
        return ""

    return " ".join(
        value.replace("\xa0", " ").split()
    ).strip()


# --------------------------------------------------
# CAS FORMAT VALIDATION
# --------------------------------------------------
def looks_like_cas_number(value):
    value = normalise_text(value)

    return bool(
        re.fullmatch(
            r"\d{2,7}-\d{2}-\d",
            value,
        )
    )


# --------------------------------------------------
# EXTRACT ECHA RML ID
# --------------------------------------------------
def extract_rml_id(echa_url):
    """
    Extract an ECHA substance identifier such as
    100.004.439 from an ECHA overview URL.
    """

    echa_url = normalise_text(echa_url)

    match = re.search(
        r"/(\d{3}\.\d{3}\.\d{3})(?:/|$)",
        echa_url,
    )

    if not match:
        return ""

    return match.group(1)


# --------------------------------------------------
# LOAD ECHA EXCEL DATA
# --------------------------------------------------
@st.cache_data(show_spinner=False)
def load_echa_data():
    if not ECHA_DATA_FILE.exists():
        raise FileNotFoundError(
            "The ECHA Excel file was not found at: "
            f"{ECHA_DATA_FILE}"
        )

    dataframe = pd.read_excel(
        ECHA_DATA_FILE,
        sheet_name=ECHA_SHEET_NAME,
        dtype=str,
        keep_default_na=False,
        engine="openpyxl",
    )

    required_columns = [
        NAME_COLUMN,
        EC_COLUMN,
        CAS_COLUMN,
        URL_COLUMN,
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise RuntimeError(
            "The ECHA Excel file is missing these columns: "
            + ", ".join(missing_columns)
        )

    dataframe[CAS_COLUMN] = (
        dataframe[CAS_COLUMN]
        .astype(str)
        .map(normalise_text)
    )

    return dataframe


# --------------------------------------------------
# FIND SUBSTANCE IN LOCAL ECHA INDEX
# --------------------------------------------------
def find_substance_by_cas(
    dataframe,
    cas_number,
):
    cas_number = normalise_text(cas_number)

    matches = dataframe[
        dataframe[CAS_COLUMN] == cas_number
    ]

    results = []

    for _, row in matches.iterrows():
        echa_url = normalise_text(
            row[URL_COLUMN]
        )

        results.append(
            {
                "name": normalise_text(
                    row[NAME_COLUMN]
                ),
                "ec_number": normalise_text(
                    row[EC_COLUMN]
                ),
                "cas_number": normalise_text(
                    row[CAS_COLUMN]
                ),
                "echa_url": echa_url,
                "rml_id": extract_rml_id(
                    echa_url
                ),
            }
        )

    return results


# --------------------------------------------------
# CREATE HTTP SESSION
# --------------------------------------------------
def create_http_session():
    session = requests.Session()

    session.headers.update(
        REQUEST_HEADERS
    )

    return session


# --------------------------------------------------
# EXECUTE ECHA GET REQUEST
# --------------------------------------------------
def execute_echa_request(
    session,
    url,
    params=None,
):
    print(
        f"ECHA REST GET: {url}",
        flush=True,
    )

    if params:
        print(
            f"ECHA REST PARAMS: {params}",
            flush=True,
        )

    try:
        response = session.get(
            url,
            params=params,
            timeout=(
                CONNECT_TIMEOUT_SECONDS,
                READ_TIMEOUT_SECONDS,
            ),
            allow_redirects=True,
        )

    except requests.Timeout as error:
        raise RuntimeError(
            "The ECHA REST request timed out: "
            f"{error}"
        ) from error

    except requests.RequestException as error:
        raise RuntimeError(
            "The ECHA REST request failed: "
            f"{error}"
        ) from error

    print(
        f"ECHA REST FINAL URL: {response.url}",
        flush=True,
    )

    print(
        f"ECHA REST STATUS: {response.status_code}",
        flush=True,
    )

    print(
        "ECHA REST CONTENT TYPE: "
        f"{response.headers.get('content-type', '')}",
        flush=True,
    )

    preview = response.text[:1000]

    print(
        f"ECHA REST BODY PREVIEW: {preview}",
        flush=True,
    )

    return response


# --------------------------------------------------
# PARSE JSON RESPONSE
# --------------------------------------------------
def parse_json_response(
    response,
    description,
):
    content_type = (
        response.headers
        .get("content-type", "")
        .lower()
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{description} returned HTTP "
            f"{response.status_code}. "
            f"Response: {response.text[:1000]}"
        )

    if (
        "application/json" not in content_type
        and not response.text.lstrip().startswith(
            ("{", "[")
        )
    ):
        raise RuntimeError(
            f"{description} did not return JSON. "
            f"Content-Type: {content_type}. "
            f"Response: {response.text[:1000]}"
        )

    try:
        return response.json()

    except ValueError as error:
        raise RuntimeError(
            f"{description} returned invalid JSON. "
            f"Response: {response.text[:1000]}"
        ) from error


# --------------------------------------------------
# REMOVE VERY LARGE FIELDS FROM DISPLAY
# --------------------------------------------------
def clean_substance_response(api_body):
    """
    Remove the large base64 molecular image from the displayed
    Substance API response. The original API response is otherwise
    left unchanged.
    """

    if not isinstance(api_body, dict):
        return api_body

    cleaned_body = api_body.copy()
    cleaned_body.pop("img64", None)

    return cleaned_body


# --------------------------------------------------
# GET SUBSTANCE IDENTITY
# --------------------------------------------------
def get_substance_identity(
    session,
    rml_id,
):
    rml_id = normalise_text(rml_id)

    if not rml_id:
        raise RuntimeError(
            "The rmlId is empty."
        )

    endpoint = SUBSTANCE_ENDPOINT.format(
        rml_id=rml_id
    )

    response = execute_echa_request(
        session=session,
        url=endpoint,
    )

    return {
        "status_code": response.status_code,
        "url": response.url,
        "body": parse_json_response(
            response,
            "ECHA substance endpoint",
        ),
    }


# --------------------------------------------------
# GET REACH DOSSIERS
# --------------------------------------------------
def get_reach_dossiers(
    session,
    rml_id,
    registration_status=None,
):
    """
    Retrieve REACH dossiers for the supplied ECHA rmlId.

    All basic parameters are created in one dictionary so that adding
    legislation or status cannot accidentally remove rmlId.
    """

    rml_id = normalise_text(rml_id)

    if not rml_id:
        raise RuntimeError(
            "The dossier request cannot be executed because "
            "the rmlId is empty."
        )

    params = {
        "pageIndex": 1,
        "pageSize": 100,
        "rmlId": rml_id,
        "legislation": "REACH",
    }

    if registration_status:
        params["registrationStatuses"] = (
            registration_status
        )

    response = execute_echa_request(
        session=session,
        url=DOSSIER_ENDPOINT,
        params=params,
    )

    return {
        "status_code": response.status_code,
        "url": response.url,
        "params": params,
        "body": parse_json_response(
            response,
            "ECHA dossier endpoint",
        ),
    }


# --------------------------------------------------
# EXTRACT ITEMS FROM API RESULT
# --------------------------------------------------
def extract_items(api_body):
    if isinstance(api_body, list):
        return api_body

    if not isinstance(api_body, dict):
        return []

    for key in (
        "items",
        "content",
        "results",
        "data",
    ):
        value = api_body.get(key)

        if isinstance(value, list):
            return value

        # Some APIs place an items/content list inside data.
        if isinstance(value, dict):
            for nested_key in (
                "items",
                "content",
                "results",
            ):
                nested_value = value.get(
                    nested_key
                )

                if isinstance(
                    nested_value,
                    list,
                ):
                    return nested_value

    return []


# --------------------------------------------------
# EXTRACT ASSET EXTERNAL IDS
# --------------------------------------------------
def extract_asset_external_ids(items):
    asset_external_ids = []

    for item in items:
        if not isinstance(item, dict):
            continue

        asset_external_id = item.get(
            "assetExternalId"
        )

        if asset_external_id:
            asset_external_ids.append(
                str(asset_external_id)
            )

    return list(
        dict.fromkeys(asset_external_ids)
    )


# --------------------------------------------------
# MAIN TEST
# --------------------------------------------------
def run_test(cas_number):
    print(
        f"ECHA code version: {CODE_VERSION}",
        flush=True,
    )

    print(
        f"ECHA API test started for CAS "
        f"{cas_number}",
        flush=True,
    )

    dataframe = load_echa_data()

    local_results = find_substance_by_cas(
        dataframe=dataframe,
        cas_number=cas_number,
    )

    if not local_results:
        raise RuntimeError(
            f"CAS {cas_number} was not found in "
            "reach_registrations.xlsx."
        )

    selected = local_results[0]

    if not selected["rml_id"]:
        raise RuntimeError(
            "The ECHA rmlId could not be extracted "
            f"from this URL: {selected['echa_url']}"
        )

    print(
        f"ECHA local match: {selected}",
        flush=True,
    )

    session = create_http_session()

    substance_result = None
    substance_error = None

    try:
        substance_result = get_substance_identity(
            session=session,
            rml_id=selected["rml_id"],
        )

    except Exception as error:
        substance_error = str(error)

        print(
            f"ECHA substance endpoint error: "
            f"{error}",
            flush=True,
        )

    dossier_attempts = []

    for status in (
        None,
        "Active",
        "Inactive",
    ):
        try:
            result = get_reach_dossiers(
                session=session,
                rml_id=selected["rml_id"],
                registration_status=status,
            )

            items = extract_items(
                result["body"]
            )

            asset_external_ids = (
                extract_asset_external_ids(
                    items
                )
            )

            dossier_attempts.append(
                {
                    "registration_status": (
                        status or "No filter"
                    ),
                    "success": True,
                    "status_code": (
                        result["status_code"]
                    ),
                    "url": result["url"],
                    "params": result["params"],
                    "item_count": len(items),
                    "items": items,
                    "asset_external_ids": (
                        asset_external_ids
                    ),
                    "raw_body": result["body"],
                    "error": None,
                }
            )

        except Exception as error:
            dossier_attempts.append(
                {
                    "registration_status": (
                        status or "No filter"
                    ),
                    "success": False,
                    "status_code": None,
                    "url": None,
                    "params": {
                        "pageIndex": 1,
                        "pageSize": 100,
                        "rmlId": selected["rml_id"],
                        "legislation": "REACH",
                        **(
                            {
                                "registrationStatuses": (
                                    status
                                )
                            }
                            if status
                            else {}
                        ),
                    },
                    "item_count": 0,
                    "items": [],
                    "asset_external_ids": [],
                    "raw_body": None,
                    "error": str(error),
                }
            )

            print(
                "ECHA dossier endpoint error "
                f"for status {status}: {error}",
                flush=True,
            )

    return {
        "version": CODE_VERSION,
        "local_substance": selected,
        "substance_result": substance_result,
        "substance_error": substance_error,
        "dossier_attempts": dossier_attempts,
    }


# --------------------------------------------------
# STREAMLIT UI
# --------------------------------------------------
st.title("ECHA REST API diagnostic")

st.caption(
    f"Version: {CODE_VERSION}"
)

st.write(
    "This test uses the local ECHA registrations export "
    "to resolve a CAS number to an ECHA rmlId, then queries "
    "the substance and dossier REST endpoints in real time."
)

st.caption(
    f"Local ECHA file: {ECHA_DATA_FILE}"
)

cas_number = st.text_input(
    "CAS number",
    value="128-37-0",
    placeholder="For example: 128-37-0",
)

run_button = st.button(
    "Run ECHA API test",
    type="primary",
)

if run_button:
    cleaned_cas = normalise_text(
        cas_number
    )

    if not looks_like_cas_number(
        cleaned_cas
    ):
        st.error(
            "Enter a valid CAS number, for example "
            "128-37-0."
        )

    else:
        with st.spinner(
            "Testing the ECHA REST endpoints..."
        ):
            try:
                test_result = run_test(
                    cleaned_cas
                )

            except Exception as error:
                st.error(
                    f"ECHA API test failed: {error}"
                )

                print(
                    f"ECHA API test failed: {error}",
                    flush=True,
                )

            else:
                st.success(
                    "ECHA API test completed."
                )

                substance = test_result[
                    "local_substance"
                ]

                # ------------------------------------------
                # LOCAL RESULT
                # ------------------------------------------
                st.subheader(
                    "1. Local substance match"
                )

                col1, col2, col3 = st.columns(3)

                col1.metric(
                    "CAS number",
                    substance["cas_number"],
                )

                col2.metric(
                    "EC number",
                    (
                        substance["ec_number"]
                        or "Not available"
                    ),
                )

                col3.metric(
                    "ECHA rmlId",
                    substance["rml_id"],
                )

                st.write(
                    f"**Name:** {substance['name']}"
                )

                st.write(
                    f"**ECHA URL:** "
                    f"{substance['echa_url']}"
                )

                # ------------------------------------------
                # SUBSTANCE API
                # ------------------------------------------
                st.subheader(
                    "2. Substance API"
                )

                if test_result[
                    "substance_result"
                ]:
                    substance_api = test_result[
                        "substance_result"
                    ]

                    st.success(
                        "The substance endpoint "
                        f"returned HTTP "
                        f"{substance_api['status_code']}."
                    )

                    substance_body = (
                        substance_api["body"]
                    )

                    if isinstance(
                        substance_body,
                        dict,
                    ):
                        summary_col1, summary_col2 = (
                            st.columns(2)
                        )

                        participation = (
                            substance_body.get(
                                "listParticipation",
                                [],
                            )
                        )

                        is_reach_registered = (
                            isinstance(
                                participation,
                                list,
                            )
                            and (
                                "REACH REGISTERED"
                                in participation
                            )
                        )

                        summary_col1.metric(
                            "REACH status",
                            (
                                "Registered"
                                if is_reach_registered
                                else "Not confirmed"
                            ),
                        )

                        summary_col2.metric(
                            "Tonnage band",
                            (
                                substance_body.get(
                                    "tonnageBand"
                                )
                                or "Not available"
                            ),
                        )

                    with st.expander(
                        "Substance API response",
                        expanded=False,
                    ):
                        st.json(
                            clean_substance_response(
                                substance_body
                            )
                        )

                else:
                    st.error(
                        test_result[
                            "substance_error"
                        ]
                        or
                        "The substance endpoint failed."
                    )

                # ------------------------------------------
                # DOSSIER API
                # ------------------------------------------
                st.subheader(
                    "3. REACH dossier API"
                )

                successful_dossier_call = False

                for attempt in test_result[
                    "dossier_attempts"
                ]:
                    with st.expander(
                        (
                            "Registration status: "
                            f"{attempt['registration_status']}"
                        ),
                        expanded=(
                            attempt[
                                "registration_status"
                            ]
                            == "Active"
                        ),
                    ):
                        st.markdown(
                            "**Request parameters**"
                        )

                        st.json(
                            attempt["params"]
                        )

                        if attempt["url"]:
                            st.markdown(
                                "**Final API URL**"
                            )

                            st.code(
                                attempt["url"],
                                language=None,
                            )

                        if attempt["success"]:
                            successful_dossier_call = True

                            st.success(
                                "HTTP "
                                f"{attempt['status_code']} | "
                                f"{attempt['item_count']} "
                                "dossier item(s)"
                            )

                            if attempt[
                                "asset_external_ids"
                            ]:
                                st.markdown(
                                    "**assetExternalId values**"
                                )

                                for asset_id in attempt[
                                    "asset_external_ids"
                                ]:
                                    st.code(
                                        asset_id,
                                        language=None,
                                    )

                            if attempt["items"]:
                                st.markdown(
                                    "**Dossier items**"
                                )

                                try:
                                    st.dataframe(
                                        pd.json_normalize(
                                            attempt["items"]
                                        ),
                                        use_container_width=True,
                                        hide_index=True,
                                    )

                                except Exception:
                                    st.json(
                                        attempt["items"]
                                    )

                            else:
                                st.info(
                                    "The request succeeded, "
                                    "but no dossier items were "
                                    "returned for this filter."
                                )

                            with st.expander(
                                "Raw dossier JSON response",
                                expanded=False,
                            ):
                                st.json(
                                    attempt["raw_body"]
                                )

                        else:
                            st.error(
                                attempt["error"]
                            )

                if successful_dossier_call:
                    st.info(
                        "The REST route is reachable. "
                        "The next step is to inspect the "
                        "returned dossier fields and use "
                        "assetExternalId for the published "
                        "dossier information."
                    )