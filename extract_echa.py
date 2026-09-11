from playwright.sync_api import sync_playwright

CAS_NUMBER = "110-94-1"

with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False
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

    # CAS zoeken
    search_field = page.locator(
        'input[name="searchText"]'
    )

    search_field.fill(CAS_NUMBER)

    search_field.press("Enter")

    page.wait_for_timeout(8000)

    table = page.locator("table")

    table_text = table.inner_text()

    print("")
    print("RESULT TABLE")
    print("")
    print(table_text)

    browser.close()