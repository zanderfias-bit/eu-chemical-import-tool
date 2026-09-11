from playwright.sync_api import sync_playwright


def search_echa(cas_number):

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        page.goto(
            "https://chem.echa.europa.eu/",
            timeout=60000
        )

        page.wait_for_timeout(3000)

        # Legal notice accepteren

        page.locator(
            'label[for="legal-notice"]'
        ).click()

        page.wait_for_timeout(1000)

        # Zoeken

        search_field = page.locator(
            'input[name="searchText"]'
        )

        search_field.fill(
            cas_number
        )

        search_field.press("Enter")

        page.wait_for_timeout(8000)

        table = page.locator("table")

        rows = table.locator("tr")

        for i in range(rows.count()):

            print("ROW", i)

            print(
                rows.nth(i).inner_text()
            )

            print("-" * 50)