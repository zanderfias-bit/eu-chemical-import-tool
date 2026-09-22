from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


ECHA_URL = "https://chem.echa.europa.eu/"


def search_echa(cas_number):
    results = []

    with sync_playwright() as playwright:
        browser = None
        context = None

        try:
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )

            browser.on(
                "disconnected",
                lambda _: print("EVENT: Browser disconnected")
            )

            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )

            context.on(
                "close",
                lambda _: print("EVENT: Browser context closed")
            )

            page = context.new_page()

            page.on(
                "close",
                lambda _: print("EVENT: Page closed")
            )

            page.on(
                "crash",
                lambda _: print("EVENT: Page crashed")
            )
            

            context = browser.new_context(
                viewport={
                    "width": 1280,
                    "height": 900,
                },
                locale="en-US",
            )

            page = context.new_page()

            response = page.goto(
                ECHA_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            if response is not None and response.status >= 400:
                raise RuntimeError(
                    f"ECHA returned HTTP status {response.status}."
                )

            # Accept the legal notice if it is displayed.
            try:
                legal_notice = page.locator(
                    'label[for="legal-notice"]'
                )

                if legal_notice.count() > 0:
                    legal_notice.first.click(
                        timeout=10000
                    )

            except PlaywrightError:
                # The legal notice may already have been accepted.
                pass

            search_field = page.locator(
                'input[name="searchText"]'
            )

            search_field.wait_for(
                state="visible",
                timeout=30000,
            )

            search_field.fill(cas_number)
            search_field.press("Enter")

            rows = page.locator("table tbody tr")

            try:
                rows.first.wait_for(
                    state="visible",
                    timeout=30000,
                )
            except PlaywrightTimeoutError:
                return []

            row_count = rows.count()

            for index in range(row_count):
                row = rows.nth(index)
                cells = row.locator("td")

                if cells.count() < 3:
                    continue

                try:
                    name = (
                        cells.nth(0)
                        .inner_text()
                        .strip()
                    )

                    ec_number = (
                        cells.nth(1)
                        .inner_text()
                        .strip()
                    )

                    found_cas = (
                        cells.nth(2)
                        .inner_text()
                        .strip()
                    )

                    link = row.locator("a").first
                    relative_url = link.get_attribute("href")

                    if not relative_url:
                        continue

                    if relative_url.startswith("/"):
                        full_url = (
                            "https://chem.echa.europa.eu"
                            f"{relative_url}"
                        )
                    else:
                        full_url = relative_url

                    results.append(
                        {
                            "Name": name,
                            "EC Number": ec_number,
                            "CAS Number": found_cas,
                            "URL": full_url,
                        }
                    )

                except PlaywrightError:
                    continue

            return results

        except PlaywrightTimeoutError as error:
            raise RuntimeError(
                "ECHA loaded, but the search interface did not "
                "become available."
            ) from error

        except Exception as error:
            raise RuntimeError(
                f"REAL ERROR: {str(error)}"
            ) from error

        finally:
            if context is not None:
                try:
                    context.close()
                except PlaywrightError:
                    pass

            if browser is not None:
                try:
                    browser.close()
                except PlaywrightError:
                    pass