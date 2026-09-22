import traceback

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_SEARCH_NO_HTML_URL_V7"


# --------------------------------------------------
# BUILD URLS WITHOUT LITERAL URL STRINGS
# --------------------------------------------------
PROTOCOL = "".join(
    [
        "h",
        "t",
        "t",
        "p",
        "s",
        chr(58),
        chr(47),
        chr(47),
    ]
)

ECHA_BASE_URL = "".join(
    [
        PROTOCOL,
        "chem",
        chr(46),
        "echa",
        chr(46),
        "europa",
        chr(46),
        "eu",
    ]
)

ECHA_URL = "".join(
    [
        ECHA_BASE_URL,
        chr(47),
    ]
)


# --------------------------------------------------
# URL VALIDATION
# --------------------------------------------------
def validate_url(name, value):
    forbidden_fragments = (
        "<",
        ">",
        "href=",
        "target=",
        "fai-ChatInputEntity",
        "&quot;",
        "&gt;",
        "&lt;",
    )

    for fragment in forbidden_fragments:
        if fragment in value:
            raise ValueError(
                f"{name} contains copied HTML: {value!r}"
            )

    if not value.startswith(PROTOCOL):
        raise ValueError(
            f"{name} is not a valid HTTPS address: {value!r}"
        )


validate_url(
    "ECHA_BASE_URL",
    ECHA_BASE_URL,
)

validate_url(
    "ECHA_URL",
    ECHA_URL,
)


