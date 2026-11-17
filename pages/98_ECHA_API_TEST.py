import json

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------
st.set_page_config(
    page_title="ECHA Registrants API Test",
    page_icon="🔎",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_REGISTRANTS_API_TEST_V7"


# --------------------------------------------------
# TEST SUBSTANCE
# --------------------------------------------------
CAS_NUMBER = "128-37-0"
EC_NUMBER = "204-881-4"
RML_ID = "100.004.439"

ECHA_BASE_URL = "https://chem.echa.europa.eu"

REGISTRANTS_ENDPOINT = (
    ECHA_BASE_URL
    + "/api-dossier-list/v1/asset-owner"
)


# --------------------------------------------------
# REQUEST PARAMETERS
# --------------------------------------------------
REGISTRANTS_PARAMS = {
    "rmlId": RML_ID,
    "pageIndex": 1,
    "pageSize": 100,
}


# --------------------------------------------------
# REQUEST CONFIGURATION
# --------------------------------------------------
CONNECT_TIMEOUT_SECONDS = 30
READ_TIMEOUT_SECONDS = 90

REQUEST_HEADERS = {
    "Accept": (
        "application/json,"
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
    "Referer": (
        f"{ECHA_BASE_URL}/"
        f"{RML_ID}/"
        "dossier-list/reach/asset-owner"
    ),
}


# --------------------------------------------------
# GENERAL HELPERS
# --------------------------------------------------
def normalise_text(
    value,
):
    if value is None:
        return ""

    if isinstance(
        value,
        (
            dict,
            list,
            tuple,
            set,
        ),
    ):
        return json.dumps(
            value,
            ensure_ascii=False,
        )

    value = str(
        value
    ).strip()

    if value.lower() in {
        "",
        "none",
        "null",
        "nan",
    }:
        return ""

    return " ".join(
        value
        .replace(
            "\xa0",
            " ",
        )
        .split()
    )


# --------------------------------------------------
# HTTP SESSION
# --------------------------------------------------
def create_session():
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
# FIND LISTS IN JSON
# --------------------------------------------------
def find_json_lists(
    value,
    path="root",
    results=None,
):
    if results is None:
        results = []

    if isinstance(
        value,
        list,
    ):
        results.append(
            {
                "path": path,
                "length": len(
                    value
                ),
                "value": value,
            }
        )

        for index, item in enumerate(
            value
        ):
            find_json_lists(
                value=item,
                path=(
                    f"{path}"
                    f"[{index}]"
                ),
                results=results,
            )

    elif isinstance(
        value,
        dict,
    ):
        for key, nested_value in (
            value.items()
        ):
            find_json_lists(
                value=nested_value,
                path=(
                    f"{path}.{key}"
                ),
                results=results,
            )

    return results


# --------------------------------------------------
# SCORE POSSIBLE RESULT LIST
# --------------------------------------------------
def score_result_list(
    candidate,
):
    value = candidate.get(
        "value"
    )

    if not isinstance(
        value,
        list,
    ):
        return -1

    if not value:
        return 0

    dictionary_items = [
        item
        for item in value
        if isinstance(
            item,
            dict,
        )
    ]

    if not dictionary_items:
        return 0

    score = len(
        dictionary_items
    )

    relevant_keys = {
        "name",
        "registrantname",
        "assetownername",
        "address",
        "status",
        "registrationstatus",
        "id",
        "assetownerid",
        "legalentityname",
        "organisationname",
        "organizationname",
    }

    for item in dictionary_items[
        :10
    ]:
        item_keys = {
            str(key).lower()
            for key in item.keys()
        }

        score += (
            len(
                item_keys
                & relevant_keys
            )
            * 10
        )

    path = str(
        candidate.get(
            "path",
            "",
        )
    ).lower()

    if any(
        term in path
        for term in (
            "item",
            "content",
            "result",
            "data",
            "registrant",
            "owner",
        )
    ):
        score += 25

    return score


# --------------------------------------------------
# SELECT MOST LIKELY RESULT LIST
# --------------------------------------------------
def select_result_list(
    api_body,
):
    if isinstance(
        api_body,
        list,
    ):
        return {
            "path": "root",
            "items": api_body,
        }

    if not isinstance(
        api_body,
        dict,
    ):
        return {
            "path": "",
            "items": [],
        }

    direct_keys = [
        "items",
        "content",
        "results",
        "data",
        "assetOwners",
        "assetOwner",
        "registrants",
    ]

    for key in direct_keys:
        value = api_body.get(
            key
        )

        if isinstance(
            value,
            list,
        ):
            return {
                "path": (
                    f"root.{key}"
                ),
                "items": value,
            }

        if isinstance(
            value,
            dict,
        ):
            for nested_key in (
                direct_keys
            ):
                nested_value = (
                    value.get(
                        nested_key
                    )
                )

                if isinstance(
                    nested_value,
                    list,
                ):
                    return {
                        "path": (
                            f"root.{key}."
                            f"{nested_key}"
                        ),
                        "items": (
                            nested_value
                        ),
                    }

    candidates = (
        find_json_lists(
            api_body
        )
    )

    if not candidates:
        return {
            "path": "",
            "items": [],
        }

    scored_candidates = [
        (
            score_result_list(
                candidate
            ),
            candidate,
        )
        for candidate in candidates
    ]

    scored_candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    best_score, best_candidate = (
        scored_candidates[0]
    )

    if best_score <= 0:
        return {
            "path": "",
            "items": [],
        }

    return {
        "path": (
            best_candidate[
                "path"
            ]
        ),
        "items": (
            best_candidate[
                "value"
            ]
        ),
    }


# --------------------------------------------------
# RECURSIVE FIELD LOOKUP
# --------------------------------------------------
def find_value_by_keys(
    value,
    accepted_keys,
):
    accepted_keys = {
        str(key).lower()
        for key in accepted_keys
    }

    if isinstance(
        value,
        dict,
    ):
        for key, nested_value in (
            value.items()
        ):
            if (
                str(key).lower()
                in accepted_keys
            ):
                if isinstance(
                    nested_value,
                    (
                        str,
                        int,
                        float,
                        bool,
                    ),
                ):
                    return nested_value

        for nested_value in (
            value.values()
        ):
            found_value = (
                find_value_by_keys(
                    nested_value,
                    accepted_keys,
                )
            )

            if found_value not in (
                None,
                "",
            ):
                return found_value

    elif isinstance(
        value,
        list,
    ):
        for item in value:
            found_value = (
                find_value_by_keys(
                    item,
                    accepted_keys,
                )
            )

            if found_value not in (
                None,
                "",
            ):
                return found_value

    return None


# --------------------------------------------------
# NORMALISE ONE REGISTRANT
# --------------------------------------------------
def normalise_registrant(
    item,
):
    if not isinstance(
        item,
        dict,
    ):
        return {
            "Name": normalise_text(
                item
            ),
            "Address": "",
            "Status": "",
            "ID": "",
        }

    name = find_value_by_keys(
        item,
        {
            "name",
            "registrantName",
            "assetOwnerName",
            "legalEntityName",
            "organisationName",
            "organizationName",
            "companyName",
        },
    )

    address = find_value_by_keys(
        item,
        {
            "address",
            "registrantAddress",
            "assetOwnerAddress",
            "fullAddress",
            "formattedAddress",
        },
    )

    status = find_value_by_keys(
        item,
        {
            "status",
            "registrationStatus",
            "assetOwnerStatus",
        },
    )

    identifier = find_value_by_keys(
        item,
        {
            "id",
            "assetOwnerId",
            "legalEntityId",
            "uuid",
            "externalId",
        },
    )

    return {
        "Name": normalise_text(
            name
        ),
        "Address": normalise_text(
            address
        ),
        "Status": normalise_text(
            status
        ),
        "ID": normalise_text(
            identifier
        ),
    }


# --------------------------------------------------
# KNOWN-NAME CHECK
# --------------------------------------------------
def find_known_name_matches(
    value,
):
    try:
        searchable_text = json.dumps(
            value,
            ensure_ascii=False,
        ).lower()

    except Exception:
        searchable_text = str(
            value
        ).lower()

    benchmarks = [
        "3m belgium",
        "afton chemical",
        "basf se",
    ]

    return [
        benchmark
        for benchmark in benchmarks
        if benchmark in searchable_text
    ]


# --------------------------------------------------
# PARSE TOTAL NUMBER
# --------------------------------------------------
def find_total_count(
    value,
):
    total_keys = {
        "total",
        "totalcount",
        "totalitems",
        "totalelements",
        "totalresults",
        "numberofelements",
    }

    if isinstance(
        value,
        dict,
    ):
        for key, nested_value in (
            value.items()
        ):
            if (
                str(key).lower()
                in total_keys
                and isinstance(
                    nested_value,
                    (
                        int,
                        float,
                    ),
                )
            ):
                return int(
                    nested_value
                )

        for nested_value in (
            value.values()
        ):
            result = (
                find_total_count(
                    nested_value
                )
            )

            if result is not None:
                return result

    elif isinstance(
        value,
        list,
    ):
        for item in value:
            result = (
                find_total_count(
                    item
                )
            )

            if result is not None:
                return result

    return None


# --------------------------------------------------
# EXECUTE REGISTRANTS REQUEST
# --------------------------------------------------
def get_registrants():
    session = (
        create_session()
    )

    print(
        "=" * 80,
        flush=True,
    )

    print(
        f"ECHA test version: "
        f"{CODE_VERSION}",
        flush=True,
    )

    print(
        "ECHA REGISTRANTS REQUEST",
        flush=True,
    )

    print(
        f"METHOD: GET",
        flush=True,
    )

    print(
        f"ENDPOINT: "
        f"{REGISTRANTS_ENDPOINT}",
        flush=True,
    )

    print(
        f"PARAMETERS: "
        f"{REGISTRANTS_PARAMS}",
        flush=True,
    )

    try:
        response = session.get(
            REGISTRANTS_ENDPOINT,
            params=(
                REGISTRANTS_PARAMS
            ),
            timeout=(
                CONNECT_TIMEOUT_SECONDS,
                READ_TIMEOUT_SECONDS,
            ),
            allow_redirects=True,
        )

    except requests.Timeout as error:
        return {
            "success": False,
            "requested_endpoint": (
                REGISTRANTS_ENDPOINT
            ),
            "final_url": "",
            "parameters": (
                REGISTRANTS_PARAMS
            ),
            "status_code": None,
            "content_type": "",
            "response_length": 0,
            "raw_text": "",
            "json_body": None,
            "result_path": "",
            "items": [],
            "registrants": [],
            "total_count": None,
            "known_matches": [],
            "error": (
                "The ECHA registrants "
                "request timed out: "
                f"{error}"
            ),
        }

    except requests.RequestException as error:
        return {
            "success": False,
            "requested_endpoint": (
                REGISTRANTS_ENDPOINT
            ),
            "final_url": "",
            "parameters": (
                REGISTRANTS_PARAMS
            ),
            "status_code": None,
            "content_type": "",
            "response_length": 0,
            "raw_text": "",
            "json_body": None,
            "result_path": "",
            "items": [],
            "registrants": [],
            "total_count": None,
            "known_matches": [],
            "error": (
                "The ECHA registrants "
                "request failed: "
                f"{error}"
            ),
        }

    content_type = (
        response.headers.get(
            "content-type",
            "",
        )
    )

    raw_text = (
        response.text
        or ""
    )

    print(
        f"FINAL URL: "
        f"{response.url}",
        flush=True,
    )

    print(
        f"HTTP STATUS: "
        f"{response.status_code}",
        flush=True,
    )

    print(
        f"CONTENT TYPE: "
        f"{content_type}",
        flush=True,
    )

    print(
        f"RESPONSE BYTES: "
        f"{len(response.content)}",
        flush=True,
    )

    print(
        "RAW RESPONSE PREVIEW:",
        flush=True,
    )

    print(
        raw_text[:5000],
        flush=True,
    )

    try:
        json_body = (
            response.json()
        )

    except ValueError:
        json_body = None

    error = None

    if response.status_code == 403:
        error = (
            "ECHA returned HTTP 403. "
            "The endpoint exists or was reached, "
            "but access was refused."
        )

    elif response.status_code == 404:
        error = (
            "ECHA returned HTTP 404. "
            "The tested asset-owner endpoint "
            "was not found at this API path."
        )

    elif response.status_code == 429:
        error = (
            "ECHA returned HTTP 429. "
            "Too many requests were made. "
            "Wait before trying again."
        )

    elif response.status_code >= 500:
        error = (
            "ECHA returned a server error: "
            f"HTTP {response.status_code}."
        )

    elif response.status_code >= 400:
        error = (
            "ECHA returned HTTP "
            f"{response.status_code}."
        )

    elif json_body is None:
        error = (
            "The endpoint returned HTTP "
            f"{response.status_code}, but the "
            "response was not valid JSON."
        )

    result_selection = {
        "path": "",
        "items": [],
    }

    registrants = []
    total_count = None
    known_matches = []

    if json_body is not None:
        result_selection = (
            select_result_list(
                json_body
            )
        )

        registrants = [
            normalise_registrant(
                item
            )
            for item in (
                result_selection[
                    "items"
                ]
            )
        ]

        total_count = (
            find_total_count(
                json_body
            )
        )

        known_matches = (
            find_known_name_matches(
                json_body
            )
        )

    return {
        "success": (
            response.status_code
            == 200
            and
            json_body is not None
        ),
        "requested_endpoint": (
            REGISTRANTS_ENDPOINT
        ),
        "final_url": (
            response.url
        ),
        "parameters": (
            REGISTRANTS_PARAMS
        ),
        "status_code": (
            response.status_code
        ),
        "content_type": (
            content_type
        ),
        "response_length": (
            len(
                response.content
            )
        ),
        "raw_text": (
            raw_text
        ),
        "json_body": (
            json_body
        ),
        "result_path": (
            result_selection[
                "path"
            ]
        ),
        "items": (
            result_selection[
                "items"
            ]
        ),
        "registrants": (
            registrants
        ),
        "total_count": (
            total_count
        ),
        "known_matches": (
            known_matches
        ),
        "error": (
            error
        ),
    }


# --------------------------------------------------
# STREAMLIT INTERFACE
# --------------------------------------------------
st.title(
    "ECHA Registrants API Test"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.write(
    "This test calls the asset-owner endpoint "
    "behind the ECHA CHEM Registrants view."
)

st.info(
    "The request is based on route names and "
    "configuration found in the public ECHA CHEM "
    "frontend. This test uses no browser automation "
    "and does not attempt to bypass access controls."
)


# --------------------------------------------------
# TEST SUBSTANCE
# --------------------------------------------------
st.subheader(
    "Known test substance"
)

column1, column2, column3 = (
    st.columns(3)
)

column1.metric(
    "CAS",
    CAS_NUMBER,
)

column2.metric(
    "EC",
    EC_NUMBER,
)

column3.metric(
    "rmlId",
    RML_ID,
)

st.write(
    "Expected benchmark from the ECHA CHEM "
    "interface: **42 registrants**."
)


# --------------------------------------------------
# REQUEST DETAILS
# --------------------------------------------------
st.subheader(
    "Request to test"
)

st.write(
    "**HTTP method:** GET"
)

st.write(
    "**Endpoint:**"
)

st.code(
    REGISTRANTS_ENDPOINT,
    language=None,
)

st.write(
    "**Parameters:**"
)

st.json(
    REGISTRANTS_PARAMS
)


# --------------------------------------------------
# RUN TEST
# --------------------------------------------------
if st.button(
    "Retrieve ECHA registrants",
    type="primary",
):
    with st.spinner(
        "Requesting the ECHA registrants list..."
    ):
        result = (
            get_registrants()
        )

    st.subheader(
        "1. HTTP result"
    )

    status_column, bytes_column, json_column = (
        st.columns(3)
    )

    status_column.metric(
        "HTTP status",
        (
            result[
                "status_code"
            ]
            if (
                result[
                    "status_code"
                ]
                is not None
            )
            else
            "Request error"
        ),
    )

    bytes_column.metric(
        "Response bytes",
        result[
            "response_length"
        ],
    )

    json_column.metric(
        "Valid JSON",
        (
            "Yes"
            if (
                result[
                    "json_body"
                ]
                is not None
            )
            else
            "No"
        ),
    )

    st.write(
        "**Final URL:**"
    )

    st.code(
        result[
            "final_url"
        ],
        language=None,
    )

    st.write(
        "**Content-Type:** "
        f"{result['content_type']}"
    )

    if result[
        "error"
    ]:
        st.error(
            result[
                "error"
            ]
        )

    elif result[
        "success"
    ]:
        st.success(
            "The registrants endpoint "
            "returned HTTP 200 and valid JSON."
        )

    # ----------------------------------
    # REGISTRANT SUMMARY
    # ----------------------------------
    st.subheader(
        "2. Registrant summary"
    )

    registrants = (
        result[
            "registrants"
        ]
    )

    summary1, summary2, summary3 = (
        st.columns(3)
    )

    summary1.metric(
        "Items extracted",
        len(
            registrants
        ),
    )

    summary2.metric(
        "Total reported by API",
        (
            result[
                "total_count"
            ]
            if (
                result[
                    "total_count"
                ]
                is not None
            )
            else
            "Not found"
        ),
    )

    summary3.metric(
        "Known-name matches",
        len(
            result[
                "known_matches"
            ]
        ),
    )

    st.write(
        "**Selected JSON list path:**"
    )

    st.code(
        (
            result[
                "result_path"
            ]
            or
            "No result list selected"
        ),
        language=None,
    )

    if result[
        "known_matches"
    ]:
        st.success(
            "Known benchmark names were found: "
            + ", ".join(
                result[
                    "known_matches"
                ]
            )
        )

    # ----------------------------------
    # REGISTRANT TABLE
    # ----------------------------------
    st.subheader(
        "3. Registrants"
    )

    if registrants:
        registrant_dataframe = (
            pd.DataFrame(
                registrants
            )
        )

        non_empty_columns = [
            column
            for column in (
                registrant_dataframe
                .columns
            )
            if (
                registrant_dataframe[
                    column
                ]
                .astype(str)
                .str.strip()
                .ne("")
                .any()
            )
        ]

        if non_empty_columns:
            registrant_dataframe = (
                registrant_dataframe[
                    non_empty_columns
                ]
            )

        st.dataframe(
            registrant_dataframe,
            use_container_width=True,
            hide_index=True,
        )

    else:
        st.warning(
            "No registrant rows were extracted "
            "from the response."
        )

    # ----------------------------------
    # RAW ITEMS
    # ----------------------------------
    with st.expander(
        "4. Raw selected items",
        expanded=False,
    ):
        st.json(
            result[
                "items"
            ]
        )

    # ----------------------------------
    # COMPLETE JSON
    # ----------------------------------
    with st.expander(
        "5. Complete parsed JSON",
        expanded=False,
    ):
        if (
            result[
                "json_body"
            ]
            is not None
        ):
            st.json(
                result[
                    "json_body"
                ]
            )

        else:
            st.warning(
                "The response was not valid JSON."
            )

    # ----------------------------------
    # RAW RESPONSE
    # ----------------------------------
    with st.expander(
        "6. Raw response preview",
        expanded=False,
    ):
        st.code(
            result[
                "raw_text"
            ][:10000],
            language=None,
        )