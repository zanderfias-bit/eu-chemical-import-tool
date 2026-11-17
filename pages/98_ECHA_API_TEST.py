import re
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="ECHA Registrants Route Discovery",
    page_icon="🔎",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_REGISTRANTS_ROUTE_DISCOVERY_V2"


# --------------------------------------------------
# KNOWN TEST SUBSTANCE
# --------------------------------------------------
CAS_NUMBER = "128-37-0"
EC_NUMBER = "204-881-4"
RML_ID = "100.004.439"

ECHA_BASE_URL = "https://chem.echa.europa.eu"

SUBSTANCE_OVERVIEW_URL = (
    f"{ECHA_BASE_URL}/"
    f"{RML_ID}/overview"
)

REACH_REGISTRATION_URLS = [
    f"{ECHA_BASE_URL}/{RML_ID}/dossiers/reach",
    f"{ECHA_BASE_URL}/{RML_ID}/dossiers",
    f"{ECHA_BASE_URL}/{RML_ID}/overview",
]


# --------------------------------------------------
# REQUEST SETTINGS
# --------------------------------------------------
CONNECT_TIMEOUT = 20
READ_TIMEOUT = 60

HEADERS = {
    "Accept": (
        "text/html,"
        "application/xhtml+xml,"
        "application/json,"
        "text/plain,"
        "*/*"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


# --------------------------------------------------
# SEARCH TERMS
# --------------------------------------------------
SEARCH_TERMS = [
    "registrant",
    "registrants",
    "registration",
    "registrationNumber",
    "registrationNumbers",
    "legalEntity",
    "legal-entity",
    "rmlId",
    "dossier-list",
    "api-",
    "/api/",
    "/v1/",
]


# --------------------------------------------------
# HTTP SESSION
# --------------------------------------------------
def create_session():
    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    retry = Retry(
        total=1,
        connect=1,
        read=1,
        status=1,
        backoff_factor=0.5,
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
# SAFE REQUEST
# --------------------------------------------------
def safe_get(
    session,
    url,
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
            headers=(
                request_headers
                or None
            ),
            timeout=(
                CONNECT_TIMEOUT,
                READ_TIMEOUT,
            ),
            allow_redirects=True,
        )

        return {
            "success": True,
            "response": response,
            "error": None,
        }

    except Exception as error:
        return {
            "success": False,
            "response": None,
            "error": str(error),
        }


# --------------------------------------------------
# SCRIPT EXTRACTION
# --------------------------------------------------
def extract_script_urls(
    html_text,
    page_url,
):
    script_sources = re.findall(
        r"""<script[^>]+src=["']([^"']+)["']""",
        html_text or "",
        flags=re.IGNORECASE,
    )

    urls = []

    seen = set()

    for source in script_sources:
        full_url = urljoin(
            page_url,
            source,
        )

        if full_url in seen:
            continue

        seen.add(
            full_url
        )

        urls.append(
            full_url
        )

    return urls


# --------------------------------------------------
# API STRING EXTRACTION
# --------------------------------------------------
def extract_api_like_strings(
    text,
):
    if not text:
        return []

    patterns = [
        r"""["']([^"']*?/api-[^"']+)["']""",
        r"""["']([^"']*?/api/[^"']+)["']""",
        r"""["']([^"']*?api-[A-Za-z0-9_\-/{}.?=&]+)["']""",
        r"""["']([^"']*?/v1/[A-Za-z0-9_\-/{}.?=&]+)["']""",
    ]

    values = []

    seen = set()

    for pattern in patterns:
        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        for match in matches:
            match = (
                str(match)
                .replace("\\/", "/")
                .strip()
            )

            if not match:
                continue

            if match in seen:
                continue

            seen.add(
                match
            )

            values.append(
                match
            )

    return values


# --------------------------------------------------
# SEARCH CONTEXT
# --------------------------------------------------
def find_contexts(
    text,
    source,
):
    if not text:
        return []

    contexts = []

    seen = set()

    lower_text = text.lower()

    for term in SEARCH_TERMS:
        term_lower = (
            term.lower()
        )

        start_position = 0

        while True:
            position = lower_text.find(
                term_lower,
                start_position,
            )

            if position == -1:
                break

            context_start = max(
                0,
                position - 350,
            )

            context_end = min(
                len(text),
                position + len(term) + 650,
            )

            context = text[
                context_start:
                context_end
            ]

            context = (
                context
                .replace("\\n", " ")
                .replace("\\r", " ")
                .replace("\\t", " ")
            )

            context = re.sub(
                r"\s+",
                " ",
                context,
            ).strip()

            key = (
                term_lower,
                context[:300],
            )

            if key not in seen:
                seen.add(
                    key
                )

                contexts.append(
                    {
                        "source": source,
                        "term": term,
                        "context": context,
                    }
                )

            start_position = (
                position
                + len(term)
            )

            if len(contexts) >= 200:
                return contexts

    return contexts


# --------------------------------------------------
# ANALYSE PAGE
# --------------------------------------------------
def analyse_page(
    session,
    url,
):
    request_result = safe_get(
        session,
        url,
    )

    if not request_result[
        "success"
    ]:
        return {
            "requested_url": url,
            "final_url": None,
            "status": None,
            "content_type": None,
            "response_length": 0,
            "scripts": [],
            "api_strings": [],
            "contexts": [],
            "body_preview": "",
            "error": request_result[
                "error"
            ],
        }

    response = request_result[
        "response"
    ]

    page_text = (
        response.text
    )

    script_urls = (
        extract_script_urls(
            page_text,
            response.url,
        )
    )

    return {
        "requested_url": url,
        "final_url": (
            response.url
        ),
        "status": (
            response.status_code
        ),
        "content_type": (
            response.headers.get(
                "content-type",
                "",
            )
        ),
        "response_length": len(
            response.content
        ),
        "scripts": script_urls,
        "api_strings": (
            extract_api_like_strings(
                page_text
            )
        ),
        "contexts": (
            find_contexts(
                page_text,
                "PAGE HTML",
            )
        ),
        "body_preview": (
            page_text[:5000]
        ),
        "error": None,
    }


# --------------------------------------------------
# ANALYSE JAVASCRIPT
# --------------------------------------------------
def analyse_script(
    session,
    script_url,
    referer,
):
    request_result = safe_get(
        session,
        script_url,
        referer=referer,
    )

    if not request_result[
        "success"
    ]:
        return {
            "script_url": script_url,
            "status": None,
            "content_type": None,
            "response_length": 0,
            "api_strings": [],
            "contexts": [],
            "error": request_result[
                "error"
            ],
        }

    response = request_result[
        "response"
    ]

    text = response.text

    return {
        "script_url": script_url,
        "status": (
            response.status_code
        ),
        "content_type": (
            response.headers.get(
                "content-type",
                "",
            )
        ),
        "response_length": len(
            response.content
        ),
        "api_strings": (
            extract_api_like_strings(
                text
            )
        ),
        "contexts": (
            find_contexts(
                text,
                script_url,
            )
        ),
        "error": None,
    }


# --------------------------------------------------
# COMPLETE DISCOVERY
# --------------------------------------------------
def run_discovery():
    session = (
        create_session()
    )

    page_results = []

    all_script_urls = []

    seen_scripts = set()

    for page_url in (
        REACH_REGISTRATION_URLS
    ):
        page_result = analyse_page(
            session,
            page_url,
        )

        page_results.append(
            page_result
        )

        for script_url in (
            page_result[
                "scripts"
            ]
        ):
            if script_url in seen_scripts:
                continue

            seen_scripts.add(
                script_url
            )

            all_script_urls.append(
                script_url
            )

    script_results = []

    referer = (
        SUBSTANCE_OVERVIEW_URL
    )

    for script_url in (
        all_script_urls
    ):
        script_result = (
            analyse_script(
                session,
                script_url,
                referer,
            )
        )

        script_results.append(
            script_result
        )

    api_strings = []

    seen_api_strings = set()

    for result in (
        page_results
    ):
        for value in result[
            "api_strings"
        ]:
            if (
                value
                in seen_api_strings
            ):
                continue

            seen_api_strings.add(
                value
            )

            api_strings.append(
                {
                    "source": (
                        "PAGE HTML"
                    ),
                    "value": value,
                }
            )

    for result in (
        script_results
    ):
        for value in result[
            "api_strings"
        ]:
            if (
                value
                in seen_api_strings
            ):
                continue

            seen_api_strings.add(
                value
            )

            api_strings.append(
                {
                    "source": (
                        result[
                            "script_url"
                        ]
                    ),
                    "value": value,
                }
            )

    all_contexts = []

    for result in page_results:
        all_contexts.extend(
            result[
                "contexts"
            ]
        )

    for result in script_results:
        all_contexts.extend(
            result[
                "contexts"
            ]
        )

    return {
        "pages": (
            page_results
        ),
        "scripts": (
            script_results
        ),
        "api_strings": (
            api_strings
        ),
        "contexts": (
            all_contexts
        ),
    }


# --------------------------------------------------
# STREAMLIT UI
# --------------------------------------------------
st.title(
    "ECHA Registrants route discovery"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.write(
    "This diagnostic inspects the public "
    "ECHA CHEM application resources for the "
    "API route used by the REACH Registrants tab."
)

st.info(
    "This test does not use Selenium, "
    "Playwright, browser automation, CAPTCHA "
    "handling, authentication bypasses or "
    "anti-bot workarounds."
)


# --------------------------------------------------
# CHEMICAL
# --------------------------------------------------
st.subheader(
    "Known test substance"
)

col1, col2, col3 = (
    st.columns(3)
)

col1.metric(
    "CAS",
    CAS_NUMBER,
)

col2.metric(
    "EC",
    EC_NUMBER,
)

col3.metric(
    "rmlId",
    RML_ID,
)

st.write(
    "Expected benchmark:"
)

st.write(
    "**42 registrants** are visible "
    "in the ECHA CHEM Registrants tab "
    "for this test case."
)


# --------------------------------------------------
# RUN
# --------------------------------------------------
if st.button(
    "Discover registrants route",
    type="primary",
):
    with st.spinner(
        "Inspecting ECHA CHEM "
        "application resources..."
    ):
        result = (
            run_discovery()
        )

    st.success(
        "Discovery completed."
    )

    # ----------------------------------
    # PAGE RESULTS
    # ----------------------------------
    st.subheader(
        "1. Page requests"
    )

    page_rows = []

    for page in result[
        "pages"
    ]:
        page_rows.append(
            {
                "Requested URL": (
                    page[
                        "requested_url"
                    ]
                ),
                "HTTP": (
                    page[
                        "status"
                    ]
                ),
                "Final URL": (
                    page[
                        "final_url"
                    ]
                ),
                "Content-Type": (
                    page[
                        "content_type"
                    ]
                ),
                "Bytes": (
                    page[
                        "response_length"
                    ]
                ),
                "JavaScript files": (
                    len(
                        page[
                            "scripts"
                        ]
                    )
                ),
                "Keyword contexts": (
                    len(
                        page[
                            "contexts"
                        ]
                    )
                ),
                "Error": (
                    page[
                        "error"
                    ]
                ),
            }
        )

    st.dataframe(
        pd.DataFrame(
            page_rows
        ),
        width="stretch",
        hide_index=True,
    )

    # ----------------------------------
    # SCRIPT RESULTS
    # ----------------------------------
    st.subheader(
        "2. JavaScript resources"
    )

    script_rows = []

    for script in   script_rows.append(
            {
                "Script": (
                    script[
                        "script_url"
                    ]
                ),
                "HTTP": (
                    script[
                        "status"
                    ]
                ),
                "Content-Type": (
                    script[
                        "content_type"
                    ]
                ),
                "Bytes": (
                    script[
                        "response_length"
                    ]
                ),
                "API-like strings": (
                    len(
                        script[
                            "api_strings"
                        ]
                    )
                ),
                "Keyword contexts": (
                    len(
                        script[
                            "contexts"
                        ]
                    )
                ),
                "Error": (
                    script[
                        "error"
                    ]
                ),
            }
        )

    if script_rows:
        st.dataframe(
            pd.DataFrame(
                script_rows
            ),
            width="stretch",
            hide_index=True,
        )

    else:
        st.warning(
            "No JavaScript resource URLs "
            "were discovered."
        )

    # ----------------------------------
    # API STRINGS
    # ----------------------------------
    st.subheader(
        "3. API-like strings"
    )

    if result[
        "api_strings"
    ]:
        st.success(
            "API-like strings were found."
        )

        st.dataframe(
            pd.DataFrame(
                result[
                    "api_strings"
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    else:
        st.warning(
            "No explicit API-like strings "
            "were found."
        )

    # ----------------------------------
    # REGISTRANT CONTEXTS
    # ----------------------------------
    st.subheader(
        "4. Registrant-related code contexts"
    )

    useful_contexts = [
        row
        for row in result[
            "contexts"
        ]
        if row[
            "term"
        ].lower()
        in {
            "registrant",
            "registrants",
            "registration",
            "registrationnumber",
            "registrationnumbers",
            "legalentity",
            "legal-entity",
            "rmlid",
            "dossier-list",
            "api-",
            "/api/",
            "/v1/",
        }
    ]

    if useful_contexts:
        st.success(
            "Relevant frontend code "
            "contexts were found."
        )

        st.dataframe(
            pd.DataFrame(
                useful_contexts
            ),
            width="stretch",
            hide_index=True,
        )

    else:
        st.warning(
            "No registrant-related frontend "
            "code context was found."
        )

    # ----------------------------------
    # RAW PAGE DETAILS
    # ----------------------------------
    with st.expander(
        "Raw page diagnostics",
        expanded=False,
    ):
        for page in result[
            "pages"
        ]:
            st.markdown(
                "### Page"
            )

            st.code(
                page[
                    "requested_url"
                ],
                language=None,
            )

            st.write(
                f"HTTP: "
                f"{page['status']}"
            )

            st.write(
                "**Discovered scripts:**"
            )

            st.json(
                page[
                    "scripts"
                ]
            )

            st.write(
                "**HTML preview:**"
            )

            st.code(
                page[
                    "body_preview"
                ],
                language="html",
            )