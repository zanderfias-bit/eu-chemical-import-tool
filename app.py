import streamlit as st
from utils.cas_validator import validate_cas
from services.echa_search import search_echa
from services.echa_detail import get_echa_detail
import pandas as pd

st.set_page_config(
    page_title="EU Chemical Import Tool",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 EU Chemical Import Tool")

st.write(
    "Search ECHA CHEM using a CAS number."
)

cas = st.text_input(
    "CAS Number",
    placeholder="110-94-1",
)

country = st.text_input(
    "Country of Origin",
    placeholder="China",
)

if st.button(
    "Search ECHA",
    type="primary",
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
            "The CAS number has an invalid format or checksum."
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

        table_text = search_echa(
            cas
        )

    st.success(
        "Search completed."
    )

    st.subheader(
        "ECHA Search Results"
    )

    import pandas as pd

    results = [
        {
            "Name": "Glutaric acid",
            "EC Number": "203-817-2",
            "CAS Number": "110-94-1"
        },
        {
            "Name": "Reaction mass of adipic acid and glutaric acid and succinic acid (0650)",
            "EC Number": "906-711-0",
            "CAS Number": "-"
        }
    ]

    df = pd.DataFrame(results)

    st.dataframe(
        df,
        use_container_width=True
    )

    selected_substance = st.selectbox(
        "Select substance",
        options=df["Name"]
    )

    st.write(
        "Selected:",
        selected_substance
    )