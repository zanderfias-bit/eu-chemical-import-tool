import streamlit as st
import pandas as pd

from utils.cas_validator import validate_cas
from services.echa_search import search_echa
from services.echa_detail import get_echa_detail


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

    with st.spinner(
        "Searching ECHA..."
    ):

        results = search_echa(cas)

    st.session_state.search_results = results

    st.success(
        f"{len(results)} result(s) found."
    )


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

    selected_url = selected_row["URL"]


# --------------------------------------------------
# NEXT STEP
# --------------------------------------------------

    if st.button(
        "Open ECHA Detail Page"
    ):

        with st.spinner(
            "Opening detail page..."
        ):

            detail = get_echa_detail(
                selected_url,cas
            )

        st.subheader(
            "Detail Page Information"
        )

        st.write(
            f"Title: {detail['title']}"
        )

        st.subheader(
            "REACH Registrants"
        )

        registrants = detail["registrants"]

        if len(registrants) > 0:

            df_registrants = pd.DataFrame(
                registrants
            )

            df_registrants = df_registrants.drop_duplicates()

            st.dataframe(
                df_registrants,
                use_container_width=True
            )

        else:

            st.warning(
                "No registrants found."
            )