import json
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
    page_title="ECHA Registrants API Discovery",
    page_icon="🔎",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_REGISTRANTS_API_DISCOVERY_V8"


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


# --------------------------------------------------
# REQUEST SETTINGS
# --------------------------------------------------
CONNECT_TIMEOUT_SECONDS = 20
READ_TIMEOUT_SECONDS = 90

MAX_FILES = 100

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
# CRITICAL SEARCH TERMS
# --------------------------------------------------
SEARCH_TERMS = [
    "dossierListApiUrl",
    "dossierApiUrl",
    "api-dossier-list/v1/",
    "api-dossier-list",
    "asset-owner",
    "assetowner",
    "registrants",
    "registrant",
    'listType:"registrants"',
    "listType",
    "runtimeConfig",
    "runtime-config",
    "remoteEntry.json",
    "remoteEntry",
    "iucdas-mod-dossier-list-app",
    "app-reach-registrants-list",
]


# --------------------------------------------------
# HTML PARSER
# --------------------------------------------------
class ECHAHTMLParser(HTMLParser):

    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )

        self.base_href = "/"
        self.script_sources = []
        self.link_sources = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        attributes = dict(
            attrs
        )

        tag = str(
            tag
        ).lower()

        if tag == "base":
            href = attributes.get(
                "href"
            )

            if href:
                self.base_href = str(
                    href
                ).strip()

        elif tag == "script":
            src = attributes.get(
                "src"
            )

            if src:
                self.script_sources.append(
                    str(src).strip()
                )

        elif tag == "link":
            href = attributes.get(
                "href"
            )

            if href:
                clean_href = str(
                    href
                ).strip()

                if (
                    clean_href
                    .lower()
                    .split("?")[0]
                    .endswith(".js")
                ):
                    self.link_sources.append(
                        clean_href
                    )


# --------------------------------------------------
# SESSION
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
# SAFE GET
# --------------------------------------------------
def safe_get(
    session,
    url,
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

    except requests.RequestException as error:
        return None, str(
            error
        )


# --------------------------------------------------
# URL VALIDATION
# --------------------------------------------------
def is_allowed_url(
    url,
):

    try:
        parsed = urlparse(
            url
        )

    except Exception:
        return False

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return False

    hostname = (
        parsed.hostname
        or ""
    ).lower()

    return hostname in {
        "chem.echa.europa.eu",
        "webtools.europa.eu",
    }


# --------------------------------------------------
# JAVASCRIPT CHECK
# --------------------------------------------------
def looks_like_javascript(
    response,
):

    if response is None:
        return False

    content_type = (
        response.headers
        .get(
            "content-type",
            "",
        )
        .lower()
    )

    start = (
        response.text[:1000]
        .lower()
    )

    if (
        "<!doctype html"
        in start
    ):
        return False

    if re.search(
        r"<html\b",
        start,
    ):
        return False

    if (
        "javascript"
        in content_type
    ):
        return True

    path = (
        urlparse(
            response.url
        )
        .path
        .lower()
    )

    return path.endswith(
        ".js"
    )


# --------------------------------------------------
# LOAD APPLICATION SHELL
# --------------------------------------------------
def load_application_shell(
    session,
):

    response, error = safe_get(
        session=session,
        url=OVERVIEW_URL,
    )

    if response is None:
        return {
            "status": None,
            "bytes": 0,
            "base_url": "",
            "scripts": [],
            "error": error,
        }

    parser = (
        ECHAHTMLParser()
    )

    try:
        parser.feed(
            response.text
        )

    except Exception as error:
        return {
            "status": (
                response.status_code
            ),
            "bytes": len(
                response.content
            ),
            "base_url": "",
            "scripts": [],
            "error": str(
                error
            ),
        }

    base_url = urljoin(
        response.url,
        parser.base_href,
    )

    sources = (
        parser.script_sources
        +
        parser.link_sources
    )

    scripts = []
    seen = set()

    for source in sources:

        script_url = urljoin(
            base_url,
            source,
        )

        if (
            script_url in seen
        ):
            continue

        if not is_allowed_url(
            script_url
        ):
            continue

        if not (
            urlparse(
                script_url
            )
            .path
            .lower()
            .endswith(".js")
        ):
            continue

        seen.add(
            script_url
        )

        scripts.append(
            script_url
        )

    return {
        "status": (
            response.status_code
        ),
        "bytes": len(
            response.content
        ),
        "base_url": (
            base_url
        ),
        "scripts": (
            scripts
        ),
        "error": None,
    }


# --------------------------------------------------
# EXTRACT CHILD JS FILES
# --------------------------------------------------
def extract_child_scripts(
    script_text,
    script_url,
):

    candidates = []

    patterns = [
        (
            r'''["']([^"']+\.js(?:\?[^"']*)?)["']'''
        ),
        (
            r'''import\s*\(\s*["']([^"']+)["']\s*\)'''
        ),
        (
            r'''chunk-[A-Za-z0-9_-]+\.js'''
        ),
        (
            r'''main-[A-Za-z0-9_-]+\.js'''
        ),
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            script_text,
            flags=re.IGNORECASE,
        )

        candidates.extend(
            matches
        )

    results = []
    seen = set()

    for candidate in candidates:

        if isinstance(
            candidate,
            tuple,
        ):
            candidate = next(
                (
                    item
                    for item
                    in candidate
                    if item
                ),
                "",
            )

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
        )

        if not candidate:
            continue

        child_url = urljoin(
            script_url,
            candidate,
        )

        if not is_allowed_url(
            child_url
        ):
            continue

        if not (
            urlparse(
                child_url
            )
            .path
            .lower()
            .endswith(".js")
        ):
            continue

        if child_url in seen:
            continue

        seen.add(
            child_url
        )

        results.append(
            child_url
        )

    return results


