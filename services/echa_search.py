import re
from urllib.parse import quote, urljoin

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_SEARCH_VERIFICATION_TEST_V15"


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
VERIFICATION_MAX_WAIT_SECONDS = 60
VERIFICATION_CHECK_INTERVAL_SECONDS = 5

DEFAULT_TIMEOUT_MS = 15000
NAVIGATION_TIMEOUT_MS = 60000
DOM_TIMEOUT_MS = 30000


# --------------------------------------------------
# ECHA URLS
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

ECHA_URL = ECHA_BASE_URL + "/"


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


# --------------------------------------------------
# BUILD DIRECT SEARCH URL
# --------------------------------------------------
def build_search_url(cas_number):
    encoded_cas = quote(
        str(cas_number).strip(),
        safe="",
    )

    search_url = (
        ECHA_BASE_URL
        + "/substance-search"
        + "?searchText="
        + encoded_cas
    )

    validate_url(
        "search_url",
        search_url,
    )

    return search_url


validate_url(
    "ECHA_BASE_URL",
    ECHA_BASE_URL,
)

validate_url(
    "ECHA_URL",
    ECHA_URL,
)


# --------------------------------------------------
# NORMALISE TEXT
# --------------------------------------------------
def normalise_text(value):
    if value is None:
        return ""

    return " ".join(
        str(value)
        .replace("\xa0", " ")
        .split()
    ).strip()


# --------------------------------------------------
# CAS NUMBER VALIDATION
# --------------------------------------------------
def looks_like_cas_number(value):
    value = normalise_text(value)

    return bool(
        re.fullmatch(
            r"\d{2,7}-\d{2}-\d",
            value,
        )
    )


# --------------------------------------------------
# EC NUMBER VALIDATION
# --------------------------------------------------
def looks_like_ec_number(value):
    value = normalise_text(value)

    return bool(
        re.fullmatch(
            r"\d{3}-\d{3}-\d",
            value,
        )
    )


# --------------------------------------------------
# READ BODY TEXT
# --------------------------------------------------
def read_body_text(page):
    try:
        return page.locator(
            "body"
        ).inner_text(
            timeout=10000
        )

    except PlaywrightError as error:
        print(
            f"BODY READ ERROR: {error}",
            flush=True,
        )

        return ""


# --------------------------------------------------
# PRINT PAGE DIAGNOSTICS
# --------------------------------------------------
def print_page_diagnostics(page, body_text=None):
    try:
        print(
            "PAGE TITLE:",
            page.title(),
            flush=True,
        )

    except PlaywrightError as error:
        print(
            f"PAGE TITLE ERROR: {error}",
            flush=True,
        )

    print(
        "CURRENT URL:",
        page.url,
        flush=True,
    )

    if body_text is None:
        body_text = read_body_text(page)

    print(
        "BODY TEXT START",
        flush=True,
    )

    print(
        body_text[:4000],
        flush=True,
    )

    print(
        "BODY TEXT END",
        flush=True,
    )


# --------------------------------------------------
# DETECT BLOCK / VERIFICATION PAGE
# --------------------------------------------------
def page_looks_blocked(page):
    """
    Determine whether Chromium is still showing the
    Azure 403 / intermediate access-control response.

    This function does not attempt to solve or bypass
    any interactive verification challenge.
    """

    try:
        title = normalise_text(
            page.title()
        )

    except PlaywrightError:
        title = ""

    body_text = read_body_text(
        page
    )

    combined_text = (
        title
        + " "
        + body_text
    ).lower()

    blocked_indicators = [
        "403 forbidden",
        "microsoft-azure-application-gateway",
    ]

    return any(
        indicator in combined_text
        for indicator in blocked_indicators
    )


