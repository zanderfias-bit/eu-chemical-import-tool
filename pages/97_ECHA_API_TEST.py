import re

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

st.set_page_config(page_title="ECHA registrants import discovery", page_icon="🔎", layout="wide")

CODE_VERSION = "ECHA_REGISTRANTS_IMPORT_DISCOVERY_V15"
CAS_NUMBER = "128-37-0"
EC_NUMBER = "204-881-4"
RML_ID = "100.004.439"
EXPECTED_REGISTRANTS = 42

ECHA_BASE_URL = "https://chem.echa.europa.eu"
OVERVIEW_URL = f"{ECHA_BASE_URL}/{RML_ID}/overview"
WEB_COMPONENTS_URL = f"{ECHA_BASE_URL}/dossierList/web-components-NIMFYLDU.js"
RUNTIME_CONFIG_URL = f"{ECHA_BASE_URL}/mfe-config/dossierList/mfe-config.json"

CONNECT_TIMEOUT_SECONDS = 20
READ_TIMEOUT_SECONDS = 90

HEADERS = {
    "Accept": "application/json,application/javascript,text/javascript,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


def create_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.75,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def safe_get(session, url, referer=None):
    headers = {"Referer": referer} if referer else None
    try:
        response = session.get(
            url,
            headers=headers,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            allow_redirects=True,
        )
        return response, None
    except requests.Timeout as error:
        return None, f"Request timed out: {error}"
    except requests.RequestException as error:
        return None, f"Request failed: {error}"


def parse_json(response):
    if response is None:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def clean_js(text):
    return (
        (text or "")
        .replace("\\/", "/")
        .replace("\\u002F", "/")
        .replace("\\u002f", "/")
    )


def get_context(text, start, end, before=1200, after=2500):
    return text[max(0, start - before):min(len(text), end + after)]


def extract_imports(text):
    patterns = [
        re.compile(
            r'import\{(?P<body>[^}]+)\}from["\'](?P<module>[^"\']+)["\']',
            re.IGNORECASE,
        ),
        re.compile(
            r'import\*as\s+(?P<alias>[A-Za-z_$][A-Za-z0-9_$]*)\s+from["\'](?P<module>[^"\']+)["\']',
            re.IGNORECASE,
        ),
    ]

    rows = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            data = match.groupdict()
            rows.append(
                {
                    "position": match.start(),
                    "module": data.get("module", ""),
                    "body": data.get("body", "") or "",
                    "alias": data.get("alias", "") or "",
                    "statement": match.group(0),
                }
            )
    return rows


def imports_that_define_g(imports):
    matches = []
    for row in imports:
        body = row.get("body", "")
        alias = row.get("alias", "")

        body_match = re.search(
            r'(?:^|,)\s*([A-Za-z_$][A-Za-z0-9_$]*)\s+as\s+g\s*(?:,|$)',
            body,
        )
        direct_match = re.search(
            r'(?:^|,)\s*g\s*(?:,|$)',
            body,
        )

        if alias == "g" or body_match or direct_match:
            source_export = ""
            if body_match:
                source_export = body_match.group(1)
            elif direct_match:
                source_export = "g"
            elif alias == "g":
                source_export = "*"

            found = dict(row)
            found["source_export"] = source_export
            matches.append(found)

    return matches


def resolve_module_url(module_name):
    if not module_name:
        return ""
    if module_name.startswith("http://") or module_name.startswith("https://"):
        return module_name
    if module_name.startswith("./") or module_name.startswith("../"):
        return requests.compat.urljoin(WEB_COMPONENTS_URL, module_name)
    return ""


def extract_environment_evidence(text):
    rows = []
    patterns = [
        ("registrantsApiUrl property", r'registrantsApiUrl\s*:\s*["\']([^"\']*)["\']'),
        ("dossierListApiUrl property", r'dossierListApiUrl\s*:\s*["\']([^"\']*)["\']'),
        ("dossier API literal", r'["\']([^"\']*api-dossier-list/v\d+/[^"\']*)["\']'),
        ("registrants API literal", r'["\']([^"\']*registrant[^"\']*)["\']'),
    ]

    seen = set()
    for label, pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            value = match.group(1).strip()
            key = (label, value, match.start())
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "type": label,
                    "value": value,
                    "position": match.start(),
                    "context": get_context(text, match.start(), match.end()),
                }
            )
    return rows


def find_g_usage_context(text):
    term = "g?.registrantsApiUrl"
    pos = text.find(term)
    if pos < 0:
        term = "g.registrantsApiUrl"
        pos = text.find(term)
    if pos < 0:
        return ""
    return get_context(text, pos, pos + len(term), before=2500, after=4500)


