import json
import re
from pathlib import Path

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.cas_validator import validate_cas
from services.ecics_lookup import get_goods_code
from services.taric_lookup import COUNTRY_CODES, get_taric
from services.purchase_history import (
    get_purchase_information,
    load_purchase_history,
)
from services.sales_history import (
    get_customers_for_cas,
    get_sales_information,
    load_sales_history,
)


# --------------------------------------------------
# PAGE SETTINGS
# --------------------------------------------------
st.set_page_config(
    page_title="EU Chemical Import Tool",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 EU Chemical Import Tool")

st.write(
    "Search ECHA CHEM by CAS number, EC number, substance name, or rmlId. "
    "The tool retrieves the selected substance, current ECHA registrants, "
    "ECICS/TARIC information, and internal purchase and sales history."
)


# --------------------------------------------------
# ECHA API CONFIGURATION
# --------------------------------------------------
ECHA_BASE_URL = "https://chem.echa.europa.eu"
SUBSTANCE_SEARCH_API_URL = f"{ECHA_BASE_URL}/api-substance/v1/substance"
REGISTRANTS_API_URL = f"{ECHA_BASE_URL}/api-registrants/v1/registrants"

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

    return " ".join(
        text.split()
    )


def clean_identifier(value):
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
            cleaned_item = clean_identifier(
                item
            )

            if (
                cleaned_item
                and
                cleaned_item not in cleaned_values
            ):
                cleaned_values.append(
                    cleaned_item
                )

        return ", ".join(
            cleaned_values
        )

    if isinstance(
        value,
        dict,
    ):
        return clean_text(
            value
        )

    return clean_text(
        value
    )


def looks_like_cas(value):
    return bool(
        re.fullmatch(
            r"\d{2,7}-\d{2}-\d",
            value.strip(),
        )
    )


def create_echa_session():
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
            max_retries=retry
        ),
    )

    return session


