import re
from html.parser import HTMLParser
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
CODE_VERSION = "ECHA_REGISTRANTS_ROUTE_DISCOVERY_V5"


# --------------------------------------------------
# TEST SUBSTANCE
# --------------------------------------------------
CAS_NUMBER = "128-37-0"
EC_NUMBER = "204-881-4"
RML_ID = "100.004.439"

ECHA_BASE_URL = "https://chem.echa.europa.eu"

OVERVIEW_URL = (
    f"{ECHA_BASE_URL}/"
    f"{RML_ID}/overview"
)

ASSET_OWNER_ROUTE = (
    f"{ECHA_BASE_URL}/"
    f"{RML_ID}/"
    "dossier-list/reach/asset-owner"
    f"?searchText={CAS_NUMBER}"
    "&pageIndex=1"
)


# --------------------------------------------------
# REQUEST SETTINGS
# --------------------------------------------------
CONNECT_TIMEOUT = 20
READ_TIMEOUT = 90

HEADERS = {
    "Accept": (
        "text/html,"
        "application/xhtml+xml,"
        "application/javascript,"
        "text/javascript,"
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
    "assetowner",
    "registrant",
    "registrants",
    "registrationnumber",
    "registrationnumbers",
    "dossier-list",
    "api-dossier",
    "rmlid",
    "legalentity",
    "legal-entity",
]


# --------------------------------------------------
# HTML RESOURCE PARSER
# --------------------------------------------------
class ECHAHTMLResourceParser(
    HTMLParser
):
    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )

        self.base_href = None
        self.script_sources = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        tag = (
            str(tag)
            .lower()
            .strip()
        )

        attributes = dict(
            attrs
        )

        if tag == "base":
            href = attributes.get(
                "href"
            )

            if href:
                self.base_href = (
                    str(href)
                    .strip()
                )

        if tag == "script":
            src = attributes.get(
                "src"
            )

            if src:
                clean_src = (
                    str(src)
                    .strip()
                )

                if clean_src:
                    self.script_sources.append(
                        clean_src
                    )


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
    accept=None,
):
    request_headers = {}

    if referer:
        request_headers[
            "Referer"
        ] = referer

    if accept:
        request_headers[
            "Accept"
        ] = accept

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
# PARSE APP SHELL
# --------------------------------------------------
def parse_app_shell(
    html_text,
    response_url,
):
    parser = (
        ECHAHTMLResourceParser()
    )

    try:
        parser.feed(
            html_text or ""
        )

    except Exception as error:
        return {
            "base_href": "",
            "base_url": "",
            "script_sources": [],
            "script_urls": [],
            "error": str(error),
        }

    base_href = (
        parser.base_href
        or "/"
    )

    base_url = urljoin(
        response_url,
        base_href,
    )

    script_urls = []
    seen_urls = set()

    for script_source in (
        parser.script_sources
    ):
        script_url = urljoin(
            base_url,
            script_source,
        )

        if script_url in seen_urls:
            continue

        seen_urls.add(
            script_url
        )

        script_urls.append(
            script_url
        )

    return {
        "base_href": (
            base_href
        ),
        "base_url": (
            base_url
        ),
        "script_sources": (
            parser.script_sources
        ),
        "script_urls": (
            script_urls
        ),
        "error": None,
    }


# --------------------------------------------------
# JAVASCRIPT VALIDATION
# --------------------------------------------------
def looks_like_javascript(
    response,
):
    if response is None:
        return False

    content_type = (
        response.headers.get(
            "content-type",
            "",
        )
        .lower()
    )

    text_start = (
        response.text[:1000]
        .lower()
    )

    if (
        "<!doctype html"
        in text_start
    ):
        return False

    if (
        "<html"
        in text_start
    ):
        return False

    if (
        "javascript"
        in content_type
    ):
        return True

    if (
        response.url.lower()
        .split("?")[0]
        .endswith(".js")
    ):
        return True

    return False


