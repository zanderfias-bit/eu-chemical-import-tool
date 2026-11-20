import subprocess
import sys

from playwright.sync_api import sync_playwright


ECICS_BASE_URL = (
    "https://ec.europa.eu/"
    "taxation_customs/dds2/ecics/"
)

ECICS_SEARCH_URL = (
    ECICS_BASE_URL
    + "chemicalsubstance_consultation.jsp"
)


def build_ecics_url(ec_number):
    """
    Build the ECICS search URL for an EC number.
    """
    return (
        f"{ECICS_SEARCH_URL}"
        f"?Lang=en"
        f"&Cas="
        f"&Cus="
        f"&CnCode="
        f"&EcCode={ec_number}"
        f"&UnCode="
        f"&Name="
        f"&LangNm=en"
        f"&NomenclatureSystem="
        f"&Inchi="
        f"&Inchikey="
        f"&Characteristic="
        f"&sortOrder=1"
        f"&Expand=true"
        f"&offset=0"
        f"&viewVal="
        f"&isVisitedRef=true"
    )


def install_chromium():
    """
    Install the Chromium version required by the
    currently installed Playwright version.

    This is mainly a fallback for Streamlit Cloud
    when the Playwright package is available but
    the matching Chromium binary is missing.
    """
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "playwright",
                "install",
                "chromium",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": (
                "Chromium installation timed out."
            ),
        }

    except Exception as error:
        return {
            "success": False,
            "message": (
                "Could not start the Chromium "
                "installation: "
                f"{error}"
            ),
        }

    if result.returncode != 0:
        error_text = (
            result.stderr.strip()
            or result.stdout.strip()
            or "Unknown installation error."
        )

        return {
            "success": False,
            "message": (
                "Playwright Chromium installation "
                "failed: "
                f"{error_text}"
            ),
        }

    return {
        "success": True,
        "message": (
            "Chromium installed successfully."
        ),
    }


def launch_chromium(playwright):
    """
    Launch Chromium.

    If the browser executable is missing, install
    the matching Playwright Chromium binary and
    try one more time.
    """
    try:
        return playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

    except Exception as error:
        error_text = str(error)

        missing_browser_indicators = (
            "Executable doesn't exist",
            "playwright install",
        )

        browser_missing = any(
            indicator in error_text
            for indicator in missing_browser_indicators
        )

        if not browser_missing:
            raise

        installation_result = (
            install_chromium()
        )

        if not installation_result[
            "success"
        ]:
            raise RuntimeError(
                installation_result[
                    "message"
                ]
            ) from error

        return playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )


def get_goods_code(ec_number):
    """
    Search ECICS by EC number and return the first
    matching chemical result.

    ECICS is accessed using Playwright/Chromium
    because the result page is scraped from the
    rendered ECICS website.
    """
    if ec_number is None:
        return {
            "success": False,
            "message": (
                "No EC number was provided."
            ),
        }

    ec_number = str(
        ec_number
    ).strip()

    if not ec_number:
        return {
            "success": False,
            "message": (
                "No EC number was provided."
            ),
        }

    url = build_ecics_url(
        ec_number
    )

    browser = None

    try:
        with sync_playwright() as playwright:
            browser = launch_chromium(
                playwright
            )

            page = browser.new_page(
                viewport={
                    "width": 1280,
                    "height": 900,
                }
            )

            page.goto(
                url,
                timeout=60000,
                wait_until="domcontentloaded",
            )

            page.wait_for_timeout(
                5000
            )

            tables = page.locator(
                "table"
            )

            table_count = tables.count()

            if table_count < 3:
                page_title = (
                    page.title()
                )

                return {
                    "success": False,
                    "message": (
                        "ECICS result table not found. "
                        f"Tables found: {table_count}. "
                        f"Page title: {page_title}"
                    ),
                    "url": url,
                }

            # In the existing ECICS implementation,
            # table 2 contains the required result data.
            table = tables.nth(
                2
            )

            rows = table.locator(
                "tr"
            )

            row_count = rows.count()

            for row_index in range(
                1,
                row_count,
            ):
                try:
                    cells = (
                        rows
                        .nth(
                            row_index
                        )
                        .locator(
                            "td"
                        )
                    )

                    cell_count = (
                        cells.count()
                    )

                    if cell_count < 6:
                        continue

                    cus_number = (
                        cells
                        .nth(
                            0
                        )
                        .inner_text()
                        .strip()
                    )

                    goods_code = (
                        cells
                        .nth(
                            1
                        )
                        .inner_text()
                        .strip()
                    )

                    cas_number = (
                        cells
                        .nth(
                            2
                        )
                        .inner_text()
                        .strip()
                    )

                    ec_result = (
                        cells
                        .nth(
                            3
                        )
                        .inner_text()
                        .strip()
                    )

                    substance_name = (
                        cells
                        .nth(
                            5
                        )
                        .inner_text()
                        .strip()
                    )

                    if not goods_code:
                        continue

                    return {
                         "success": True,
                        "ec_number": (
                            ec_result
                        ),
                        "goods_code": (
                            goods_code
                        ),
                        "cus_number": (
                            cus_number
                        ),
                        "cas_number": (
                            cas_number
                        ),
                        "substance_name": (
                            substance_name
                        ),
                        "url": url,
                    }

                except Exception as row_error:
                    print(
                        "ECICS row parsing error:",
                        row_error,
                    )

            return {
                "success": False,
                "message": (
                    "No matching ECICS record "
                    "was found in the result table."
                ),
                "url": url,
            }

    except Exception as error:
        return {
            "success": False,
            "message": (
                "ECICS Playwright lookup failed: "
                f"{error}"
            ),
            "url": url,
        }

    finally:
        if browser is not None:
            try:
                browser.close()

            except Exception:
                pass