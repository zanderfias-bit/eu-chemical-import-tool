from io import StringIO

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ECICS_BASE_URL = (
    "https://ec.europa.eu/"
    "taxation_customs/dds2/ecics/"
)

ECICS_SEARCH_URL = (
    ECICS_BASE_URL
    + "chemicalsubstance_consultation.jsp"
)

CONNECT_TIMEOUT = 20
READ_TIMEOUT = 60


def clean_text(value):
    """
    Convert a value to a clean string.
    """
    if value is None:
        return ""

    text = str(value).strip()

    if text.lower() in {
        "",
        "none",
        "nan",
        "null",
    }:
        return ""

    return " ".join(
        text.split()
    )


def normalise_column_name(value):
    """
    Normalise column names so ECICS table headers
    can be recognised even if their formatting changes
    slightly.
    """
    text = clean_text(value).lower()

    replacements = {
        "\n": " ",
        "\r": " ",
        "-": " ",
        "_": " ",
        ".": " ",
        ":": " ",
        "/": " ",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new,
        )

    return " ".join(
        text.split()
    )


def create_session():
    """
    Create a requests session with conservative retry logic.
    """
    session = requests.Session()

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.0,
        status_forcelist=(
            429,
            500,
            502,
            503,
            504,
        ),
        allowed_methods=frozenset(
            {
                "GET",
            }
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

    session.headers.update(
        {
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "*/*;q=0.8"
            ),
            "Accept-Language": (
                "en-US,en;q=0.9"
            ),
            "User-Agent": (
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/131.0.0.0 "
                "Safari/537.36"
            ),
        }
    )

    return session


def find_column(
    dataframe,
    possible_names,
):
    """
    Find a dataframe column by matching
    common ECICS header variants.
    """
    normalised_possible_names = [
        normalise_column_name(
            name
        )
        for name in possible_names
    ]

    for column in dataframe.columns:
        column_name = normalise_column_name(
            column
        )

        for possible_name in (
            normalised_possible_names
        ):
            if (
                column_name
                == possible_name
            ):
                return column

    for column in dataframe.columns:
        column_name = normalise_column_name(
            column
        )

        for possible_name in (
            normalised_possible_names
        ):
            if (
                possible_name
                and possible_name
                in column_name
            ):
                return column

    return None


def identify_ecics_columns(
    dataframe,
):
    """
    Identify relevant ECICS result columns.
    """
    cus_column = find_column(
        dataframe,
        [
            "CUS",
            "CUS Number",
            "CUS No",
        ],
    )

    cn_column = find_column(
        dataframe,
        [
            "CN Code",
            "CN",
            "Goods Code",
            "Commodity Code",
        ],
    )

    cas_column = find_column(
        dataframe,
        [
            "CAS RN",
            "CAS",
            "CAS Number",
        ],
    )

    ec_column = find_column(
        dataframe,
        [
            "EC Number",
            "EC No",
            "EC",
        ],
    )

    name_column = find_column(
        dataframe,
        [
            "Name",
            "Chemical Name",
            "Substance Name",
        ],
    )

    return {
        "cus": cus_column,
        "cn": cn_column,
        "cas": cas_column,
        "ec": ec_column,
        "name": name_column,
    }


