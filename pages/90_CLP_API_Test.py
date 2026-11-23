import json
import re
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --------------------------------------------------
# PAGE SETTINGS
# --------------------------------------------------
st.set_page_config(
    page_title="ECHA CLP Test",
    page_icon="⚠️",
    layout="wide",
)

st.title("⚠️ ECHA Classification & Labelling Test")

st.write(
    "This separate test page searches ECHA CHEM, selects a substance "
    "and requests the available Classification & Labelling overview. "
    "The raw response is displayed so that the final CLP parser can be "
    "built from ECHA's actual response structure."
)

st.info(
    "Recommended first test: BHT, CAS 128-37-0. "
    "The expected ECHA rmlId is 100.004.439."
)


# --------------------------------------------------
# ECHA API CONFIGURATION
# --------------------------------------------------
ECHA_BASE_URL = "https://chem.echa.europa.eu"

SUBSTANCE_SEARCH_API_URL = (
    f"{ECHA_BASE_URL}/api-substance/v1/substance"
)

CLP_OVERVIEW_INFO_URL = (
    f"{ECHA_BASE_URL}"
    "/api-cnl-inventory/prominent/overview/info"
)

CONNECT_TIMEOUT_SECONDS = 20
READ_TIMEOUT_SECONDS = 90

ECHA_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


# --------------------------------------------------
# GENERIC HELPERS
# --------------------------------------------------
def clean_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, (dict, list, tuple)):
        return json.dumps(
            value,
            ensure_ascii=False,
        )

    text = str(value).strip()

    if text.lower() in {
        "",
        "none",
        "null",
        "nan",
    }:
        return ""

    return " ".join(text.split())


def clean_identifier(value: Any) -> str:
    """
    Format CAS and EC identifiers without
    JSON list brackets or quotation marks.
    """
    if value is None:
        return ""

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        cleaned_values = []

        for item in value:
            cleaned_item = clean_identifier(item)

            if (
                cleaned_item
                and cleaned_item not in cleaned_values
            ):
                cleaned_values.append(cleaned_item)

        return ", ".join(cleaned_values)

    if isinstance(value, dict):
        return clean_text(value)

    return clean_text(value)


def looks_like_cas(value: str) -> bool:
    return bool(
        re.fullmatch(
            r"\d{2,7}-\d{2}-\d",
            value.strip(),
        )
    )


def validate_cas_locally(cas_number: str) -> bool:
    """
    Validate a CAS Registry Number using its check digit.

    This is included locally so that the test page does not depend
    on another project module.
    """
    if not looks_like_cas(cas_number):
        return False

    digits, check_digit = cas_number.rsplit("-", 1)

    digits = digits.replace("-", "")

    total = sum(
        int(digit) * position
        for position, digit in enumerate(
            reversed(digits),
            start=1,
        )
    )

    return total % 10 == int(check_digit)


def create_echa_session() -> requests.Session:
    session = requests.Session()

    session.headers.update(ECHA_HEADERS)

    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.75,
        status_forcelist=(
            429,
            500,
            502,
            503,
            504,
        ),
        allowed_methods=frozenset(
            {
                "GET",
            }
        ),
        respect_retry_after_header=True,
        raise_on_status=False,
    )

    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=retry,
        ),
    )

    return session


def echa_get(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    referer: str | None = None,
) -> dict:
    request_headers = (
        {
            "Referer": referer,
        }
        if referer
        else None
    )

    try:
        response = session.get(
            url,
            params=params,
            headers=request_headers,
            timeout=(
                CONNECT_TIMEOUT_SECONDS,
                READ_TIMEOUT_SECONDS,
            ),
            allow_redirects=True,
        )

    except requests.Timeout as error:
        return {
            "response": None,
            "json": None,
            "error": (
                "Request timed out: "
                f"{error}"
            ),
        }

    except requests.RequestException as error:
        return {
            "response": None,
            "json": None,
            "error": (
                "Request failed: "
                f"{error}"
            ),
        }

    try:
        response_json = response.json()

    except ValueError:
        response_json = None

    return {
        "response": response,
        "json": response_json,
        "error": None,
    }


