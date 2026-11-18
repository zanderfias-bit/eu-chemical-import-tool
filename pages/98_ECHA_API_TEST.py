import json
import re
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
    page_title="ECHA Registrants API Test",
    page_icon="🔎",
    layout="wide",
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_REGISTRANTS_API_TEST_V13"


# --------------------------------------------------
# TEST SUBSTANCE
# --------------------------------------------------
CAS_NUMBER = "128-37-0"
EC_NUMBER = "204-881-4"
RML_ID = "100.004.439"
EXPECTED_REGISTRANTS = 42


# --------------------------------------------------
# ECHA RESOURCES
# --------------------------------------------------
ECHA_BASE_URL = "https://chem.echa.europa.eu"

OVERVIEW_URL = (
    f"{ECHA_BASE_URL}/"
    f"{RML_ID}/overview"
)

HOST_RUNTIME_CONFIG_URL = (
    f"{ECHA_BASE_URL}/"
    "mfe-config/mfe-config.json"
)

DOSSIER_RUNTIME_CONFIG_URL = (
    f"{ECHA_BASE_URL}/"
    "mfe-config/dossierList/mfe-config.json"
)

DOSSIER_LIST_WEB_COMPONENTS_URL = (
    f"{ECHA_BASE_URL}/"
    "dossierList/"
    "web-components-NIMFYLDU.js"
)


# --------------------------------------------------
# REQUEST SETTINGS
# --------------------------------------------------
CONNECT_TIMEOUT_SECONDS = 20
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
}


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
        backoff_factor=0.75,
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

    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=retry
        ),
    )

    return session


# --------------------------------------------------
# SAFE GET
# --------------------------------------------------
def safe_get(
    session,
    url,
    params=None,
    referer=None,
):
    headers = (
        {"Referer": referer}
        if referer
        else None
    )

    try:
        response = session.get(
            url,
            params=params,
            headers=headers,
            timeout=(
                CONNECT_TIMEOUT_SECONDS,
                READ_TIMEOUT_SECONDS,
            ),
            allow_redirects=True,
        )

        return response, None

    except requests.Timeout as error:
        return (
            None,
            f"Request timed out: {error}",
        )

    except requests.RequestException as error:
        return (
            None,
            f"Request failed: {error}",
        )


# --------------------------------------------------
# JSON PARSER
# --------------------------------------------------
def parse_json(
    response,
):
    if response is None:
        return None

    try:
        return response.json()

    except ValueError:
        return None


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
# RECURSIVE JSON KEY LOOKUP
# --------------------------------------------------
def find_json_key(
    value,
    wanted_key,
):
    wanted = (
        wanted_key.lower()
    )

    if isinstance(
        value,
        dict,
    ):
        for key, nested in (
            value.items()
        ):
            if (
                str(key).lower()
                ==
                wanted
            ):
                return nested

        for nested in (
            value.values()
        ):
            found = find_json_key(
                nested,
                wanted_key,
            )

            if found is not None:
                return found

    elif isinstance(
        value,
        list,
    ):
        for item in value:
            found = find_json_key(
                item,
                wanted_key,
            )

            if found is not None:
                return found

    return None


# --------------------------------------------------
# EXTRACT REGISTRANTS SUFFIX
# --------------------------------------------------
def extract_registrants_suffix(
    javascript_text,
):
    match = re.search(
        (
            r"registrantsUrl\s*=\s*"
            r"this\.registrantsApiUrl"
            r"\.concat\(\s*"
            r"[\"']([^\"']+)[\"']"
            r"\s*\)"
        ),
        javascript_text
        or "",
        flags=re.IGNORECASE,
    )

    if not match:
        return ""

    return (
        match.group(1)
        .strip()
    )


# --------------------------------------------------
# BUILD ENDPOINT
# --------------------------------------------------
def build_endpoint(
    api_base,
    suffix,
):
    if not api_base:
        return ""

    if not suffix:
        return ""

    absolute_base = urljoin(
        ECHA_BASE_URL + "/",
        str(
            api_base
        ).strip(),
    )

    if not absolute_base.endswith(
        "/"
    ):
        absolute_base += "/"

    clean_suffix = (
        str(
            suffix
        )
        .strip()
        .lstrip("/")
    )

    return urljoin(
        absolute_base,
        clean_suffix,
    )


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
                "path": path,
                "items": value,
            }
        )

        for index, item in enumerate(
            value
        ):
            find_json_lists(
                item,
                f"{path}[{index}]",
                results,
            )

    elif isinstance(
        value,
        dict,
    ):
        for key, nested in (
            value.items()
        ):
            find_json_lists(
                nested,
                f"{path}.{key}",
                results,
            )

    return results


