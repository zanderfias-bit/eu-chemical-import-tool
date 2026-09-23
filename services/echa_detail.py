import re

from playwright.sync_api import (
    sync_playwright,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
ECHA_BASE_URL = (
    "https://chem.echa.europa.eu/"
)


# --------------------------------------------------
# ECHA DETAIL
# --------------------------------------------------
def get_echa_detail(
    relative_url,
    cas_number,
):

    # --------------------------------------------------
    # EXTRACT SUBSTANCE ID
    # --------------------------------------------------
    match = re.search(
        r"(\d+\.\d+\.\d+)",
        relative_url,
    )

    if not match:
        raise RuntimeError(
            "Could not extract substance ID from URL."
        )

    substance_id = match.group(1)

    # --------------------------------------------------
    # BUILD REACH URL
    # --------------------------------------------------
    reach_url = (
        f"{ECHA_BASE_URL}"
        f"{substance_id}"
        f"/dossier-list/reach/asset-owner"
        f"?searchText={cas_number}"
        f"&pageIndex=1"
    )

    print(
        f"Opening ECHA detail page "
        f"for CAS {cas_number}",
        flush=True,
    )

    try:

        with sync_playwright() as playwright:

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

            # --------------------------------------------------
            # OPEN PAGE
            # --------------------------------------------------
            response = page.goto(
                reach_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            if (
                response is not None
                and response.status >= 400
            ):
                raise RuntimeError(
                    f"ECHA returned HTTP "
                    f"status {response.status}"
                )

            # --------------------------------------------------
            # WAIT FOR APP
            # --------------------------------------------------
            page.wait_for_timeout(
                5000
            )

            # --------------------------------------------------
            # ACCEPT LEGAL NOTICE
            # --------------------------------------------------
            try:

                legal_notice = page.locator(
                    "text=Legal notice"
                )

                if legal_notice.count() > 0:

                    print(
                        "Legal notice detected",
                        flush=True,
                    )

                    accept_button = (
                        page.get_by_text(
                            "I Accept the terms",
                            exact=False,
                        ).first
                    )

                    if (
                        accept_button.count()
                        > 0
                    ):
                        accept_button.click(
                            timeout=10000,
                        )

                        print(
                            "Legal notice accepted",
                            flush=True,
                        )

                        page.wait_for_load_state(
                            "networkidle",
                            timeout=30000,
                        )

                        page.wait_for_timeout(
                            3000
                        )

            except (
                PlaywrightError,
                PlaywrightTimeoutError,
            ):
                pass

            # --------------------------------------------------
            # FIND TABLE
            # --------------------------------------------------
            tables = page.locator(
                "table"
            )

            try:

                tables.first.wait_for(
                    state="visible",
                    timeout=60000,
                )

            except PlaywrightTimeoutError:

                print(
                    "No registrant tables found.",
                    flush=True,
                )

                return {
                    "url": page.url,
                    "title": page.title(),
                    "registrants": [],
                }

            # --------------------------------------------------
            # EXTRACT REGISTRANTS
            # --------------------------------------------------
            registrants = []

            table = tables.first

            rows = table.locator(
                "tr"
            )

            row_count = rows.count()

            print(
                f"Registrant rows found: "
                f"{row_count}",
                flush=True,
            )

            for i in range(
                1,
                row_count,
            ):

                try:

                    cells = (
                        rows.nth(i)
                        .locator("td")
                    )

                    if (
                        cells.count() < 4
                    ):
                        continue

                    registrants.append(
                        {
                            "Registrant":
                                cells.nth(0)
                                .inner_text()
                                .strip(),

                            "Address":
                                cells.nth(1)
                                .inner_text()
                                .strip(),

                            "Status":
                                cells.nth(2)
                                .inner_text()
                                .strip(),

                            "Details":
                                cells.nth(3)
                                .inner_text()
                                .strip(),
                        }
                    )

                except PlaywrightError:
                    continue

            return {
                "url": page.url,
                "title": page.title(),
                "registrants": registrants,
            }

    except PlaywrightError as error:

        raise RuntimeError(
            f"ECHA detail search failed: "
            f"{error}"
        ) from error

    except Exception as error:

        raise RuntimeError(
            f"Unexpected ECHA detail error: "
            f"{error}"
        ) from error