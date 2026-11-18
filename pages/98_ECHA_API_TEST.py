import json
import re
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="ECHA Registrants API Test",
    page_icon="🔎",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_REGISTRANTS_API_TEST_V11"


# --------------------------------------------------
# TEST SUBSTANCE
# --------------------------------------------------
CAS_NUMBER = "128-37-0"
EC_NUMBER = "204-881-4"
RML_ID = "100.004.439"

EXPECTED_REGISTRANTS = 42


# --------------------------------------------------
# ECHA RESOURCES
# --------------------------------------------------
ECHA_BASE_URL = "https://chem.echa.europa.eu"

OVERVIEW_URL = (
    f"{ECHA_BASE_URL}/"
    f"{RML_ID}/overview"
)

RUNTIME_CONFIG_URL = (
    f"{ECHA_BASE_URL}/"
    "mfe-config/mfe-config.json"
)

DOSSIER_LIST_WEB_COMPONENTS_URL = (
    f"{ECHA_BASE_URL}/"
    "dossierList/"
    "web-components-NIMFYLDU.js"
)


# --------------------------------------------------
# REQUEST SETTINGS
# --------------------------------------------------
CONNECT_TIMEOUT_SECONDS = 20
READ_TIMEOUT_SECONDS = 90

REQUEST_HEADERS = {
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
# HTTP SESSION
# --------------------------------------------------
def create_session():
    session = requests.Session()

    session.headers.update(
        REQUEST_HEADERS
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
            {"GET"}
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
# SAFE GET
# --------------------------------------------------
def safe_get(
    session,
    url,
    params=None,
    referer=None,
):
    headers = {}

    if referer:
        headers[
            "Referer"
        ] = referer

    try:
        response = session.get(
            url,
            params=params,
            headers=(
                headers
                or None
            ),
            timeout=(
                CONNECT_TIMEOUT_SECONDS,
                READ_TIMEOUT_SECONDS,
            ),
            allow_redirects=True,
        )

        return response, None

    except requests.Timeout as error:
        return (
            None,
            f"Request timed out: {error}",
        )

    except requests.RequestException as error:
        return (
            None,
            f"Request failed: {error}",
        )


# --------------------------------------------------
# SAFE JSON PARSER
# --------------------------------------------------
def parse_json_response(
    response,
):
    if response is None:
        return None

    try:
        return response.json()

    except ValueError:
        return None


# --------------------------------------------------
# NORMALISE TEXT
# --------------------------------------------------
def normalise_text(
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
# RECURSIVE JSON KEY LOOKUP
# --------------------------------------------------
def find_json_key(
    value,
    wanted_key,
):
    wanted_key_lower = (
        wanted_key.lower()
    )

    if isinstance(
        value,
        dict,
    ):
        for key, nested_value in (
            value.items()
        ):
            if (
                str(key).lower()
                ==
                wanted_key_lower
            ):
                return nested_value

        for nested_value in (
            value.values()
        ):
            result = find_json_key(
                nested_value,
                wanted_key,
            )

            if result is not None:
                return result

    elif isinstance(
        value,
        list,
    ):
        for item in value:
            result = find_json_key(
                item,
                wanted_key,
            )

            if result is not None:
                return result

    return None


# --------------------------------------------------
# SOURCE CONTEXT
# --------------------------------------------------
def source_context(
    text,
    search_text,
    before=1000,
    after=2500,
):
    if not text:
        return ""

    position = (
        text.lower()
        .find(
            search_text.lower()
        )
    )

    if position < 0:
        return ""

    start = max(
        0,
        position - before,
    )

    end = min(
        len(text),
        (
            position
            + len(search_text)
            + after
        ),
    )

    return text[
        start:end
    ]


# --------------------------------------------------
# EXTRACT DEFAULT REGISTRANTS API BASE
# --------------------------------------------------
def extract_default_api_base(
    javascript_text,
):
    if not javascript_text:
        return ""

    patterns = [
        (
            r'["\']'
            r'([^"\']*/api-dossier-list/v\d+/)'
            r'["\']'
        ),
        (
            r'["\']'
            r'(api-dossier-list/v\d+/)'
            r'["\']'
        ),
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            javascript_text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        value = (
            match.group(1)
            .replace(
                "\\/",
                "/",
            )
            .strip()
        )

        if value:
            return value

    return ""


# --------------------------------------------------
# EXTRACT REGISTRANTS SUFFIX
# --------------------------------------------------
def extract_registrants_suffix(
    javascript_text,
):
    result = {
        "suffix": "",
        "context": "",
        "matched_expression": "",
    }

    if not javascript_text:
        return result

    patterns = [
        (
            r'registrantsUrl\s*='
            r'\s*this\.registrantsApiUrl'
            r'\.concat\(\s*'
            r'["\']([^"\']+)["\']'
            r'\s*\)'
        ),
        (
            r'registrantsApiUrl'
            r'[^;]{0,1000}?'
            r'\.concat\(\s*'
            r'["\']([^"\']+)["\']'
            r'\s*\)'
        ),
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            javascript_text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        suffix = (
            match.group(1)
            .replace(
                "\\/",
                "/",
            )
            .strip()
        )

        if not suffix:
            continue

        result[
            "suffix"
        ] = suffix

        result[
            "matched_expression"
        ] = (
            match.group(0)
        )

        result[
            "context"
        ] = (
            javascript_text[
                max(
                    0,
                    match.start() - 1000,
                ):
                min(
                    len(
                        javascript_text
                    ),
                    match.end() + 2200,
                )
            ]
        )

        return result

    result[
        "context"
    ] = source_context(
        javascript_text,
        "registrantsUrl",
    )

    return result


# --------------------------------------------------
# BUILD ABSOLUTE API BASE
# --------------------------------------------------
def build_absolute_api_base(
    api_base,
):
    if not api_base:
        return ""

    clean_base = (
        str(
            api_base
        )
        .replace(
            "\\/",
            "/",
        )
        .strip()
    )

    absolute_base = urljoin(
        (
            ECHA_BASE_URL
            + "/"
        ),
        clean_base,
    )

    if not absolute_base.endswith(
        "/"
    ):
        absolute_base += "/"

    return absolute_base


# -------------------------------------# BUILD REGISTRANTS ENDPOINT
# --------------------------------------------------
def build_registrants_endpoint(
    api_base,
    suffix,
):
    absolute_base = (
        build_absolute_api_base(
            api_base
        )
    )

    if not absolute_base:
        return ""

    if not suffix:
        return ""

    clean_suffix = (
        str(
            suffix
        )
        .replace(
            "\\/",
            "/",
        )
        .strip()
        .lstrip(
            "/"
        )
    )

    if not clean_suffix:
        return ""

    return urljoin(
        absolute_base,
        clean_suffix,
    )


# --------------------------------------------------
# FIND ALL LISTS IN JSON
# --------------------------------------------------
def find_json_lists(
    value,
    path="root",
    results=None,
):
    if results is None:
        results = []

    if isinstance(
        value,
        list,
    ):
        results.append(
            {
                "path": (
                    path
                ),
                "length": len(
                    value
                ),
                "items": (
                    value
                ),
            }
        )

        for index, item in enumerate(
            value
        ):
            find_json_lists(
                value=item,
                path=(
                    f"{path}"
                    f"[{index}]"
                ),
                results=results,
            )

    elif isinstance(
        value,
        dict,
    ):
        for key, nested_value in (
            value.items()
        ):
            find_json_lists(
                value=nested_value,
                path=(
                    f"{path}.{key}"
                ),
                results=results,
            )

    return results


# --------------------------------------------------
# SCORE JSON LIST
# --------------------------------------------------
def score_json_list(
    candidate,
):
    items = candidate.get(
        "items"
    )

    if not isinstance(
        items,
        list,
    ):
        return -1

    if not items:
        return 0

    score = len(
        items
    )

    relevant_keys = {
        "name",
        "address",
        "status",
        "registrantname",
        "registrationstatus",
        "assetownername",
        "legalentityname",
    }

    dictionary_items = [
        item
        for item in items[:10]
        if isinstance(
            item,
            dict,
        )
    ]

    for item in dictionary_items:
        keys = {
            str(key).lower()
            for key in item.keys()
        }

        score += (
            len(
                keys
                & relevant_keys
            )
            * 20
        )

    candidate_path = (
        candidate.get(
            "path",
            "",
        )
        .lower()
    )

    if any(
        keyword in candidate_path
        for keyword in (
            "registrant",
            "item",
            "result",
            "content",
            "data",
        )
    ):
        score += 50

    return score


# --------------------------------------------------
# SELECT RESULT LIST
# --------------------------------------------------
def select_result_list(
    json_body,
):
    if isinstance(
        json_body,
        list,
    ):
        return {
            "path": (
                "root"
            ),
            "items": (
                json_body
            ),
        }

    if not isinstance(
        json_body,
        (
            dict,
            list,
        ),
    ):
        return {
            "path": "",
            "items": [],
        }

    # Common result structures first.
    if isinstance(
        json_body,
        dict,
    ):
        preferred_keys = [
            "items",
            "results",
            "content",
            "registrants",
            "data",
        ]

        for key in preferred_keys:
            value = (
                json_body.get(
                    key
                )
            )

            if isinstance(
                value,
                list,
            ):
                return {
                    "path": (
                        f"root.{key}"
                    ),
                    "items": (
                        value
                    ),
                }

    lists = find_json_lists(
        json_body
    )

    if not lists:
        return {
            "path": "",
            "items": [],
        }

    scored_lists = [
        (
            score_json_list(
                candidate
            ),
            candidate,
        )
        for candidate
        in lists
    ]

    scored_lists.sort(
        key=lambda row: row[0],
        reverse=True,
    )

    best_score, best_candidate = (
        scored_lists[0]
    )

    if best_score <= 0:
        return {
            "path": "",
            "items": [],
        }

    return {
        "path": (
            best_candidate[
                "path"
            ]
        ),
        "items": (
            best_candidate[
                "items"
            ]
        ),
    }


# --------------------------------------------------
# RECURSIVE FIELD LOOKUP
# --------------------------------------------------
def find_field(
    value,
    possible_keys,
):
    possible_keys = {
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
                in possible_keys
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
            result = find_field(
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
            result = find_field(
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
# NORMALISE REGISTRANT
# --------------------------------------------------
def normalise_registrant(
    item,
):
    if not isinstance(
        item,
        dict,
    ):
        return {
            "Name": (
                normalise_text(
                    item
                )
            ),
            "Address": "",
            "Status": "",
            "ID": "",
        }

    name = find_field(
        item,
        {
            "name",
            "registrantName",
            "registrant-name",
            "assetOwnerName",
            "legalEntityName",
            "organisationName",
            "organizationName",
            "companyName",
        },
    )

    address = find_field(
        item,
        {
            "address",
            "registrantAddress",
            "assetOwnerAddress",
            "fullAddress",
            "formattedAddress",
        },
    )

    status = find_field(
        item,
        {
            "status",
            "registrationStatus",
            "registrantStatus",
            "assetOwnerStatus",
        },
    )

    identifier = find_field(
        item,
        {
            "id",
            "uuid",
            "externalId",
            "assetOwnerId",
            "legalEntityId",
        },
    )

    return {
        "Name": (
            normalise_text(
                name
            )
        ),
        "Address": (
            normalise_text(
                address
            )
        ),
        "Status": (
            normalise_text(
                status
            )
        ),
        "ID": (
            normalise_text(
                identifier
            )
        ),
    }


# --------------------------------------------------
# FIND TOTAL COUNT
# --------------------------------------------------
def find_total_count(
    value,
):
    total_keys = {
        "total",
        "totalcount",
        "totalitems",
        "totalelements",
        "totalresults",
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
                in total_keys
                and
                isinstance(
                    nested_value,
                    (
                        int,
                        float,
                    ),
                )
            ):
                return int(
                    nested_value
                )

        for nested_value in (
            value.values()
        ):
            result = find_total_count(
                nested_value
            )

            if result is not None:
                return result

    elif isinstance(
        value,
        list,
    ):
        for item in value:
            result = find_total_count(
                item
            )

            if result is not None:
                return result

    return None


# --------------------------------------------------
# KNOWN REGISTRANT CHECK
# --------------------------------------------------
def find_known_registrants(
    json_body,
):
    if json_body is None:
        return []

    try:
        text = json.dumps(
            json_body,
            ensure_ascii=False,
        ).lower()

    except Exception:
        text = str(
            json_body
        ).lower()

    known_names = [
        "3m belgium",
        "afton chemical",
        "basf se",
    ]

    return [
        name
        for name
        in known_names
        if name in text
    ]


# --------------------------------------------------
# RUN TEST
# --------------------------------------------------
def run_test():
    session = (
        create_session()
    )

    # ----------------------------------
    # LOAD RUNTIME CONFIG
    # ----------------------------------
    runtime_response, runtime_error = (
        safe_get(
            session=session,
            url=RUNTIME_CONFIG_URL,
            referer=OVERVIEW_URL,
        )
    )

    runtime_json = (
        parse_json_response(
            runtime_response
        )
    )

    runtime_api_base = ""

    if runtime_json is not None:
        runtime_value = (
            find_json_key(
                runtime_json,
                "registrantsApiUrl",
            )
        )

        if runtime_value:
            runtime_api_base = (
                normalise_text(
                    runtime_value
                )
            )

    # ----------------------------------
    # LOAD DOSSIER LIST COMPONENT
    # ----------------------------------
    javascript_response, javascript_error = (
        safe_get(
            session=session,
            url=(
                DOSSIER_LIST_WEB_COMPONENTS_URL
            ),
            referer=OVERVIEW_URL,
        )
    )

    javascript_text = ""

    if javascript_response is not None:
        javascript_text = (
            javascript_response.text
            or ""
        )

    # ----------------------------------
    # EXTRACT BASE AND SUFFIX
    # ----------------------------------
    default_api_base = (
        extract_default_api_base(
            javascript_text
        )
    )

    suffix_result = (
        extract_registrants_suffix(
            javascript_text
        )
    )

    suffix = (
        suffix_result[
            "suffix"
        ]
    )

    final_api_base = (
        runtime_api_base
        or
        default_api_base
    )

    endpoint = (
        build_registrants_endpoint(
            api_base=(
                final_api_base
            ),
            suffix=(
                suffix
            ),
        )
    )

    # ----------------------------------
    # API PARAMETERS
    # ----------------------------------
    api_params = {
        "rmlId": (
            RML_ID
        ),
        "pageIndex": 1,
        "pageSize": 100,
    }

    api_response = None
    api_error = None
    api_json = None

    # ----------------------------------
    # ONLY CALL IF EXTRACTED FROM ECHA
    # ----------------------------------
    if (
        endpoint
        and
        suffix.lower()
        ==
        "registrants"
        and
        "api-dossier-list"
        in final_api_base.lower()
    ):
        api_response, api_error = (
            safe_get(
                session=session,
                url=endpoint,
                params=api_params,
                referer=OVERVIEW_URL,
            )
        )

        api_json = (
            parse_json_response(
                api_response
            )
        )

    # ----------------------------------
    # PROCESS RESPONSE
    # ----------------------------------
    selected_list = {
        "path": "",
        "items": [],
    }

    registrants = []
    total_count = None
    known_registrants = []

    if api_json is not None:
        selected_list = (
            select_result_list(
                api_json
            )
        )

        registrants = [
            normalise_registrant(
                item
            )
            for item
            in selected_list[
                "items"
            ]
        ]

        total_count = (
            find_total_count(
                api_json
            )
        )

        known_registrants = (
            find_known_registrants(
                api_json
            )
        )

    return {
        "runtime_status": (
            runtime_response.status_code
            if runtime_response
            is not None
            else None
        ),
        "runtime_content_type": (
            runtime_response.headers.get(
                "content-type",
                "",
            )
            if runtime_response
            is not None
            else ""
        ),
        "runtime_json": (
            runtime_json
        ),
        "runtime_error": (
            runtime_error
        ),
        "javascript_status": (
            javascript_response.status_code
            if javascript_response
            is not None
            else None
        ),
        "javascript_content_type": (
            javascript_response.headers.get(
                "content-type",
                "",
            )
            if javascript_response
            is not None
            else ""
        ),
        "javascript_bytes": (
            len(
                javascript_response.content
            )
            if javascript_response
            is not None
            else 0
        ),
        "javascript_error": (
            javascript_error
        ),
        "runtime_api_base": (
            runtime_api_base
        ),
        "default_api_base": (
            default_api_base
        ),
        "final_api_base": (
            final_api_base
        ),
        "suffix": (
            suffix
        ),
        "matched_expression": (
            suffix_result[
                "matched_expression"
            ]
        ),
        "source_context": (
            suffix_result[
                "context"
            ]
        ),
        "endpoint": (
            endpoint
        ),
        "api_params": (
            api_params
        ),
        "api_status": (
            api_response.status_code
            if api_response
            is not None
            else None
        ),
        "api_final_url": (
            api_response.url
            if api_response
            is not None
            else ""
        ),
        "api_content_type": (
            api_response.headers.get(
                "content-type",
                "",
            )
            if api_response
            is not None
            else ""
        ),
        "api_bytes": (
            len(
                api_response.content
            )
            if api_response
            is not None
            else 0
        ),
        "api_text": (
            api_response.text
            if api_response
            is not None
            else ""
        ),
        "api_json": (
            api_json
        ),
        "api_error": (
            api_error
        ),
        "selected_path": (
            selected_list[
                "path"
            ]
        ),
        "registrants": (
            registrants
        ),
        "total_count": (
            total_count
        ),
        "known_registrants": (
            known_registrants
        ),
    }


# --------------------------------------------------
# STREAMLIT INTERFACE
# --------------------------------------------------
st.title(
    "ECHA Registrants API Test"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.write(
    "V11 reconstructs the registrants API "
    "request from the actual ECHA dossierList "
    "micro-frontend."
)

st.info(
    "The API request is only sent when the code "
    "confirms both the dossier-list API base and "
    'the "registrants" endpoint suffix.'
)


# --------------------------------------------------
# TEST SUBSTANCE DISPLAY
# --------------------------------------------------
st.subheader(
    "Known test substance"
)

metric_columns = (
    st.columns(4)
)

metric_columns[0].metric(
    "CAS",
    CAS_NUMBER,
)

metric_columns[1].metric(
    "EC",
    EC_NUMBER,
)

metric_columns[2].metric(
    "rmlId",
    RML_ID,
)

metric_columns[3].metric(
    "Expected registrants",
    EXPECTED_REGISTRANTS,
)


# --------------------------------------------------
# SOURCE
# --------------------------------------------------
st.subheader(
    "Source implementation"
)

st.code(
    DOSSIER_LIST_WEB_COMPONENTS_URL,
    language=None,
)


# --------------------------------------------------
# RUN
# --------------------------------------------------
if st.button(
    "Test extracted registrants API",
    type="primary",
):
    with st.spinner(
        "Extracting and testing "
        "the registrants API..."
    ):
        result = (
            run_test()
        )

    st.success(
        "Test completed."
    )

    # ----------------------------------
    # 1. EXTRACTION
    # ----------------------------------
    st.subheader(
        "1. Extracted API configuration"
    )

    config_rows = [
        {
            "Setting": (
                "Runtime registrantsApiUrl"
            ),
            "Value": (
                result[
                    "runtime_api_base"
                ]
            ),
        },
        {
            "Setting": (
                "JavaScript default API base"
            ),
            "Value": (
                result[
                    "default_api_base"
                ]
            ),
        },
        {
            "Setting": (
                "Selected API base"
            ),
            "Value": (
                result[
                    "final_api_base"
                ]
            ),
        },
        {
            "Setting": (
                "Extracted suffix"
            ),
            "Value": (
                result[
                    "suffix"
                ]
            ),
        },
        {
            "Setting": (
                "Constructed endpoint"
            ),
            "Value": (
                result[
                    "endpoint"
                ]
            ),
        },
    ]

    st.dataframe(
        pd.DataFrame(
            config_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    # ----------------------------------
    # 2. MATCH
    # ----------------------------------
    st.subheader(
        "2. JavaScript expression"
    )

    if result[
        "matched_expression"
    ]:
        st.success(
            "The registrants endpoint "
            "construction was found."
        )

        st.code(
            result[
                "matched_expression"
            ],
            language="javascript",
        )

    else:
        st.warning(
            "The exact registrants endpoint "
            "expression was not matched."
        )

        if result[
            "source_context"
        ]:
            st.code(
                result[
                    "source_context"
                ],
                language="javascript",
            )

    # ----------------------------------
    # 3. API REQUEST
    # ----------------------------------
    st.subheader(
        "3. API request"
    )

    api_columns = (
        st.columns(4)
    )

    api_columns[0].metric(
        "HTTP",
        (
            result[
                "api_status"
            ]
            if result[
                "api_status"
            ]
            is not None
            else
            "Not sent"
        ),
    )

    api_columns[1].metric(
        "Response bytes",
        result[
            "api_bytes"
        ],
    )

    api_columns[2].metric(
        "Valid JSON",
        (
            "Yes"
            if result[
                "api_json"
            ]
            is not None
            else
            "No"
        ),
    )

    api_columns[3].metric(
        "Total reported",
        (
            result[
                "total_count"
            ]
            if result[
                "total_count"
            ]
            is not None
            else
            "Not found"
        ),
    )

    st.write(
        "**Final request URL:**"
    )

    st.code(
        result[
            "api_final_url"
        ]
        or
        result[
            "endpoint"
        ]
        or
        "No endpoint constructed",
        language=None,
    )

    st.write(
        "**Request parameters:**"
    )

    st.json(
        result[
            "api_params"
        ]
    )

    if result[
        "api_content_type"
    ]:
        st.write(
            "**Content-Type:** "
            f"{result['api_content_type']}"
        )

    if result[
        "api_error"
    ]:
        st.error(
            result[
                "api_error"
            ]
        )

    # ----------------------------------
    # RESPONSE STATUS
    # ----------------------------------
    if (
        result[
            "api_status"
        ]
        == 200
        and
        result[
            "api_json"
        ]
        is not None
    ):
        st.success(
            "ECHA returned HTTP 200 "
            "with valid JSON."
        )

    elif (
        result[
            "api_status"
        ]
        == 403
    ):
        st.error(
            "ECHA returned HTTP 403. "
            "The endpoint was reached but "
            "access was refused."
        )

    elif (
        result[
            "api_status"
        ]
        == 404
    ):
        st.error(
            "ECHA returned HTTP 404. "
            "The constructed endpoint was "
            "not found."
        )

    elif (
        result[
            "api_status"
        ]
        == 429
    ):
        st.error(
            "ECHA returned HTTP 429. "
            "The request was rate limited."
        )

    elif (
        result[
            "api_status"
        ]
        is not None
        and
        result[
            "api_status"
        ]
        >= 400
    ):
        st.error(
            "ECHA returned HTTP "
            f"{result['api_status']}."
        )

    # ----------------------------------
    # 4. BENCHMARK
    # ----------------------------------
    st.subheader(
        "4. Benchmark check"
    )

    benchmark_columns = (
        st.columns(3)
    )

    benchmark_columns[0].metric(
        "Expected",
        EXPECTED_REGISTRANTS,
    )

    benchmark_columns[1].metric(
        "API total",
        (
            result[
                "total_count"
            ]
            if result[
                "total_count"
            ]
            is not None
            else
            "Unknown"
        ),
    )

    benchmark_columns[2].metric(
        "Rows extracted",
        len(
            result[
                "registrants"
            ]
        ),
    )

    if (
        result[
            "total_count"
        ]
        ==
        EXPECTED_REGISTRANTS
    ):
        st.success(
            "Exact benchmark match: "
            "the API reports 42 registrants."
        )

    if result[
        "known_registrants"
    ]:
        st.write(
            "**Known benchmark names found:**"
        )

        st.write(
            ", ".join(
                result[
                    "known_registrants"
                ]
            )
        )

    # ----------------------------------
    # 5. REGISTRANTS
    # ----------------------------------
    st.subheader(
        "5. Registrants"
    )

    st.write(
        "**Selected JSON list path:**"
    )

    st.code(
        result[
            "selected_path"
        ]
        or
        "No list selected",
        language=None,
    )

    registrants = (
        result[
            "registrants"
        ]
    )

    if registrants:
        dataframe = (
            pd.DataFrame(
                registrants
            )
        )

        useful_columns = [
            column
            for column
            in dataframe.columns
            if (
                dataframe[
                    column
                ]
                .astype(str)
                .str.strip()
                .ne("")
                .any()
            )
        ]

        if useful_columns:
            dataframe = (
                dataframe[
                    useful_columns
                ]
            )

        st.dataframe(
            dataframe,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No registrant rows "
            "were extracted."
        )

    # ----------------------------------
    # 6. RAW JSON
    # ----------------------------------
    with st.expander(
        "6. Complete API JSON",
        expanded=False,
    ):
        if (
            result[
                "api_json"
            ]
            is not None
        ):
            st.json(
                result[
                    "api_json"
                ]
            )

        else:
            st.write(
                "No valid JSON returned."
            )

    # ----------------------------------
    # 7. RAW RESPONSE
    # ----------------------------------
    with st.expander(
        "7. Raw API response",
        expanded=False,
    ):
        if result[
            "api_text"
        ]:
            st.code(
                result[
                    "api_text"
                ][:20000],
                language=None,
            )

        else:
            st.write(
                "No API response body."
            )

    # ----------------------------------
    # 8. RUNTIME CONFIG
    # ----------------------------------
    with st.expander(
        "8. Runtime configuration",
        expanded=False,
    ):
        if (
            result[
                "runtime_json"
            ]
            is not None
        ):
            st.json(
                result[
                    "runtime_json"
                ]
            )

        else:
            st.write(
                "No runtime configuration JSON."
            )