def extract_items(response_json: Any) -> list:
    if not isinstance(response_json, dict):
        return []

    items = response_json.get(
        "items",
        [],
    )

    if not isinstance(items, list):
        return []

    return items


def extract_state(response_json: Any) -> dict:
    if not isinstance(response_json, dict):
        return {}

    state = response_json.get(
        "state",
        {},
    )

    if not isinstance(state, dict):
        return {}

    return state


def find_first_field(
    value: Any,
    possible_keys: set[str],
) -> Any:
    wanted_keys = {
        key.lower()
        for key in possible_keys
    }

    if isinstance(value, dict):
        for key, nested_value in value.items():
            if str(key).lower() in wanted_keys:
                if not isinstance(
                    nested_value,
                    (
                        dict,
                        list,
                    ),
                ):
                    return nested_value

        for nested_value in value.values():
            result = find_first_field(
                nested_value,
                possible_keys,
            )

            if result not in (
                None,
                "",
            ):
                return result

    elif isinstance(value, list):
        for item in value:
            result = find_first_field(
                item,
                possible_keys,
            )

            if result not in (
                None,
                "",
            ):
                return result

    return None


def flatten_json(
    value: Any,
    parent_path: str = "",
) -> list:
    """
    Convert nested JSON into a table containing one row
    for every scalar value.
    """
    rows = []

    if isinstance(value, dict):
        if not value:
            rows.append(
                {
                    "Path": parent_path or "$",
                    "Field": "",
                    "Value": "{}",
                    "Value Type": "dict",
                }
            )

        for key, nested_value in value.items():
            path = (
                f"{parent_path}.{key}"
                if parent_path
                else str(key)
            )

            rows.extend(
                flatten_json(
                    nested_value,
                    path,
                )
            )

    elif isinstance(value, list):
        if not value:
            rows.append(
                {
                    "Path": parent_path or "$",
                    "Field": "",
                    "Value": "[]",
                    "Value Type": "list",
                }
            )

        for index, item in enumerate(value):
            path = f"{parent_path}[{index}]"

            rows.extend(
                flatten_json(
                    item,
                    path,
                )
            )

    else:
        field_name = (
            parent_path
            .replace("]", "")
            .split(".")[-1]
            .split("[")[0]
        )

        rows.append(
            {
                "Path": parent_path or "$",
                "Field": field_name,
                "Value": clean_text(value),
                "Value Type": type(value).__name__,
            }
        )

    return rows


def is_possible_clp_field(path: str) -> bool:
    path_lower = path.lower()

    clp_terms = (
        "classification",
        "classifications",
        "hazard",
        "hazardclass",
        "hazardcategory",
        "hazardstatement",
        "statement",
        "pictogram",
        "signalword",
        "signal",
        "labelling",
        "labeling",
        "clp",
        "harmonised",
        "harmonized",
        "annexvi",
        "annex_vi",
        "indexnumber",
        "index_number",
        "concentrationlimit",
        "concentration_limit",
        "specificconcentration",
        "m-factor",
        "mfactor",
        "note",
        "atp",
        "effective",
        "applicationdate",
        "implementationdate",
    )

    return any(
        term in path_lower
        for term in clp_terms
    )


def is_possible_identifier_field(path: str) -> bool:
    field_name = (
        path
        .replace("]", "")
        .split(".")[-1]
        .split("[")[0]
        .lower()
    )

    return (
        field_name == "id"
        or field_name.endswith("id")
        or field_name.endswith("identifier")
        or field_name in {
            "uuid",
            "key",
            "code",
        }
    )


