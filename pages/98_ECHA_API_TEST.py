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
CODE_VERSION = "ECHA_REGISTRANTS_API_DISCOVERY_V8_FIX2"


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
    "Accept-Language": "en-US,en;q=0.9",
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

            rel = str(
                attributes.get(
                    "rel",
                    "",
                )
            ).lower()

            if not href:
                return

            clean_href = str(
                href
            ).strip()

            if (
                "modulepreload" in rel
                or clean_href
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

    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=retry
        ),
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
    request_headers = (
        {
            "Referer": referer
        }
        if referer
        else None
    )

    try:
        response = session.get(
            url,
            headers=request_headers,
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

    return (
        urlparse(
            response.url
        )
        .path
        .lower()
        .endswith(".js")
    )


# --------------------------------------------------
# LOAD APPLICATION SHELL
# --------------------------------------------------
def load_application_shell(
    session,
):
    response, error = safe_get(
        session,
        OVERVIEW_URL,
    )

    if response is None:
        return {
            "status": None,
            "bytes": 0,
            "base_url": "",
            "scripts": [],
            "error": error,
        }

    parser = ECHAHTMLParser()

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

        path = (
            urlparse(
                script_url
            )
            .path
            .lower()
        )

        if script_url in seen:
            continue

        if not is_allowed_url(
            script_url
        ):
            continue

        if not path.endswith(
            ".js"
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
# EXTRACT CHILD JAVASCRIPT FILES
# --------------------------------------------------
def extract_child_scripts(
    script_text,
    script_url,
):
    if not script_text:
        return []

    candidates = []

    candidates.extend(
        re.findall(
            r'''["']([^"']+\.js(?:\?[^"']*)?)["']''',
            script_text,
            flags=re.IGNORECASE,
        )
    )

    candidates.extend(
        re.findall(
            r'''import\s*\(\s*["']([^"']+)["']\s*\)''',
            script_text,
            flags=re.IGNORECASE,
        )
    )

    candidates.extend(
        re.findall(
            (
                r"(?:chunk|main|runtime|polyfills)-"
                r"[A-Za-z0-9_-]+\.js"
            ),
            script_text,
            flags=re.IGNORECASE,
        )
    )
    results = []
    seen = set()

    for candidate in candidates:
        clean_candidate = (
            str(candidate)
            .strip()
            .strip("\"'")
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

        if not clean_candidate:
            continue

        child_url = urljoin(
            script_url,
            clean_candidate,
        )

        child_path = (
            urlparse(
                child_url
            )
            .path
            .lower()
        )

        if child_url in seen:
            continue

        if not is_allowed_url(
            child_url
        ):
            continue

        if not child_path.endswith(
            ".js"
        ):
            continue

        seen.add(
            child_url
        )

        results.append(
            child_url
        )

    return results


# --------------------------------------------------
# FIND CONTEXTS
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
            position = lower_text.find(
                term_lower,
                start,
            )

            if position < 0:
                break

            context_start = max(
                0,
                position - 900,
            )

            context_end = min(
                len(text),
                (
                    position
                    + len(term)
                    + 2200
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
                context[:700],
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

            if len(
                results
            ) >= 250:
                return results

    return results


# --------------------------------------------------
# EXTRACT CONFIG URL REFERENCES
# --------------------------------------------------
def extract_config_urls(
    text,
    source_url,
):
    if not text:
        return []

    patterns = [
        (
            r'''[^"']*remoteEntry\.json'''
            r'''[^"']*["']'''
        ),
        (
            r'''[^"']*config[^"']*\.json'''
            r'''[^"']*["']'''
        ),
        (
            r'''[^"']*runtime[^"']*\.json'''
            r'''[^"']*["']'''
        ),
        (
            r'''[^"']*environment[^"']*\.json'''
            r'''[^"']*["']'''
        ),
        (
            r'''[^"']*settings[^"']*\.json'''
            r'''[^"']*["']'''
        ),
    ]

    candidates = []

    for pattern in patterns:
        candidates.extend(
            re.findall(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
        )

    results = []
    seen = set()

    for candidate in candidates:
        clean_candidate = (
            str(candidate)
            .strip()
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

        if not clean_candidate:
            continue

        url = urljoin(
            source_url,
            clean_candidate,
        )

        if url in seen:
            continue

        if not is_allowed_url(
            url
        ):
            continue

        seen.add(
            url
        )

        results.append(
            url
        )

    return results


# --------------------------------------------------
# ANALYSE JAVASCRIPT TREE
# --------------------------------------------------
def analyse_javascript_tree(
    session,
    initial_scripts,
):
    pending = deque(
        {
            "url": script_url,
            "depth": 0,
            "parent": OVERVIEW_URL,
        }
        for script_url
        in initial_scripts
    )

    visited = set()

    file_results = []
    context_results = []

    config_urls = []
    seen_config_urls = set()

    while (
        pending
        and
        len(visited) < MAX_FILES
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

        response, error = safe_get(
            session=session,
            url=script_url,
            referer=(
                pending_item[
                    "parent"
                ]
            ),
        )

        if response is None:
            file_results.append(
                {
                    "Depth": (
                        pending_item[
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
        discovered_configs = []

        if javascript:
            child_scripts = (
                extract_child_scripts(
                    response.text,
                    response.url,
                )
            )

            contexts = find_contexts(
                text=(
                    response.text
                ),
                source=(
                    response.url
                ),
            )

            discovered_configs = (
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
                    pending_item[
                        "depth"
                    ]
                ),
                "Script": (
                    response.url
                ),
                "HTTP": (
                    response.status_code
                ),
                "Bytes": len(
                    response.content
                ),
                "JavaScript": (
                    javascript
                ),
                "Child scripts": len(
                    child_scripts
                ),
                "Relevant contexts": len(
                    contexts
                ),
                "Config URLs": len(
                    discovered_configs
                ),
                "Error": None,
            }
        )

        context_results.extend(
            contexts
        )

        for config_url in (
            discovered_configs
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
                        pending_item[
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
# FETCH DISCOVERED CONFIG
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

    contexts = find_contexts(
        text=text,
        source=response.url,
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
# FIND VALUES RECURSIVELY IN JSON
# --------------------------------------------------
def find_json_key_values(
    value,
    wanted_keys,
    path="root",
    results=None,
):
    if results is None:
        results = []

    wanted_lower = {
        key.lower()
        for key
        in wanted_keys
    }

    if isinstance(
        value,
        dict,
    ):
        for key, nested_value in (
            value.items()
        ):
            nested_path = (
                f"{path}.{key}"
            )

            if (
                str(key).lower()
                in wanted_lower
            ):
                results.append(
                    {
                        "path": (
                            nested_path
                        ),
                        "key": (
                            str(key)
                        ),
                        "value": (
                            nested_value
                        ),
                    }
                )

            find_json_key_values(
                value=nested_value,
                wanted_keys=(
                    wanted_keys
                ),
                path=(
                    nested_path
                ),
                results=(
                    results
                ),
            )

    elif isinstance(
        value,
        list,
    ):
        for index, item in enumerate(
            value
        ):
            find_json_key_values(
                value=item,
                wanted_keys=(
                    wanted_keys
                ),
                path=(
                    f"{path}[{index}]"
                ),
                results=(
                    results
                ),
            )

    return results


# --------------------------------------------------
# API BASE CANDIDATES
# --------------------------------------------------
def extract_api_base_candidates(
    contexts,
):
    patterns = [
        (
            r"https?://"
            r"[A-Za-z0-9._:-]+/"
            r"[A-Za-z0-9_./-]*"
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

    candidates = []
    seen = set()

    for row in contexts:
        context = row.get(
            "context",
            "",
        )

        for pattern in patterns:
            matches = re.findall(
                pattern,
                context,
                flags=re.IGNORECASE,
            )

            for match in matches:
                value = str(
                    match
                ).strip()

                key = (
                    row.get(
                        "source",
                        "",
                    ),
                    value,
                )

                if key in seen:
                    continue

                seen.add(
                    key
                )

                candidates.append(
                    {
                        "source": (
                            row.get(
                                "source",
                                "",
                            )
                        ),
                        "term": (
                            row.get(
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
    session = create_session()

    shell = load_application_shell(
        session
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
        config_result = (
            fetch_config_url(
                session=session,
                url=(
                    config_row[
                        "url"
                    ]
                ),
            )
        )

        config_result[
            "discovered_from"
        ] = (
            config_row[
                "source"
            ]
        )

        config_results.append(
            config_result
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
            config_result.get(
                "contexts"
            )
            or []
        )

    json_config_values = []

    for config_result in (
        config_results
    ):
        if (
            config_result[
                "json"
            ]
            is None
        ):
            continue

        found_values = (
            find_json_key_values(
                value=(
                    config_result[
                        "json"
                    ]
                ),
                wanted_keys={
                    "dossierListApiUrl",
                    "dossierApiUrl",
                    "mfe_regdas",
                    "regdas",
                },
            )
        )

        for found_value in (
            found_values
        ):
            found_value[
                "source"
            ] = (
                config_result[
                    "url"
                ]
            )

            json_config_values.append(
                found_value
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
        "json_config_values": (
            json_config_values
        ),
        "api_candidates": (
            extract_api_base_candidates(
                all_contexts
            )
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
    "V8 discovers the actual ECHA dossier-list "
    "API configuration before testing another "
    "registrants endpoint."
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

metric_columns = (
    st.columns(3)
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

    configs = (
        result[
            "configs"
        ]
    )

    # ----------------------------------
    # 1. APPLICATION SHELL
    # ----------------------------------
    st.subheader(
        "1. Application shell"
    )

    shell_columns = (
        st.columns(3)
    )

    shell_columns[0].metric(
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

    shell_columns[1].metric(
        "HTML bytes",
        shell[
            "bytes"
        ],
    )

    shell_columns[2].metric(
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

    javascript_columns = (
        st.columns(3)
    )

    javascript_columns[0].metric(
        "Files analysed",
        len(
            files
        ),
    )

    javascript_columns[1].metric(
        "Relevant contexts",
        len(
            javascript[
                "contexts"
            ]
        ),
    )

    javascript_columns[2].metric(
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

    else:
        st.warning(
            "No JavaScript files "
            "were analysed."
        )

    # ----------------------------------
    # 3. CONFIGURATION URLS
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
    # 4. CONFIG RESPONSES
    # ----------------------------------
    st.subheader(
        "4. Configuration responses"
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
                    "Relevant contexts": len(
                        config[
                            "contexts"
                        ]
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
    # 5. DOSSIER API CONFIG CONTEXTS
    # ----------------------------------
    st.subheader(
        "5. dossierListApiUrl / "
        "dossierApiUrl contexts"
    )

    api_config_terms = {
        "dossierlistapiurl",
        "dossierapiurl",
        "api-dossier-list/v1/",
        "api-dossier-list",
        "runtimeconfig",
        "runtime-config",
    }

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
            in api_config_terms
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
    # 6. REGISTRANTS CONTEXTS
    # ----------------------------------
    st.subheader(
        "6. Registrants configuration contexts"
    )

    registrant_terms = {
        "asset-owner",
        "assetowner",
        "registrants",
        "registrant",
        'listtype:"registrants"',
        "listtype",
        "app-reach-registrants-list",
    }

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
            in registrant_terms
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
    # 8. DIRECT JSON CONFIG VALUES
    # ----------------------------------
    st.subheader(
        "8. Direct API values from configuration"
    )

    json_config_values = (
        result[
            "json_config_values"
        ]
    )

    if json_config_values:
        st.success(
            "Relevant values were found "
            "directly in configuration JSON."
        )

        display_values = [
            {
                "Source": (
                    value[
                        "source"
                    ]
                ),
                "Path": (
                    value[
                        "path"
                    ]
                ),
                "Key": (
                    value[
                        "key"
                    ]
                ),
                "Value": str(
                    value[
                        "value"
                    ]
                ),
            }
            for value
            in json_config_values
        ]

        st.dataframe(
            pd.DataFrame(
                display_values
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No dossierListApiUrl, "
            "dossierApiUrl or regdas value "
            "was found directly in JSON."
        )

    # ----------------------------------
    # 9. PARSED CONFIGURATION JSON
    # ----------------------------------
    st.subheader(
        "9. Parsed configuration JSON"
    )

    json_configs = [
        config
        for config
        in configs
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
                expanded=False,
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
    # 10. CRITICAL CONTEXTS
    # ----------------------------------
    with st.expander(
        "10. All critical discovery contexts",
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
                "No critical contexts found."
            )