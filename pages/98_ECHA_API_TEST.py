import json

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="ECHA Registrants API Test",
    page_icon="🧪",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_REGISTRANTS_API_TEST_V16"


# --------------------------------------------------
# KNOWN TEST SUBSTANCE
# --------------------------------------------------
CAS_NUMBER = "128-37-0"
EC_NUMBER = "204-881-4"
RML_ID = "100.004.439"

EXPECTED_REGISTRANTS = 42


# --------------------------------------------------
# ECHA API
# --------------------------------------------------
ECHA_BASE_URL = (
    "https://chem.echa.europa.eu"
)

REGISTRANTS_API_BASE = (
    "/api-registrants/v1/"
)

REGISTRANTS_ENDPOINT_SUFFIX = (
    "registrants"
)

REGISTRANTS_API_URL = (
    ECHA_BASE_URL
    + REGISTRANTS_API_BASE
    + REGISTRANTS_ENDPOINT_SUFFIX
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

HEADERS = {
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
}


# --------------------------------------------------
# CREATE SESSION
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

    return session


# --------------------------------------------------
# NORMALISE TEXT
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
        ),
    ):

        return json.dumps(
            value,
            ensure_ascii=False,
        )

    text = str(
        value
    ).strip()

    if text.lower() in {
        "",
        "none",
        "null",
        "nan",
    }:
        return ""

    return " ".join(
        text.split()
    )


# --------------------------------------------------
# RECURSIVE JSON FIELD SEARCH
# --------------------------------------------------
def find_field(
    value,
    possible_keys,
):

    wanted_keys = {
        key.lower()
        for key
        in possible_keys
    }

    if isinstance(
        value,
        dict,
    ):

        # First check current level.
        for key, nested_value in (
            value.items()
        ):

            if (
                str(key).lower()
                in wanted_keys
            ):

                if not isinstance(
                    nested_value,
                    (
                        dict,
                        list,
                    ),
                ):

                    return nested_value

        # Then recurse.
        for nested_value in (
            value.values()
        ):

            result = find_field(
                nested_value,
                possible_keys,
            )

            if result not in (
                None,
                "",
            ):
                return result

    elif isinstance(
        value,
        list,
    ):

        for item in value:

            result = find_field(
                item,
                possible_keys,
            )

            if result not in (
                None,
                "",
            ):
                return result

    return None


