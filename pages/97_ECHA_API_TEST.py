import json

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="ECHA Automated Substance Lookup",
    page_icon="🧪",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_AUTOMATED_LOOKUP_V1"


# --------------------------------------------------
# KNOWN TEST VALUES
# --------------------------------------------------
DEFAULT_SEARCH_TEXT = "128-37-0"

EXPECTED_RML_ID = "100.004.439"
EXPECTED_EC_NUMBER = "204-881-4"
EXPECTED_REGISTRANTS = 42


# --------------------------------------------------
# ECHA API ENDPOINTS
# --------------------------------------------------
ECHA_BASE_URL = "https://chem.echa.europa.eu"

SUBSTANCE_SEARCH_API_URL = (
    f"{ECHA_BASE_URL}/"
    "api-substance/v1/substance"
)

REGISTRANTS_API_URL = (
    f"{ECHA_BASE_URL}/"
    "api-registrants/v1/registrants"
)


# --------------------------------------------------
# REQUEST SETTINGS
# --------------------------------------------------
CONNECT_TIMEOUT_SECONDS = 20
READ_TIMEOUT_SECONDS = 90

HEADERS = {
    "Accept": (
        "application/json,"
        "text/plain,"
        "*/*"
    ),
    "Accept-Language": (
        "en-US,en;q=0.9"
    ),
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


# --------------------------------------------------
# CREATE HTTP SESSION
# --------------------------------------------------
def create_session():
    session = requests.Session()

    session.headers.update(
        HEADERS
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

    adapter = HTTPAdapter(
        max_retries=retry
    )

    session.mount(
        "https://",
        adapter,
    )

    return session


# --------------------------------------------------
# GENERIC GET REQUEST
# --------------------------------------------------
def api_get(
    session,
    url,
    params=None,
    referer=None,
):
    request_headers = {}

    if referer:
        request_headers[
            "Referer"
        ] = referer

    try:
        response = session.get(
            url,
            params=params,
            headers=(
                request_headers
                or None
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


# --------------------------------------------------
# SAFE TEXT CONVERSION
# --------------------------------------------------
def clean_text(
    value,
):
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

    text = str(
        value
    ).strip()

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


# --------------------------------------------------
# RECURSIVE FIELD LOOKUP
# --------------------------------------------------
def find_first_field(
    value,
    possible_keys,
):
    wanted_keys = {
        key.lower()
        for key
        in possible_keys
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
# EXTRACT ITEMS FROM ECHA RESPONSE
# --------------------------------------------------
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


# --------------------------------------------------
# EXTRACT STATE FROM ECHA RESPONSE
# --------------------------------------------------
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


# --------------------------------------------------
# NORMALISE SUBSTANCE RESULT
# --------------------------------------------------
def normalise_substance(
    item,
):
    if not isinstance(
        item,
        dict,
    ):
        return {
            "Substance name": "",
            "CAS number": "",
            "EC number": "",
            "rmlId": "",
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

    return {
        "Substance name": (
            clean_text(
                substance_name
            )
        ),
        "CAS number": (
            clean_text(
                cas_number
            )
        ),
        "EC number": (
            clean_text(
                ec_number
            )
        ),
        "rmlId": (
            clean_text(
                rml_id
            )
        ),
        "_raw": item,
    }


# --------------------------------------------------
# SCORE RESULT AGAINST SEARCH TEXT
# --------------------------------------------------
def result_score(
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
            "Substance name",
            "",
        )
        .lower()
    )

    cas_number = (
        result.get(
            "CAS number",
            "",
        )
        .lower()
    )

    ec_number = (
        result.get(
            "EC number",
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

    if (
        query
        and
        query == cas_number
    ):
        return 100

    if (
        query
        and
        query == ec_number
    ):
        return 95

    if (
        query
        and
        query == rml_id
    ):
        return 90

    if (
        query
        and
        query == name
    ):
        return 85

    if (
        query
        and
        query in name
    ):
        return 60

    if (
        query
        and
        query in cas_number
    ):
        return 50

    if (
        query
        and
        query in ec_number
    ):
        return 45

    return 0


# --------------------------------------------------
# SEARCH SUBSTANCES
# --------------------------------------------------
@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def search_substances(
    search_text,
):
    session = create_session()

    params = {
        "pageIndex": 1,
        "pageSize": 100,
        "searchText": (
            search_text
        ),
    }

    referer = (
        f"{ECHA_BASE_URL}/"
        "substance-search"
        f"?searchText={search_text}"
    )

    result = api_get(
        session=session,
        url=SUBSTANCE_SEARCH_API_URL,
        params=params,
        referer=referer,
    )

    items = extract_items(
        result[
            "json"
        ]
    )

    substances = [
        normalise_substance(
            item
        )
        for item
        in items
    ]

    substances.sort(
        key=lambda substance: (
            result_score(
                substance,
                search_text,
            )
        ),
        reverse=True,
    )

    result[
        "params"
    ] = params

    result[
        "substances"
    ] = substances

    result[
        "state"
    ] = extract_state(
        result[
            "json"
        ]
    )

    return result


# --------------------------------------------------
# NORMALISE ONE REGISTRANT
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


# --------------------------------------------------
# LOAD ONE PAGE OF REGISTRANTS
# --------------------------------------------------
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

    referer = (
        f"{ECHA_BASE_URL}/"
        f"{rml_id}/overview"
    )

    result = api_get(
        session=session,
        url=REGISTRANTS_API_URL,
        params=params,
        referer=referer,
    )

    result[
        "params"
    ] = params

    result[
        "items"
    ] = extract_items(
        result[
            "json"
        ]
    )

    result[
        "state"
    ] = extract_state(
        result[
            "json"
        ]
    )

    return result


# --------------------------------------------------
# LOAD ALL REGISTRANTS
# --------------------------------------------------
@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def get_all_registrants(
    rml_id,
):
    session = create_session()

    page_size = 100

    first_page = get_registrant_page(
        session=session,
        rml_id=rml_id,
        page_index=1,
        page_size=page_size,
    )

    if (
        first_page[
            "error"
        ]
        or
        first_page[
            "response"
        ]
        is None
    ):
        return {
            "error": (
                first_page[
                    "error"
                ]
            ),
            "response": (
                first_page[
                    "response"
                ]
            ),
            "json": (
                first_page[
                    "json"
                ]
            ),
            "params": (
                first_page[
                    "params"
                ]
            ),
            "state": (
                first_page[
                    "state"
                ]
            ),
            "registrants": [],
            "page_results": [
                first_page
            ],
        }

    first_response = (
        first_page[
            "response"
        ]
    )

    if (
        first_response.status_code
        != 200
        or
        first_page[
            "json"
        ]
        is None
    ):
        return {
            "error": None,
            "response": (
                first_response
            ),
            "json": (
                first_page[
                    "json"
                ]
            ),
            "params": (
                first_page[
                    "params"
                ]
            ),
            "state": (
                first_page[
                    "state"
                ]
            ),
            "registrants": [],
            "page_results": [
                first_page
            ],
        }

    all_items = list(
        first_page[
            "items"
        ]
    )

    state = first_page[
        "state"
    ]

    total_pages = state.get(
        "totalPages",
        1,
    )

    try:
        total_pages = int(
            total_pages
        )

    except (
        TypeError,
        ValueError,
    ):
        total_pages = 1

    page_results = [
        first_page
    ]

    for page_index in range(
        2,
        total_pages + 1,
    ):
        page_result = (
            get_registrant_page(
                session=session,
                rml_id=rml_id,
                page_index=page_index,
                page_size=page_size,
            )
        )

        page_results.append(
            page_result
        )

        if (
            page_result[
                "error"
            ]
            or
            page_result[
                "response"
            ]
            is None
        ):
            break

        if (
            page_result[
                "response"
            ]
            .status_code
            != 200
        ):
            break

        all_items.extend(
            page_result[
                "items"
            ]
        )

    registrants = [
        normalise_registrant(
            item
        )
        for item
        in all_items
    ]

    return {
        "error": None,
        "response": (
            first_response
        ),
        "json": (
            first_page[
                "json"
            ]
        ),
        "params": (
            first_page[
                "params"
            ]
        ),
        "state": (
            state
        ),
        "registrants": (
            registrants
        ),
        "page_results": (
            page_results
        ),
    }


# --------------------------------------------------
# INITIALISE SESSION STATE
# --------------------------------------------------
if (
    "echa_search_results"
    not in st.session_state
):
    st.session_state[
        "echa_search_results"
    ] = []

if (
    "echa_search_debug"
    not in st.session_state
):
    st.session_state[
        "echa_search_debug"
    ] = None

if (
    "echa_selected_index"
    not in st.session_state
):
    st.session_state[
        "echa_selected_index"
    ] = 0

if (
    "echa_registrant_result"
    not in st.session_state
):
    st.session_state[
        "echa_registrant_result"
    ] = None

if (
    "echa_loaded_rml_id"
    not in st.session_state
):
    st.session_state[
        "echa_loaded_rml_id"
    ] = ""


# --------------------------------------------------
# PAGE HEADER
# --------------------------------------------------
st.title(
    "ECHA Automated Substance Lookup"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.write(
    "Search by CAS number, EC number, "
    "substance name, or rmlId. "
    "The tool first resolves the ECHA substance "
    "and then retrieves the published registrants."
)


# --------------------------------------------------
# SEARCH FORM
# --------------------------------------------------
with st.form(
    "echa_search_form",
):
    search_text = st.text_input(
        (
            "CAS number, EC number, "
            "substance name, or rmlId"
        ),
        value=DEFAULT_SEARCH_TEXT,
        placeholder=(
            "For example: 128-37-0"
        ),
    )

    search_clicked = (
        st.form_submit_button(
            "Search ECHA",
            type="primary",
        )
    )


# --------------------------------------------------
# PERFORM SEARCH
# --------------------------------------------------
if search_clicked:
    clean_query = (
        search_text.strip()
    )

    if not clean_query:
        st.warning(
            "Enter a CAS number, EC number, "
            "substance name, or rmlId."
        )

    else:
        with st.spinner(
            "Searching ECHA for the substance..."
        ):
            search_result = (
                search_substances(
                    clean_query
                )
            )

        st.session_state[
            "echa_search_debug"
        ] = search_result

        st.session_state[
            "echa_search_results"
        ] = search_result[
            "substances"
        ]

        st.session_state[
            "echa_selected_index"
        ] = 0

        st.session_state[
            "echa_registrant_result"
        ] = None

        st.session_state[
            "echa_loaded_rml_id"
        ] = ""


# --------------------------------------------------
# CURRENT STATE
# --------------------------------------------------
search_debug = (
    st.session_state[
        "echa_search_debug"
    ]
)

search_results = (
    st.session_state[
        "echa_search_results"
    ]
)


# --------------------------------------------------
# SUBSTANCE SEARCH RESPONSE
# --------------------------------------------------
if search_debug is not None:
    response = search_debug[
        "response"
    ]

    st.subheader(
        "1. Substance search request"
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

    if search_debug[
        "error"
    ]:
        st.error(
            search_debug[
                "error"
            ]
        )

    elif response is not None:
        response_columns = (
            st.columns(4)
        )

        response_columns[0].metric(
            "HTTP",
            response.status_code,
        )

        response_columns[1].metric(
            "Response bytes",
            len(
                response.content
            ),
        )

        response_columns[2].metric(
            "Valid JSON",
            (
                "Yes"
                if search_debug[
                    "json"
                ]
                is not None
                else
                "No"
            ),
        )

        response_columns[3].metric(
            "Results",
            len(
                search_results
            ),
        )

        st.write(
            "**Final URL:**"
        )

        st.code(
            response.url,
            language=None,
        )

        st.write(
            "**Content-Type:** "
            f"{response.headers.get('content-type', '')}"
        )

        if (
            response.status_code
            == 200
            and
            search_debug[
                "json"
            ]
            is not None
        ):
            st.success(
                "The ECHA substance search "
                "returned valid JSON."
            )

        elif (
            response.status_code
            == 403
        ):
            st.error(
                "ECHA returned HTTP 403 for "
                "the substance search endpoint."
            )

        elif (
            response.status_code
            == 404
        ):
            st.error(
                "ECHA returned HTTP 404 for "
                "the substance search endpoint."
            )

        elif (
            response.status_code
            == 429
        ):
            st.error(
                "ECHA returned HTTP 429. "
                "The request was rate limited."
            )

        elif (
            response.status_code
            >= 500
        ):
            st.error(
                "ECHA returned server error "
                f"HTTP {response.status_code}."
            )

        elif (
            response.status_code
            >= 400
        ):
            st.error(
                "ECHA returned HTTP "
                f"{response.status_code}."
            )


# --------------------------------------------------
# DISPLAY SEARCH RESULTS
# --------------------------------------------------
if search_results:
    st.subheader(
        "2. Substance search results"
    )

    display_rows = [
        {
            "Substance name": (
                result[
                    "Substance name"
                ]
            ),
            "CAS number": (
                result[
                    "CAS number"
                ]
            ),
            "EC number": (
                result[
                    "EC number"
                ]
            ),
            "rmlId": (
                result[
                    "rmlId"
                ]
            ),
        }
        for result
        in search_results
    ]

    st.dataframe(
        pd.DataFrame(
            display_rows
        ),
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
            "One result was found and "
            "selected automatically."
        )

    else:
        labels = []

        for result in search_results:
            label = (
                f"{result['Substance name'] or 'Unnamed substance'}"
                f" | CAS: {result['CAS number'] or '-'}"
                f" | EC: {result['EC number'] or '-'}"
                f" | rmlId: {result['rmlId'] or '-'}"
            )

            labels.append(
                label
            )

        safe_index = min(
            st.session_state[
                "echa_selected_index"
            ],
            len(
                labels
            ) - 1,
        )

        selected_label = (
            st.selectbox(
                "Select the correct substance",
                options=labels,
                index=safe_index,
            )
        )

        selected_index = (
            labels.index(
                selected_label
            )
        )

        st.session_state[
            "echa_selected_index"
        ] = selected_index

    selected_substance = (
        search_results[
            selected_index
        ]
    )

    st.subheader(
        "3. Selected substance"
    )

    selected_columns = (
        st.columns(4)
    )

    selected_columns[0].metric(
        "Substance",
        (
            selected_substance[
                "Substance name"
            ]
            or
            "Unknown"
        ),
    )

    selected_columns[1].metric(
        "CAS",
        (
            selected_substance[
                "CAS number"
            ]
            or
            "Unknown"
        ),
    )

    selected_columns[2].metric(
        "EC",
        (
            selected_substance[
                "EC number"
            ]
            or
            "Unknown"
        ),
    )

    selected_columns[3].metric(
        "rmlId",
        (
            selected_substance[
                "rmlId"
            ]
            or
            "Unknown"
        ),
    )

    if (
        search_text.strip()
        ==
        DEFAULT_SEARCH_TEXT
    ):
        benchmark_ok = (
            selected_substance[
                "rmlId"
            ]
            ==
            EXPECTED_RML_ID
            and
            selected_substance[
                "EC number"
            ]
            ==
            EXPECTED_EC_NUMBER
        )

        if benchmark_ok:
            st.success(
                "Benchmark match: CAS 128-37-0 "
                "resolved to EC 204-881-4 and "
                "rmlId 100.004.439."
            )

        else:
            st.warning(
                "The selected result does not "
                "yet match the complete expected "
                "BHT benchmark."
            )

    selected_rml_id = (
        selected_substance[
            "rmlId"
        ]
    )

    if not selected_rml_id:
        st.error(
            "The selected ECHA result "
            "does not contain an rmlId."
        )

    else:
        load_registrants = (
            st.button(
                (
                    "Load registrants for "
                    "selected substance"
                ),
                type="primary",
            )
        )

        if load_registrants:
            with st.spinner(
                "Loading ECHA registrants..."
            ):
                registrant_result = (
                    get_all_registrants(
                        selected_rml_id
                    )
                )

            st.session_state[
                "echa_registrant_result"
            ] = registrant_result

            st.session_state[
                "echa_loaded_rml_id"
            ] = selected_rml_id


# --------------------------------------------------
# DISPLAY REGISTRANTS
# --------------------------------------------------
registrant_result = (
    st.session_state[
        "echa_registrant_result"
    ]
)

loaded_rml_id = (
    st.session_state[
        "echa_loaded_rml_id"
    ]
)

if (
    registrant_result
    is not None
):
    st.subheader(
        "4. Registrants API response"
    )

    registrant_response = (
        registrant_result[
            "response"
        ]
    )

    if registrant_result[
        "error"
    ]:
        st.error(
            registrant_result[
                "error"
            ]
        )

    elif registrant_response is not None:
        state = (
            registrant_result[
                "state"
            ]
        )

        registrants = (
            registrant_result[
                "registrants"
            ]
        )

        registrant_columns = (
            st.columns(4)
        )

        registrant_columns[0].metric(
            "HTTP",
            registrant_response.status_code,
        )

        registrant_columns[1].metric(
            "Valid JSON",
            (
                "Yes"
                if registrant_result[
                    "json"
                ]
                is not None
                else
                "No"
            ),
        )

        registrant_columns[2].metric(
            "Total reported",
            state.get(
                "totalItems",
                "Not found",
            ),
        )

        registrant_columns[3].metric(
            "Items extracted",
            len(
                registrants
            ),
        )

        st.write(
            "**Final URL:**"
        )

        st.code(
            registrant_response.url,
            language=None,
        )

        if (
            registrant_response.status_code
            == 200
        ):
            st.success(
                "ECHA returned the registrants "
                "successfully."
            )

        elif (
            registrant_response.status_code
            == 403
        ):
            st.error(
                "ECHA returned HTTP 403 for "
                "the registrants request."
            )

        elif (
            registrant_response.status_code
            == 404
        ):
            st.error(
                "ECHA returned HTTP 404 for "
                "the registrants request."
            )

        elif (
            registrant_response.status_code
            == 429
        ):
            st.error(
                "ECHA returned HTTP 429. "
                "The registrants request was "
                "rate limited."
            )

        elif (
            registrant_response.status_code
            >= 500
        ):
            st.error(
                "ECHA returned server error "
                f"HTTP {registrant_response.status_code}."
            )

        elif (
            registrant_response.status_code
            >= 400
        ):
            st.error(
                "ECHA returned HTTP "
                f"{registrant_response.status_code}."
            )

        if (
            loaded_rml_id
            ==
            EXPECTED_RML_ID
            and
            state.get(
                "totalItems"
            )
            ==
            EXPECTED_REGISTRANTS
        ):
            st.success(
                "Final benchmark match: "
                "42 registrants found for BHT."
            )

        st.subheader(
            "5. Registrants"
        )

        if registrants:
            registrants_dataframe = (
                pd.DataFrame(
                    registrants
                )
            )

            status_options = sorted(
                value
                for value
                in registrants_dataframe[
                    "Status"
                ]
                .dropna()
                .unique()
                .tolist()
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

            filtered_dataframe = (
                registrants_dataframe.copy()
            )

            if selected_statuses:
                filtered_dataframe = (
                    filtered_dataframe[
                        filtered_dataframe[
                            "Status"
                        ]
                        .isin(
                            selected_statuses
                        )
                    ]
                )

            else:
                filtered_dataframe = (
                    filtered_dataframe.iloc[
                        0:0
                    ]
                )

            if not show_confidential:
                hidden_names = {
                    "[Confidential]",
                    (
                        "Only representative "
                        "(No publishable name)"
                    ),
                }

                filtered_dataframe = (
                    filtered_dataframe[
                        ~filtered_dataframe[
                            "Registrant"
                        ]
                        .isin(
                            hidden_names
                        )
                    ]
                )

            filtered_dataframe = (
                filtered_dataframe
                .reset_index(
                    drop=True
                )
            )

            st.dataframe(
                filtered_dataframe,
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                label=(
                    "Download registrants as CSV"
                ),
                data=(
                    filtered_dataframe
                    .to_csv(
                        index=False
                    )
                    .encode(
                        "utf-8-sig"
                    )
                ),
                file_name=(
                    "ECHA_registrants_"
                    f"{loaded_rml_id}.csv"
                ),
                mime="text/csv",
            )

        else:
            st.warning(
                "No registrants were returned "
                "for the selected substance."
            )

        with st.expander(
            "6. Complete registrants JSON",
            expanded=False,
        ):
            if (
                registrant_result[
                    "json"
                ]
                is not None
            ):
                st.json(
                    registrant_result[
                        "json"
                    ]
                )

            else:
                st.write(
                    "No valid registrants "
                    "JSON was returned."
                )


# --------------------------------------------------
# NO RESULTS MESSAGE
# --------------------------------------------------
elif (
    search_debug
    is not None
    and
    not search_results
):
    st.warning(
        "No ECHA substances were found "
        "for this search."
    )


# --------------------------------------------------
# RAW SUBSTANCE SEARCH RESPONSE
# --------------------------------------------------
if search_debug is not None:
    with st.expander(
        "Raw substance search response",
        expanded=False,
    ):
        if (
            search_debug[
                "json"
            ]
            is not None
        ):
            st.json(
                search_debug[
                    "json"
                ]
            )

        elif (
            search_debug[
                "response"
            ]
            is not None
        ):
            st.code(
                search_debug[
                    "response"
                ]
                .text[
                    :30000
                ],
                language=None,
            )

        else:
            st.write(
                "No response was received."
            )