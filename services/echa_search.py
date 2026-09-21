from playwright.sync_api import sync_playwright
import streamlit as st


def search_echa(cas_number):
    st.write("Launching browser...")
    results = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        st.write("Browser launched")
        page = browser.new_page()
        

        page.goto(
            "https://chem.echa.europa.eu/",
            timeout=60000
        )
        st.write("ECHA loaded")

        page.wait_for_timeout(3000)

        # legal notice accepteren
        try:
            page.locator(
                'label[for="legal-notice"]'
            ).click()

            page.wait_for_timeout(1000)

        except Exception:
            pass

        # zoeken
        search_field = page.locator(
            'input[name="searchText"]'
        )

        st.write("Search field found")

        search_field.fill(
            cas_number
        )

        search_field.press("Enter")

        page.wait_for_timeout(5000)

        rows = page.locator("table tbody tr")

        count = rows.count()

        for i in range(count):

            row = rows.nth(i)

            cells = row.locator("td")

            if cells.count() < 3:
                continue

            try:

                name = cells.nth(0).inner_text().strip()

                ec_number = cells.nth(1).inner_text().strip()

                cas = cells.nth(2).inner_text().strip()

                link = row.locator("a").first

                url = link.get_attribute("href")

                results.append(
                    {
                        "Name": name,
                        "EC Number": ec_number,
                        "CAS Number": cas,
                        "URL": url
                    }
                )

            except Exception:
                continue

        browser.close()

    return results