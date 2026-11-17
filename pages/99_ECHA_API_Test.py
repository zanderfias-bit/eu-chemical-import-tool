import html
import re
from html.parser import HTMLParser
from pathlib import Path
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
    page_title="ECHA REST API Test",
    page_icon="🧪",
    layout="wide",
)

CODE_VERSION = "ECHA_REST_API_TEST_V6"


# --------------------------------------------------
# PATHS AND COLUMNS
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
# ECHA ROUTES
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
        r"<[^>]+>",
        " ",
        text,
    )

    text = html.unescape(text)

    return " ".join(
        text.replace("\xa0", " ").split()
    )


# --------------------------------------------------
# HTML LINK PARSER
# --------------------------------------------------
class DossierLinkParser(HTMLParser):
    def __init__(self):
        super().__init__(
            convert_charrefs=True
        )

        self.hrefs = []
        self.scripts = []

    def handle_starttag(
        self,
        tag,
        attrs,
    ):
        attributes = dict(attrs)

        href = attributes.get(
            "href"
        )

        src = attributes.get(
            "src"
        )

        if href:
            self.hrefs.append(
                href
            )

        if (
            tag.lower() == "script"
            and src
        ):
            self.scripts.append(
                src
            )


# --------------------------------------------------
# EXTRACT REFERENCES FROM INDEX
# --------------------------------------------------
def extract_index_references(
    index_html,
):
    parser = DossierLinkParser()

    try:
        parser.feed(
            index_html or ""
        )

    except Exception:
        pass

    hrefs = list(
        parser.hrefs
    )

    scripts = list(
        parser.scripts
    )

    # Regex fallback.
    #
    # Important V6 fix:
    # capture the VALUE between the quotes.
    href_matches = re.findall(
        r'''href\s*=\s*[^"']+["']''',
        index_html or "",
        flags=re.IGNORECASE,
    )

    hrefs.extend(
        href_matches
    )

    script_matches = re.findall(
        r'''<script\b[^"']+["']''',
        index_html or "",
        flags=re.IGNORECASE,
    )

    scripts.extend(
        script_matches
    )

    clean_hrefs = []

    for value in hrefs:
        value = html.unescape(
            str(value).strip()
        )

        if value:
            clean_hrefs.append(
                value
            )

    clean_scripts = []

    for value in scripts:
        value = html.unescape(
            str(value).strip()
        )

        if value:
            clean_scripts.append(
                value
            )

    return (
        list(
            dict.fromkeys(
                clean_hrefs
            )
        ),
        list(
            dict.fromkeys(
                clean_scripts
            )
        ),
    )


# --------------------------------------------------
# EXTRACT INTERNAL DOSSIER LINKS
# --------------------------------------------------
def extract_internal_dossier_links(
    index_html,
    index_url,
):
    (
        href_values,
        script_values,
    ) = extract_index_references(
        index_html
    )

    links = []
    ignored_assets = []

    for href in href_values:
        lower_href = href.lower()

        if lower_href.startswith(
            (
                "#",
                "javascript:",
                "mailto:",
                "tel:",
            )
        ):
            continue

        if lower_href.startswith(
            (
                "assets/",
                "./assets/",
            )
        ):
            ignored_assets.append(
                href
            )

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

        if (
            "/html-pages/"
            not in absolute_url
        ):
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

        if "." not in last_path_part:
            absolute_url = (
                absolute_url.rstrip("/")
                + ".html"
            )

        links.append(
            absolute_url
        )

    return {
        "all_hrefs": href_values,
        "scripts": script_values,
        "ignored_asset_hrefs": (
            ignored_assets
        ),
        "internal_links": list(
            dict.fromkeys(
                links
            )
        ),
    }


