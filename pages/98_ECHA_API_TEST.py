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
CODE_VERSION = "ECHA_REGISTRANTS_ROUTE_DISCOVERY_V4"


# --------------------------------------------------
# KNOWN TEST SUBSTANCE
# --------------------------------------------------
CAS_NUMBER = "128-37-0"
EC_NUMBER = "204-881-4"
RML_ID = "100.004.439"

ECHA_BASE_URL = "https://chem.echa.europa.eu"


# --------------------------------------------------
# KNOWN ECHA PAGES
# --------------------------------------------------
OVERVIEW_URL = (
    f"{ECHA_BASE_URL}/"
    f"{RML_ID}/overview"
)

DOSSIERS_URL = (
    f"{ECHA_BASE_URL}/"
    f"{RML_ID}/dossiers"
)

REACH_URL = (
    f"{ECHA_BASE_URL}/"
    f"{RML_ID}/dossiers/reach"
)


# --------------------------------------------------
# IMPORTANT HISTORICAL ROUTE
#
# This route already existed in the user's earlier
# ECHA implementation.
#
# We are NOT inventing this route.
# --------------------------------------------------
ASSET_OWNER_URL = (
    f"{ECHA_BASE_URL}/"
    f"{RML_ID}/"
    "dossier-list/reach/asset-owner"
    f"?searchText={CAS_NUMBER}"
    "&pageIndex=1"
)


PAGE_URLS = [
    {
        "name": "Substance overview",
        "url": OVERVIEW_URL,
    },
    {
        "name": "Dossiers",
        "url": DOSSIERS_URL,
    },
    {
        "name": "REACH registrations",
        "url": REACH_URL,
    },
    {
        "name": "REACH asset owner / registrant route",
        "url": ASSET_OWNER_URL,
    },
]


# --------------------------------------------------
# REQUEST SETTINGS
# --------------------------------------------------
CONNECT_TIMEOUT = 20
READ_TIMEOUT = 90

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
    "asset-owner",
    "assetOwner",
    "registrant",
    "registrants",
    "registration",
    "registrationNumber",
    "registrationNumbers",
    "legalEntity",
    "legal-entity",
    "rmlId",
    "dossier-list",
    "owner",
    "api-dossier",
    "/api-",
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

        return response, None

    except requests.RequestException as error:
        return None, str(error)


# --------------------------------------------------
# HTML BASE HREF
# --------------------------------------------------
def extract_base_href(
    html_text,
    page_url,
):
    if not html_text:
        return page_url

    match = re.search(
        (
            r"<base\b[^>]*"
            r"\bhref\s*=\s*"
            r"[^\"']+[\"']"
        ),
        html_text,
        flags=re.IGNORECASE,
    )

    if not match:
        return page_url

    base_href = (
        match.group(1)
        .strip()
    )

    if not base_href:
        return page_url

    return urljoin(
        page_url,
        base_href,
    )


# --------------------------------------------------
# SCRIPT EXTRACTION
# --------------------------------------------------
def extract_script_urls(
    html_text,
    page_url,
):
    if not html_text:
        return [], page_url

    base_url = (
        extract_base_href(
            html_text=html_text,
            page_url=page_url,
        )
    )

    script_sources = re.findall(
        (
            r"<script\b[^>]*"
            r"\bsrc\s*=\s*"
            r"[^\"']+[\"']"
            r"[^>]*>"
        ),
        html_text,
        flags=re.IGNORECASE,
    )

    script_urls = []
    seen_urls = set()

    for source in script_sources:
        source = (
            str(source)
            .strip()
        )

        if not source:
            continue

        full_url = urljoin(
            base_url,
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

    return script_urls, base_url


# --------------------------------------------------
# API / ROUTE STRING EXTRACTION
# --------------------------------------------------
def extract_interesting_strings(
    text,
):
    if not text:
        return []

    patterns = [
        # API paths
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

        # dossier related paths
        (
            r"[\"']"
            r"([^\"']*dossier-list[^\"']*)"
            r"[\"']"
        ),

        # asset-owner paths
        (
            r"[\"']"
            r"([^\"']*asset-owner[^\"']*)"
            r"[\"']"
        ),

        # registrant strings
        (
            r"[\"']"
            r"([^\"']*registrant[^\"']*)"
            r"[\"']"
        ),

        # versioned API paths
        (
            r"[\"']"
            r"([^\"']*/v1/[^\"']*)"
            r"[\"']"
        ),
    ]

    results = []
    seen = set()

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
                .replace("\\u002F", "/")
                .strip()
            )

            if not value:
                continue

            if len(value) > 1000:
                continue

            if value in seen:
                continue

            seen.add(
                value
            )

            results.append(
                value
            )

    return results


