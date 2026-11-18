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
    page_title="ECHA registrants environment discovery",
    page_icon="🔎",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_REGISTRANTS_ENV_DISCOVERY_V14"


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

DOSSIER_RUNTIME_CONFIG_URL = (
    f"{ECHA_BASE_URL}/"
    "mfe-config/dossierList/mfe-config.json"
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
):
    try:
        response = session.get(
            url,
            headers={
                "Referer": OVERVIEW_URL
            },
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
# JSON PARSER
# --------------------------------------------------
def parse_json(
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
    return (
        (text or "")
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
# SOURCE CONTEXT
# --------------------------------------------------
def context(
    text,
    start,
    end,
    before=1800,
    after=3500,
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
# FIND OCCURRENCES
# --------------------------------------------------
def find_all_occurrences(
    text,
    term,
    limit=30,
):
    rows = []

    lower_text = (
        text.lower()
    )

    lower_term = (
        term.lower()
    )

    start = 0

    while True:
        position = lower_text.find(
            lower_term,
            start,
        )

        if position < 0:
            break

        rows.append(
            {
                "term": (
                    term
                ),
                "position": (
                    position
                ),
                "context": (
                    context(
                        text,
                        position,
                        position + len(
                            term
                        ),
                    )
                ),
            }
        )

        start = (
            position
            + len(term)
        )

        if len(
            rows
        ) >= limit:
            break

    return rows


# --------------------------------------------------
# REGISTRANTS EXPRESSION
# --------------------------------------------------
def find_registrants_expression(
    text,
):
    match = re.search(
        (
            r"registrantsApiUrl"
            r"\s*=\s*"
            r"([^;]{1,1500});"
        ),
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return {
            "expression": "",
            "context": "",
        }

    return {
        "expression": (
            match.group(1)
            .strip()
        ),
        "context": (
            context(
                text,
                match.start(),
                match.end(),
            )
        ),
    }


# --------------------------------------------------
# FIND DEFINITIONS OF g
# --------------------------------------------------
def find_g_definitions(
    text,
):
    patterns = [
        (
            r"(?:var|let|const)"
            r"\s+g\s*=\s*"
            r"(?P<value>[^;]{1,3000});"
        ),
        (
            r"(?:^|;)"
            r"g\s*=\s*"
            r"(?P<value>[^;]{1,3000});"
        ),
        (
            r"(?:^|,)"
            r"g\s*=\s*"
            r"(?P<value>[^;]{1,3000});"
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

            rows.append(
                {
                    "position": (
                        match.start()
                    ),
                    "value_expression": (
                        value
                    ),
                    "context": (
                        context(
                            text,
                            match.start(),
                            match.end(),
                            before=2500,
                            after=5000,
                        )
                    ),
                }
            )

    return rows


# --------------------------------------------------
# FIND DIRECT registrantsApiUrl PROPERTIES
# --------------------------------------------------
def find_object_literals_with_registrants_api(
    text,
):
    rows = []
    seen = set()

    patterns = [
        (
            r"registrantsApiUrl"
            r"\s*:\s*"
            r"[\"']"
            r"(?P<value>[^\"']*)"
            r"[\"']"
        ),
        (
            r"registrantsApiUrl"
            r"\s*=\s*"
            r"[\"']"
            r"(?P<value>[^\"']*)"
            r"[\"']"
        ),
    ]

    for pattern in patterns:
        matches = re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE,
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

            rows.append(
                {
                    "position": (
                        match.start()
                    ),
                    "registrantsApiUrl": (
                        value
                    ),
                    "context": (
                        context(
                            text,
                            match.start(),
                            match.end(),
                            before=2500,
                            after=5000,
                        )
                    ),
                }
            )

    return rows


# --------------------------------------------------
# FIND API STRING LITERALS
# --------------------------------------------------
def find_api_literals(
    text,
):
    pattern = re.compile(
        (
            r"[\"']"
            r"(?P<value>"
            r"[^\"']*"
            r"(?:api-dossier-list|registrant)"
            r"[^\"']*"
            r")"
            r"[\"']"
        ),
        flags=re.IGNORECASE,
    )

    rows = []
    seen = set()

    for match in pattern.finditer(
        text
    ):
        value = (
            match.group(
                "value"
            )
            .strip()
        )

        if not value:
            continue

        if len(
            value
        ) > 1500:
            continue

        if value in seen:
            continue

        seen.add(
            value
        )

        rows.append(
            {
                "position": (
                    match.start()
                ),
                "value": (
                    value
                ),
                "context": (
                    context(
                        text,
                        match.start(),
                        match.end(),
                        before=800,
                        after=1800,
                    )
                ),
            }
        )

    return rows


# --------------------------------------------------
# FIND IMPORTS / EXPORTS INVOLVING g
# --------------------------------------------------
def find_imports_and_exports_near_g(
    text,
):
    rows = []

    patterns = [
        (
            r"import\{"
            r"[^}]{1,3000}"
            r"\}"
            r"from"
            r"[\"']"
            r"[^\"']+"
            r"[\"']"
        ),
        (
            r"import\*as\s+"
            r"[A-Za-z_$]"
            r"[A-Za-z0-9_$]*"
            r"\s+from"
            r"[\"']"
            r"[^\"']+"
            r"[\"']"
        ),
        (
            r"export\{"
            r"[^}]{1,3000}"
            r"\}"
        ),
    ]

    for pattern in patterns:
        matches = re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        for match in matches:
            snippet = (
                match.group(0)
            )

            if not (
                " g"
                in snippet
                or
                "g "
                in snippet
                or
                " as g"
                in snippet
                or
                "g as "
                in snippet
            ):
                continue

            rows.append(
                {
                    "position": (
                        match.start()
                    ),
                    "statement": (
                        snippet
                    ),
                    "context": (
                        context(
                            text,
                            match.start(),
                            match.end(),
                            before=800,
                            after=1500,
                        )
                    ),
                }
            )

    return rows


# --------------------------------------------------
# RUN DISCOVERY
# --------------------------------------------------
def run_discovery():
    session = (
        create_session()
    )

    # ----------------------------------
    # RUNTIME CONFIG
    # ----------------------------------
    runtime_response, runtime_error = (
        safe_get(
            session,
            DOSSIER_RUNTIME_CONFIG_URL,
        )
    )

    runtime_json = (
        parse_json(
            runtime_response
        )
    )

    # ----------------------------------
    # WEB COMPONENTS JS
    # ----------------------------------
    js_response, js_error = (
        safe_get(
            session,
            DOSSIER_LIST_WEB_COMPONENTS_URL,
        )
    )

    js_text = (
        clean_javascript(
            js_response.text
            if js_response
            is not None
            else ""
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
                js_response.status_code
                if js_response
                is not None
                else None
            ),
            "content_type": (
                js_response.headers.get(
                    "content-type",
                    "",
                )
                if js_response
                is not None
                else ""
            ),
            "bytes": (
                len(
                    js_response.content
                )
                if js_response
                is not None
                else 0
            ),
            "error": (
                js_error
            ),
        },
        "registrants_expression": (
            find_registrants_expression(
                js_text
            )
        ),
        "g_definitions": (
            find_g_definitions(
                js_text
            )
        ),
        "registrants_properties": (
            find_object_literals_with_registrants_api(
                js_text
            )
        ),
        "api_literals": (
            find_api_literals(
                js_text
            )
        ),
        "g_imports": (
            find_imports_and_exports_near_g(
                js_text
            )
        ),
        "g_contexts": (
            find_all_occurrences(
                js_text,
                "g?.registrantsApiUrl",
            )
        ),
        "dossier_contexts": (
            find_all_occurrences(
                js_text,
                "g.dossierListApiUrl",
            )
        ),
        "v2_contexts": (
            find_all_occurrences(
                js_text,
                "/api-dossier-list/v2/",
            )
        ),
    }


# --------------------------------------------------
# STREAMLIT INTERFACE
# --------------------------------------------------
st.title(
    "ECHA registrants environment discovery"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.write(
    "V14 determines where the minified JavaScript "
    "object `g` gets its `registrantsApiUrl` value. "
    "No registrants endpoint is called in this version."
)

st.info(
    "The dossierList runtime configuration only "
    "contains `/api-dossier-list/v1/`. "
    "The ECHA JavaScript separately reads "
    "`g?.registrantsApiUrl`, so V14 examines "
    "that environment object directly instead of "
    "guessing another endpoint."
)


# --------------------------------------------------
# KNOWN TEST SUBSTANCE
# --------------------------------------------------
st.subheader(
    "Known test substance"
)

columns = (
    st.columns(4)
)

columns[0].metric(
    "CAS",
    CAS_NUMBER,
)

columns[1].metric(
    "EC",
    EC_NUMBER,
)

columns[2].metric(
    "rmlId",
    RML_ID,
)

columns[3].metric(
    "Expected registrants",
    EXPECTED_REGISTRANTS,
)


# --------------------------------------------------
# RUN
# --------------------------------------------------
if st.button(
    "Discover g.registrantsApiUrl",
    type="primary",
):
    with st.spinner(
        "Inspecting the dossierList JavaScript "
        "environment object..."
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
                "dossierList runtime config"
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
    # 2. RUNTIME CONFIG
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
        st.code(
            result[
                "runtime"
            ][
                "text"
            ][:10000],
            language=None,
        )

    # ----------------------------------
    # 3. registrantsApiUrl EXPRESSION
    # ----------------------------------
    st.subheader(
        "3. registrantsApiUrl expression"
    )

    expression = (
        result[
            "registrants_expression"
        ]
    )

    if expression[
        "expression"
    ]:
        st.write(
            "**Expression:**"
        )

        st.code(
            expression[
                "expression"
            ],
            language="javascript",
        )

        st.write(
            "**Context:**"
        )

        st.code(
            expression[
                "context"
            ],
            language="javascript",
        )

    else:
        st.warning(
            "No registrantsApiUrl "
            "assignment was found."
        )

    # ----------------------------------
    # 4. DIRECT PROPERTIES
    # ----------------------------------
    st.subheader(
        "4. Direct registrantsApiUrl properties"
    )

    properties = (
        result[
            "registrants_properties"
        ]
    )

    if properties:
        property_rows = [
            {
                "Position": (
                    row[
                        "position"
                    ]
                ),
                "registrantsApiUrl": (
                    row[
                        "registrantsApiUrl"
                    ]
                ),
            }
            for row
            in properties
        ]

        st.dataframe(
            pd.DataFrame(
                property_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

        for index, row in enumerate(
            properties,
            start=1,
        ):
            with st.expander(
                f"Property context {index}",
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
            "No direct registrantsApiUrl "
            "property was found in this bundle."
        )

    # ----------------------------------
    # 5. DEFINITIONS OF g
    # ----------------------------------
    st.subheader(
        "5. Definitions of minified object g"
    )

    g_definitions = (
        result[
            "g_definitions"
        ]
    )

    if g_definitions:
        definition_rows = [
            {
                "Position": (
                    row[
                        "position"
                    ]
                ),
                "Value expression": (
                    row[
                        "value_expression"
                    ]
                ),
            }
            for row
            in g_definitions
        ]

        st.dataframe(
            pd.DataFrame(
                definition_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

        for index, row in enumerate(
            g_definitions,
            start=1,
        ):
            with st.expander(
                f"g definition context {index}",
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
            "No local `g = ...` definition "
            "was found in this bundle."
        )

    # ----------------------------------
    # 6. IMPORTS / EXPORTS
    # ----------------------------------
    st.subheader(
        "6. Imports/exports involving g"
    )

    g_imports = (
        result[
            "g_imports"
        ]
    )

    if g_imports:
        import_rows = [
            {
                "Position": (
                    row[
                        "position"
                    ]
                ),
                "Statement": (
                    row[
                        "statement"
                    ]
                ),
            }
            for row
            in g_imports
        ]

        st.dataframe(
            pd.DataFrame(
                import_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No import/export statement "
            "involving `g` was detected."
        )

    # ----------------------------------
    # 7. STRING LITERALS
    # ----------------------------------
    st.subheader(
        "7. API and registrant string literals"
    )

    api_literals = (
        result[
            "api_literals"
        ]
    )

    if api_literals:
        literal_rows = [
            {
                "Position": (
                    row[
                        "position"
                    ]
                ),
                "Value": (
                    row[
                        "value"
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
            "No API/registrant string "
            "literals were found."
        )

    # ----------------------------------
    # 8. REGISTRANTS API CONTEXT
    # ----------------------------------
    st.subheader(
        "8. Context around "
        "g?.registrantsApiUrl"
    )

    g_contexts = (
        result[
            "g_contexts"
        ]
    )

    if g_contexts:
        for index, row in enumerate(
            g_contexts,
            start=1,
        ):
            with st.expander(
                (
                    "registrantsApiUrl "
                    f"context {index}"
                ),
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
            "No `g?.registrantsApiUrl` "
            "context was found."
        )

    # ----------------------------------
    # 9. DOSSIER API CONTEXT
    # ----------------------------------
    st.subheader(
        "9. Context around "
        "g.dossierListApiUrl"
    )

    dossier_contexts = (
        result[
            "dossier_contexts"
        ]
    )

    if dossier_contexts:
        for index, row in enumerate(
            dossier_contexts,
            start=1,
        ):
            with st.expander(
                (
                    "dossierListApiUrl "
                    f"context {index}"
                ),
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
            "No `g.dossierListApiUrl` "
            "context was found."
        )

    # ----------------------------------
    # 10. V2 CONTEXT
    # ----------------------------------
    st.subheader(
        "10. Context around "
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
                f"v2 context {index}",
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
            "No `/api-dossier-list/v2/` "
            "context was found."
        )