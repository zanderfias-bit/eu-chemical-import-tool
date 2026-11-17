import re
from collections import deque
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
    page_title="ECHA Dossier List Discovery",
    page_icon="🔎",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_DOSSIER_LIST_DISCOVERY_V9"


# --------------------------------------------------
# TEST SUBSTANCE
# --------------------------------------------------
CAS_NUMBER = "128-37-0"
EC_NUMBER = "204-881-4"
RML_ID = "100.004.439"

ECHA_BASE_URL = "https://chem.echa.europa.eu"

DOSSIER_LIST_REMOTE_ENTRY = (
    f"{ECHA_BASE_URL}/"
    "dossierList/remoteEntry.json"
)

RUNTIME_CONFIG_URL = (
    f"{ECHA_BASE_URL}/"
    "mfe-config/mfe-config.json"
)

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
# SEARCH TERMS
# --------------------------------------------------
SEARCH_TERMS = [
    "registrants",
    "registrant",
    "asset-owner",
    "assetowner",
    "listType",
    "dossierListApiUrl",
    "dossierApiUrl",
    "api-dossier-list",
    "pageIndex",
    "pageSize",
    "rmlId",
    "address",
    "registrationStatus",
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
# CLEAN DISCOVERED URL
# --------------------------------------------------
def clean_discovered_url(
    value,
    base_url,
):
    if value is None:
        return ""

    cleaned = (
        str(value)
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

    # Remove accidentally encoded quote marks.
    while (
        cleaned.lower().endswith(
            "%22"
        )
        or
        cleaned.lower().endswith(
            "%27"
        )
    ):
        cleaned = (
            cleaned[:-3]
        )

    cleaned = (
        cleaned.rstrip(
            "\"'"
        )
    )

    return urljoin(
        base_url,
        cleaned,
    )


# --------------------------------------------------
# ALLOWED URL CHECK
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

    return (
        parsed.scheme
        in {
            "http",
            "https",
        }
        and
        (
            parsed.hostname
            or ""
        ).lower()
        ==
        "chem.echa.europa.eu"
    )


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
        response.text
        or ""
    )[:1000].lower()

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
# EXTRACT JS REFERENCES FROM JSON
# --------------------------------------------------
def extract_json_file_references(
    value,
    base_url,
    path="root",
    results=None,
):
    if results is None:
        results = []

    if isinstance(
        value,
        dict,
    ):
        for key, nested in (
            value.items()
        ):
            extract_json_file_references(
                value=nested,
                base_url=base_url,
                path=(
                    f"{path}.{key}"
                ),
                results=results,
            )

    elif isinstance(
        value,
        list,
    ):
        for index, nested in enumerate(
            value
        ):
            extract_json_file_references(
                value=nested,
                base_url=base_url,
                path=(
                    f"{path}[{index}]"
                ),
                results=results,
            )

    elif isinstance(
        value,
        str,
    ):
        lower_value = (
            value.lower()
        )

        if (
            lower_value.endswith(
                ".js"
            )
            or
            ".js?"
            in lower_value
        ):
            url = clean_discovered_url(
                value=value,
                base_url=base_url,
            )

            if is_allowed_url(
                url
            ):
                results.append(
                    {
                        "path": (
                            path
                        ),
                        "value": (
                            value
                        ),
                        "url": (
                            url
                        ),
                    }
                )

    return results


# --------------------------------------------------
# EXTRACT JS REFERENCES FROM TEXT
# --------------------------------------------------
def extract_script_references(
    text,
    source_url,
):
    if not text:
        return []

    candidates = []

    patterns = [
        (
            r'''["']'''
            r'''([^"']+\.js'''
            r'''(?:\?[^"']*)?)'''
            r'''["']'''
        ),
        (
            r'''import\s*\(\s*'''
            r'''["']'''
            r'''([^"']+)'''
            r'''["']'''
            r'''\s*\)'''
        ),
        (
            r'''(?:chunk|main|runtime|polyfills)-'''
            r'''[A-Za-z0-9_-]+\.js'''
        ),
    ]

    for pattern in patterns:
        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        candidates.extend(
            matches
        )

    urls = []
    seen = set()

    for candidate in candidates:
        url = clean_discovered_url(
            value=candidate,
            base_url=source_url,
        )

        if not is_allowed_url(
            url
        ):
            continue

        path = (
            urlparse(
                url
            )
            .path
            .lower()
        )

        if not path.endswith(
            ".js"
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
# FIND RELEVANT CODE CONTEXT
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
        start = 0

        term_lower = (
            term.lower()
        )

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
                    + 1800
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

            start = (
                position
                + len(term)
            )

            if (
                len(contexts)
                >= 250
            ):
                return contexts

    return contexts


# --------------------------------------------------
# EXTRACT POSSIBLE ENDPOINT FRAGMENTS
# --------------------------------------------------
def extract_endpoint_fragments(
    text,
    source,
):
    fragments = []
    seen = set()

    patterns = [
        (
            r'''["']'''
            r'''([^"']*'''
            r'''(?:asset-owner|assetowner|'''
            r'''registrants|registrant)'''
            r'''[^"']*)'''
            r'''["']'''
        ),
        (
            r'''["']'''
            r'''([^"']*'''
            r'''api-dossier-list'''
            r'''[^"']*)'''
            r'''["']'''
        ),
        (
            r'''["']'''
            r'''([^"']*'''
            r'''(?:pageIndex|pageSize|rmlId)'''
            r'''[^"']*)'''
            r'''["']'''
        ),
    ]

    for pattern in patterns:
        matches = re.findall(
            pattern,
            text or "",
            flags=re.IGNORECASE,
        )

        for match in matches:
            value = re.sub(
                r"\s+",
                " ",
                str(match),
            ).strip()

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

            fragments.append(
                {
                    "source": (
                        source
                    ),
                    "fragment": (
                        value
                    ),
                }
            )

    return fragments


# --------------------------------------------------
# FETCH JSON RESOURCE
# --------------------------------------------------
def fetch_json_resource(
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
            "url": (
                url
            ),
            "status": None,
            "content_type": "",
            "bytes": 0,
            "json": None,
            "text": "",
            "error": (
                error
            ),
        }

    try:
        body = (
            response.json()
        )

    except ValueError:
        body = None

    return {
        "url": (
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
        "bytes": len(
            response.content
        ),
        "json": (
            body
        ),
        "text": (
            response.text
            or ""
        ),
        "error": None,
    }


# --------------------------------------------------
# ANALYSE JAVASCRIPT TREE
# --------------------------------------------------
def analyse_javascript_tree(
    session,
    initial_urls,
):
    pending = deque(
        (
            url,
            DOSSIER_LIST_REMOTE_ENTRY,
            0,
        )
        for url
        in initial_urls
    )

    visited = set()

    rows = []
    contexts = []
    fragments = []

    while (
        pending
        and
        len(visited) < MAX_FILES
    ):
        (
            url,
            parent,
            depth,
        ) = pending.popleft()

        if url in visited:
            continue

        visited.add(
            url
        )

        response, error = safe_get(
            session=session,
            url=url,
            referer=(
                parent
                if parent.startswith(
                    "http"
                )
                else OVERVIEW_URL
            ),
        )

        if response is None:
            rows.append(
                {
                    "Depth": (
                        depth
                    ),
                    "URL": (
                        url
                    ),
                    "HTTP": None,
                    "Content-Type": "",
                    "Bytes": 0,
                    "JavaScript": False,
                    "Children": 0,
                    "Contexts": 0,
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

        children = []
        file_contexts = []
        file_fragments = []

        if javascript:
            children = (
                extract_script_references(
                    text=(
                        response.text
                    ),
                    source_url=(
                        response.url
                    ),
                )
            )

            file_contexts = (
                find_contexts(
                    text=(
                        response.text
                    ),
                    source=(
                        response.url
                    ),
                )
            )

            file_fragments = (
                extract_endpoint_fragments(
                    text=(
                        response.text
                    ),
                    source=(
                        response.url
                    ),
                )
            )

        rows.append(
            {
                "Depth": (
                    depth
                ),
                "URL": (
                    response.url
                ),
                "HTTP": (
                    response.status_code
                ),
                "Content-Type": (
                    response.headers.get(
                        "content-type",
                        "",
                    )
                ),
                "Bytes": len(
                    response.content
                ),
                "JavaScript": (
                    javascript
                ),
                "Children": len(
                    children
                ),
                "Contexts": len(
                    file_contexts
                ),
                "Error": None,
            }
        )

        contexts.extend(
            file_contexts
        )

        fragments.extend(
            file_fragments
        )

        for child in children:
            if child in visited:
                continue

            pending.append(
                (
                    child,
                    response.url,
                    depth + 1,
                )
            )

    return {
        "files": (
            rows
        ),
        "contexts": (
            contexts
        ),
        "fragments": (
            fragments
        ),
    }


# --------------------------------------------------
# COMPLETE DISCOVERY
# --------------------------------------------------
def run_discovery():
    session = (
        create_session()
    )

    # ----------------------------------
    # 1. DOSSIER LIST REMOTE ENTRY
    # ----------------------------------
    remote_entry = (
        fetch_json_resource(
            session=session,
            url=(
                DOSSIER_LIST_REMOTE_ENTRY
            ),
        )
    )

    # ----------------------------------
    # 2. RUNTIME CONFIG
    # ----------------------------------
    runtime_config = (
        fetch_json_resource(
            session=session,
            url=(
                RUNTIME_CONFIG_URL
            ),
        )
    )

    initial_scripts = []
    manifest_references = []

    # ----------------------------------
    # EXTRACT JS FROM MANIFEST JSON
    # ----------------------------------
    if (
        remote_entry[
            "json"
        ]
        is not None
    ):
        manifest_references = (
            extract_json_file_references(
                value=(
                    remote_entry[
                        "json"
                    ]
                ),
                base_url=(
                    DOSSIER_LIST_REMOTE_ENTRY
                ),
            )
        )

        initial_scripts.extend(
            item[
                "url"
            ]
            for item
            in manifest_references
        )

    # ----------------------------------
    # ALSO CHECK RAW MANIFEST TEXT
    # ----------------------------------
    initial_scripts.extend(
        extract_script_references(
            text=(
                remote_entry[
                    "text"
                ]
            ),
            source_url=(
                DOSSIER_LIST_REMOTE_ENTRY
            ),
        )
    )

    # ----------------------------------
    # DEDUPLICATE
    # ----------------------------------
    deduplicated_scripts = []

    seen = set()

    for url in initial_scripts:
        if url in seen:
            continue

        seen.add(
            url
        )

        deduplicated_scripts.append(
            url
        )

    # ----------------------------------
    # ANALYSE DOSSIER LIST JS
    # ----------------------------------
    javascript = (
        analyse_javascript_tree(
            session=session,
            initial_urls=(
                deduplicated_scripts
            ),
        )
    )

    # ----------------------------------
    # COMBINE CONTEXTS
    # ----------------------------------
    all_contexts = list(
        javascript[
            "contexts"
        ]
    )

    if remote_entry[
        "text"
    ]:
        all_contexts.extend(
            find_contexts(
                text=(
                    remote_entry[
                        "text"
                    ]
                ),
                source=(
                    remote_entry[
                        "url"
                    ]
                ),
            )
        )

    if runtime_config[
        "text"
    ]:
        all_contexts.extend(
            find_contexts(
                text=(
                    runtime_config[
                        "text"
                    ]
                ),
                source=(
                    runtime_config[
                        "url"
                    ]
                ),
            )
        )

    # ----------------------------------
    # COMBINE ENDPOINT FRAGMENTS
    # ----------------------------------
    all_fragments = list(
        javascript[
            "fragments"
        ]
    )

    all_fragments.extend(
        extract_endpoint_fragments(
            text=(
                remote_entry[
                    "text"
                ]
            ),
            source=(
                remote_entry[
                    "url"
                ]
            ),
        )
    )

    return {
        "remote_entry": (
            remote_entry
        ),
        "runtime_config": (
            runtime_config
        ),
        "manifest_references": (
            manifest_references
        ),
        "initial_scripts": (
            deduplicated_scripts
        ),
        "javascript": (
            javascript
        ),
        "contexts": (
            all_contexts
        ),
        "fragments": (
            all_fragments
        ),
    }


# --------------------------------------------------
# STREAMLIT INTERFACE
# --------------------------------------------------
st.title(
    "ECHA Dossier List micro-frontend discovery"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.write(
    "V9 inspects only the ECHA dossierList "
    "micro-frontend and its runtime configuration "
    "to identify the exact registrants request."
)

st.info(
    "This test uses public ECHA resources only. "
    "It does not use browser automation or attempt "
    "to bypass access controls."
)


# --------------------------------------------------
# TEST SUBSTANCE
# --------------------------------------------------
st.subheader(
    "Known test substance"
)

columns = (
    st.columns(3)
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

st.write(
    "Expected benchmark: "
    "**42 registrants**."
)


# --------------------------------------------------
# RESOURCES
# --------------------------------------------------
st.subheader(
    "Resources to inspect"
)

st.write(
    "**dossierList remoteEntry:**"
)

st.code(
    DOSSIER_LIST_REMOTE_ENTRY,
    language=None,
)

st.write(
    "**Runtime configuration:**"
)

st.code(
    RUNTIME_CONFIG_URL,
    language=None,
)


# --------------------------------------------------
# RUN
# --------------------------------------------------
if st.button(
    "Inspect dossierList micro-frontend",
    type="primary",
):
    with st.spinner(
        "Inspecting the ECHA dossierList "
        "micro-frontend..."
    ):
        result = (
            run_discovery()
        )

    st.success(
        "Discovery completed."
    )

    # ----------------------------------
    # 1. RESOURCE RESPONSES
    # ----------------------------------
    st.subheader(
        "1. Resource responses"
    )

    response_rows = []

    resources = [
        (
            "dossierList remoteEntry",
            result[
                "remote_entry"
            ],
        ),
        (
            "runtime configuration",
            result[
                "runtime_config"
            ],
        ),
    ]

    for (
        label,
        resource,
    ) in resources:
        response_rows.append(
            {
                "Resource": (
                    label
                ),
                "URL": (
                    resource[
                        "url"
                    ]
                ),
                "HTTP": (
                    resource[
                        "status"
                    ]
                ),
                "Content-Type": (
                    resource[
                        "content_type"
                    ]
                ),
                "Bytes": (
                    resource[
                        "bytes"
                    ]
                ),
                "Valid JSON": (
                    resource[
                        "json"
                    ]
                    is not None
                ),
                "Error": (
                    resource[
                        "error"
                    ]
                ),
            }
        )

    st.dataframe(
        pd.DataFrame(
            response_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    # ----------------------------------
    # 2. JS REFERENCES
    # ----------------------------------
    st.subheader(
        "2. JavaScript references "
        "in remoteEntry"
    )

    manifest_references = (
        result[
            "manifest_references"
        ]
    )

    if manifest_references:
        st.dataframe(
            pd.DataFrame(
                manifest_references
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No JavaScript file references "
            "were parsed from remoteEntry.json."
        )

    st.write(
        "**Initial JavaScript URLs:**"
    )

    st.json(
        result[
            "initial_scripts"
        ]
    )

    # ----------------------------------
    # 3. JS FILES
    # ----------------------------------
    st.subheader(
        "3. dossierList JavaScript files"
    )

    files = (
        result[
            "javascript"
        ][
            "files"
        ]
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
            "No dossierList JavaScript "
            "files were analysed."
        )

    # ----------------------------------
    # 4. ENDPOINT FRAGMENTS
    # ----------------------------------
    st.subheader(
        "4. Registrant/API endpoint fragments"
    )

    fragments = (
        result[
            "fragments"
        ]
    )

    if fragments:
        st.dataframe(
            pd.DataFrame(
                fragments
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No registrant/API endpoint "
            "fragments were found."
        )

    # ----------------------------------
    # 5. CRITICAL CONTEXTS
    # ----------------------------------
    st.subheader(
        "5. Critical code contexts"
    )

    contexts = (
        result[
            "contexts"
        ]
    )

    critical_terms = {
        "registrants",
        "registrant",
        "asset-owner",
        "assetowner",
        "dossierlistapiurl",
        "dossierapiurl",
        "api-dossier-list",
        "listtype",
        "pageindex",
        "pagesize",
        "rmlid",
    }

    critical_contexts = [
        row
        for row in contexts
        if (
            row.get(
                "term",
                "",
            ).lower()
            in critical_terms
        )
    ]

    if critical_contexts:
        st.dataframe(
            pd.DataFrame(
                critical_contexts
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No critical dossierList "
            "contexts were found."
        )

    # ----------------------------------
    # 6. RUNTIME CONFIG
    # ----------------------------------
    st.subheader(
        "6. Runtime configuration JSON"
    )

    runtime_config = (
        result[
            "runtime_config"
        ]
    )

    if (
        runtime_config[
            "json"
        ]
        is not None
    ):
        st.json(
            runtime_config[
                "json"
            ]
        )

    else:
        st.warning(
            "Runtime configuration did "
            "not return valid JSON."
        )

        with st.expander(
            "Raw runtime response",
            expanded=False,
        ):
            st.code(
                runtime_config[
                    "text"
                ][:10000],
                language=None,
            )

    # ----------------------------------
    # 7. REMOTE ENTRY
    # ----------------------------------
    st.subheader(
        "7. dossierList remoteEntry JSON"
    )

    remote_entry = (
        result[
            "remote_entry"
        ]
    )

    if (
        remote_entry[
            "json"
        ]
        is not None
    ):
        with st.expander(
            "Parsed remoteEntry.json",
            expanded=False,
        ):
            st.json(
                remote_entry[
                    "json"
                ]
            )

    else:
        st.warning(
            "dossierList remoteEntry "
            "did not return valid JSON."
        )

        with st.expander(
            "Raw remoteEntry response",
            expanded=False,
        ):
            st.code(
                remote_entry[
                    "text"
                ][:10000],
                language=None,
            )