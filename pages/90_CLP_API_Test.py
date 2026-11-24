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
    "Search ECHA CHEM by CAS number, EC number, substance name, "
    "or rmlId. The test retrieves the CLP overview, classification "
    "details, hazard statements and ECHA pictograms."
)

st.info(
    "Recommended first test: BHT, CAS 128-37-0. "
    "Expected ECHA rmlId: 100.004.439."
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

CLP_OVERVIEW_CLASSIFICATIONS_URL = (
    f"{ECHA_BASE_URL}"
    "/api-cnl-inventory/prominent/overview/classifications"
)

CLP_INDUSTRY_PICTOGRAMS_URL = (
    f"{ECHA_BASE_URL}"
    "/api-cnl-inventory/industry/pictograms"
)

CLP_HARMONISED_PICTOGRAMS_URL = (
    f"{ECHA_BASE_URL}"
    "/api-cnl-inventory/harmonized/pictograms"
)

CLP_PICTOGRAM_IMAGE_URL = (
    f"{ECHA_BASE_URL}"
    "/api-cnl-inventory/pictograms/get"
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

    if isinstance(
        value,
        (
            dict,
            list,
            tuple,
        ),
    ):
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
            cleaned_item = clean_identifier(
                item
            )

            if (
                cleaned_item
                and cleaned_item not in cleaned_values
            ):
                cleaned_values.append(
                    cleaned_item
                )

        return ", ".join(
            cleaned_values
        )

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


def validate_cas_locally(
    cas_number: str,
) -> bool:
    if not looks_like_cas(
        cas_number
    ):
        return False

    digits, check_digit = (
        cas_number.rsplit(
            "-",
            1,
        )
    )

    digits = digits.replace(
        "-",
        "",
    )

    total = sum(
        int(digit) * position
        for position, digit in enumerate(
            reversed(digits),
            start=1,
        )
    )

    return (
        total % 10
        == int(check_digit)
    )


def create_echa_session() -> requests.Session:
    session = requests.Session()

    session.headers.update(
        ECHA_HEADERS
    )

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
    request_headers = None

    if referer:
        request_headers = {
            "Referer": referer,
        }

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


def build_response_result(
    request_url: str,
    referer: str,
    result: dict,
) -> dict:
    response = result["response"]

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
        "response_text": (
            response.text
            if response is not None
            else ""
        ),
        "json": result["json"],
        "error": result["error"],
    }


def extract_items(
    response_json: Any,
) -> list:
    if not isinstance(
        response_json,
        dict,
    ):
        return []

    items = response_json.get(
        "items",
        [],
    )

    if not isinstance(
        items,
        list,
    ):
        return []

    return items


def extract_state(
    response_json: Any,
) -> dict:
    if not isinstance(
        response_json,
        dict,
    ):
        return {}

    state = response_json.get(
        "state",
        {},
    )

    if not isinstance(
        state,
        dict,
    ):
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
            if (
                str(key).lower()
                in wanted_keys
            ):
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


# --------------------------------------------------
# ECHA SUBSTANCE SEARCH
# --------------------------------------------------
def normalise_substance(
    item: Any,
) -> dict:
    if not isinstance(
        item,
        dict,
    ):
        return {
            "Name": "",
            "EC Number": "",
            "CAS Number": "",
            "rmlId": "",
            "URL": "",
        }

    substance_index = item.get(
        "substanceIndex",
        {},
    )

    if not isinstance(
        substance_index,
        dict,
    ):
        substance_index = {}

    rml_id = (
        substance_index.get(
            "rmlId"
        )
        or find_first_field(
            item,
            {
                "rmlId",
            },
        )
    )

    substance_name = (
        substance_index.get(
            "rmlName"
        )
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
        substance_index.get(
            "rmlCas"
        )
        or substance_index.get(
            "casNumber"
        )
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
        substance_index.get(
            "ecNumber"
        )
        or substance_index.get(
            "rmlEc"
        )
        or substance_index.get(
            "rmlEcNumber"
        )
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

    clean_rml_id = clean_text(
        rml_id
    )

    return {
        "Name": clean_text(
            substance_name
        ),
        "EC Number": clean_identifier(
            ec_number
        ),
        "CAS Number": clean_identifier(
            cas_number
        ),
        "rmlId": clean_rml_id,
        "URL": (
            f"{ECHA_BASE_URL}/"
            f"{clean_rml_id}/overview"
            if clean_rml_id
            else ""
        ),
    }


def substance_result_score(
    result: dict,
    search_text: str,
) -> int:
    query = clean_text(
        search_text
    ).lower()

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
def search_echa_api(
    search_text: str,
) -> dict:
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
            f"{ECHA_BASE_URL}/"
            "substance-search"
            f"?searchText={quote(search_text)}"
        ),
    )

    substances = [
        normalise_substance(
            item
        )
        for item in extract_items(
            result["json"]
        )
    ]

    substances.sort(
        key=lambda item: (
            substance_result_score(
                item,
                search_text,
            )
        ),
        reverse=True,
    )

    response = result["response"]

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
        "json": result["json"],
        "error": result["error"],
        "results": substances,
        "state": extract_state(
            result["json"]
        ),
    }


