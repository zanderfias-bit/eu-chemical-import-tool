import json
import re

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="ECHA Registrants API Discovery",
    page_icon="🔎",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_REGISTRANTS_API_DISCOVERY_V12"


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
# SAFE GET
# --------------------------------------------------
def safe_get(
    session,
    url,
    referer=None,
):
    headers = (
        {
            "Referer": referer
        }
        if referer
        else None
    )

    try:
        response = session.get(
            url,
            headers=headers,
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
# CLEAN JAVASCRIPT
# --------------------------------------------------
def clean_javascript(
    text,
):
    if not text:
        return ""

    return (
        text
        .replace(
            "\\/",
            "/",
        )
        .replace(
            "\\u002F",
            "/",
        )
        .replace(
            "\\u002f",
            "/",
        )
    )


# --------------------------------------------------
# GET SOURCE CONTEXT
# --------------------------------------------------
def get_context(
    text,
    start,
    end,
    before=1500,
    after=4000,
):
    context_start = max(
        0,
        start - before,
    )

    context_end = min(
        len(text),
        end + after,
    )

    return text[
        context_start:
        context_end
    ]


# --------------------------------------------------
# FIND ALL CONTEXTS
# --------------------------------------------------
def find_all_contexts(
    text,
    search_term,
    before=1500,
    after=4000,
):
    if not text:
        return []

    lower_text = (
        text.lower()
    )

    lower_term = (
        search_term.lower()
    )

    contexts = []
    start = 0

    while True:
        position = lower_text.find(
            lower_term,
            start,
        )

        if position < 0:
            break

        contexts.append(
            {
                "term": (
                    search_term
                ),
                "position": (
                    position
                ),
                "context": (
                    get_context(
                        text,
                        position,
                        position + len(
                            search_term
                        ),
                        before=before,
                        after=after,
                    )
                ),
            }
        )

        start = (
            position
            + len(search_term)
        )

        if len(
            contexts
        ) >= 20:
            break

    return contexts


# --------------------------------------------------
# EXTRACT REGISTRANTS API ASSIGNMENT
# --------------------------------------------------
def extract_registrants_assignment(
    text,
):
    if not text:
        return {
            "full_assignment": "",
            "fallback_expression": "",
            "fallback_identifier": "",
            "context": "",
        }

    patterns = [
        re.compile(
            (
                r"registrantsApiUrl\s*=\s*"
                r"(?P<runtime>"
                r"[^;]{0,300}?"
                r"registrantsApiUrl"
                r")\s*\|\|\s*"
                r"(?P<fallback>"
                r"[^;]{1,1000}"
                r")\s*;"
            ),
            flags=re.IGNORECASE,
        ),
        re.compile(
            (
                r"registrantsApiUrl\s*=\s*"
                r"(?P<runtime>"
                r"[^;]{0,500}?"
                r")\|\|"
                r"(?P<fallback>"
                r"[^;]{1,1000}"
                r");"
            ),
            flags=re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        match = pattern.search(
            text
        )

        if not match:
            continue

        fallback = (
            match.group(
                "fallback"
            )
            .strip()
        )

        identifier_match = (
            re.fullmatch(
                (
                    r"(?:"
                    r"[A-Za-z_$]"
                    r"[A-Za-z0-9_$]*"
                    r"\.)*"
                    r"("
                    r"[A-Za-z_$]"
                    r"[A-Za-z0-9_$]*"
                    r")"
                ),
                fallback,
            )
        )

        fallback_identifier = ""

        if identifier_match:
            fallback_identifier = (
                identifier_match.group(
                    1
                )
            )

        return {
            "full_assignment": (
                match.group(0)
            ),
            "fallback_expression": (
                fallback
            ),
            "fallback_identifier": (
                fallback_identifier
            ),
            "context": (
                get_context(
                    text,
                    match.start(),
                    match.end(),
                )
            ),
        }

    contexts = (
        find_all_contexts(
            text,
            "registrantsApiUrl",
        )
    )

    return {
        "full_assignment": "",
        "fallback_expression": "",
        "fallback_identifier": "",
        "context": (
            contexts[0][
                "context"
            ]
            if contexts
            else ""
        ),
    }


# --------------------------------------------------
# EXTRACT REGISTRANTS URL ASSIGNMENT
# --------------------------------------------------
def extract_registrants_url_assignment(
    text,
):
    if not text:
        return {
            "full_assignment": "",
            "suffix": "",
            "context": "",
        }

    pattern = re.compile(
        (
            r"registrantsUrl\s*=\s*"
            r"this\.registrantsApiUrl"
            r"\.concat\(\s*"
            r"[\"']"
            r"(?P<suffix>[^\"']+)"
            r"[\"']"
            r"\s*\)"
        ),
        flags=re.IGNORECASE,
    )

    match = pattern.search(
        text
    )

    if not match:
        contexts = (
            find_all_contexts(
                text,
                "registrantsUrl",
            )
        )

        return {
            "full_assignment": "",
            "suffix": "",
            "context": (
                contexts[0][
                    "context"
                ]
                if contexts
                else ""
            ),
        }

    return {
        "full_assignment": (
            match.group(0)
        ),
        "suffix": (
            match.group(
                "suffix"
            )
            .strip()
        ),
        "context": (
            get_context(
                text,
                match.start(),
                match.end(),
            )
        ),
    }


# --------------------------------------------------
# EXTRACT RELEVANT STRING LITERALS
# --------------------------------------------------
def extract_api_literals(
    text,
):
    if not text:
        return []

    patterns = [
        (
            r"[\"']"
            r"([^\"']*"
            r"api-dossier-list/v\d+/"
            r"[^\"']*)"
            r"[\"']"
        ),
        (
            r"[\"']"
            r"([^\"']*"
            r"registrant"
            r"[^\"']*)"
            r"[\"']"
        ),
    ]

    rows = []
    seen = set()

    for pattern in patterns:
        matches = re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        for match in matches:
            value = (
                match.group(1)
                .strip()
            )

            if not value:
                continue

            if len(
                value
            ) > 1000:
                continue

            if value in seen:
                continue

            seen.add(
                value
            )

            rows.append(
                {
                    "value": (
                        value
                    ),
                    "position": (
                        match.start()
                    ),
                    "context": (
                        get_context(
                            text,
                            match.start(),
                            match.end(),
                            before=500,
                            after=1200,
                        )
                    ),
                }
            )

    return rows


# --------------------------------------------------
# FIND IDENTIFIER DEFINITIONS
# --------------------------------------------------
def find_identifier_definitions(
    text,
    identifier,
):
    if not text:
        return []

    if not identifier:
        return []

    escaped = re.escape(
        identifier
    )

    patterns = [
        re.compile(
            (
                rf"(?:var|let|const)"
                rf"\s+{escaped}\s*=\s*"
                rf"(?P<value>"
                rf"[^;]{{1,1500}}"
                rf");"
            ),
            flags=re.IGNORECASE,
        ),
        re.compile(
            (
                rf"(?:^|[,;])\s*"
                rf"{escaped}\s*=\s*"
                rf"(?P<value>"
                rf"[^;]{{1,1500}}"
                rf");"
            ),
            flags=re.IGNORECASE,
        ),
        re.compile(
            (
                rf"{escaped}\s*:\s*"
                rf"(?P<value>"
                rf"[^,}}]{{1,1200}}"
                rf")"
            ),
            flags=re.IGNORECASE,
        ),
    ]

    results = []
    seen = set()

    for pattern in patterns:
        matches = pattern.finditer(
            text
        )

        for match in matches:
            value = (
                match.group(
                    "value"
                )
                .strip()
            )

            key = (
                match.start(),
                value,
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            results.append(
                {
                    "identifier": (
                        identifier
                    ),
                    "value_expression": (
                        value
                    ),
                    "position": (
                        match.start()
                    ),
                    "context": (
                        get_context(
                            text,
                            match.start(),
                            match.end(),
                            before=1500,
                            after=3000,
                        )
                    ),
                }
            )

            if len(
                results
            ) >= 20:
                return results

    return results


# --------------------------------------------------
# RUN DISCOVERY
# --------------------------------------------------
def run_discovery():
    session = (
        create_session()
    )

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
            clean_javascript(
                javascript_response.text
                or ""
            )
        )

    # ----------------------------------
    # EXTRACT ASSIGNMENTS
    # ----------------------------------
    api_assignment = (
        extract_registrants_assignment(
            javascript_text
        )
    )

    url_assignment = (
        extract_registrants_url_assignment(
            javascript_text
        )
    )

    api_literals = (
        extract_api_literals(
            javascript_text
        )
    )

    fallback_definitions = (
        find_identifier_definitions(
            javascript_text,
            api_assignment[
                "fallback_identifier"
            ],
        )
    )

    registrants_contexts = (
        find_all_contexts(
            javascript_text,
            "registrantsApiUrl",
        )
    )

    v2_contexts = (
        find_all_contexts(
            javascript_text,
            "/api-dossier-list/v2/",
            before=1500,
            after=3500,
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
            "text": (
                runtime_response.text
                if runtime_response
                is not None
                else ""
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
        "api_assignment": (
            api_assignment
        ),
        "url_assignment": (
            url_assignment
        ),
        "api_literals": (
            api_literals
        ),
        "fallback_definitions": (
            fallback_definitions
        ),
        "registrants_contexts": (
            registrants_contexts
        ),
        "v2_contexts": (
            v2_contexts
        ),
    }


# --------------------------------------------------
# STREAMLIT INTERFACE
# --------------------------------------------------
st.title(
    "ECHA Registrants API discovery"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.write(
    "V12 performs one focused task: determine "
    "the exact fallback value used for "
    "`registrantsApiUrl` in the ECHA dossierList "
    "micro-frontend."
)

st.info(
    "This version does not call a registrants "
    "endpoint. It only reads public ECHA "
    "configuration and JavaScript to avoid "
    "guessing another API URL."
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
# RESOURCES
# --------------------------------------------------
st.subheader(
    "Resources"
)

st.code(
    RUNTIME_CONFIG_URL,
    language=None,
)

st.code(
    DOSSIER_LIST_WEB_COMPONENTS_URL,
    language=None,
)


# --------------------------------------------------
# RUN
# --------------------------------------------------
if st.button(
    "Discover registrantsApiUrl fallback",
    type="primary",
):
    with st.spinner(
        "Reading the ECHA dossierList "
        "configuration..."
    ):
        result = (
            run_discovery()
        )

    st.success(
        "Discovery completed."
    )

    # ----------------------------------
    # 1. SOURCE RESPONSES
    # ----------------------------------
    st.subheader(
        "1. Source responses"
    )

    response_rows = [
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
            "Valid JSON": (
                result[
                    "runtime"
                ][
                    "json"
                ]
                is not None
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
                "dossierList web-components"
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
            "Valid JSON": False,
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
            response_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    # ----------------------------------
    # 2. RUNTIME CONFIGURATION
    # ----------------------------------
    st.subheader(
        "2. Runtime configuration"
    )

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
        st.warning(
            "Runtime configuration did "
            "not return valid JSON."
        )

        st.code(
            result[
                "runtime"
            ][
                "text"
            ][:5000],
            language=None,
        )

    # ----------------------------------
    # 3. REGISTRANTS API ASSIGNMENT
    # ----------------------------------
    st.subheader(
        "3. registrantsApiUrl assignment"
    )

    assignment = (
        result[
            "api_assignment"
        ]
    )

    assignment_rows = [
        {
            "Field": (
                "Full assignment"
            ),
            "Value": (
                assignment[
                    "full_assignment"
                ]
            ),
        },
        {
            "Field": (
                "Fallback expression"
            ),
            "Value": (
                assignment[
                    "fallback_expression"
                ]
            ),
        },
        {
            "Field": (
                "Fallback identifier"
            ),
            "Value": (
                assignment[
                    "fallback_identifier"
                ]
            ),
        },
    ]

    st.dataframe(
        pd.DataFrame(
            assignment_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    if assignment[
        "context"
    ]:
        st.code(
            assignment[
                "context"
            ],
            language="javascript",
        )

    else:
        st.warning(
            "No registrantsApiUrl context "
            "was found."
        )

    # ----------------------------------
    # 4. REGISTRANTS URL ASSIGNMENT
    # ----------------------------------
    st.subheader(
        "4. registrantsUrl assignment"
    )

    url_assignment = (
        result[
            "url_assignment"
        ]
    )

    url_rows = [
        {
            "Field": (
                "Full assignment"
            ),
            "Value": (
                url_assignment[
                    "full_assignment"
                ]
            ),
        },
        {
            "Field": (
                "Suffix"
            ),
            "Value": (
                url_assignment[
                    "suffix"
                ]
            ),
        },
    ]

    st.dataframe(
        pd.DataFrame(
            url_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    if url_assignment[
        "context"
    ]:
        st.code(
            url_assignment[
                "context"
            ],
            language="javascript",
        )

    # ----------------------------------
    # 5. FALLBACK DEFINITIONS
    # ----------------------------------
    st.subheader(
        "5. Fallback identifier definitions"
    )

    fallback_definitions = (
        result[
            "fallback_definitions"
        ]
    )

    if fallback_definitions:
        definition_rows = [
            {
                "Identifier": (
                    row[
                        "identifier"
                    ]
                ),
                "Value expression": (
                    row[
                        "value_expression"
                    ]
                ),
                "Position": (
                    row[
                        "position"
                    ]
                ),
            }
            for row
            in fallback_definitions
        ]

        st.dataframe(
            pd.DataFrame(
                definition_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

        for index, row in enumerate(
            fallback_definitions,
            start=1,
        ):
            with st.expander(
                f"Definition context {index}",
                expanded=(
                    index == 1
                ),
            ):
                st.code(
                    row[
                        "context"
                    ],
                    language="javascript",
                )

    else:
        st.warning(
            "No definition for the fallback "
            "identifier was found."
        )

    # ----------------------------------
    # 6. API LITERALS
    # ----------------------------------
    st.subheader(
        "6. API and registrant string literals"
    )

    api_literals = (
        result[
            "api_literals"
        ]
    )

    if api_literals:
        literal_rows = [
            {
                "Value": (
                    row[
                        "value"
                    ]
                ),
                "Position": (
                    row[
                        "position"
                    ]
                ),
            }
            for row
            in api_literals
        ]

        st.dataframe(
            pd.DataFrame(
                literal_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No relevant API string "
            "literals were found."
        )

    # ----------------------------------
    # 7. V2 CONTEXT
    # ----------------------------------
    st.subheader(
        "7. Context around "
        "/api-dossier-list/v2/"
    )

    v2_contexts = (
        result[
            "v2_contexts"
        ]
    )

    if v2_contexts:
        for index, row in enumerate(
            v2_contexts,
            start=1,
        ):
            with st.expander(
                f"V2 context {index}",
                expanded=(
                    index == 1
                ),
            ):
                st.code(
                    row[
                        "context"
                    ],
                    language="javascript",
                )

    else:
        st.warning(
            "No /api-dossier-list/v2/ "
            "context was found."
        )

    # ----------------------------------
    # 8. ALL REGISTRANTS CONTEXTS
    # ----------------------------------
    with st.expander(
        "8. All registrantsApiUrl contexts",
        expanded=False,
    ):
        registrants_contexts = (
            result[
                "registrants_contexts"
            ]
        )

        if registrants_contexts:
            for index, row in enumerate(
                registrants_contexts,
                start=1,
            ):
                st.markdown(
                    f"**Context {index} at "
                    f"position {row['position']}**"
                )

                st.code(
                    row[
                        "context"
                    ],
                    language="javascript",
                )

        else:
            st.write(
                "No registrantsApiUrl "
                "contexts found."
            )