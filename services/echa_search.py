from playwright.sync_api import (
    Error as PlaywrightError,
    TargetClosedError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


ECHA_URL = "https://chem.echa.europa.eu/"
ECHA_BASE_URL = "https://chem.echa.europa.eu"


def search_echa(cas_number):
    """
    Search ECHA CHEM using a CAS number.

    Returns:
        list[dict\]: Matching substances.

    Raises:
        RuntimeError: If ECHA cannot be reached or Chromium closes.
    """

    results = []
    cas_number = str(cas_number).strip()

    with sync_playwright() as playwright:
        browser = None
        context = None
        page = None

        try:
            # --------------------------------------------------
            # LAUNCH CHROMIUM
            # --------------------------------------------------
            browser = playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )

            # Temporary diagnostic logging for Streamlit Cloud.
            browser.on(
                "disconnected",
                lambda _: print(
                    "PLAYWRIGHT EVENT: Browser disconnected"
                ),
            )

            # --------------------------------------------------
            # CREATE ONE CONTEXT AND ONE PAGE
            # --------------------------------------------------
            context = browser.new_context(
                viewport={
                    "width": 1280,
                    "height": 900,
                },
                locale="en-US",
            )

            context.on(
                "close",
                lambda _: print(
                    "PLAYWRIGHT EVENT: Browser context closed"
                ),
            )

            page = context.new_page()

            page.on(
                "close",
                lambda _: print(
                    "PLAYWRIGHT EVENT: Page closed"
                ),
            )

            page.on(
                "crash",
                lambda _: print(
                    "PLAYWRIGHT EVENT: Page crashed"
                ),
            )

            # --------------------------------------------------
            # OPEN ECHA
            # --------------------------------------------------
            response = page.goto(
                ECHA_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            print("ECHA navigation completed")
            print("Current URL:", page.url)
            print("Page closed:", page.is_closed())
            print(
                "Browser connected:",
                browser.is_connected(),
            )

            if response is not None:
                print(
                    "ECHA HTTP status:",
                    response.status,
                )

                if response.status >= 400:
                    raise RuntimeError(
                        "ECHA returned HTTP status "
                        f"{response.status}."
                    )

            if page.is_closed():
                raise RuntimeError(
                    "The ECHA page closed immediately "
                    "after navigation."
                )

            if not browser.is_connected():
                raise RuntimeError(
                    "Chromium disconnected immediately "
                    "after navigation."
                )

            # --------------------------------------------------
            # ACCEPT LEGAL NOTICE
            # --------------------------------------------------
            try:
                legal_notice_checkbox = page.locator(
                    'label[for="legal-notice"]'
                )

                if legal_notice_checkbox.count() > 0:
                    if legal_notice_checkbox.first.is_visible():
                        legal_notice_checkbox.first.click(
                            timeout=10000
                        )

                accept_button = page.get_by_text(
                    "I Accept the terms",
                    exact=False,
                )

                if accept_button.count() > 0:
                    if accept_button.first.is_visible():
                        accept_button.first.click(
                            timeout=10000
                        )

                page.wait_for_timeout(1000)

            except PlaywrightTimeoutError:
                print(
                    "Legal notice was found, but could "
                    "not be accepted within the timeout."
                )

            except PlaywrightError as error:
                print(
                    "Legal notice handling skipped:",
                    repr(error),
                )

            # --------------------------------------------------
            # FIND SEARCH FIELD
            # --------------------------------------------------
            search_field = page.locator(
                'input[name="searchText"]'
            ).first

            search_field.wait_for(
                state="visible",
                timeout=30000,
            )

            if page.is_closed():
                raise RuntimeError(
                    "The ECHA page closed before the "
                    "search could be submitted."
                )

            # --------------------------------------------------
            # EXECUTE SEARCH
            # --------------------------------------------------
            search_field.fill(cas_number)
            search_field.press("Enter")

            # Wait for either results or the page to settle.
            page.wait_for_load_state(
                "domcontentloaded",
                timeout=30000,
            )

            rows = page.locator(
                "table tbody tr"
            )

            try:
                rows.first.wait_for(
                    state="visible",
                    timeout=30000,
                )

            except PlaywrightTimeoutError:
                print(
                    "ECHA search completed, but no result "
                    "rows became visible."
                )

                return []

            # --------------------------------------------------
            # EXTRACT RESULTS
            # --------------------------------------------------
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
                    relative_url = link.get_attribute(
                        "href"
                    )

                    if not relative_url:
                        continue

                    if relative_url.startswith("/"):
                        full_url = (
                            f"{ECHA_BASE_URL}"
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

                except PlaywrightError as error:
                    print(
                        "Could not process ECHA result "
                        f"row {index}:",
                        repr(error),
                    )

                    continue

            return results

        # --------------------------------------------------
        # TARGET CLOSED
        # --------------------------------------------------
        except TargetClosedError as error:
            page_was_closed = (
                page.is_closed()
                if page is not None
                else True
            )

            browser_was_connected = (
                browser.is_connected()
                if browser is not None
                else False
            )

            print(
                "ECHA TARGET CLOSED ERROR:",
                repr(error),
            )

            print(
                "Page closed:",
                page_was_closed,
            )

            print(
                "Browser connected:",
                browser_was_connected,
            )

            raise RuntimeError(
                "Chromium closed unexpectedly while "
                "searching ECHA. Check the Streamlit "
                "Cloud logs for the browser event that "
                "occurred immediately before this error."
            ) from error

        # --------------------------------------------------
        # TIMEOUT
        # --------------------------------------------------
        except PlaywrightTimeoutError as error:
            print(
                "ECHA TIMEOUT ERROR:",
                repr(error),
            )

            raise RuntimeError(
                "ECHA loaded, but the search interface "
                "did not become available."
            ) from error

        # --------------------------------------------------
        # OTHER PLAYWRIGHT ERROR
        # --------------------------------------------------
        except PlaywrightError as error:
            print(
                "ECHA PLAYWRIGHT ERROR:",
                repr(error),
            )

            raise RuntimeError(
                "The browser encountered an error while "
                "searching ECHA."
            ) from error

        # --------------------------------------------------
        # APPLICATION OR HTTP ERROR
        # --------------------------------------------------
        except RuntimeError:
            raise

        except Exception as error:
            print(
                "ECHA UNEXPECTED ERROR:",
                repr(error),
            )

            raise RuntimeError(
                "An unexpected error occurred while "
                "searching ECHA."
            ) from error

        # --------------------------------------------------
        # CLEANUP
        # --------------------------------------------------
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