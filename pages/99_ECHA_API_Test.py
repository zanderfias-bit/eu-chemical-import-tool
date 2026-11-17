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
# PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="ECHA REST API Test",
    page_icon="🧪",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_REST_API_TEST_V8"


# --------------------------------------------------
# LOCAL DATA
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

ECHA_DATA_FILE = (
    BASE_DIR
    / "data"
    / "reach_registrations.xlsx"
)

ECHA_SHEET_NAME = "Substances list"

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

MAX_DOCUMENTS_TO_SCAN = 50

REQUEST_HEADERS = {
    "Accept": (
        "application/json, text/plain, text/html, "
        "application/xhtml+xml, */*"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}


# --------------------------------------------------
# SEARCH TERMS
# --------------------------------------------------
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
    "Manufacturer",
    "Importer name",
    "Importer",
    "Only representative",
    "Third party representative",
]

DIAGNOSTIC_TERMS = [
    "Legal entity",
    "Registrant",
    "Company",
    "Organisation",
    "Organization",
    "Manufacturer",
    "Importer",
    "Only representative",
    "Registration holder",
    "Applicant",
    "Address",
    "Country",
    "Registration number",
]

EXCLUDED_CANDIDATE_PHRASES = [
    "registrant specific composition",
    "registrant-specific composition",
    "registrant specific analytical information",
    "registrant specific",
    "information provided by the registrant",
    "information submitted by the registrant",
    "registrants may",
    "registrants shall",
    "registration dossier",
    "dossier publication",
]

GENERIC_CANDIDATE_VALUES = {
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
    "no data",
    "no information",
}


# --------------------------------------------------
# GENERAL HELPERS
# --------------------------------------------------
def normalise_text(value):
    if value is None:
        return ""

    value = str(value).strip()

    if value.lower() in {
        "",
        "nan",
        "none",
        "null",
    }:
        return ""

    if value == "-":
        return ""

    return " ".join(
        value.replace("\xa0", " ").split()
    ).strip()


def looks_like_cas_number(value):
    return bool(
        re.fullmatch(
            r"\d{2,7}-\d{2}-\d",
            normalise_text(value),
        )
    )


def extract_rml_id(echa_url):
    match = re.search(
        r"/(\d{3}\.\d{3}\.\d{3})(?:/|$)",
        normalise_text(echa_url),
    )

    if not match:
        return ""

    return match.group(1)


def clean_substance_response(api_body):
    if not isinstance(api_body, dict):
        return api_body

    cleaned_body = api_body.copy()
    cleaned_body.pop("img64", None)

    return cleaned_body


# --------------------------------------------------
# LOCAL ECHA EXPORT
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
# HTTP SESSION
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


def execute_echa_request(
    session,
    url,
    params=None,
    additional_headers=None,
    preview_length=1000,
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
            "The ECHA request timed out: "
            f"{error}"
        ) from error

    except requests.RequestException as error:
        raise RuntimeError(
            "The ECHA request failed: "
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
        f"{response.text[:preview_length]}",
        flush=True,
    )

    return response


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
# ECHA API
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


def create_dossier_summary(items):
    summaries = []

    for item in items:
        if not isinstance(item, dict):
            continue

        reach_info = (
            item.get("reachDossierInfo")
            or {}
        )

        summaries.append(
            {
                "status": normalise_text(
                    item.get(
                        "registrationStatus"
                    )
                ),
                "registration_number": normalise_text(
                    item.get(
                        "registrationNumber"
                    )
                ),
                "registration_date": normalise_text(
                    item.get(
                        "registrationDate"
                    )
                ),
                "last_updated": normalise_text(
                    item.get(
                        "lastUpdatedDate"
                    )
                ),
                "role": normalise_text(
                    reach_info.get(
                        "registrationRole"
                    )
                ),
                "dossier_subtype": normalise_text(
                    reach_info.get(
                        "dossierSubtype"
                    )
                ),
                "details": normalise_text(
                    reach_info.get(
                        "details"
                    )
                ),
                "asset_external_id": normalise_text(
                    item.get(
                        "assetExternalId"
                    )
                ),
            }
        )

    return summaries


# --------------------------------------------------
# HTML TEXT PROCESSING
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
        r"<[^>]+>",
        " ",
        text,
    )

    text = html.unescape(text)

    return " ".join(
        text.replace("\xa0", " ").split()
    )