def echa_get(
    session,
    url,
    params=None,
    referer=None,
):
    request_headers = (
        {
            "Referer": referer
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
        response_json = (
            response.json()
        )

    except ValueError:
        response_json = None

    return {
        "response": response,
        "json": response_json,
        "error": None,
    }


def extract_items(
    response_json,
):
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
    response_json,
):
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
    value,
    possible_keys,
):
    wanted_keys = {
        key.lower()
        for key in possible_keys
    }

    if isinstance(
        value,
        dict,
    ):
        for key, nested_value in (
            value.items()
        ):
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

        for nested_value in (
            value.values()
        ):
            result = find_first_field(
                nested_value,
                possible_keys,
            )

            if result not in (
                None,
                "",
            ):
                return result

    elif isinstance(
        value,
        list,
    ):
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
    item,
):
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
            "_raw": item,
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
        or
        find_first_field(
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
        or
        find_first_field(
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
        or
        substance_index.get(
            "casNumber"
        )
        or
        find_first_field(
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
        or
        substance_index.get(
            "rmlEc"
        )
        or
        substance_index.get(
            "rmlEcNumber"
        )
        or
        find_first_field(
            item,
            {
                "ecNumber",
                "rmlEc",
                "rmlEcNumber",
                "ec",
            },
        )
    )

    clean_rml_id = (
        clean_text(
            rml_id
        )
    )

    return {
        "Name": (
            clean_text(
                substance_name
            )
        ),
        "EC Number": (
            clean_identifier(
                ec_number
            )
        ),
        "CAS Number": (
            clean_identifier(
                cas_number
            )
        ),
        "rmlId": (
            clean_rml_id
        ),
        "URL": (
            f"{ECHA_BASE_URL}/"
            f"{clean_rml_id}/overview"
            if clean_rml_id
            else ""
        ),
        "_raw": item,
    }


def substance_result_score(
    result,
    search_text,
):
    query = (
        clean_text(
            search_text
        )
        .lower()
    )

    name = (
        result.get(
            "Name",
            "",
        )
        .lower()
    )

    cas_number = (
        result.get(
            "CAS Number",
            "",
        )
        .lower()
    )

    ec_number = (
        result.get(
            "EC Number",
            "",
        )
        .lower()
    )

    rml_id = (
        result.get(
            "rmlId",
            "",
        )
        .lower()
    )

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
    search_text,
):
    session = (
        create_echa_session()
    )

    params = {
        "pageIndex": 1,
        "pageSize": 100,
        "searchText": (
            search_text
        ),
    }

    result = echa_get(
        session=session,
        url=SUBSTANCE_SEARCH_API_URL,
        params=params,
        referer=(
            f"{ECHA_BASE_URL}/"
            "substance-search"
            f"?searchText={search_text}"
        ),
    )

    substances = [
        normalise_substance(
            item
        )
        for item in extract_items(
            result[
                "json"
            ]
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

    response = (
        result[
            "response"
        ]
    )

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
        "json": (
            result[
                "json"
            ]
        ),
        "error": (
            result[
                "error"
            ]
        ),
        "params": (
            params
        ),
        "results": (
            substances
        ),
        "state": (
            extract_state(
                result[
                    "json"
                ]
            )
        ),
    }


# --------------------------------------------------
# ECHA REGISTRANTS
# --------------------------------------------------
def normalise_registrant(
    item,
):
    if not isinstance(
        item,
        dict,
    ):
        return {
            "Registrant": (
                clean_text(
                    item
                )
            ),
            "Address": "",
            "Status": "",
            "Details": "",
        }

    return {
        "Registrant": (
            clean_text(
                item.get(
                    "name"
                )
            )
        ),
        "Address": (
            clean_text(
                item.get(
                    "address"
                )
            )
        ),
        "Status": (
            clean_text(
                item.get(
                    "registrationStatus"
                )
            )
        ),
        "Details": (
            clean_text(
                item.get(
                    "details"
                )
            )
        ),
    }


def get_registrant_page(
    session,
    rml_id,
    page_index,
    page_size,
):
    params = {
        "pageIndex": (
            page_index
        ),
        "pageSize": (
            page_size
        ),
        "rmlId": (
            rml_id
        ),
    }

    result = echa_get(
        session=session,
        url=REGISTRANTS_API_URL,
        params=params,
        referer=(
            f"{ECHA_BASE_URL}/"
            f"{rml_id}/overview"
        ),
    )

    response = (
        result[
            "response"
        ]
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
        "text": (
            response.text
            if response is not None
            else ""
        ),
        "json": (
            result[
                "json"
            ]
        ),
        "error": (
            result[
                "error"
            ]
        ),
        "params": (
            params
        ),
        "items": (
            extract_items(
                result[
                    "json"
                ]
            )
        ),
        "state": (
            extract_state(
                result[
                    "json"
                ]
            )
        ),
    }


@st.cache_data(
    ttl=86400,
    show_spinner=False,
)
def get_echa_registrants(
    rml_id,
):
    session = (
        create_echa_session()
    )

    page_size = 100

    first_page = (
        get_registrant_page(
            session=session,
            rml_id=rml_id,
            page_index=1,
            page_size=page_size,
        )
    )

    if (
        first_page[
            "error"
        ]
        or
        first_page[
            "status"
        ]
        != 200
        or
        first_page[
            "json"
        ]
        is None
    ):
        return {
            "status": (
                first_page[
                    "status"
                ]
            ),
            "url": (
                first_page[
                    "url"
                ]
            ),
            "content_type": (
                first_page[
                    "content_type"
                ]
            ),
            "text": (
                first_page[
                    "text"
                ]
            ),
            "json": (
                first_page[
                    "json"
                ]
            ),
            "error": (
                first_page[
                    "error"
                ]
            ),
            "state": (
                first_page[
                    "state"
                ]
            ),
            "registrants": [],
            "pages_loaded": 1,
        }

    all_items = list(
        first_page[
            "items"
        ]
    )

    state = (
        first_page[
            "state"
        ]
    )

    try:
        total_pages = int(
            state.get(
                "totalPages",
                1,
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        total_pages = 1

    pages_loaded = 1

    for page_index in range(
        2,
        total_pages + 1,
    ):
        page = (
            get_registrant_page(
                session=session,
                rml_id=rml_id,
                page_index=page_index,
                page_size=page_size,
            )
        )

        if (
            page[
                "error"
            ]
            or
            page[
                "status"
            ]
            != 200
            or
            page[
                "json"
            ]
            is None
        ):
            break

        all_items.extend(
            page[
                "items"
            ]
        )

        pages_loaded += 1

    registrants = [
        normalise_registrant(
            item
        )
        for item in all_items
    ]

    return {
        "status": (
            first_page[
                "status"
            ]
        ),
        "url": (
            first_page[
                "url"
            ]
        ),
        "content_type": (
            first_page[
                "content_type"
            ]
        ),
        "text": (
            first_page[
                "text"
            ]
        ),
        "json": (
            first_page[
                "json"
            ]
        ),
        "error": None,
        "state": (
            state
        ),
        "registrants": (
            registrants
        ),
        "pages_loaded": (
            pages_loaded
        ),
    }


# --------------------------------------------------
# CACHED EXISTING SERVICES
# --------------------------------------------------
@st.cache_data(
    ttl=86400,
)
def get_cached_goods_code(
    ec_number,
):
    return get_goods_code(
        ec_number
    )


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
DEFAULT_STATE = {
    "search_results": [],
    "selected_result_index": 0,
    "last_search_query": "",
    "echa_search_debug": None,
    "registrant_result": None,
    "registrant_rml_id": "",
}

for key, default_value in (
    DEFAULT_STATE.items()
):
    if key not in st.session_state:
        st.session_state[
            key
        ] = default_value


# --------------------------------------------------
# LOAD PURCHASE AND SALES HISTORY
# --------------------------------------------------
BASE_DIR = (
    Path(
        __file__
    )
    .resolve()
    .parent
)

PURCHASE_HISTORY_FILE = (
    BASE_DIR
    / "data"
    / "aankoop orders product - leverancier.xlsx"
)

SALES_HISTORY_FILE = (
    BASE_DIR
    / "data"
    / "Sales information.xlsx"
)

purchase_df = None
sales_df = None

try:
    purchase_df = (
        load_purchase_history(
            PURCHASE_HISTORY_FILE
        )
    )

except Exception as error:
    st.error(
        "Purchase history error: "
        f"{error}"
    )

try:
    sales_df = (
        load_sales_history(
            SALES_HISTORY_FILE
        )
    )

except Exception as error:
    st.error(
        "Sales history error: "
        f"{error}"
    )


# --------------------------------------------------
# SEARCH INPUTS
# --------------------------------------------------
search_query = (
    st.text_input(
        (
            "CAS number, EC number, "
            "substance name, or rmlId"
        ),
        placeholder=(
            "For example: 128-37-0"
        ),
    )
)

country = (
    st.selectbox(
        "Country of Origin",
        options=list(
            COUNTRY_CODES.keys()
        ),
        index=0,
    )
)


# --------------------------------------------------
# SEARCH BUTTON
# --------------------------------------------------
if st.button(
    "Search ECHA",
    type="primary",
):
    clean_query = (
        search_query.strip()
    )

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
        and
        not validate_cas(
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
        search_result = (
            search_echa_api(
                clean_query
            )
        )

    st.session_state[
        "last_search_query"
    ] = clean_query

    st.session_state[
        "echa_search_debug"
    ] = search_result

    st.session_state[
        "search_results"
    ] = search_result[
        "results"
    ]

    st.session_state[
        "selected_result_index"
    ] = 0

    st.session_state[
        "registrant_result"
    ] = None

    st.session_state[
        "registrant_rml_id"
    ] = ""

    if search_result[
        "error"
    ]:
        st.error(
            "The ECHA search "
            "could not be completed."
        )

        st.info(
            search_result[
                "error"
            ]
        )

    elif (
        search_result[
            "response_status"
        ]
        != 200
    ):
        st.error(
            "ECHA returned HTTP "
            f"{search_result['response_status']} "
            "for the substance search."
        )

    elif search_result[
        "results"
    ]:
        st.success(
            f"{len(search_result['results'])} "
            "result(s) found."
        )

    else:
        st.warning(
            "ECHA was reached, but no "
            "matching result was found."
        )


# --------------------------------------------------
# SEARCH DEBUG INFORMATION
# --------------------------------------------------
search_debug = (
    st.session_state[
        "echa_search_debug"
    ]
)

if search_debug is not None:
    with st.expander(
        "ECHA substance search details",
        expanded=False,
    ):
        debug_columns = (
            st.columns(3)
        )

        debug_columns[0].metric(
            "HTTP",
            (
                search_debug[
                    "response_status"
                ]
                if search_debug[
                    "response_status"
                ]
                is not None
                else "Error"
            ),
        )

        debug_columns[1].metric(
            "Valid JSON",
            (
                "Yes"
                if search_debug[
                    "json"
                ]
                is not None
                else "No"
            ),
        )

        debug_columns[2].metric(
            "Results",
            len(
                search_debug[
                    "results"
                ]
            ),
        )

        st.write(
            "**Endpoint:**"
        )

        st.code(
            SUBSTANCE_SEARCH_API_URL,
            language=None,
        )

        st.write(
            "**Parameters:**"
        )

        st.json(
            search_debug[
                "params"
            ]
        )

        st.write(
            "**Final URL:**"
        )

        st.code(
            (
                search_debug[
                    "response_url"
                ]
                or
                "No response URL"
            ),
            language=None,
        )

        st.write(
            "**Content-Type:** "
            f"{search_debug['response_content_type']}"
        )


# --------------------------------------------------
# DISPLAY ECHA RESULTS AND SELECT SUBSTANCE
# --------------------------------------------------
selected_row = None

search_results = (
    st.session_state[
        "search_results"
    ]
)

if search_results:
    display_dataframe = (
        pd.DataFrame(
            [
                {
                    "Name": (
                        result[
                            "Name"
                        ]
                    ),
                    "EC Number": (
                        result[
                            "EC Number"
                        ]
                    ),
                    "CAS Number": (
                        result[
                            "CAS Number"
                        ]
                    ),
                    "rmlId": (
                        result[
                            "rmlId"
                        ]
                    ),
                }
                for result in search_results
            ]
        )
    )

    st.subheader(
        "ECHA Search Results"
    )

    st.dataframe(
        display_dataframe,
        use_container_width=True,
        hide_index=True,
    )

    if (
        len(
            search_results
        )
        == 1
    ):
        selected_index = 0

        st.info(
            "Only one ECHA result found. "
            "Automatically selected."
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
                "selected_result_index"
            ],
            len(
                result_labels
            ) - 1,
        )

        selected_label = (
            st.selectbox(
                "Select substance",
                options=result_labels,
                index=safe_index,
            )
        )

        selected_index = (
            result_labels.index(
                selected_label
            )
        )

        st.session_state[
            "selected_result_index"
        ] = selected_index

    selected_row = (
        search_results[
            selected_index
        ]
    )

    st.subheader(
        "Selected Substance"
    )

    selected_columns = (
        st.columns(4)
    )

    selected_columns[0].metric(
        "Name",
        (
            selected_row[
                "Name"
            ]
            or "Unknown"
        ),
    )

    selected_columns[1].metric(
        "EC Number",
        (
            selected_row[
                "EC Number"
            ]
            or "Unknown"
        ),
    )

    selected_columns[2].metric(
        "CAS Number",
        (
            selected_row[
                "CAS Number"
            ]
            or "Unknown"
        ),
    )

    selected_columns[3].metric(
        "rmlId",
        (
            selected_row[
                "rmlId"
            ]
            or "Unknown"
        ),
    )

    if selected_row[
        "URL"
    ]:
        st.markdown(
            "[Open substance in ECHA CHEM]"
            f"({selected_row['URL']})"
        )


# --------------------------------------------------
# AUTOMATIC REGISTRANTS API LOOKUP
# --------------------------------------------------
if selected_row is not None:
    selected_rml_id = (
        selected_row.get(
            "rmlId",
            "",
        )
    )

    if not selected_rml_id:
        st.warning(
            "The selected ECHA result "
            "does not contain an rmlId."
        )

    else:
        if (
            st.session_state[
                "registrant_rml_id"
            ]
            != selected_rml_id
        ):
            with st.spinner(
                "Loading ECHA registrants..."
            ):
                st.session_state[
                    "registrant_result"
                ] = (
                    get_echa_registrants(
                        selected_rml_id
                    )
                )

            st.session_state[
                "registrant_rml_id"
            ] = selected_rml_id

        registrant_result = (
            st.session_state[
                "registrant_result"
            ]
        )

        st.subheader(
            "REACH Registrants"
        )

        if registrant_result is None:
            st.warning(
                "No registrant result "
                "is available."
            )

        elif registrant_result[
            "error"
        ]:
            st.error(
                "The ECHA registrants request "
                "could not be completed."
            )

            st.info(
                registrant_result[
                    "error"
                ]
            )

        elif (
            registrant_result[
                "status"
            ]
            != 200
        ):
            st.error(
                "ECHA returned HTTP "
                f"{registrant_result['status']} "
                "for the registrants request."
            )

            with st.expander(
                "Raw registrants response",
                expanded=False,
            ):
                st.code(
                    registrant_result[
                        "text"
                    ][:30000],
                    language=None,
                )

        else:
            registrants = (
                registrant_result[
                    "registrants"
                ]
            )

            registrant_state = (
                registrant_result[
                    "state"
                ]
            )

            registrant_columns = (
                st.columns(4)
            )

            registrant_columns[0].metric(
                "HTTP",
                registrant_result[
                    "status"
                ],
            )

            registrant_columns[1].metric(
                "Total reported",
                registrant_state.get(
                    "totalItems",
                    len(
                        registrants
                    ),
                ),
            )

            registrant_columns[2].metric(
                "Rows loaded",
                len(
                    registrants
                ),
            )

            registrant_columns[3].metric(
                "Pages loaded",
                registrant_result[
                    "pages_loaded"
                ],
            )

            st.write(
                "**Final API URL:**"
            )

            st.code(
                registrant_result[
                    "url"
                ],
                language=None,
            )

            if registrants:
                registrants_dataframe = (
                    pd.DataFrame(
                        registrants
                    )
                )

                status_options = sorted(
                    value
                    for value in (
                        registrants_dataframe[
                            "Status"
                        ]
                        .dropna()
                        .unique()
                        .tolist()
                    )
                    if str(
                        value
                    ).strip()
                )

                selected_statuses = (
                    st.multiselect(
                        "Filter by registration status",
                        options=status_options,
                        default=status_options,
                    )
                )

                show_confidential = (
                    st.checkbox(
                        (
                            "Show confidential or "
                            "non-publishable registrants"
                        ),
                        value=True,
                    )
                )

                filtered_registrants = (
                    registrants_dataframe.copy()
                )

                if selected_statuses:
                    filtered_registrants = (
                        filtered_registrants[
                            filtered_registrants[
                                "Status"
                            ].isin(
                                selected_statuses
                            )
                        ]
                    )

                else:
                    filtered_registrants = (
                        filtered_registrants.iloc[
                            0:0
                        ]
                    )

                if not show_confidential:
                    confidential_names = {
                        "[Confidential]",
                        (
                            "Only representative "
                            "(No publishable name)"
                        ),
                    }

                    filtered_registrants = (
                        filtered_registrants[
                            ~filtered_registrants[
                                "Registrant"
                            ].isin(
                                confidential_names
                            )
                        ]
                    )

                filtered_registrants = (
                    filtered_registrants
                    .reset_index(
                        drop=True
                    )
                )

                st.dataframe(
                    filtered_registrants,
                    use_container_width=True,
                    hide_index=True,
                )

                st.download_button(
                    label=(
                        "Download registrants "
                        "as CSV"
                    ),
                    data=(
                        filtered_registrants
                        .to_csv(
                            index=False
                        )
                        .encode(
                            "utf-8-sig"
                        )
                    ),
                    file_name=(
                        "ECHA_registrants_"
                        f"{selected_rml_id}.csv"
                    ),
                    mime="text/csv",
                )

            else:
                st.warning(
                    "No registrants were returned "
                    "for the selected substance."
                )


# --------------------------------------------------
# ECICS AND TARIC LOOKUP
# --------------------------------------------------
ecics_result = None

if selected_row is not None:
    selected_ec_number = (
        selected_row.get(
            "EC Number",
            "",
        )
    )

    selected_cas_number = (
        selected_row.get(
            "CAS Number",
            "",
        )
    )

    if selected_ec_number:
        with st.spinner(
            "Searching ECICS..."
        ):
            try:
                ecics_result = (
                    get_cached_goods_code(
                        selected_ec_number
                    )
                )

            except Exception as error:
                ecics_result = {
                    "success": False,
                    "message": (
                        "ECICS lookup failed: "
                        f"{error}"
                    ),
                }

        if ecics_result.get(
            "success"
        ):
            st.subheader(
                "ECICS Information"
            )

            ecics_columns = (
                st.columns(2)
            )

            with ecics_columns[0]:
                st.write(
                    "Goods Code: "
                    f"{ecics_result.get('goods_code', '-')}"
                )

                st.write(
                    "CUS Number: "
                    f"{ecics_result.get('cus_number', '-')}"
                )

            with ecics_columns[1]:
                st.write(
                    "CAS Number: "
                    f"{ecics_result.get('cas_number', '-')}"
                )

                st.write(
                    "Substance Name: "
                    f"{ecics_result.get('substance_name', '-')}"
                )

        else:
            st.warning(
                ecics_result.get(
                    "message",
                    "No ECICS result found.",
                )
            )

    else:
        st.info(
            "No EC number is available "
            "for the ECICS lookup."
        )

    if (
        ecics_result
        and
        ecics_result.get(
            "success"
        )
    ):
        goods_code = (
            ecics_result.get(
                "goods_code"
            )
        )

        if goods_code:
            with st.spinner(
                "Building TARIC URL..."
            ):
                try:
                    taric_result = (
                        get_taric(
                            goods_code,
                            country,
                            selected_cas_number,
                        )
                    )

                except Exception as error:
                    taric_result = {
                        "success": False,
                        "message": (
                            "TARIC lookup failed: "
                            f"{error}"
                        ),
                    }

            st.subheader(
                "TARIC Information"
            )

            if taric_result.get(
                "success"
            ):
                st.write(
                    "Country of Origin: "
                    f"{country}"
                )

                st.write(
                    "Goods Code: "
                    f"{goods_code}"
                )

                st.markdown(
                    taric_result.get(
                        "taric_url",
                        "",
                    )
                )

                if (
                    "selected_taric_code"
                    in taric_result
                ):
                    st.write(
                        "Selected TARIC Code: "
                        f"{taric_result['selected_taric_code']}"
                    )

                if (
                    "measure_text"
                    in taric_result
                ):
                    st.text_area(
                        "TARIC Measures",
                        taric_result[
                            "measure_text"
                        ],
                        height=800,
                    )

            else:
                st.warning(
                    taric_result.get(
                        "message",
                        "TARIC lookup failed.",
                    )
                )

                if (
                    "debug_links"
                    in taric_result
                ):
                    with st.expander(
                        "TARIC debug links",
                        expanded=False,
                    ):
                        for link in (
                            taric_result[
                                "debug_links"
                            ]
                        ):
                            st.write(
                                link
                            )


# --------------------------------------------------
# PURCHASE HISTORY LOOKUP
# --------------------------------------------------
if (
    selected_row is not None
    and
    purchase_df is not None
):
    selected_cas = (
        selected_row.get(
            "CAS Number",
            "",
        )
    )

    if selected_cas:
        try:
            purchase_info = (
                get_purchase_information(
                    purchase_df,
                    selected_cas,
                )
            )

        except Exception as error:
            st.error(
                "Purchase history lookup failed: "
                f"{error}"
            )

            purchase_info = None

        if purchase_info is not None:
            st.subheader(
                "Purchase History"
            )

            if purchase_info.get(
                "purchased"
            ):
                st.success(
                    "This product has previously "
                    "been purchased."
                )

                latest_suppliers = (
                    purchase_info.get(
                        "last_suppliers",
                        [],
                    )
                )

                supplier_text = (
                    ", ".join(
                        latest_suppliers
                    )
                    if latest_suppliers
                    else
                    "Supplier not available"
                )

                purchase_columns = (
                    st.columns(2)
                )

                with purchase_columnslast_purchase_date = (
                        purchase_info.get(
                            "last_purchase_date"
                        )
                    )

                    st.write(
                        "**Last purchase date:**",
                        (
                            last_purchase_date.strftime("%d/%m/%Y")
                            if pd.notna(last_purchase_date)
                            else "-"
                        ),
                    )

                    st.write(
                        "**Supplier on last purchase:**",
                        supplier_text,
                    )
                    st.write(
                        "**Last purchase date:**",
                        (
                            last_purchase_date.strftime(
                                "%d/%m/%Y"
                            )
                            if pd.notna(
                                last_purchase_date
                            )
                            else "-"
                        ),
                    )

                    st.write(
                        "**Supplier on last purchase:**",
                        supplier_text,
                    )

                with purchase_columns[1]:
                    st.write(
                        "**Purchase lines found:**",
                        purchase_info.get(
                            "purchase_line_count",
                            0,
                        ),
                    )

                    st.write(
                        "**Suppliers used:**",
                        len(
                            purchase_info.get(
                                "all_suppliers",
                                [],
                            )
                        ),
                    )

                latest_purchases = (
                    purchase_info[
                        "latest_purchases"
                    ]
                    .copy()
                )

                latest_purchases[
                    "unit_price"
                ] = (
                    latest_purchases[
                        "purchase_price"
                    ]
                    .fillna("")
                    .astype(str)
                    +
                    " "
                    +
                    latest_purchases[
                        "currency"
                    ]
                    .fillna("")
                    .astype(str)
                ).str.strip()

                latest_columns = [
                    "supplier_name",
                    "product_description",
                    "article_reference",
                    "unit_price",
                ]

                latest_columns = [
                    column
                    for column in latest_columns
                    if column
                    in latest_purchases.columns
                ]

                st.write(
                    "**Most recent purchase:**"
                )

                st.dataframe(
                    latest_purchases[
                        latest_columns
                    ],
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "supplier_name": (
                            "Supplier"
                        ),
                        "product_description": (
                            "Purchased product"
                        ),
                        "article_reference": (
                            "Article reference"
                        ),
                        "unit_price": (
                            "Unit purchase price"
                        ),
                    },
                )

                with st.expander(
                    "View complete purchase history"
                ):
                    history = (
                        purchase_info[
                            "history"
                        ]
                        .copy()
                    )

                    history_columns = [
                        "purchase_date",
                        "supplier_name",
                        "product_description",
                        "article_reference",
                        "purchase_price",
                        "currency",
                        "document_number",
                    ]

                    history_columns = [
                        column
                        for column in history_columns
                        if column
                        in history.columns
                    ]

                    st.dataframe(
                        history[
                            history_columns
                        ],
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "purchase_date": (
                                st.column_config.DateColumn(
                                    "Purchase date",
                                    format="DD/MM/YYYY",
                                )
                            ),
                            "supplier_name": (
                                "Supplier"
                            ),
                            "product_description": (
                                "Purchased product"
                            ),
                            "article_reference": (
                                "Article reference"
                            ),
                            "document_number": (
                                "Document number"
                            ),
                            "purchase_price": (
                                "Unit purchase price"
                            ),
                            "currency": (
                                "Currency"
                            ),
                        },
                    )

            else:
                st.info(
                    purchase_info.get(
                        "message",
                        "No purchase history found.",
                    )
                )

    else:
        st.info(
            "No CAS number is available "
            "for the purchase history lookup."
        )


# --------------------------------------------------
# SALES HISTORY LOOKUP
# --------------------------------------------------
if (
    selected_row is not None
    and
    sales_df is not None
):
    selected_cas = (
        selected_row.get(
            "CAS Number",
            "",
        )
    )

    if selected_cas:
        st.subheader(
            "Sales History"
        )

        try:
            customers = (
                get_customers_for_cas(
                    sales_df,
                    selected_cas,
                )
            )

        except Exception as error:
            st.error(
                "Could not load customers: "
                f"{error}"
            )

            customers = []

        customer_options = [
            "All customers"
        ]

        customer_options.extend(
            customers
            or []
        )

        selected_customer = (
            st.selectbox(
                "Customer",
                customer_options,
                key=(
                    "sales_customer_selector"
                ),
            )
        )

        try:
            sales_info = (
                get_sales_information(
                    sales_df,
                    selected_cas,
                    (
                        None
                        if selected_customer
                        == "All customers"
                        else selected_customer
                    ),
                )
            )

        except Exception as error:
            st.error(
                "Sales history lookup failed: "
                f"{error}"
            )

            sales_info = None

        if sales_info is not None:
            if sales_info.get(
                "sold"
            ):
                history = (
                    sales_info[
                        "history"
                    ]
                    .copy()
                )

                latest_sale = (
                    history.iloc[0]
                )

                st.success(
                    f"{sales_info.get('sales_line_count', len(history))} "
                    "sales records found."
                )

                st.write(
                    "### Last Sale"
                )

                sales_columns = (
                    st.columns(2)
                )

                with sales_columnssales_date = (
                        latest_sale.get(
                            "sales_date"
                        )
                    )

                    st.write(
                        "**Date:**",
                        (
                            sales_date.strftime("%d/%m/%Y")
                            if pd.notna(sales_date)
                            else "-"
                        ),
                    )

                    st.write(
                        "**Sales Order:**",
                        latest_sale.get(
                            "sales_order",
                            "-",
                        ),
                    )

                    st.write(
                        "**Date:**",
                        (
                            sales_date.strftime(
                                "%d/%m/%Y"
                            )
                            if pd.notna(
                                sales_date
                            )
                            else "-"
                        ),
                    )

                    st.write(
                        "**Sales Order:**",
                        latest_sale.get(
                            "sales_order",
                            "-",
                        ),
                    )

                with sales_columns[1]:
                    st.write(
                        "**Unit Price:**",
                        latest_sale.get(
                            "sales_price",
                            "-",
                        ),
                    )

                    st.write(
                        "**Quantity:**",
                        latest_sale.get(
                            "sales_quantity",
                            "-",
                        ),
                    )

                st.write(
                    "### Sales History"
                )

                history_columns = [
                    "sales_date",
                    "customer_name",
                    "product_description",
                    "sales_order",
                    "sales_quantity",
                    "sales_price",
                    "currency",
                    "sales_value",
                    "document_number",
                ]

                history_columns = [
                    column
                    for column in history_columns
                    if column
                    in history.columns
                ]

                st.dataframe(
                    history[
                        history_columns
                    ],
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "sales_date": (
                            st.column_config.DateColumn(
                                "Date",
                                format="DD/MM/YYYY",
                            )
                        ),
                        "customer_name": (
                            "Customer"
                        ),
                        "product_description": (
                            "Product"
                        ),
                        "sales_order": (
                            "Sales Order"
                        ),
                        "sales_quantity": (
                            st.column_config.NumberColumn(
                                "Quantity",
                                format="%.2f",
                            )
                        ),
                        "sales_price": (
                            st.column_config.NumberColumn(
                                "Unit Price",
                                format="%.2f",
                            )
                        ),
                        "sales_value": (
                            st.column_config.NumberColumn(
                                "Sales Value",
                                format="%.2f",
                            )
                        ),
                        "currency": (
                            "Currency"
                        ),
                        "document_number": (
                            "Document Number"
                        ),
                    },
                )

            else:
                st.info(
                    "No sales records found."
                )

    else:
        st.info(
            "No CAS number is available "
            "for the sales history lookup."
        )


# --------------------------------------------------
# CACHE CONTROL
# --------------------------------------------------
st.divider()

if st.button(
    "Clear Cache"
):
    st.cache_data.clear()

    for key, default_value in (
        DEFAULT_STATE.items()
    ):
        st.session_state[
            key
        ] = default_value

    st.success(
        "Cache and ECHA selections cleared."
    )