def run_discovery():
    session = create_session()

    js_response, js_error = safe_get(session, WEB_COMPONENTS_URL, OVERVIEW_URL)
    runtime_response, runtime_error = safe_get(session, RUNTIME_CONFIG_URL, OVERVIEW_URL)

    js_text = clean_js(js_response.text if js_response is not None else "")
    imports = extract_imports(js_text)
    g_imports = imports_that_define_g(imports)

    imported_modules = []
    for row in g_imports:
        module_url = resolve_module_url(row["module"])
        imported = {
            "module": row["module"],
            "module_url": module_url,
            "source_export": row["source_export"],
            "http": None,
            "content_type": "",
            "bytes": 0,
            "error": "",
            "evidence": [],
            "preview": "",
        }

        if module_url:
            response, error = safe_get(session, module_url, WEB_COMPONENTS_URL)
            imported["error"] = error or ""
            if response is not None:
                imported["http"] = response.status_code
                imported["content_type"] = response.headers.get("content-type", "")
                imported["bytes"] = len(response.content)
                imported_text = clean_js(response.text or "")
                imported["evidence"] = extract_environment_evidence(imported_text)
                imported["preview"] = imported_text[:12000]

        imported_modules.append(imported)

    return {
        "javascript": {
            "status": js_response.status_code if js_response is not None else None,
            "content_type": js_response.headers.get("content-type", "") if js_response is not None else "",
            "bytes": len(js_response.content) if js_response is not None else 0,
            "error": js_error,
        },
        "runtime": {
            "status": runtime_response.status_code if runtime_response is not None else None,
            "content_type": runtime_response.headers.get("content-type", "") if runtime_response is not None else "",
            "bytes": len(runtime_response.content) if runtime_response is not None else 0,
            "json": parse_json(runtime_response),
            "error": runtime_error,
        },
        "imports": imports,
        "g_imports": g_imports,
        "imported_modules": imported_modules,
        "local_evidence": extract_environment_evidence(js_text),
        "g_usage_context": find_g_usage_context(js_text),
    }


st.title("ECHA registrants import discovery")
st.caption(f"Version: {CODE_VERSION}")
st.write(
    "V15 changes approach. Instead of searching again for a local `g = ...` assignment, "
    "it parses the JavaScript import statements to identify which module supplies the "
    "minified variable `g`, then follows that module when it is a relative ECHA file."
)
st.info(
    "No registrants API request is sent in V15. The only goal is to identify the source "
    "of `g.registrantsApiUrl` from ECHA's actual module graph."
)

st.subheader("Known test substance")
columns = st.columns(4)
columns[0].metric("CAS", CAS_NUMBER)
columns[1].metric("EC", EC_NUMBER)
columns[2].metric("rmlId", RML_ID)
columns[3].metric("Expected registrants", EXPECTED_REGISTRANTS)

if st.button("Trace imported variable g", type="primary"):
    with st.spinner("Tracing the JavaScript import that defines g..."):
        result = run_discovery()

    st.success("Discovery completed.")

    st.subheader("1. Source responses")
    source_rows = [
        {
            "Resource": "dossierList web-components",
            "HTTP": result["javascript"]["status"],
            "Content-Type": result["javascript"]["content_type"],
            "Bytes": result["javascript"]["bytes"],
            "Error": result["javascript"]["error"],
        },
        {
            "Resource": "dossierList runtime config",
            "HTTP": result["runtime"]["status"],
            "Content-Type": result["runtime"]["content_type"],
            "Bytes": result["runtime"]["bytes"],
            "Error": result["runtime"]["error"],
        },
    ]
    st.dataframe(pd.DataFrame(source_rows), use_container_width=True, hide_index=True)

    st.subheader("2. Import statements that define g")
    if result["g_imports"]:
        st.dataframe(
            pd.DataFrame([
                {
                    "Position": row["position"],
                    "Module": row["module"],
                    "Source export": row["source_export"],
                    "Statement": row["statement"],
                }
                for row in result["g_imports"]
            ]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("No import statement mapping an export to the local variable g was found.")

    st.subheader("3. Imported module inspection")
    if result["imported_modules"]:
        module_rows = [
            {
                "Module": row["module"],
                "Resolved URL": row["module_url"],
                "Source export": row["source_export"],
                "HTTP": row["http"],
                "Content-Type": row["content_type"],
                "Bytes": row["bytes"],
                "Evidence count": len(row["evidence"]),
                "Error": row["error"],
            }
            for row in result["imported_modules"]
        ]
        st.dataframe(pd.DataFrame(module_rows), use_container_width=True, hide_index=True)

        for index, row in enumerate(result["imported_modules"], start=1):
            with st.expander(f"Imported module {index}: {row['module']}", expanded=True):
                if row["evidence"]:
                    st.dataframe(
                        pd.DataFrame([
                            {
                                "Type": evidence["type"],
                                "Value": evidence["value"],
                                "Position": evidence["position"],
                            }
                            for evidence in row["evidence"]
                        ]),
                        use_container_width=True,
                        hide_index=True,
                    )
                    for evidence_index, evidence in enumerate(row["evidence"], start=1):
                        st.markdown(f"**Evidence context {evidence_index}**")
                        st.code(evidence["context"], language="javascript")
                elif row["preview"]:
                    st.write("No direct API evidence found. Module preview:")
                    st.code(row["preview"], language="javascript")
                else:
                    st.write("The module could not be inspected as a relative ECHA JavaScript resource.")
    else:
        st.warning("No imported module could be associated with local variable g.")

    st.subheader("4. Local environment/API evidence")
    if result["local_evidence"]:
        st.dataframe(
            pd.DataFrame([
                {
                    "Type": row["type"],
                    "Value": row["value"],
                    "Position": row["position"],
                }
                for row in result["local_evidence"]
            ]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.warning("No local environment/API literals were found.")

    st.subheader("5. Exact context where g is used")
    if result["g_usage_context"]:
        st.code(result["g_usage_context"], language="javascript")
    else:
        st.warning("No g.registrantsApiUrl usage context was found.")

    with st.expander("6. All parsed imports", expanded=False):
        if result["imports"]:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Position": row["position"],
                        "Module": row["module"],
                        "Body": row["body"],
                        "Alias": row["alias"],
                    }
                    for row in result["imports"]
                ]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.write("No imports parsed.")