# --------------------------------------------------
# PUBLISHED DOSSIER INDEX PARSER
# --------------------------------------------------
class DossierIndexParser(HTMLParser):
    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )

        self.current_link = None
        self.links = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        if tag.lower() != "a":
            return

        attributes = dict(attrs)

        href = normalise_text(
            attributes.get("href")
        )

        relationship = normalise_text(
            attributes.get("rel")
        )

        css_class = normalise_text(
            attributes.get("class")
        )

        if not href:
            return

        self.current_link = {
            "href": href,
            "rel": relationship,
            "class": css_class,
            "text_parts": [],
        }

    def handle_data(
        self,
        data,
    ):
        if self.current_link is None:
            return

        clean_data = normalise_text(data)

        if clean_data:
            self.current_link[
                "text_parts"
            ].append(
                clean_data
            )

    def handle_endtag(
        self,
        tag,
    ):
        if (
            tag.lower() == "a"
            and self.current_link is not None
        ):
            self.current_link["label"] = (
                normalise_text(
                    " ".join(
                        self.current_link[
                            "text_parts"
                        ]
                    )
                )
            )

            self.current_link.pop(
                "text_parts",
                None,
            )

            self.links.append(
                self.current_link
            )

            self.current_link = None


def looks_like_document_key(value):
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


def extract_document_links(
    index_html,
):
    parser = DossierIndexParser()

    try:
        parser.feed(
            index_html or ""
        )

    except Exception as error:
        return [], str(error)

    document_links = []
    seen = set()

    for link in parser.links:
        document_key = normalise_text(
            link.get("href")
        )

        if not looks_like_document_key(
            document_key
        ):
            continue

        if document_key in seen:
            continue

        seen.add(document_key)

        document_links.append(
            {
                "document_key": document_key,
                "label": (
                    normalise_text(
                        link.get("label")
                    )
                    or "No label"
                ),
                "class": normalise_text(
                    link.get("class")
                ),
                "rel": normalise_text(
                    link.get("rel")
                ),
            }
        )

    return document_links, None


# --------------------------------------------------
# DOCUMENT URL
# --------------------------------------------------
def build_document_url(
    index_url,
    document_key,
):
    document_key = normalise_text(
        document_key
    )

    return urljoin(
        index_url,
        (
            "documents/"
            + document_key
            + ".html"
        ),
    )


