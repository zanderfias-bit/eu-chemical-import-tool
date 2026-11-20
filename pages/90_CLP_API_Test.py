import json
import re
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --------------------------------------------------
# PAGE SETTINGS
# --------------------------------------------------
st.set_page_config(
    page_title="ECHA CLP API Discovery",
    page_icon="🔬",
    layout="wide",
)

st.title("🔬 ECHA CLP API Discovery")

st.write(
    "This page investigates where ECHA CHEM retrieves its "
    "Classification and Labelling information. It does not change "
    "or import the main app.py file."
)

st.info(
    "The page first uses the known substance search API. "
    "After selecting a substance, it inspects the official ECHA "
    "substance page and its JavaScript files for real API references "
    "and CLP-related fields."
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
ECHA_BASE_URL = "https://chem.echa.europa.eu"

SUBSTANCE_SEARCH_API_URL = (
    f"{ECHA_BASE_URL}/api-substance/v1/substance"
)

CONNECT_TIMEOUT_SECONDS = 20
READ_TIMEOUT_SECONDS = 90

MAX_SCRIPT_FILES = 40
MAX_SCRIPT_SIZE_BYTES = 12_000_000
MAX_DISPLAY_CONTEXTS = 500

ECHA_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

CLP_SEARCH_TERMS = [
    "classification",
    "labelling",
    "labeling",
    "clp",
    "annex vi",
    "annexvi",
    "harmonised",
    "harmonized",
    "hazard",
    "hazardstatement",
    "hazard statement",
    "signalword",
    "signal word",
    "pictogram",
    "ghs",
    "specificconcentrationlimit",
    "specific concentration limit",
    "m-factor",
    "m_factor",
    "self-classification",
    "self classification",
    "notification",
    "inventory",
]


# --------------------------------------------------
# GENERIC HELPERS
# --------------------------------------------------
def clean_text(value):
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


def clean_identifier(value):
    if value is None:
        return ""

    if isinstance(value, (list, tuple, set)):
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


def create_echa_session():
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
                "HEAD",
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


def safe_get(
    session,
    url,
    params=None,
    referer=None,
):
    request_headers = {}

    if referer:
        request_headers["Referer"] = referer

    try:
        response = session.get(
            url,
            params=params,
            headers=(
                request_headers
                if request_headers
                else None
            ),
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
            "text": "",
            "error": (
                "Request timed out: "
                f"{error}"
            ),
        }

    except requests.RequestException as error:
        return {
            "response": None,
            "json": None,
            "text": "",
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
        "text": response.text,
        "error": None,
    }


def extract_items(response_json):
    if not isinstance(response_json, dict):
        return []

    items = response_json.get(
        "items",
        [],
    )

    if not isinstance(items, list):
        return []

    return items


def find_first_field(
    value,
    possible_keys,
):
    wanted_keys = {
        str(key).lower()
        for key in possible_keys
    }

    if isinstance(value, dict):
        for key, nested_value in value.items():
            if str(key).lower() in wanted_keys:
                if not isinstance(
                    nested_value,
                    (dict, list),
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


def normalise_substance(item):
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
    result,
    search_text,
):
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


# --------------------------------------------------
# SUBSTANCE SEARCH
# --------------------------------------------------
@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def search_substances(search_text):
    session = create_echa_session()

    params = {
        "pageIndex": 1,
        "pageSize": 100,
        "searchText": search_text,
    }

    result = safe_get(
        session=session,
        url=SUBSTANCE_SEARCH_API_URL,
        params=params,
        referer=(
            f"{ECHA_BASE_URL}/substance-search"
            f"?searchText={search_text}"
        ),
    )

    response = result["response"]

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

    return {
        "status": (
            response.status_code
            if response is not None
            else None
        ),
        "url": (
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
        "error": result["error"],
        "json": result["json"],
        "text": result["text"],
        "params": params,
        "results": substances,
    }


# --------------------------------------------------
# HTML AND JAVASCRIPT DISCOVERY
# --------------------------------------------------
def extract_script_urls(
    html_text,
    page_url,
):
    script_patterns = [
        r'<script[^"\']+["\']',
        r'<link[^"\']+\.js(?:\?[^"\']*?)["\']',
    ]

    script_urls = []

    for pattern in script_patterns:
        matches = re.findall(
            pattern,
            html_text,
            flags=re.IGNORECASE,
        )

        for match in matches:
            absolute_url = urljoin(
                page_url,
                match,
            )

            if absolute_url not in script_urls:
                script_urls.append(
                    absolute_url
                )

    return script_urls


def extract_api_candidates(text):
    if not text:
        return []

    patterns = [
        r'[^"\']*/api-[A-Za-z0-9_./?=&{}:-]+["\']',
        r'[^"\']*/api/[A-Za-z0-9_./?=&{}:-]+["\']',
        r'[^"\']*classification[A-Za-z0-9_./?=&{}:-]*["\']',
        r'[^"\']*labelling[A-Za-z0-9_./?=&{}:-]*["\']',
        r'[^"\']*labeling[A-Za-z0-9_./?=&{}:-]*["\']',
        r'[^"\']*annex[A-Za-z0-9_./?=&{}:-]*["\']',
        r'[^"\']*hazard[A-Za-z0-9_./?=&{}:-]*["\']',
    ]

    candidates = []

    for pattern in patterns:
        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        for match in matches:
            cleaned_match = clean_text(match)

            if (
                cleaned_match
                and len(cleaned_match) <= 500
                and cleaned_match not in candidates
            ):
                candidates.append(
                    cleaned_match
                )

    return candidates


def extract_keyword_contexts(
    text,
    source_url,
    context_size=220,
):
    if not text:
        return []

    lower_text = text.lower()
    contexts = []
    seen_contexts = set()

    for search_term in CLP_SEARCH_TERMS:
        start_position = 0
        lower_term = search_term.lower()

        while True:
            position = lower_text.find(
                lower_term,
                start_position,
            )

            if position == -1:
                break

            context_start = max(
                0,
                position - context_size,
            )

            context_end = min(
                len(text),
                position + len(search_term) + context_size,
            )

            context = text[
                context_start:context_end
            ]

            context = re.sub(
                r"\s+",
                " ",
                context,
            ).strip()

            context_key = (
                search_term.lower(),
                context,
            )

            if context_key not in seen_contexts:
                contexts.append(
                    {
                        "Search term": search_term,
                        "Source": source_url,
                        "Context": context,
                    }
                )

                seen_contexts.add(
                    context_key
                )

            if len(contexts) >= MAX_DISPLAY_CONTEXTS:
                return contexts

            start_position = (
                position + len(search_term)
            )

    return contexts


@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def investigate_echa_page(rml_id):
    session = create_echa_session()

    overview_url = (
        f"{ECHA_BASE_URL}/{rml_id}/overview"
    )

    overview_result = safe_get(
        session=session,
        url=overview_url,
        referer=ECHA_BASE_URL,
    )

    overview_response = overview_result[
        "response"
    ]

    report = {
        "rmlId": rml_id,
        "overview": {
            "requested_url": overview_url,
            "status": (
                overview_response.status_code
                if overview_response is not None
                else None
            ),
            "final_url": (
                overview_response.url
                if overview_response is not None
                else ""
            ),
            "content_type": (
                overview_response.headers.get(
                    "content-type",
                    "",
                )
                if overview_response is not None
                else ""
            ),
            "error": overview_result["error"],
        },
        "script_files": [],
        "api_candidates": [],
        "keyword_contexts": [],
    }

    if (
        overview_result["error"]
        or overview_response is None
        or overview_response.status_code != 200
    ):
        return report

    html_text = overview_result["text"]

    report["api_candidates"].extend(
        extract_api_candidates(
            html_text
        )
    )

    report["keyword_contexts"].extend(
        extract_keyword_contexts(
            text=html_text,
            source_url=overview_url,
        )
    )

    script_urls = extract_script_urls(
        html_text=html_text,
        page_url=overview_url,
    )

    script_urls = script_urls[
        :MAX_SCRIPT_FILES
    ]

    for script_url in script_urls:
        script_result = safe_get(
            session=session,
            url=script_url,
            referer=overview_url,
        )

        script_response = script_result[
            "response"
        ]

        script_record = {
            "url": script_url,
            "status": (
                script_response.status_code
                if script_response is not None
                else None
            ),
            "content_type": (
                script_response.headers.get(
                    "content-type",
                    "",
                )
                if script_response is not None
                else ""
            ),
            "bytes": (
                len(
                    script_response.content
                )
                if script_response is not None
                else 0
            ),
            "error": script_result["error"],
            "scanned": False,
        }

        if (
            script_result["error"]
            or script_response is None
            or script_response.status_code != 200
        ):
            report["script_files"].append(
                script_record
            )
            continue

        script_size = len(
            script_response.content
        )

        if script_size > MAX_SCRIPT_SIZE_BYTES:
            script_record["error"] = (
                "Script skipped because it exceeds "
                f"{MAX_SCRIPT_SIZE_BYTES:,} bytes."
            )

            report["script_files"].append(
                script_record
            )
            continue

        script_text = script_result["text"]
        script_record["scanned"] = True

        api_candidates = extract_api_candidates(
            script_text
        )

        for candidate in api_candidates:
            if candidate not in report[
                "api_candidates"
            ]:
                report[
                    "api_candidates"
                ].append(candidate)

        remaining_context_capacity = (
            MAX_DISPLAY_CONTEXTS
            - len(
                report[
                    "keyword_contexts"
                ]
            )
        )

        if remaining_context_capacity > 0:
            contexts = extract_keyword_contexts(
                text=script_text,
                source_url=script_url,
            )

            report["keyword_contexts"].extend(
                contexts[
                    :remaining_context_capacity
                ]
            )

        report["script_files"].append(
            script_record
        )

    return report


# --------------------------------------------------
# MANUAL ENDPOINT TESTER
# --------------------------------------------------
def build_test_url(endpoint_text):
    endpoint_text = endpoint_text.strip()

    if not endpoint_text:
        return ""

    if endpoint_text.startswith(
        (
            "https://",
            "http://",
        )
    ):
        return endpoint_text

    return urljoin(
        f"{ECHA_BASE_URL}/",
        endpoint_text.lstrip("/"),
    )


def replace_endpoint_placeholders(
    endpoint_url,
    rml_id,
):
    placeholder_values = {
        "{rmlId}": rml_id,
        "{rmlid}": rml_id,
        ":rmlId": rml_id,
        ":rmlid": rml_id,
    }

    updated_url = endpoint_url

    for placeholder, replacement in (
        placeholder_values.items()
    ):
        updated_url = updated_url.replace(
            placeholder,
            replacement,
        )

    return updated_url


def parse_query_parameters(
    parameter_text,
):
    if not parameter_text.strip():
        return {}, None

    try:
        parameters = json.loads(
            parameter_text
        )

    except json.JSONDecodeError as error:
        return (
            None,
            (
                "The query parameters are not "
                f"valid JSON: {error}"
            ),
        )

    if not isinstance(parameters, dict):
        return (
            None,
            "Query parameters must be a JSON object.",
        )

    return parameters, None


def test_endpoint(
    endpoint_url,
    parameters,
    referer,
):
    session = create_echa_session()

    result = safe_get(
        session=session,
        url=endpoint_url,
        params=parameters,
        referer=referer,
    )

    response = result["response"]

    return {
        "requested_endpoint": endpoint_url,
        "parameters": parameters,
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
        "error": result["error"],
        "json": result["json"],
        "text": result["text"],
    }


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
DEFAULT_STATE = {
    "clp_search_result": None,
    "clp_selected_substance": None,
    "clp_discovery_report": None,
    "clp_endpoint_result": None,
}

for key, default_value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


# --------------------------------------------------
# STEP 1: SUBSTANCE SEARCH
# --------------------------------------------------
st.header("1. Select a test substance")

search_text = st.text_input(
    "CAS number, EC number, substance name, or rmlId",
    value="123-31-9",
    placeholder="For example: 123-31-9",
)

if st.button(
    "Search test substance",
    type="primary",
):
    clean_search_text = search_text.strip()

    if not clean_search_text:
        st.error(
            "Enter a CAS number, EC number, "
            "substance name, or rmlId."
        )

    else:
        with st.spinner(
            "Searching ECHA CHEM..."
        ):
            search_result = search_substances(
                clean_search_text
            )

        st.session_state[
            "clp_search_result"
        ] = search_result

        st.session_state[
            "clp_selected_substance"
        ] = None

        st.session_state[
            "clp_discovery_report"
        ] = None

        st.session_state[
            "clp_endpoint_result"
        ] = None


search_result = st.session_state[
    "clp_search_result"
]

selected_substance = None

if search_result is not None:
    search_metrics = st.columns(3)

    search_metrics[0].metric(
        "HTTP",
        (
            search_result["status"]
            if search_result["status"] is not None
            else "Error"
        ),
    )

    search_metrics[1].metric(
        "Valid JSON",
        (
            "Yes"
            if search_result["json"] is not None
            else "No"
        ),
    )

    search_metrics[2].metric(
        "Results",
        len(
            search_result["results"]
        ),
    )

    with st.expander(
        "Substance search request details",
        expanded=False,
    ):
        st.write("**Endpoint**")
        st.code(
            SUBSTANCE_SEARCH_API_URL,
            language=None,
        )

        st.write("**Parameters**")
        st.json(
            search_result["params"]
        )

        st.write("**Final URL**")
        st.code(
            search_result["url"]
            or "No response URL",
            language=None,
        )

        st.write("**Content-Type**")
        st.code(
            search_result["content_type"]
            or "Unknown",
            language=None,
        )

        if search_result["error"]:
            st.error(
                search_result["error"]
            )

    if (
        search_result["status"] == 200
        and search_result["results"]
    ):
        results = search_result["results"]

        results_dataframe = pd.DataFrame(
            [
                {
                    "Name": result["Name"],
                    "EC Number": result["EC Number"],
                    "CAS Number": result["CAS Number"],
                    "rmlId": result["rmlId"],
                }
                for result in results
            ]
        )

        st.dataframe(
            results_dataframe,
            hide_index=True,
            use_container_width=True,
        )

        result_labels = [
            (
                f"{result['Name'] or 'Unnamed substance'}"
                f" | EC {result['EC Number'] or '-'}"
                f" | CAS {result['CAS Number'] or '-'}"
                f" | rmlId {result['rmlId'] or '-'}"
            )
            for result in results
        ]

        selected_label = st.selectbox(
            "Select the substance to investigate",
            options=result_labels,
        )

        selected_index = result_labels.index(
            selected_label
        )

        selected_substance = results[
            selected_index
        ]

        st.session_state[
            "clp_selected_substance"
        ] = selected_substance

        selected_columns = st.columns(4)

        selected_columns[0].metric(
            "Name",
            selected_substance["Name"]
            or "Unknown",
        )

        selected_columns[1].metric(
            "EC Number",
            selected_substance["EC Number"]
            or "Unknown",
        )

        selected_columns[2].metric(
            "CAS Number",
            selected_substance["CAS Number"]
            or "Unknown",
        )

        selected_columns[3].metric(
            "rmlId",
            selected_substance["rmlId"]
            or "Unknown",
        )

    elif search_result["error"]:
        st.error(
            "The ECHA substance search failed."
        )

        st.info(
            search_result["error"]
        )

    elif search_result["status"] != 200:
        st.error(
            "ECHA returned HTTP "
            f"{search_result['status']}."
        )

        with st.expander(
            "Raw substance search response",
            expanded=False,
        ):
            st.code(
                search_result["text"][:30000],
                language=None,
            )

    else:
        st.warning(
            "No matching substances were returned."
        )


# --------------------------------------------------
# STEP 2: DISCOVERY SCAN
# --------------------------------------------------
selected_substance = st.session_state[
    "clp_selected_substance"
]

if selected_substance is not None:
    st.divider()
    st.header("2. Discover CLP-related API references")

    selected_rml_id = selected_substance.get(
        "rmlId",
        "",
    )

    if not selected_rml_id:
        st.warning(
            "The selected substance does not "
            "contain an rmlId."
        )

    else:
        st.write(
            "The scanner will inspect the official "
            "substance overview page and the JavaScript "
            "files loaded by that page."
        )

        st.warning(
            "This can take one or two minutes because "
            "several JavaScript files may need to be checked."
        )

        if st.button(
            "Scan ECHA page for CLP API references",
            type="primary",
        ):
            with st.spinner(
                "Inspecting ECHA CHEM JavaScript files..."
            ):
                discovery_report = (
                    investigate_echa_page(
                        selected_rml_id
                    )
                )

            st.session_state[
                "clp_discovery_report"
            ] = discovery_report

            st.session_state[
                "clp_endpoint_result"
            ] = None


discovery_report = st.session_state[
    "clp_discovery_report"
]

if discovery_report is not None:
    overview = discovery_report["overview"]
    script_files = discovery_report[
        "script_files"
    ]
    api_candidates = discovery_report[
        "api_candidates"
    ]
    keyword_contexts = discovery_report[
        "keyword_contexts"
    ]

    scanned_script_count = sum(
        1
        for script in script_files
        if script.get("scanned")
    )

    discovery_metrics = st.columns(4)

    discovery_metrics[0].metric(
        "Overview HTTP",
        (
            overview["status"]
            if overview["status"] is not None
            else "Error"
        ),
    )

    discovery_metrics[1].metric(
        "Scripts found",
        len(script_files),
    )

    discovery_metrics[2].metric(
        "Scripts scanned",
        scanned_script_count,
    )

    discovery_metrics[3].metric(
        "Candidate references",
        len(api_candidates),
    )

    st.write("**Overview URL**")
    st.code(
        overview["final_url"]
        or overview["requested_url"],
        language=None,
    )

    if overview["error"]:
        st.error(
            overview["error"]
        )

    with st.expander(
        "JavaScript files inspected",
        expanded=False,
    ):
        if script_files:
            script_dataframe = pd.DataFrame(
                script_files
            )

            st.dataframe(
                script_dataframe,
                hide_index=True,
                use_container_width=True,
            )

        else:
            st.warning(
                "No JavaScript files were found "
                "in the retrieved HTML."
            )

    st.subheader(
        "Possible API routes or CLP references"
    )

    if api_candidates:
        candidate_dataframe = pd.DataFrame(
            {
                "Candidate": api_candidates
            }
        )

        st.dataframe(
            candidate_dataframe,
            hide_index=True,
            use_container_width=True,
        )

    else:
        st.warning(
            "No obvious API route was found. "
            "Review the keyword contexts below."
        )

    st.subheader(
        "CLP keyword contexts"
    )

    if keyword_contexts:
        context_dataframe = pd.DataFrame(
            keyword_contexts
        )

        selected_terms = st.multiselect(
            "Filter by keyword",
            options=sorted(
                context_dataframe[
                    "Search term"
                ]
                .dropna()
                .unique()
                .tolist()
            ),
            default=[],
        )

        filtered_contexts = (
            context_dataframe.copy()
        )

        if selected_terms:
            filtered_contexts = (
                filtered_contexts[
                    filtered_contexts[
                        "Search term"
                    ].isin(
                        selected_terms
                    )
                ]
            )

        st.dataframe(
            filtered_contexts,
            hide_index=True,
            use_container_width=True,
            height=600,
        )

    else:
        st.warning(
            "No CLP keywords were found in the "
            "retrieved page resources."
        )

    report_json = json.dumps(
        discovery_report,
        ensure_ascii=False,
        indent=2,
    )

    st.download_button(
        label="Download complete discovery report",
        data=report_json.encode("utf-8"),
        file_name=(
            "echa_clp_discovery_"
            f"{discovery_report['rmlId']}.json"
        ),
        mime="application/json",
    )


# --------------------------------------------------
# STEP 3: MANUAL ENDPOINT TEST
# --------------------------------------------------
if discovery_report is not None:
    st.divider()
    st.header("3. Test a discovered endpoint")

    st.write(
        "Only paste a route that appears in the discovery "
        "results or that you observe in the browser's Network tab. "
        "The tester performs a normal GET request and does not "
        "attempt to bypass access controls."
    )

    selected_rml_id = discovery_report[
        "rmlId"
    ]

    candidate_options = [
        ""
    ]

    candidate_options.extend(
        discovery_report[
            "api_candidates"
        ]
    )

    selected_candidate = st.selectbox(
        "Select a discovered candidate",
        options=candidate_options,
        format_func=lambda value: (
            "Select a candidate or enter one manually"
            if not value
            else value
        ),
    )

    manual_endpoint = st.text_input(
        "Endpoint or route",
        value=selected_candidate,
        placeholder=(
            "/api-example/v1/example"
        ),
    )

    query_parameter_text = st.text_area(
        "Query parameters as JSON",
        value=json.dumps(
            {
                "rmlId": selected_rml_id
            },
            indent=2,
        ),
        height=140,
    )

    if st.button(
        "Test selected endpoint"
    ):
        endpoint_url = build_test_url(
            manual_endpoint
        )

        endpoint_url = replace_endpoint_placeholders(
            endpoint_url=endpoint_url,
            rml_id=selected_rml_id,
        )

        parameters, parameter_error = (
            parse_query_parameters(
                query_parameter_text
            )
        )

        if not endpoint_url:
            st.error(
                "Enter an endpoint or route."
            )

        elif parameter_error:
            st.error(
                parameter_error
            )

        elif not endpoint_url.startswith(
            (
                f"{ECHA_BASE_URL}/",
                ECHA_BASE_URL,
            )
        ):
            st.error(
                "For this investigation, only endpoints "
                "on chem.echa.europa.eu are allowed."
            )

        else:
            with st.spinner(
                "Testing endpoint..."
            ):
                endpoint_result = test_endpoint(
                    endpoint_url=endpoint_url,
                    parameters=parameters,
                    referer=(
                        f"{ECHA_BASE_URL}/"
                        f"{selected_rml_id}/overview"
                    ),
                )

            st.session_state[
                "clp_endpoint_result"
            ] = endpoint_result


endpoint_result = st.session_state[
    "clp_endpoint_result"
]

if endpoint_result is not None:
    endpoint_metrics = st.columns(3)

    endpoint_metrics[0].metric(
        "HTTP",
        (
            endpoint_result["status"]
            if endpoint_result["status"] is not None
            else "Error"
        ),
    )

    endpoint_metrics[1].metric(
        "Valid JSON",
        (
            "Yes"
            if endpoint_result["json"] is not None
            else "No"
        ),
    )

    endpoint_metrics[2].metric(
        "Response length",
        len(
            endpoint_result["text"]
        ),
    )

    st.write("**Final request URL**")
    st.code(
        endpoint_result["final_url"]
        or endpoint_result[
            "requested_endpoint"
        ],
        language=None,
    )

    st.write("**Parameters**")
    st.json(
        endpoint_result["parameters"]
    )

    st.write("**Content-Type**")
    st.code(
        endpoint_result["content_type"]
        or "Unknown",
        language=None,
    )

    if endpoint_result["error"]:
        st.error(
            endpoint_result["error"]
        )

    elif endpoint_result["json"] is not None:
        st.subheader("Parsed JSON response")

        st.json(
            endpoint_result["json"],
            expanded=False,
        )

        if isinstance(
            endpoint_result["json"],
            dict,
        ):
            st.write("**Top-level JSON keys**")

            st.code(
                "\n".join(
                    str(key)
                    for key in endpoint_result[
                        "json"
                    ].keys()
                )
                or "No top-level keys",
                language=None,
            )

        endpoint_json_download = json.dumps(
            endpoint_result["json"],
            ensure_ascii=False,
            indent=2,
        )

        st.download_button(
            label="Download endpoint JSON response",
            data=endpoint_json_download.encode(
                "utf-8"
            ),
            file_name="echa_clp_endpoint_response.json",
            mime="application/json",
        )

    else:
        st.subheader("Raw response")

        st.code(
            endpoint_result["text"][:50000],
            language=None,
        )


# --------------------------------------------------
# CACHE CONTROL
# --------------------------------------------------
st.divider()

if st.button(
    "Clear CLP discovery cache"
):
    st.cache_data.clear()

    for key, default_value in (
        DEFAULT_STATE.items()
    ):
        st.session_state[key] = default_value

    st.success(
        "CLP discovery cache cleared."
    )

    st.rerun()