# --------------------------------------------------
# SUBSTANCE SEARCH
# --------------------------------------------------
def normalise_substance(item: Any) -> dict:
    if not isinstance(item, dict):
        return {
            "Name": "",
            "EC Number": "",
            "CAS Number": "",
            "rmlId": "",
            "URL": "",
            "_raw": item,
        }

    substance_index = item.get(
        "substanceIndex",
        {},
    )

    if not isinstance(substance_index, dict):
        substance_index = {}

    rml_id = (
        substance_index.get("rmlId")
        or find_first_field(
            item,
            {
                "rmlId",
            },
        )
    )

    substance_name = (
        substance_index.get("rmlName")
        or find_first_field(
            item,
            {
                "rmlName",
                "name",
                "substanceName",
                "preferredName",
                "publicName",
            },
        )
    )

    cas_number = (
        substance_index.get("rmlCas")
        or substance_index.get("casNumber")
        or find_first_field(
            item,
            {
                "rmlCas",
                "casNumber",
                "cas",
            },
        )
    )

    ec_number = (
        substance_index.get("ecNumber")
        or substance_index.get("rmlEc")
        or substance_index.get("rmlEcNumber")
        or find_first_field(
            item,
            {
                "ecNumber",
                "rmlEc",
                "rmlEcNumber",
                "ec",
            },
        )
    )

    clean_rml_id = clean_text(rml_id)

    return {
        "Name": clean_text(substance_name),
        "EC Number": clean_identifier(ec_number),
        "CAS Number": clean_identifier(cas_number),
        "rmlId": clean_rml_id,
        "URL": (
            f"{ECHA_BASE_URL}/{clean_rml_id}/overview"
            if clean_rml_id
            else ""
        ),
        "_raw": item,
    }


def substance_result_score(
    result: dict,
    search_text: str,
) -> int:
    query = clean_text(search_text).lower()

    name = result.get(
        "Name",
        "",
    ).lower()

    cas_number = result.get(
        "CAS Number",
        "",
    ).lower()

    ec_number = result.get(
        "EC Number",
        "",
    ).lower()

    rml_id = result.get(
        "rmlId",
        "",
    ).lower()

    if query and query == cas_number:
        return 100

    if query and query == ec_number:
        return 95

    if query and query == rml_id:
        return 90

    if query and query == name:
        return 85

    if query and query in name:
        return 60

    if query and query in cas_number:
        return 50

    if query and query in ec_number:
        return 45

    return 0


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def search_echa_api(search_text: str) -> dict:
    session = create_echa_session()

    params = {
        "pageIndex": 1,
        "pageSize": 100,
        "searchText": search_text,
    }

    result = echa_get(
        session=session,
        url=SUBSTANCE_SEARCH_API_URL,
        params=params,
        referer=(
            f"{ECHA_BASE_URL}/substance-search"
            f"?searchText={quote(search_text)}"
        ),
    )

    substances = [
        normalise_substance(item)
        for item in extract_items(
            result["json"]
        )
    ]

    substances.sort(
        key=lambda item: substance_result_score(
            item,
            search_text,
        ),
        reverse=True,
    )

    response = result["response"]

    return {
        "response_status": (
            response.status_code
            if response is not None
            else None
        ),
        "response_url": (
            response.url
            if response is not None
            else ""
        ),
        "response_content_type": (
            response.headers.get(
                "content-type",
                "",
            )
            if response is not None
            else ""
        ),
        "response_text": (
            response.text
            if response is not None
            else ""
        ),
        "json": result["json"],
        "error": result["error"],
        "params": params,
        "results": substances,
        "state": extract_state(
            result["json"]
        ),
    }


# --------------------------------------------------
# CLP OVERVIEW REQUEST
# --------------------------------------------------
@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def get_clp_overview_info(rml_id: str) -> dict:
    """
    Request the ECHA Classification & Labelling overview information.

    This first test intentionally returns both raw and parsed data.
    No regulatory information is invented if a field is missing.
    """
    session = create_echa_session()

    safe_rml_id = quote(
        clean_text(rml_id),
        safe="",
    )

    request_url = (
        f"{CLP_OVERVIEW_INFO_URL}/{safe_rml_id}"
    )

    referer = (
        f"{ECHA_BASE_URL}/{safe_rml_id}/"
        "classification-and-labelling"
    )

    result = echa_get(
        session=session,
        url=request_url,
        referer=referer,
    )

    response = result["response"]

    response_text = (
        response.text
        if response is not None
        else ""
    )

    response_headers = (
        dict(response.headers)
        if response is not None
        else {}
    )

    return {
        "request_method": "GET",
        "request_url": request_url,
        "referer": referer,
        "status": (
            response.status_code
            if response is not None
            else None
        ),
        "final_url": (
            response.url
            if response is not None
            else ""
        ),
        "content_type": (
            response.headers.get(
                "content-type",
                "",
            )
            if response is not None
            else ""
        ),
        "response_headers": response_headers,
        "response_text": response_text,
        "json": result["json"],
        "error": result["error"],
    }


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
DEFAULT_STATE = {
    "clp_search_results": [],
    "clp_selected_index": 0,
    "clp_search_debug": None,
    "clp_result": None,
    "clp_result_rml_id": "",
}