def parse_ecics_tables(
    html,
    requested_ec_number,
):
    """
    Parse the HTML tables returned by ECICS and
    locate the chemical result table.
    """
    try:
        tables = pd.read_html(
            StringIO(
                html
            )
        )

    except ValueError:
        return {
            "success": False,
            "message": (
                "ECICS responded successfully, "
                "but no HTML result tables "
                "were found."
            ),
            "tables_found": 0,
        }

    except Exception as error:
        return {
            "success": False,
            "message": (
                "The ECICS response could not "
                "be parsed: "
                f"{error}"
            ),
            "tables_found": 0,
        }

    requested_ec_number = clean_text(
        requested_ec_number
    )

    candidate_rows = []

    for table_index, dataframe in enumerate(
        tables
    ):
        if dataframe.empty:
            continue

        # Flatten MultiIndex headers if ECICS uses them.
        if isinstance(
            dataframe.columns,
            pd.MultiIndex,
        ):
            dataframe.columns = [
                " ".join(
                    clean_text(part)
                    for part in column
                    if clean_text(part)
                )
                for column in dataframe.columns
            ]

        columns = identify_ecics_columns(
            dataframe
        )

        # A useful ECICS result should at least contain
        # a CN/goods code and one substance identifier.
        has_goods_code = (
            columns[
                "cn"
            ]
            is not None
        )

        has_identifier = any(
            columns[
                key
            ]
            is not None
            for key in (
                "cus",
                "cas",
                "ec",
                "name",
            )
        )

        if not (
            has_goods_code
            and has_identifier
        ):
            continue

        for row_index, row in (
            dataframe.iterrows()
        ):
            ec_result = (
                clean_text(
                    row.get(
                        columns["ec"]
                    )
                )
                if columns[
                    "ec"
                ]
                is not None
                else ""
            )

            goods_code = clean_text(
                row.get(
                    columns[
                        "cn"
                    ]
                )
            )

            cus_number = (
                clean_text(
                    row.get(
                        columns["cus"]
                    )
                )
                if columns[
                    "cus"
                ]
                is not None
                else ""
            )

            cas_number = (
                clean_text(
                    row.get(
                        columns["cas"]
                    )
                )
                if columns[
                    "cas"
                ]
                is not None
                else ""
            )

            substance_name = (
                clean_text(
                    row.get(
                        columns["name"]
                    )
                )
                if columns[
                    "name"
                ]
                is not None
                else ""
            )

            if not goods_code:
                continue

            candidate = {
                "table_index": (
                    table_index
                ),
                "row_index": int(
                    row_index
                ),
                "ec_number": ec_result,
                "goods_code": goods_code,
                "cus_number": cus_number,
                "cas_number": cas_number,
                "substance_name": (
                    substance_name
                ),
            }

            candidate_rows.append(
                candidate
            )

    if not candidate_rows:
        return {
            "success": False,
            "message": (
                "ECICS result table not found "
                "or no usable chemical record "
                "was returned."
            ),
            "tables_found": len(
                tables
            ),
        }

    # Prefer an exact EC-number match.
    exact_matches = [
        candidate
        for candidate in candidate_rows
        if clean_text(
            candidate[
                "ec_number"
            ]
        )
        == requested_ec_number
    ]

    if exact_matches:
        selected = exact_matches[0]

    else:
        selected = candidate_rows[0]

    return {
        "success": True,
        "ec_number": selected[
            "ec_number"
        ],
        "goods_code": selected[
            "goods_code"
        ],
        "cus_number": selected[
            "cus_number"
        ],
        "cas_number": selected[
            "cas_number"
        ],
        "substance_name": selected[
            "substance_name"
        ],
        "tables_found": len(
            tables
        ),
        "table_index": selected[
            "table_index"
        ],
    }


def get_goods_code(
    ec_number,
):
    """
    Search ECICS using an EC number and return the
    corresponding CN/goods code and chemical identifiers.

    This implementation uses a normal HTTP request
    instead of Playwright/Chromium.
    """
    ec_number = clean_text(
        ec_number
    )

    if not ec_number:
        return {
            "success": False,
            "message": (
                "No EC number was provided "
                "for the ECICS lookup."
            ),
        }

    params = {
        "Lang": "en",
        "Cas": "",
        "Cus": "",
        "CnCode": "",
        "EcCode": ec_number,
        "UnCode": "",
        "Name": "",
        "LangNm": "en",
        "NomenclatureSystem": "",
        "Inchi": "",
        "Inchikey": "",
        "Characteristic": "",
        "sortOrder": "1",
        "Expand": "true",
        "offset": "0",
        "viewVal": "",
        "isVisitedRef": "true",
    }

    session = create_session()

    try:
        response = session.get(
            ECICS_SEARCH_URL,
            params=params,
            timeout=(
                CONNECT_TIMEOUT,
                READ_TIMEOUT,
            ),
            allow_redirects=True,
        )

    except requests.Timeout as error:
        return {
            "success": False,
            "message": (
                "ECICS request timed out: "
                f"{error}"
            ),
            "url": ECICS_SEARCH_URL,
        }

    except requests.ConnectionError as error:
        return {
            "success": False,
            "message": (
                "Could not connect to ECICS: "
                f"{error}"
            ),
            "url": ECICS_SEARCH_URL,
        }

    except requests.RequestException as error:
        return {
            "success": False,
            "message": (
                "ECICS request failed: "
                f"{error}"
            ),
            "url": ECICS_SEARCH_URL,
        }

    if response.status_code != 200:
        return {
            "success": False,
            "message": (
                "ECICS returned HTTP "
                f"{response.status_code}."
            ),
            "http_status": (
                response.status_code
            ),
            "url": response.url,
        }

    if not response.text.strip():
        return {
            "success": False,
            "message": (
                "ECICS returned an empty response."
            ),
            "http_status": (
                response.status_code
            ),
            "url": response.url,
        }

    parsed_result = parse_ecics_tables(
        response.text,
        ec_number,
    )

    parsed_result[
        "http_status"
    ] = response.status_code

    parsed_result[
        "url"
    ] = response.url

    return parsed_result