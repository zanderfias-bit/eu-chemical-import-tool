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
    page_title="ECHA Registrants Route Discovery",
    page_icon="🔎",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_REGISTRANTS_ROUTE_DISCOVERY_V3"


# --------------------------------------------------
# KNOWN TEST SUBSTANCE
# --------------------------------------------------
CAS_NUMBER = "128-37-0"
EC_NUMBER = "204-881-4"
RML_ID = "100.004.439"

ECHA_BASE_URL = "https://chem.echa.europa.eu"


# --------------------------------------------------
# PAGES TO ANALYSE
# --------------------------------------------------
PAGE_URLS = [
    (
        f"{ECHA_BASE_URL}/"
        f"{RML_ID}/overview"
    ),
    (
        f"{ECHA_BASE_URL}/"
        f"{RML_ID}/dossiers"
    ),
    (
        f"{ECHA_BASE_URL}/"
        f"{RML_ID}/dossiers/reach"
    ),
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
# SEARCH TERMS
# --------------------------------------------------
SEARCH_TERMS = [
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
# SAFE HTTP REQUEST
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

        return response, None

    except requests.RequestException as error:
        return None, str(error)


# --------------------------------------------------
# SCRIPT URL EXTRACTION
# --------------------------------------------------
def extract_script_urls(
    html_text,
    page_url,
):
    script_sources = re.findall(
        (
            r"<script\b[^>]*"
            r"\bsrc\s*=\s*"
            r"[\"']([^\"']+)[\"']"
            r"[^>]*>"
        ),
        html_text or "",
        flags=re.IGNORECASE,
    )

    script_urls = []
    seen_urls = set()

    for source in script_sources:
        source = str(
            source
        ).strip()

        if not source:
            continue

        full_url = urljoin(
            page_url,
            source,
        )

        if full_url in seen_urls:
            continue

        seen_urls.add(
            full_url
        )

        script_urls.append(
            full_url
        )

    return script_urls


# --------------------------------------------------
# API-LIKE STRING EXTRACTION
# --------------------------------------------------
def extract_api_like_strings(
    text,
):
    if not text:
        return []

    patterns = [
        (
            r"[\"']"
            r"([^\"']*/api-[^\"']+)"
            r"[\"']"
        ),
        (
            r"[\"']"
            r"([^\"']*/api/[^\"']+)"
            r"[\"']"
        ),
        (
            r"[\"']"
            r"([^\"']*api-"
            r"[A-Za-z0-9_\-/{}.?=&]+)"
            r"[\"']"
        ),
        (
            r"[\"']"
            r"([^\"']*/v1/"
            r"[A-Za-z0-9_\-/{}.?=&]+)"
            r"[\"']"
        ),
    ]

    values = []
    seen_values = set()

    for pattern in patterns:
        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        for match in matches:
            value = (
                str(match)
                .replace("\\/", "/")
                .strip()
            )

            if not value:
                continue

            if value in seen_values:
                continue

            seen_values.add(
                value
            )

            values.append(
                value
            )

    return values


# --------------------------------------------------
# SEARCH FOR RELEVANT CODE CONTEXTS
# --------------------------------------------------
def find_contexts(
    text,
    source,
):
    if not text:
        return []

    lower_text = (
        text.lower()
    )

    contexts = []
    seen_contexts = set()

    for term in SEARCH_TERMS:
        term_lower = (
            term.lower()
        )

        start_position = 0

        while True:
            position = (
                lower_text.find(
                    term_lower,
                    start_position,
                )
            )

            if position < 0:
                break

            context_start = max(
                0,
                position - 300,
            )

            context_end = min(
                len(text),
                (
                    position
                    + len(term)
                    + 650
                ),
            )

            context = text[
                context_start:
                context_end
            ]

            context = (
                context
                .replace("\\/", "/")
                .replace("\n", " ")
                .replace("\r", " ")
                .replace("\t", " ")
            )

            context = re.sub(
                r"\s+",
                " ",
                context,
            ).strip()

            context_key = (
                source,
                term_lower,
                context[:250],
            )

            if (
                context_key
                not in seen_contexts
            ):
                seen_contexts.add(
                    context_key
                )

                contexts.append(
                    {
                        "source": (
                            source
                        ),
                        "term": (
                            term
                        ),
                        "context": (
                            context
                        ),
                    }
                )

            start_position = (
                position
                + len(term)
            )

            if len(contexts) >= 250:
                return contexts

    return contexts


# --------------------------------------------------
# ANALYSE ONE PAGE
# --------------------------------------------------
def analyse_page(
    session,
    url,
):
    response, error = safe_get(
        session=session,
        url=url,
    )

    if response is None:
        return {
            "requested_url": url,
            "final_url": "",
            "status": None,
            "content_type"           "response_length": 0,
            "scripts": [],
            "api_strings": [],
            "contexts": [],
            "body_preview": "",
            "error": error,
        }

    page_text = (
        response.text
        or ""
    )

    script_urls = (
        extract_script_urls(
            html_text=page_text,
            page_url=response.url,
        )
    )

    api_strings = (
        extract_api_like_strings(
            page_text
        )
    )

    contexts = find_contexts(
        text=page_text,
        source="PAGE HTML",
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
        "scripts": (
            script_urls
        ),
        "api_strings": (
            api_strings
        ),
        "contexts": (
            contexts
        ),
        "body_preview": (
            page_text[:5000]
        ),
        "error": None,
    }


# --------------------------------------------------
# ANALYSE ONE JAVASCRIPT FILE
# --------------------------------------------------
def analyse_script(
    session,
    script_url,
    referer,
):
    response, error = safe_get(
        session=session,
        url=script_url,
        referer=referer,
    )

    if response is None:
        return {
            "script_url": (
                script_url
            ),
            "status": None,
            "content_type": "",
            "response_length": 0,
            "api_strings": [],
            "contexts": [],
            "error": error,
        }

    script_text = (
        response.text
        or ""
    )

    api_strings = (
        extract_api_like_strings(
            script_text
        )
    )

    contexts = find_contexts(
        text=script_text,
        source=script_url,
    )

    return {
        "script_url": (
            script_url
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
        "api_strings": (
            api_strings
        ),
        "contexts": (
            contexts
        ),
        "error": None,
    }


# --------------------------------------------------
# COMPLETE ROUTE DISCOVERY
# --------------------------------------------------
def run_discovery():
    session = (
        create_session()
    )

    page_results = []

    for page_url in PAGE_URLS:
        page_result = (
            analyse_page(
                session=session,
                url=page_url,
            )
        )

        page_results.append(
            page_result
        )

    script_urls = []
    seen_script_urls = set()

    for page_result in page_results:
        page_scripts = (
            page_result.get(
                "scripts"
            )
            or []
        )

        for script_url in (
            page_scripts
        ):
            if (
                script_url
                in seen_script_urls
            ):
                continue

            seen_script_urls.add(
                script_url
            )

            script_urls.append(
                script_url
            )

    script_results = []

    referer = PAGE_URLS[0]

    for script_url in (
        script_urls
    ):
        script_result = (
            analyse_script(
                session=session,
                script_url=script_url,
                referer=referer,
            )
        )

        script_results.append(
            script_result
        )

    combined_api_strings = []
    seen_api_strings = set()

    for page_result in (
        page_results
    ):
        page_api_strings = (
            page_result.get(
                "api_strings"
            )
            or []
        )

        for value in (
            page_api_strings
        ):
            key = (
                "PAGE HTML",
                value,
            )

            if key in seen_api_strings:
                continue

            seen_api_strings.add(
                key
            )

            combined_api_strings.append(
                {
                    "source": (
                        "PAGE HTML"
                    ),
                    "value": (
                        value
                    ),
                }
            )

    for script_result in (
        script_results
    ):
        script_api_strings = (
            script_result.get(
                "api_strings"
            )
            or []
        )

        source = (
            script_result.get(
                "script_url",
                "",
            )
        )

        for value in (
            script_api_strings
        ):
            key = (
                source,
                value,
            )

            if key in seen_api_strings:
                continue

            seen_api_strings.add(
                key
            )

            combined_api_strings.append(
                {
                    "source": (
                        source
                    ),
                    "value": (
                        value
                    ),
                }
            )

    combined_contexts = []

    for page_result in (
        page_results
    ):
        combined_contexts.extend(
            page_result.get(
                "contexts"
            )
            or []
        )

    for script_result in (
        script_results
    ):
        combined_contexts.extend(
            script_result.get(
                "contexts"
            )
            or []
        )

    return {
        "pages": (
            page_results
        ),
        "scripts": (
            script_results
        ),
        "api_strings": (
            combined_api_strings
        ),
        "contexts": (
            combined_contexts
        ),
    }


# --------------------------------------------------
# STREAMLIT INTERFACE
# --------------------------------------------------
st.title(
    "ECHA Registrants route discovery"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.write(
    "This diagnostic inspects public ECHA CHEM "
    "page resources for the route used by the "
    "REACH Registrants view."
)

st.info(
    "This test does not use browser automation, "
    "does not handle CAPTCHA challenges, and does "
    "not attempt to bypass ECHA access controls."
)


# --------------------------------------------------
# TEST SUBSTANCE
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
    "Expected benchmark: the ECHA CHEM "
    "interface shows 42 registrants for "
    "this test substance."
)


# --------------------------------------------------
# RUN DISCOVERY
# --------------------------------------------------
run_button = st.button(
    "Discover registrants route",
    type="primary",
)


if run_button:
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
    # 1. PAGE RESULTS
    # ----------------------------------
    st.subheader(
        "1. Page requests"
    )

    page_rows = []

    pages = (
        result.get(
            "pages"
        )
        or []
    )

    for page in pages:
        scripts = (
            page.get(
                "scripts"
            )
            or []
        )

        contexts = (
            page.get(
                "contexts"
            )
            or []
        )

        page_rows.append(
            {
                "Requested URL": (
                    page.get(
                        "requested_url",
                        "",
                    )
                ),
                "HTTP": (
                    page.get(
                        "status"
                    )
                ),
                "Final URL": (
                    page.get(
                        "final_url",
                        "",
                    )
                ),
                "Content-Type": (
                    page.get(
                        "content_type",
                        "",
                    )
                ),
                "Bytes": (
                    page.get(
                        "response_length",
                        0,
                    )
                ),
                "JavaScript files": (
                    len(scripts)
                ),
                "Keyword contexts": (
                    len(contexts)
                ),
                "Error": (
                    page.get(
                        "error"
                    )
                ),
            }
        )

    if page_rows:
        page_dataframe = (
            pd.DataFrame(
                page_rows
            )
        )

        st.dataframe(
            page_dataframe,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No page request results "
            "were returned."
        )

    # ----------------------------------
    # 2. JAVASCRIPT RESULTS
    # ----------------------------------
    st.subheader(
        "2. JavaScript resources"
    )

    script_rows = []

    scripts = (
        result.get(
            "scripts"
        )
        or []
    )

    for script in scripts:
        api_strings = (
            script.get(
                "api_strings"
            )
            or []
        )

        contexts = (
            script.get(
                "contexts"
            )
            or []
        )

        script_rows.append(
            {
                "Script": (
                    script.get(
                        "script_url",
                        "",
                    )
                ),
                "HTTP": (
                    script.get(
                        "status"
                    )
                ),
                "Content-Type": (
                    script.get(
                        "content_type",
                        "",
                    )
                ),
                "Bytes": (
                    script.get(
                        "response_length",
                        0,
                    )
                ),
                "API-like strings": (
                    len(
                        api_strings
                    )
                ),
                "Keyword contexts": (
                    len(
                        contexts
                    )
                ),
                "Error": (
                    script.get(
                        "error"
                    )
                ),
            }
        )

    if script_rows:
        script_dataframe = (
            pd.DataFrame(
                script_rows
            )
        )

        st.dataframe(
            script_dataframe,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No JavaScript resource "
            "URLs were discovered."
        )

    # ----------------------------------
    # 3. API-LIKE STRINGS
    # ----------------------------------
    st.subheader(
        "3. API-like strings"
    )

    api_rows = (
        result.get(
            "api_strings"
        )
        or []
    )

    if api_rows:
        st.success(
            "API-like strings were found."
        )

        api_dataframe = (
            pd.DataFrame(
                api_rows
            )
        )

        st.dataframe(
            api_dataframe,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No explicit API-like "
            "strings were found."
        )

    # ----------------------------------
    # 4. REGISTRANT CODE CONTEXTS
    # ----------------------------------
    st.subheader(
        "4. Registrant-related "
        "code contexts"
    )

    contexts = (
        result.get(
            "contexts"
        )
        or []
    )

    if contexts:
        context_dataframe = (
            pd.DataFrame(
                contexts
            )
        )

        st.dataframe(
            context_dataframe,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No registrant-related "
            "frontend code context "
            "was found."
        )

    # ----------------------------------
    # RAW PAGE DIAGNOSTICS
    # ----------------------------------
    with st.expander(
        "Raw page diagnostics",
        expanded=False,
    ):
        for page in pages:
            st.markdown(
                "### Page"
            )

            st.code(
                page.get(
                    "requested_url",
                    "",
                ),
                language=None,
            )

            st.write(
                "HTTP: "
                f"{page.get('status')}"
            )

            st.write(
                "**Final URL:**"
            )

            st.code(
                page.get(
                    "final_url",
                    "",
                ),
                language=None,
            )

            st.write(
                "**Discovered scripts:**"
            )

            st.json(
                page.get(
                    "scripts"
                )
                or []
            )

            st.write(
                "**HTML preview:**"
            )

            st.code(
                page.get(
                    "body_preview",
                    "",
                ),
                language="html",
            )