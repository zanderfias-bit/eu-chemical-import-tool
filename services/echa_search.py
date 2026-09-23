import os
import traceback

# Browserproceslogging activeren.
# Dit moet vóór de Playwright-import gebeuren.
os.environ.setdefault("DEBUG", "pw:browser")

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_SEARCH_RENDERER_DEBUG_V10"


# --------------------------------------------------
# BUILD ECHA URL SAFELY
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

ECHA_URL = ECHA_BASE_URL + chr(47)


# --------------------------------------------------
# URL VALIDATION
# --------------------------------------------------
def validate_url(name, value):
    """
    Prevent copied HTML from being used as a URL.
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
            f"{name} is not a valid HTTPS URL: {value!r}"
        )


validate_url("ECHA_BASE_URL", ECHA_BASE_URL)
validate_url("ECHA_URL", ECHA_URL)


# --------------------------------------------------
# RESOURCE FILTER
# --------------------------------------------------
def block_unnecessary_resources(route):
    """
    Block only images, media and fonts.

    JavaScript, CSS, documents, XHR and fetch requests
    remain enabled because ECHA CHEM needs them.
    """

    resource_type = route.request.resource_type

    if resource_type in {
        "image",
        "media",
        "font",
    }:
        route.abort()
    else:
        route.continue_()


# --------------------------------------------------
# ECHA SEARCH
# --------------------------------------------------
def search_echa(cas_number):
    """
    Search ECHA CHEM using a CAS number.

    Returns:
        A list of dictionaries containing:
        - Name
        - EC Number
        - CAS Number
        - URL

    Raises:
        RuntimeError:
            If Playwright cannot start, ECHA cannot be reached,
            the ECHA renderer crashes, or Chromium disconnects.
    """

    results = []
    cas_number = str(cas_number).strip()

    if not cas_number:
        return results

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

                chromium_executable = (
                    playwright.chromium.executable_path
                )

                print(
                    f"CHROMIUM EXECUTABLE: {chromium_executable}",
                    flush=True,
                )

                browser = playwright.chromium.launch(
                    executable_path=chromium_executable,
                    headless=True,
                    chromium_sandbox=False,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
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

                browser.on(
                    "disconnected",
                    lambda _: print(
                        "PLAYWRIGHT EVENT: Browser disconnected",
                        flush=True,
                    ),
                )

                # --------------------------------------------------
                # CREATE CONTEXT
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
                        f"BROWSER JAVASCRIPT ERROR: {error}",
                        flush=True,
                    ),
                )

                page.on(
                    "console",
                    lambda message: print(
                        "BROWSER CONSOLE "
                        f"[{message.type}\]: "
                        f"{message.text}",
                        flush=True,
                    ),
                )

                page.on(
                    "requestfailed",
                    lambda request: print(
                        "BROWSER REQUEST FAILED: "
                        f"{request.resource_type} | "
                        f"{request.url} | "
                        f"{request.failure}",
                        flush=True,
                    ),
                )

                # --------------------------------------------------
                # INSTALL RESOURCE FILTER
                # --------------------------------------------------
                page.route(
                    "**/*",
                    block_unnecessary_resources,
                )

                print(
                    "CHECKPOINT 5: Resource filter installed",
                    flush=True,
                )

                # --------------------------------------------------
                # OPEN ECHA
                # --------------------------------------------------
                print(
                    "CHECKPOINT 6: Opening ECHA",
                    flush=True,
                )

                response = page.goto(
                    ECHA_URL,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                print(
                    "CHECKPOINT 7: ECHA navigation completed",
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
                    "PAGE CLOSED AFTER NAVIGATION: "
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
                # INITIAL APPLICATION WAIT
                # --------------------------------------------------
                print(
                    "CHECKPOINT 8: Waiting for ECHA application",
                    flush=True,
                )

                page.wait_for_timeout(3000)

                # --------------------------------------------------
                # LEGAL NOTICE
                # --------------------------------------------------
                # --------------------------------------------------
                # LEGAL NOTICE
                # --------------------------------------------------
                print(
                    "CHECKPOINT 9: Checking legal notice",
                    flush=True,
                )

                try:
                    legal_notice_checkbox = page.locator(
                        'input#legal-notice, '
                        'input[name="legal-notice"]'
                    ).first

                    legal_notice_label = page.locator(
                        'label[for="legal-notice"]'
                    ).first

                    checkbox_count = (
                        legal_notice_checkbox.count()
                    )

                    label_count = (
                        legal_notice_label.count()
                    )

                    print(
                        "LEGAL NOTICE CHECKBOX COUNT: "
                        f"{checkbox_count}",
                        flush=True,
                    )

                    print(
                        "LEGAL NOTICE LABEL COUNT: "
                        f"{label_count}",
                        flush=True,
                    )

                    if (
                        label_count > 0
                        and legal_notice_label.is_visible()
                    ):
                        legal_notice_label.click(
                            timeout=10000
                        )

                        print(
                            "LEGAL NOTICE LABEL CLICKED",
                            flush=True,
                        )

                    elif checkbox_count > 0:
                        if not legal_notice_checkbox.is_checked():
                            legal_notice_checkbox.check(
                                force=True,
                                timeout=10000,
                            )

                            print(
                                "LEGAL NOTICE CHECKBOX CHECKED",
                                flush=True,
                            )

                    accept_button = page.get_by_text(
                        "I Accept the terms",
                        exact=False,
                    ).first

                    accept_button_count = (
                        accept_button.count()
                    )

                    print(
                        "LEGAL NOTICE ACCEPT BUTTON COUNT: "
                        f"{accept_button_count}",
                        flush=True,
                    )

                    if accept_button_count > 0:
                        try:
                            page.wait_for_function(
                                """
                                () => {
                                    const elements = Array.from(
                                        document.querySelectorAll(
                                            "button, input[type='button'], "
                                            + "input[type='submit'], a"
                                        )
                                    );

                                    return elements.some(
                                        element => {
                                            const text = (
                                                element.innerText
                                                || element.value
                                                || element.textContent
                                                || ""
                                            );

                                            return (
                                                text.includes(
                                                    "I Accept the terms"
                                                )
                                                && !element.disabled
                                            );
                                        }
                                    );
                                }
                                """,
                                timeout=15000,
                            )

                        except PlaywrightTimeoutError:
                            print(
                                "ACCEPT BUTTON DID NOT BECOME "
                                "ENABLED WITHIN 15 SECONDS",
                                flush=True,
                            )

                        if accept_button.is_visible():
                            accept_button.click(
                                timeout=10000,
                            )

                            print(
                                "LEGAL NOTICE ACCEPTED",
                                flush=True,
                            )

                            page.wait_for_timeout(2000)

                    else:
                        print(
                            "LEGAL NOTICE ACCEPT BUTTON "
                            "NOT PRESENT",
                            flush=True,
                        )

                except PlaywrightTimeoutError as error:
                    print(
                        "LEGAL NOTICE TIMEOUT: "
                        f"{error!r}",
                        flush=True,
                    )

                except PlaywrightError as error:
                    if "Page crashed" in str(error):
                        raise

                    print(
                        "LEGAL NOTICE COULD NOT BE PROCESSED: "
                        f"{error!r}",
                        flush=True,
                    )

                # --------------------------------------------------
                # VERIFY STATE BEFORE SEARCH
                # --------------------------------------------------
                print(
                    "PAGE CLOSED EFORE SEARCH: "
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
                        "The ECHA page closed before locating "
                        "the search field."
                    )

                if not browser.is_connected():
                    raise RuntimeError(
                        "Chromium disconnected before locating "
                        "the search field."
                    )

                # --------------------------------------------------
                # LOCATE SEARCH FIELD
                # --------------------------------------------------
                print(
                    "CHECKPOINT 10: Locating ECHA search field",
                    flush=True,
                )

                search_field = page.locator(
                    'input[name="searchText"]'
                ).first

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
                        "No visible ECHA result rows were returned.",
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
                            f"ROW {index}: {error!r}",
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
            # PLAYWRIGHT ERRORS
            # --------------------------------------------------
            except PlaywrightError as error:
                error_name = type(error).__name__
                error_text = str(error)

                print("=" * 60, flush=True)
                print(
                    f"PLAYWRIGHT ERROR TYPE: {error_name}",
                    flush=True,
                )
                print(
                    f"PLAYWRIGHT ERROR: {error!r}",
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

                if "Page crashed" in error_text:
                    raise RuntimeError(
                        "The Chromium renderer for the ECHA "
                        "page crashed while the ECHA application "
                        "was initialising. Chromium itself "
                        "remained connected. Review the pw:browser "
                        "lines immediately before this error."
                    ) from error

                if error_name == "TargetClosedError":
                    raise RuntimeError(
                        "The ECHA page, browser context or "
                        "Chromium process closed unexpectedly. "
                        "Review the last completed checkpoint."
                    ) from error

                if isinstance(
                    error,
                    PlaywrightTimeoutError,
                ):
                    raise RuntimeError(
                        "The browser or ECHA page did not respond "
                        "within the allowed time."
                    ) from error

                raise RuntimeError(
                    "Playwright encountered an error while "
                    "searching ECHA."
                ) from error

            # --------------------------------------------------
            # APPLICATION ERRORS
            # --------------------------------------------------
            except RuntimeError:
                traceback.print_exc()
                raise

            except Exception as error:
                print("=" * 60, flush=True)
                print(
                    f"UNEXPECTED ERROR: {error!r}",
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
                            f"{error!r}",
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
                            f"{error!r}",
                            flush=True,
                        )

    except RuntimeError:
        raise

    except Exception as error:
        print(
            "ERROR OUTSIDE PLAYWRIGHT CONTEXT: "
            f"{error!r}",
            flush=True,
        )

        traceback.print_exc()

        raise RuntimeError(
            "The Playwright service could not be started."
        ) from error