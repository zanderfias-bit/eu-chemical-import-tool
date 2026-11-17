import html
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
import streamlit as st


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
CODE_VERSION = "ECHA_REST_API_TEST_V5"


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
# ECHA API
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

# Prevent excessive requests during diagnostics.
MAX_PUBLISHED_DETAIL_PAGES = 250

REQUEST_HEADERS = {
    "Accept": (
        "application/json, text/plain, "
        "text/html, */*"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


# --------------------------------------------------
# REGISTRANT SEARCH TERMS
# --------------------------------------------------
DOSSIER_SEARCH_TERMS = [
    "Registrant",
    "Legal entity",
    "Company",
    "Company name",
    "Organisation",
    "Organization",
    "Manufacturer",
    "Importer",
    "Only representative",
    "Third party representative",
    "Registration holder",
    "Applicant",
]

REGISTRANT_FIELD_TERMS = [
    "Legal entity name",
    "Legal entity",
    "Registrant name",
    "Registrant",
    "Company name",
    "Organisation name",
    "Organization name",
    "Registration holder",
    "Applicant name",
    "Manufacturer name",
    "Importer name",
    "Only representative",
]

REGISTRANT_EXCLUDED_PHRASES = [
    "registrant specific composition",
    "registrant-specific composition",
    "registrant specific analytical information",
    "registrant specific",
    "information provided by the registrant",
    "information submitted by the registrant",
    "registrants may",
    "registrants shall",
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

    return session


# --------------------------------------------------
# EXECUTE ECHA REQUEST
# --------------------------------------------------
def execute_echa_request(
    session,
    url,
    params=None,
    additional_headers=None,
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
        f"{response.text[:1000]}",
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
# EXTRACT ASSET EXTERNAL IDS
# --------------------------------------------------
def extract_asset_external_ids(items):
    values = []

    for item in items:
        if not isinstance(item, dict):
            continue

        asset_external_id = item.get(
            "assetExternalId"
        )

        if asset_external_id:
            values.append(
                str(asset_external_id)
            )

    return list(
        dict.fromkeys(values)
    )


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
# HTML TO SEARCHABLE TEXT
# --------------------------------------------------
def html_to_searchable_text(
    html_content,
):
    if not html_content:
        return ""

    text = str(html_content)

    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        text,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    text = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        text,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    text = re.sub(
        r"</?(?:div|p|li|tr|td|th|h[1-6]|br)"
        r"\b[^>]*>",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"<[^>]+>",
        " ",
        text,
    )

    text = html.unescape(text)

    return " ".join(
        text.replace("\xa0", " ").split()
    )


# --------------------------------------------------
# FIND DIAGNOSTIC TEXT MATCHES
# --------------------------------------------------
def find_dossier_text_matches(
    searchable_text,
    terms=None,
    context_characters=350,
):
    if terms is None:
        terms = DOSSIER_SEARCH_TERMS

    matches = []

    if not searchable_text:
        return matches

    for term in terms:
        match = re.search(
            re.escape(term),
            searchable_text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        start = max(
            0,
            match.start()
            - context_characters,
        )

        end = min(
            len(searchable_text),
            match.end()
            + context_characters,
        )

        matches.append(
            {
                "term": term,
                "excerpt": searchable_text[
                    start:end
                ].strip(),
            }
        )

    return matches


# --------------------------------------------------
# EXTRACT INTERNAL DOSSIER LINKS
# --------------------------------------------------
def extract_internal_dossier_links(
    index_html,
    index_url,
):
    """
    Extract internal published-dossier links.

    ECHA usually omits the .html extension in the href values,
    while the underlying published blobs use .html filenames.
    """

    if not index_html:
        return []

    href_values = re.findall(
        r"""href\s*=\s*[^"']+["']""",
        index_html,
        flags=re.IGNORECASE,
    )

    links = []

    for href in href_values:
        href = html.unescape(
            str(href).strip()
        )

        if not href:
            continue

        if href.startswith(
            (
                "#",
                "javascript:",
                "mailto:",
                "tel:",
            )
        ):
            continue

        lower_href = href.lower()

        if lower_href.startswith(
            (
                "assets/",
                "./assets/",
            )
        ):
            continue

        if lower_href.endswith(
            (
                ".css",
                ".js",
                ".png",
                ".jpg",
                ".jpeg",
                ".gif",
                ".svg",
                ".ico",
                ".map",
            )
        ):
            continue

        absolute_url = urljoin(
            index_url,
            href,
        )

        parsed_url = urlparse(
            absolute_url
        )

        if (
            parsed_url.netloc
            and parsed_url.netloc
            != "chem.echa.europa.eu"
        ):
            continue

        if "/html-pages/" not in absolute_url:
            continue

        if (
            absolute_url.rstrip("/")
            == index_url.rstrip("/")
        ):
            continue

        last_path_part = (
            parsed_url.path
            .rstrip("/")
            .split("/")[-1]
        )

        # Add .html when the index link omits the extension.
        if "." not in last_path_part:
            absolute_url = (
                absolute_url.rstrip("/")
                + ".html"
            )

        links.append(
            absolute_url
        )

    return list(
        dict.fromkeys(links)
    )


# --------------------------------------------------
# CLEAN REGISTRANT CANDIDATE
# --------------------------------------------------
def clean_possible_registrant_value(value):
    value = normalise_text(value)

    value = re.sub(
        r"^[\s:;|\-]+",
        "",
        value,
    )

    value = re.sub(
        r"[\s:;|\-]+$",
        "",
        value,
    )

    value = normalise_text(value)

    if len(value) < 3:
        return ""

    if len(value) > 250:
        return ""

    lower_value = value.lower()

    if any(
        excluded in lower_value
        for excluded
        in REGISTRANT_EXCLUDED_PHRASES
    ):
        return ""

    generic_values = {
        "registrant",
        "legal entity",
        "company",
        "company name",
        "organisation",
        "organisation name",
        "organization",
        "organization name",
        "manufacturer",
        "importer",
        "only representative",
        "registration holder",
        "applicant",
        "not available",
        "not applicable",
        "confidential",
    }

    if lower_value in generic_values:
        return ""

    return value


# --------------------------------------------------
# EXTRACT LABEL/VALUE PAIRS
# --------------------------------------------------
def extract_html_label_value_pairs(
    html_content,
):
    pairs = []

    if not html_content:
        return pairs

    # Table rows
    table_rows = re.findall(
        r"<tr\b[^>]*>(.*?)</tr>",
        html_content,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    for row_html in table_rows:
        cells = re.findall(
            r"<(?:th|td)\b[^>]*>"
            r"(.*?)"
            r"</(?:th|td)>",
            row_html,
            flags=(
                re.IGNORECASE
                | re.DOTALL
            ),
        )

        cell_texts = [
            html_to_searchable_text(cell)
            for cell in cells
        ]

        cell_texts = [
            value
            for value in cell_texts
            if value
        ]

        if len(cell_texts) >= 2:
            pairs.append(
                (
                    cell_texts[0],
                    cell_texts[1],
                )
            )

    # Definition lists
    definition_pairs = re.findall(
        r"<dt\b[^>]*>(.*?)</dt>\s*"
        r"<dd\b[^>]*>(.*?)</dd>",
        html_content,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    for label_html, value_html in definition_pairs:
        label = html_to_searchable_text(
            label_html
        )

        value = html_to_searchable_text(
            value_html
        )

        if label and value:
            pairs.append(
                (
                    label,
                    value,
                )
            )

    # Label followed by span/div/p
    block_pairs = re.findall(
        r"<(?:label|strong|b)\b[^>]*>"
        r"(.*?)"
        r"</(?:label|strong|b)>"
        r"\s*"
        r"<(?:span|div|p)\b[^>]*>"
        r"(.*?)"
        r"</(?:span|div|p)>",
        html_content,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    for label_html, value_html in block_pairs:
        label = html_to_searchable_text(
            label_html
        )

        value = html_to_searchable_text(
            value_html
        )

        if label and value:
            pairs.append(
                (
                    label,
                    value,
                )
            )

    return pairs


# --------------------------------------------------
# EXTRACT REGISTRANT CANDIDATES
# --------------------------------------------------
def extract_registrant_candidates(
    html_content,
    source_url,
):
    candidates = []

    searchable_text = (
        html_to_searchable_text(
            html_content
        )
    )

    # Structured label/value fields
    for label, value in (
        extract_html_label_value_pairs(
            html_content
        )
    ):
        matching_term = None

        for term in REGISTRANT_FIELD_TERMS:
            if term.lower() in label.lower():
                matching_term = term
                break

        if not matching_term:
            continue

        cleaned_value = (
            clean_possible_registrant_value(
                value
            )
        )

        if cleaned_value:
            candidates.append(
                {
                    "field": label,
                    "value": cleaned_value,
                    "source_url": source_url,
                    "method": "HTML label/value",
                }
            )

    # Plain-text fallback
    for term in REGISTRANT_FIELD_TERMS:
        pattern = re.compile(
            re.escape(term)
            + r"\s*(?::|-)?\s*"
            + r"(.{3,250})",
            flags=re.IGNORECASE,
        )

        match = pattern.search(
            searchable_text
        )

        if not match:
            continue

        candidate_value = match.group(1)

        candidate_value = re.split(
            r"\s{2,}|"
            r"(?:Registration number|"
            r"Registration date|"
            r"Status|"
            r"Address|"
            r"Country|"
            r"UUID|"
            r"General information)",
            candidate_value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]

        cleaned_value = (
            clean_possible_registrant_value(
                candidate_value
            )
        )

        if cleaned_value:
            candidates.append(
                {
                    "field": term,
                    "value": cleaned_value,
                    "source_url": source_url,
                    "method": "Text search",
                }
            )

    unique_candidates = []
    seen = set()

    for candidate in candidates:
        key = (
            candidate["field"].lower(),
            candidate["value"].lower(),
            candidate["source_url"],
        )

        if key in seen:
            continue

        seen.add(key)
        unique_candidates.append(
            candidate
        )

    return unique_candidates


# --------------------------------------------------
# GET ONE PUBLISHED DETAIL PAGE
# --------------------------------------------------
def get_published_detail_page(
    session,
    detail_url,
    referer,
):
    """
    Try the supplied URL and its .html alternative.

    This allows the diagnostic to handle both possible ECHA
    publication URL structures.
    """

    detail_url = normalise_text(
        detail_url
    )

    if not detail_url:
        return None

    parsed_url = urlparse(
        detail_url
    )

    last_path_part = (
        parsed_url.path
        .rstrip("/")
        .split("/")[-1]
    )

    candidate_urls = []

    if last_path_part.endswith(".html"):
        candidate_urls.append(
            detail_url
        )

        candidate_urls.append(
            detail_url[:-5]
        )

    else:
        candidate_urls.append(
            detail_url + ".html"
        )

        candidate_urls.append(
            detail_url
        )

    candidate_urls = list(
        dict.fromkeys(candidate_urls)
    )

    last_response = None

    for candidate_url in candidate_urls:
        response = execute_echa_request(
            session=session,
            url=candidate_url,
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

        last_response = response

        if response.status_code == 200:
            return response

        if response.status_code != 404:
            return response

    return last_response


# --------------------------------------------------
# SCAN INTERNAL DOSSIER PAGES
# --------------------------------------------------
def scan_published_dossier_pages(
    session,
    index_url,
    index_html,
    rml_id=None,
):
    internal_links = (
        extract_internal_dossier_links(
            index_html=index_html,
            index_url=index_url,
        )
    )

    links_to_test = internal_links[
        :MAX_PUBLISHED_DETAIL_PAGES
    ]

    page_results = []
    all_candidates = []

    if rml_id:
        referer = (
            f"{ECHA_BASE_URL}/"
            f"{normalise_text(rml_id)}"
            f"/overview"
        )
    else:
        referer = index_url

    for page_number, detail_url in enumerate(
        links_to_test,
        start=1,
    ):
        try:
            response = get_published_detail_page(
                session=session,
                detail_url=detail_url,
                referer=referer,
            )

            if response is None:
                raise RuntimeError(
                    "No response was returned for "
                    "the published detail page."
                )

            content_type = (
                response.headers
                .get(
                    "content-type",
                    "",
                )
                .lower()
            )

            candidates = []

            if response.status_code == 200:
                candidates = (
                    extract_registrant_candidates(
                        html_content=response.text,
                        source_url=response.url,
                    )
                )

                all_candidates.extend(
                    candidates
                )

            page_results.append(
                {
                    "page_number": page_number,
                    "requested_url": detail_url,
                    "final_url": response.url,
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "response_size": len(
                        response.content
                    ),
                    "candidate_count": len(
                        candidates
                    ),
                    "candidates": candidates,
                    "error": (
                        None
                        if response.status_code == 200
                        else (
                            "Detail page returned HTTP "
                            f"{response.status_code}."
                        )
                    ),
                }
            )

        except Exception as error:
            page_results.append(
                {
                    "page_number": page_number,
                    "requested_url": detail_url,
                    "final_url": None,
                    "status_code": None,
                    "content_type": None,
                    "response_size": 0,
                    "candidate_count": 0,
                    "candidates": [],
                    "error": str(error),
                }
            )

    unique_candidates = []
    seen_candidates = set()

    for candidate in all_candidates:
        candidate_value = normalise_text(
            candidate.get("value")
        )

        if not candidate_value:
            continue

        key = candidate_value.lower()

        if key in seen_candidates:
            continue

        seen_candidates.add(key)

        unique_candidates.append(
            candidate
        )

    successful_page_count = sum(
        1
        for page_result in page_results
        if page_result.get("status_code") == 200
    )

    failed_page_count = sum(
        1
        for page_result in page_results
        if page_result.get("status_code") != 200
    )

    return {
        "internal_link_count": len(
            internal_links
        ),
        "tested_page_count": len(
            links_to_test
        ),
        "successful_page_count": (
            successful_page_count
        ),
        "failed_page_count": (
            failed_page_count
        ),
        "page_results": page_results,
        "registrant_candidates": (
            unique_candidates
        ),
    }


# --------------------------------------------------
# GET AND SCAN PUBLISHED DOSSIER
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

    response_text = response.text

    searchable_text = (
        html_to_searchable_text(
            response_text
        )
    )

    detail_scan = {
        "internal_link_count": 0,
        "tested_page_count": 0,
        "successful_page_count": 0,
        "failed_page_count": 0,
        "page_results": [],
        "registrant_candidates": [],
    }

    if response.status_code == 200:
        detail_scan = (
            scan_published_dossier_pages(
                session=session,
                index_url=response.url,
                index_html=response_text,
                rml_id=rml_id,
            )
        )

    return {
        "success": (
            response.status_code == 200
        ),
        "status_code": response.status_code,
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
        "html_length": len(
            response_text
        ),
        "searchable_text_length": len(
            searchable_text
        ),
        "matches": find_dossier_text_matches(
            searchable_text
        ),
        "html_preview": response_text[:10000],
        "text_preview": searchable_text[:5000],
        "detail_scan": detail_scan,
        "registrant_candidates": (
            detail_scan[
                "registrant_candidates"
            ]
        ),
        "error": (
            None
            if response.status_code == 200
            else (
                "Published dossier endpoint returned HTTP "
                f"{response.status_code}. "
                f"Response: {response_text[:1000]}"
            )
        ),
    }


# --------------------------------------------------
# MAIN TEST
# --------------------------------------------------
def run_test(cas_number):
    print(
        f"ECHA code version: {CODE_VERSION}",
        flush=True,
    )

    print(
        f"ECHA API test started for CAS "
        f"{cas_number}",
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

    if not selected["rml_id"]:
        raise RuntimeError(
            "The ECHA rmlId could not be extracted "
            f"from this URL: {selected['echa_url']}"
        )

    session = create_http_session()

    # -----------------------------
    # SUBSTANCE
    # -----------------------------
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

    # -----------------------------
    # DOSSIERS
    # -----------------------------
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
                        status or "No filter"
                    ),
                    "success": True,
                    "status_code": (
                        result["status_code"]
                    ),
                    "url": result["url"],
                    "params": result["params"],
                    "item_count": len(items),
                    "items": items,
                    "asset_external_ids": (
                        extract_asset_external_ids(
                            items
                        )
                    ),
                    "raw_body": result["body"],
                    "error": None,
                }
            )

        except Exception as error:
            dossier_attempts.append(
                {
                    "registration_status": (
                        status or "No filter"
                    ),
                    "success": False,
                    "status_code": None,
                    "url": None,
                    "params": request_params,
                    "item_count": 0,
                    "items": [],
                    "asset_external_ids": [],
                    "raw_body": None,
                    "error": str(error),
                }
            )

    # -----------------------------
    # PUBLISHED DOSSIER
    # -----------------------------
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
                    rml_id=selected["rml_id"],
                )
            )

            published_dossier_test = {
                "dossier": first_active_dossier,
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
                "dossier": first_active_dossier,
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
                "html_length": 0,
                "searchable_text_length": 0,
                "matches": [],
                "html_preview": None,
                "text_preview": None,
                "detail_scan": {},
                "registrant_candidates": [],
                "error": str(error),
            }

    return {
        "version": CODE_VERSION,
        "local_substance": selected,
        "substance_result": substance_result,
        "substance_error": substance_error,
        "dossier_attempts": dossier_attempts,
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
    "This test uses the local ECHA registrations export "
    "to resolve a CAS number to an ECHA rmlId, then queries "
    "the substance, dossier-list and published-dossier "
    "endpoints in real time."
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
            "Testing ECHA and scanning "
            "the first active dossier..."
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

            else:
                st.success(
                    "ECHA API test completed."
                )

                substance = test_result[
                    "local_substance"
                ]

                # ----------------------------------
                # 1. LOCAL MATCH
                # ----------------------------------
                st.subheader(
                    "1. Local substance match"
                )

                col1, col2, col3 = (
                    st.columns(3)
                )

                col1.metric(
                    "CAS number",
                    substance["cas_number"],
                )

                col2.metric(
                    "EC number",
                    substance["ec_number"]
                    or "Not available",
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
                                or
                                "Not available"
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

                successful_dossier_call = (
                    False
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
                            successful_dossier_call = (
                                True
                            )

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
                                    attempt["raw_body"]
                                )

                        else:
                            st.error(
                                attempt["error"]
                            )

                # ----------------------------------
                # 4. PUBLISHED DOSSIER
                # ----------------------------------
                st.subheader(
                    "4. Published dossier and registrant scan"
                )

                published_test = (
                    test_result.get(
                        "published_dossier_test"
                    )
                )

                if not published_test:
                    st.warning(
                        "No active dossier with an "
                        "assetExternalId was available."
                    )

                else:
                    detail1, detail2 = (
                        st.columns(2)
                    )

                    detail1.metric(
                        "assetExternalId",
                        (
                            published_test.get(
                                "asset_external_id"
                            )
                            or
                            "Not available"
                        ),
                    )

                    detail2.metric(
                        "Registration number",
                        (
                            published_test.get(
                                "registration_number"
                            )
                            or
                            "Not available"
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

                    detail_scan = (
                        published_test.get(
                            "detail_scan",
                            {},
                        )
                    )

                    registrant_candidates = (
                        published_test.get(
                            "registrant_candidates",
                            [],
                        )
                    )

                    st.markdown(
                        "### Published dossier detail scan"
                    )

                    scan1, scan2, scan3, scan4 = (
                        st.columns(4)
                    )

                    scan1.metric(
                        "Internal detail links",
                        detail_scan.get(
                            "internal_link_count",
                            0,
                        ),
                    )

                    scan2.metric(
                        "Detail pages tested",
                        detail_scan.get(
                            "tested_page_count",
                            0,
                        ),
                    )

                    scan3.metric(
                        "Successful pages",
                        detail_scan.get(
                            "successful_page_count",
                            0,
                        ),
                    )

                    scan4.metric(
                        "Registrant candidates",
                        len(
                            registrant_candidates
                        ),
                    )

                    if registrant_candidates:
                        st.success(
                            "Possible registrant or "
                            "legal-entity information "
                            "was found."
                        )

                        st.dataframe(
                            pd.DataFrame(
                                registrant_candidates
                            ),
                            width="stretch",
                            hide_index=True,
                        )

                        registrant_names = list(
                            dict.fromkeys(
                                candidate["value"]
                                for candidate
                                in registrant_candidates
                                if candidate.get("value")
                            )
                        )

                        st.markdown(
                            "### Possible registrant names"
                        )

                        for registrant_name in (
                            registrant_names
                        ):
                            st.write(
                                f"- {registrant_name}"
                            )

                    else:
                        successful_pages = (
                            detail_scan.get(
                                "successful_page_count",
                                0,
                            )
                        )

                        if successful_pages == 0:
                            st.error(
                                "No internal detail pages "
                                "were retrieved successfully. "
                                "The URL structure still needs "
                                "to be adjusted."
                            )

                        else:
                            st.warning(
                                "The detail pages were retrieved, "
                                "but no public registrant or "
                                "legal-entity name was found."
                            )

                    page_results = (
                        detail_scan.get(
                            "page_results",
                            [],
                        )
                    )

                    if page_results:
                        diagnostics = []

                        for item in page_results:
                            diagnostics.append(
                                {
                                    "page": item.get(
                                        "page_number"
                                    ),
                                    "status": item.get(
                                        "status_code"
                                    ),
                                    "size": item.get(
                                        "response_size"
                                    ),
                                    "candidates": item.get(
                                        "candidate_count"
                                    ),
                                    "url": (
                                        item.get(
                                            "final_url"
                                        )
                                        or
                                        item.get(
                                            "requested_url"
                                        )
                                    ),
                                    "error": item.get(
                                        "error"
                                    ),
                                }
                            )

                        with st.expander(
                            "Published detail-page diagnostics",
                            expanded=False,
                        ):
                            st.dataframe(
                                pd.DataFrame(
                                    diagnostics
                                ),
                                width="stretch",
                                hide_index=True,
                            )

                    with st.expander(
                        "Published dossier text preview",
                        expanded=False,
                    ):
                        st.text(
                            published_test.get(
                                "text_preview"
                            )
                            or
                            "No searchable text was returned."
                        )

                if successful_dossier_call:
                    st.info(
                        "The dossier-list route works. "
                        "V5 tries the internal dossier links "
                        "with and without the .html extension "
                        "and reports successful detail pages "
                        "and possible registrant names."
                    )