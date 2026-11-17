import re
from collections import deque
from html.parser import HTMLParser
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
CODE_VERSION = "ECHA_REGISTRANTS_ROUTE_DISCOVERY_V6"


# --------------------------------------------------
# KNOWN TEST SUBSTANCE
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
CONNECT_TIMEOUT_SECONDS = 20
READ_TIMEOUT_SECONDS = 90

MAX_JAVASCRIPT_FILES = 100
MAX_CONTEXTS_PER_FILE = 100
MAX_ROUTE_STRINGS_PER_FILE = 200

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
    "asset owner",
    "registrant",
    "registrants",
    "registrationnumber",
    "registrationnumbers",
    "registration number",
    "dossier-list",
    "api-dossier",
    "rmlid",
    "legalentity",
    "legal-entity",
    "legal entity",
    "assetownerlist",
    "ownerlist",
]


# --------------------------------------------------
# ROUTE STRING KEYWORDS
# --------------------------------------------------
ROUTE_KEYWORDS = [
    "asset-owner",
    "assetowner",
    "registrant",
    "dossier-list",
    "api-dossier",
    "registrationnumber",
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
        self.preload_sources = []

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

        elif tag == "script":
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

        elif tag == "link":
            rel = (
                str(
                    attributes.get(
                        "rel",
                        "",
                    )
                )
                .lower()
                .strip()
            )

            href = attributes.get(
                "href"
            )

            if not href:
                return

            clean_href = (
                str(href)
                .strip()
            )

            if not clean_href:
                return

            if (
                "modulepreload" in rel
                or
                clean_href.lower()
                .split("?")[0]
                .endswith(".js")
            ):
                self.preload_sources.append(
                    clean_href
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
                CONNECT_TIMEOUT_SECONDS,
                READ_TIMEOUT_SECONDS,
            ),
            allow_redirects=True,
        )

        return response, None

    except requests.RequestException as error:
        return None, str(error)


# --------------------------------------------------
# URL HELPERS
# --------------------------------------------------
def is_http_url(
    value,
):
    try:
        parsed = urlparse(
            value
        )

        return (
            parsed.scheme
            in {
                "http",
                "https",
            }
            and
            bool(
                parsed.netloc
            )
        )

    except Exception:
        return False


def is_allowed_javascript_url(
    url,
):
    if not is_http_url(
        url
    ):
        return False

    parsed = urlparse(
        url
    )

    hostname = (
        parsed.hostname
        or ""
    ).lower()

    allowed_hosts = {
        "chem.echa.europa.eu",
        "webtools.europa.eu",
    }

    if hostname not in allowed_hosts:
        return False

    path = (
        parsed.path
        or ""
    ).lower()

    return path.endswith(
        ".js"
    )


def normalise_javascript_url(
    base_url,
    candidate,
):
    if candidate is None:
        return ""

    candidate = (
        str(candidate)
        .strip()
        .strip(
            "\"'"
        )
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

    if not candidate:
        return ""

    if candidate.startswith(
        "data:"
    ):
        return ""

    if candidate.startswith(
        "blob:"
    ):
        return ""

    candidate_url = urljoin(
        base_url,
        candidate,
    )

    if not is_allowed_javascript_url(
        candidate_url
    ):
        return ""

    return candidate_url


# --------------------------------------------------
# PARSE ECHA HTML SHELL
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
            html_text
            or ""
        )

    except Exception as error:
        return {
            "base_href": "",
            "base_url": "",
            "script_sources": [],
            "preload_sources": [],
            "script_urls": [],
            "error": str(
                error
            ),
        }

    base_href = (
        parser.base_href
        or "/"
    )

    base_url = urljoin(
        response_url,
        base_href,
    )

    raw_sources = (
        list(
            parser.script_sources
        )
        +
        list(
            parser.preload_sources
        )
    )

    script_urls = []
    seen_urls = set()

    for source in raw_sources:
        script_url = (
            normalise_javascript_url(
                base_url=base_url,
                candidate=source,
            )
        )

        if not script_url:
            continue

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
        "preload_sources": (
            parser.preload_sources
        ),
        "script_urls": (
            script_urls
        ),
        "error": None,
    }


# --------------------------------------------------
# JAVASCRIPT RESPONSE VALIDATION
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
        response.text[:1500]
        .lower()
    )

    if (
        "<!doctype html"
        in text_start
    ):
        return False

    if re.search(
        r"<html\b",
        text_start,
    ):
        return False

    if (
        "javascript"
        in content_type
    ):
        return True

    request_path = (
        urlparse(
            response.url
        ).path.lower()
    )

    if request_path.endswith(
        ".js"
    ):
        return True

    return False


