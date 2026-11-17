import json
from pathlib import Path

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
CODE_VERSION = "ECHA_REGISTRANTS_API_TEST_V1"


# --------------------------------------------------
# TEST SUBSTANCE
# --------------------------------------------------
TEST_CAS = "128-37-0"
TEST_EC = "204-881-4"
TEST_RML_ID = "100.004.439"

ECHA_BASE_URL = "https://chem.echa.europa.eu"


# --------------------------------------------------
# IMPORTANT
#
# These are discovery candidates only.
#
# We do NOT assume that any of them is the correct
# endpoint.
#
# The script will show exactly which endpoints exist
# and what response ECHA returns.
# --------------------------------------------------
CANDIDATE_ENDPOINTS = [
    {
        "name": "Registrant list candidate 1",
        "url": (
            ECHA_BASE_URL
            + "/api-dossier-list/v1/registrant"
        ),
    },
    {
        "name": "Registrant list candidate 2",
        "url": (
            ECHA_BASE_URL
            + "/api-dossier-list/v1/registrants"
        ),
    },
    {
        "name": "Registrant list candidate 3",
        "url": (
            ECHA_BASE_URL
            + "/api-dossier-list/v1/legal-entity"
        ),
    },
    {
        "name": "Registrant list candidate 4",
        "url": (
            ECHA_BASE_URL
            + "/api-dossier-list/v1/legal-entities"
        ),
    },
    {
        "name": "Registration list candidate",
        "url": (
            ECHA_BASE_URL
            + "/api-dossier-list/v1/registration"
        ),
    },
]


# --------------------------------------------------
# STANDARD PARAMETERS
# --------------------------------------------------
BASE_PARAMS = {
    "pageIndex": 1,
    "pageSize": 100,
    "rmlId": TEST_RML_ID,
    "legislation": "REACH",
}


# --------------------------------------------------
# REQUEST SETTINGS
# --------------------------------------------------
CONNECT_TIMEOUT_SECONDS = 20
READ_TIMEOUT_SECONDS = 60

