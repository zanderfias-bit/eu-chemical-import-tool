import html
import re
import time
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
CODE_VERSION = "ECHA_REST_API_TEST_V10"


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

PUBLISHED_INDEX_ENDPOINT = (
    ECHA_BASE_URL
    + "/html-pages/{asset_external_id}/index.html"
)


# --------------------------------------------------
# REQUEST CONFIGURATION
# --------------------------------------------------
CONNECT_TIMEOUT_SECONDS = 30
READ_TIMEOUT_SECONDS = 90

REQUEST_DELAY_SECONDS = 0.15
MAX_ACTIVE_DOSSIERS = 100

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
# DOCUMENT KEY PATTERN
# --------------------------------------------------
UUID_PATTERN = (
    r"[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}"
)

DOCUMENT_KEY_PATTERN = re.compile(
    rf"^{UUID_PATTERN}_{UUID_PATTERN}$"
)


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
    cas_number = normalise_text(
        cas_number
    )

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
    preview_length=500,
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
# SUBSTANCE API
# --------------------------------------------------
def get_substance_identity(
    session,
    rml_id,
):
    rml_id = normalise_text(
        rml_id
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
# DOSSIER API
# --------------------------------------------------
def get_reach_dossiers(
    session,
    rml_id,
    registration_status=None,
):
    rml_id = normalise_text(
        rml_id
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
        value = api_body.get(
            key
        )

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


def clean_substance_response(
    api_body,
):
    if not isinstance(api_body, dict):
        return api_body

    cleaned_body = api_body.copy()

    cleaned_body.pop(
        "img64",
        None,
    )

    return cleaned_body


def create_dossier_summary(
    items,
):
    rows = []

    for item in items:
        if not isinstance(item, dict):
            continue

        reach_info = (
            item.get("reachDossierInfo")
            or {}
        )

        rows.append(
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

    return rows


# --------------------------------------------------
# HTML PROCESSING
# --------------------------------------------------
def html_to_searchable_text(
    html_content,
):
    if not html_content:
        return ""

    text = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        str(html_content),
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

    text = html.unescape(
        text
    )

    return " ".join(
        text.replace(
            "\xa0",
            " ",
        ).split()
    )


# --------------------------------------------------
# DOSSIER INDEX PARSER
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

        attributes = dict(
            attrs
        )

        href = normalise_text(
            attributes.get(
                "href"
            )
        )

        if not href:
            return

        self.current_link = {
            "href": href,
            "rel": normalise_text(
                attributes.get(
                    "rel"
                )
            ),
            "class": normalise_text(
                attributes.get(
                    "class"
                )
            ),
            "text_parts": [],
        }

    def handle_data(
        self,
        data,
    ):
        if self.current_link is None:
            return

        value = normalise_text(
            data
        )

        if value:
            self.current_link[
                "text_parts"
            ].append(
                value
            )

    def handle_endtag(
        self,
        tag,
    ):
        if (
            tag.lower() == "a"
            and self.current_link is not None
        ):
            text_parts = (
                self.current_link.pop(
                    "text_parts",
                    [],
                )
            )

            self.current_link[
                "label"
            ] = normalise_text(
                " ".join(
                    text_parts
                )
            )

            self.links.append(
                self.current_link
            )

            self.current_link = None


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
            link.get(
                "href"
            )
        )

        if not DOCUMENT_KEY_PATTERN.fullmatch(
            document_key
        ):
            continue

        if document_key in seen:
            continue

        seen.add(
            document_key
        )

        document_links.append(
            {
                "document_key": (
                    document_key
                ),
                "label": (
                    normalise_text(
                        link.get(
                            "label"
                        )
                    )
                    or "No label"
                ),
                "class": normalise_text(
                    link.get(
                        "class"
                    )
                ),
                "rel": normalise_text(
                    link.get(
                        "rel"
                    )
                ),
            }
        )

    return document_links, None


def build_document_url(
    index_url,
    document_key,
):
    return urljoin(
        index_url,
        (
            "documents/"
            + normalise_text(
                document_key
            )
            + ".html"
        ),
    )


# --------------------------------------------------
# V10 DOCUMENT SELECTION
# --------------------------------------------------
def rank_identity_documents(
    document_links,
):
    ranked_documents = []

    for link in document_links:
        label = normalise_text(
            link.get(
                "label"
            )
        )

        css_class = normalise_text(
            link.get(
                "class"
            )
        )

        lower_label = (
            label.lower()
        )

        # Do not use the dossier header itself.
        if (
            "das-header-doc-link"
            in css_class
        ):
            continue

        if (
            lower_label
            == "echa dossier publication"
        ):
            continue

        # Substance is normally the best source.
        if lower_label == "substance":
            score = 0

        # Older dossiers may organise this differently.
        elif any(
            term in lower_label
            for term in (
                "identification",
                "legal entity",
                "registrant",
            )
        ):
            score = 1

        elif any(
            term in lower_label
            for term in (
                "manufacturer",
                "importer",
                "only representative",
            )
        ):
            score = 2

        else:
            score = 10

        ranked_documents.append(
            (
                score,
                link,
            )
        )

    ranked_documents.sort(
        key=lambda item: item[0]
    )

    return [
        link
        for _, link
        in ranked_documents
    ]


def document_has_identity_evidence(
    html_content,
):
    searchable_text = (
        html_to_searchable_text(
            html_content
        ).lower()
    )

    identity_terms = (
        "legal entity",
        "registrant",
        "manufacturer",
        "importer",
        "only representative",
    )

    return any(
        term in searchable_text
        for term in identity_terms
    )


# --------------------------------------------------
# STRUCTURED FIELD EXTRACTION
# --------------------------------------------------
def extract_label_value_pairs(
    html_content,
):
    pairs = []

    table_rows = re.findall(
        r"<tr\b[^>]*>(.*?)</tr>",
        html_content or "",
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

        cell_values = [
            html_to_searchable_text(
                cell
            )
            for cell in cells
        ]

        cell_values = [
            value
            for value in cell_values
            if value
        ]

        if len(cell_values) >= 2:
            pairs.append(
                (
                    cell_values[0],
                    cell_values[1],
                )
            )

    definition_pairs = re.findall(
        (
            r"<dt\b[^>]*>"
            r"(.*?)"
            r"</dt>\s*"
            r"<dd\b[^>]*>"
            r"(.*?)"
            r"</dd>"
        ),
        html_content or "",
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    for (
        label_html,
        value_html,
    ) in definition_pairs:
        label = (
            html_to_searchable_text(
                label_html
            )
        )

        value = (
            html_to_searchable_text(
                value_html
            )
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

        seen.add(
            key
        )

        unique_pairs.append(
            (
                label,
                value,
            )
        )

    return unique_pairs


def clean_published_entity_name(
    value,
):
    value = normalise_text(
        value
    )

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

    value = normalise_text(
        value
    )

    if len(value) <= 2:
        return ""

    if len(value) > 250:
        return ""

    lower_value = (
        value.lower()
    )

    rejected_exact_values = {
        "legal entity",
        "registrant",
        "manufacturer",
        "importer",
        "only representative",
        "third party",
        "not publishable",
        "empty",
        "confidential",
        "not available",
    }

    rejected_fragments = {
        "[not publishable]",
        "flags confidentiality",
        "justification",
        "use restricted",
        "third party flags",
        "back to top",
        "use number use name",
        "further description",
        "substitution activities",
        "regulatory activities",
        "registrant specific",
    }

    if (
        lower_value
        in rejected_exact_values
    ):
        return ""

    if any(
        fragment in lower_value
        for fragment
        in rejected_fragments
    ):
        return ""

    return value


def extract_published_entity_name(
    html_content,
):
    accepted_labels = {
        "legal entity",
        "legal entity name",
        "registrant",
        "registrant name",
        "company name",
        "organisation name",
        "organization name",
    }

    label_value_pairs = (
        extract_label_value_pairs(
            html_content
        )
    )

    for (
        label,
        value,
    ) in label_value_pairs:
        normalised_label = (
            normalise_text(
                label
            ).lower()
        )

        if (
            normalised_label
            not in accepted_labels
        ):
            continue

        cleaned_value = (
            clean_published_entity_name(
                value
            )
        )

        if cleaned_value:
            return (
                cleaned_value,
                label,
            )

    return "", ""


# --------------------------------------------------
# LEGAL ENTITY CLASSIFICATION
# --------------------------------------------------
def classify_legal_entity(
    html_content,
):
    searchable_text = (
        html_to_searchable_text(
            html_content
        )
    )

    lower_text = (
        searchable_text.lower()
    )

    (
        published_name,
        source_field,
    ) = (
        extract_published_entity_name(
            html_content
        )
    )

    if published_name:
        return {
            "legal_entity_status": (
                "Published"
            ),
            "legal_entity_name": (
                published_name
            ),
            "legal_entity_field": (
                source_field
            ),
            "evidence": (
                f"{source_field}: "
                f"{published_name}"
            ),
        }

    not_publishable_patterns = [
        (
            r"legal entity\s*"
            r"\[not publishable\]"
        ),
        (
            r"legal entity name\s*"
            r"\[not publishable\]"
        ),
        (
            r"registrant(?: name)?\s*"
            r"\[not publishable\]"
        ),
    ]

    if any(
        re.search(
            pattern,
            lower_text,
            flags=re.IGNORECASE,
        )
        for pattern
        in not_publishable_patterns
    ):
        return {
            "legal_entity_status": (
                "Not publishable"
            ),
            "legal_entity_name": "",
            "legal_entity_field": (
                "Legal entity"
            ),
            "evidence": (
                "ECHA displays the "
                "legal-entity value as "
                "[Not publishable]."
            ),
        }

    if (
        "legal entity" in lower_text
        or "registrant" in lower_text
    ):
        return {
            "legal_entity_status": (
                "Not available"
            ),
            "legal_entity_name": "",
            "legal_entity_field": "",
            "evidence": (
                "The document contains "
                "identity-related fields, "
                "but no public legal-entity "
                "name was found."
            ),
        }

    return {
        "legal_entity_status": (
            "Not available"
        ),
        "legal_entity_name": "",
        "legal_entity_field": "",
        "evidence": (
            "No public legal-entity field "
            "was found in this document."
        ),
    }


# --------------------------------------------------
# CHECK ONE REGISTRATION
# --------------------------------------------------
def get_published_registration_identity(
    session,
    dossier_item,
    rml_id,
):
    asset_external_id = normalise_text(
        dossier_item.get(
            "assetExternalId"
        )
    )

    registration_number = normalise_text(
        dossier_item.get(
            "registrationNumber"
        )
    )

    reach_info = (
        dossier_item.get(
            "reachDossierInfo"
        )
        or {}
    )

    result = {
        "registration_number": (
            registration_number
        ),
        "registration_status": normalise_text(
            dossier_item.get(
                "registrationStatus"
            )
        ),
        "registration_date": normalise_text(
            dossier_item.get(
                "registrationDate"
            )
        ),
        "last_updated": normalise_text(
            dossier_item.get(
                "lastUpdatedDate"
            )
        ),
        "registration_role": normalise_text(
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
        "asset_external_id": (
            asset_external_id
        ),
        "index_status": None,
        "document_status": None,
        "document_label": "",
        "document_url": "",
        "documents_checked": 0,
        "legal_entity_status": (
            "Not available"
        ),
        "legal_entity_name": "",
        "legal_entity_field": "",
        "evidence": "",
        "error": None,
    }

    if not asset_external_id:
        result["error"] = (
            "The dossier has no "
            "assetExternalId."
        )

        return result

    index_url = (
        PUBLISHED_INDEX_ENDPOINT
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

    try:
        # ----------------------------------
        # LOAD DOSSIER INDEX
        # ----------------------------------
        index_response = (
            execute_echa_request(
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
                preview_length=200,
            )
        )

        result["index_status"] = (
            index_response.status_code
        )

        if (
            index_response.status_code
            != 200
        ):
            result["error"] = (
                "Published dossier index "
                "returned HTTP "
                f"{index_response.status_code}."
            )

            return result

        (
            document_links,
            parse_error,
        ) = extract_document_links(
            index_response.text
        )

        if parse_error:
            result["error"] = (
                "Could not parse the "
                "dossier index: "
                f"{parse_error}"
            )

            return result

        # ----------------------------------
        # V10: RANK REAL DOCUMENTS
        # ----------------------------------
        candidate_documents = (
            rank_identity_documents(
                document_links
            )
        )

        if not candidate_documents:
            result["evidence"] = (
                "No publishable dossier "
                "documents were present "
                "in the index."
            )

            return result

        first_success_status = None
        first_success_url = ""
        first_success_label = ""

        found_identity_evidence = False

        # ----------------------------------
        # V10: CHECK DOCUMENTS
        # ----------------------------------
        for document_link in (
            candidate_documents
        ):
            document_url = (
                build_document_url(
                    index_url=(
                        index_response.url
                    ),
                    document_key=(
                        document_link[
                            "document_key"
                        ]
                    ),
                )
            )

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

            document_response = (
                execute_echa_request(
                    session=session,
                    url=document_url,
                    additional_headers={
                        "Accept": (
                            "text/html,"
                            "application/xhtml+xml,"
                            "application/xml;q=0.9,"
                            "*/*;q=0.8"
                        ),
                        "Referer": (
                            index_response.url
                        ),
                    },
                    preview_length=150,
                )
            )

            result[
                "documents_checked"
            ] += 1

            # Keep the first successful
            # real document as diagnostics.
            if first_success_status is None:
                first_success_status = (
                    document_response.status_code
                )

                first_success_url = (
                    document_response.url
                )

                first_success_label = (
                    document_link[
                        "label"
                    ]
                )

            if (
                document_response.status_code
                != 200
            ):
                continue

            # Ignore documents that have
            # nothing to do with identity.
            if not (
                document_has_identity_evidence(
                    document_response.text
                )
            ):
                continue

            found_identity_evidence = True

            entity_result = (
                classify_legal_entity(
                    document_response.text
                )
            )

            result["document_status"] = (
                document_response.status_code
            )

            result["document_label"] = (
                document_link[
                    "label"
                ]
            )

            result["document_url"] = (
                document_response.url
            )

            result.update(
                entity_result
            )

            # Strong result:
            # stop scanning this dossier.
            if entity_result[
                "legal_entity_status"
            ] in {
                "Published",
                "Not publishable",
            }:
                return result

        # ----------------------------------
        # NOTHING DEFINITIVE FOUND
        # ----------------------------------
        if (
            result["document_status"]
            is None
        ):
            result["document_status"] = (
                first_success_status
            )

            result["document_url"] = (
                first_success_url
            )

            result["document_label"] = (
                first_success_label
            )

        if not found_identity_evidence:
            result["evidence"] = (
                "All published dossier "
                "documents were checked, "
                "but none contained a "
                "public legal-entity or "
                "registrant field."
            )

        elif not result["evidence"]:
            result["evidence"] = (
                "Identity-related fields "
                "were found, but no "
                "published name or explicit "
                "[Not publishable] "
                "legal-entity value was "
                "identified."
            )

        return result

    except Exception as error:
        result["error"] = str(
            error
        )

        return result


# --------------------------------------------------
# CHECK ALL ACTIVE REGISTRATIONS
# --------------------------------------------------
def scan_active_registrations(
    session,
    active_items,
    rml_id,
):
    items_to_scan = (
        active_items[
            :MAX_ACTIVE_DOSSIERS
        ]
    )

    results = []

    total_items = len(
        items_to_scan
    )

    for number, item in enumerate(
        items_to_scan,
        start=1,
    ):
        registration_number = (
            normalise_text(
                item.get(
                    "registrationNumber"
                )
            )
            or "Unknown"
        )

        print(
            "ECHA ACTIVE REGISTRATION SCAN: "
            f"{number}/{total_items} - "
            f"{registration_number}",
            flush=True,
        )

        result = (
            get_published_registration_identity(
                session=session,
                dossier_item=item,
                rml_id=rml_id,
            )
        )

        results.append(
            result
        )

        if number < total_items:
            time.sleep(
                REQUEST_DELAY_SECONDS
            )

    published_name_count = sum(
        1
        for row in results
        if (
            row[
                "legal_entity_status"
            ]
            == "Published"
        )
    )

    not_publishable_count = sum(
        1
        for row in results
        if (
            row[
                "legal_entity_status"
            ]
            == "Not publishable"
        )
    )

    not_available_count = sum(
        1
        for row in results
        if (
            row[
                "legal_entity_status"
            ]
            == "Not available"
        )
    )

    successful_index_count = sum(
        1
        for row in results
        if (
            row["index_status"]
            == 200
        )
    )

    successful_document_count = sum(
        1
        for row in results
        if (
            row[
                "document_status"
            ]
            == 200
        )
    )

    error_count = sum(
        1
        for row in results
        if row["error"]
    )

    return {
        "active_dossier_count": len(
            active_items
        ),
        "scanned_dossier_count": len(
            items_to_scan
        ),
        "published_name_count": (
            published_name_count
        ),
        "not_publishable_count": (
            not_publishable_count
        ),
        "not_available_count": (
            not_available_count
        ),
        "successful_index_count": (
            successful_index_count
        ),
        "successful_document_count": (
            successful_document_count
        ),
        "error_count": (
            error_count
        ),
        "results": results,
    }


# --------------------------------------------------
# COMPLETE TEST
# --------------------------------------------------
def run_test(
    cas_number,
):
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

    dataframe = (
        load_echa_data()
    )

    local_results = (
        find_substance_by_cas(
            dataframe=dataframe,
            cas_number=cas_number,
        )
    )

    if not local_results:
        raise RuntimeError(
            f"CAS {cas_number} was not "
            "found in "
            "reach_registrations.xlsx."
        )

    selected = (
        local_results[0]
    )

    print(
        f"ECHA local match: "
        f"{selected}",
        flush=True,
    )

    if not selected[
        "rml_id"
    ]:
        raise RuntimeError(
            "The ECHA rmlId could not "
            "be extracted from: "
            f"{selected['echa_url']}"
        )

    session = (
        create_http_session()
    )

    # ----------------------------------
    # SUBSTANCE
    # ----------------------------------
    substance_result = None
    substance_error = None

    try:
        substance_result = (
            get_substance_identity(
                session=session,
                rml_id=(
                    selected[
                        "rml_id"
                    ]
                ),
            )
        )

    except Exception as error:
        substance_error = (
            str(error)
        )

    # ----------------------------------
    # DOSSIERS
    # ----------------------------------
    dossier_attempts = []

    for status in (
        None,
        "Active",
        "Inactive",
    ):
        try:
            response = (
                get_reach_dossiers(
                    session=session,
                    rml_id=(
                        selected[
                            "rml_id"
                        ]
                    ),
                    registration_status=(
                        status
                    ),
                )
            )

            items = (
                extract_items(
                    response[
                        "body"
                    ]
                )
            )

            dossier_attempts.append(
                {
                    "registration_status": (
                        status
                        or "No filter"
                    ),
                    "success": True,
                    "status_code": (
                        response[
                            "status_code"
                        ]
                    ),
                    "url": (
                        response[
                            "url"
                        ]
                    ),
                    "params": (
                        response[
                            "params"
                        ]
                    ),
                    "item_count": (
                        len(items)
                    ),
                    "items": items,
                    "summary": (
                        create_dossier_summary(
                            items
                        )
                    ),
                    "raw_body": (
                        response[
                            "body"
                        ]
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
                    "params": {},
                    "item_count": 0,
                    "items": [],
                    "summary": [],
                    "raw_body": None,
                    "error": str(
                        error
                    ),
                }
            )

    # ----------------------------------
    # ACTIVE DOSSIER SCAN
    # ----------------------------------
    active_attempt = next(
        (
            attempt
            for attempt
            in dossier_attempts
            if (
                attempt[
                    "registration_status"
                ]
                == "Active"
                and attempt[
                    "success"
                ]
            )
        ),
        None,
    )

    active_scan = None

    if active_attempt:
        active_scan = (
            scan_active_registrations(
                session=session,
                active_items=(
                    active_attempt[
                        "items"
                    ]
                ),
                rml_id=(
                    selected[
                        "rml_id"
                    ]
                ),
            )
        )

    return {
        "version": (
            CODE_VERSION
        ),
        "local_substance": (
            selected
        ),
        "substance_result": (
            substance_result
        ),
        "substance_error": (
            substance_error
        ),
        "dossier_attempts": (
            dossier_attempts
        ),
        "active_registration_scan": (
            active_scan
        ),
    }


# --------------------------------------------------
# STREAMLIT INTERFACE
# --------------------------------------------------
st.title(
    "ECHA REST API diagnostic"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.write(
    "This version retrieves public REACH "
    "dossiers and checks every active "
    "registration for a published legal-entity "
    "name. Older dossier structures are also "
    "searched. Values marked by ECHA as "
    "not publishable remain hidden."
)

st.caption(
    f"Local ECHA file: "
    f"{ECHA_DATA_FILE}"
)

cas_number = st.text_input(
    "CAS number",
    value="128-37-0",
    placeholder=(
        "For example: 128-37-0"
    ),
)

run_button = st.button(
    "Run ECHA API test",
    type="primary",
)


if run_button:
    cleaned_cas = (
        normalise_text(
            cas_number
        )
    )

    if not (
        looks_like_cas_number(
            cleaned_cas
        )
    ):
        st.error(
            "Enter a valid CAS number, "
            "for example 128-37-0."
        )

        st.stop()

    with st.spinner(
        "Retrieving ECHA data and "
        "checking all active "
        "published dossiers..."
    ):
        try:
            test_result = (
                run_test(
                    cleaned_cas
                )
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

    substance = (
        test_result[
            "local_substance"
        ]
    )

    # ----------------------------------
    # 1. LOCAL SUBSTANCE MATCH
    # ----------------------------------
    st.subheader(
        "1. Local substance match"
    )

    col1, col2, col3 = (
        st.columns(3)
    )

    col1.metric(
        "CAS number",
        substance[
            "cas_number"
        ],
    )

    col2.metric(
        "EC number",
        (
            substance[
                "ec_number"
            ]
            or "Not available"
        ),
    )

    col3.metric(
        "ECHA rmlId",
        substance[
            "rml_id"
        ],
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
            substance_api[
                "body"
            ]
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
            "The substance endpoint "
            "failed."
        )

    # ----------------------------------
    # 3. DOSSIER API
    # ----------------------------------
    st.subheader(
        "3. REACH dossier API"
    )

    for attempt in (
        test_result[
            "dossier_attempts"
        ]
    ):
        expander_title = (
            "Registration status: "
            f"{attempt['registration_status']} "
            f"({attempt['item_count']})"
        )

        with st.expander(
            expander_title,
            expanded=(
                attempt[
                    "registration_status"
                ]
                == "Active"
            ),
        ):
            if attempt[
                "success"
            ]:
                st.success(
                    "HTTP "
                    f"{attempt['status_code']} | "
                    f"{attempt['item_count']} "
                    "dossier item(s)"
                )

                if attempt[
                    "summary"
                ]:
                    st.dataframe(
                        pd.DataFrame(
                            attempt[
                                "summary"
                            ]
                        ),
                        width="stretch",
                        hide_index=True,
                    )

                with st.expander(
                    "Request details",
                    expanded=False,
                ):
                    st.json(
                        attempt[
                            "params"
                        ]
                    )

                    st.code(
                        attempt[
                            "url"
                        ],
                        language=None,
                    )

                with st.expander(
                    "Raw dossier JSON",
                    expanded=False,
                ):
                    st.json(
                        attempt[
                            "raw_body"
                        ]
                    )

            else:
                st.error(
                    attempt[
                        "error"
                    ]
                )

    # ----------------------------------
    # 4. ACTIVE REGISTRATIONS
    # ----------------------------------
    st.subheader(
        "4. Active REACH registrations "
        "and legal entities"
    )

    active_scan = (
        test_result.get(
            "active_registration_scan"
        )
    )

    if not active_scan:
        st.warning(
            "No successful Active "
            "dossier response was "
            "available for scanning."
        )

    else:
        (
            metric1,
            metric2,
            metric3,
            metric4,
            metric5,
        ) = st.columns(5)

        metric1.metric(
            "Active dossiers",
            active_scan[
                "active_dossier_count"
            ],
        )

        metric2.metric(
            "Dossiers scanned",
            active_scan[
                "scanned_dossier_count"
            ],
        )

        metric3.metric(
            "Published names",
            active_scan[
                "published_name_count"
            ],
        )

        metric4.metric(
            "Not publishable",
            active_scan[
                "not_publishable_count"
            ],
        )

        metric5.metric(
            "Not available",
            active_scan[
                "not_available_count"
            ],
        )

        st.caption(
            "Published index HTTP 200: "
            f"{active_scan['successful_index_count']} | "
            "Selected document HTTP 200: "
            f"{active_scan['successful_document_count']} | "
            "Errors: "
            f"{active_scan['error_count']}"
        )

        if active_scan[
            "published_name_count"
        ]:
            st.success(
                "One or more legal-entity "
                "names are explicitly published "
                "in the ECHA dossier."
            )

        elif active_scan[
            "not_publishable_count"
        ]:
            st.info(
                "ECHA marks the legal-entity "
                "identity as Not publishable "
                "for one or more dossiers. "
                "V10 does not attempt to infer "
                "or reconstruct hidden names."
            )

        else:
            st.warning(
                "No public legal-entity "
                "name was found in the "
                "published dossier documents."
            )

        # ----------------------------------
        # MAIN RESULT TABLE
        # ----------------------------------
        display_columns = [
            "registration_number",
            "registration_status",
            "registration_date",
            "last_updated",
            "registration_role",
            "dossier_subtype",
            "legal_entity_status",
            "legal_entity_name",
            "document_label",
            "documents_checked",
            "index_status",
            "document_status",
            "error",
        ]

        results_dataframe = (
            pd.DataFrame(
                active_scan[
                    "results"
                ]
            )
        )

        if not (
            results_dataframe.empty
        ):
            st.dataframe(
                results_dataframe[
                    display_columns
                ],
                width="stretch",
                hide_index=True,
            )

        # ----------------------------------
        # PUBLISHED NAMES
        # ----------------------------------
        published_rows = [
            row
            for row
            in active_scan[
                "results"
            ]
            if (
                row[
                    "legal_entity_status"
                ]
                == "Published"
            )
        ]

        if published_rows:
            st.markdown(
                "### Published "
                "legal-entity names"
            )

            published_dataframe = (
                pd.DataFrame(
                    [
                        {
                            "registration_number": (
                                row[
                                    "registration_number"
                                ]
                            ),
                            "legal_entity_name": (
                                row[
                                    "legal_entity_name"
                                ]
                            ),
                            "source_field": (
                                row[
                                    "legal_entity_field"
                                ]
                            ),
                            "document_label": (
                                row[
                                    "document_label"
                                ]
                            ),
                            "source_url": (
                                row[
                                    "document_url"
                                ]
                            ),
                        }
                        for row
                        in published_rows
                    ]
                )
            )

            st.dataframe(
                published_dataframe,
                width="stretch",
                hide_index=True,
            )

        # ----------------------------------
        # DETAILED EVIDENCE
        # ----------------------------------
        with st.expander(
            "Detailed scan evidence",
            expanded=False,
        ):
            evidence_rows = [
                {
                    "registration_number": (
                        row[
                            "registration_number"
                        ]
                    ),
                    "legal_entity_status": (
                        row[
                            "legal_entity_status"
                        ]
                    ),
                    "evidence": (
                        row[
                            "evidence"
                        ]
                    ),
                    "document_label": (
                        row[
                            "document_label"
                        ]
                    ),
                    "documents_checked": (
                        row.get(
                            "documents_checked",
                            0,
                        )
                    ),
                    "asset_external_id": (
                        row[
                            "asset_external_id"
                        ]
                    ),
                    "document_url": (
                        row[
                            "document_url"
                        ]
                    ),
                    "error": (
                        row[
                            "error"
                        ]
                    ),
                }
                for row
                in active_scan[
                    "results"
                ]
            ]

            st.dataframe(
                pd.DataFrame(
                    evidence_rows
                ),
                width="stretch",
                hide_index=True,
            )