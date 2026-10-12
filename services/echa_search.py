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
CODE_VERSION = "ECHA_SEARCH_DIRECT_URL_V12"


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
# RESOURCE FILTER
# --------------------------------------------------
def block_unnecessary_resources(route):
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
# NORMALISE TEXT
# --------------------------------------------------
def normalise_text(value):
    if value is None:
        return ""

    return " ".join(
        str(value).replace("\xa0", " ").split()
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
# CLICK BUTTON IF VISIBLE
# --------------------------------------------------
def click_button_if_visible(page, button_name):
    try:
        button = page.get_by_role(
            "button",
            name=button_name,
            exact=False,
        ).first

        if button.count() == 0:
            return False

        if not button.is_visible():
            return False

        print(
            f"Clicking ECHA button: {button_name}",
            flush=True,
        )

        button.click(
            timeout=10000,
        )

        page.wait_for_timeout(
            1500
        )

        return True

    except PlaywrightError as error:
        print(
            f"Could not click '{button_name}': {error}",
            flush=True,
        )

        return False


# --------------------------------------------------
# HANDLE ECHA COOKIE AND LEGAL NOTICES
# --------------------------------------------------
def handle_echa_consent(page):
    consent_clicked = False

    cookie_button_names = [
        "Accept only essential cookies",
        "Accept all cookies",
    ]

    for button_name in cookie_button_names:
        if click_button_if_visible(
            page,
            button_name,
        ):
            consent_clicked = True
            break

    legal_button_names = [
        "I Accept the terms",
        "I accept the terms",
        "Accept the terms",
        "I Accept",
    ]

    for button_name in legal_button_names:
        if click_button_if_visible(
            page,
            button_name,
        ):
            consent_clicked = True
            break

    return consent_clicked


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
# WAIT FOR ECHA PAGE CONTENT
# --------------------------------------------------
def wait_for_echa_content(page, cas_number):
    try:
        page.wait_for_function(
            f"""
            () => {{
                const bodyText =
                    document.body
                    ? document.body.innerText
                    : "";

                return bodyText.includes("{cas_number}");
            }}
            """,
            timeout=30000,
        )

        return True

    except PlaywrightTimeoutError:
        return False


# --------------------------------------------------
# FIND RESULT ROWS
# --------------------------------------------------
def find_result_rows(page, cas_number):
    all_rows = page.locator(
        "table tbody tr:has(td)"
    )

    matching_rows = []

    row_count = all_rows.count()

    print(
        f"ECHA TABLE ROW COUNT: {row_count}",
        flush=True,
    )

    for index in range(row_count):
        row = all_rows.nth(index)

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
                matching_rows.append(row)

        except PlaywrightError as error:
            print(
                f"Could not read row {index}: {error}",
                flush=True,
            )

    print(
        f"ECHA MATCHING ROW COUNT: "
        f"{len(matching_rows)}",
        flush=True,
    )

    return matching_rows


# --------------------------------------------------
# EXTRACT A RESULT FROM A ROW
# --------------------------------------------------
def extract_result_from_row(
    row,
    cas_number,
    row_index,
):
    cells = row.locator("td")
    cell_count = cells.count()

    cell_values = []

    for cell_index in range(cell_count):
        try:
            cell_text = cells.nth(
                cell_index
            ).inner_text(
                timeout=5000
            )

            cell_values.append(
                normalise_text(cell_text)
            )

        except PlaywrightError:
            cell_values.append("")

    print(
        f"ROW {row_index} CELLS: {cell_values}",
        flush=True,
    )

    if not cell_values:
        print(
            f"Skipping row {row_index}: no cells",
            flush=True,
        )
        return None

    combined_text = " | ".join(cell_values)

    if cas_number not in combined_text:
        print(
            f"Skipping row {row_index}: "
            f"CAS number not found in row",
            flush=True,
        )
        return None

    found_cas = ""

    for value in cell_values:
        if cas_number in value:
            found_cas = cas_number
            break

        if looks_like_cas_number(value):
            found_cas = value
            break

    ec_number = ""

    for value in cell_values:
        if looks_like_ec_number(value):
            ec_number = value
            break

    links = row.locator("a[href]")
    relative_url = None
    link_text = ""

    for link_index in range(links.count()):
        link = links.nth(link_index)

        try:
            candidate_url = link.get_attribute(
                "href"
            )

            candidate_text = normalise_text(
                link.inner_text(
                    timeout=3000
                )
            )

            if candidate_url:
                relative_url = candidate_url

                if candidate_text:
                    link_text = candidate_text

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

    name = link_text

    if not name:
        for value in cell_values:
            if not value:
                continue

            if value == found_cas:
                continue

            if value == ec_number:
                continue

            if looks_like_cas_number(value):
                continue

            if looks_like_ec_number(value):
                continue

            name = value
            break

    if not name:
        name = "ECHA substance"

    return {
        "Name": name,
        "EC Number": ec_number,
        "CAS Number": found_cas or cas_number,
        "URL": full_url,
    }


# --------------------------------------------------
# ECHA SEARCH
# --------------------------------------------------
def search_echa(cas_number):
    results = []

    cas_number = normalise_text(
        cas_number
    )

    if not cas_number:
        return results

    browser = None
    context = None

    print(
        f"ECHA code version: {CODE_VERSION}",
        flush=True,
    )

    print(
        f"ECHA search started for CAS {cas_number}",
        flush=True,
    )

    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    headless=True,
                    chromium_sandbox=False,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )

                context = browser.new_context(
                    viewport={
                        "width": 1280,
                        "height": 900,
                    },
                    locale="en-US",
                )

                page = context.new_page()

                page.route(
                    "**/*",
                    block_unnecessary_resources,
                )

                search_url = build_search_url(
                    cas_number
                )

                print(
                    f"Searching ECHA for {cas_number}",
                    flush=True,
                )

                response = page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                if (
                    response is not None
                    and response.status >= 400
                ):
                    raise RuntimeError(
                        f"ECHA returned HTTP status "
                        f"{response.status}"
                    )

                page.wait_for_timeout(
                    2000
                )

                # Handle the cookie banner or legal notice.
                consent_clicked = handle_echa_consent(
                    page
                )

                # Reload the search URL if consent was accepted.
                if consent_clicked:
                    print(
                        "Reloading ECHA search after consent",
                        flush=True,
                    )

                    response = page.goto(
                        search_url,
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )

                    if (
                        response is not None
                        and response.status >= 400
                    ):
                        raise RuntimeError(
                            f"ECHA returned HTTP status "
                            f"{response.status}"
                        )

                    page.wait_for_timeout(
                        2000
                    )

                    # Check for a second consent notice.
                    second_consent_clicked = (
                        handle_echa_consent(page)
                    )

                    if second_consent_clicked:
                        print(
                            "Reloading ECHA after second consent",
                            flush=True,
                        )

                        page.goto(
                            search_url,
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )

                        page.wait_for_timeout(
                            2000
                        )

                # Wait until the CAS number appears somewhere
                # in the rendered page.
                cas_visible = wait_for_echa_content(
                    page,
                    cas_number,
                )

                body_text = read_body_text(
                    page
                )

                print_page_diagnostics(
                    page,
                    body_text,
                )

                if not cas_visible:
                    print(
                        f"CAS {cas_number} did not appear "
                        f"in the rendered page within the timeout",
                        flush=True,
                    )

                matching_rows = find_result_rows(
                    page,
                    cas_number,
                )

                if not matching_rows:
                    print(
                        f"No ECHA substance result rows found "
                        f"for {cas_number}",
                        flush=True,
                    )

                    return []

                for index, row in enumerate(
                    matching_rows
                ):
                    try:
                        result = extract_result_from_row(
                            row=row,
                            cas_number=cas_number,
                            row_index=index,
                        )

                        if result is not None:
                            results.append(result)

                    except PlaywrightError as error:
                        print(
                            f"Could not process matching row "
                            f"{index}: {error}",
                            flush=True,
                        )

                    except Exception as error:
                        print(
                            f"Unexpected row error at "
                            f"{index}: {error}",
                            flush=True,
                        )

                # Remove duplicate results.
                unique_results = []
                seen_urls = set()

                for result in results:
                    result_url = result.get(
                        "URL",
                        "",
                    )

                    if result_url in seen_urls:
                        continue

                    seen_urls.add(
                        result_url
                    )

                    unique_results.append(
                        result
                    )

                print(
                    "ECHA SEARCH COMPLETED SUCCESSFULLY",
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
                    f"ECHA search timed out: {error}"
                ) from error

            except PlaywrightError as error:
                raise RuntimeError(
                    f"ECHA search failed: {error}"
                ) from error

            except Exception as error:
                raise RuntimeError(
                    f"Unexpected ECHA error: {error}"
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

    except RuntimeError:
        raise

    except Exception as error:
        raise RuntimeError(
            f"The Playwright service could not be started: "
            f"{error}"
        ) from error