# --------------------------------------------------
# WAIT FOR POSSIBLE VERIFICATION PAGE
# --------------------------------------------------
def wait_for_verification_to_clear(
    page,
    description,
):
    """
    Wait for a temporary access-control / verification
    page to clear by itself.

    No CAPTCHA or interactive verification mechanism is
    clicked or bypassed here.
    """

    print(
        f"{description} appears to be blocked or "
        f"behind an intermediate verification page.",
        flush=True,
    )

    print(
        f"Waiting up to "
        f"{VERIFICATION_MAX_WAIT_SECONDS} seconds "
        f"for the browser session to continue naturally.",
        flush=True,
    )

    elapsed_seconds = 0

    while (
        elapsed_seconds
        < VERIFICATION_MAX_WAIT_SECONDS
    ):
        page.wait_for_timeout(
            VERIFICATION_CHECK_INTERVAL_SECONDS
            * 1000
        )

        elapsed_seconds += (
            VERIFICATION_CHECK_INTERVAL_SECONDS
        )

        print(
            f"ECHA verification wait: "
            f"{elapsed_seconds} seconds",
            flush=True,
        )

        try:
            title = normalise_text(
                page.title()
            )

        except PlaywrightError as error:
            title = ""

            print(
                f"Could not read page title: {error}",
                flush=True,
            )

        try:
            body_text = read_body_text(
                page
            )

            print(
                f"Current title: {title}",
                flush=True,
            )

            print(
                f"Current URL: {page.url}",
                flush=True,
            )

            print(
                "Current body start: "
                f"{body_text[:500]}",
                flush=True,
            )

            if not page_looks_blocked(page):
                print(
                    f"{description} no longer shows "
                    f"the Azure 403 response.",
                    flush=True,
                )

                print(
                    f"Verification/block page cleared "
                    f"after approximately "
                    f"{elapsed_seconds} seconds.",
                    flush=True,
                )

                try:
                    page.wait_for_load_state(
                        "domcontentloaded",
                        timeout=DOM_TIMEOUT_MS,
                    )

                    print(
                        "DOM content loaded after "
                        "verification",
                        flush=True,
                    )

                except PlaywrightTimeoutError:
                    print(
                        "DOM content did not fully finish "
                        "loading after verification. "
                        "Continuing with the rendered page.",
                        flush=True,
                    )

                return True

        except PlaywrightError as error:
            print(
                f"Could not inspect verification page: "
                f"{error}",
                flush=True,
            )

    print(
        f"ERROR: {description} is still blocked "
        f"after {VERIFICATION_MAX_WAIT_SECONDS} seconds.",
        flush=True,
    )

    print_page_diagnostics(
        page
    )

    return False


# --------------------------------------------------
# CLICK BUTTON IF VISIBLE
# --------------------------------------------------
def click_button_if_visible(
    container,
    button_name,
):
    """
    Find and click a normal ECHA consent control.

    This only handles ordinary cookie/legal consent
    controls. It does not interact with CAPTCHA or
    anti-bot verification challenges.
    """

    selectors = [
        f'button:has-text("{button_name}")',
        f'a:has-text("{button_name}")',
        f'[role="button"]:has-text("{button_name}")',
        f'text="{button_name}"',
    ]

    for selector in selectors:
        try:
            locator = container.locator(
                selector
            ).first

            if locator.count() == 0:
                continue

            if not locator.is_visible(
                timeout=1000
            ):
                continue

            print(
                f"Found ECHA consent control "
                f"'{button_name}' using {selector}",
                flush=True,
            )

            locator.click(
                timeout=5000,
                force=True,
            )

            print(
                f"Clicked ECHA consent control: "
                f"{button_name}",
                flush=True,
            )

            return True

        except PlaywrightTimeoutError:
            continue

        except PlaywrightError as error:
            print(
                f"Could not click '{button_name}' "
                f"using {selector}: {error}",
                flush=True,
            )

    return False


# --------------------------------------------------
# HANDLE ECHA COOKIE AND LEGAL NOTICES
# --------------------------------------------------
def handle_echa_consent(page):
    consent_names = [
        "Accept only essential cookies",
        "Accept all cookies",
        "I Accept the terms",
        "I accept the terms",
        "Accept the terms",
        "I Accept",
    ]

    print(
        "Checking ECHA consent controls "
        "on the main page",
        flush=True,
    )

    for consent_name in consent_names:
        if click_button_if_visible(
            page,
            consent_name,
        ):
            page.wait_for_timeout(
                2000
            )

            return True

    print(
        f"Consent control not found on main page. "
        f"Checking {len(page.frames)} frame(s).",
        flush=True,
    )

    for frame_index, frame in enumerate(
        page.frames
    ):
        try:
            print(
                f"Checking frame {frame_index}: "
                f"{frame.url}",
                flush=True,
            )

            for consent_name in consent_names:
                if click_button_if_visible(
                    frame,
                    consent_name,
                ):
                    page.wait_for_timeout(
                        2000
                    )

                    return True

        except PlaywrightError as error:
            print(
                f"Could not inspect frame "
                f"{frame_index}: {error}",
                flush=True,
            )

    print(
        "No clickable ECHA consent control was found.",
        flush=True,
    )

    return False


