from playwright.sync_api import sync_playwright


def get_echa_detail(relative_url):

    full_url = (
        "https://chem.echa.europa.eu"
        + relative_url
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page()

        page.goto(
            full_url,
            timeout=60000
        )

        page.wait_for_timeout(5000)

        title = page.title()

        body_text = page.locator(
            "body"
        ).inner_text()

        browser.close()

        return {
            "url": full_url,
            "title": title,
            "body_text": body_text
        }