# --------------------------------------------------
# FIND TERM CONTEXTS
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

    results = []

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
                position - 800,
            )

            context_end = min(
                len(text),
                (
                    position
                    + len(term)
                    + 2000
                ),
            )

            context = text[
                context_start:
                context_end
            ]

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

            key = (
                term_lower,
                context[:600],
            )

            if key not in seen:

                seen.add(
                    key
                )

                results.append(
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

            start = (
                position
                + len(term)
            )

            if (
                len(results)
                >= 200
            ):
                return results

    return results


# --------------------------------------------------
# EXTRACT CONFIG-LIKE URLS
# --------------------------------------------------
def extract_config_urls(
    text,
    source_url,
):

    if not text:
        return []

    candidates = []

    patterns = [
        r'''["']([^"']*remoteEntry\.json[^"']*)["']''',
        r'''["']([^"']*config[^"']*\.json[^"']*)["']''',
        r'''["']([^"']*runtime[^"']*\.json[^"']*)["']''',
        r'''["']([^"']*environment[^"']*\.json[^"']*)["']''',
        r'''["']([^"']*settings[^"']*\.json[^"']*)["']''',
        r'''["']([^"']*assets[^"']*\.json[^"']*)["']''',
    ]

    for pattern in patterns:

        candidates.extend(
            re.findall(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
        )

    urls = []

    seen = set()

    for candidate in candidates:

        candidate = (
            str(candidate)
            .replace(
                "\\/",
                "/",
            )
            .strip()
        )

        if not candidate:
            continue

        url = urljoin(
            source_url,
            candidate,
        )

        if not is_allowed_url(
            url
        ):
            continue

        if url in seen:
            continue

        seen.add(
            url
        )

        urls.append(
            url
        )

    return urls


# --------------------------------------------------
# ANALYSE JS TREE
# --------------------------------------------------
def analyse_javascript_tree(
    session,
    initial_scripts,
):

    pending = deque()

    for script_url in (
        initial_scripts
    ):

        pending.append(
            {
                "url": (
                    script_url
                ),
                "depth": 0,
                "parent": (
                    OVERVIEW_URL
                ),
            }
        )

    visited = set()

    file_results = []
    context_results = []
    config_urls = []

    seen_config_urls = set()

    while (
        pending
        and
        len(visited)
        < MAX_FILES
    ):

        item = (
            pending.popleft()
        )

        script_url = (
            item[
                "url"
            ]
        )

        if script_url in visited:
            continue

        visited.add(
            script_url
        )

        response, error = safe_get(
            session=session,
            url=script_url,
            referer=(
                item[
                    "parent"
                ]
            ),
        )

        if response is None:

            file_results.append(
                {
                    "Depth": (
                        item[
                            "depth"
                        ]
                    ),
                    "Script": (
                        script_url
                    ),
                    "HTTP": None,
                    "Bytes": 0,
                    "JavaScript": False,
                    "Child scripts": 0,
                    "Relevant contexts": 0,
                    "Config URLs": 0,
                    "Error": (
                        error
                    ),
                }
            )

            continue

        javascript = (
            looks_like_javascript(
                response
            )
        )

        child_scripts = []

        contexts = []

        discovered_config_urls = []

        if javascript:

            child_scripts = (
                extract_child_scripts(
                    script_text=(
                        response.text
                    ),
                    script_url=(
                        response.url
                    ),
                )
            )

            contexts = (
                find_contexts(
                    text=(
                        response.text
                    ),
                    source=(
                        response.url
                    ),
                )
            )

            discovered_config_urls = (
                extract_config_urls(
                    text=(
                        response.text
                    ),
                    source_url=(
                        response.url
                    ),
                )
            )

        file_results.append(
            {
                "Depth": (
                    item[
                        "depth"
                    ]
                ),
                "Script": (
                    response.url
                ),
                "HTTP": (
                    response.status_code
                ),
                "Bytes": (
                    len(
                        response.content
                    )
                ),
                "JavaScript": (
                    javascript
                ),
                "Child scripts": (
                    len(
                        child_scripts
                    )
                ),
                "Relevant contexts": (
                    len(
                        contexts
                    )
                ),
                "Config URLs": (
                    len(
                        discovered_config_urls
                    )
                ),
                "Error": None,
            }
        )

        context_results.extend(
            contexts
        )

        for config_url in (
            discovered_config_urls
        ):

            if (
                config_url
                in seen_config_urls
            ):
                continue

            seen_config_urls.add(
                config_url
            )

            config_urls.append(
                {
                    "source": (
                        response.url
                    ),
                    "url": (
                        config_url
                    ),
                }
            )

        for child_url in (
            child_scripts
        ):

            if child_url in visited:
                continue

            pending.append(
                {
                    "url": (
                        child_url
                    ),
                    "depth": (
                        item[
                            "depth"
                        ]
                        + 1
                    ),
                    "parent": (
                        response.url
                    ),
                }
            )

    return {
        "files": (
            file_results
        ),
        "contexts": (
            context_results
        ),
        "config_urls": (
            config_urls
        ),
    }


# --------------------------------------------------
# FETCH CONFIG URL
# --------------------------------------------------
def fetch_config_url(
    session,
    url,
):

    response, error = safe_get(
        session=session,
        url=url,
        referer=OVERVIEW_URL,
    )

    if response is None:

        return {
            "url": url,
            "status": None,
            "content_type": "",
            "bytes": 0,
            "json": None,
            "text": "",
            "contexts": [],
            "error": error,
        }

    content_type = (
        response.headers
        .get(
            "content-type",
            "",
        )
    )

    text = (
        response.text
        or ""
    )

    try:
        json_body = (
            response.json()
        )

    except ValueError:
        json_body = None

    contexts = (
        find_contexts(
            text=text,
            source=(
                response.url
            ),
        )
    )

    return {
        "url": (
            response.url
        ),
        "status": (
            response.status_code
        ),
        "content_type": (
            content_type
        ),
        "bytes": len(
            response.content
        ),
        "json": (
            json_body
        ),
        "text": (
            text[:20000]
        ),
        "contexts": (
            contexts
        ),
        "error": None,
    }


# --------------------------------------------------
# EXTRACT LIKELY API BASE VALUES
# --------------------------------------------------
def extract_api_base_candidates(
    contexts,
):

    candidates = []

    seen = set()

    patterns = [
        (
            r"https?://"
            r"[A-Za-z0-9._:-]+"
            r"/[A-Za-z0-9_./-]*"
            r"api-dossier-list"
            r"[A-Za-z0-9_./-]*"
        ),
        (
            r"/api-dossier-list/v1/"
        ),
        (
            r"api-dossier-list/v1/"
        ),
    ]

    for context_row in contexts:

        text = (
            context_row.get(
                "context",
                "",
            )
        )

        for pattern in patterns:

            matches = re.findall(
                pattern,
                text,
                flags=re.IGNORECASE,
            )

            for match in matches:

                value = str(
                    match
                ).strip()

                if (
                    value
                    in seen
                ):
                    continue

                seen.add(
                    value
                )

                candidates.append(
                    {
                        "source": (
                            context_row.get(
                                "source",
                                "",
                            )
                        ),
                        "term": (
                            context_row.get(
                                "term",
                                "",
                            )
                        ),
                        "candidate": (
                            value
                        ),
                    }
                )

    return candidates


# --------------------------------------------------
# COMPLETE DISCOVERY
# --------------------------------------------------
def run_discovery():

    session = (
        create_session()
    )

    shell = (
        load_application_shell(
            session
        )
    )

    javascript_analysis = (
        analyse_javascript_tree(
            session=session,
            initial_scripts=(
                shell.get(
                    "scripts"
                )
                or []
            ),
        )
    )

    config_results = []

    for config_row in (
        javascript_analysis[
            "config_urls"
        ]
    ):

        result = (
            fetch_config_url(
                session=session,
                url=(
                    config_row[
                        "url"
                    ]
                ),
            )
        )

        result[
            "discovered_from"
        ] = (
            config_row[
                "source"
            ]
        )

        config_results.append(
            result
        )

    all_contexts = list(
        javascript_analysis[
            "contexts"
        ]
    )

    for config_result in (
        config_results
    ):

        all_contexts.extend(
            config_result[
                "contexts"
            ]
        )

    api_candidates = (
        extract_api_base_candidates(
            all_contexts
        )
    )

    return {
        "shell": (
            shell
        ),
        "javascript": (
            javascript_analysis
        ),
        "configs": (
            config_results
        ),
        "contexts": (
            all_contexts
        ),
        "api_candidates": (
            api_candidates
        ),
    }


# --------------------------------------------------
# STREAMLIT INTERFACE
# --------------------------------------------------
st.title(
    "ECHA Registrants API discovery"
)

st.caption(
    f"Version: "
    f"{CODE_VERSION}"
)

st.write(
    "V8 determines the actual ECHA dossier-list "
    "API configuration before another registrants "
    "endpoint is tested."
)

st.info(
    "This version performs discovery only. "
    "It does not guess another registrant endpoint "
    "and does not use browser automation."
)


# --------------------------------------------------
# TEST SUBSTANCE
# --------------------------------------------------
st.subheader(
    "Known test substance"
)

column1, column2, column3 = (
    st.columns(3)
)

column1.metric(
    "CAS",
    CAS_NUMBER,
)

column2.metric(
    "EC",
    EC_NUMBER,
)

column3.metric(
    "rmlId",
    RML_ID,
)

st.write(
    "Expected ECHA CHEM benchmark: "
    "**42 registrants**."
)


# --------------------------------------------------
# RUN
# --------------------------------------------------
if st.button(
    "Discover actual dossier API configuration",
    type="primary",
):

    with st.spinner(
        "Inspecting ECHA frontend configuration..."
    ):

        result = (
            run_discovery()
        )

    st.success(
        "Discovery completed."
    )

    shell = (
        result[
            "shell"
        ]
    )

    javascript = (
        result[
            "javascript"
        ]
    )

    # ----------------------------------
    # 1. APPLICATION SHELL
    # ----------------------------------
    st.subheader(
        "1. Application shell"
    )

   

    col1.metric(
        "HTTP",
        (
            shell[
                "status"
            ]
            if (
                shell[
                    "status"
                ]
                is not None
            )
            else
            "Error"
        ),
    )

    col2.metric(
        "HTML bytes",
        shell[
            "bytes"
        ],
    )

    col3.metric(
        "Initial scripts",
        len(
            shell[
                "scripts"
            ]
        ),
    )

    st.write(
        "**Initial scripts:**"
    )

    st.json(
        shell[
            "scripts"
        ]
    )

    if shell[
        "error"
    ]:

        st.error(
            shell[
                "error"
            ]
        )

    # ----------------------------------
    # 2. JAVASCRIPT DISCOVERY
    # ----------------------------------
    st.subheader(
        "2. JavaScript discovery"
    )

    files = (
        javascript[
            "files"
        ]
    )

    js_col1, js_col2, js_col3 = (
        st.columns(3)
    )

    js_col1.metric(
        "Files analysed",
        len(
            files
        ),
    )

    js_col2.metric(
        "Relevant contexts",
        len(
            javascript[
                "contexts"
            ]
        ),
    )

    js_col3.metric(
        "Config URLs found",
        len(
            javascript[
                "config_urls"
            ]
        ),
    )

    if files:

        st.dataframe(
            pd.DataFrame(
                files
            ),
            use_container_width=True,
            hide_index=True,
        )

    # ----------------------------------
    # 3. CONFIG URLS
    # ----------------------------------
    st.subheader(
        "3. Configuration URLs discovered"
    )

    config_urls = (
        javascript[
            "config_urls"
        ]
    )

    if config_urls:

        st.dataframe(
            pd.DataFrame(
                config_urls
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.warning(
            "No configuration URLs "
            "were extracted."
        )

    # ----------------------------------
    # 4. FETCHED CONFIGURATION
    # ----------------------------------
    st.subheader(
        "4. Configuration responses"
    )

    configs = (
        result[
            "configs"
        ]
    )

    if configs:

        config_rows = []

        for config in configs:

            config_rows.append(
                {
                    "URL": (
                        config[
                            "url"
                        ]
                    ),
                    "HTTP": (
                        config[
                            "status"
                        ]
                    ),
                    "Content-Type": (
                        config[
                            "content_type"
                        ]
                    ),
                    "Bytes": (
                        config[
                            "bytes"
                        ]
                    ),
                    "Valid JSON": (
                        config[
                            "json"
                        ]
                        is not None
                    ),
                    "Relevant contexts": (
                        len(
                            config[
                                "contexts"
                            ]
                        )
                    ),
                    "Error": (
                        config[
                            "error"
                        ]
                    ),
                }
            )

        st.dataframe(
            pd.DataFrame(
                config_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.warning(
            "No configuration files "
            "were fetched."
        )

    # ----------------------------------
    # 5. DOSSIER API URL CONTEXTS
    # ----------------------------------
    st.subheader(
        "5. dossierListApiUrl / dossierApiUrl contexts"
    )

    api_config_contexts = [
        row
        for row in (
            result[
                "contexts"
            ]
        )
        if (
            row.get(
                "term",
                "",
            ).lower()
            in {
                "dossierlistapiurl",
                "dossierapiurl",
                "api-dossier-list/v1/",
                "api-dossier-list",
                "runtimeconfig",
                "runtime-config",
            }
        )
    ]

    if api_config_contexts:

        st.success(
            "Dossier API configuration "
            "context was found."
        )

        st.dataframe(
            pd.DataFrame(
                api_config_contexts
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.warning(
            "No dossier API configuration "
            "context was found."
        )

    # ----------------------------------
    # 6. REGISTRANTS CONTEXT
    # ----------------------------------
    st.subheader(
        "6. Registrants configuration contexts"
    )

    registrant_contexts = [
        row
        for row in (
            result[
                "contexts"
            ]
        )
        if (
            row.get(
                "term",
                "",
            ).lower()
            in {
                "asset-owner",
                "assetowner",
                "registrants",
                "registrant",
                'listtype:"registrants"',
                "listtype",
                "app-reach-registrants-list",
            }
        )
    ]

    if registrant_contexts:

        st.success(
            "Registrant configuration "
            "context was found."
        )

        st.dataframe(
            pd.DataFrame(
                registrant_contexts
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.warning(
            "No registrant configuration "
            "contexts were found."
        )

    # ----------------------------------
    # 7. API BASE CANDIDATES
    # ----------------------------------
    st.subheader(
        "7. API base candidates"
    )

    api_candidates = (
        result[
            "api_candidates"
        ]
    )

    if api_candidates:

        st.success(
            "Potential dossier API base "
            "values were extracted."
        )

        st.dataframe(
            pd.DataFrame(
                api_candidates
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.warning(
            "No complete dossier API base "
            "value was extracted yet."
        )

    # ----------------------------------
    # 8. PARSED CONFIG JSON
    # ----------------------------------
    st.subheader(
        "8. Parsed configuration JSON"
    )

    json_configs = [
        config
        for config in configs
        if (
            config[
                "json"
            ]
            is not None
        )
    ]

    if json_configs:

        for config in (
            json_configs
        ):

            with st.expander(
                config[
                    "url"
                ],
                expanded=True,
            ):

                st.json(
                    config[
                        "json"
                    ]
                )

    else:

        st.warning(
            "No JSON configuration "
            "response was found."
        )

    # ----------------------------------
    # 9. RAW CRITICAL CONTEXTS
    # ----------------------------------
    with st.expander(
        "9. All critical discovery contexts",
        expanded=False,
    ):

        contexts = (
            result[
                "contexts"
            ]
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

            st.write(
                "No contexts found."
            )