from playwright.sync_api import sync_playwright


def get_goods_code(ec_number):

    url = (
        "https://ec.europa.eu/taxation_customs/dds2/ecics/"
        "chemicalsubstance_consultation.jsp"
        f"?Lang=en"
        f"&Cas="
        f"&Cus="
        f"&CnCode="
        f"&EcCode={ec_number}"
        f"&UnCode="
        f"&Name="
        f"&LangNm=en"
        f"&NomenclatureSystem="
        f"&Inchi="
        f"&Inchikey="
        f"&Characteristic="
        f"&sortOrder=1"
        f"&Expand=true"
        f"&offset=0"
        f"&viewVal="
        f"&isVisitedRef=true"
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        page.goto(
            url,
            timeout=60000
        )

        page.wait_for_timeout(5000)

        tables = page.locator("table")

        if tables.count() < 3:

            browser.close()

            return {
                "success": False,
                "message": "ECICS result table not found"
            }

        # TABLE 2 bevat de gewenste data
        table = tables.nth(2)

        rows = table.locator("tr")

        goods_code = None
        cus_number = None
        cas_number = None
        substance_name = None

        # eerste data-rij na de header
        for i in range(1, rows.count()):

            try:

                cells = rows.nth(i).locator("td")

                if cells.count() < 6:
                    continue

                cus_number = (
                    cells.nth(0)
                    .inner_text()
                    .strip()
                )

                goods_code = (
                    cells.nth(1)
                    .inner_text()
                    .strip()
                )

                cas_number = (
                    cells.nth(2)
                    .inner_text()
                    .strip()
                )

                ec_result = (
                    cells.nth(3)
                    .inner_text()
                    .strip()
                )

                substance_name = (
                    cells.nth(5)
                    .inner_text()
                    .strip()
                )

                browser.close()

                return {
                    "success": True,
                    "ec_number": ec_result,
                    "goods_code": goods_code,
                    "cus_number": cus_number,
                    "cas_number": cas_number,
                    "substance_name": substance_name,
                    "url": url
                }

            except Exception as e:

                print(e)

        browser.close()

        return {
            "success": False,
            "message": "No matching record found"
        }