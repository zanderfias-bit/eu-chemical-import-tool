import html
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="ECHA REST API Test",
    page_icon="🧪",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_REST_API_TEST_V7"


# --------------------------------------------------
# PATHS
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

ECHA_DATA_FILE = (
    BASE_DIR
    / "data"
    / "reach_registrations.xlsx"
)

ECHA_SHEET_NAME = "Substances list"


# --------------------------------------------------
# EXCEL COLUMNS
# --------------------------------------------------
NAME_COLUMN = "Name"
EC_COLUMN = "EC Number"
CAS_COLUMN = "CAS Number"
URL_COLUMN = "Link to substance's overview page"


# --------------------------------------------------
# ECHA ENDPOINTS
# --------------------------------------------------
ECHA_BASE_URL = "https://chem.echa.europa.eu"

SUBSTANCE_ENDPOINT = (
    ECHA_BASE_URL
    + "/api-substance/v1/substance/{rml_id}"
)

DOSSIER_ENDPOINT = (
    ECHA_BASE_URL
    + "/api-dossier-list/v1/dossier"
)

PUBLISHED_DOSSIER_ENDPOINT = (
    ECHA_BASE_URL
    + "/html-pages/{asset_external_id}/index.html"
)


# --------------------------------------------------
# REQUEST CONFIGURATION
# --------------------------------------------------
CONNECT_TIMEOUT_SECONDS = 30
READ_TIMEOUT_SECONDS = 90

