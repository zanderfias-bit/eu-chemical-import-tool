from playwright.sync_api import sync_playwright
from datetime import datetime


COUNTRY_CODES = {
    "China": "CN",
    "India": "IN",
    "United States": "US",
    "USA": "US",
    "Japan": "JP",
    "South Korea": "KR",
    "United Kingdom": "GB",
    "Turkey": "TR",
    "Taiwan": "TW",
    "Thailand": "TH",
    "Vietnam": "VN",
    "Malaysia": "MY",
    "Singapore": "SG",
    "Indonesia": "ID"
}


def get_taric(goods_code, country):

    country_code = COUNTRY_CODES.get(country)

    if not country_code:

        return {
            "success": False,
            "message": f"Country '{country}' not supported"
        }

    today = datetime.today()

    sim_date = today.strftime("%Y%m%d")
    date_picker = today.strftime("%d-%m-%Y")

    taric_url = (
        "https://ec.europa.eu/taxation_customs/dds2/taric/measures.jsp"
        f"?Lang=en"
        f"&SimDate={sim_date}"
        f"&Area={country_code}"
        f"&MeasType="
        f"&StartPub="
        f"&EndPub="
        f"&MeasText="
        f"&GoodsText="
        f"&op="
        f"&Taric={goods_code}"
        f"&AdditionalCode="
        f"&search_text=goods"
        f"&textSearch="
        f"&LangDescr=en"
        f"&OrderNum="
        f"&Regulation="
        f"&measStartDat="
        f"&measEndDat="
        f"&DatePicker={date_picker}"
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        page.goto(
            taric_url,
            timeout=60000
        )

        page.wait_for_timeout(5000)

        tables = page.locator("table")

        print("=" * 80)
        print("TARIC URL")
        print(taric_url)

        print("=" * 80)
        print("TABLES FOUND")
        print(tables.count())

        table_data = []

        for i in range(tables.count()):

            try:

                table_text = (
                    tables.nth(i)
                    .inner_text()
                )

                table_data.append(
                    {
                        "table_number": i,
                        "content": table_text[:5000]
                    }
                )

            except Exception:
                pass

        browser.close()

        return {
            "success": True,
            "taric_url": taric_url,
            "tables_found": tables.count(),
            "tables": table_data
        }