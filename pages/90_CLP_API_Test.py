import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --------------------------------------------------
# PAGE SETTINGS
# --------------------------------------------------
st.set_page_config(
    page_title="ECHA CLP API Discovery",
    page_icon="🔬",
    layout="wide",
)

st.title("🔬 ECHA CLP API Discovery")
st.write(
    "This separate test page investigates where ECHA CHEM retrieves "
    "Classification and Labelling information. It does not modify app.py."
)
st.info(
    "First search for a substance. Then scan the official overview page "
    "and the real JavaScript resources referenced by that page."
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
ECHA_BASE_URL = "https://chem.echa.europa.eu"
SUBSTANCE_SEARCH_API_URL = f"{ECHA_BASE_URL}/api-substance/v1/substance"

CONNECT_TIMEOUT_SECONDS = 20
READ_TIMEOUT_SECONDS = 90
MAX_RESOURCE_FILES = 60
MAX_RESOURCE_SIZE_BYTES = 15_000_000
MAX_DISPLAY_CONTEXTS = 500

ECHA_HEADERS = {
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

CLP_SEARCH_TERMS = [
    "classification",
    "labelling",
    "labeling",
    "clp",
    "annex vi",
    "annexvi",
    "harmonised",
    "harmonized",
    "hazard",
    "hazardstatement",
    "hazard statement",
    "signalword",
    "signal word",
    "pictogram",
    "ghs",
    "specificconcentrationlimit",
    "specific concentration limit",
    "m-factor",
    "m_factor",
    "self-classification",
    "self classification",
    "notification",
    "inventory",
]


# --------------------------------------------------
# HTTP AND DATA HELPERS
# --------------------------------------------------
def clean_text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    if text.lower() in {"", "none", "null", "nan"}:
        return ""
    return " ".join(text.split())


def clean_identifier(value):
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        values = []
        for item in value:
            cleaned = clean_identifier(item)
            if cleaned and cleaned not in values:
                values.append(cleaned)
        return ", ".join(values)
    if isinstance(value, dict):
        return clean_text(value)
    return clean_text(value)


def create_echa_session():
    session = requests.Session()
    session.headers.update(ECHA_HEADERS)
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.75,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def safe_get(session, url, params=None, referer=None):
    headers = {"Referer": referer} if referer else None
    try:
        response = session.get(
            url,
            params=params,
            headers=headers,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
            allow_redirects=True,
        )
    except requests.Timeout as error:
        return {"response": None, "json": None, "text": "", "error": f"Request timed out: {error}"}
    except requests.RequestException as error:
        return {"response": None, "json": None, "text": "", "error": f"Request failed: {error}"}

    try:
        response_json = response.json()
    except ValueError:
        response_json = None

    return {
        "response": response,
        "json": response_json,
        "text": response.text,
        "error": None,
    }


def extract_items(response_json):
    if not isinstance(response_json, dict):
        return []
    items = response_json.get("items", [])
    return items if isinstance(items, list) else []


def find_first_field(value, possible_keys):
    wanted = {str(key).lower() for key in possible_keys}
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if str(key).lower() in wanted and not isinstance(nested_value, (dict, list)):
                return nested_value
        for nested_value in value.values():
            result = find_first_field(nested_value, possible_keys)
            if result not in (None, ""):
                return result
    elif isinstance(value, list):
        for item in value:
            result = find_first_field(item, possible_keys)
            if result not in (None, ""):
                return result
    return None


def normalise_substance(item):
    if not isinstance(item, dict):
        return {"Name": "", "EC Number": "", "CAS Number": "", "rmlId": "", "URL": "", "_raw": item}

    substance_index = item.get("substanceIndex", {})
    if not isinstance(substance_index, dict):
        substance_index = {}

    rml_id = substance_index.get("rmlId") or find_first_field(item, {"rmlId"})
    substance_name = substance_index.get("rmlName") or find_first_field(
        item, {"rmlName", "name", "substanceName", "preferredName", "publicName"}
    )
    cas_number = (
        substance_index.get("rmlCas")
        or substance_index.get("casNumber")
        or find_first_field(item, {"rmlCas", "casNumber", "cas"})
    )
    ec_number = (
        substance_index.get("ecNumber")
        or substance_index.get("rmlEc")
        or substance_index.get("rmlEcNumber")
        or find_first_field(item, {"ecNumber", "rmlEc", "rmlEcNumber", "ec"})
    )
    clean_rml_id = clean_text(rml_id)
    return {
        "Name": clean_text(substance_name),
        "EC Number": clean_identifier(ec_number),
        "CAS Number": clean_identifier(cas_number),
        "rmlId": clean_rml_id,
        "URL": f"{ECHA_BASE_URL}/{clean_rml_id}/overview" if clean_rml_id else "",
        "_raw": item,
    }


def substance_result_score(result, search_text):
    query = clean_text(search_text).lower()
    name = result.get("Name", "").lower()
    cas_number = result.get("CAS Number", "").lower()
    ec_number = result.get("EC Number", "").lower()
    rml_id = result.get("rmlId", "").lower()
    if query == cas_number:
        return 100
    if query == ec_number:
        return 95
    if query == rml_id:
        return 90
    if query == name:
        return 85
    if query and query in name:
        return 60
    if query and query in cas_number:
        return 50
    if query and query in ec_number:
        return 45
    return 0


@st.cache_data(ttl=3600, show_spinner=False)
def search_substances(search_text):
    session = create_echa_session()
    params = {"pageIndex": 1, "pageSize": 100, "searchText": search_text}
    result = safe_get(
        session,
        SUBSTANCE_SEARCH_API_URL,
        params=params,
        referer=f"{ECHA_BASE_URL}/substance-search?searchText={search_text}",
    )
    response = result["response"]
    substances = [normalise_substance(item) for item in extract_items(result["json"])]
    substances.sort(key=lambda item: substance_result_score(item, search_text), reverse=True)
    return {
        "status": response.status_code if response is not None else None,
        "url": response.url if response is not None else "",
        "content_type": response.headers.get("content-type", "") if response is not None else "",
        "error": result["error"],
        "json": result["json"],
        "text": result["text"],
        "params": params,
        "results": substances,
    }


# --------------------------------------------------
# CORRECT HTML RESOURCE DISCOVERY
# --------------------------------------------------
class ResourceParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.resources = []
        self.inline_scripts = []
        self._inside_script = False
        self._current_script_src = ""
        self._current_script_parts = []

    def handle_starttag(self, tag, attrs):
        attributes = {str(key).lower(): value for key, value in attrs if key}
        tag = tag.lower()

        if tag == "script":
            self._inside_script = True
            self._current_script_src = attributes.get("src") or ""
            self._current_script_parts = []
            if self._current_script_src:
                self.resources.append(("script", self._current_script_src))

        if tag == "link":
            href = attributes.get("href") or ""
            rel = (attributes.get("rel") or "").lower()
            as_value = (attributes.get("as") or "").lower()
            if href and (
                href.lower().split("?", 1)[0].endswith(".js")
                or "modulepreload" in rel
                or as_value == "script"
            ):
                self.resources.append(("link", href))

    def handle_data(self, data):
        if self._inside_script and not self._current_script_src:
            self._current_script_parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._inside_script:
            if not self._current_script_src:
                inline_text = "".join(self._current_script_parts).strip()
                if inline_text:
                    self.inline_scripts.append(inline_text)
            self._inside_script = False
            self._current_script_src = ""
            self._current_script_parts = []


def extract_page_resources(html_text, page_url):
    parser = ResourceParser()
    parser.feed(html_text)
    resources = []
    seen = set()

    for resource_type, raw_url in parser.resources:
        absolute_url = urljoin(page_url, raw_url.strip())
        parsed = urlparse(absolute_url)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc != urlparse(ECHA_BASE_URL).netloc:
            continue
        if absolute_url not in seen:
            resources.append({"type": resource_type, "url": absolute_url})
            seen.add(absolute_url)

    return resources, parser.inline_scripts


def extract_api_candidates(text):
    if not text:
        return []

    patterns = [
        r'["\'](https?://chem\.echa\.europa\.eu/api-[^"\'\s]+)["\']',
        r'["\'](/api-[A-Za-z0-9_./?=&{}:$-]+)["\']',
        r'["\'](/api/[A-Za-z0-9_./?=&{}:$-]+)["\']',
        r'["\']([^"\']*(?:classification|labelling|labeling|annexvi|annex-vi|hazard)[^"\']*)["\']',
    ]
    candidates = []
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            cleaned = clean_text(match).rstrip(";,)")
            if cleaned and len(cleaned) <= 600 and cleaned not in candidates:
                candidates.append(cleaned)
    return candidates


def extract_keyword_contexts(text, source_url, context_size=250):
    if not text:
        return []
    lower_text = text.lower()
    contexts = []
    seen = set()

    for term in CLP_SEARCH_TERMS:
        start = 0
        while True:
            position = lower_text.find(term.lower(), start)
            if position == -1:
                break
            context = re.sub(
                r"\s+",
                " ",
                text[max(0, position - context_size):min(len(text), position + len(term) + context_size)],
            ).strip()
            key = (term.lower(), context)
            if key not in seen:
                contexts.append({"Search term": term, "Source": source_url, "Context": context})
                seen.add(key)
            if len(contexts) >= MAX_DISPLAY_CONTEXTS:
                return contexts
            start = position + len(term)
    return contexts


def append_unique(target, values):
    for value in values:
        if value not in target:
            target.append(value)


@st.cache_data(ttl=3600, show_spinner=False)
def investigate_echa_page(rml_id):
    session = create_echa_session()
    overview_url = f"{ECHA_BASE_URL}/{rml_id}/overview"
    overview_result = safe_get(session, overview_url, referer=ECHA_BASE_URL)
    overview_response = overview_result["response"]

    report = {
        "rmlId": rml_id,
        "overview": {
            "requested_url": overview_url,
            "status": overview_response.status_code if overview_response is not None else None,
            "final_url": overview_response.url if overview_response is not None else "",
            "content_type": overview_response.headers.get("content-type", "") if overview_response is not None else "",
            "error": overview_result["error"],
        },
        "resources_found": [],
        "resource_files": [],
        "inline_scripts_found": 0,
        "api_candidates": [],
        "keyword_contexts": [],
    }

    if overview_result["error"] or overview_response is None or overview_response.status_code != 200:
        return report

    html_text = overview_result["text"]
    append_unique(report["api_candidates"], extract_api_candidates(html_text))
    report["keyword_contexts"].extend(extract_keyword_contexts(html_text, overview_url))

    resources, inline_scripts = extract_page_resources(html_text, overview_url)
    report["resources_found"] = resources
    report["inline_scripts_found"] = len(inline_scripts)

    for index, inline_script in enumerate(inline_scripts, start=1):
        source = f"{overview_url}#inline-script-{index}"
        append_unique(report["api_candidates"], extract_api_candidates(inline_script))
        remaining = MAX_DISPLAY_CONTEXTS - len(report["keyword_contexts"])
        if remaining > 0:
            report["keyword_contexts"].extend(
                extract_keyword_contexts(inline_script, source)[:remaining]
            )

    for resource in resources[:MAX_RESOURCE_FILES]:
        resource_url = resource["url"]
        resource_result = safe_get(session, resource_url, referer=overview_url)
        response = resource_result["response"]
        content_type = response.headers.get("content-type", "") if response is not None else ""
        size = len(response.content) if response is not None else 0
        record = {
            "type": resource["type"],
            "url": resource_url,
            "status": response.status_code if response is not None else None,
            "content_type": content_type,
            "bytes": size,
            "error": resource_result["error"],
            "scanned": False,
        }

        if resource_result["error"] or response is None or response.status_code != 200:
            report["resource_files"].append(record)
            continue
        if size > MAX_RESOURCE_SIZE_BYTES:
            record["error"] = f"Skipped because the resource exceeds {MAX_RESOURCE_SIZE_BYTES:,} bytes."
            report["resource_files"].append(record)
            continue
        if "javascript" not in content_type.lower() and not resource_url.lower().split("?", 1)[0].endswith((".js", ".mjs")):
            record["error"] = "Skipped because the response is not JavaScript."
            report["resource_files"].append(record)
            continue

        resource_text = resource_result["text"]
        record["scanned"] = True
        append_unique(report["api_candidates"], extract_api_candidates(resource_text))
        remaining = MAX_DISPLAY_CONTEXTS - len(report["keyword_contexts"])
        if remaining > 0:
            report["keyword_contexts"].extend(
                extract_keyword_contexts(resource_text, resource_url)[:remaining]
            )
        report["resource_files"].append(record)

    return report


# --------------------------------------------------
# MANUAL ENDPOINT TESTER
# --------------------------------------------------
def build_test_url(endpoint_text):
    endpoint_text = endpoint_text.strip().strip('"\'')
    if not endpoint_text:
        return ""
    if endpoint_text.startswith(("https://", "http://")):
        return endpoint_text
    return urljoin(f"{ECHA_BASE_URL}/", endpoint_text.lstrip("/"))


def replace_endpoint_placeholders(endpoint_url, rml_id):
    updated = endpoint_url
    for placeholder in ("{rmlId}", "{rmlid}", ":rmlId", ":rmlid"):
        updated = updated.replace(placeholder, rml_id)
    return updated


def parse_query_parameters(parameter_text):
    if not parameter_text.strip():
        return {}, None
    try:
        parameters = json.loads(parameter_text)
    except json.JSONDecodeError as error:
        return None, f"The query parameters are not valid JSON: {error}"
    if not isinstance(parameters, dict):
        return None, "Query parameters must be a JSON object."
    return parameters, None


def test_endpoint(endpoint_url, parameters, referer):
    session = create_echa_session()
    result = safe_get(session, endpoint_url, params=parameters, referer=referer)
    response = result["response"]
    return {
        "requested_endpoint": endpoint_url,
        "parameters": parameters,
        "status": response.status_code if response is not None else None,
        "final_url": response.url if response is not None else "",
        "content_type": response.headers.get("content-type", "") if response is not None else "",
        "error": result["error"],
        "json": result["json"],
        "text": result["text"],
    }


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
DEFAULT_STATE = {
    "clp_search_result": None,
    "clp_selected_substance": None,
    "clp_discovery_report": None,
    "clp_endpoint_result": None,
}
for key, default_value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default_value


# --------------------------------------------------
# STEP 1: SUBSTANCE SEARCH
# --------------------------------------------------
st.header("1. Select a test substance")
search_text = st.text_input(
    "CAS number, EC number, substance name, or rmlId",
    value="123-31-9",
    placeholder="For example: 123-31-9",
)

if st.button("Search test substance", type="primary"):
    clean_search_text = search_text.strip()
    if not clean_search_text:
        st.error("Enter a CAS number, EC number, substance name, or rmlId.")
    else:
        with st.spinner("Searching ECHA CHEM..."):
            search_result = search_substances(clean_search_text)
        st.session_state["clp_search_result"] = search_result
        st.session_state["clp_selected_substance"] = None
        st.session_state["clp_discovery_report"] = None
        st.session_state["clp_endpoint_result"] = None

search_result = st.session_state["clp_search_result"]
if search_result is not None:
    cols = st.columns(3)
    cols[0].metric("HTTP", search_result["status"] if search_result["status"] is not None else "Error")
    cols[1].metric("Valid JSON", "Yes" if search_result["json"] is not None else "No")
    cols[2].metric("Results", len(search_result["results"]))

    with st.expander("Substance search request details", expanded=False):
        st.write("**Endpoint**")
        st.code(SUBSTANCE_SEARCH_API_URL, language=None)
        st.write("**Parameters**")
        st.json(search_result["params"])
        st.write("**Final URL**")
        st.code(search_result["url"] or "No response URL", language=None)
        st.write("**Content-Type**")
        st.code(search_result["content_type"] or "Unknown", language=None)

    if search_result["status"] == 200 and search_result["results"]:
        results = search_result["results"]
        st.dataframe(
            pd.DataFrame([
                {
                    "Name": result["Name"],
                    "EC Number": result["EC Number"],
                    "CAS Number": result["CAS Number"],
                    "rmlId": result["rmlId"],
                }
                for result in results
            ]),
            hide_index=True,
            use_container_width=True,
        )
        labels = [
            f"{result['Name'] or 'Unnamed substance'} | EC {result['EC Number'] or '-'} "
            f"| CAS {result['CAS Number'] or '-'} | rmlId {result['rmlId'] or '-'}"
            for result in results
        ]
        selected_label = st.selectbox("Select the substance to investigate", labels)
        selected_substance = results[labels.index(selected_label)]
        st.session_state["clp_selected_substance"] = selected_substance

        selected_cols = st.columns(4)
        selected_cols[0].metric("Name", selected_substance["Name"] or "Unknown")
        selected_cols[1].metric("EC Number", selected_substance["EC Number"] or "Unknown")
        selected_cols[2].metric("CAS Number", selected_substance["CAS Number"] or "Unknown")
        selected_cols[3].metric("rmlId", selected_substance["rmlId"] or "Unknown")
    elif search_result["error"]:
        st.error("The ECHA substance search failed.")
        st.info(search_result["error"])
    elif search_result["status"] != 200:
        st.error(f"ECHA returned HTTP {search_result['status']}.")
        with st.expander("Raw substance search response", expanded=False):
            st.code(search_result["text"][:30000], language=None)
    else:
        st.warning("No matching substances were returned.")


# --------------------------------------------------
# STEP 2: DISCOVERY SCAN
# --------------------------------------------------
selected_substance = st.session_state["clp_selected_substance"]
if selected_substance is not None:
    st.divider()
    st.header("2. Discover CLP-related API references")
    selected_rml_id = selected_substance.get("rmlId", "")
    if not selected_rml_id:
        st.warning("The selected substance does not contain an rmlId.")
    else:
        st.write(
            "The scanner reads real script src and modulepreload attributes, then checks only "
            "JavaScript resources hosted on chem.echa.europa.eu."
        )
        if st.button("Scan ECHA page for CLP API references", type="primary"):
            with st.spinner("Inspecting ECHA CHEM resources..."):
                st.session_state["clp_discovery_report"] = investigate_echa_page(selected_rml_id)
            st.session_state["clp_endpoint_result"] = None

discovery_report = st.session_state["clp_discovery_report"]
if discovery_report is not None:
    overview = discovery_report["overview"]
    resource_files = discovery_report["resource_files"]
    api_candidates = discovery_report["api_candidates"]
    keyword_contexts = discovery_report["keyword_contexts"]
    scanned_count = sum(1 for resource in resource_files if resource.get("scanned"))

    cols = st.columns(5)
    cols[0].metric("Overview HTTP", overview["status"] if overview["status"] is not None else "Error")
    cols[1].metric("Resources found", len(discovery_report["resources_found"]))
    cols[2].metric("Resources scanned", scanned_count)
    cols[3].metric("Inline scripts", discovery_report["inline_scripts_found"])
    cols[4].metric("Candidates", len(api_candidates))

    st.write("**Overview URL**")
    st.code(overview["final_url"] or overview["requested_url"], language=None)

    with st.expander("Resources found in HTML", expanded=False):
        if discovery_report["resources_found"]:
            st.dataframe(pd.DataFrame(discovery_report["resources_found"]), hide_index=True, use_container_width=True)
        else:
            st.warning("No JavaScript resources were referenced by the returned HTML.")

    with st.expander("Resource scan details", expanded=False):
        if resource_files:
            st.dataframe(pd.DataFrame(resource_files), hide_index=True, use_container_width=True)
        else:
            st.warning("No external JavaScript resource was scanned.")

    st.subheader("Possible API routes or CLP references")
    if api_candidates:
        st.dataframe(pd.DataFrame({"Candidate": api_candidates}), hide_index=True, use_container_width=True)
    else:
        st.warning("No obvious API route was found. Review the keyword contexts below.")

    st.subheader("CLP keyword contexts")
    if keyword_contexts:
        context_dataframe = pd.DataFrame(keyword_contexts)
        selected_terms = st.multiselect(
            "Filter by keyword",
            sorted(context_dataframe["Search term"].dropna().unique().tolist()),
            default=[],
        )
        if selected_terms:
            context_dataframe = context_dataframe[context_dataframe["Search term"].isin(selected_terms)]
        st.dataframe(context_dataframe, hide_index=True, use_container_width=True, height=600)
    else:
        st.warning("No CLP keywords were found in the retrieved page resources.")

    report_json = json.dumps(discovery_report, ensure_ascii=False, indent=2)
    st.download_button(
        "Download complete discovery report",
        report_json.encode("utf-8"),
        file_name=f"echa_clp_discovery_{discovery_report['rmlId']}.json",
        mime="application/json",
    )


# --------------------------------------------------
# STEP 3: MANUAL ENDPOINT TEST
# --------------------------------------------------
if discovery_report is not None:
    st.divider()
    st.header("3. Test a discovered endpoint")
    st.write(
        "Select a discovered route or paste a route observed in the browser Network tab. "
        "Only normal GET requests to chem.echa.europa.eu are allowed."
    )
    selected_rml_id = discovery_report["rmlId"]
    candidate_options = [""] + discovery_report["api_candidates"]
    selected_candidate = st.selectbox(
        "Select a discovered candidate",
        candidate_options,
        format_func=lambda value: "Select a candidate or enter one manually" if not value else value,
    )
    manual_endpoint = st.text_input(
        "Endpoint or route",
        value=selected_candidate,
        placeholder="/api-example/v1/example",
    )
    query_parameter_text = st.text_area(
        "Query parameters as JSON",
        value=json.dumps({"rmlId": selected_rml_id}, indent=2),
        height=140,
    )

    if st.button("Test selected endpoint"):
        endpoint_url = replace_endpoint_placeholders(build_test_url(manual_endpoint), selected_rml_id)
        parameters, parameter_error = parse_query_parameters(query_parameter_text)
        parsed_endpoint = urlparse(endpoint_url) if endpoint_url else None

        if not endpoint_url:
            st.error("Enter an endpoint or route.")
        elif parameter_error:
            st.error(parameter_error)
        elif parsed_endpoint.netloc != urlparse(ECHA_BASE_URL).netloc:
            st.error("Only endpoints on chem.echa.europa.eu are allowed.")
        else:
            with st.spinner("Testing endpoint..."):
                st.session_state["clp_endpoint_result"] = test_endpoint(
                    endpoint_url,
                    parameters,
                    f"{ECHA_BASE_URL}/{selected_rml_id}/overview",
                )

endpoint_result = st.session_state["clp_endpoint_result"]
if endpoint_result is not None:
    cols = st.columns(3)
    cols[0].metric("HTTP", endpoint_result["status"] if endpoint_result["status"] is not None else "Error")
    cols[1].metric("Valid JSON", "Yes" if endpoint_result["json"] is not None else "No")
    cols[2].metric("Response length", len(endpoint_result["text"]))
    st.write("**Final request URL**")
    st.code(endpoint_result["final_url"] or endpoint_result["requested_endpoint"], language=None)
    st.write("**Parameters**")
    st.json(endpoint_result["parameters"])
    st.write("**Content-Type**")
    st.code(endpoint_result["content_type"] or "Unknown", language=None)

    if endpoint_result["error"]:
        st.error(endpoint_result["error"])
    elif endpoint_result["json"] is not None:
        st.subheader("Parsed JSON response")
        st.json(endpoint_result["json"], expanded=False)
        if isinstance(endpoint_result["json"], dict):
            st.write("**Top-level JSON keys**")
            st.code("\n".join(str(key) for key in endpoint_result["json"].keys()) or "No top-level keys", language=None)
        st.download_button(
            "Download endpoint JSON response",
            json.dumps(endpoint_result["json"], ensure_ascii=False, indent=2).encode("utf-8"),
            file_name="echa_clp_endpoint_response.json",
            mime="application/json",
        )
    else:
        st.subheader("Raw response")
        st.code(endpoint_result["text"][:50000], language=None)


# --------------------------------------------------
# CACHE CONTROL
# --------------------------------------------------
st.divider()
if st.button("Clear CLP discovery cache"):
    st.cache_data.clear()
    for key, default_value in DEFAULT_STATE.items():
        st.session_state[key] = default_value
    st.success("CLP discovery cache cleared.")
    st.rerun()