for key, default_value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


# --------------------------------------------------
# SEARCH FORM
# --------------------------------------------------
search_query = st.text_input(
    "CAS number, EC number, substance name, or rmlId",
    value="128-37-0",
    placeholder="For example: 128-37-0",
)

search_button = st.button(
    "Search substance",
    type="primary",
)


# --------------------------------------------------
# SEARCH ACTION
# --------------------------------------------------
if search_button:
    clean_query = search_query.strip()

    if not clean_query:
        st.error(
            "Please enter a CAS number, EC number, "
            "substance name, or rmlId."
        )
        st.stop()

    if (
        looks_like_cas(clean_query)
        and not validate_cas_locally(clean_query)
    ):
        st.error("Invalid CAS number.")
        st.stop()

    with st.spinner("Searching ECHA CHEM..."):
        search_result = search_echa_api(
            clean_query
        )

    st.session_state[
        "clp_search_debug"
    ] = search_result

    st.session_state[
        "clp_search_results"
    ] = search_result["results"]

    st.session_state[
        "clp_selected_index"
    ] = 0

    st.session_state[
        "clp_result"
    ] = None

    st.session_state[
        "clp_result_rml_id"
    ] = ""

    if search_result["error"]:
        st.error(
            "The ECHA substance search "
            "could not be completed."
        )
        st.info(search_result["error"])

    elif search_result["response_status"] != 200:
        st.error(
            "ECHA returned HTTP "
            f"{search_result['response_status']} "
            "for the substance search."
        )

    elif search_result["results"]:
        st.success(
            f"{len(search_result['results'])} "
            "result(s) found."
        )

    else:
        st.warning(
            "ECHA was reached, but no matching "
            "substance was found."
        )


# --------------------------------------------------
# SEARCH DEBUG INFORMATION
# --------------------------------------------------
search_debug = st.session_state[
    "clp_search_debug"
]

if search_debug is not None:
    with st.expander(
        "Substance search diagnostics",
        expanded=False,
    ):
        debug_columns = st.columns(3)

        debug_columns[0].metric(
            "HTTP status",
            (
                search_debug["response_status"]
                if search_debug["response_status"]
                is not None
                else "No response"
            ),
        )

        debug_columns[1].metric(
            "Results",
            len(
                search_debug["results"]
            ),
        )

        debug_columns[2].metric(
            "Content type",
            (
                search_debug[
                    "response_content_type"
                ]
                or "Unknown"
            ),
        )

        st.write(
            "**Requested URL:**",
            search_debug["response_url"],
        )

        st.write(
            "**Parameters:**"
        )
        st.json(
            search_debug["params"],
            expanded=False,
        )

        if search_debug["json"] is not None:
            st.write(
                "**Raw substance search JSON:**"
            )
            st.json(
                search_debug["json"],
                expanded=False,
            )

        elif search_debug["response_text"]:
            st.write(
                "**Raw substance search response:**"
            )
            st.code(
                search_debug[
                    "response_text"
                ][:30000],
                language=None,
            )


# --------------------------------------------------
# DISPLAY AND SELECT SUBSTANCE
# --------------------------------------------------
selected_row = None

search_results = st.session_state[
    "clp_search_results"
]

