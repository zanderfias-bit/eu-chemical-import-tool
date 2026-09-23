import os

from urllib.parse import quote

from playwright.sync_api import (
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


# --------------------------------------------------
# VERSION
# --------------------------------------------------
CODE_VERSION = "ECHA_SEARCH_DIRECT_URL_V11"


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
# ECHA SEARCH
# --------------------------------------------------
def search_echa(cas_number):
    results = []

    cas_number = str(
        cas_number
    ).strip()

    if not cas_number:
        return results

    browser = None
    context = None

    print(
        f"ECHA search started for CAS {cas_number}",
        flush=True,
    )

    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(
                    executable_path=
                    playwright.chromium.executable_path,
                    headless=True,
                    chromium_sandbox=False,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
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

                # --------------------------------------------------
                # ACCEPT LEGAL NOTICE IF PRESENT
                # --------------------------------------------------
                try:
                    accept_button = page.get_by_text(
                        "I Accept the terms",
                        exact=False,
                    ).first

                    if (
                        accept_button.count() > 0
                        and accept_button.is_visible(
                            timeout=5000
                        )
                    ):
                        print(
                            "Accepting ECHA legal notice",
                            flush=True,
                        )

                        accept_button.click(
                            timeout=10000,
                        )

                        page.wait_for_load_state(
                            "networkidle",
                            timeout=30000,
                        )

                        page.wait_for_timeout(
                            2000
                        )

                except PlaywrightTimeoutError:
                    pass

                except PlaywrightError:
                    pass

                if response is not None:
                    if response.status >= 400:
                        raise RuntimeError(
                            f"ECHA returned HTTP status "
                            f"{response.status}"
                        )

                rows = page.locator(
                    "table tbody tr"
                )

                try:
                    rows.first.wait_for(
                        state="visible",
                        timeout=60000,
                    )

                except PlaywrightTimeoutError:
                    print(
                        f"No ECHA results found for "
                        f"{cas_number}",
                        flush=True,
                    )

                    return []

                row_count = rows.count()

                print(
                    f"ECHA RESULT ROW COUNT: "
                    f"{row_count}",
                    flush=True,
                )

                for index in range(
                    row_count
                ):
                    row = rows.nth(index)

                    cells = row.locator(
                        "td"
                    )

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

                        link = (
                            row.locator("a")
                            .first
                        )

                        relative_url = (
                            link.get_attribute(
                                "href"
                            )
                        )

                        if not relative_url:
                            continue

                        if relative_url.startswith(
                            "/"
                        ):
                            full_url = (
                                ECHA_BASE_URL
                                + relative_url
                            )
                        else:
                            full_url = (
                                relative_url
                            )

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

                print(
                    "ECHA SEARCH COMPLETED "
                    "SUCCESSFULLY",
                    flush=True,
                )

                print(
                    f"RESULTS FOUND: "
                    f"{len(results)}",
                    flush=True,
                )

                return results

            except PlaywrightError as error:
                raise RuntimeError(
                    f"ECHA search failed: "
                    f"{error}"
                ) from error

            except Exception as error:
                raise RuntimeError(
                    f"Unexpected ECHA error: "
                    f"{error}"
                ) from error

            finally:
                if context is not None:
                    context.close()

                if browser is not None:
                    browser.close()

    except RuntimeError:
        raise

    except Exception as error:
        raise RuntimeError(
            f"The Playwright service "
            f"could not be started: "
            f"{error}"
        ) from error