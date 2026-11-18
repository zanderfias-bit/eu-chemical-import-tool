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
CODE_VERSION = "ECHA_REGISTRANTS_API_TEST_V10"


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
        "application/javascript,"
        "text/javascript,"
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

    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=retry
        ),
    )

    return session


# --------------------------------------------------
# SAFE GET REQUEST
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
# FIND SOURCE CONTEXT
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
# EXTRACT DEFAULT REGISTRANTS API URL
# --------------------------------------------------
def extract_default_registrants_api_url(
    javascript_text,
):
    if not javascript_text:
        return ""

    patterns = [
        (
            r"registrantsApiUrl"
            r"\s*="
            r"[^;]{0,500}?"
            r"[\"']"
            r"([^\"']*api-dossier-list[^\"']*)"
            r"[\"']"
        ),
        (
            r"[\"']"
            r"([^\"']*/api-dossier-list/v\d+/)"
            r"[\"']"
        ),
        (
            r"[\"']"
            r"([^\"']*api-dossier-list/v\d+/)"
            r"[\"']"
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
# EXTRACT CONCAT ARGUMENT
# --------------------------------------------------
def extract_registrants_concat_argument(
    javascript_text,
):
    if not javascript_text:
        return {
            "raw_argument": "",
            "literal_value": "",
            "context": "",
        }

    patterns = [
        (
            r"registrantsUrl"
            r"\s*="
            r"this\.registrantsApiUrl"
            r"\.concat\("
            r"([^)]{0,500})"
            r"\)"
        ),
        (
            r"registrantsUrl"
            r"\s*="
            r"[^;]{0,300}?"
            r"\.concat\("
            r"([^)]{0,500})"
            r"\)"
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

        raw_argument = (
            match.group(1)
            .strip()
        )

        literal_match = re.fullmatch(
            r"""[^"']+["']""",
            raw_argument,
        )

        literal_value = ""

        if literal_match:
            literal_value = (
                literal_match.group(1)
                .replace(
                    "\\/",
                    "/",
                )
                .strip()
            )

        return {
            "raw_argument": (
                raw_argument
            ),
            "literal_value": (
                literal_value
            ),
            "context": (
                javascript_text[
                    max(
                        0,
                        match.start() - 1200,
                    ):
                    min(
                        len(
                            javascript_text
                        ),
                        match.end() + 2500,
                    )
                ]
            ),
        }

    return {
        "raw_argument": "",
        "literal_value": "",
        "context": source_context(
            javascript_text,
            "registrantsUrl",
        ),
    }


# --------------------------------------------------
# EXTRACT INTERESTING STRING LITERALS
# --------------------------------------------------
def extract_registrant_strings(
    javascript_text,
):
    if not javascript_text:
        return []

    quoted_strings = re.findall(
        r"""[^"']{1,500}["']""",
        javascript_text,
    )

    keywords = {
        "registrant",
        "asset-owner",
        "assetowner",
        "api-dossier-list",
        "pageindex",
        "pagesize",
        "rmlid",
    }

    results = []
    seen = set()

    for value in quoted_strings:
        clean_value = (
            value
            .replace(
                "\\/",
                "/",
            )
            .strip()
        )

        lower_value = (
            clean_value.lower()
        )

        if not any(
            keyword in lower_value
            for keyword in keywords
        ):
            continue

        if clean_value in seen:
            continue

        seen.add(
            clean_value
        )

        results.append(
            clean_value
        )

    return results


# --------------------------------------------------
# BUILD API ENDPOINT
# --------------------------------------------------
def build_registrants_endpoint(
    api_base,
    suffix,
):
    if not api_base:
        return ""

    if not suffix:
        return ""

    clean_base = (
        api_base
        .replace(
            "\\/",
            "/",
        )
        .strip()
    )

    clean_suffix = (
        suffix
        .replace(
            "\\/",
            "/",
        )
        .strip()
    )

    if not clean_suffix:
        return ""

    absolute_base = urljoin(
        ECHA_BASE_URL,
        clean_base,
    )

    if not absolute_base.endswith(
        "/"
    ):
        absolute_base = (
            absolute_base
            + "/"
        )

    clean_suffix = (
        clean_suffix.lstrip(
            "/"
        )
    )

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
# SCORE CANDIDATE LIST
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
# SELECT MOST LIKELY RESULT LIST
# --------------------------------------------------
def select_result_list(
    json_body,
):
    if isinstance(
        json_body,
        list,
    ):
        return {
            "path": "root",
            "items": json_body,
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
        for candidate in lists
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
            result = (
                find_total_count(
                    nested_value
                )
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
# RUN COMPLETE TEST
# --------------------------------------------------
def run_test():
    session = create_session()

    # ----------------------------------
    # RUNTIME CONFIGURATION
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

    runtime_registrants_api_url = ""

    if runtime_json is not None:
        runtime_value = find_json_key(
            runtime_json,
            "registrantsApiUrl",
        )

        if runtime_value is not None:
            runtime_registrants_api_url = (
                normalise_text(
                    runtime_value
                )
            )

    # ----------------------------------
    # DOSSIER LIST JAVASCRIPT
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

    default_api_url = (
        extract_default_registrants_api_url(
            javascript_text
        )
    )

    concat_result = (
        extract_registrants_concat_argument(
            javascript_text
        )
    )

    registrant_strings = (
        extract_registrant_strings(
            javascript_text
        )
    )

    final_api_base = (
        runtime_registrants_api_url
        or
        default_api_url
    )

    endpoint = (
        build_registrants_endpoint(
            api_base=(
                final_api_base
            ),
            suffix=(
                concat_result[
                    "literal_value"
                ]
            ),
        )
    )

    # ----------------------------------
    # ONLY REQUEST WHEN EXACTLY EXTRACTED
    # ----------------------------------
    api_response = None
    api_error = None
    api_json = None

    api_params = {
        "rmlId": RML_ID,
        "pageIndex": 1,
        "pageSize": 100,
    }

    if endpoint:
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

    selected_list = {
        "path": "",
        "items": [],
    }

    registrants = []

    total_count = None

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
            for item in (
                selected_list[
                    "items"
                ]
            )
        ]

        total_count = (
            find_total_count(
                api_json
            )
        )

    return {
        "runtime": {
            "status": (
                runtime_response.status_code
                if runtime_response
                is not None
                else None
            ),
            "content_type": (
                runtime_response.headers.get(
                    "content-type",
                    "",
                )
                if runtime_response
                is not None
                else ""
            ),
            "bytes": (
                len(
                    runtime_response.content
                )
                if runtime_response
                is not None
                else 0
            ),
            "json": (
                runtime_json
            ),
            "error": (
                runtime_error
            ),
        },
        "javascript": {
            "status": (
                javascript_response.status_code
                if javascript_response
                is not None
                else None
            ),
            "content_type": (
                javascript_response.headers.get(
                    "content-type",
                    "",
                )
                if javascript_response
                is not None
                else ""
            ),
            "bytes": (
                len(
                    javascript_response.content
                )
                if javascript_response
                is not None
                else 0
            ),
            "error": (
                javascript_error
            ),
        },
        "runtime_api_base": (
            runtime_registrants_api_url
        ),
        "default_api_base": (
            default_api_url
        ),
        "final_api_base": (
            final_api_base
        ),
        "concat_raw_argument": (
            concat_result[
                "raw_argument"
            ]
        ),
        "concat_literal_value": (
            concat_result[
                "literal_value"
            ]
        ),
        "concat_context": (
            concat_result[
                "context"
            ]
        ),
        "registrant_strings": (
            registrant_strings
        ),
        "endpoint": (
            endpoint
        ),
        "api_params": (
            api_params
        ),
        "api": {
            "status": (
                api_response.status_code
                if api_response
                is not None
                else None
            ),
            "final_url": (
                api_response.url
                if api_response
                is not None
                else ""
            ),
            "content_type": (
                api_response.headers.get(
                    "content-type",
                    "",
                )
                if api_response
                is not None
                else ""
            ),
            "bytes": (
                len(
                    api_response.content
                )
                if api_response
                is not None
                else 0
            ),
            "text": (
                api_response.text
                if api_response
                is not None
                else ""
            ),
            "json": (
                api_json
            ),
            "error": (
                api_error
            ),
        },
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
    "V10 extracts the exact registrants endpoint "
    "construction from the ECHA dossierList "
    "micro-frontend."
)

st.info(
    "An API request is only performed when both "
    "the API base and the concatenated endpoint "
    "suffix are extracted from actual ECHA code."
)


# --------------------------------------------------
# TEST SUBSTANCE
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
# SOURCE RESOURCE
# --------------------------------------------------
st.subheader(
    "Source resource"
)

st.code(
    DOSSIER_LIST_WEB_COMPONENTS_URL,
    language=None,
)


# --------------------------------------------------
# RUN
# --------------------------------------------------
if st.button(
    "Extract and test registrants endpoint",
    type="primary",
):
    with st.spinner(
        "Analysing the ECHA dossierList code..."
    ):
        result = (
            run_test()
        )

    st.success(
        "Analysis completed."
    )

    # ----------------------------------
    # 1. SOURCE RESPONSES
    # ----------------------------------
    st.subheader(
        "1. Source responses"
    )

    source_rows = [
        {
            "Resource": (
                "Runtime configuration"
            ),
            "HTTP": (
                result[
                    "runtime"
                ][
                    "status"
                ]
            ),
            "Content-Type": (
                result[
                    "runtime"
                ][
                    "content_type"
                ]
            ),
            "Bytes": (
                result[
                    "runtime"
                ][
                    "bytes"
                ]
            ),
            "Error": (
                result[
                    "runtime"
                ][
                    "error"
                ]
            ),
        },
        {
            "Resource": (
                "dossierList web components"
            ),
            "HTTP": (
                result[
                    "javascript"
                ][
                    "status"
                ]
            ),
            "Content-Type": (
                result[
                    "javascript"
                ][
                    "content_type"
                ]
            ),
            "Bytes": (
                result[
                    "javascript"
                ][
                    "bytes"
                ]
            ),
            "Error": (
                result[
                    "javascript"
                ][
                    "error"
                ]
            ),
        },
    ]

    st.dataframe(
        pd.DataFrame(
            source_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    # ----------------------------------
    # 2. EXTRACTED API CONFIGURATION
    # ----------------------------------
    st.subheader(
        "2. Extracted registrants configuration"
    )

    configuration_rows = [
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
                "Default API base from JavaScript"
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
                "Raw concat argument"
            ),
            "Value": (
                result[
                    "concat_raw_argument"
                ]
            ),
        },
        {
            "Setting": (
                "Literal concat value"
            ),
            "Value": (
                result[
                    "concat_literal_value"
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
            configuration_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    # ----------------------------------
    # 3. SOURCE CONTEXT
    # ----------------------------------
    st.subheader(
        "3. Exact registrantsUrl source context"
    )

    if result[
        "concat_context"
    ]:
        st.code(
            result[
                "concat_context"
            ],
            language="javascript",
        )

    else:
        st.warning(
            "The registrantsUrl construction "
            "was not found."
        )

    # ----------------------------------
    # 4. RELEVANT STRINGS
    # ----------------------------------
    st.subheader(
        "4. Registrant-related strings"
    )

    if result[
        "registrant_strings"
    ]:
        st.json(
            result[
                "registrant_strings"
            ]
        )

    else:
        st.warning(
            "No registrant-related string "
            "literals were found."
        )

    # ----------------------------------
    # 5. API REQUEST RESULT
    # ----------------------------------
    st.subheader(
        "5. Registrants API request"
    )

    if not result[
        "endpoint"
    ]:
        st.warning(
            "No API request was made because "
            "the endpoint suffix could not be "
            "extracted as a literal value."
        )

    else:
        request_columns = (
            st.columns(4)
        )

        request_columns[0].metric(
            "HTTP",
            (
                result[
                    "api"
                ][
                    "status"
                ]
                if result[
                    "api"
                ][
                    "status"
                ]
                is not None
                else
                "Error"
            ),
        )

        request_columns[1].metric(
            "Response bytes",
            result[
                "api"
            ][
                "bytes"
            ],
        )

        request_columns[2].metric(
            "Valid JSON",
            (
                "Yes"
                if result[
                    "api"
                ][
                    "json"
                ]
                is not None
                else
                "No"
            ),
        )

        request_columns[3].metric(
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
                "api"
            ][
                "final_url"
            ],
            language=None,
        )

        st.write(
            "**Parameters:**"
        )

        st.json(
            result[
                "api_params"
            ]
        )

        st.write(
            "**Content-Type:** "
            f"{result['api']['content_type']}"
        )

        if result[
            "api"
        ][
            "error"
        ]:
            st.error(
                result[
                    "api"
                ][
                    "error"
                ]
            )

    # ----------------------------------
    # 6. REGISTRANTS
    # ----------------------------------
    st.subheader(
        "6. Registrants"
    )

    registrants = (
        result[
            "registrants"
        ]
    )

    st.write(
        "**Selected JSON list path:**"
    )

    st.code(
        (
            result[
                "selected_path"
            ]
            or
            "No list selected"
        ),
        language=None,
    )

    if registrants:
        registrants_dataframe = (
            pd.DataFrame(
                registrants
            )
        )

        non_empty_columns = [
            column
            for column in (
                registrants_dataframe
                .columns
            )
            if (
                registrants_dataframe[
                    column
                ]
                .astype(str)
                .str.strip()
                .ne("")
                .any()
            )
        ]

        if non_empty_columns:
            registrants_dataframe = (
                registrants_dataframe[
                    non_empty_columns
                ]
            )

        st.dataframe(
            registrants_dataframe,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No registrant rows were extracted."
        )

    # ----------------------------------
    # 7. RAW RESPONSES
    # ----------------------------------
    with st.expander(
        "7. Runtime configuration JSON",
        expanded=False,
    ):
        if (
            result[
                "runtime"
            ][
                "json"
            ]
            is not None
        ):
            st.json(
                result[
                    "runtime"
                ][
                    "json"
                ]
            )

        else:
            st.write(
                "No valid runtime JSON."
            )

    with st.expander(
        "8. Complete API JSON",
        expanded=False,
    ):
        if (
            result[
                "api"
            ][
                "json"
            ]
            is not None
        ):
            st.json(
                result[
                    "api"
                ][
                    "json"
                ]
            )

        else:
            st.write(
                "No valid API JSON."
            )

    with st.expander(
        "9. Raw API response",
        expanded=False,
    ):
        st.code(
            result[
                "api"
            ][
                "text"
            ][:20000],
            language=None,
        )