# --------------------------------------------------
# JAVASCRIPT REFERENCE EXTRACTION
# --------------------------------------------------
def extract_javascript_references(
    script_text,
    script_url,
):
    if not script_text:
        return []

    candidates = []

    # Quoted references ending in .js.
    quoted_patterns = [
        (
            r"""["']"""
            r"""([^"']+\.js"""
            r"""(?:\?[^"']*)?)"""
            r"""["']"""
        ),
        (
            r"""import\s*\(\s*"""
            r"""["']"""
            r"""([^"']+)"""
            r"""["']"""
            r"""\s*\)"""
        ),
        (
            r"""from\s+"""
            r"""["']"""
            r"""([^"']+)"""
            r"""["']"""
        ),
    ]

    for pattern in quoted_patterns:
        matches = re.findall(
            pattern,
            script_text,
            flags=re.IGNORECASE,
        )

        candidates.extend(
            matches
        )

    # Angular chunk names can sometimes occur outside
    # ordinary quoted import statements.
    chunk_patterns = [
        (
            r"chunk-"
            r"[A-Za-z0-9_-]+"
            r"\.js"
        ),
        (
            r"main-"
            r"[A-Za-z0-9_-]+"
            r"\.js"
        ),
        (
            r"polyfills-"
            r"[A-Za-z0-9_-]+"
            r"\.js"
        ),
        (
            r"runtime-"
            r"[A-Za-z0-9_-]+"
            r"\.js"
        ),
    ]

    for pattern in chunk_patterns:
        candidates.extend(
            re.findall(
                pattern,
                script_text,
                flags=re.IGNORECASE,
            )
        )

    resolved_urls = []
    seen_urls = set()

    for candidate in candidates:
        resolved_url = (
            normalise_javascript_url(
                base_url=script_url,
                candidate=candidate,
            )
        )

        if not resolved_url:
            continue

        if resolved_url in seen_urls:
            continue

        seen_urls.add(
            resolved_url
        )

        resolved_urls.append(
            resolved_url
        )

    return resolved_urls