# --------------------------------------------------
# CLP API REQUESTS
# --------------------------------------------------
@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def get_clp_overview(
    rml_id: str,
) -> dict:
    session = create_echa_session()

    safe_rml_id = quote(
        clean_text(rml_id),
        safe="",
    )

    request_url = (
        f"{CLP_OVERVIEW_INFO_URL}/"
        f"{safe_rml_id}"
    )

    referer = (
        f"{ECHA_BASE_URL}/"
        f"{safe_rml_id}/overview"
    )

    result = echa_get(
        session=session,
        url=request_url,
        referer=referer,
    )

    return build_response_result(
        request_url=request_url,
        referer=referer,
        result=result,
    )


@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def get_classification_details(
    classification_id: str,
    classification_type: str,
    rml_id: str,
) -> dict:
    session = create_echa_session()

    classification_type = clean_text(
        classification_type
    ).lower()

    if classification_type in {
        "harmonised",
        "harmonized",
    }:
        endpoint_type = "harmonised"
    else:
        endpoint_type = "industry"

    safe_classification_id = quote(
        clean_text(
            classification_id
        ),
        safe="",
    )

    request_url = (
        f"{CLP_OVERVIEW_CLASSIFICATIONS_URL}/"
        f"{endpoint_type}/"
        f"{safe_classification_id}"
    )

    referer = (
        f"{ECHA_BASE_URL}/"
        f"{quote(clean_text(rml_id), safe='')}/overview"
    )

    result = echa_get(
        session=session,
        url=request_url,
        referer=referer,
    )

    return build_response_result(
        request_url=request_url,
        referer=referer,
        result=result,
    )


@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def get_pictograms(
    classification_id: str,
    classification_type: str,
    rml_id: str,
) -> dict:
    session = create_echa_session()

    classification_type = clean_text(
        classification_type
    ).lower()

    safe_classification_id = quote(
        clean_text(
            classification_id
        ),
        safe="",
    )

    if classification_type == "industry":
        request_url = (
            f"{CLP_INDUSTRY_PICTOGRAMS_URL}/"
            f"{safe_classification_id}"
        )

    elif classification_type in {
        "harmonised",
        "harmonized",
    }:
        request_url = (
            f"{CLP_HARMONISED_PICTOGRAMS_URL}/"
            f"{safe_classification_id}"
        )

    else:
        return {
            "request_method": "GET",
            "request_url": "",
            "referer": "",
            "status": None,
            "final_url": "",
            "content_type": "",
            "response_text": "",
            "json": None,
            "error": (
                "Unsupported classification type: "
                f"{classification_type}"
            ),
        }

    referer = (
        f"{ECHA_BASE_URL}/"
        f"{quote(clean_text(rml_id), safe='')}/overview"
    )

    result = echa_get(
        session=session,
        url=request_url,
        referer=referer,
    )

    return build_response_result(
        request_url=request_url,
        referer=referer,
        result=result,
    )