REQUEST_HEADERS = {
    "Accept": (
        "application/json, text/plain, "
        "text/html, application/javascript, */*"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


# --------------------------------------------------
# JAVASCRIPT DIAGNOSTIC TERMS
# --------------------------------------------------
JAVASCRIPT_SEARCH_TERMS = [
    ".html",
    "href",
    "location",
    "window.location",
    "document.location",
    "fetch(",
    "iframe",
    "content",
    "html-pages",
    "assetExternalId",
    "setHeaderDocId",
    "addEventListener",
    "preventDefault",
    "target",
    "pathname",
    "replace(",
    "substring(",
    "split(",
]


# --------------------------------------------------
# TEXT NORMALISATION
# --------------------------------------------------
def normalise_text(value):
    if value is None:
        return ""

    value = str(value).strip()

    if value.lower() in {
        "",
        "nan",
        "none",
    }:
        return ""

    if value == "-":
        return ""

    return " ".join(
        value.replace("\xa0", " ").split()
    ).strip()


# --------------------------------------------------
# CAS VALIDATION
# --------------------------------------------------
def looks_like_cas_number(value):
    value = normalise_text(value)

    return bool(
        re.fullmatch(
            r"\d{2,7}-\d{2}-\d",
            value,
        )
    )


# --------------------------------------------------
# EXTRACT RML ID
# --------------------------------------------------
def extract_rml_id(echa_url):
    echa_url = normalise_text(echa_url)

    match = re.search(
        r"/(\d{3}\.\d{3}\.\d{3})(?:/|$)",
        echa_url,
    )

    if not match:
        return ""

    return match.group(1)


# --------------------------------------------------
# LOAD LOCAL ECHA DATA
# --------------------------------------------------
@st.cache_data(show_spinner=False)
def load_echa_data():
    if not ECHA_DATA_FILE.exists():
        raise FileNotFoundError(
            "The ECHA Excel file was not found at: "
            f"{ECHA_DATA_FILE}"
        )

    dataframe = pd.read_excel(
        ECHA_DATA_FILE,
        sheet_name=ECHA_SHEET_NAME,
        dtype=str,
        keep_default_na=False,
        engine="openpyxl",
    )

    required_columns = [
        NAME_COLUMN,
        EC_COLUMN,
        CAS_COLUMN,
        URL_COLUMN,
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise RuntimeError(
            "The ECHA Excel file is missing these columns: "
            + ", ".join(missing_columns)
        )

    dataframe[CAS_COLUMN] = (
        dataframe[CAS_COLUMN]
        .astype(str)
        .map(normalise_text)
    )

    return dataframe


# --------------------------------------------------
# FIND SUBSTANCE BY CAS
# --------------------------------------------------
def find_substance_by_cas(
    dataframe,
    cas_number,
):
    cas_number = normalise_text(cas_number)

    matches = dataframe[
        dataframe[CAS_COLUMN] == cas_number
    ]

    results = []

    for _, row in matches.iterrows():
        echa_url = normalise_text(
            row[URL_COLUMN]
        )

        results.append(
            {
                "name": normalise_text(
                    row[NAME_COLUMN]
                ),
                "ec_number": normalise_text(
                    row[EC_COLUMN]
                ),
                "cas_number": normalise_text(
                    row[CAS_COLUMN]
                ),
                "echa_url": echa_url,
                "rml_id": extract_rml_id(
                    echa_url
                ),
            }
        )

    return results


# --------------------------------------------------
# CREATE HTTP SESSION
# --------------------------------------------------
def create_http_session():
    session = requests.Session()

    session.headers.update(
        REQUEST_HEADERS
    )

    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=1.0,
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
# EXECUTE ECHA REQUEST
# --------------------------------------------------
def execute_echa_request(
    session,
    url,
    params=None,
    additional_headers=None,
    body_preview_length=1000,
):
    print(
        f"ECHA REST GET: {url}",
        flush=True,
    )

    if params:
        print(
            f"ECHA REST PARAMS: {params}",
            flush=True,
        )

    try:
        response = session.get(
            url,
            params=params,
            headers=additional_headers or None,
            timeout=(
                CONNECT_TIMEOUT_SECONDS,
                READ_TIMEOUT_SECONDS,
            ),
            allow_redirects=True,
        )

    except requests.Timeout as error:
        raise RuntimeError(
            "The ECHA REST request timed out: "
            f"{error}"
        ) from error

    except requests.RequestException as error:
        raise RuntimeError(
            "The ECHA REST request failed: "
            f"{error}"
        ) from error

    print(
        f"ECHA REST FINAL URL: {response.url}",
        flush=True,
    )

    print(
        f"ECHA REST STATUS: {response.status_code}",
        flush=True,
    )

    print(
        "ECHA REST CONTENT TYPE: "
        f"{response.headers.get('content-type', '')}",
        flush=True,
    )

    print(
        "ECHA REST BODY PREVIEW: "
        f"{response.text[:body_preview_length]}",
        flush=True,
    )

    return response


# --------------------------------------------------
# PARSE JSON RESPONSE
# --------------------------------------------------
def parse_json_response(
    response,
    description,
):
    content_type = (
        response.headers
        .get("content-type", "")
        .lower()
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"{description} returned HTTP "
            f"{response.status_code}. "
            f"Response: {response.text[:1000]}"
        )

    if (
        "application/json" not in content_type
        and not response.text.lstrip().startswith(
            ("{", "[")
        )
    ):
        raise RuntimeError(
            f"{description} did not return JSON. "
            f"Content-Type: {content_type}. "
            f"Response: {response.text[:1000]}"
        )

    try:
        return response.json()

    except ValueError as error:
        raise RuntimeError(
            f"{description} returned invalid JSON. "
            f"Response: {response.text[:1000]}"
        ) from error


# --------------------------------------------------
# CLEAN SUBSTANCE RESPONSE
# --------------------------------------------------
def clean_substance_response(api_body):
    if not isinstance(api_body, dict):
        return api_body

    cleaned_body = api_body.copy()

    cleaned_body.pop(
        "img64",
        None,
    )

    return cleaned_body


# --------------------------------------------------
# GET SUBSTANCE IDENTITY
# --------------------------------------------------
def get_substance_identity(
    session,
    rml_id,
):
    rml_id = normalise_text(rml_id)

    if not rml_id:
        raise RuntimeError(
            "The rmlId is empty."
        )

    endpoint = SUBSTANCE_ENDPOINT.format(
        rml_id=rml_id
    )

    response = execute_echa_request(
        session=session,
        url=endpoint,
    )

    return {
        "status_code": response.status_code,
        "url": response.url,
        "body": parse_json_response(
            response,
            "ECHA substance endpoint",
        ),
    }


# --------------------------------------------------
# GET REACH DOSSIERS
# --------------------------------------------------
def get_reach_dossiers(
    session,
    rml_id,
    registration_status=None,
):
    rml_id = normalise_text(rml_id)

    if not rml_id:
        raise RuntimeError(
            "The dossier request cannot be executed "
            "because the rmlId is empty."
        )

    params = {
        "pageIndex": 1,
        "pageSize": 100,
        "rmlId": rml_id,
        "legislation": "REACH",
    }

    if registration_status:
        params["registrationStatuses"] = (
            registration_status
        )

    response = execute_echa_request(
        session=session,
        url=DOSSIER_ENDPOINT,
        params=params,
    )

    return {
        "status_code": response.status_code,
        "url": response.url,
        "params": params,
        "body": parse_json_response(
            response,
            "ECHA dossier endpoint",
        ),
    }


# --------------------------------------------------
# EXTRACT DOSSIER ITEMS
# --------------------------------------------------
def extract_items(api_body):
    if isinstance(api_body, list):
        return api_body

    if not isinstance(api_body, dict):
        return []

    for key in (
        "items",
        "content",
        "results",
        "data",
    ):
        value = api_body.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            for nested_key in (
                "items",
                "content",
                "results",
            ):
                nested_value = value.get(
                    nested_key
                )

                if isinstance(
                    nested_value,
                    list,
                ):
                    return nested_value

    return []


# --------------------------------------------------
# SELECT FIRST ACTIVE DOSSIER
# --------------------------------------------------
def select_first_active_dossier(
    dossier_attempts,
):
    for attempt in dossier_attempts:
        if not attempt.get("success"):
            continue

        if (
            attempt.get("registration_status")
            != "Active"
        ):
            continue

        for item in attempt.get(
            "items",
            [],
        ):
            if not isinstance(item, dict):
                continue

            asset_external_id = normalise_text(
                item.get("assetExternalId")
            )

            if asset_external_id:
                return item

    return None


# --------------------------------------------------
# HTML LINK PARSER
# --------------------------------------------------
class DossierIndexParser(HTMLParser):
    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )

        self.links = []
        self.scripts = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        attributes = {
            str(key): value
            for key, value in attrs
        }

        tag_name = tag.lower()

        if tag_name == "a":
            href = attributes.get("href")

            if href is not None:
                self.links.append(
                    {
                        "href": href,
                        "id": attributes.get("id"),
                        "class": attributes.get("class"),
                        "target": attributes.get("target"),
                        "title": attributes.get("title"),
                        "onclick": attributes.get("onclick"),
                        "data_target": attributes.get(
                            "data-target"
                        ),
                        "data_id": attributes.get(
                            "data-id"
                        ),
                    }
                )

        if tag_name == "script":
            src = attributes.get("src")

            if src:
                self.scripts.append(
                    src
                )


# --------------------------------------------------
# PARSE INDEX HTML
# --------------------------------------------------
def parse_index_html(index_html):
    parser = DossierIndexParser()

    try:
        parser.feed(
            index_html or ""
        )

    except Exception as error:
        return {
            "links": [],
            "scripts": [],
            "parse_error": str(error),
        }

    unique_links = []
    seen_links = set()

    for link in parser.links:
        href = normalise_text(
            link.get("href")
        )

        if not href:
            continue

        key = (
            href,
            normalise_text(
                link.get("onclick")
            ),
        )

        if key in seen_links:
            continue

        seen_links.add(key)
        unique_links.append(link)

    unique_scripts = list(
        dict.fromkeys(
            normalise_text(script)
            for script in parser.scripts
            if normalise_text(script)
        )
    )

    return {
        "links": unique_links,
        "scripts": unique_scripts,
        "parse_error": None,
    }


# --------------------------------------------------
# IDENTIFY DOSSIER ROUTE IDS
# --------------------------------------------------
def looks_like_dossier_route_id(value):
    value = normalise_text(value)

    return bool(
        re.fullmatch(
            (
                r"[0-9a-fA-F]{8}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{12}"
                r"_"
                r"[0-9a-fA-F]{8}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{12}"
            ),
            value,
        )
    )


# --------------------------------------------------
# EXTRACT CONTEXT AROUND TEXT
# --------------------------------------------------
def extract_contexts(
    source_text,
    search_value,
    context_characters=350,
    maximum_matches=5,
):
    if not source_text:
        return []

    if not search_value:
        return []

    contexts = []

    for match in re.finditer(
        re.escape(search_value),
        source_text,
        flags=re.IGNORECASE,
    ):
        start = max(
            0,
            match.start()
            - context_characters,
        )

        end = min(
            len(source_text),
            match.end()
            + context_characters,
        )

        contexts.append(
            source_text[start:end]
            .replace("\r", " ")
            .replace("\n", " ")
            .strip()
        )

        if (
            len(contexts)
            >= maximum_matches
        ):
            break

    return contexts


# --------------------------------------------------
# FIND JAVASCRIPT CLUES
# --------------------------------------------------
def find_javascript_clues(
    javascript_text,
):
    clues = []

    if not javascript_text:
        return clues

    for term in JAVASCRIPT_SEARCH_TERMS:
        contexts = extract_contexts(
            source_text=javascript_text,
            search_value=term,
            context_characters=500,
            maximum_matches=10,
        )

        for context in contexts:
            clues.append(
                {
                    "term": term,
                    "context": context,
                }
            )

    unique_clues = []
    seen = set()

    for clue in clues:
        key = (
            clue["term"].lower(),
            clue["context"],
        )

        if key in seen:
            continue

        seen.add(key)
        unique_clues.append(clue)

    return unique_clues


# --------------------------------------------------
# EXTRACT JAVASCRIPT STRING VALUES
# --------------------------------------------------
def extract_javascript_string_values(
    javascript_text,
):
    if not javascript_text:
        return []

    values = re.findall(
        r"""[^"'\\\r\n]{2,300}["']""",
        javascript_text,
    )

    relevant_values = []

    for value in values:
        value = normalise_text(value)

        lower_value = value.lower()

        if any(
            marker in lower_value
            for marker in (
                ".html",
                "href",
                "location",
                "iframe",
                "content",
                "html-pages",
                "pathname",
                "index",
            )
        ):
            relevant_values.append(
                value
            )

    return list(
        dict.fromkeys(
            relevant_values
        )
    )[:200]


# --------------------------------------------------
# FETCH INDEX JAVASCRIPT
# --------------------------------------------------
def fetch_index_scripts(
    session,
    index_url,
    script_references,
):
    script_results = []

    for script_reference in script_references:
        script_url = urljoin(
            index_url,
            script_reference,
        )

        try:
            response = execute_echa_request(
                session=session,
                url=script_url,
                additional_headers={
                    "Accept": (
                        "application/javascript, "
                        "text/javascript, */*"
                    ),
                    "Referer": index_url,
                },
                body_preview_length=2000,
            )

            javascript_text = (
                response.text
                if response.status_code == 200
                else ""
            )

            script_results.append(
                {
                    "script_reference": (
                        script_reference
                    ),
                    "script_url": response.url,
                    "status_code": (
                        response.status_code
                    ),
                    "content_type": (
                        response.headers
                        .get(
                            "content-type",
                            "",
                        )
                        .lower()
                    ),
                    "content_length": len(
                        response.content
                    ),
                    "javascript_preview": (
                        javascript_text[:10000]
                    ),
                    "clues": (
                        find_javascript_clues(
                            javascript_text
                        )
                    ),
                    "relevant_strings": (
                        extract_javascript_string_values(
                            javascript_text
                        )
                    ),
                    "error": (
                        None
                        if response.status_code == 200
                        else (
                            "JavaScript request returned "
                            f"HTTP {response.status_code}."
                        )
                    ),
                }
            )

        except Exception as error:
            script_results.append(
                {
                    "script_reference": (
                        script_reference
                    ),
                    "script_url": script_url,
                    "status_code": None,
                    "content_type": None,
                    "content_length": 0,
                    "javascript_preview": "",
                    "clues": [],
                    "relevant_strings": [],
                    "error": str(error),
                }
            )

    return script_results


# --------------------------------------------------
# ANALYSE PUBLISHED DOSSIER INDEX
# --------------------------------------------------
def analyse_published_dossier_index(
    session,
    index_url,
    index_html,
):
    parsed_index = parse_index_html(
        index_html
    )

    route_links = []

    for link in parsed_index["links"]:
        href = normalise_text(
            link.get("href")
        )

        if looks_like_dossier_route_id(
            href
        ):
            contexts = extract_contexts(
                source_text=index_html,
                search_value=href,
                context_characters=500,
                maximum_matches=3,
            )

            route_links.append(
                {
                    **link,
                    "html_context": (
                        contexts[0]
                        if contexts
                        else ""
                    ),
                }
            )

    script_results = fetch_index_scripts(
        session=session,
        index_url=index_url,
        script_references=(
            parsed_index["scripts"]
        ),
    )

    return {
        "parse_error": (
            parsed_index[
                "parse_error"
            ]
        ),
        "all_links": (
            parsed_index[
                "links"
            ]
        ),
        "script_references": (
            parsed_index[
                "scripts"
            ]
        ),
        "route_links": route_links,
        "script_results": script_results,
    }


# --------------------------------------------------
# GET PUBLISHED DOSSIER
# --------------------------------------------------
def get_published_dossier(
    session,
    asset_external_id,
    rml_id=None,
):
    asset_external_id = normalise_text(
        asset_external_id
    )

    if not asset_external_id:
        raise RuntimeError(
            "The assetExternalId is empty."
        )

    endpoint = (
        PUBLISHED_DOSSIER_ENDPOINT
        .format(
            asset_external_id=(
                asset_external_id
            )
        )
    )

    referer = ECHA_BASE_URL

    if rml_id:
        referer = (
            f"{ECHA_BASE_URL}/"
            f"{normalise_text(rml_id)}"
            f"/overview"
        )

    response = execute_echa_request(
        session=session,
        url=endpoint,
        additional_headers={
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
            "Referer": referer,
        },
    )

    analysis = {
        "parse_error": None,
        "all_links": [],
        "script_references": [],
        "route_links": [],
        "script_results": [],
    }

    if response.status_code == 200:
        analysis = (
            analyse_published_dossier_index(
                session=session,
                index_url=response.url,
                index_html=response.text,
            )
        )

    return {
        "success": (
            response.status_code == 200
        ),
        "status_code": (
            response.status_code
        ),
        "url": response.url,
        "content_type": (
            response.headers
            .get(
                "content-type",
                "",
            )
            .lower()
        ),
        "content_length": len(
            response.content
        ),
        "index_html_preview": (
            response.text[:15000]
        ),
        "analysis": analysis,
        "error": (
            None
            if response.status_code == 200
            else (
                "Published dossier endpoint "
                "returned HTTP "
                f"{response.status_code}. "
                f"Response: "
                f"{response.text[:1000]}"
            )
        ),
    }


# --------------------------------------------------
# MAIN TEST
# --------------------------------------------------
def run_test(cas_number):
    print(
        f"ECHA code version: "
        f"{CODE_VERSION}",
        flush=True,
    )

    print(
        f"ECHA API test started "
        f"for CAS {cas_number}",
        flush=True,
    )

    dataframe = load_echa_data()

    local_results = find_substance_by_cas(
        dataframe=dataframe,
        cas_number=cas_number,
    )

    if not local_results:
        raise RuntimeError(
            f"CAS {cas_number} was not found in "
            "reach_registrations.xlsx."
        )

    selected = local_results[0]

    print(
        f"ECHA local match: {selected}",
        flush=True,
    )

    if not selected["rml_id"]:
        raise RuntimeError(
            "The ECHA rmlId could not be extracted "
            f"from this URL: {selected['echa_url']}"
        )

    session = create_http_session()

    substance_result = None
    substance_error = None

    try:
        substance_result = (
            get_substance_identity(
                session=session,
                rml_id=selected["rml_id"],
            )
        )

    except Exception as error:
        substance_error = str(error)

    dossier_attempts = []

    for status in (
        None,
        "Active",
        "Inactive",
    ):
        request_params = {
            "pageIndex": 1,
            "pageSize": 100,
            "rmlId": selected["rml_id"],
            "legislation": "REACH",
        }

        if status:
            request_params[
                "registrationStatuses"
            ] = status

        try:
            result = get_reach_dossiers(
                session=session,
                rml_id=selected["rml_id"],
                registration_status=status,
            )

            items = extract_items(
                result["body"]
            )

            dossier_attempts.append(
                {
                    "registration_status": (
                        status
                        or "No filter"
                    ),
                    "success": True,
                    "status_code": (
                        result[
                            "status_code"
                        ]
                    ),
                    "url": result["url"],
                    "params": (
                        result["params"]
                    ),
                    "item_count": len(
                        items
                    ),
                    "items": items,
                    "raw_body": (
                        result["body"]
                    ),
                    "error": None,
                }
            )

        except Exception as error:
            dossier_attempts.append(
                {
                    "registration_status": (
                        status
                        or "No filter"
                    ),
                    "success": False,
                    "status_code": None,
                    "url": None,
                    "params": request_params,
                    "item_count": 0,
                    "items": [],
                    "raw_body": None,
                    "error": str(error),
                }
            )

    published_dossier_test = None

    first_active_dossier = (
        select_first_active_dossier(
            dossier_attempts
        )
    )

    if first_active_dossier:
        asset_external_id = (
            normalise_text(
                first_active_dossier.get(
                    "assetExternalId"
                )
            )
        )

        try:
            published_result = (
                get_published_dossier(
                    session=session,
                    asset_external_id=(
                        asset_external_id
                    ),
                    rml_id=(
                        selected["rml_id"]
                    ),
                )
            )

            published_dossier_test = {
                "dossier": (
                    first_active_dossier
                ),
                "asset_external_id": (
                    asset_external_id
                ),
                "registration_number": (
                    first_active_dossier.get(
                        "registrationNumber"
                    )
                ),
                **published_result,
            }

        except Exception as error:
            published_dossier_test = {
                "dossier": (
                    first_active_dossier
                ),
                "asset_external_id": (
                    asset_external_id
                ),
                "registration_number": (
                    first_active_dossier.get(
                        "registrationNumber"
                    )
                ),
                "success": False,
                "status_code": None,
                "url": None,
                "content_type": None,
                "content_length": 0,
                "index_html_preview": "",
                "analysis": {
                    "parse_error": None,
                    "all_links": [],
                    "script_references": [],
                    "route_links": [],
                    "script_results": [],
                },
                "error": str(error),
            }

    return {
        "version": CODE_VERSION,
        "local_substance": selected,
        "substance_result": (
            substance_result
        ),
        "substance_error": (
            substance_error
        ),
        "dossier_attempts": (
            dossier_attempts
        ),
        "published_dossier_test": (
            published_dossier_test
        ),
    }


# --------------------------------------------------
# STREAMLIT UI
# --------------------------------------------------
st.title(
    "ECHA REST API diagnostic"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.write(
    "This test resolves a CAS number through the local "
    "ECHA export, queries the substance and dossier-list "
    "APIs, and analyses the JavaScript used by the "
    "published dossier."
)

st.caption(
    f"Local ECHA file: {ECHA_DATA_FILE}"
)

cas_number = st.text_input(
    "CAS number",
    value="128-37-0",
    placeholder="For example: 128-37-0",
)

run_button = st.button(
    "Run ECHA API test",
    type="primary",
)


if run_button:
    cleaned_cas = normalise_text(
        cas_number
    )

    if not looks_like_cas_number(
        cleaned_cas
    ):
        st.error(
            "Enter a valid CAS number, "
            "for example 128-37-0."
        )

    else:
        with st.spinner(
            "Testing ECHA and analysing "
            "the published dossier scripts..."
        ):
            try:
                test_result = run_test(
                    cleaned_cas
                )

            except Exception as error:
                st.error(
                    "ECHA API test failed: "
                    f"{error}"
                )

                st.stop()

        st.success(
            "ECHA API test completed."
        )

        substance = test_result[
            "local_substance"
        ]

        # ----------------------------------
        # 1. LOCAL SUBSTANCE
        # ----------------------------------
        st.subheader(
            "1. Local substance match"
        )

        col1, col2, col3 = st.columns(
            3
        )

        col1.metric(
            "CAS number",
            substance["cas_number"],
        )

        col2.metric(
            "EC number",
            (
                substance["ec_number"]
                or "Not available"
            ),
        )

        col3.metric(
            "ECHA rmlId",
            substance["rml_id"],
        )

        st.write(
            f"**Name:** "
            f"{substance['name']}"
        )

        st.write(
            f"**ECHA URL:** "
            f"{substance['echa_url']}"
        )

        # ----------------------------------
        # 2. SUBSTANCE API
        # ----------------------------------
        st.subheader(
            "2. Substance API"
        )

        if test_result[
            "substance_result"
        ]:
            substance_api = (
                test_result[
                    "substance_result"
                ]
            )

            st.success(
                "The substance endpoint "
                "returned HTTP "
                f"{substance_api['status_code']}."
            )

            substance_body = (
                substance_api["body"]
            )

            if isinstance(
                substance_body,
                dict,
            ):
                summary1, summary2 = (
                    st.columns(2)
                )

                participation = (
                    substance_body.get(
                        "listParticipation",
                        [],
                    )
                )

                summary1.metric(
                    "REACH status",
                    (
                        "Registered"
                        if (
                            "REACH REGISTERED"
                            in participation
                        )
                        else
                        "Not confirmed"
                    ),
                )

                summary2.metric(
                    "Tonnage band",
                    (
                        substance_body.get(
                            "tonnageBand"
                        )
                        or "Not available"
                    ),
                )

            with st.expander(
                "Substance API response",
                expanded=False,
            ):
                st.json(
                    clean_substance_response(
                        substance_body
                    )
                )

        else:
            st.error(
                test_result[
                    "substance_error"
                ]
                or
                "The substance endpoint failed."
            )

        # ----------------------------------
        # 3. DOSSIER API
        # ----------------------------------
        st.subheader(
            "3. REACH dossier API"
        )

        for attempt in test_result[
            "dossier_attempts"
        ]:
            with st.expander(
                (
                    "Registration status: "
                    f"{attempt['registration_status']}"
                ),
                expanded=(
                    attempt[
                        "registration_status"
                    ]
                    == "Active"
                ),
            ):
                st.markdown(
                    "**Request parameters**"
                )

                st.json(
                    attempt["params"]
                )

                if attempt["url"]:
                    st.markdown(
                        "**Final API URL**"
                    )

                    st.code(
                        attempt["url"],
                        language=None,
                    )

                if attempt["success"]:
                    st.success(
                        "HTTP "
                        f"{attempt['status_code']} | "
                        f"{attempt['item_count']} "
                        "dossier item(s)"
                    )

                    if attempt["items"]:
                        st.dataframe(
                            pd.json_normalize(
                                attempt["items"]
                            ),
                            width="stretch",
                            hide_index=True,
                        )

                    with st.expander(
                        "Raw dossier JSON response",
                        expanded=False,
                    ):
                        st.json(
                            attempt[
                                "raw_body"
                            ]
                        )

                else:
                    st.error(
                        attempt["error"]
                    )

        # ----------------------------------
        # 4. PUBLISHED DOSSIER
        # ----------------------------------
        st.subheader(
            "4. Published dossier route analysis"
        )

        published_test = test_result.get(
            "published_dossier_test"
        )

        if not published_test:
            st.warning(
                "No active dossier with an "
                "assetExternalId was available."
            )

        else:
            detail1, detail2 = st.columns(
                2
            )

            detail1.metric(
                "assetExternalId",
                (
                    published_test.get(
                        "asset_external_id"
                    )
                    or "Not available"
                ),
            )

            detail2.metric(
                "Registration number",
                (
                    published_test.get(
                        "registration_number"
                    )
                    or "Not available"
                ),
            )

            if published_test.get("url"):
                st.markdown(
                    "**Published dossier URL**"
                )

                st.code(
                    published_test["url"],
                    language=None,
                )

            if published_test.get(
                "success"
            ):
                st.success(
                    "Published dossier returned "
                    "HTTP "
                    f"{published_test['status_code']}."
                )

            else:
                st.error(
                    published_test.get(
                        "error"
                    )
                    or
                    "Published dossier test failed."
                )

            analysis = published_test.get(
                "analysis",
                {},
            )

            all_links = analysis.get(
                "all_links",
                [],
            )

            route_links = analysis.get(
                "route_links",
                [],
            )

            script_references = (
                analysis.get(
                    "script_references",
                    [],
                )
            )

            script_results = analysis.get(
                "script_results",
                [],
            )

            metric1, metric2, metric3 = (
                st.columns(3)
            )

            metric1.metric(
                "All HTML links",
                len(all_links),
            )

            metric2.metric(
                "Dossier route identifiers",
                len(route_links),
            )

            metric3.metric(
                "JavaScript files",
                len(script_results),
            )

            # ----------------------------------
            # ROUTE IDENTIFIERS
            # ----------------------------------
            with st.expander(
                "Dossier route identifiers",
                expanded=False,
            ):
                if route_links:
                    route_table = []

                    for route_link in route_links:
                        route_table.append(
                            {
                                "href": (
                                    route_link.get(
                                        "href"
                                    )
                                ),
                                "target": (
                                    route_link.get(
                                        "target"
                                    )
                                ),
                                "onclick": (
                                    route_link.get(
                                        "onclick"
                                    )
                                ),
                                "class": (
                                    route_link.get(
                                        "class"
                                    )
                                ),
                                "data_target": (
                                    route_link.get(
                                        "data_target"
                                    )
                                ),
                                "data_id": (
                                    route_link.get(
                                        "data_id"
                                    )
                                ),
                            }
                        )

                    st.dataframe(
                        pd.DataFrame(
                            route_table
                        ),
                        width="stretch",
                        hide_index=True,
                    )

                else:
                    st.warning(
                        "No dossier route identifiers "
                        "were found."
                    )

            # ----------------------------------
            # HTML CONTEXT
            # ----------------------------------
            with st.expander(
                "HTML context around first route",
                expanded=False,
            ):
                if route_links:
                    st.code(
                        route_links[0].get(
                            "html_context"
                        )
                        or
                        "No context available.",
                        language="html",
                    )

                else:
                    st.text(
                        "No route context available."
                    )

            # ----------------------------------
            # SCRIPT REFERENCES
            # ----------------------------------
            with st.expander(
                "JavaScript references",
                expanded=False,
            ):
                st.json(
                    script_references
                )

            # ----------------------------------
            # JAVASCRIPT RESULTS
            # ----------------------------------
            st.markdown(
                "### JavaScript route diagnostics"
            )

            if not script_results:
                st.warning(
                    "No JavaScript files were found."
                )

            for script_result in script_results:
                script_name = (
                    script_result.get(
                        "script_reference"
                    )
                    or "Unknown script"
                )

                with st.expander(
                    script_name,
                    expanded=(
                        script_name.endswith(
                            "index.js"
                        )
                    ),
                ):
                    if script_result.get(
                        "error"
                    ):
                        st.error(
                            script_result[
                                "error"
                            ]
                        )

                    else:
                        script_col1, script_col2 = (
                            st.columns(2)
                        )

                        script_col1.metric(
                            "HTTP status",
                            script_result.get(
                                "status_code"
                            ),
                        )

                        script_col2.metric(
                            "Response size",
                            script_result.get(
                                "content_length"
                            ),
                        )

                    st.markdown(
                        "**Script URL**"
                    )

                    st.code(
                        script_result.get(
                            "script_url"
                        )
                        or
                        "Not available",
                        language=None,
                    )

                    st.markdown(
                        "**Relevant JavaScript strings**"
                    )

                    st.json(
                        script_result.get(
                            "relevant_strings",
                            [],
                        )
                    )

                    clues = script_result.get(
                        "clues",
                        [],
                    )

                    st.markdown(
                        "**Route-related code contexts**"
                    )

                    if clues:
                        clue_table = []

                        for clue in clues:
                            clue_table.append(
                                {
                                    "term": (
                                        clue.get(
                                            "term"
                                        )
                                    ),
                                    "context": (
                                        clue.get(
                                            "context"
                                        )
                                    ),
                                }
                            )

                        st.dataframe(
                            pd.DataFrame(
                                clue_table
                            ),
                            width="stretch",
                            hide_index=True,
                        )

                    else:
                        st.info(
                            "No route-related terms "
                            "were found in this script."
                        )

                    with st.expander(
                        "JavaScript source preview",
                        expanded=False,
                    ):
                        st.code(
                            script_result.get(
                                "javascript_preview"
                            )
                            or
                            "No JavaScript source "
                            "was returned.",
                            language="javascript",
                        )

            # ----------------------------------
            # INDEX PREVIEW
            # ----------------------------------
            with st.expander(
                "Published index HTML preview",
                expanded=False,
            ):
                st.code(
                    published_test.get(
                        "index_html_preview"
                    )
                    or
                    "No index HTML was returned.",
                    language="html",
                )