if search_results:
    st.subheader("1. ECHA search results")

    display_dataframe = pd.DataFrame(
        [
            {
                "Name": result["Name"],
                "EC Number": result["EC Number"],
                "CAS Number": result["CAS Number"],
                "rmlId": result["rmlId"],
            }
            for result in search_results
        ]
    )

    st.dataframe(
        display_dataframe,
        use_container_width=True,
        hide_index=True,
    )

    if len(search_results) == 1:
        selected_index = 0

        st.info(
            "Only one result was found and "
            "has been selected automatically."
        )

    else:
        result_labels = [
            (
                f"{result['Name'] or 'Unnamed substance'}"
                f" | EC {result['EC Number'] or '-'}"
                f" | CAS {result['CAS Number'] or '-'}"
                f" | rmlId {result['rmlId'] or '-'}"
            )
            for result in search_results
        ]

        safe_index = min(
            st.session_state[
                "clp_selected_index"
            ],
            len(result_labels) - 1,
        )

        selected_label = st.selectbox(
            "Select substance",
            options=result_labels,
            index=safe_index,
        )

        selected_index = result_labels.index(
            selected_label
        )

        st.session_state[
            "clp_selected_index"
        ] = selected_index

    selected_row = search_results[
        selected_index
    ]

    st.subheader("2. Selected substance")

    selected_columns = st.columns(4)

    selected_columns[0].metric(
        "Name",
        selected_row["Name"] or "Unknown",
    )

    selected_columns[1].metric(
        "EC Number",
        selected_row["EC Number"] or "Unknown",
    )

    selected_columns[2].metric(
        "CAS Number",
        selected_row["CAS Number"] or "Unknown",
    )

    selected_columns[3].metric(
        "rmlId",
        selected_row["rmlId"] or "Unknown",
    )

    if selected_row["URL"]:
        st.markdown(
            "[Open selected substance in ECHA CHEM]"
            f"({selected_row['URL']})"
        )


# --------------------------------------------------
# CLP REQUEST
# --------------------------------------------------
if selected_row is not None:
    selected_rml_id = clean_text(
        selected_row.get(
            "rmlId",
            "",
        )
    )

    if not selected_rml_id:
        st.warning(
            "The selected substance does not "
            "contain an rmlId."
        )

    else:
        st.subheader(
            "3. Classification & Labelling test"
        )

        st.write(
            "The button below requests the ECHA "
            "Classification & Labelling overview "
            "for the selected rmlId."
        )

        if st.button(
            "Fetch ECHA CLP overview",
            type="primary",
        ):
            with st.spinner(
                "Requesting ECHA Classification "
                "& Labelling information..."
            ):
                clp_result = get_clp_overview_info(
                    selected_rml_id
                )

            st.session_state[
                "clp_result"
            ] = clp_result

            st.session_state[
                "clp_result_rml_id"
            ] = selected_rml_id


# --------------------------------------------------
# DISPLAY CLP RESPONSE
# --------------------------------------------------
clp_result = st.session_state[
    "clp_result"
]

clp_result_rml_id = st.session_state[
    "clp_result_rml_id"
]

