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


def get_taric(goods_code, country, cas_number):

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
        # --------------------------------------------------
        # GET PAGE CONTENT
        # --------------------------------------------------

        body_text = page.locator("body").inner_text()

        print("=" * 80)
        print("SEARCHING CAS")
        print(cas_number)

        # --------------------------------------------------
        # FIND GOODS CODE LINK
        # --------------------------------------------------

        body_text = page.locator("body").inner_text()

        result = {
            "success": True,
            "body_text": body_text,
            "taric_url": page.url
        }

        browser.close()

        return {
            "success": True,
            "taric_url": taric_url,
            "goods_code": goods_code,
            "country": country
        }

        links_found = links.count()

        print("=" * 80)
        print("ALL LINKS FOUND")
        print("=" * 80)

        for i in range(links_found):

            try:

                text = links.nth(i).inner_text().strip()

                href = links.nth(i).get_attribute("href")

                if text:

                    print(
                        f"{i} | {text}"
                    )

                    print(
                        f"HREF: {href}"
                    )

                    print("-" * 40)

            except Exception as e:

                print(e)

        selected_link = None
        selected_code = None

        # eerst alle links met goederencodes verzamelen
        goods_links = []

        for i in range(links_found):

            try:

                text = links.nth(i).inner_text().strip()

                # voorbeeld:
                # 2917 19 80 55
                # 2917 19 80 90

                if text and text[0].isdigit():

                    goods_links.append(
                        {
                            "index": i,
                            "code": text,
                            "locator": links.nth(i)
                        }
                    )

            except Exception:
                pass

        # --------------------------------------------------
        # ZOEK CAS IN PAGINA
        # --------------------------------------------------

        cas_found = False

        for i in range(links_found):

            try:

                text = links.nth(i).inner_text()

                if cas_number in text:

                    cas_found = True

                    print(
                        f"CAS FOUND IN: {text}"
                    )

                    # neem de vorige goederencode
                    for g in reversed(goods_links):

                        if g["index"] < i:

                            selected_link = g["locator"]

                            selected_code = g["code"]

                            break

                    break

            except Exception:
                pass

        # --------------------------------------------------
        # CAS NIET GEVONDEN
        # GEBRUIK LAATSTE 'OTHER'
        # --------------------------------------------------

        if selected_link is None:

            print(
                "CAS NOT FOUND - USING LAST OTHER"
            )

            for i in range(links_found):

                try:

                    text = links.nth(i).inner_text().strip()

                    if text.lower() == "other":

                        # neem voorgaande goederenlink
                        for g in reversed(goods_links):

                            if g["index"] < i:

                                selected_link = g["locator"]

                                selected_code = g["code"]

                                break

                except Exception:
                    pass

        # --------------------------------------------------
        # OPEN TARIC DETAIL
        # --------------------------------------------------

        if selected_link is not None:

            print(
                f"CLICKING {selected_code}"
            )

            selected_link.click()

            page.wait_for_timeout(5000)

            measure_text = page.locator(
                "body"
            ).inner_text()

            result = {
                "success": True,
                "selected_taric_code": selected_code,
                "taric_url": page.url,
                "measure_text": measure_text
            }

        else:

            result = {
                "success": False,
                "message":
                    "No matching CAS or Other entry found"
            }

        browser.close()

        return result