# --------------------------------------------------
# CLEAN REGISTRANT CANDIDATE
# --------------------------------------------------
def clean_possible_registrant_value(
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
        r"<dt\b[^>]*>(.*?)</dt>\s*"
        r"<dd\b[^>]*>(.*?)</dd>",
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

    return pairs


# --------------------------------------------------
# EXTRACT REGISTRANT CANDIDATES
# --------------------------------------------------
def extract_registrant_candidates(
    html_content,
    source_url,
):
    candidates = []

    for (
        label,
        value,
    ) in extract_html_label_value_pairs(
        html_content
    ):
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
                    "method": (
                        "HTML label/value"
                    ),
                }
            )

    searchable_text = (
        html_to_searchable_text(
            html_content
        )
    )

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

        candidate_value = (
            match.group(1)
        )

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
                    "method": (
                        "Text search"
                    ),
                }
            )

    unique_candidates = []
    seen = set()

    for candidate in candidates:
        key = (
            candidate[
                "field"
            ].lower(),
            candidate[
                "value"
            ].lower(),
            candidate[
                "source_url"
            ],
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        unique_candidates.append(
            candidate
        )

    return unique_candidates


# --------------------------------------------------
# GET PUBLISHED DETAIL PAGE
# --------------------------------------------------
def get_published_detail_page(
    session,
    detail_url,
    referer,
):
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

    if last_path_part.endswith(
        ".html"
    ):
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
        dict.fromkeys(
            candidate_urls
        )
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

        if (
            response.status_code
            == 200
        ):
            return response

        if (
            response.status_code
            != 404
        ):
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
    link_diagnostics = (
        extract_internal_dossier_links(
            index_html=index_html,
            index_url=index_url,
        )
    )

    internal_links = (
        link_diagnostics[
            "internal_links"
        ]
    )

    links_to_test = (
        internal_links[
            :MAX_PUBLISHED_DETAIL_PAGES
        ]
    )

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

    for (
        page_number,
        detail_url,
    ) in enumerate(
        links_to_test,
        start=1,
    ):
        try:
            response = (
                get_published_detail_page(
                    session=session,
                    detail_url=detail_url,
                    referer=referer,
                )
            )

            if response is None:
                raise RuntimeError(
                    "No response was returned "
                    "for the detail page."
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

            if (
                response.status_code
                == 200
            ):
                candidates = (
                    extract_registrant_candidates(
                        html_content=(
                            response.text
                        ),
                        source_url=(
                            response.url
                        ),
                    )
                )

                all_candidates.extend(
                    candidates
                )

            page_results.append(
                {
                    "page_number": (
                        page_number
                    ),
                    "requested_url": (
                        detail_url
                    ),
                    "final_url": (
                        response.url
                    ),
                    "status_code": (
                        response.status_code
                    ),
                    "content_type": (
                        content_type
                    ),
                    "response_size": len(
                        response.content
                    ),
                    "candidate_count": len(
                        candidates
                    ),
                    "candidates": (
                        candidates
                    ),
                    "error": (
                        None
                        if (
                            response.status_code
                            == 200
                        )
                        else (
                            "Detail page returned "
                            "HTTP "
                            f"{response.status_code}."
                        )
                    ),
                }
            )

        except Exception as error:
            page_results.append(
                {
                    "page_number": (
                        page_number
                    ),
                    "requested_url": (
                        detail_url
                    ),
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
        candidate_value = (
            normalise_text(
                candidate.get(
                    "value"
                )
            )
        )

        if not candidate_value:
            continue

        key = (
            candidate_value.lower()
        )

        if key in seen_candidates:
            continue

        seen_candidates.add(
            key
        )

        unique_candidates.append(
            candidate
        )

    successful_page_count = sum(
        1
        for item in page_results
        if (
            item.get(
                "status_code"
            )
            == 200
        )
    )

    failed_page_count = sum(
        1
        for item in page_results
        if (
            item.get(
                "status_code"
            )
            != 200
        )
    )

    return {
        "href_count": len(
            link_diagnostics[
                "all_hrefs"
            ]
        ),
        "href_preview": (
            link_diagnostics[
                "all_hrefs"
            ][:100]
        ),
        "script_count": len(
            link_diagnostics[
                "scripts"
            ]
        ),
        "script_preview": (
            link_diagnostics[
                "scripts"
            ][:50]
        ),
        "ignored_asset_href_count": (
            len(
                link_diagnostics[
                    "ignored_asset_hrefs"
                ]
            )
        ),
        "internal_link_count": len(
            internal_links
        ),
        "internal_link_preview": (
            internal_links[:100]
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
# GET PUBLISHED DOSSIER
# --------------------------------------------------
def get_published_dossier(
    session,
    asset_external_id,
    rml_id=None,
):
    asset_external_id = (
        normalise_text(
            asset_external_id
        )
    )

    if not asset_external_id:
        raise RuntimeError(
            "The assetExternalId "
            "is empty."
        )

    endpoint = (
        PUBLISHED_DOSSIER_ENDPOINT
        .format(
            asset_external_id=(
                asset_external_id
            )
        )
    )

    if rml_id:
        referer = (
            f"{ECHA_BASE_URL}/"
            f"{normalise_text(rml_id)}"
            f"/overview"
        )
    else:
        referer = ECHA_BASE_URL

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
        "href_count": 0,
        "href_preview": [],
        "script_count": 0,
        "script_preview": [],
        "ignored_asset_href_count": 0,
        "internal_link_count": 0,
        "internal_link_preview": [],
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
            response.status_code
            == 200
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
        "html_length": len(
            response_text
        ),
        "searchable_text_length": len(
            searchable_text
        ),
        "text_preview": (
            searchable_text[:5000]
        ),
        "detail_scan": (
            detail_scan
        ),
        "registrant_candidates": (
            detail_scan[
                "registrant_candidates"
            ]
        ),
        "error": (
            None
            if response.status_code == 200
            else (
                "Published dossier endpoint "
                "returned HTTP "
                f"{response.status_code}. "
                f"Response: "
                f"{response_text[:1000]}"
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
            f"CAS {cas_number} was "
            "not found in "
            "reach_registrations.xlsx."
        )

    selected = local_results[0]

    if not selected["rml_id"]:
        raise RuntimeError(
            "The ECHA rmlId could "
            "not be extracted from "
            f"this URL: "
            f"{selected['echa_url']}"
        )

    session = (
        create_http_session()
    )

    # -----------------------------
    # SUBSTANCE
    # -----------------------------
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

    # -----------------------------
    # DOSSIERS
    # -----------------------------
    dossier_attempts = []

    for status in (
        None,
        "Active",
        "Inactive",
    ):
        try:
            result = (
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
                    "url": (
                        result[
                            "url"
                        ]
                    ),
                    "params": (
                        result[
                            "params"
                        ]
                    ),
                    "item_count": (
                        len(items)
                    ),
                    "items": items,
                    "raw_body": (
                        result[
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
                    rml_id=(
                        selected[
                            "rml_id"
                        ]
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
                "detail_scan": {},
                "registrant_candidates": [],
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
    "This test uses the local ECHA registrations "
    "export to resolve a CAS number to an ECHA "
    "rmlId, then queries the substance, dossier-list "
    "and first active published dossier."
)

st.caption(
    f"Local ECHA file: {ECHA_DATA_FILE}"
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

            st.success(
                "The substance endpoint "
                "returned HTTP "
                f"{substance_api['status_code']}."
            )

            substance_body = (
                substance_api[
                    "body"
                ]
            )

            if isinstance(
                substance_body,
                dict,
            ):
                (
                    summary1,
                    summary2,
                ) = st.columns(2)

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

        for attempt in (
            test_result[
                "dossier_attempts"
            ]
        ):
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
                    attempt[
                        "params"
                    ]
                )

                if attempt["url"]:
                    st.markdown(
                        "**Final API URL**"
                    )

                    st.code(
                        attempt[
                            "url"
                        ],
                        language=None,
                    )

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
                        "items"
                    ]:
                        st.dataframe(
                            pd.json_normalize(
                                attempt[
                                    "items"
                                ]
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
                        attempt[
                            "error"
                        ]
                    )

        # ----------------------------------
        # 4. PUBLISHED DOSSIER
        # ----------------------------------
        st.subheader(
            "4. Published dossier and "
            "registrant scan"
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
            (
                detail1,
                detail2,
            ) = st.columns(2)

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

            if published_test.get(
                "url"
            ):
                st.markdown(
                    "**Published dossier URL**"
                )

                st.code(
                    published_test[
                        "url"
                    ],
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
                "### Published dossier "
                "detail scan"
            )

            (
                scan1,
                scan2,
                scan3,
                scan4,
                scan5,
            ) = st.columns(5)

            scan1.metric(
                "All href values",
                detail_scan.get(
                    "href_count",
                    0,
                ),
            )

            scan2.metric(
                "Internal detail links",
                detail_scan.get(
                    "internal_link_count",
                    0,
                ),
            )

            scan3.metric(
                "Detail pages tested",
                detail_scan.get(
                    "tested_page_count",
                    0,
                ),
            )

            scan4.metric(
                "Successful pages",
                detail_scan.get(
                    "successful_page_count",
                    0,
                ),
            )

            scan5.metric(
                "Registrant candidates",
                len(
                    registrant_candidates
                ),
            )

            # ----------------------------------
            # V6 INDEX DIAGNOSTICS
            # ----------------------------------
            with st.expander(
                "Index-link diagnostics",
                expanded=(
                    detail_scan.get(
                        "internal_link_count",
                        0,
                    )
                    == 0
                ),
            ):
                st.markdown(
                    "**All href values found "
                    "in index.html**"
                )

                st.json(
                    detail_scan.get(
                        "href_preview",
                        [],
                    )
                )

                st.markdown(
                    "**Script files found "
                    "in index.html**"
                )

                st.json(
                    detail_scan.get(
                        "script_preview",
                        [],
                    )
                )

                st.markdown(
                    "**Internal dossier links "
                    "selected for testing**"
                )

                st.json(
                    detail_scan.get(
                        "internal_link_preview",
                        [],
                    )
                )

            # ----------------------------------
            # REGISTRANT RESULTS
            # ----------------------------------
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
                        candidate[
                            "value"
                        ]
                        for candidate
                        in registrant_candidates
                        if candidate.get(
                            "value"
                        )
                    )
                )

                st.markdown(
                    "### Possible "
                    "registrant names"
                )

                for registrant_name in (
                    registrant_names
                ):
                    st.write(
                        f"- {registrant_name}"
                    )

            else:
                href_count = (
                    detail_scan.get(
                        "href_count",
                        0,
                    )
                )

                internal_link_count = (
                    detail_scan.get(
                        "internal_link_count",
                        0,
                    )
                )

                successful_pages = (
                    detail_scan.get(
                        "successful_page_count",
                        0,
                    )
                )

                if href_count == 0:
                    st.warning(
                        "The index page contains "
                        "no href values. The dossier "
                        "navigation may be generated "
                        "through JavaScript or another "
                        "manifest."
                    )

                elif internal_link_count == 0:
                    st.warning(
                        "The index page contains "
                        "href values, but none were "
                        "identified as dossier detail "
                        "links. Check the Index-link "
                        "diagnostics below."
                    )

                elif successful_pages == 0:
                    st.warning(
                        "Internal detail links were "
                        "found, but none returned "
                        "HTTP 200."
                    )

                else:
                    st.warning(
                        "The detail pages were "
                        "retrieved, but no public "
                        "registrant or legal-entity "
                        "name was found."
                    )

            # ----------------------------------
            # DETAIL-PAGE DIAGNOSTICS
            # ----------------------------------
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
                            "page": (
                                item.get(
                                    "page_number"
                                )
                            ),
                            "status": (
                                item.get(
                                    "status_code"
                                )
                            ),
                            "size": (
                                item.get(
                                    "response_size"
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

                with st.expander(
                    "Published detail-page "
                    "diagnostics",
                    expanded=False,
                ):
                    st.dataframe(
                        pd.DataFrame(
                            diagnostics
                        ),
                        width="stretch",
                        hide_index=True,
                    )

            # ----------------------------------
            # TEXT PREVIEW
            # ----------------------------------
            with st.expander(
                "Published dossier "
                "text preview",
                expanded=False,
            ):
                st.text(
                    published_test.get(
                        "text_preview"
                    )
                    or
                    "No searchable text "
                    "was returned."
                )