# --------------------------------------------------
# ROUTE STRING EXTRACTION
# --------------------------------------------------
def extract_route_strings(
    script_text,
):
    if not script_text:
        return []

    results = []
    seen = set()

    # First analyse quoted strings.
    quoted_strings = re.findall(
        r"""[^"']{2,800}["']""",
        script_text,
    )

    for value in quoted_strings:
        clean_value = (
            str(value)
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
            .strip()
        )

        lower_value = (
            clean_value.lower()
        )

        if not any(
            keyword in lower_value
            for keyword
            in ROUTE_KEYWORDS
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

        if (
            len(results)
            >= MAX_ROUTE_STRINGS_PER_FILE
        ):
            return results

    # Also retain short unquoted fragments containing
    # one of the critical route terms.
    for keyword in ROUTE_KEYWORDS:
        pattern = (
            r"[A-Za-z0-9_./?=&:{}\-]{0,250}"
            + re.escape(
                keyword
            )
            + r"[A-Za-z0-9_./?=&:{}\-]{0,500}"
        )

        matches = re.findall(
            pattern,
            script_text,
            flags=re.IGNORECASE,
        )

        for match in matches:
            clean_value = (
                str(match)
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
                .strip()
            )

            if not clean_value:
                continue

            if clean_value in seen:
                continue

            seen.add(
                clean_value
            )

            results.append(
                clean_value
            )

            if (
                len(results)
                >= MAX_ROUTE_STRINGS_PER_FILE
            ):
                return results

    return results


# --------------------------------------------------
# SEARCH TERM CONTEXTS
# --------------------------------------------------
def find_term_contexts(
    script_text,
    source,
):
    if not script_text:
        return []

    lower_text = (
        script_text.lower()
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
                position - 600,
            )

            context_end = min(
                len(
                    script_text
                ),
                (
                    position
                    + len(term)
                    + 1600
                ),
            )

            context = (
                script_text[
                    context_start:
                    context_end
                ]
            )

            context = (
                context
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

            context = re.sub(
                r"\s+",
                " ",
                context,
            ).strip()

            context_key = (
                term_lower,
                context[:500],
            )

            if context_key not in seen:
                seen.add(
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

            if (
                len(contexts)
                >= MAX_CONTEXTS_PER_FILE
            ):
                return contexts

    return contexts


# --------------------------------------------------
# LOAD APPLICATION SHELL
# --------------------------------------------------
def load_app_shell(
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
            "preload_sources": [],
            "script_urls": [],
            "body_end": "",
            "error": error,
        }

    parsed_shell = (
        parse_app_shell(
            html_text=(
                response.text
            ),
            response_url=(
                response.url
            ),
        )
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
        "response_length": (
            len(
                response.content
            )
        ),
        "base_href": (
            parsed_shell[
                "base_href"
            ]
        ),
        "base_url": (
            parsed_shell[
                "base_url"
            ]
        ),
        "script_sources": (
            parsed_shell[
                "script_sources"
            ]
        ),
        "preload_sources": (
            parsed_shell[
                "preload_sources"
            ]
        ),
        "script_urls": (
            parsed_shell[
                "script_urls"
            ]
        ),
        "body_end": (
            response.text[
                -8000:
            ]
        ),
        "error": (
            parsed_shell[
                "error"
            ]
        ),
    }


# --------------------------------------------------
# ANALYSE ONE JAVASCRIPT FILE
# --------------------------------------------------
def analyse_javascript_file(
    session,
    script_url,
    parent_url=None,
    depth=0,
):
    response, error = safe_get(
        session=session,
        url=script_url,
        referer=(
            parent_url
            or OVERVIEW_URL
        ),
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
            "parent_url": (
                parent_url
                or ""
            ),
            "depth": (
                depth
            ),
            "status": None,
            "content_type": "",
            "response_length": 0,
            "javascript": False,
            "child_scripts": [],
            "route_strings": [],
            "contexts": [],
            "source_preview": "",
            "error": error,
        }

    javascript = (
        looks_like_javascript(
            response
        )
    )

    script_text = (
        response.text
        or ""
    )

    child_scripts = []
    route_strings = []
    contexts = []

    if javascript:
        child_scripts = (
            extract_javascript_references(
                script_text=script_text,
                script_url=(
                    response.url
                ),
            )
        )

        route_strings = (
            extract_route_strings(
                script_text
            )
        )

        contexts = (
            find_term_contexts(
                script_text=script_text,
                source=(
                    response.url
                ),
            )
        )

    return {
        "script_url": (
            response.url
        ),
        "parent_url": (
            parent_url
            or ""
        ),
        "depth": (
            depth
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
            javascript
        ),
        "child_scripts": (
            child_scripts
        ),
        "route_strings": (
            route_strings
        ),
        "contexts": (
            contexts
        ),
        "source_preview": (
            script_text[:12000]
            if javascript
            else ""
        ),
        "error": None,
    }


# --------------------------------------------------
# RECURSIVE JAVASCRIPT DISCOVERY
# --------------------------------------------------
def discover_javascript_tree(
    session,
    initial_script_urls,
):
    pending = deque()

    for script_url in (
        initial_script_urls
    ):
        pending.append(
            {
                "url": (
                    script_url
                ),
                "parent_url": (
                    OVERVIEW_URL
                ),
                "depth": 0,
            }
        )

    visited = set()
    results = []

    while (
        pending
        and
        len(visited)
        < MAX_JAVASCRIPT_FILES
    ):
        pending_item = (
            pending.popleft()
        )

        script_url = (
            pending_item[
                "url"
            ]
        )

        if script_url in visited:
            continue

        visited.add(
            script_url
        )

        result = (
            analyse_javascript_file(
                session=session,
                script_url=(
                    script_url
                ),
                parent_url=(
                    pending_item[
                        "parent_url"
                    ]
                ),
                depth=(
                    pending_item[
                        "depth"
                    ]
                ),
            )
        )

        results.append(
            result
        )

        if not result[
            "javascript"
        ]:
            continue

        for child_url in (
            result.get(
                "child_scripts"
            )
            or []
        ):
            if child_url in visited:
                continue

            pending.append(
                {
                    "url": (
                        child_url
                    ),
                    "parent_url": (
                        result[
                            "script_url"
                        ]
                    ),
                    "depth": (
                        result[
                            "depth"
                        ]
                        + 1
                    ),
                }
            )

    return results


# --------------------------------------------------
# ASSET-OWNER ROUTE CHECK
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
            "returns_app_shell": False,
            "error": error,
        }

    text_start = (
        response.text[:5000]
        .lower()
    )

    returns_app_shell = (
        "<!doctype html"
        in text_start
        and
        "echa chem"
        in text_start
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
        "returns_app_shell": (
            returns_app_shell
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

    app_shell = (
        load_app_shell(
            session
        )
    )

    initial_scripts = (
        app_shell.get(
            "script_urls"
        )
        or []
    )

    javascript_results = (
        discover_javascript_tree(
            session=session,
            initial_script_urls=(
                initial_scripts
            ),
        )
    )

    route_rows = []
    seen_route_rows = set()

    context_rows = []
    seen_context_rows = set()

    for script in (
        javascript_results
    ):
        source = (
            script.get(
                "script_url",
                "",
            )
        )

        for route_string in (
            script.get(
                "route_strings"
            )
            or []
        ):
            key = (
                source,
                route_string,
            )

            if key in seen_route_rows:
                continue

            seen_route_rows.add(
                key
            )

            route_rows.append(
                {
                    "source": (
                        source
                    ),
                    "depth": (
                        script.get(
                            "depth",
                            0,
                        )
                    ),
                    "route_string": (
                        route_string
                    ),
                }
            )

        for context in (
            script.get(
                "contexts"
            )
            or []
        ):
            key = (
                context.get(
                    "source",
                    "",
                ),
                context.get(
                    "term",
                    "",
                ),
                context.get(
                    "context",
                    "",
                )[:500],
            )

            if key in seen_context_rows:
                continue

            seen_context_rows.add(
                key
            )

            context_rows.append(
                context
            )

    asset_owner = (
        analyse_asset_owner_route(
            session
        )
    )

    return {
        "app_shell": (
            app_shell
        ),
        "javascript_results": (
            javascript_results
        ),
        "route_rows": (
            route_rows
        ),
        "context_rows": (
            context_rows
        ),
        "asset_owner": (
            asset_owner
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
    "V6 reads the ECHA CHEM application shell, "
    "recursively follows referenced JavaScript "
    "chunks, and searches those chunks for the "
    "route used by the REACH Registrants table."
)

st.info(
    "This diagnostic uses ordinary public HTTP "
    "requests. It does not use Playwright, Selenium, "
    "CAPTCHA handling, authentication bypasses or "
    "anti-bot workarounds."
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
    "Expected benchmark from the public "
    "ECHA CHEM interface: **42 registrants**."
)


# --------------------------------------------------
# RUN BUTTON
# --------------------------------------------------
if st.button(
    "Discover registrants route",
    type="primary",
):
    with st.spinner(
        "Following ECHA CHEM JavaScript chunks..."
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

    javascript_results = (
        result[
            "javascript_results"
        ]
    )

    route_rows = (
        result[
            "route_rows"
        ]
    )

    context_rows = (
        result[
            "context_rows"
        ]
    )

    # ----------------------------------
    # 1. APPLICATION SHELL
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
        app_shell[
            "response_length"
        ],
    )

    shell_col3.metric(
        "Initial scripts",
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
        "**Initial JavaScript URLs:**"
    )

    st.json(
        app_shell.get(
            "script_urls"
        )
        or []
    )

    if app_shell.get(
        "preload_sources"
    ):
        st.write(
            "**Module preload sources:**"
        )

        st.json(
            app_shell[
                "preload_sources"
            ]
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
    # 2. JAVASCRIPT TREE SUMMARY
    # ----------------------------------
    st.subheader(
        "2. JavaScript discovery summary"
    )

    js_metric1, js_metric2, js_metric3, js_metric4 = (
        st.columns(4)
    )

    js_metric1.metric(
        "Files requested",
        len(
            javascript_results
        ),
    )

    js_metric2.metric(
        "Confirmed JavaScript",
        sum(
            1
            for item
            in javascript_results
            if item.get(
                "javascript"
            )
        ),
    )

    js_metric3.metric(
        "Child references",
        sum(
            len(
                item.get(
                    "child_scripts"
                )
                or []
            )
            for item
            in javascript_results
        ),
    )

    js_metric4.metric(
        "Relevant contexts",
        len(
            context_rows
        ),
    )

    # ----------------------------------
    # 3. JAVASCRIPT FILE TABLE
    # ----------------------------------
    st.subheader(
        "3. JavaScript files"
    )

    javascript_rows = []

    for item in (
        javascript_results
    ):
        javascript_rows.append(
            {
                "Depth": (
                    item.get(
                        "depth",
                        0,
                    )
                ),
                "Script": (
                    item.get(
                        "script_url",
                        "",
                    )
                ),
                "Parent": (
                    item.get(
                        "parent_url",
                        "",
                    )
                ),
                "HTTP": (
                    item.get(
                        "status"
                    )
                ),
                "Content-Type": (
                    item.get(
                        "content_type",
                        "",
                    )
                ),
                "Bytes": (
                    item.get(
                        "response_length",
                        0,
                    )
                ),
                "JavaScript": (
                    item.get(
                        "javascript",
                        False,
                    )
                ),
                "Child scripts": (
                    len(
                        item.get(
                            "child_scripts"
                        )
                        or []
                    )
                ),
                "Route strings": (
                    len(
                        item.get(
                            "route_strings"
                        )
                        or []
                    )
                ),
                "Contexts": (
                    len(
                        item.get(
                            "contexts"
                        )
                        or []
                    )
                ),
                "Error": (
                    item.get(
                        "error"
                    )
                ),
            }
        )

    if javascript_rows:
        st.dataframe(
            pd.DataFrame(
                javascript_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No JavaScript files "
            "were analysed."
        )

    # ----------------------------------
    # 4. CHILD SCRIPT RELATIONSHIPS
    # ----------------------------------
    st.subheader(
        "4. JavaScript chunk relationships"
    )

    relationship_rows = []

    for item in (
        javascript_results
    ):
        parent = (
            item.get(
                "script_url",
                "",
            )
        )

        for child in (
            item.get(
                "child_scripts"
            )
            or []
        ):
            relationship_rows.append(
                {
                    "Parent script": (
                        parent
                    ),
                    "Child script": (
                        child
                    ),
                }
            )

    if relationship_rows:
        st.dataframe(
            pd.DataFrame(
                relationship_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No child JavaScript chunks "
            "were found in the analysed files."
        )

    # ----------------------------------
    # 5. ROUTE STRINGS
    # ----------------------------------
    st.subheader(
        "5. Registrant/API route strings"
    )

    if route_rows:
        st.success(
            "Registrant-related route "
            "strings were found."
        )

        st.dataframe(
            pd.DataFrame(
                route_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No registrant/API route strings "
            "were found."
        )

    # ----------------------------------
    # 6. CODE CONTEXTS
    # ----------------------------------
    st.subheader(
        "6. Registrant/API code contexts"
    )

    if context_rows:
        st.success(
            "Relevant JavaScript contexts "
            "were found."
        )

        st.dataframe(
            pd.DataFrame(
                context_rows
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
    # 7. ASSET OWNER ROUTE
    # ----------------------------------
    st.subheader(
        "7. Historical asset-owner route"
    )

    asset_owner = (
        result[
            "asset_owner"
        ]
    )

    asset_col1, asset_col2, asset_col3 = (
        st.columns(3)
    )

    asset_col1.metric(
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

    asset_col2.metric(
        "Response bytes",
        asset_owner[
            "response_length"
        ],
    )

    asset_col3.metric(
        "Returns app shell",
        (
            "Yes"
            if asset_owner[
                "returns_app_shell"
            ]
            else
            "No"
        ),
    )

    st.code(
        ASSET_OWNER_ROUTE,
        language=None,
    )

    if asset_owner.get(
        "error"
    ):
        st.error(
            asset_owner[
                "error"
            ]
        )

    # ----------------------------------
    # 8. MAIN SCRIPT PREVIEW
    # ----------------------------------
    st.subheader(
        "8. Main JavaScript preview"
    )

    main_scripts = [
        item
        for item
        in javascript_results
        if (
            "/main-"
            in item.get(
                "script_url",
                ""
            ).lower()
        )
    ]

    if main_scripts:
        for main_script in (
            main_scripts
        ):
            with st.expander(
                main_script.get(
                    "script_url",
                    "Main JavaScript",
                ),
                expanded=True,
            ):
                st.write(
                    "**HTTP:** "
                    f"{main_script.get('status')}"
                )

                st.write(
                    "**Bytes:** "
                    f"{main_script.get('response_length')}"
                )

                st.write(
                    "**Child JavaScript URLs:**"
                )

                st.json(
                    main_script.get(
                        "child_scripts"
                    )
                    or []
                )

                st.write(
                    "**Source preview:**"
                )

                st.code(
                    main_script.get(
                        "source_preview",
                        "",
                    ),
                    language="javascript",
                )

    else:
        st.warning(
            "No main JavaScript bundle "
            "was identified."
        )