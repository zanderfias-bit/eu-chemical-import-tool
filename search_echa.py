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

    # Zoeken
    search_field = page.locator(
        'input[name="searchText"]'
    )

    search_field.fill(
        CAS_NUMBER
    )

    search_field.press("Enter")

    page.wait_for_timeout(8000)

    print("PAGE TITLE:")
    print(page.title())

    print("\nTABLES FOUND:")

    tables = page.locator("table")

    print(
        f"Number of tables: {tables.count()}"
    )

    for i in range(tables.count()):

        print("")
        print("=" * 40)
        print(f"TABLE {i}")
        print("=" * 40)

        try:

            text = tables.nth(i).inner_text()

            print(text[:5000])

        except Exception as error:

            print(error)

    input(
        "\nPress ENTER to close..."
    )

    browser.close()