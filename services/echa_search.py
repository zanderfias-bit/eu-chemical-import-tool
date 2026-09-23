import traceback

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_SEARCH_MINIMAL_V8"


# --------------------------------------------------
# BUILD URLS
# --------------------------------------------------
# De URL wordt uit delen opgebouwd om te voorkomen dat
# een chatinterface de URL omzet in HTML tijdens het kopiëren.
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

ECHA_URL = ECHA_BASE_URL + chr(47)


# --------------------------------------------------
# URL VALIDATION
# --------------------------------------------------
def validate_url(name, value):
    """
    Controleert of een URL geen gekopieerde HTML bevat.
    """

    forbidden_fragments = (
        "<",
        ">",
        "href=",
        "target=",
        "fai-ChatInputEntity",
        "&lt;",
        "&gt;",
        "&quot;",
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


validate_url("ECHA_BASE_URL", ECHA_BASE_URL)
validate_url("ECHA_URL", ECHA_URL)


# --------------------------------------------------
# ECHA SEARCH
# --------------------------------------------------
def search_echa(cas_number):
    """
    Search ECHA CHEM using a CAS number.

    Returns:
        A list of dictionaries with:
        - Name
        - EC Number
        - CAS Number
        - URL

    Raises:
        RuntimeError:
            If Chromium cannot start, ECHA cannot be reached,
            or the browser closes unexpectedly.
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
                    ],
                )

                print(
                    "CHECKPOINT 2: Chromium started",
                    flush=True,
                )
                print(
                    f"CHROMIUM VERSION: {browser.version}",
                    flush=True,
                )
                print(
                    "PLAYWRIGHT CHROMIUM EXECUTABLE: "
                    f"{playwright.chromium.executable_path}",
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

                page.on(
                    "pageerror",
                    lambda error: print(
                        "PLAYWRIGHT EVENT: Page JavaScript error: "
                        f"{error}",
                        flush=True,
                    ),
                )

                # --------------------------------------------------
                # OPEN ECHA DIRECTLY
                # --------------------------------------------------
                print(
                    "CHECKPOINT 5: Opening ECHA",
                    flush=True,
                )

                response = page.goto(
                    ECHA_URL,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                print(
                    "CHECKPOINT 6: ECHA navigation completed",
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
                    f"PAGE CLOSED AFTER NAVIGATION: "
                    f"{page.is_closed()}",
                    flush=True,
                )
                print(
                    "BROWSER CONNECTED AFTER NAVIGATION: "
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
                # WAIT FOR ECHA APPLICATION
                # --------------------------------------------------
                print(
                    "CHECKPOINT 7: Waiting for ECHA application",
                    flush=True,
                )

                page.wait_for_timeout(3000)

                # --------------------------------------------------
                # ACCEPT LEGAL NOTICE
                # --------------------------------------------------
                print(
                    "CHECKPOINT 8: Checking legal notice",
                    flush=True,
                )

                try:
                    accept_button = page.get_by_text(
                        "I Accept the terms",
                        exact=False,
                    ).first

                    if accept_button.is_visible(timeout=5000):
                        accept_button.click(timeout=10000)

                        print(
                            "LEGAL NOTICE ACCEPTED",
                            flush=True,
                        )

                        page.wait_for_timeout(2000)

                except PlaywrightTimeoutError:
                    print(
                        "NO VISIBLE LEGAL NOTICE",
                        flush=True,
                    )

                except PlaywrightError as error:
                    print(
                        "LEGAL NOTICE COULD NOT BE PROCESSED: "
                        f"{repr(error)}",
                        flush=True,
                    )

                # --------------------------------------------------
                # VERIFY BROWSER STATE
                # --------------------------------------------------
                print(
                    f"PAGE CLOSED BEFORE SEARCH: "
                    f"{page.is_closed()}",
                    flush=True,
                )
                print(
                    "BROWSER CONNECTED BEFORE SEARCH: "
                    f"{browser.is_connected()}",
                    flush=True,
                )

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
                    "CHECKPOINT 9: Locating ECHA search field",
                    flush=True,
                )

                search_field = page.locator(
                    'input[name="searchText"]'
                ).first

                print(
                    "CHECKPOINT 10: Waiting for search field "
                    "to be attached",
                    flush=True,
                )

                search_field.wait_for(
                    state="attached",
                    timeout=60000,
                )

                print(
                    "CHECKPOINT 11: Search field attached",
                    flush=True,
                )

                search_field.wait_for(
                    state="visible",
                    timeout=60000,
                )

                print(
                    "CHECKPOINT 12: Search field visible",
                    flush=True,
                )

                print(
                    f"PAGE CLOSED BEFORE FILL: "
                    f"{page.is_closed()}",
                    flush=True,
                )
                print(
                    "BROWSER CONNECTED BEFORE FILL: "
                    f"{browser.is_connected()}",
                    flush=True,
                )

                if page.is_closed():
                    raise RuntimeError(
                        "The ECHA page closed immediately "
                        "before entering the CAS number."
                    )

                if not browser.is_connected():
                    raise RuntimeError(
                        "Chromium disconnected immediately "
                        "before entering the CAS number."
                    )

                # --------------------------------------------------
                # EXECUTE SEARCH
                # --------------------------------------------------
                search_field.fill(
                    cas_number,
                    timeout=30000,
                )

                print(
                    "CHECKPOINT 13: CAS number entered",
                    flush=True,
                )

                search_field.press(
                    "Enter",
                    timeout=30000,
                )

                print(
                    "CHECKPOINT 14: ECHA search submitted",
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
                        relative_url = link.get_attribute("href")

                        if not relative_url:
                            continue

                        if relative_url.startswith("/"):
                            full_url = (
                                ECHA_BASE_URL + relative_url
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
                            f"ROW {index}: {repr(error)}",
                            flush=True,
                        )

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
                        "Check the final completed checkpoint "
                        "in the Streamlit Cloud logs."
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
                    "Playwright encountered an error while "
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
                    f"UNEXPECTED ERROR: {repr(error)}",
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
                            "CONTEXT CLEANUP ERROR: "
                            f"{repr(error)}",
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
                            "BROWSER CLEANUP ERROR: "
                            f"{repr(error)}",
                            flush=True,
                        )

    except RuntimeError:
        raise

    except Exception as error:
        print(
            "ERROR OUTSIDE PLAYWRIGHT CONTEXT: "
            f"{repr(error)}",
            flush=True,
        )

        traceback.print_exc()

        raise RuntimeError(
            "The Playwright service could not be started."
        ) from error