HEADERS = {
    "Accept": (
        "application/json, "
        "text/plain, "
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
# SESSION
# --------------------------------------------------
def create_session():
    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    retry = Retry(
        total=1,
        connect=1,
        read=1,
        status=1,
        backoff_factor=0.5,
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
# SAFE JSON PARSER
# --------------------------------------------------
def parse_json_safe(response):
    try:
        return response.json()

    except Exception:
        return None


# --------------------------------------------------
# SEARCH JSON RECURSIVELY
# --------------------------------------------------
def search_json_for_values(
    value,
    search_terms,
    path="root",
    matches=None,
):
    if matches is None:
        matches = []

    if isinstance(value, dict):
        for key, nested_value in value.items():
            nested_path = (
                f"{path}.{key}"
            )

            key_lower = (
                str(key).lower()
            )

            matching_terms = [
                term
                for term in search_terms
                if term.lower()
                in key_lower
            ]

            if matching_terms:
                matches.append(
                    {
                        "path": nested_path,
                        "value": str(
                            nested_value
                        )[:500],
                        "matched_on": (
                            ", ".join(
                                matching_terms
                            )
                        ),
                    }
                )

            search_json_for_values(
                nested_value,
                search_terms,
                nested_path,
                matches,
            )

    elif isinstance(value, list):
        for index, item in enumerate(
            value
        ):
            search_json_for_values(
                item,
                search_terms,
                (
                    f"{path}"
                    f"[{index}]"
                ),
                matches,
            )

    else:
        text = str(value)

        text_lower = (
            text.lower()
        )

        matching_terms = [
            term
            for term in search_terms
            if term.lower()
            in text_lower
        ]

        if matching_terms:
            matches.append(
                {
                    "path": path,
                    "value": text[:500],
                    "matched_on": (
                        ", ".join(
                            matching_terms
                        )
                    ),
                }
            )

    return matches


# --------------------------------------------------
# TEST ONE ENDPOINT
# --------------------------------------------------
def test_endpoint(
    session,
    endpoint,
):
    url = endpoint["url"]

    print(
        "",
        flush=True,
    )

    print(
        "=" * 80,
        flush=True,
    )

    print(
        "ECHA REGISTRANT "
        "ENDPOINT TEST",
        flush=True,
    )

    print(
        f"NAME: "
        f"{endpoint['name']}",
        flush=True,
    )

    print(
        f"GET: {url}",
        flush=True,
    )

    print(
        f"PARAMS: "
        f"{BASE_PARAMS}",
        flush=True,
    )

    try:
        response = session.get(
            url,
            params=BASE_PARAMS,
            timeout=(
                CONNECT_TIMEOUT_SECONDS,
                READ_TIMEOUT_SECONDS,
            ),
            allow_redirects=True,
        )

    except Exception as error:
        print(
            "REQUEST ERROR: "
            f"{error}",
            flush=True,
        )

        return {
            "name": endpoint[
                "name"
            ],
            "requested_url": url,
            "final_url": None,
            "status": None,
            "content_type": None,
            "response_length": 0,
            "json": None,
            "body_preview": "",
            "interesting_matches": [],
            "error": str(error),
        }

    content_type = (
        response.headers
        .get(
            "content-type",
            "",
        )
    )

    print(
        "FINAL URL: "
        f"{response.url}",
        flush=True,
    )

    print(
        "STATUS: "
        f"{response.status_code}",
        flush=True,
    )

    print(
        "CONTENT TYPE: "
        f"{content_type}",
        flush=True,
    )

    print(
        "BODY PREVIEW:",
        flush=True,
    )

    print(
        response.text[:2000],
        flush=True,
    )

    parsed_json = (
        parse_json_safe(
            response
        )
    )

    interesting_matches = []

    if parsed_json is not None:
        interesting_matches = (
            search_json_for_values(
                parsed_json,
                [
                    "BASF",
                    "3M Belgium",
                    "Afton",
                    "registrant",
                    "legal",
                    "address",
                    "status",
                    "company",
                    "organisation",
                    "organization",
                ],
            )
        )

        if interesting_matches:
            print(
                "INTERESTING "
                "JSON MATCHES:",
                flush=True,
            )

            for item in (
                interesting_matches[
                    :50
                ]
            ):
                print(
                    item,
                    flush=True,
                )

    return {
        "name": endpoint[
            "name"
        ],
        "requested_url": url,
        "final_url": response.url,
        "status": (
            response.status_code
        ),
        "content_type": (
            content_type
        ),
        "response_length": len(
            response.content
        ),
        "json": parsed_json,
        "body_preview": (
            response.text[:5000]
        ),
        "interesting_matches": (
            interesting_matches
        ),
        "error": None,
    }


# --------------------------------------------------
# RUN TEST
# --------------------------------------------------
def run_registrant_test():
    session = (
        create_session()
    )

    results = []

    print(
        "ECHA code version: "
        f"{CODE_VERSION}",
        flush=True,
    )

    print(
        "TEST SUBSTANCE:",
        flush=True,
    )

    print(
        f"CAS: {TEST_CAS}",
        flush=True,
    )

    print(
        f"EC: {TEST_EC}",
        flush=True,
    )

    print(
        f"RML ID: "
        f"{TEST_RML_ID}",
        flush=True,
    )

    for endpoint in (
        CANDIDATE_ENDPOINTS
    ):
        result = test_endpoint(
            session,
            endpoint,
        )

        results.append(
            result
        )

    return results


# --------------------------------------------------
# STREAMLIT UI
# --------------------------------------------------
st.title(
    "ECHA Registrants API discovery"
)

st.caption(
    f"Version: {CODE_VERSION}"
)

st.info(
    "This page tests possible ECHA REST "
    "routes for the REACH Registrants tab. "
    "It does not use browser automation and "
    "does not attempt to bypass ECHA access "
    "controls."
)


# --------------------------------------------------
# TEST CHEMICAL
# --------------------------------------------------
st.subheader(
    "Test substance"
)

column1, column2, column3 = (
    st.columns(3)
)

column1.metric(
    "CAS",
    TEST_CAS,
)

column2.metric(
    "EC",
    TEST_EC,
)

column3.metric(
    "RML ID",
    TEST_RML_ID,
)

st.write(
    "Expected benchmark from the "
    "ECHA Registrants tab:"
)

st.write(
    "- approximately 42 registrants"
)

st.write(
    "- known visible examples include "
    "3M Belgium, Afton Chemical and BASF SE"
)


# --------------------------------------------------
# RUN BUTTON
# --------------------------------------------------
run_button = st.button(
    "Test registrant API routes",
    type="primary",
)


if run_button:
    with st.spinner(
        "Testing ECHA registrant "
        "API routes..."
    ):
        results = (
            run_registrant_test()
        )

    st.success(
        "Endpoint discovery "
        "test completed."
    )

    # ----------------------------------
    # SUMMARY
    # ----------------------------------
    st.subheader(
        "Endpoint results"
    )

    summary_rows = []

    for result in results:
        summary_rows.append(
            {
                "Test": (
                    result["name"]
                ),
                "HTTP": (
                    result[
                        "status"
                    ]
                ),
                "Content type": (
                    result[
                        "content_type"
                    ]
                ),
                "Response bytes": (
                    result[
                        "response_length"
                    ]
                ),
                "JSON": (
                    result["json"]
                    is not None
                ),
                "Relevant matches": (
                    len(
                        result[
                            "interesting_matches"
                        ]
                    )
                ),
                "Error": (
                    result[
                        "error"
                    ]
                ),
            }
        )

    st.dataframe(
        pd.DataFrame(
            summary_rows
        ),
        width="stretch",
        hide_index=True,
    )

    # ----------------------------------
    # DETAILS
    # ----------------------------------
    st.subheader(
        "Detailed results"
    )

    for result in results:
        title = (
            f"{result['name']} "
            f"— HTTP "
            f"{result['status']}"
        )

        with st.expander(
            title,
            expanded=(
                result[
                    "status"
                ]
                == 200
            ),
        ):
            st.write(
                "**Requested endpoint:**"
            )

            st.code(
                result[
                    "requested_url"
                ],
                language=None,
            )

            if result[
                "final_url"
            ]:
                st.write(
                    "**Final URL:**"
                )

                st.code(
                    result[
                        "final_url"
                    ],
                    language=None,
                )

            if result[
                "error"
            ]:
                st.error(
                    result[
                        "error"
                    ]
                )

                continue

            st.write(
                "**HTTP status:** "
                f"{result['status']}"
            )

            st.write(
                "**Content-Type:** "
                f"{result['content_type']}"
            )

            # --------------------------
            # FOUND MATCHES
            # --------------------------
            matches = (
                result[
                    "interesting_matches"
                ]
            )

            if matches:
                st.success(
                    "Interesting registrant-"
                    "related values were "
                    "found in this response."
                )

                st.dataframe(
                    pd.DataFrame(
                        matches
                    ),
                    width="stretch",
                    hide_index=True,
                )

            # --------------------------
            # JSON
            # --------------------------
            if (
                result["json"]
                is not None
            ):
                with st.expander(
                    "Parsed JSON",
                    expanded=False,
                ):
                    st.json(
                        result[
                            "json"
                        ]
                    )

            # --------------------------
            # RAW BODY
            # --------------------------
            with st.expander(
                "Raw response preview",
                expanded=False,
            ):
                st.code(
                    result[
                        "body_preview"
                    ],
                    language=None,
                )