# --------------------------------------------------
# CHECK WHETHER LEGAL NOTICE IS ACTIVE
# --------------------------------------------------
def legal_notice_is_active(page):
    try:
        body_text = page.locator(
            "body"
        ).inner_text(
            timeout=10000
        )

        indicators = [
            "Accept only essential cookies",
            "Accept all cookies",
            "The European Chemicals Agency",
            "1. Disclaimer",
        ]

        matches = sum(
            indicator in body_text
            for indicator in indicators
        )

        print(
            f"ECHA legal notice indicator matches: "
            f"{matches}",
            flush=True,
        )

        return matches >= 3

    except PlaywrightError as error:
        print(
            f"Could not determine whether the ECHA "
            f"legal notice is active: {error}",
            flush=True,
        )

        return False


# --------------------------------------------------
# GENERIC ECHA NAVIGATION
# --------------------------------------------------
def open_echa_page(
    page,
    url,
    description,
):
    """
    Navigate to an ECHA page.

    A 403 is intentionally not treated as immediately fatal.
    Chromium is allowed to remain on the page for up to
    60 seconds to determine whether an intermediate page
    clears naturally.
    """

    print(
        f"Opening {description}: {url}",
        flush=True,
    )

    try:
        response = page.goto(
            url,
            wait_until="commit",
            timeout=NAVIGATION_TIMEOUT_MS,
        )

    except PlaywrightTimeoutError as error:
        print(
            f"{description} initial navigation timed out: "
            f"{error}",
            flush=True,
        )

        response = None

    print(
        f"{description} navigation step completed. "
        f"Current URL: {page.url}",
        flush=True,
    )

    status = None

    if response is not None:
        status = response.status

        print(
            f"{description} HTTP status: {status}",
            flush=True,
        )

    else:
        print(
            f"WARNING: {description} returned "
            f"no response object",
            flush=True,
        )

    # --------------------------------------------------
    # SPECIAL HANDLING FOR HTTP 403
    # --------------------------------------------------
    if status == 403:
        print(
            f"WARNING: {description} returned HTTP 403.",
            flush=True,
        )

        print(
            "The browser will remain open temporarily "
            "to determine whether this response changes "
            "after an intermediate verification step.",
            flush=True,
        )

        cleared = wait_for_verification_to_clear(
            page,
            description,
        )

        if not cleared:
            raise RuntimeError(
                f"{description} remained blocked with "
                f"HTTP 403 after "
                f"{VERIFICATION_MAX_WAIT_SECONDS} seconds"
            )

        return response

    # --------------------------------------------------
    # OTHER HTTP ERRORS
    # --------------------------------------------------
    if (
        status is not None
        and status >= 400
    ):
        print_page_diagnostics(
            page
        )

        raise RuntimeError(
            f"{description} returned "
            f"HTTP status {status}"
        )

    # --------------------------------------------------
    # NORMAL DOM LOADING
    # --------------------------------------------------
    try:
        page.wait_for_load_state(
            "domcontentloaded",
            timeout=DOM_TIMEOUT_MS,
        )

        print(
            f"{description} DOM content loaded",
            flush=True,
        )

    except PlaywrightTimeoutError:
        print(
            f"WARNING: {description} DOM content "
            f"did not finish loading within "
            f"{DOM_TIMEOUT_MS // 1000} seconds. "
            f"Continuing with the rendered page.",
            flush=True,
        )

    page.wait_for_timeout(
        3000
    )

    return response


# --------------------------------------------------
# WAIT FOR ECHA SEARCH CONTENT
# --------------------------------------------------
def wait_for_echa_content(
    page,
    cas_number,
):
    print(
        f"Waiting for CAS {cas_number} "
        f"to appear in the rendered ECHA page",
        flush=True,
    )

    try:
        page.wait_for_function(
            """
            casNumber => {
                const bodyText = document.body
                    ? document.body.innerText
                    : "";

                return bodyText.includes(casNumber);
            }
            """,
            arg=cas_number,
            timeout=60000,
        )

        print(
            f"CAS {cas_number} is visible "
            f"in the page",
            flush=True,
        )

        return True

    except PlaywrightTimeoutError:
        print(
            f"CAS {cas_number} was not visible "
            f"after 60 seconds",
            flush=True,
        )

        return False

    except PlaywrightError as error:
        print(
            f"Could not wait for ECHA content: "
            f"{error}",
            flush=True,
        )

        return False


