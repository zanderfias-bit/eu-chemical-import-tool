from playwright.sync_api import sync_playwright


def lookup_echa(cas_number):

    result = {
        "cas_number": cas_number,
        "substance_name": None,
        "ec_number": None,
        "list_number": None,
        "status": "unknown",
        "message": ""
    }

    try:

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=False
            )

            page = browser.new_page()

            page.goto(
                "https://chem.echa.europa.eu/",
                timeout=60000
            )

            page.wait_for_timeout(1500)

            print("Titel:")
            print(page.title())

            result["substance_name"] = page.title()
            result["status"] = "success"
            result["list_number"] = "Not yet extracted"
            result["message"] = "ECHA website geopend"

            browser.close()

    except Exception as error:

        result["status"] = "error"
        result["message"] = str(error)

    return result