# --------------------------------------------------
# FIND TOTAL COUNT
# --------------------------------------------------
def find_total_count(
    value,
):

    possible_keys = {
        "total",
        "totalcount",
        "totalitems",
        "totalelements",
        "totalresults",
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
                in possible_keys
                and
                isinstance(
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

            result = find_total_count(
                nested_value
            )

            if result is not None:
                return result

    elif isinstance(
        value,
        list,
    ):

        for item in value:

            result = find_total_count(
                item
            )

            if result is not None:
                return result

    return None


# --------------------------------------------------
# FIND JSON LISTS
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
                "path": (
                    path
                ),
                "items": (
                    value
                ),
            }
        )

        for index, item in enumerate(
            value
        ):

            find_json_lists(
                value=item,
                path=(
                    f"{path}[{index}]"
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
def score_list(
    candidate,
):

    items = candidate.get(
        "items",
        [],
    )

    if not items:
        return 0

    score = len(
        items
    )

    relevant_keys = {
        "name",
        "address",
        "status",
        "registrantname",
        "registrationstatus",
        "assetownername",
        "legalentityname",
    }

    for item in items[:10]:

        if not isinstance(
            item,
            dict,
        ):
            continue

        keys = {
            str(key).lower()
            for key
            in item.keys()
        }

        score += (
            len(
                keys
                & relevant_keys
            )
            * 20
        )

    path = candidate.get(
        "path",
        "",
    ).lower()

    if any(
        word in path
        for word in (
            "registrant",
            "items",
            "results",
            "content",
            "data",
        )
    ):
        score += 50

    return score


# --------------------------------------------------
# SELECT RESULT LIST
# --------------------------------------------------
def select_result_list(
    json_body,
):

    if isinstance(
        json_body,
        list,
    ):

        return (
            "root",
            json_body,
        )

    if isinstance(
        json_body,
        dict,
    ):

        preferred_keys = (
            "items",
            "results",
            "content",
            "registrants",
            "data",
        )

        for key in preferred_keys:

            value = json_body.get(
                key
            )

            if isinstance(
                value,
                list,
            ):

                return (
                    f"root.{key}",
                    value,
                )

    candidates = find_json_lists(
        json_body
    )

    if not candidates:

        return (
            "",
            [],
        )

    best_candidate = max(
        candidates,
        key=score_list,
    )

    if (
        score_list(
            best_candidate
        )
        <= 0
    ):

        return (
            "",
            [],
        )

    return (
        best_candidate[
            "path"
        ],
        best_candidate[
            "items"
        ],
    )


# --------------------------------------------------
# NORMALISE REGISTRANT
# --------------------------------------------------
def normalise_registrant(
    item,
):

    if not isinstance(
        item,
        dict,
    ):

        return {
            "Name": (
                normalise_text(
                    item
                )
            ),
            "Address": "",
            "Status": "",
            "ID": "",
        }

    name = find_field(
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

    address = find_field(
        item,
        {
            "address",
            "registrantAddress",
            "assetOwnerAddress",
            "fullAddress",
            "formattedAddress",
        },
    )

    status = find_field(
        item,
        {
            "status",
            "registrationStatus",
            "registrantStatus",
            "assetOwnerStatus",
        },
    )

    identifier = find_field(
        item,
        {
            "id",
            "uuid",
            "externalId",
            "assetOwnerId",
            "legalEntityId",
        },
    )

    return {
        "Name": (
            normalise_text(
                name
            )
        ),
        "Address": (
            normalise_text(
                address
            )
        ),
        "Status": (
            normalise_text(
                status
            )
        ),
        "ID": (
            normalise_text(
                identifier
            )
        ),
    }


# --------------------------------------------------
# RUN API TEST
# --------------------------------------------------
def run_api_test():

    session = (
        create_session()
    )

    params = {
        "pageIndex": 1,
        "pageSize": 100,
        "rmlId": RML_ID,
    }

    request_headers = {
        "Referer": (
            OVERVIEW_URL
        ),
    }

    try:

        response = session.get(
            REGISTRANTS_API_URL,
            params=params,
            headers=request_headers,
            timeout=(
                CONNECT_TIMEOUT_SECONDS,
                READ_TIMEOUT_SECONDS,
            ),
            allow_redirects=True,
        )

    except requests.Timeout as error:

        return {
            "error": (
                f"Request timed out: "
                f"{error}"
            ),
            "response": None,
            "json": None,
            "registrants": [],
            "selected_path": "",
            "total_count": None,
            "params": params,
        }

    except requests.RequestException as error:

        return {
            "error": (
                f"Request failed: "
                f"{error}"
            ),
            "response": None,
            "json": None,
            "registrants": [],
            "selected_path": "",
            "total_count": None,
            "params": params,
        }

    # ----------------------------------
    # JSON
    # ----------------------------------
    try:
        json_body = (
            response.json()
        )

    except ValueError:
        json_body = None

    selected_path = ""
    items = []
    registrants = []
    total_count = None

    # ----------------------------------
    # PROCESS JSON
    # ----------------------------------
    if json_body is not None:

        (
            selected_path,
            items,
        ) = select_result_list(
            json_body
        )

        registrants = [
            normalise_registrant(
                item
            )
            for item
            in items
        ]

        total_count = (
            find_total_count(
                json_body
            )
        )

    return {
        "error": None,
        "response": response,
        "json": json_body,
        "registrants": registrants,
        "selected_path": selected_path,
        "total_count": total_count,
        "params": params,
    }


# --------------------------------------------------
# STREAMLIT UI
# --------------------------------------------------
st.title(
    "ECHA Registrants API Test"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.success(
    "ECHA frontend discovery is complete. "
    "The dossierList JavaScript defines "
    "registrantsApiUrl as /api-registrants/v1/ "
    'and appends "registrants".'
)


# --------------------------------------------------
# KNOWN TEST SUBSTANCE
# --------------------------------------------------
st.subheader(
    "Known test substance"
)

columns = (
    st.columns(4)
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

columns[3].metric(
    "Expected registrants",
    EXPECTED_REGISTRANTS,
)


# --------------------------------------------------
# EXTRACTED ECHA IMPLEMENTATION
# --------------------------------------------------
st.subheader(
    "Extracted ECHA implementation"
)

config_rows = [
    {
        "Component": (
            "registrantsApiUrl"
        ),
        "Value": (
            REGISTRANTS_API_BASE
        ),
    },
    {
        "Component": (
            "Suffix"
        ),
        "Value": (
            REGISTRANTS_ENDPOINT_SUFFIX
        ),
    },
    {
        "Component": (
            "Final endpoint"
        ),
        "Value": (
            REGISTRANTS_API_URL
        ),
    },
]

st.dataframe(
    pd.DataFrame(
        config_rows
    ),
    use_container_width=True,
    hide_index=True,
)


# --------------------------------------------------
# RUN
# --------------------------------------------------
if st.button(
    "Test ECHA registrants API",
    type="primary",
):

    with st.spinner(
        "Requesting registrants from ECHA..."
    ):

        result = (
            run_api_test()
        )

    # ----------------------------------
    # ERROR
    # ----------------------------------
    if result[
        "error"
    ]:

        st.error(
            result[
                "error"
            ]
        )

        st.stop()

    response = (
        result[
            "response"
        ]
    )

    # ----------------------------------
    # REQUEST DETAILS
    # ----------------------------------
    st.subheader(
        "1. Request"
    )

    st.write(
        "**HTTP method:** GET"
    )

    st.write(
        "**Endpoint:**"
    )

    st.code(
        REGISTRANTS_API_URL,
        language=None,
    )

    st.write(
        "**Parameters:**"
    )

    st.json(
        result[
            "params"
        ]
    )


    # ----------------------------------
    # RESPONSE
    # ----------------------------------
    st.subheader(
        "2. HTTP response"
    )

    response_columns = (
        st.columns(4)
    )

    response_columns[0].metric(
        "HTTP",
        response.status_code,
    )

    response_columns[1].metric(
        "Response bytes",
        len(
            response.content
        ),
    )

    response_columns[2].metric(
        "Valid JSON",
        (
            "Yes"
            if result[
                "json"
            ]
            is not None
            else
            "No"
        ),
    )

    response_columns[3].metric(
        "Total reported",
        (
            result[
                "total_count"
            ]
            if result[
                "total_count"
            ]
            is not None
            else
            "Not found"
        ),
    )

    st.write(
        "**Final URL:**"
    )

    st.code(
        response.url,
        language=None,
    )

    st.write(
        "**Content-Type:** "
        f"{response.headers.get('content-type', '')}"
    )


    # ----------------------------------
    # HTTP STATUS
    # ----------------------------------
    if (
        response.status_code
        == 200
    ):

        st.success(
            "ECHA returned HTTP 200."
        )

    elif (
        response.status_code
        == 403
    ):

        st.error(
            "ECHA returned HTTP 403. "
            "The correct endpoint was reached, "
            "but access was refused."
        )

    elif (
        response.status_code
        == 404
    ):

        st.error(
            "ECHA returned HTTP 404."
        )

    elif (
        response.status_code
        == 429
    ):

        st.error(
            "ECHA returned HTTP 429. "
            "The request was rate limited."
        )

    elif (
        response.status_code
        >= 400
    ):

        st.error(
            "ECHA returned HTTP "
            f"{response.status_code}."
        )


    # ----------------------------------
    # REGISTRANT SUMMARY
    # ----------------------------------
    st.subheader(
        "3. Registrant summary"
    )

    summary_columns = (
        st.columns(4)
    )

    summary_columns[0].metric(
        "Expected",
        EXPECTED_REGISTRANTS,
    )

    summary_columns[1].metric(
        "API total",
        (
            result[
                "total_count"
            ]
            if result[
                "total_count"
            ]
            is not None
            else
            "Unknown"
        ),
    )

    summary_columns[2].metric(
        "Items extracted",
        len(
            result[
                "registrants"
            ]
        ),
    )

    summary_columns[3].metric(
        "Benchmark",
        (
            "MATCH"
            if (
                result[
                    "total_count"
                ]
                ==
                EXPECTED_REGISTRANTS
            )
            else
            "Pending"
        ),
    )

    st.write(
        "**Selected JSON list path:**"
    )

    st.code(
        (
            result[
                "selected_path"
            ]
            or
            "No list selected"
        ),
        language=None,
    )


    # ----------------------------------
    # REGISTRANTS TABLE
    # ----------------------------------
    st.subheader(
        "4. Registrants"
    )

    registrants = (
        result[
            "registrants"
        ]
    )

    if registrants:

        dataframe = (
            pd.DataFrame(
                registrants
            )
        )

        useful_columns = [
            column
            for column
            in dataframe.columns
            if (
                dataframe[
                    column
                ]
                .astype(str)
                .str.strip()
                .ne("")
                .any()
            )
        ]

        if useful_columns:

            dataframe = (
                dataframe[
                    useful_columns
                ]
            )

        st.dataframe(
            dataframe,
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.warning(
            "No registrant rows "
            "were extracted."
        )


    # ----------------------------------
    # COMPLETE JSON
    # ----------------------------------
    with st.expander(
        "5. Complete API JSON",
        expanded=False,
    ):

        if (
            result[
                "json"
            ]
            is not None
        ):

            st.json(
                result[
                    "json"
                ]
            )

        else:

            st.write(
                "No valid JSON response."
            )


    # ----------------------------------
    # RAW RESPONSE
    # ----------------------------------
    with st.expander(
        "6. Raw API response",
        expanded=False,
    ):

        st.code(
            response.text[
                :30000
            ],
            language=None,
        )