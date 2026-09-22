from playwright.sync_api import sync_playwright
import re


def get_echa_detail(relative_url, cas_number):

    # --------------------------------------------------
    # EXTRACT SUBSTANCE ID
    # --------------------------------------------------

    match = re.search(
        r"(\d+\.\d+\.\d+)",
        relative_url
    )

    if not match:

        raise Exception(
            "Could not extract substance ID from URL"
        )

    substance_id = match.group(1)

    # --------------------------------------------------
    # BUILD REACH REGISTRATION URL
    # --------------------------------------------------

    reach_url = (
        f"https://chem.echa.europa.eu/"
        f"{substance_id}"
        f"/dossier-list/reach/asset-owner"
        f"?searchText={cas_number}"
        f"&pageIndex=1"
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page()

        # --------------------------------------------------
        # OPEN REACH PAGE
        # --------------------------------------------------

        page.goto(
            reach_url,
            timeout=60000
        )

        page.wait_for_timeout(3000)

        # --------------------------------------------------
        # ACCEPT LEGAL NOTICE
        # --------------------------------------------------

        try:

            accept_button = page.get_by_text(
                "I Accept the terms",
                exact=False
            )

            if accept_button.count() > 0:


                accept_button.first.click()

                page.wait_for_timeout(5000)

        except Exception as e:

            print(
                "No legal notice found"
            )

            print(e)

        # --------------------------------------------------
        # PAGE DEBUG
        # --------------------------------------------------

        print("=" * 60)
        print("CURRENT URL")
        print(page.url)

        print("=" * 60)
        print("PAGE TITLE")
        print(page.title())

        # --------------------------------------------------
        # CAPTURE BODY TEXT
        # --------------------------------------------------

        body_text = page.locator(
            "body"
        ).inner_text()

        print("=" * 60)
        print("BODY START")
        print(body_text[:5000])

        # --------------------------------------------------
        # FIND TABLES
        # --------------------------------------------------

        tables = page.locator("table")

        print("=" * 60)
        print(
            "TABLES FOUND:",
            tables.count()
        )

        for t in range(tables.count()):

            try:

                print("=" * 60)
                print(
                    f"TABLE {t}"
                )

                print(
                    tables.nth(t)
                    .inner_text()[:3000]
                )

            except Exception as e:

                print(e)
        
        # --------------------------------------------------
        # EXTRACT REGISTRANTS TABLE
        # --------------------------------------------------

        registrants = []

        table = page.locator("table").first

        rows = table.locator("tr")

        for i in range(1, rows.count()):  # skip header

            try:

                cells = rows.nth(i).locator("td")

                if cells.count() < 4:
                    continue

                registrants.append({
                    "Registrant": cells.nth(0).inner_text().strip(),
                    "Address": cells.nth(1).inner_text().strip(),
                    "Status": cells.nth(2).inner_text().strip(),
                    "Details": cells.nth(3).inner_text().strip()
                })

            except Exception as e:

                print(
                    f"Error row {i}: {e}"
                )
        # --------------------------------------------------
        # RETURN RESULT
        # --------------------------------------------------

        result = {
            "url": page.url,
            "title": page.title(),
            "registrants": registrants
        }

        browser.close()

        return result