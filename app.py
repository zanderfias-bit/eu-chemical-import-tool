import streamlit as st
import pandas as pd

from utils.cas_validator import validate_cas
from services.echa_search import search_echa
from services.echa_detail import get_echa_detail
from services.ecics_lookup import get_goods_code
from services.taric_lookup import get_taric

# --------------------------------------------------
# CACHE FUNCTIONS
# --------------------------------------------------
selected_url = None

@st.cache_data(ttl=86400)
def get_cached_echa_search(
    cas_number,
):
    return search_echa(
        cas_number
    )


@st.cache_data(ttl=86400)
def get_cached_echa_detail(
    url,
    cas_number,
):
    return get_echa_detail(
        url,
        cas_number,
    )


@st.cache_data(ttl=86400)
def get_cached_goods_code(
    ec_number,
):
    return get_goods_code(
        ec_number
    )

import os
import sys
import subprocess

if not os.path.exists("/home/appuser/.cache/ms-playwright"):

    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True
    )



# --------------------------------------------------
# PAGE SETTINGS
# --------------------------------------------------

st.set_page_config(
    page_title="EU Chemical Import Tool",
    page_icon="🧪",
    layout="wide"
)

st.title("🧪 EU Chemical Import Tool")

st.write(
    "Search ECHA CHEM using a CAS number."
)


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------

if "search_results" not in st.session_state:
    st.session_state.search_results = []

if "selected_substance" not in st.session_state:
    st.session_state.selected_substance = None


# --------------------------------------------------
# INPUTS
# --------------------------------------------------

cas = st.text_input(
    "CAS Number",
    placeholder="110-94-1"
)

country = st.text_input(
    "Country of Origin",
    placeholder="China"
)


# --------------------------------------------------
# SEARCH BUTTON
# --------------------------------------------------

if st.button(
    "Search ECHA",
    type="primary"
):

    cas = cas.strip()
    country = country.strip()

    if not cas:

        st.error(
            "Please enter a CAS number."
        )

        st.stop()

    if not validate_cas(cas):

        st.error(
            "Invalid CAS number."
        )

        st.stop()

    if not country:

        st.error(
            "Please enter the country of origin."
        )

        st.stop()

    try:
        with st.spinner("Searching ECHA..."):
            results = results = get_cached_echa_search(
                cas
            )

        st.session_state.search_results = results

        if results:
            st.success(
                f"{len(results)} result(s) found."
            )
        else:
            st.warning(
                "ECHA was reached, but no matching result was found."
            )

    except RuntimeError as error:
        st.session_state.search_results = []

        st.error(
            "The ECHA search could not be completed."
        )

        st.info(str(error))
        st.stop()


# --------------------------------------------------
# DISPLAY RESULTS
# --------------------------------------------------

if len(st.session_state.search_results) > 0:

    df = pd.DataFrame(
        st.session_state.search_results
    )

    st.subheader(
        "ECHA Search Results"
    )

    st.dataframe(
        df[
            [
                "Name",
                "EC Number",
                "CAS Number"
            ]
        ],
        use_container_width=True
    )

    # nicer display text

    df["Display"] = (
        df["Name"]
        + " | EC "
        + df["EC Number"].fillna("")
        + " | CAS "
        + df["CAS Number"].fillna("")
    )

    selected_display = st.selectbox(
        "Select substance",
        options=df["Display"],
        key="selected_substance"
    )

    selected_row = df[
        df["Display"] == selected_display
    ].iloc[0]

    st.subheader(
        "Selected Substance"
    )

    st.write(
        f"Name: {selected_row['Name']}"
    )

    st.write(
        f"EC Number: {selected_row['EC Number']}"
    )

    st.write(
        f"CAS Number: {selected_row['CAS Number']}"
    )

    st.write(
        f"URL: {selected_row['URL']}"
    )
    try:
        # code using selected_url
        selected_url = selected_row["URL"]

    except Exception:
        pass
    

    # --------------------------------------------------
    # AUTOMATIC ECICS LOOKUP
    # --------------------------------------------------

    with st.spinner(
        "Searching ECICS..."
    ):

        ecics_result = get_goods_code(
            selected_row["EC Number"]
        )

    if ecics_result["success"]:

        st.subheader(
            "ECICS Information"
        )

        col1, col2 = st.columns(2)

        with col1:

            st.write(
                f"Goods Code: {ecics_result['goods_code']}"
            )

            st.write(
                f"CUS Number: {ecics_result['cus_number']}"
            )

        with col2:

            st.write(
                f"CAS Number: {ecics_result['cas_number']}"
            )

            st.write(
                f"Substance Name: {ecics_result['substance_name']}"
            )

    else:

        st.warning(
            ecics_result["message"]
        )
    # --------------------------------------------------
    # AUTOMATIC TARIC LOOKUP
    # --------------------------------------------------

    if (
        ecics_result.get("success", False)
        and "goods_code" in ecics_result
    ):

        with st.spinner(
            "Building TARIC URL..."
        ):

            taric_result = get_taric(
                ecics_result["goods_code"],
                country,
                selected_row["CAS Number"]
            )

        st.subheader(
            "TARIC Information"
        )

        if taric_result["success"]:

            st.write(
                f"Country of Origin: {country}"
            )

            st.write(
                f"Goods Code: {ecics_result['goods_code']}"
            )

            st.markdown(
                taric_result["taric_url"]
            )

            st.code(
                taric_result["taric_url"],
                language="text"
            )

            if (
                "selected_taric_code"
                in taric_result
            ):
                st.write(
                    f"Selected TARIC Code: "
                    f"{taric_result['selected_taric_code']}"
                )

            if (
                "measure_text"
                in taric_result
            ):
                st.text_area(
                    "TARIC Measures",
                    taric_result["measure_text"],
                    height=800,
                )

        else:

            st.warning(
                taric_result["message"]
            )

            if (
                "debug_links"
                in taric_result
            ):
                st.subheader(
                    "Debug Links"
                )

                for link in taric_result[
                    "debug_links"
                ]:
                    st.write(link)

    else:

        st.warning(
            "No ECICS goods code found. "
            "TARIC lookup skipped."
        )

        st.write(
            "ECICS Result:",
            ecics_result
        )

    
# --------------------------------------------------
# AUTOMATIC ECHA DETAIL LOOKUP
# --------------------------------------------------

with st.spinner(
    "Loading ECHA registration details..."
):
    try:
        # code using selected_url
        detail = detail = get_cached_echa_detail(
                selected_url,
                cas)
    except Exception:
        pass

st.subheader(
    "Detail Page Information"
)

try:
        # code using selected_url
        st.write(
            f"Title: {detail['title']}")
except Exception:
    pass


st.subheader(
    "REACH Registrants"
)

try:
        # code using selected_url
        registrants = detail["registrants"]
except Exception:
    pass


if len(registrants) > 0:

    df_registrants = pd.DataFrame(
        registrants
    )

    df_registrants = (
        df_registrants
        .drop_duplicates()
        .reset_index(drop=True)
    )

    st.success(
        f"{len(df_registrants)} registrant(s) found."
    )

    st.dataframe(
        df_registrants,
        use_container_width=True
    )

else:

    st.warning(
        "No registrants found."
    )


if st.button(
    "Clear Cache"
):
    st.cache_data.clear()

    st.success(
        "Cache cleared."
    )
    