# --------------------------------------------------
# CLP PARSERS
# --------------------------------------------------
def parse_overview(
    response_json: Any,
) -> list:
    parsed_items = []

    for item in extract_items(
        response_json
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        signal_word = item.get(
            "signalWord",
            {},
        )

        if not isinstance(
            signal_word,
            dict,
        ):
            signal_word = {}

        parsed_items.append(
            {
                "classification_id": clean_text(
                    item.get(
                        "classificationId"
                    )
                ),
                "rml_id": clean_text(
                    item.get(
                        "rmlId"
                    )
                ),
                "type": clean_text(
                    item.get(
                        "type"
                    )
                ),
                "industry_count": item.get(
                    "totalIndustryClassifications"
                ),
                "harmonised_count": item.get(
                    "totalHarmonisedClassifications"
                ),
                "signal_word_code": clean_text(
                    signal_word.get(
                        "signalWordCode"
                    )
                ),
                "signal_word": clean_text(
                    signal_word.get(
                        "signalWordText"
                    )
                ),
                "display_order": item.get(
                    "displayOrder"
                ),
            }
        )

    return parsed_items


def parse_classification(
    response_json: Any,
) -> list:
    classifications = []

    for item in extract_items(
        response_json
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        hazard_statements = item.get(
            "hazardStatements",
            [],
        )

        if not isinstance(
            hazard_statements,
            list,
        ):
            hazard_statements = []

        hazard_codes = []
        hazard_texts = []

        for statement in hazard_statements:
            if not isinstance(
                statement,
                dict,
            ):
                continue

            code = clean_text(
                statement.get(
                    "hazardStatementCode"
                )
            )

            text = clean_text(
                statement.get(
                    "hazardStatementText"
                )
            )

            if code:
                hazard_codes.append(
                    code
                )

            if text:
                hazard_texts.append(
                    text
                )

        classifications.append(
            {
                "Classification ID": clean_text(
                    item.get(
                        "classificationId"
                    )
                ),
                "Hazard Class / Category": clean_text(
                    item.get(
                        "hazardClassAndCategoryCode"
                    )
                ),
                "H-statement": ", ".join(
                    hazard_codes
                ),
                "Hazard statement": " | ".join(
                    hazard_texts
                ),
                "Classified Hazard ID": clean_text(
                    item.get(
                        "classifiedHazardId"
                    )
                ),
            }
        )

    return classifications


def parse_pictograms(
    response_json: Any,
) -> list:
    pictograms = []

    for item in extract_items(
        response_json
    ):
        if not isinstance(
            item,
            dict,
        ):
            continue

        code = clean_text(
            item.get(
                "code"
            )
        )

        text = clean_text(
            item.get(
                "text"
            )
        )

        if not code:
            continue

        pictograms.append(
            {
                "Classification ID": clean_text(
                    item.get(
                        "classificationId"
                    )
                ),
                "Code": code,
                "Meaning": text,
                "Display Order": item.get(
                    "displayOrder"
                ),
                "Image URL": (
                    f"{CLP_PICTOGRAM_IMAGE_URL}/"
                    f"{quote(code, safe='')}"
                ),
            }
        )

    pictograms.sort(
        key=lambda item: (
            item["Display Order"]
            if isinstance(
                item["Display Order"],
                (int, float),
            )
            else 999999
        )
    )

    return pictograms


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
DEFAULT_STATE = {
    "clp_search_results": [],
    "clp_selected_index": 0,
    "clp_search_result": None,
    "clp_overview_result": None,
    "clp_details_result": None,
    "clp_pictograms_result": None,
}

for key, default_value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[
            key
        ] = default_value


# --------------------------------------------------
# SEARCH INPUT
# --------------------------------------------------
search_query = st.text_input(
    (
        "CAS number, EC number, "
        "substance name, or rmlId"
    ),
    value="128-37-0",
    placeholder="For example: 128-37-0",
)

if st.button(
    "Search ECHA",
    type="primary",
):
    clean_query = search_query.strip()

    if not clean_query:
        st.error(
            "Please enter a CAS number, "
            "EC number, substance name, "
            "or rmlId."
        )
        st.stop()

    if (
        looks_like_cas(
            clean_query
        )
        and not validate_cas_locally(
            clean_query
        )
    ):
        st.error(
            "Invalid CAS number."
        )
        st.stop()

    with st.spinner(
        "Searching ECHA..."
    ):
        search_result = search_echa_api(
            clean_query
        )

    st.session_state[
        "clp_search_result"
    ] = search_result

    st.session_state[
        "clp_search_results"
    ] = search_result[
        "results"
    ]

    st.session_state[
        "clp_selected_index"
    ] = 0

    st.session_state[
        "clp_overview_result"
    ] = None

    st.session_state[
        "clp_details_result"
    ] = None

    st.session_state[
        "clp_pictograms_result"
    ] = None

    if search_result["error"]:
        st.error(
            "The ECHA search failed."
        )

        st.info(
            search_result["error"]
        )

    elif (
        search_result["status"]
        != 200
    ):
        st.error(
            "ECHA returned HTTP "
            f"{search_result['status']}."
        )

    elif search_result["results"]:
        st.success(
            f"{len(search_result['results'])} "
            "result(s) found."
        )

    else:
        st.warning(
            "ECHA was reached, but no "
            "matching substance was found."
        )


# --------------------------------------------------
# SUBSTANCE SELECTION
# --------------------------------------------------
search_results = st.session_state[
    "clp_search_results"
]

selected_substance = None

if search_results:
    st.subheader(
        "1. Substance"
    )

    search_dataframe = pd.DataFrame(
        [
            {
                "Name": item[
                    "Name"
                ],
                "EC Number": item[
                    "EC Number"
                ],
                "CAS Number": item[
                    "CAS Number"
                ],
                "rmlId": item[
                    "rmlId"
                ],
            }
            for item in search_results
        ]
    )

    st.dataframe(
        search_dataframe,
        hide_index=True,
        use_container_width=True,
    )

    if len(search_results) == 1:
        selected_index = 0

        st.info(
            "The single ECHA result "
            "was selected automatically."
        )

    else:
        labels = [
            (
                f"{item['Name'] or 'Unnamed substance'}"
                f" | EC {item['EC Number'] or '-'}"
                f" | CAS {item['CAS Number'] or '-'}"
                f" | rmlId {item['rmlId'] or '-'}"
            )
            for item in search_results
        ]

        safe_index = min(
            st.session_state[
                "clp_selected_index"
            ],
            len(labels) - 1,
        )

        selected_label = st.selectbox(
            "Select substance",
            labels,
            index=safe_index,
        )

        selected_index = labels.index(
            selected_label
        )

        st.session_state[
            "clp_selected_index"
        ] = selected_index

    selected_substance = search_results[
        selected_index
    ]

    columns = st.columns(4)

    columns[0].metric(
        "Name",
        selected_substance[
            "Name"
        ]
        or "Unknown",
    )

    columns[1].metric(
        "CAS Number",
        selected_substance[
            "CAS Number"
        ]
        or "Unknown",
    )

    columns[2].metric(
        "EC Number",
        selected_substance[
            "EC Number"
        ]
        or "Unknown",
    )

    columns[3].metric(
        "rmlId",
        selected_substance[
            "rmlId"
        ]
        or "Unknown",
    )

    if selected_substance[
        "URL"
    ]:
        st.markdown(
            "[Open selected substance "
            "in ECHA CHEM]"
            f"({selected_substance['URL']})"
        )


# --------------------------------------------------
# COMPLETE CLP LOOKUP
# --------------------------------------------------
if selected_substance is not None:
    selected_rml_id = clean_text(
        selected_substance.get(
            "rmlId",
            "",
        )
    )

    st.subheader(
        "2. Retrieve CLP information"
    )

    if not selected_rml_id:
        st.warning(
            "The selected ECHA result does "
            "not contain an rmlId."
        )

    elif st.button(
        "Fetch CLP information",
        type="primary",
    ):
        st.session_state[
            "clp_overview_result"
        ] = None

        st.session_state[
            "clp_details_result"
        ] = None

        st.session_state[
            "clp_pictograms_result"
        ] = None

        with st.spinner(
            "Retrieving CLP overview..."
        ):
            overview_result = (
                get_clp_overview(
                    selected_rml_id
                )
            )

        st.session_state[
            "clp_overview_result"
        ] = overview_result

        if (
            overview_result["status"] == 200
            and overview_result["json"] is not None
        ):
            overview_items = parse_overview(
                overview_result[
                    "json"
                ]
            )

            if overview_items:
                primary_overview = (
                    overview_items[0]
                )

                classification_id = (
                    primary_overview[
                        "classification_id"
                    ]
                )

                classification_type = (
                    primary_overview[
                        "type"
                    ]
                )

                if classification_id:
                    with st.spinner(
                        "Retrieving classification "
                        "details..."
                    ):
                        details_result = (
                            get_classification_details(
                                classification_id=(
                                    classification_id
                                ),
                                classification_type=(
                                    classification_type
                                ),
                                rml_id=(
                                    selected_rml_id
                                ),
                            )
                        )

                    st.session_state[
                        "clp_details_result"
                    ] = details_result

                    with st.spinner(
                        "Retrieving ECHA "
                        "pictograms..."
                    ):
                        pictogram_result = (
                            get_pictograms(
                                classification_id=(
                                    classification_id
                                ),
                                classification_type=(
                                    classification_type
                                ),
                                rml_id=(
                                    selected_rml_id
                                ),
                            )
                        )

                    st.session_state[
                        "clp_pictograms_result"
                    ] = pictogram_result


# --------------------------------------------------
# DISPLAY PARSED CLP INFORMATION
# --------------------------------------------------
overview_result = st.session_state[
    "clp_overview_result"
]

details_result = st.session_state[
    "clp_details_result"
]

pictogram_result = st.session_state[
    "clp_pictograms_result"
]

if overview_result is not None:
    st.divider()

    st.subheader(
        "3. Parsed CLP information"
    )

    if overview_result["error"]:
        st.error(
            "The ECHA CLP overview request failed."
        )

        st.info(
            overview_result["error"]
        )

    elif (
        overview_result["status"]
        != 200
    ):
        st.error(
            "ECHA returned HTTP "
            f"{overview_result['status']} "
            "for the CLP overview."
        )

    elif (
        overview_result["json"]
        is None
    ):
        st.warning(
            "ECHA returned no parseable "
            "CLP overview JSON."
        )

    else:
        overview_items = parse_overview(
            overview_result[
                "json"
            ]
        )

        if not overview_items:
            st.warning(
                "ECHA returned no CLP "
                "overview items."
            )

        else:
            primary_overview = (
                overview_items[0]
            )

            overview_columns = (
                st.columns(4)
            )

            overview_columns[0].metric(
                "Classification ID",
                primary_overview[
                    "classification_id"
                ]
                or "-",
            )

            overview_columns[1].metric(
                "Classification type",
                primary_overview[
                    "type"
                ]
                or "-",
            )

            overview_columns[2].metric(
                "Signal word",
                primary_overview[
                    "signal_word"
                ]
                or "-",
            )

            overview_columns[3].metric(
                "Industry classifications",
                (
                    primary_overview[
                        "industry_count"
                    ]
                    if primary_overview[
                        "industry_count"
                    ] is not None
                    else "-"
                ),
            )

            harmonised_count = (
                primary_overview[
                    "harmonised_count"
                ]
            )

            st.write(
                "**Harmonised classifications:**",
                (
                    harmonised_count
                    if harmonised_count
                    is not None
                    else "-"
                ),
            )

            if (
                primary_overview[
                    "type"
                ].lower()
                == "industry"
            ):
                st.info(
                    "This result represents an "
                    "industry classification from "
                    "the ECHA Classification & "
                    "Labelling Inventory."
                )

            elif (
                primary_overview[
                    "type"
                ].lower()
                in {
                    "harmonised",
                    "harmonized",
                }
            ):
                st.success(
                    "This result represents a "
                    "harmonised classification."
                )


# --------------------------------------------------
# DISPLAY HAZARD CLASSIFICATION
# --------------------------------------------------
if details_result is not None:
    st.write(
        "### Hazard classification"
    )

    if details_result["error"]:
        st.error(
            "The classification detail "
            "request failed."
        )

        st.info(
            details_result["error"]
        )

    elif (
        details_result["status"]
        != 200
    ):
        st.error(
            "ECHA returned HTTP "
            f"{details_result['status']} "
            "for classification details."
        )

    elif (
        details_result["json"]
        is None
    ):
        st.warning(
            "No classification detail "
            "JSON was returned."
        )

    else:
        classifications = (
            parse_classification(
                details_result[
                    "json"
                ]
            )
        )

        if classifications:
            classification_dataframe = (
                pd.DataFrame(
                    classifications
                )
            )

            st.dataframe(
                classification_dataframe,
                hide_index=True,
                use_container_width=True,
            )

        else:
            st.info(
                "No hazard classifications "
                "were returned."
            )


# --------------------------------------------------
# DISPLAY ECHA PICTOGRAMS
# --------------------------------------------------
if pictogram_result is not None:
    st.write(
        "### ECHA pictograms"
    )

    st.caption(
        "Pictogram codes are retrieved directly "
        "from ECHA and are not inferred locally "
        "from the H-statements."
    )

    if pictogram_result["error"]:
        st.error(
            "The pictogram request failed."
        )

        st.info(
            pictogram_result["error"]
        )

    elif (
        pictogram_result["status"]
        != 200
    ):
        st.error(
            "ECHA returned HTTP "
            f"{pictogram_result['status']} "
            "for the pictogram request."
        )

    elif (
        pictogram_result["json"]
        is None
    ):
        st.warning(
            "The pictogram endpoint did not "
            "return parseable JSON."
        )

    else:
        pictograms = parse_pictograms(
            pictogram_result[
                "json"
            ]
        )

        if pictograms:
            number_of_columns = min(
                len(pictograms),
                5,
            )

            pictogram_columns = (
                st.columns(
                    number_of_columns
                )
            )

            for index, pictogram in enumerate(
                pictograms
            ):
                column = (
                    pictogram_columns[
                        index
                        % number_of_columns
                    ]
                )

                with column:
                    st.image(
                        pictogram[
                            "Image URL"
                        ],
                        width=120,
                    )

                    st.markdown(
                        f"**{pictogram['Code']}**"
                    )

                    st.write(
                        pictogram[
                            "Meaning"
                        ]
                        or "-"
                    )

            pictogram_dataframe = (
                pd.DataFrame(
                    [
                        {
                            "Code": item[
                                "Code"
                            ],
                            "Meaning": item[
                                "Meaning"
                            ],
                            "Display Order": item[
                                "Display Order"
                            ],
                        }
                        for item in pictograms
                    ]
                )
            )

            st.dataframe(
                pictogram_dataframe,
                hide_index=True,
                use_container_width=True,
            )

        else:
            st.info(
                "ECHA returned no pictograms "
                "for this classification."
            )


# --------------------------------------------------
# DEBUG OUTPUT
# --------------------------------------------------
if (
    overview_result is not None
    or details_result is not None
    or pictogram_result is not None
):
    st.divider()

    st.subheader(
        "4. API debugging"
    )


if overview_result is not None:
    with st.expander(
        "CLP overview response",
        expanded=False,
    ):
        st.write(
            "**Requested endpoint:**",
            overview_result[
                "request_url"
            ],
        )

        st.write(
            "**HTTP method:**",
            overview_result[
                "request_method"
            ],
        )

        st.write(
            "**HTTP status:**",
            overview_result[
                "status"
            ],
        )

        st.write(
            "**Content type:**",
            overview_result[
                "content_type"
            ]
            or "-",
        )

        if (
            overview_result["json"]
            is not None
        ):
            st.json(
                overview_result[
                    "json"
                ],
                expanded=False,
            )

        elif (
            overview_result[
                "response_text"
            ]
        ):
            st.code(
                overview_result[
                    "response_text"
                ][:30000],
                language=None,
            )


if details_result is not None:
    with st.expander(
        "Classification detail response",
        expanded=False,
    ):
        st.write(
            "**Requested endpoint:**",
            details_result[
                "request_url"
            ],
        )

        st.write(
            "**HTTP method:**",
            details_result[
                "request_method"
            ],
        )

        st.write(
            "**HTTP status:**",
            details_result[
                "status"
            ],
        )

        st.write(
            "**Content type:**",
            details_result[
                "content_type"
            ]
            or "-",
        )

        if (
            details_result["json"]
            is not None
        ):
            st.json(
                details_result[
                    "json"
                ],
                expanded=False,
            )

        elif (
            details_result[
                "response_text"
            ]
        ):
            st.code(
                details_result[
                    "response_text"
                ][:30000],
                language=None,
            )


if pictogram_result is not None:
    with st.expander(
        "Pictogram response",
        expanded=False,
    ):
        st.write(
            "**Requested endpoint:**",
            pictogram_result[
                "request_url"
            ],
        )

        st.write(
            "**HTTP method:**",
            pictogram_result[
                "request_method"
            ],
        )

        st.write(
            "**HTTP status:**",
            pictogram_result[
                "status"
            ],
        )

        st.write(
            "**Content type:**",
            pictogram_result[
                "content_type"
            ]
            or "-",
        )

        if (
            pictogram_result["json"]
            is not None
        ):
            st.json(
                pictogram_result[
                    "json"
                ],
                expanded=False,
            )

        elif (
            pictogram_result[
                "response_text"
            ]
        ):
            st.code(
                pictogram_result[
                    "response_text"
                ][:30000],
                language=None,
            )


# --------------------------------------------------
# RAW JSON DOWNLOADS
# --------------------------------------------------
if (
    details_result is not None
    and details_result["json"]
    is not None
):
    classification_json = json.dumps(
        details_result["json"],
        ensure_ascii=False,
        indent=2,
    ).encode(
        "utf-8"
    )

    st.download_button(
        label=(
            "Download classification "
            "JSON"
        ),
        data=classification_json,
        file_name=(
            "ECHA_CLP_classification.json"
        ),
        mime="application/json",
    )


if (
    pictogram_result is not None
    and pictogram_result["json"]
    is not None
):
    pictogram_json = json.dumps(
        pictogram_result["json"],
        ensure_ascii=False,
        indent=2,
    ).encode(
        "utf-8"
    )

    st.download_button(
        label=(
            "Download pictogram JSON"
        ),
        data=pictogram_json,
        file_name=(
            "ECHA_CLP_pictograms.json"
        ),
        mime="application/json",
    )


# --------------------------------------------------
# CACHE CONTROL
# --------------------------------------------------
st.divider()

if st.button(
    "Clear CLP test cache",
):
    st.cache_data.clear()

    for key, default_value in (
        DEFAULT_STATE.items()
    ):
        st.session_state[
            key
        ] = default_value

    st.success(
        "CLP test cache cleared."
    )

    st.rerun()