# --------------------------------------------------
# DOCUMENT FIELD EXTRACTION
# --------------------------------------------------
def extract_html_label_value_pairs(
    html_content,
):
    pairs = []

    if not html_content:
        return pairs

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
            (
                r"<(?:th|td)\b[^>]*>"
                r"(.*?)"
                r"</(?:th|td)>"
            ),
            row_html,
            flags=(
                re.IGNORECASE
                | re.DOTALL
            ),
        )

        cell_texts = [
            html_to_searchable_text(
                cell
            )
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

    definition_pairs = re.findall(
        (
            r"<dt\b[^>]*>(.*?)</dt>\s*"
            r"<dd\b[^>]*>(.*?)</dd>"
        ),
        html_content,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    for (
        label_html,
        value_html,
    ) in definition_pairs:
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

    block_pairs = re.findall(
        (
            r"<(?:label|strong|b)\b[^>]*>"
            r"(.*?)"
            r"</(?:label|strong|b)>"
            r"\s*"
            r"<(?:span|div|p)\b[^>]*>"
            r"(.*?)"
            r"</(?:span|div|p)>"
        ),
        html_content,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    for (
        label_html,
        value_html,
    ) in block_pairs:
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

    unique_pairs = []
    seen = set()

    for label, value in pairs:
        key = (
            label.lower(),
            value.lower(),
        )

        if key in seen:
            continue

        seen.add(key)

        unique_pairs.append(
            (
                label,
                value,
            )
        )

    return unique_pairs


def clean_possible_candidate(
    value,
):
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

    if lower_value in (
        GENERIC_CANDIDATE_VALUES
    ):
        return ""

    if any(
        phrase in lower_value
        for phrase in EXCLUDED_CANDIDATE_PHRASES
    ):
        return ""

    return value


def extract_registrant_candidates(
    html_content,
    document_label,
    source_url,
):
    candidates = []

    label_value_pairs = (
        extract_html_label_value_pairs(
            html_content
        )
    )

    for label, value in label_value_pairs:
        matching_term = None

        for term in REGISTRANT_FIELD_TERMS:
            if (
                term.lower()
                in label.lower()
            ):
                matching_term = term
                break

        if not matching_term:
            continue

        cleaned_value = (
            clean_possible_candidate(
                value
            )
        )

        if not cleaned_value:
            continue

        candidates.append(
            {
                "document": document_label,
                "field": label,
                "value": cleaned_value,
                "method": (
                    "Structured HTML field"
                ),
                "source_url": source_url,
            }
        )

    searchable_text = (
        html_to_searchable_text(
            html_content
        )
    )

    for term in REGISTRANT_FIELD_TERMS:
        pattern = re.compile(
            (
                re.escape(term)
                + r"\s*(?::|-)?\s*"
                + r"(.{3,250})"
            ),
            flags=re.IGNORECASE,
        )

        match = pattern.search(
            searchable_text
        )

        if not match:
            continue

        candidate_value = (
            match.group(1)
        )

        candidate_value = re.split(
            (
                r"\s{2,}|"
                r"(?:Registration number|"
                r"Registration date|"
                r"Status|"
                r"Address|"
                r"Country|"
                r"UUID|"
                r"General information|"
                r"Administrative data)"
            ),
            candidate_value,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]

        cleaned_value = (
            clean_possible_candidate(
                candidate_value
            )
        )

        if not cleaned_value:
            continue

        candidates.append(
            {
                "document": document_label,
                "field": term,
                "value": cleaned_value,
                "method": "Text fallback",
                "source_url": source_url,
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


def find_terms_in_document(
    searchable_text,
):
    found_terms = []

    lower_text = searchable_text.lower()

    for term in DIAGNOSTIC_TERMS:
        if term.lower() in lower_text:
            found_terms.append(
                term
            )

    return found_terms


# --------------------------------------------------
# SCAN PUBLISHED DOCUMENTS
# --------------------------------------------------
def scan_published_documents(
    session,
    index_url,
    document_links,
):
    documents_to_scan = (
        document_links[
            :MAX_DOCUMENTS_TO_SCAN
        ]
    )

    document_results = []
    all_candidates = []

    for (
        document_number,
        document_link,
    ) in enumerate(
        documents_to_scan,
        start=1,
    ):
        document_key = (
            document_link[
                "document_key"
            ]
        )

        document_label = (
            document_link[
                "label"
            ]
        )

        document_url = (
            build_document_url(
                index_url=index_url,
                document_key=document_key,
            )
        )

        try:
            response = execute_echa_request(
                session=session,
                url=document_url,
                additional_headers={
                    "Accept": (
                        "text/html,"
                        "application/xhtml+xml,"
                        "application/xml;q=0.9,"
                        "*/*;q=0.8"
                    ),
                    "Referer": index_url,
                },
                preview_length=500,
            )

            searchable_text = ""

            candidates = []

            found_terms = []

            if response.status_code == 200:
                searchable_text = (
                    html_to_searchable_text(
                        response.text
                    )
                )

                found_terms = (
                    find_terms_in_document(
                        searchable_text
                    )
                )

                candidates = (
                    extract_registrant_candidates(
                        html_content=response.text,
                        document_label=(
                            document_label
                        ),
                        source_url=response.url,
                    )
                )

                all_candidates.extend(
                    candidates
                )

            document_results.append(
                {
                    "document_number": (
                        document_number
                    ),
                    "document_key": (
                        document_key
                    ),
                    "document_label": (
                        document_label
                    ),
                    "requested_url": (
                        document_url
                    ),
                    "final_url": (
                        response.url
                    ),
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
                    "response_size": len(
                        response.content
                    ),
                    "text_length": len(
                        searchable_text
                    ),
                    "found_terms": (
                        found_terms
                    ),
                    "candidate_count": len(
                        candidates
                    ),
                    "candidates": (
                        candidates
                    ),
                    "text_preview": (
                        searchable_text[:1500]
                    ),
                    "error": (
                        None
                        if response.status_code == 200
                        else (
                            "Document returned "
                            f"HTTP {response.status_code}."
                        )
                    ),
                }
            )

        except Exception as error:
            document_results.append(
                {
                    "document_number": (
                        document_number
                    ),
                    "document_key": (
                        document_key
                    ),
                    "document_label": (
                        document_label
                    ),
                    "requested_url": (
                        document_url
                    ),
                    "final_url": None,
                    "status_code": None,
                    "content_type": None,
                    "response_size": 0,
                    "text_length": 0,
                    "found_terms": [],
                    "candidate_count": 0,
                    "candidates": [],
                    "text_preview": "",
                    "error": str(error),
                }
            )

    unique_candidates = []
    seen_candidates = set()

    for candidate in all_candidates:
        value = normalise_text(
            candidate.get("value")
        )

        if not value:
            continue

        key = value.lower()

        if key in seen_candidates:
            continue

        seen_candidates.add(key)

        unique_candidates.append(
            candidate
        )

    return {
        "document_count": len(
            document_links
        ),
        "tested_document_count": len(
            documents_to_scan
        ),
        "successful_document_count": sum(
            1
            for item in document_results
            if item.get("status_code") == 200
        ),
        "failed_document_count": sum(
            1
            for item in document_results
            if item.get("status_code") != 200
        ),
        "documents_with_search_terms": sum(
            1
            for item in document_results
            if item.get("found_terms")
        ),
        "document_results": (
            document_results
        ),
        "registrant_candidates": (
            unique_candidates
        ),
    }


# --------------------------------------------------
# PUBLISHED DOSSIER
# --------------------------------------------------
def get_published_dossier(
    session,
    asset_external_id,
    rml_id,
):
    asset_external_id = normalise_text(
        asset_external_id
    )

    if not asset_external_id:
        raise RuntimeError(
            "The assetExternalId is empty."
        )

    index_url = (
        PUBLISHED_DOSSIER_ENDPOINT
        .format(
            asset_external_id=(
                asset_external_id
            )
        )
    )

    referer = (
        f"{ECHA_BASE_URL}/"
        f"{normalise_text(rml_id)}"
        f"/overview"
    )

    response = execute_echa_request(
        session=session,
        url=index_url,
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

    empty_scan = {
        "document_count": 0,
        "tested_document_count": 0,
        "successful_document_count": 0,
        "failed_document_count": 0,
        "documents_with_search_terms": 0,
        "document_results": [],
        "registrant_candidates": [],
    }

    if response.status_code != 200:
        return {
            "success": False,
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
            "document_links": [],
            "index_parse_error": None,
            "document_scan": empty_scan,
            "error": (
                "Published dossier index "
                "returned HTTP "
                f"{response.status_code}. "
                f"Response: "
                f"{response.text[:1000]}"
            ),
        }

    (
        document_links,
        index_parse_error,
    ) = extract_document_links(
        response.text
    )

    document_scan = (
        scan_published_documents(
            session=session,
            index_url=response.url,
            document_links=document_links,
        )
    )

    return {
        "success": True,
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
        "document_links": (
            document_links
        ),
        "index_parse_error": (
            index_parse_error
        ),
        "document_scan": (
            document_scan
        ),
        "error": None,
    }


# --------------------------------------------------
# COMPLETE TEST
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

    local_results = (
        find_substance_by_cas(
            dataframe=dataframe,
            cas_number=cas_number,
        )
    )

    if not local_results:
        raise RuntimeError(
            f"CAS {cas_number} was not found "
            "in reach_registrations.xlsx."
        )

    selected = local_results[0]

    print(
        f"ECHA local match: {selected}",
        flush=True,
    )

    if not selected["rml_id"]:
        raise RuntimeError(
            "The ECHA rmlId could not be "
            "extracted from this URL: "
            f"{selected['echa_url']}"
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
                        result["status_code"]
                    ),
                    "url": result["url"],
                    "params": result["params"],
                    "item_count": len(items),
                    "items": items,
                    "summary": (
                        create_dossier_summary(
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
                        status
                        or "No filter"
                    ),
                    "success": False,
                    "status_code": None,
                    "url": None,
                    "params": {},
                    "item_count": 0,
                    "items": [],
                    "summary": [],
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
                "document_links": [],
                "index_parse_error": None,
                "document_scan": {
                    "document_count": 0,
                    "tested_document_count": 0,
                    "successful_document_count": 0,
                    "failed_document_count": 0,
                    "documents_with_search_terms": 0,
                    "document_results": [],
                    "registrant_candidates": [],
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
    "This test resolves a CAS number through the "
    "local ECHA export, queries the substance and "
    "dossier-list APIs, and scans the published "
    "dossier documents."
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
            "the first active published dossier..."
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
        # 1. LOCAL SUBSTANCE MATCH
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

            substance_body = (
                substance_api["body"]
            )

            st.success(
                "The substance endpoint "
                "returned HTTP "
                f"{substance_api['status_code']}."
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
        # 3. DOSSIER LIST
        # ----------------------------------
        st.subheader(
            "3. REACH registration dossiers"
        )

        for attempt in test_result[
            "dossier_attempts"
        ]:
            with st.expander(
                (
                    "Registration status: "
                    f"{attempt['registration_status']} "
                    f"({attempt['item_count']})"
                ),
                expanded=(
                    attempt[
                        "registration_status"
                    ]
                    == "Active"
                ),
            ):
                if attempt["success"]:
                    st.success(
                        "HTTP "
                        f"{attempt['status_code']} | "
                        f"{attempt['item_count']} "
                        "dossier item(s)"
                    )

                    if attempt["summary"]:
                        st.dataframe(
                            pd.DataFrame(
                                attempt["summary"]
                            ),
                            width="stretch",
                            hide_index=True,
                        )

                    with st.expander(
                        "Request details",
                        expanded=False,
                    ):
                        st.json(
                            attempt["params"]
                        )

                        st.code(
                            attempt["url"],
                            language=None,
                        )

                    with st.expander(
                        "Raw dossier JSON",
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
            "4. Published dossier document scan"
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
                    "**Published dossier index**"
                )

                st.code(
                    published_test["url"],
                    language=None,
                )

            if not published_test.get(
                "success"
            ):
                st.error(
                    published_test.get(
                        "error"
                    )
                    or
                    "Published dossier scan failed."
                )

            else:
                st.success(
                    "Published dossier index "
                    "returned HTTP "
                    f"{published_test['status_code']}."
                )

                document_scan = (
                    published_test.get(
                        "document_scan",
                        {},
                    )
                )

                registrant_candidates = (
                    document_scan.get(
                        "registrant_candidates",
                        [],
                    )
                )

                (
                    metric1,
                    metric2,
                    metric3,
                    metric4,
                    metric5,
                ) = st.columns(5)

                metric1.metric(
                    "Documents found",
                    document_scan.get(
                        "document_count",
                        0,
                    ),
                )

                metric2.metric(
                    "Documents tested",
                    document_scan.get(
                        "tested_document_count",
                        0,
                    ),
                )

                metric3.metric(
                    "HTTP 200 documents",
                    document_scan.get(
                        "successful_document_count",
                        0,
                    ),
                )

                metric4.metric(
                    "Documents with terms",
                    document_scan.get(
                        "documents_with_search_terms",
                        0,
                    ),
                )

                metric5.metric(
                    "Candidate names",
                    len(
                        registrant_candidates
                    ),
                )

                # --------------------------
                # CANDIDATE RESULTS
                # --------------------------
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

                else:
                    successful_count = (
                        document_scan.get(
                            "successful_document_count",
                            0,
                        )
                    )

                    if successful_count == 0:
                        st.error(
                            "The document routes still "
                            "did not return HTTP 200. "
                            "Check the document diagnostics."
                        )

                    else:
                        st.warning(
                            "The published documents were "
                            "retrieved, but no public "
                            "registrant or legal-entity "
                            "name was identified."
                        )

                # --------------------------
                # DOCUMENT DIAGNOSTICS
                # --------------------------
                document_results = (
                    document_scan.get(
                        "document_results",
                        [],
                    )
                )

                diagnostics = []

                for item in document_results:
                    diagnostics.append(
                        {
                            "document": (
                                item.get(
                                    "document_number"
                                )
                            ),
                            "label": (
                                item.get(
                                    "document_label"
                                )
                            ),
                            "status": (
                                item.get(
                                    "status_code"
                                )
                            ),
                            "response_size": (
                                item.get(
                                    "response_size"
                                )
                            ),
                            "text_length": (
                                item.get(
                                    "text_length"
                                )
                            ),
                            "terms": ", ".join(
                                item.get(
                                    "found_terms",
                                    [],
                                )
                            ),
                            "candidates": (
                                item.get(
                                    "candidate_count"
                                )
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
                            "error": (
                                item.get(
                                    "error"
                                )
                            ),
                        }
                    )

                if diagnostics:
                    st.markdown(
                        "### Published document diagnostics"
                    )

                    st.dataframe(
                        pd.DataFrame(
                            diagnostics
                        ),
                        width="stretch",
                        hide_index=True,
                    )

                # --------------------------
                # RELEVANT DOCUMENT PREVIEWS
                # --------------------------
                relevant_documents = [
                    item
                    for item in document_results
                    if (
                        item.get("found_terms")
                        or
                        item.get(
                            "candidate_count",
                            0,
                        ) > 0
                    )
                ]

                if relevant_documents:
                    st.markdown(
                        "### Relevant document previews"
                    )

                    for item in relevant_documents:
                        title = (
                            f"{item.get('document_number')}. "
                            f"{item.get('document_label')}"
                        )

                        with st.expander(
                            title,
                            expanded=False,
                        ):
                            st.write(
                                "**Terms found:** "
                                + (
                                    ", ".join(
                                        item.get(
                                            "found_terms",
                                            [],
                                        )
                                    )
                                    or
                                    "None"
                                )
                            )

                            st.code(
                                item.get(
                                    "final_url"
                                )
                                or
                                item.get(
                                    "requested_url"
                                )
                                or
                                "No URL",
                                language=None,
                            )

                            st.text(
                                item.get(
                                    "text_preview"
                                )
                                or
                                "No searchable text."
                            )