# --------------------------------------------------
# SCORE POSSIBLE REGISTRANT LIST
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

        item_keys = {
            str(key).lower()
            for key
            in item.keys()
        }

        score += (
            len(
                item_keys
                & relevant_keys
            )
            * 20
        )

    path = (
        candidate.get(
            "path",
            "",
        )
        .lower()
    )

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
    body,
):
    if isinstance(
        body,
        list,
    ):
        return (
            "root",
            body,
        )

    if isinstance(
        body,
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
            value = body.get(
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

    candidates = (
        find_json_lists(
            body
        )
        if isinstance(
            body,
            (
                dict,
                list,
            ),
        )
        else []
    )

    if not candidates:
        return (
            "",
            [],
        )

    best = max(
        candidates,
        key=score_list,
    )

    if score_list(
        best
    ) <= 0:
        return (
            "",
            [],
        )

    return (
        best[
            "path"
        ],
        best[
            "items"
        ],
    )


# --------------------------------------------------
# RECURSIVE FIELD LOOKUP
# --------------------------------------------------
def find_field(
    value,
    possible_keys,
):
    keys = {
        key.lower()
        for key
        in possible_keys
    }

    if isinstance(
        value,
        dict,
    ):
        for key, nested in (
            value.items()
        ):
            if (
                str(key).lower()
                in keys
                and
                not isinstance(
                    nested,
                    (
                        dict,
                        list,
                    ),
                )
            ):
                return nested

        for nested in (
            value.values()
        ):
            found = find_field(
                nested,
                possible_keys,
            )

            if found not in (
                None,
                "",
            ):
                return found

    elif isinstance(
        value,
        list,
    ):
        for item in value:
            found = find_field(
                item,
                possible_keys,
            )

            if found not in (
                None,
                "",
            ):
                return found

    return None


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
# FIND TOTAL COUNT
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
    }

    if isinstance(
        value,
        dict,
    ):
        for key, nested in (
            value.items()
        ):
            if (
                str(key).lower()
                in total_keys
                and
                isinstance(
                    nested,
                    (
                        int,
                        float,
                    ),
                )
            ):
                return int(
                    nested
                )

        for nested in (
            value.values()
        ):
            found = find_total_count(
                nested
            )

            if found is not None:
                return found

    elif isinstance(
        value,
        list,
    ):
        for item in value:
            found = find_total_count(
                item
            )

            if found is not None:
                return found

    return None


# --------------------------------------------------
# FETCH RESOURCE
# --------------------------------------------------
def fetch_resource(
    session,
    url,
):
    response, error = safe_get(
        session=session,
        url=url,
        referer=OVERVIEW_URL,
    )

    return {
        "response": (
            response
        ),
        "error": (
            error
        ),
        "status": (
            response.status_code
            if response
            is not None
            else None
        ),
        "content_type": (
            response.headers.get(
                "content-type",
                "",
            )
            if response
            is not None
            else ""
        ),
        "bytes": (
            len(
                response.content
            )
            if response
            is not None
            else 0
        ),
        "json": (
            parse_json(
                response
            )
        ),
        "text": (
            response.text
            if response
            is not None
            else ""
        ),
    }


# --------------------------------------------------
# RUN TEST
# --------------------------------------------------
def run_test():
    session = (
        create_session()
    )

    # ----------------------------------
    # HOST CONFIG
    # ----------------------------------
    host_config = (
        fetch_resource(
            session,
            HOST_RUNTIME_CONFIG_URL,
        )
    )

    # ----------------------------------
    # DOSSIER LIST-SPECIFIC CONFIG
    # ----------------------------------
    dossier_config = (
        fetch_resource(
            session,
            DOSSIER_RUNTIME_CONFIG_URL,
        )
    )

    # ----------------------------------
    # DOSSIER LIST JAVASCRIPT
    # ----------------------------------
    javascript = (
        fetch_resource(
            session,
            DOSSIER_LIST_WEB_COMPONENTS_URL,
        )
    )

    # ----------------------------------
    # EXTRACT PROVEN SUFFIX
    # ----------------------------------
    suffix = (
        extract_registrants_suffix(
            javascript[
                "text"
            ]
        )
    )

    # ----------------------------------
    # FIND REGISTRANTS API URL
    # ----------------------------------
    registrants_api_url = ""

    if (
        dossier_config[
            "json"
        ]
        is not None
    ):
        value = find_json_key(
            dossier_config[
                "json"
            ],
            "registrantsApiUrl",
        )

        registrants_api_url = (
            normalise_text(
                value
            )
        )

    # ----------------------------------
    # FIND DOSSIER LIST API URL
    # ----------------------------------
    dossier_list_api_url = ""

    if (
        dossier_config[
            "json"
        ]
        is not None
    ):
        value = find_json_key(
            dossier_config[
                "json"
            ],
            "dossierListApiUrl",
        )

        dossier_list_api_url = (
            normalise_text(
                value
            )
        )

    # ----------------------------------
    # BUILD ENDPOINT
    # ----------------------------------
    endpoint = (
        build_endpoint(
            registrants_api_url,
            suffix,
        )
    )

    api_params = {
        "rmlId": (
            RML_ID
        ),
        "pageIndex": 1,
        "pageSize": 100,
    }

    api_response = None
    api_error = None
    api_json = None

    # ----------------------------------
    # IMPORTANT:
    # ONLY MAKE REQUEST IF ECHA ITSELF
    # PROVIDED registrantsApiUrl.
    # ----------------------------------
    if (
        endpoint
        and
        registrants_api_url
        and
        suffix.lower()
        ==
        "registrants"
    ):
        api_response, api_error = (
            safe_get(
                session=session,
                url=endpoint,
                params=api_params,
                referer=OVERVIEW_URL,
            )
        )

        api_json = (
            parse_json(
                api_response
            )
        )

    # ----------------------------------
    # PROCESS RESPONSE
    # ----------------------------------
    selected_path = ""
    items = []
    registrants = []
    total_count = None

    if api_json is not None:
        (
            selected_path,
            items,
        ) = select_result_list(
            api_json
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
                api_json
            )
        )

    return {
        "host_config": (
            host_config
        ),
        "dossier_config": (
            dossier_config
        ),
        "javascript": (
            javascript
        ),
        "suffix": (
            suffix
        ),
        "registrants_api_url": (
            registrants_api_url
        ),
        "dossier_list_api_url": (
            dossier_list_api_url
        ),
        "endpoint": (
            endpoint
        ),
        "api_params": (
            api_params
        ),
        "api_status": (
            api_response_code
            if api_response
            is not None
            else None
        ),
        "api_final_url": (
            api_response.url
            if api_response
            is not None
            else ""
        ),
        "api_content_type": (
            api_response.headers.get(
                "content-type",
                "",
            )
            if api_response
            is not None
            else ""
        ),
        "api_bytes": (
            len(
                api_response.content
            )
            if api_response
            is not None
            else 0
        ),
        "api_json": (
            api_json
        ),
        "api_text": (
            api_response.text
            if api_response
            is not None
            else ""
        ),
        "api_error": (
            api_error
        ),
        "selected_path": (
            selected_path
        ),
        "registrants": (
            registrants
        ),
        "total_count": (
            total_count
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
    "V13 uses the dossierList micro-frontend's "
    "own runtime configuration."
)

st.info(
    "V13 only sends a registrants request if "
    "ECHA's dossierList runtime configuration "
    "explicitly contains registrantsApiUrl."
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
# CONFIGURATION RESOURCES
# --------------------------------------------------
st.subheader(
    "Configuration resources"
)

st.write(
    "**Host runtime configuration:**"
)

st.code(
    HOST_RUNTIME_CONFIG_URL,
    language=None,
)

st.write(
    "**dossierList runtime configuration "
    "discovered from ECHA JavaScript:**"
)

st.code(
    DOSSIER_RUNTIME_CONFIG_URL,
    language=None,
)


# --------------------------------------------------
# RUN TEST
# --------------------------------------------------
if st.button(
    "Load dossierList config and test registrants",
    type="primary",
):
    with st.spinner(
        "Loading the ECHA dossierList "
        "runtime configuration..."
    ):
        result = (
            run_test()
        )

    st.success(
        "Test completed."
    )

    # ----------------------------------
    # 1. SOURCE RESPONSES
    # ----------------------------------
    st.subheader(
        "1. Source responses"
    )

    source_rows = []

    resources = (
        (
            "Host runtime config",
            result[
                "host_config"
            ],
        ),
        (
            "dossierList runtime config",
            result[
                "dossier_config"
            ],
        ),
        (
            "dossierList web-components",
            result[
                "javascript"
            ],
        ),
    )

    for (
        label,
        resource,
    ) in resources:
        source_rows.append(
            {
                "Resource": (
                    label
                ),
                "HTTP": (
                    resource[
                        "status"
                    ]
                ),
                "Content-Type": (
                    resource[
                        "content_type"
                    ]
                ),
                "Bytes": (
                    resource[
                        "bytes"
                    ]
                ),
                "Valid JSON": (
                    resource[
                        "json"
                    ]
                    is not None
                ),
                "Error": (
                    resource[
                        "error"
                    ]
                ),
            }
        )

    st.dataframe(
        pd.DataFrame(
            source_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    # ----------------------------------
    # 2. DOSSIER LIST CONFIG
    # ----------------------------------
    st.subheader(
        "2. dossierList runtime configuration"
    )

    if (
        result[
            "dossier_config"
        ][
            "json"
        ]
        is not None
    ):
        st.json(
            result[
                "dossier_config"
            ][
                "json"
            ]
        )

    else:
        st.error(
            "The dossierList runtime "
            "configuration did not return "
            "valid JSON."
        )

        st.code(
            result[
                "dossier_config"
            ][
                "text"
            ][:10000],
            language=None,
        )

    # ----------------------------------
    # 3. EXTRACTED CONFIGURATION
    # ----------------------------------
    st.subheader(
        "3. Extracted registrants configuration"
    )

    config_rows = [
        {
            "Setting": (
                "dossierListApiUrl"
            ),
            "Value": (
                result[
                    "dossier_list_api_url"
                ]
            ),
        },
        {
            "Setting": (
                "registrantsApiUrl"
            ),
            "Value": (
                result[
                    "registrants_api_url"
                ]
            ),
        },
        {
            "Setting": (
                "registrants suffix"
            ),
            "Value": (
                result[
                    "suffix"
                ]
            ),
        },
        {
            "Setting": (
                "Constructed endpoint"
            ),
            "Value": (
                result[
                    "endpoint"
                ]
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

    # ----------------------------------
    # 4. API REQUEST
    # ----------------------------------
    st.subheader(
        "4. Registrants API request"
    )

    if not result[
        "registrants_api_url"
    ]:
        st.warning(
            "No API request was sent because "
            "dossierList runtime configuration "
            "does not contain registrantsApiUrl."
        )

    elif not result[
        "endpoint"
    ]:
        st.warning(
            "No API request was sent because "
            "the endpoint could not be constructed."
        )

    else:
        request_columns = (
            st.columns(4)
        )

        request_columns[0].metric(
            "HTTP",
            (
                result[
                    "api_status"
                ]
                if result[
                    "api_status"
                ]
                is not None
                else
                "Error"
            ),
        )

        request_columns[1].metric(
            "Response bytes",
            result[
                "api_bytes"
            ],
        )

        request_columns[2].metric(
            "Valid JSON",
            (
                "Yes"
                if result[
                    "api_json"
                ]
                is not None
                else
                "No"
            ),
        )

        request_columns[3].metric(
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
            "**Final request URL:**"
        )

        st.code(
            result[
                "api_final_url"
            ]
            or
            result[
                "endpoint"
            ],
            language=None,
        )

        st.write(
            "**Request parameters:**"
        )

        st.json(
            result[
                "api_params"
            ]
        )

        st.write(
            "**Content-Type:** "
            f"{result['api_content_type']}"
        )

        if result[
            "api_error"
        ]:
            st.error(
                result[
                    "api_error"
                ]
            )

        if (
            result[
                "api_status"
            ]
            == 404
        ):
            st.error(
                "ECHA returned HTTP 404 for "
                "the endpoint supplied by the "
                "dossierList configuration."
            )

        elif (
            result[
                "api_status"
            ]
            == 403
        ):
            st.error(
                "ECHA returned HTTP 403. "
                "The endpoint was reached but "
                "access was refused."
            )

        elif (
            result[
                "api_status"
            ]
            == 429
        ):
            st.error(
                "ECHA returned HTTP 429. "
                "The request was rate limited."
            )

        elif (
            result[
                "api_status"
            ]
            == 200
            and
            result[
                "api_json"
            ]
            is not None
        ):
            st.success(
                "ECHA returned HTTP 200 "
                "with valid JSON."
            )

    # ----------------------------------
    # 5. REGISTRANTS
    # ----------------------------------
    st.subheader(
        "5. Registrants"
    )

    st.write(
        "**Selected JSON list path:**"
    )

    st.code(
        result[
            "selected_path"
        ]
        or
        "No list selected",
        language=None,
    )

    if result[
        "registrants"
    ]:
        dataframe = (
            pd.DataFrame(
                result[
                    "registrants"
                ]
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
            "No registrant rows were extracted."
        )

    # ----------------------------------
    # 6. RAW API JSON
    # ----------------------------------
    with st.expander(
        "6. Complete API JSON",
        expanded=False,
    ):
        if (
            result[
                "api_json"
            ]
            is not None
        ):
            st.json(
                result[
                    "api_json"
                ]
            )

        else:
            st.write(
                "No valid API JSON returned."
            )

    # ----------------------------------
    # 7. RAW API RESPONSE
    # ----------------------------------
    with st.expander(
        "7. Raw API response",
        expanded=False,
    ):
        if result[
            "api_text"
        ]:
            st.code(
                result[
                    "api_text"
                ][:20000],
                language=None,
            )

        else:
            st.write(
                "No API response body."
            )