# --------------------------------------------------
# ECHA SEARCH
# --------------------------------------------------
def search_echa(cas_number):
    """
    Search ECHA CHEM using a CAS number.

    Returns:
        A list of matching substances.

    Raises:
        RuntimeError:
            If Chromium cannot start, the browser test fails,
            ECHA cannot be reached, or Chromium closes.
    """

    results = []
    cas_number = str(cas_number).strip()

    browser = None
    context = None
    page = None

    print("=" * 60, flush=True)
    print(f"CODE VERSION: {CODE_VERSION}", flush=True)
    print(f"LOADED MODULE: {__file__}", flush=True)
    print("STARTING ECHA SEARCH", flush=True)
    print(f"CAS NUMBER: {cas_number}", flush=True)
    print(f"ECHA URL VALUE: {ECHA_URL!r}", flush=True)
    print("=" * 60, flush=True)

    try:
        with sync_playwright() as playwright:
            try:
                # --------------------------------------------------
                # LAUNCH CHROMIUM
                # --------------------------------------------------
                print(
                    "CHECKPOINT 1: Launching Chromium",
                    flush=True,
                )

                browser = playwright.chromium.launch(
                    headless=True,
                    chromium_sandbox=False,
                    args=[
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--disable-extensions",
                        "--disable-background-networking",
                        "--disable-background-timer-throttling",
                        "--disable-renderer-backgrounding",
                    ],
                )

                print(
                    "CHECKPOINT 2: Chromium started",
                    flush=True,
                )

                browser.on(
                    "disconnected",
                    lambda _: print(
                        "PLAYWRIGHT EVENT: Browser disconnected",
                        flush=True,
                    ),
                )

                # --------------------------------------------------
                # CREATE BROWSER CONTEXT
                # --------------------------------------------------
                context = browser.new_context(
                    viewport={
                        "width": 1280,
                        "height": 900,
                    },
                    locale="en-US",
                )

                print(
                    "CHECKPOINT 3: Browser context created",
                    flush=True,
                )

                context.on(
                    "close",
                    lambda _: print(
                        "PLAYWRIGHT EVENT: Browser context closed",
                        flush=True,
                    ),
                )

                # --------------------------------------------------
                # CREATE PAGE
                # --------------------------------------------------
                page = context.new_page()

                print(
                    "CHECKPOINT 4: Browser page created",
                    flush=True,
                )

                page.on(
                    "close",
                    lambda _: print(
                        "PLAYWRIGHT EVENT: Page closed",
                        flush=True,
                    ),
                )

                page.on(
                    "crash",
                    lambda _: print(
                        "PLAYWRIGHT EVENT: Page crashed",
                        flush=True,
                    ),
                )

                # --------------------------------------------------
                # BUILD BROWSER TEST ADDRESS LOCALLY
                # --------------------------------------------------
                browser_test_url = "".join(
                    [
                        "h",
                        "t",
                        "t",
                        "p",
                        "s",
                        chr(58),
                        chr(47),
                        chr(47),
                        "w",
                        "w",
                        "w",
                        chr(46),
                        "g",
                        "o",
                        "o",
                        "g",
                        "l",
                        "e",
                        chr(46),
                        "c",
                        "o",
                        "m",
                        chr(47),
                    ]
                )

                validate_url(
                    "browser_test_url",
                    browser_test_url,
                )

                print(
                    "CHECKPOINT 5: Opening browser test page",
                    flush=True,
                )

                print(
                    "BROWSER TEST VALUE:",
                    repr(browser_test_url),
                    flush=True,
                )

                # --------------------------------------------------
                # TEST CHROMIUM NAVIGATION
                # --------------------------------------------------
                test_response = page.goto(
                    browser_test_url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

                print(
                    "CHECKPOINT 6: Browser test navigation completed",
                    flush=True,
                )

                print(
                    f"BROWSER TEST URL: {page.url}",
                    flush=True,
                )

                print(
                    f"BROWSER TEST TITLE: {page.title()}",
                    flush=True,
                )

                print(
                    f"PAGE CLOSED: {page.is_closed()}",
                    flush=True,
                )

                print(
                    "BROWSER CONNECTED: "
                    f"{browser.is_connected()}",
                    flush=True,
                )

                if test_response is not None:
                    print(
                        "BROWSER TEST HTTP STATUS: "
                        f"{test_response.status}",
                        flush=True,
                    )

                    if test_response.status >= 400:
                        raise RuntimeError(
                            "The browser test returned HTTP status "
                            f"{test_response.status}."
                        )

                if page.is_closed():
                    raise RuntimeError(
                        "Chromium started, but the page closed "
                        "during the browser test."
                    )

                if not browser.is_connected():
                    raise RuntimeError(
                        "Chromium started, but disconnected "
                        "during the browser test."
                    )

                # --------------------------------------------------
                # OPEN ECHA
                # --------------------------------------------------
                print(
                    "CHECKPOINT 7: Opening ECHA",
                    flush=True,
                )

                response = page.goto(
                    ECHA_URL,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                print(
                    "CHECKPOINT 8: ECHA navigation completed",
                    flush=True,
                )

                print(
                    f"ECHA CURRENT URL: {page.url}",
                    flush=True,
                )

                print(
                    f"ECHA PAGE TITLE: {page.title()}",
                    flush=True,
                )

                print(
                    f"PAGE CLOSED: {page.is_closed()}",
                    flush=True,
                )

                print(
                    "BROWSER CONNECTED: "
                    f"{browser.is_connected()}",
                    flush=True,
                )

                if response is not None:
                    print(
                        f"ECHA HTTP STATUS: {response.status}",
                        flush=True,
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
                        "after opening ECHA."
                    )

                # --------------------------------------------------
                # ACCEPT LEGAL NOTICE
                # --------------------------------------------------
                print(
                    "CHECKPOINT 9: Checking legal notice",
                    flush=True,
                )

                try:
                    legal_notice_checkbox = page.locator(
                        'label[for="legal-notice"]'
                    )

                    legal_notice_count = (
                        legal_notice_checkbox.count()
                    )

                    print(
                        "LEGAL NOTICE CHECKBOX COUNT: "
                        f"{legal_notice_count}",
                        flush=True,
                    )

                    if legal_notice_count > 0:
                        if (
                            legal_notice_checkbox
                            .first
                            .is_visible()
                        ):
                            legal_notice_checkbox.first.click(
                                timeout=10000
                            )

                            print(
                                "Legal notice checkbox clicked",
                                flush=True,
                            )

                    accept_button = page.get_by_text(
                        "I Accept the terms",
                        exact=False,
                    )

                    accept_button_count = (
                        accept_button.count()
                    )

                    print(
                        "ACCEPT BUTTON COUNT: "
                        f"{accept_button_count}",
                        flush=True,
                    )

                    if accept_button_count > 0:
                        if accept_button.first.is_visible():
                            accept_button.first.click(
                                timeout=10000
                            )

                            print(
                                "Legal notice accept button clicked",
                                flush=True,
                            )

                    page.wait_for_timeout(1000)

                except PlaywrightTimeoutError as error:
                    print(
                        "LEGAL NOTICE TIMEOUT:",
                        repr(error),
                        flush=True,
                    )

                except PlaywrightError as error:
                    print(
                        "LEGAL NOTICE PLAYWRIGHT ERROR:",
                        repr(error),
                        flush=True,
                    )

                # --------------------------------------------------
                # VERIFY BROWSER STATE
                # --------------------------------------------------
                if page.is_closed():
                    raise RuntimeError(
                        "The ECHA page closed before the "
                        "search field could be located."
                    )

                if not browser.is_connected():
                    raise RuntimeError(
                        "Chromium disconnected before the "
                        "search field could be located."
                    )

                # --------------------------------------------------
                # FIND SEARCH FIELD
                # --------------------------------------------------
                print(
                    "CHECKPOINT 10: Waiting for ECHA search field",
                    flush=True,
                )

                search_field = page.locator(
                    'input[name="searchText"]'
                ).first

                search_field.wait_for(
                    state="visible",
                    timeout=30000,
                )

                print(
                    "CHECKPOINT 11: ECHA search field visible",
                    flush=True,
                )

                # --------------------------------------------------
                # EXECUTE SEARCH
                # --------------------------------------------------
                search_field.fill(cas_number)

                print(
                    "CHECKPOINT 12: CAS number entered",
                    flush=True,
                )

                search_field.press("Enter")

                print(
                    "CHECKPOINT 13: ECHA search submitted",
                    flush=True,
                )

                # --------------------------------------------------
                # WAIT FOR RESULTS
                # --------------------------------------------------
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
                        "rows became visible.",
                        flush=True,
                    )

                    return []

                # --------------------------------------------------
                # EXTRACT RESULTS
                # --------------------------------------------------
                row_count = rows.count()

                print(
                    f"ECHA RESULT ROW COUNT: {row_count}",
                    flush=True,
                )

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

                    except PlaywrightError as error:
                        print(
                            "COULD NOT PROCESS ECHA RESULT "
                            f"ROW {index}:",
                            repr(error),
                            flush=True,
                        )

                        continue

                print(
                    "ECHA SEARCH COMPLETED SUCCESSFULLY",
                    flush=True,
                )

                print(
                    f"RESULTS FOUND: {len(results)}",
                    flush=True,
                )

                return results

            # --------------------------------------------------
            # PLAYWRIGHT ERROR
            # --------------------------------------------------
            except PlaywrightError as error:
                error_name = type(error).__name__

                print("=" * 60, flush=True)

                print(
                    f"PLAYWRIGHT ERROR TYPE: {error_name}",
                    flush=True,
                )

                print(
                    f"PLAYWRIGHT ERROR: {repr(error)}",
                    flush=True,
                )

                traceback.print_exc()

                if page is not None:
                    try:
                        print(
                            f"PAGE CLOSED: {page.is_closed()}",
                            flush=True,
                        )
                    except Exception:
                        print(
                            "PAGE STATE COULD NOT BE READ",
                            flush=True,
                        )

                if browser is not None:
                    try:
                        print(
                            "BROWSER CONNECTED: "
                            f"{browser.is_connected()}",
                            flush=True,
                        )
                    except Exception:
                        print(
                            "BROWSER STATE COULD NOT BE READ",
                            flush=True,
                        )

                print("=" * 60, flush=True)

                if error_name == "TargetClosedError":
                    raise RuntimeError(
                        "Chromium closed unexpectedly. "
                        "The Streamlit Cloud logs contain "
                        "the last completed checkpoint."
                    ) from error

                if isinstance(
                    error,
                    PlaywrightTimeoutError,
                ):
                    raise RuntimeError(
                        "The browser or ECHA page did not "
                        "respond within the allowed time."
                    ) from error

                raise RuntimeError(
                    "The browser encountered an error while "
                    "searching ECHA."
                ) from error

            # --------------------------------------------------
            # APPLICATION ERROR
            # --------------------------------------------------
            except RuntimeError:
                traceback.print_exc()
                raise

            except Exception as error:
                print("=" * 60, flush=True)

                print(
                    "UNEXPECTED ERROR:",
                    repr(error),
                    flush=True,
                )

                traceback.print_exc()

                print("=" * 60, flush=True)

                raise RuntimeError(
                    "An unexpected error occurred while "
                    "searching ECHA."
                ) from error

            # --------------------------------------------------
            # CLEANUP
            # --------------------------------------------------
            finally:
                print(
                    "STARTING BROWSER CLEANUP",
                    flush=True,
                )

                if context is not None:
                    try:
                        context.close()

                        print(
                            "CONTEXT CLOSED DURING CLEANUP",
                            flush=True,
                        )

                    except PlaywrightError as error:
                        print(
                            "CONTEXT CLEANUP ERROR:",
                            repr(error),
                            flush=True,
                        )

                if browser is not None:
                    try:
                        browser.close()

                        print(
                            "BROWSER CLOSED DURING CLEANUP",
                            flush=True,
                        )

                    except PlaywrightError as error:
                        print(
                            "BROWSER CLEANUP ERROR:",
                            repr(error),
                            flush=True,
                        )

    except RuntimeError:
        raise

    except Exception as error:
        print(
            "ERROR OUTSIDE PLAYWRIGHT CONTEXT:",
            repr(error),
            flush=True,
        )

        traceback.print_exc()

        raise RuntimeError(
            "The Playwright service could not be started."
        ) from error