# --------------------------------------------------
# CONTEXT SEARCH
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
    seen = set()

    for term in SEARCH_TERMS:
        term_lower = (
            term.lower()
        )

        start = 0

        while True:
            position = (
                lower_text.find(
                    term_lower,
                    start,
                )
            )

            if position < 0:
                break

            context_start = max(
                0,
                position - 400,
            )

            context_end = min(
                len(text),
                (
                    position
                    + len(term)
                    + 900
                ),
            )

            context = text[
                context_start:
                context_end
            ]

            context = (
                context
                .replace("\\/", "/")
                .replace("\\u002F", "/")
                .replace("\n", " ")
                .replace("\r", " ")
                .replace("\t", " ")
            )

            context = re.sub(
                r"\s+",
                " ",
                context,
            ).strip()

            key = (
                source,
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

            start = (
                position
                + len(term)
            )

            if len(contexts) >= 300:
                return contexts

    return contexts


# --------------------------------------------------
# ANALYSE PAGE
# --------------------------------------------------
def analyse_page(
    session,
    page_name,
    url,
):
    response, error = (
        safe_get(
            session=session,
            url=url,
        )
    )

    if response is None:
        return {
            "name": page_name,
            "requested_url": url,
            "final_url": "",
            "status": None,
            "content_type": "",
            "response_length": 0,
            "base_url": "",
            "scripts": [],
            "interesting_strings": [],
            "contexts": [],
            "body_preview": "",
            "error": error,
        }

    page_text = (
        response.text
        or ""
    )

    (
        script_urls,
        base_url,
    ) = extract_script_urls(
        html_text=page_text,
        page_url=response.url,
    )

    return {
        "name": page_name,
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
        "response_length": (
            len(
                response.content
            )
        ),
        "base_url": (
            base_url
        ),
        "scripts": (
            script_urls
        ),
        "interesting_strings": (
            extract_interesting_strings(
                page_text
            )
        ),
        "contexts": (
            find_contexts(
                text=page_text,
                source=page_name,
            )
        ),
        "body_preview": (
            page_text[:8000]
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
    response, error = (
        safe_get(
            session=session,
            url=script_url,
            referer=referer,
        )
    )

    if response is None:
        return {
            "script_url": script_url,
            "status": None,
            "content_type": "",
            "response_length": 0,
            "looks_like_javascript": False,
            "interesting_strings": [],
            "contexts": [],
            "error": error,
        }

    text = (
        response.text
        or ""
    )

    content_type = (
        response.headers.get(
            "content-type",
            "",
        )
    )

    looks_like_javascript = (
        "javascript"
        in content_type.lower()
        or
        (
            "<html"
            not in text[:1000].lower()
            and
            "<!doctype html"
            not in text[:1000].lower()
        )
    )

    return {
        "script_url": (
            script_url
        ),
        "status": (
            response.status_code
        ),
        "content_type": (
            content_type
        ),
        "response_length": (
            len(
                response.content
            )
        ),
        "looks_like_javascript": (
            looks_like_javascript
        ),
        "interesting_strings": (
            extract_interesting_strings(
                text
            )
            if looks_like_javascript
            else []
        ),
        "contexts": (
            find_contexts(
                text=text,
                source=script_url,
            )
            if looks_like_javascript
            else []
        ),
        "error": None,
    }


# --------------------------------------------------
# RUN DISCOVERY
# --------------------------------------------------
def run_discovery():
    session = (
        create_session()
    )

    page_results = []

    for page in PAGE_URLS:
        result = (
            analyse_page(
                session=session,
                page_name=(
                    page["name"]
                ),
                url=(
                    page["url"]
                ),
            )
        )

        page_results.append(
            result
        )

    script_urls = []
    seen_scripts = set()

    for page in page_results:
        for script_url in (
            page.get(
                "scripts"
            )
            or []
        ):
            if script_url in seen_scripts:
                continue

            seen_scripts.add(
                script_url
            )

            script_urls.append(
                script_url
            )

    script_results = []

    for script_url in script_urls:
        script_result = (
            analyse_script(
                session=session,
                script_url=script_url,
                referer=OVERVIEW_URL,
            )
        )

        script_results.append(
            script_result
        )

    combined_strings = []
    seen_strings = set()

    for page in page_results:
        for value in (
            page.get(
                "interesting_strings"
            )
            or []
        ):
            key = (
                page["name"],
                value,
            )

            if key in seen_strings:
                continue

            seen_strings.add(
                key
            )

            combined_strings.append(
                {
                    "source": (
                        page["name"]
                    ),
                    "value": value,
                }
            )

    for script in script_results:
        for value in (
            script.get(
                "interesting_strings"
            )
            or []
        ):
            source = (
                script.get(
                    "script_url",
                    "",
                )
            )

            key = (
                source,
                value,
            )

            if key in seen_strings:
                continue

            seen_strings.add(
                key
            )

            combined_strings.append(
                {
                    "source": source,
                    "value": value,
                }
            )

    combined_contexts = []

    for page in page_results:
        combined_contexts.extend(
            page.get(
                "contexts"
            )
            or []
        )

    for script in script_results:
        combined_contexts.extend(
            script.get(
                "contexts"
            )
            or []
        )

    return {
        "pages": page_results,
        "scripts": script_results,
        "strings": combined_strings,
        "contexts": combined_contexts,
    }


# --------------------------------------------------
# UI
# --------------------------------------------------
st.title(
    "ECHA Registrants route discovery"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.write(
    "This version analyses the ECHA CHEM "
    "REACH registrations frontend and the "
    "historical asset-owner route."
)

st.info(
    "The goal is to identify the existing "
    "ECHA route that supplies the Registrants "
    "table. No browser automation or access "
    "control bypass is used."
)


# --------------------------------------------------
# TEST DATA
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
    "Expected ECHA CHEM benchmark: "
    "**42 registrants**."
)

st.write(
    "Known visible examples include "
    "**3M Belgium**, **Afton Chemical** "
    "and **BASF SE**."
)


# --------------------------------------------------
# RUN
# --------------------------------------------------
if st.button(
    "Discover registrants route",
    type="primary",
):
    with st.spinner(
        "Inspecting ECHA CHEM pages and "
        "JavaScript application resources..."
    ):
        result = (
            run_discovery()
        )

    st.success(
        "Discovery completed."
    )

    # ----------------------------------
    # 1. PAGE REQUESTS
    # ----------------------------------
    st.subheader(
        "1. Page requests"
    )

    page_rows = []

    for page in (
        result.get(
            "pages"
        )
        or []
    ):
        page_rows.append(
            {
                "Page": (
                    page.get(
                        "name",
                        "",
                    )
                ),
                "HTTP": (
                    page.get(
                        "status"
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
                "Base URL": (
                    page.get(
                        "base_url",
                        "",
                    )
                ),
                "JavaScript files": (
                    len(
                        page.get(
                            "scripts"
                        )
                        or []
                    )
                ),
                "Relevant strings": (
                    len(
                        page.get(
                            "interesting_strings"
                        )
                        or []
                    )
                ),
                "Error": (
                    page.get(
                        "error"
                    )
                ),
            }
        )

    st.dataframe(
        pd.DataFrame(
            page_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    # ----------------------------------
    # 2. JAVASCRIPT
    # ----------------------------------
    st.subheader(
        "2. JavaScript resources"
    )

    script_rows = []

    for script in (
        result.get(
            "scripts"
        )
        or []
    ):
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
                "JavaScript": (
                    script.get(
                        "looks_like_javascript",
                        False,
                    )
                ),
                "Relevant strings": (
                    len(
                        script.get(
                            "interesting_strings"
                        )
                        or []
                    )
                ),
                "Relevant contexts": (
                    len(
                        script.get(
                            "contexts"
                        )
                        or []
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
        st.dataframe(
            pd.DataFrame(
                script_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No JavaScript resources "
            "were found."
        )

    # ----------------------------------
    # 3. ROUTE / API STRINGS
    # ----------------------------------
    st.subheader(
        "3. Registrant/API route strings"
    )

    route_strings = (
        result.get(
            "strings"
        )
        or []
    )

    if route_strings:
        st.success(
            "Relevant route strings "
            "were found."
        )

        st.dataframe(
            pd.DataFrame(
                route_strings
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No registrant/API route "
            "strings were found."
        )

    # ----------------------------------
    # 4. CODE CONTEXTS
    # ----------------------------------
    st.subheader(
        "4. Registrant/API code contexts"
    )

    contexts = (
        result.get(
            "contexts"
        )
        or []
    )

    if contexts:
        st.dataframe(
            pd.DataFrame(
                contexts
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No relevant frontend "
            "code contexts were found."
        )

    # ----------------------------------
    # 5. ASSET OWNER DIAGNOSTIC
    # ----------------------------------
    st.subheader(
        "5. Asset-owner route diagnostic"
    )

    asset_owner_page = next(
        (
            page
            for page
            in result.get(
                "pages",
                [],
            )
            if (
                page.get(
                    "name"
                )
                ==
                "REACH asset owner / "
                "registrant route"
            )
        ),
        None,
    )

    if asset_owner_page:
        st.write(
            "**HTTP status:** "
            f"{asset_owner_page.get('status')}"
        )

        st.write(
            "**Final URL:**"
        )

        st.code(
            asset_owner_page.get(
                "final_url",
                "",
            ),
            language=None,
        )

        st.write(
            "**Base URL:**"
        )

        st.code(
            asset_owner_page.get(
                "base_url",
                "",
            ),
            language=None,
        )

        st.write(
            "**Relevant strings on page:**"
        )

        st.json(
            asset_owner_page.get(
                "interesting_strings"
            )
            or []
        )

    # ----------------------------------
    # RAW DIAGNOSTICS
    # ----------------------------------
    with st.expander(
        "Raw page diagnostics",
        expanded=False,
    ):
        for page in (
            result.get(
                "pages"
            )
            or []
        ):
            st.markdown(
                f"### {page.get('name', 'Page')}"
            )

            st.write(
                "**Requested URL:**"
            )

            st.code(
                page.get(
                    "requested_url",
                    "",
                ),
                language=None,
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
                "**Discovered JavaScript:**"
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