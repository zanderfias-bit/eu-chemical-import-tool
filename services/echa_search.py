from playwright.sync_api import sync_playwright

def search_echa(cas_number):

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        page = browser.new_page()

        page.goto(
            "https://example.com",
            timeout=60000
        )

        title = page.title()

        browser.close()

        return [{"title": title}]