# --------------------------------------------------
# FIND RESULT ROWS
# --------------------------------------------------
def find_result_rows(page, cas_number):
    all_rows = page.locator(
        "table tbody tr:has(td)"
    )

    matching_rows = []

    try:
        row_count = all_rows.count()

    except PlaywrightError as error:
        print(
            f"Could not count ECHA result rows: "
            f"{error}",
            flush=True,
        )

        return matching_rows

    print(
        f"ECHA TABLE ROW COUNT: {row_count}",
        flush=True,
    )

    for index in range(
        row_count
    ):
        row = all_rows.nth(
            index
        )

        try:
            row_text = normalise_text(
                row.inner_text(
                    timeout=5000
                )
            )

            print(
                f"ROW {index} TEXT: {row_text}",
                flush=True,
            )

            if cas_number in row_text:
                matching_rows.append(
                    row
                )

        except PlaywrightError as error:
            print(
                f"Could not read row "
                f"{index}: {error}",
                flush=True,
            )

    print(
        f"ECHA MATCHING ROW COUNT: "
        f"{len(matching_rows)}",
        flush=True,
    )

    return matching_rows


# --------------------------------------------------
# EXTRACT RESULT FROM ROW
# --------------------------------------------------
def extract_result_from_row(
    row,
    cas_number,
    row_index,
):
    cells = row.locator(
        "td"
    )

    try:
        cell_count = cells.count()

    except PlaywrightError as error:
        print(
            f"Could not count cells in row "
            f"{row_index}: {error}",
             flush=True,
        )

        return None

    cell_values = []

    for cell_index in range(
        cell_count
    ):
        try:
            cell_text = cells.nth(
                cell_index
            ).inner_text(
                timeout=5000
            )

            cell_values.append(
                normalise_text(
                   cell_text
                )
            )

        except PlaywrightError:
            cell_values.append(
                ""
            )

    print(
        f"ROW {row_index} CELLS: "
        f"{cell_values}",
        flush=True,
    )

    if not cell_values:
        return None

    combined_text = " | ".join(
        cell_values
    )

    if cas_number not in combined_text:
        return None

    found_cas = ""

    for value in cell_values:
        if cas_number in value:
            found_cas = cas_number
            break

        if looks_like_cas_number(
            value
        ):
            found_cas = value
            break

    ec_number = ""

    for value in cell_values:
        if looks_like_ec_number(
            value
        ):
            ec_number = value
            break

    links = row.locator(
        "a[href]"
    )

    relative_url = None
    link_text = ""

    try:
        link_count = links.count()

    except PlaywrightError:
        link_count = 0

    for link_index in range(
        link_count
    ):
        link = links.nth(
            link_index
        )

        try:
            candidate_url = (
                link.get_attribute(
                    "href"
                )
            )

            candidate_text = (
                normalise_text(
                    link.inner_text(
                        timeout=3000
                    )
                )
            )

            if candidate_url:
                relative_url = (
                    candidate_url
                )

                if candidate_text:
                    link_text = (
                        candidate_text
                    )

                break

        except PlaywrightError:
            continue

    if not relative_url:
        print(
            f"Skipping row {row_index}: "
            f"no result link found",
            flush=True,
        )

        return None

    full_url = urljoin(
        ECHA_BASE_URL + "/",
        relative_url,
    )

    validate_url(
        "result_url",
        full_url,
    )

    name = link_text

    if not name:
        for value in cell_values:
            if not value:
                continue

            if value == found_cas:
                continue

            if value == ec_number:
                continue

            if looks_like_cas_number(
                value
            ):
                continue

            if looks_like_ec_number(
                value
            ):
                continue

            name = value
            break

    if not name:
        name = "ECHA substance"

    result = {
        "Name": name,
        "EC Number": ec_number,
        "CAS Number": (
            found_cas
            or cas_number
        ),
        "URL": full_url,
    }

    print(
        f"Extracted ECHA result: "
        f"{result}",
        flush=True,
    )

    return result