# --------------------------------------------------
# FIND SEARCH TERM CONTEXTS
# --------------------------------------------------
def find_term_contexts(
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
                position - 500,
            )

            context_end = min(
                len(text),
                (
                    position
                    + len(term)
                    + 1200
                ),
            )

            context = text[
                context_start:
                context_end
            ]

            context = (
                context
                .replace("\\/", "/")
                .replace(
                    "\\u002F",
                    "/",
                )
                .replace(
                    "\\u002f",
                    "/",
                )
            )

            context = re.sub(
                r"\s+",
                " ",
                context,
            ).strip()

            key = (
                term_lower,
                context[:400],
            )

            if key not in seen:
                seen.add(
                    key
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

            if len(contexts) >= 500:
                return contexts

    return contexts


# --------------------------------------------------
# EXTRACT ROUTE-LIKE STRINGS
# --------------------------------------------------
def extract_route_strings(
    text,
):
    if not text:
        return []

    results = []
    seen = set()

    quoted_strings = re.findall(
        r"""[^"']{3,500}["']""",
        text,
    )

    keywords = [
        "asset-owner",
        "assetowner",
        "registrant",
        "dossier-list",
        "api-dossier",
        "registrationnumber",
        "rmlid",
    ]

    for value in quoted_strings:
        clean_value = (
            value
            .replace("\\/", "/")
            .replace(
                "\\u002F",
                "/",
            )
            .replace(
                "\\u002f",
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
# LOAD APP SHELL
# --------------------------------------------------
def analyse_app_shell(
    session,
):
    response, error = safe_get(
        session=session,
        url=OVERVIEW_URL,
    )

    if response is None:
        return {
            "success": False,
            "status": None,
            "final_url": "",
            "content_type": "",
            "response_length": 0,
            "base_href": "",
            "base_url": "",
            "script_sources": [],
            "script_urls": [],
            "body_end": "",
            "error": error,
        }

    parsed = parse_app_shell(
        html_text=response.text,
        response_url=response.url,
    )

    return {
        "success": (
            response.status_code
            == 200
        ),
        "status": (
            response.status_code
        ),
        "final_url": (
            response.url
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
        "base_href": (
            parsed[
                "base_href"
            ]
        ),
        "base_url": (
            parsed[
                "base_url"
            ]
        ),
        "script_sources": (
            parsed[
                "script_sources"
            ]
        ),
        "script_urls": (
            parsed[
                "script_urls"
            ]
        ),
        "body_end": (
            response.text[
                -6000:
            ]
        ),
        "error": (
            parsed[
                "error"
            ]
        ),
    }


# --------------------------------------------------
# ANALYSE SCRIPT
# --------------------------------------------------
def analyse_script(
    session,
    script_url,
):
    response, error = safe_get(
        session=session,
        url=script_url,
        referer=OVERVIEW_URL,
        accept=(
            "application/javascript,"
            "text/javascript,"
            "*/*"
        ),
    )

    if response is None:
        return {
            "script_url": (
                script_url
            ),
            "status": None,
            "content_type": "",
            "response_length": 0,
            "javascript": False,
            "route_strings": [],
            "contexts": [],
            "error": error,
        }

    is_javascript = (
        looks_like_javascript(
            response
        )
    )

    script_text = (
        response.text
        or ""
    )

    route_strings = []

    contexts = []

    if is_javascript:
        route_strings = (
            extract_route_strings(
                script_text
            )
        )

        contexts = (
            find_term_contexts(
                text=script_text,
                source=script_url,
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
        "javascript": (
            is_javascript
        ),
        "route_strings": (
            route_strings
        ),
        "contexts": (
            contexts
        ),
        "error": None,
    }


# --------------------------------------------------
# ANALYSE HISTORICAL ASSET-OWNER ROUTE
# --------------------------------------------------
def analyse_asset_owner_route(
    session,
):
    response, error = safe_get(
        session=session,
        url=ASSET_OWNER_ROUTE,
        referer=OVERVIEW_URL,
    )

    if response is None:
        return {
            "status": None,
            "final_url": "",
            "content_type": "",
            "response_length": 0,
            "same_app_shell": False,
            "error": error,
        }

    text_start = (
        response.text[:1000]
        .lower()
    )

    same_app_shell = (
        "<!doctype html"
        in text_start
        and
        "echa chem"
        in response.text[:5000].lower()
    )

    return {
        "status": (
            response.status_code
        ),
        "final_url": (
            response.url
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
        "same_app_shell": (
            same_app_shell
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

    app_shell = (
        analyse_app_shell(
            session
        )
    )

    script_results = []

    for script_url in (
        app_shell.get(
            "script_urls"
        )
        or []
    ):
        script_result = (
            analyse_script(
                session=session,
                script_url=script_url,
            )
        )

        script_results.append(
            script_result
        )

    all_route_strings = []
    seen_route_strings = set()

    all_contexts = []

    for script in script_results:
        for route_string in (
            script.get(
                "route_strings"
            )
            or []
        ):
            key = (
                route_string
            )

            if (
                key
                in seen_route_strings
            ):
                continue

            seen_route_strings.add(
                key
            )

            all_route_strings.append(
                {
                    "source": (
                        script[
                            "script_url"
                        ]
                    ),
                    "route_string": (
                        route_string
                    ),
                }
            )

        all_contexts.extend(
            script.get(
                "contexts"
            )
            or []
        )

    asset_owner_result = (
        analyse_asset_owner_route(
            session
        )
    )

    return {
        "app_shell": (
            app_shell
        ),
        "scripts": (
            script_results
        ),
        "route_strings": (
            all_route_strings
        ),
        "contexts": (
            all_contexts
        ),
        "asset_owner": (
            asset_owner_result
        ),
    }


# --------------------------------------------------
# STREAMLIT UI
# --------------------------------------------------
st.title(
    "ECHA Registrants route discovery"
)

st.caption(
    f"Version: "
    f"{CODE_VERSION}"
)

st.write(
    "This version reads the ECHA CHEM "
    "application shell with an HTML parser, "
    "loads the real JavaScript bundles, and "
    "searches them for the Registrants data route."
)

st.info(
    "V5 does not use Playwright or Selenium "
    "and does not attempt to bypass ECHA "
    "access controls."
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
    "Expected benchmark from ECHA CHEM: "
    "**42 registrants**."
)


# --------------------------------------------------
# RUN
# --------------------------------------------------
if st.button(
    "Discover registrants route",
    type="primary",
):
    with st.spinner(
        "Loading ECHA CHEM application "
        "resources..."
    ):
        result = (
            run_discovery()
        )

    st.success(
        "Discovery completed."
    )

    app_shell = (
        result[
            "app_shell"
        ]
    )

    # ----------------------------------
    # 1. APP SHELL
    # ----------------------------------
    st.subheader(
        "1. ECHA application shell"
    )

    shell_col1, shell_col2, shell_col3 = (
        st.columns(3)
    )

    shell_col1.metric(
        "HTTP",
        (
            app_shell[
                "status"
            ]
            if (
                app_shell[
                    "status"
                ]
                is not None
            )
            else
            "Error"
        ),
    )

    shell_col2.metric(
        "HTML bytes",
        (
            app_shell[
                "response_length"
            ]
        ),
    )

    shell_col3.metric(
        "Scripts found",
        len(
            app_shell.get(
                "script_urls"
            )
            or []
        ),
    )

    st.write(
        "**Base href:**"
    )

    st.code(
        app_shell.get(
            "base_href",
            "",
        ),
        language=None,
    )

    st.write(
        "**Resolved base URL:**"
    )

    st.code(
        app_shell.get(
            "base_url",
            "",
        ),
        language=None,
    )

    st.write(
        "**Raw script src values:**"
    )

    st.json(
        app_shell.get(
            "script_sources"
        )
        or []
    )

    st.write(
        "**Resolved script URLs:**"
    )

    st.json(
        app_shell.get(
            "script_urls"
        )
        or []
    )

    if app_shell.get(
        "error"
    ):
        st.error(
            app_shell[
                "error"
            ]
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
                "Confirmed JavaScript": (
                    script.get(
                        "javascript",
                        False,
                    )
                ),
                "Route strings": (
                    len(
                        script.get(
                            "route_strings"
                        )
                        or []
                    )
                ),
                "Contexts": (
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
            "were discovered."
        )

    # ----------------------------------
    # 3. ROUTE STRINGS
    # ----------------------------------
    st.subheader(
        "3. Registrant route strings"
    )

    route_strings = (
        result.get(
            "route_strings"
        )
        or []
    )

    if route_strings:
        st.success(
            "Registrant-related route "
            "strings were found."
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
            "No registrant route strings "
            "were found in the JavaScript."
        )

    # ----------------------------------
    # 4. CONTEXTS
    # ----------------------------------
    st.subheader(
        "4. Registrant code contexts"
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
            "No registrant-related "
            "JavaScript contexts were found."
        )

    # ----------------------------------
    # 5. ASSET-OWNER
    # ----------------------------------
    st.subheader(
        "5. Historical asset-owner route"
    )

    asset_owner = (
        result[
            "asset_owner"
        ]
    )

    a1, a2, a3 = (
        st.columns(3)
    )

    a1.metric(
        "HTTP",
        (
            asset_owner[
                "status"
            ]
            if (
                asset_owner[
                    "status"
                ]
                is not None
            )
            else
            "Error"
        ),
    )

    a2.metric(
        "Bytes",
        asset_owner[
            "response_length"
        ],
    )

    a3.metric(
        "Returns app shell",
        (
            "Yes"
            if asset_owner[
                "same_app_shell"
            ]
            else
            "No"
        ),
    )

    st.write(
        "**Route:**"
    )

    st.code(
        ASSET_OWNER_ROUTE,
        language=None,
    )

    # ----------------------------------
    # RAW HTML END
    # ----------------------------------
    with st.expander(
        "HTML end diagnostic",
        expanded=False,
    ):
        st.write(
            "The end of the HTML is shown "
            "because Angular normally places "
            "its script tags there."
        )

        st.code(
            app_shell.get(
                "body_end",
                "",
            ),
            language="html",
        )