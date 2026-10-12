# --------------------------------------------------
# ECHA CONSENT
# --------------------------------------------------
def handle_echa_consent(page):
    """
    Handle the cookie banner and possible ECHA legal notice.

    Returns True if a consent button was clicked.
    """
    consent_clicked = False

    cookie_button_names = [
        "Accept only essential cookies",
        "Accept all cookies",
    ]

    for button_name in cookie_button_names:
        try:
            button = page.get_by_role(
                "button",
                name=button_name,
                exact=False,
            ).first

            if button.count() > 0 and button.is_visible():
                print(
                    f"Clicking ECHA consent button: {button_name}",
                    flush=True,
                )

                button.click(timeout=10000)
                consent_clicked = True
                page.wait_for_timeout(1500)
                break

        except PlaywrightError as error:
            print(
                f"Cookie consent could not be clicked: {error}",
                flush=True,
            )

    # Handle an additional legal-notice button if ECHA shows one.
    legal_notice_names = [
        "I Accept the terms",
        "Accept the terms",
        "I accept",
        "Accept",
    ]

    for button_name in legal_notice_names:
        try:
            button = page.get_by_role(
                "button",
                name=button_name,
                exact=False,
            ).first

            if button.count() > 0 and button.is_visible():
                print(
                    f"Clicking ECHA legal-notice button: {button_name}",
                    flush=True,
                )

                button.click(timeout=10000)
                consent_clicked = True
                page.wait_for_timeout(1500)
                break

        except PlaywrightError:
            continue

    return consent_clicked


# --------------------------------------------------
# ECHA SEARCH
# --------------------------------------------------
def search_echa(cas_number):
    results = []

    cas_number = str(cas_number).strip()

    if not cas_number:
        return results

    print(
        f"ECHA search started for CAS {cas_number}",
        flush=True,
    )

    try:
        with sync_playwright() as playwright:
            browser = None
            context = None

            try:
                browser = playwright.chromium.launch(
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

                search_url = build_search_url(cas_number)

                print(
                    f"Searching ECHA for {cas_number}",
                    flush=True,
                )

                response = page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                if response is not None and response.status >= 400:
                    raise RuntimeError(
                        f"ECHA returned HTTP status {response.status}"
                    )

                page.wait_for_timeout(2000)

                # Handle cookie and legal notice.
                consent_clicked = handle_echa_consent(page)

                # Reload the actual search URL after consent.
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

                # Give the SPA time to initialise.
                page.wait_for_timeout(3000)

                print(
                    "PAGE TITLE:",
                    page.title(),
                    flush=True,
                )

                print(
                    "CURRENT URL:",
                    page.url,
                    flush=True,
                )

                # Check whether the legal notice is still active.
                try:
                    body_text = page.locator("body").inner_text(
                        timeout=10000
                    )
                except PlaywrightError:
                    body_text = ""

                if (
                    "European Chemicals Agency"
                    in body_text
                    and "Legal notice" in body_text
                    and cas_number not in body_text
                ):
                    print(
                        "ECHA is still displaying the legal notice.",
                        flush=True,
                    )

                # Only select rows that actually contain td elements.
                rows = page.locator(
                    "table tbody tr:has(td)"
                )

                try:
                    rows.first.wait_for(
                        state="visible",
                        timeout=30000,
                    )
                except PlaywrightTimeoutError:
                    print(
                        f"No ECHA result rows were loaded for "
                        f"{cas_number}",
                        flush=True,
                    )

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

                    return []

                row_count = rows.count()

                print(
                    f"ECHA DATA ROW COUNT: {row_count}",
                    flush=True,
                )

                for index in range(row_count):
                    row = rows.nth(index)

                    try:
                        cells = row.locator("td")
                        cell_count = cells.count()

                        cell_values = []

                        for cell_index in range(cell_count):
                            value = (
                                cells.nth(cell_index)
                                .inner_text(timeout=5000)
                                .strip()
                            )
                            cell_values.append(value)

                        print(
                            f"ROW {index} CELLS: {cell_values}",
                            flush=True,
                        )

                        # Ignore rows that do not contain the searched CAS.
                        row_text = " | ".join(cell_values)

                        if cas_number not in row_text:
                            print(
                                f"Skipping row {index}: "
                                f"CAS number not present",
                                flush=True,
                            )
                            continue

                        if cell_count < 3:
                            print(
                                f"Skipping row {index}: "
                                f"only {cell_count} cells",
                                flush=True,
                            )
                            continue

                        # Find the detail link in the matching row.
                        links = row.locator("a[href]")
                        relative_url = None

                        for link_index in range(links.count()):
                            candidate = links.nth(link_index).get_attribute(
                                "href"
                            )

                            if candidate:
                                relative_url = candidate
                                break

                        if not relative_url:
                            print(
                                f"Skipping row {index}: "
                                f"no detail link found",
                                flush=True,
                            )
                            continue

                        if relative_url.startswith("/"):
                            full_url = ECHA_BASE_URL + relative_url
                        elif relative_url.startswith("http"):
                            full_url = relative_url
                        else:
                            full_url = (
                                ECHA_BASE_URL
                                + "/"
                                + relative_url.lstrip("/")
                            )

                        # Your original column order is retained here.
                        name = cell_values[0]
                        ec_number = cell_values[1]
                        found_cas = cell_values[2]

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
                            f"Could not process row {index}: {error}",
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
                    context.close()

                if browser is not None:
                    browser.close()

    except RuntimeError:
        raise

    except Exception as error:
        raise RuntimeError(
            f"The Playwright service could not be started: {error}"
        ) from error