# --------------------------------------------------
# REMOVE DUPLICATES
# --------------------------------------------------
def remove_duplicate_results(
    results,
):
    unique_results = []
    seen_urls = set()

    for result in results:
        result_url = result.get(
            "URL",
            "",
        )

        if (
            result_url
            and result_url in seen_urls
        ):
            continue

        if result_url:
            seen_urls.add(
                result_url
            )

        unique_results.append(
            result
        )

    return unique_results


# --------------------------------------------------
# ECHA SEARCH
# --------------------------------------------------
def search_echa(cas_number):
    results = []

    cas_number = normalise_text(
        cas_number
    )

    if not cas_number:
        print(
            "ECHA search skipped: "
            "no CAS number supplied",
            flush=True,
        )

        return results

    if not looks_like_cas_number(
        cas_number
    ):
        raise ValueError(
            f"Invalid CAS number format: "
            f"{cas_number!r}"
        )

    browser = None
    context = None

    print(
        f"ECHA code version: "
        f"{CODE_VERSION}",
        flush=True,
    )

    print(
        f"ECHA search started for "
        f"CAS {cas_number}",
        flush=True,
    )

    try:
        with sync_playwright() as playwright:
            try:
                # --------------------------------------------------
                # START CHROMIUM
                # --------------------------------------------------
                print(
                    "Starting Chromium for ECHA search",
                    flush=True,
                )

                browser = (
                    playwright.chromium.launch(
                        headless=True,
                        chromium_sandbox=False,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                        ],
                    )
                )

                print(
                    "Chromium started successfully",
                    flush=True,
                )

                # --------------------------------------------------
                # CONTEXT
                # --------------------------------------------------
                context = browser.new_context(
                    viewport={
                        "width": 1280,
                        "height": 900,
                    },
                    locale="en-US",
                )

                print(
                    "Chromium context created",
                    flush=True,
                )

                page = (
                    context.new_page()
                )

                print(
                    "Chromium page created",
                    flush=True,
                )

                page.set_default_timeout(
                    DEFAULT_TIMEOUT_MS
                )

                page.set_default_navigation_timeout(
                    NAVIGATION_TIMEOUT_MS
                )

                # IMPORTANT FOR V15:
                #
                # Do NOT block images, fonts, media or
                # scripts during this test.
                #
                # The intermediate verification mechanism
                # may depend on browser resources.
                #
                # Therefore there is intentionally no:
                #
                # page.route(
                #     "**/*",
                #     block_unnecessary_resources,
                # )

                search_url = (
                    build_search_url(
                        cas_number
                    )
                )

                # --------------------------------------------------
                # STEP 1: OPEN HOMEPAGE
                # --------------------------------------------------
                print(
                    "Creating initial ECHA "
                    "browser session",
                    flush=True,
                )

                open_echa_page(
                    page,
                    ECHA_URL,
                    "ECHA homepage",
                )

                print(
                    "ECHA homepage is accessible "
                    "after initial navigation/"
                    "verification handling",
                    flush=True,
                )

                # --------------------------------------------------
                # STEP 2: NORMAL CONSENT
                # --------------------------------------------------
                consent_clicked = (
                    handle_echa_consent(
                        page
                    )
                )

                if consent_clicked:
                    print(
                        "ECHA consent handled "
                        "on homepage",
                        flush=True,
                    )

                    page.wait_for_timeout(
                        3000
                    )

                else:
                    print(
                        "No normal ECHA consent "
                        "control found on homepage",
                        flush=True,
                    )

                # --------------------------------------------------
                # STEP 3: LEGAL NOTICE
                # --------------------------------------------------
                if legal_notice_is_active(
                    page
                ):
                    print(
                        "ECHA legal notice is active. "
                        "Trying consent once more.",
                        flush=True,
                    )

                    second_consent_clicked = (
                        handle_echa_consent(
                            page
                        )
                    )

                    if second_consent_clicked:
                        page.wait_for_timeout(
                            3000
                        )

                # --------------------------------------------------
                # STEP 4: OPEN SUBSTANCE SEARCH
                # --------------------------------------------------
                print(
                    f"Opening ECHA substance search "
                    f"for {cas_number}",
                    flush=True,
                )

                open_echa_page(
                    page,
                    search_url,
                    "ECHA substance search",
                )

                # --------------------------------------------------
                # STEP 5: CONSENT ON SEARCH PAGE
                # --------------------------------------------------
                if legal_notice_is_active(
                    page
                ):
                    print(
                        "ECHA legal notice detected "
                        "on substance search page.",
                        flush=True,
                    )

                    search_consent_clicked = (
                        handle_echa_consent(
                            page
                        )
                    )

                    if search_consent_clicked:
                        print(
                            "ECHA consent handled "
                            "on substance search page",
                            flush=True,
                        )

                        page.wait_for_timeout(
                            3000
                        )

                        print(
                            "Reloading ECHA search "
                            "after consent",
                            flush=True,
                        )

                        open_echa_page(
                            page,
                            search_url,
                            "ECHA substance search "
                            "after consent",
                        )

                # --------------------------------------------------
                # STEP 6: FINAL BLOCK CHECK
                # --------------------------------------------------
                if page_looks_blocked(
                    page
                ):
                    print(
                        "ERROR: ECHA search page "
                        "is still blocked.",
                        flush=True,
                    )

                    print_page_diagnostics(
                        page
                    )

                    raise RuntimeError(
                        "ECHA search remained blocked"
                    )

                # --------------------------------------------------
                # STEP 7: WAIT FOR CAS
                # --------------------------------------------------
                cas_visible = (
                    wait_for_echa_content(
                        page,
                        cas_number,
                    )
                )

                body_text = (
                    read_body_text(
                        page
                    )
                )

                print_page_diagnostics(
                    page,
                    body_text,
                )

                if not cas_visible:
                    print(
                        f"CAS {cas_number} did not "
                        f"appear in the rendered page "
                        f"within the timeout",
                        flush=True,
                    )

                # --------------------------------------------------
                # STEP 8: FIND RESULTS
                # --------------------------------------------------
                matching_rows = (
                    find_result_rows(
                        page,
                        cas_number,
                    )
                )

                if not matching_rows:
                    print(
                        f"No ECHA substance result "
                        f"rows found for "
                        f"{cas_number}",
                        flush=True,
                    )

                    return []

                # --------------------------------------------------
                # STEP 9: EXTRACT RESULTS
                # --------------------------------------------------
                for index, row in enumerate(
                    matching_rows
                ):
                    try:
                        result = (
                            extract_result_from_row(
                                row=row,
                                cas_number=cas_number,
                                row_index=index,
                            )
                        )

                        if result is not None:
                            results.append(
                                result
                            )

                    except PlaywrightError as error:
                        print(
                            f"Could not process "
                            f"matching row {index}: "
                            f"{error}",
                            flush=True,
                        )

                    except Exception as error:
                        print(
                            f"Unexpected row error "
                            f"at {index}: {error}",
                            flush=True,
                        )

                # --------------------------------------------------
                # STEP 10: REMOVE DUPLICATES
                # --------------------------------------------------
                unique_results = (
                    remove_duplicate_results(
                        results
                    )
                )

                print(
                    "ECHA SEARCH COMPLETED "
                    "SUCCESSFULLY",
                    flush=True,
                )

                print(
                    f"RESULTS FOUND: "
                    f"{len(unique_results)}",
                    flush=True,
                )

                return unique_results

            except PlaywrightTimeoutError as error:
                raise RuntimeError(
                    f"ECHA search timed out: "
                    f"{error}"
                ) from error

            except PlaywrightError as error:
                raise RuntimeError(
                    f"ECHA search failed: "
                    f"{error}"
                ) from error

            except RuntimeError:
                raise

            except Exception as error:
                raise RuntimeError(
                    f"Unexpected ECHA error: "
                    f"{error}"
                ) from error

            finally:
                # --------------------------------------------------
                # CLEANUP
                # --------------------------------------------------
                if context is not None:
                    try:
                        context.close()

                        print(
                            "Chromium context closed",
                            flush=True,
                        )

                    except PlaywrightError as error:
                        print(
                            f"Could not close "
                            f"Chromium context: "
                            f"{error}",
                            flush=True,
                        )

                if browser is not None:
                    try:
                        browser.close()

                        print(
                            "Chromium browser closed",
                            flush=True,
                        )

                    except PlaywrightError as error:
                        print(
                            f"Could not close "
                            f"Chromium browser: "
                            f"{error}",
                            flush=True,
                        )

    except RuntimeError:
        raise

    except Exception as error:
        raise RuntimeError(
            "The Playwright service could not "
            f"be started: {error}"
        ) from error