if clp_result is not None:
    st.divider()

    st.subheader(
        "4. ECHA CLP response"
    )

    status_columns = st.columns(4)

    status_columns[0].metric(
        "HTTP method",
        clp_result["request_method"],
    )

    status_columns[1].metric(
        "HTTP status",
        (
            clp_result["status"]
            if clp_result["status"] is not None
            else "No response"
        ),
    )

    status_columns[2].metric(
        "JSON received",
        (
            "Yes"
            if clp_result["json"] is not None
            else "No"
        ),
    )

    status_columns[3].metric(
        "rmlId",
        clp_result_rml_id or "Unknown",
    )

    st.write(
        "**Requested endpoint:**",
        clp_result["request_url"],
    )

    st.write(
        "**Final response URL:**",
        clp_result["final_url"] or "-",
    )

    st.write(
        "**Content type:**",
        clp_result["content_type"] or "-",
    )

    if clp_result["error"]:
        st.error(
            "The ECHA CLP request could "
            "not be completed."
        )

        st.info(clp_result["error"])

    elif clp_result["status"] == 200:
        if clp_result["json"] is not None:
            st.success(
                "ECHA returned a successful JSON response."
            )

        else:
            st.warning(
                "ECHA returned HTTP 200, but the response "
                "could not be parsed as JSON."
            )

    elif clp_result["status"] == 403:
        st.error(
            "ECHA returned HTTP 403. Access to this "
            "endpoint was refused."
        )

    elif clp_result["status"] == 404:
        st.error(
            "ECHA returned HTTP 404. The tested endpoint "
            "or selected rmlId was not found."
        )

    elif clp_result["status"] == 429:
        st.error(
            "ECHA returned HTTP 429. Too many requests "
            "were made. Wait before testing again."
        )

    else:
        st.error(
            "ECHA returned HTTP "
            f"{clp_result['status']}."
        )

    response_json = clp_result["json"]

    if response_json is not None:
        flattened_rows = flatten_json(
            response_json
        )

        flattened_dataframe = pd.DataFrame(
            flattened_rows
        )

        st.subheader(
            "Possible useful CLP information"
        )

        if not flattened_dataframe.empty:
            clp_mask = (
                flattened_dataframe["Path"]
                .astype(str)
                .apply(is_possible_clp_field)
            )

            possible_clp_dataframe = (
                flattened_dataframe[
                    clp_mask
                ]
                .copy()
                .reset_index(
                    drop=True
                )
            )

            if not possible_clp_dataframe.empty:
                st.dataframe(
                    possible_clp_dataframe,
                    use_container_width=True,
                    hide_index=True,
                )

            else:
                st.info(
                    "No obvious CLP fields were found by "
                    "the preliminary field-name filter. "
                    "The full JSON is still shown below."
                )

            st.subheader(
                "Possible identifiers returned by ECHA"
            )

            identifier_mask = (
                flattened_dataframe["Path"]
                .astype(str)
                .apply(
                    is_possible_identifier_field
                )
            )

            identifier_dataframe = (
                flattened_dataframe[
                    identifier_mask
                ]
                .copy()
                .reset_index(
                    drop=True
                )
            )

            if not identifier_dataframe.empty:
                st.dataframe(
                    identifier_dataframe,
                    use_container_width=True,
                    hide_index=True,
                )

            else:
                st.info(
                    "No obvious ID fields were found "
                    "in this response."
                )

            with st.expander(
                "All flattened JSON fields",
                expanded=False,
            ):
                field_filter = st.text_input(
                    "Filter JSON paths",
                    key="clp_json_path_filter",
                    placeholder=(
                        "For example: classification, "
                        "hazard, pictogram or id"
                    ),
                )

                displayed_dataframe = (
                    flattened_dataframe.copy()
                )

                if field_filter.strip():
                    displayed_dataframe = (
                        displayed_dataframe[
                            displayed_dataframe[
                                "Path"
                            ]
                            .astype(str)
                            .str.contains(
                                field_filter.strip(),
                                case=False,
                                regex=False,
                                na=False,
                            )
                        ]
                    )

                st.dataframe(
                    displayed_dataframe,
                    use_container_width=True,
                    hide_index=True,
                )

        with st.expander(
            "Complete raw CLP JSON response",
            expanded=True,
        ):
            st.json(
                response_json,
                expanded=True,
            )

        raw_json_download = json.dumps(
            response_json,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")

        st.download_button(
            label="Download raw CLP response as JSON",
            data=raw_json_download,
            file_name=(
                "ECHA_CLP_overview_"
                f"{clp_result_rml_id}.json"
            ),
            mime="application/json",
        )

    elif clp_result["response_text"]:
        with st.expander(
            "Raw non-JSON response",
            expanded=True,
        ):
            st.code(
                clp_result[
                    "response_text"
                ][:50000],
                language=None,
            )

    else:
        st.warning(
            "ECHA returned no readable response body."
        )

    with st.expander(
        "Response headers",
        expanded=False,
    ):
        safe_response_headers = {
            str(key): str(value)
            for key, value in clp_result[
                "response_headers"
            ].items()
            if str(key).lower() not in {
                "set-cookie",
                "cookie",
                "authorization",
                "proxy-authorization",
            }
        }

        st.json(
            safe_response_headers,
            expanded=False,
        )


# --------------------------------------------------
# CACHE CONTROL
# --------------------------------------------------
st.divider()

if st.button(
    "Clear CLP test cache",
):
    st.cache_data.clear()

    for key, default_value in DEFAULT_STATE.items():
        st.session_state[key] = default_value

    st.success(
        "The CLP test cache and selections "
        "have been cleared."
    )

    st.rerun()