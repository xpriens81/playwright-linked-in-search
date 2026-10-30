import hashlib
import re
import time
import random
from pathlib import Path
from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from common.logger import setup_logger

logger = setup_logger(__name__)

# Full view specific selectors
DOCUMENT_SELECTOR = '[componentkey^="document-container-"]'
FULL_VIEW_PAGE_VIEWER_PATTERN = 'div[componentkey^="document-container-"]'
FULL_VIEW_PAGE_SLIDER_PATTERN = 'div[aria-label="Slide to navigate to a page"]'
FULL_VIEW_EXIT_BUTTON_LOCATORS = [
    {"strategy": "role", "role": "button", "name": "Exit full screen"}
]
FULL_VIEW_NEXT_BUTTON_LOCATORS = [
    {"strategy": "role", "role": "button", "name": "Go to next page of document"}
]
FULL_VIEW_PREV_BUTTON_LOCATORS = [
    {"strategy": "role", "role": "button", "name": "Go to previous page of document"}
]

# Timeouts
ENTER_FULL_VIEW_TIMEOUT = 10000
PAGE_LOAD_TIMEOUT = 5000
NAVIGATION_TIMEOUT = 5000
EXIT_FULL_VIEW_TIMEOUT = 5000

def build_locator(root, definition):
    strategy = definition["strategy"]
    exact = definition.get("exact", True)

    if strategy == "role":
        return root.get_by_role(definition["role"], name=definition["name"], exact=exact)
    if strategy == "label":
        return root.get_by_label(definition["name"], exact=exact)
    if strategy == "placeholder":
        return root.get_by_placeholder(definition["name"], exact=exact)
    if strategy == "css":
        return root.locator(definition["selector"])
    raise ValueError(f"Unsupported locator strategy: {strategy!r}")

def find_first_visible_locator(page, locator_definition, timeout=3000):
    deadline = time.monotonic() + (timeout / 1000)
    locators = [(definition, build_locator(page, locator_definition)) for definition in locator_definition]

    while time.monotonic() < deadline:
        for definition, locator in locators:
            try:
                count = locator.count()
                if count == 1 and locator.is_visible() and locator.is_enabled():
                    return locator, definition
                logger.debug(f"*** ({count})\tDefinition: {definition} | Locator: {locator} | "
                             f"Visible: {locator.is_visible()} | Enabled: {locator.is_enabled()}")
            except PlaywrightError as e:
                logger.debug(f"Locator check failed: {definition} - {e}")
                continue

        page.wait_for_timeout(100)

    return None, None

def find_first_visible_locator_for_paging(page, locator_definitions, timeout=3000):
    deadline = time.monotonic() + (timeout / 1000)

    navigation_section = page.locator(
        FULL_VIEW_PAGE_SLIDER_PATTERN
    ).filter(has=page.get_by_role("slider"))

    # This is the main page viewer where the next/prev buttons exist for the full view page
    viewer = page.locator(
        FULL_VIEW_PAGE_VIEWER_PATTERN + ":visible"
    ).filter(has=navigation_section)

    locators = [
        (definition, build_locator(viewer, definition))
        for definition in locator_definitions
    ]

    while time.monotonic() < deadline:
        try:
            viewer_count = viewer.count()
            for definition, locator in locators:
                visible_buttons = [
                    button for button in locator.all()
                    if button.is_visible()
                ]

                if len(visible_buttons) > 1:
                    logger.warning(f"Ambiguous paging button inside viewer. Definition: {definition}")
                    return None, None

                if len(visible_buttons) == 1:
                    button = visible_buttons[0]
                    if button.is_enabled():
                        logger.info(f"Found viewer paging button: {definition}")
                        return button, definition
        except PlaywrightError as e:
            logger.debug(f"Viewer paging lookup failed: {e}")

        page.wait_for_timeout(100)

    return None, None

def can_enter_full_view(page, document):
    try:
        document.scroll_into_view_if_needed(timeout=5000)
        page_buttons = document.get_by_role("button", name=re.compile(r"Page\s+\d+\s+of")).all()
        if page_buttons:
            logger.info(f"Document supports full-view mode")
            return True

        logger.info(f"Document does not supports full-view mode")
        return False
    except Exception as e:
        logger.warning(f"Error checking full-view compatibility: {e}")
        return False

def enter_full_view_mode(page, document):
    try:
        document.scroll_into_view_if_needed(timeout=5000)
        page.wait_for_timeout(500)

        # Find and click the Page button to enter full-view mode
        page_button = document.get_by_role("button", name=re.compile(r"Page\s+\d+\s+of")).first
        if not page_button.count():
            logger.warning(f"Page button not found; cannot enter full-view")
            return False
        if not page_button.is_visible():
            logger.warning(f"Page button not visible; cannot enter full-view")
            return False

        logger.info(f"Clicking page button to enter full-view mode...")
        page_button.click(timeout=ENTER_FULL_VIEW_TIMEOUT)

        # Wait for full-view modal to appear
        page.wait_for_timeout(500)

        # Verify we are in full-view by checking for exit button
        exit_button, _ = find_first_visible_locator(
            page, FULL_VIEW_EXIT_BUTTON_LOCATORS, timeout=ENTER_FULL_VIEW_TIMEOUT
        )

        if exit_button:
            logger.info(f"Successfully entered full-view mode")
            return True
        logger.warning(f"Could not confirm the full-view mode")
        return False
    except PlaywrightTimeoutError as e:
        logger.error(f"Timeout entering full-view mode: {e}")
        return False
    except Exception as e:
        logger.error(f"Error entering full-view mode: {e}")
        return False

def get_full_view_page_info(page):
    page_counter_pattern = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*")

    try:
        navigation_section = page.locator(
            FULL_VIEW_PAGE_SLIDER_PATTERN
        ).filter(has=page.get_by_role("slider"))
        viewer = page.locator(
            FULL_VIEW_PAGE_VIEWER_PATTERN
        ).filter(has=navigation_section)

        viewer_count = viewer.count()
        if viewer_count != 1:
            logger.warning(f"Expected 1 document viewer with a navigation slider;"
                           f" found {viewer_count}. Cannot read page info.")
            return None

        page_counter = viewer,logger("p:visible").filter(
            has_text=page_counter_pattern
        )

        # Wait for the page counter to be visible and extract the current and total pages
        expect(page_counter).to_be_visible(timeout=PAGE_LOAD_TIMEOUT)
        counter_text = page_counter.inner_text(timeout=PAGE_LOAD_TIMEOUT).strip()
        match = page_counter_pattern.fullmatch(counter_text)
        if not match:
            logger.warning(f"Could not parse page counter text: {counter_text!r}")
            return None

        current_page = int(match.group(1))
        total_pages = int(match.group(2))
        if not 1<= current_page <= total_pages:
            logger.warning(f"Invalid page numbers: current={current_page}, total={total_pages}")
            return None

        next_button = find_first_visible_locator_for_paging(
            page, FULL_VIEW_NEXT_BUTTON_LOCATORS, timeout=1000
        )
        prev_button = find_first_visible_locator_for_paging(
            page, FULL_VIEW_PREV_BUTTON_LOCATORS, timeout=1000
        )
        info = {
            "current_page": current_page,
            "total_pages": total_pages,
            "has_next": next_button is not None and next_button.is_enabled(),
            "has_prev": prev_button is not None and prev_button.is_enabled()
        }
        logger.info(f"Page Info. Current: {current_page}, Total: {total_pages}, "
                    f"Has Next: {info['has_next']}, Has Prev: {info['has_prev']}")
        return info
    except PlaywrightError as e:
        logger.error(f"Error reading full-view page info: {e}")
        return None

def capture_full_view_screenshot(page, page_number, assets_dir, document_key):
    try:
        filename = Path(assets_dir) / f"{document_key}-fv-page-{page_number}.png"
        Path(assets_dir).mkdir(parents=True, exist_ok=True)

        # Capture the full view page screenshot
        logger.info(f"Capturing full-view screenshot for the page {page_number} at {filename}")
        page.screenshot(path=str(filename), full_page=False)

        if not filename.exists():
            logger.error(f"Screenshot file was not created: {filename}")
            return None

        logger.info(f"Screenshot saved: {filename}")

        return {
            "page_number": page_number,
            "image_path": str(filename),
            "capture_status": "captured",
            "capture_method": "full-view"
        }
    except Exception as e:
        logger.error(f"Error capturing full-view screenshot for page {page_number}: {e}")
        return None

def navigate_full_view_next_page(page):
    counter_pattern = re.compile(r"^\s*(\d+)\s*/\s*(\d+)\s*")
    try:
        navigation_section = page.locator(
            FULL_VIEW_PAGE_SLIDER_PATTERN
        ).filter(has=page.get_by_role("slider"))
        viewer = page.locator(
            FULL_VIEW_PAGE_VIEWER_PATTERN + ":visible"
        ).filter(has=navigation_section)

        # Auto-retry until exactly one matching viewer exists
        expect(viewer).to_have_count(1, timeout=NAVIGATION_TIMEOUT)
        counter = viewer.locator("p:visible").filter(
            has_text=counter_pattern
        )
        expect(counter).to_have_current_page(1, timeout=PAGE_LOAD_TIMEOUT)

        next_button, _ = find_first_visible_locator_for_paging(
            page, FULL_VIEW_NEXT_BUTTON_LOCATORS,
            timeout=NAVIGATION_TIMEOUT
        )
        if next_button is None:
            logger.info("No enabled next-page button found")
            return False

        # Capture the starting position immediately beore clicking
        counter_text = counter.inner_text(
            timeout=PAGE_LOAD_TIMEOUT
        ).strip()
        match = counter_pattern.fullmatch(counter_text)
        if not match:
            logger.warning(f"Invalid page counter: {counter_text!r}")
            return False

        current_page = int(match.group(1))
        total_pages = int(match.group(2))
        if not 1 <= current_page <= total_pages:
            logger.info(f"Cannot advance from counter: {counter_text!r}")
            return False

        expected_page = current_page + 1
        expected_counter = re.compile(
            rf"^\s*{expected_page}\s*/\s*{total_pages}\s*$"
        )

        next_button.click(
            delay=random.randint(100, 300),
            timeout=NAVIGATION_TIMEOUT
        )

        # Re-resolves the locator and retries until the expected text appears
        expect(counter).to_have_text(
            expected_counter,
            timeout=PAGE_LOAD_TIMEOUT
        )

        logger.info(f"Confirmed navigation: {expected_page}/{total_pages}")
        return True
    except (PlaywrightError, AssertionError) as e:
        logger.error(f"Error navigating to next page in full-view: {e}")
        return False

def exit_full_view_mode(page):
    try:
        exit_button, _ = find_first_visible_locator(
            page, FULL_VIEW_EXIT_BUTTON_LOCATORS, timeout=EXIT_FULL_VIEW_TIMEOUT
        )
        if not exit_button:
            logger.warning(f"Could not find exit button; attempting fallback close")
            # Try pressing Escape key as a fallback
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            return True

        logger.info(f"Clicking exit full-view button...")
        exit_button.click(timeout=EXIT_FULL_VIEW_TIMEOUT)
        page.wait_for_timeout(500)
        logger.info(f"Successfully exited full-view mode")
        return True
    except Exception as e:
        logger.error(f"Error exiting full-view mode: {e}")
        return False

def scrape_document_full_view(
        page, document,
        assets_dir, max_pages=100, timeout_seconds=120):
    document_id = document.get_attribute("componentkey") or "unknown-document"
    key = hashlib.sha256(document_id.encode("utf-8")).hexdigest()[:16]

    report = {
        "document_id": document_id,
        "strategy": "full-view",
        "expected_pages": 0,
        "captured_pages": 0,
        "pages": [],
        "missing_pages": [],
        "warnings": [],
        "capture_complete": False,
        "text_complete": False,
        "stop_reason": "not_started"
    }

    captured = {}
    deadline = time.monotonic() + timeout_seconds
    entry_attempted = False

    try:
        # Check if full-view is available
        if not can_enter_full_view(page, document):
            report["stop_reason"] = "full_view_not_available"
            logger.warning(f"Full-view mode is not available for this document")
            return report

        # Enter full-view mode if available
        entry_attempted = True
        if not enter_full_view_mode(page, document):
            logger.error(f"Failed to enter full-view mode")
            report["stop_reason"] = "failed_to_enter_full_view"
            report["warnings"].append("Could not enter full-view mode")
            return report

        # Get initial page info
        page_info = get_full_view_page_info(page)
        if not page_info:
            logger.error(f"Count not get page infor in full-view")
            report["stop_reason"] = "no_page_info"
            report["warnings"].append("Count not read full-view page information")
            return report

        report["expected_pages"] = page_info["total_pages"]
        current_page = page_info["current_page"]
        total_pages = min(page_info["total_pages"], max_pages)

        logger.info(f"Starting full-view extraction: {current_page}/{total_pages} pages")

        # Process each page now
        while current_page <= total_pages and time.monotonic() < deadline:
            if current_page in captured:
                # Already captured this page
                if not navigate_full_view_next_page(page):
                    report["stop_reason"] = "end_of_document"
                    break

                page_info = get_full_view_page_info(page)
                if page_info:
                    current_page = page_info["current_page"]
                else:
                    report["stop_reason"] = "page_info_error"
                    break
                continue

            try:
                # Capture screenshot now
                capture_result = capture_full_view_screenshot(
                    page, current_page, assets_dir, key
                )
                if not capture_result:
                    report["warnings"].append(f"Failed to capture screenshot for page {current_page}")
                    captured[current_page] = {
                        "page_number": current_page,
                        "capture_status": "failed",
                        "raw_text": "",
                        "text_status": "unavailable"
                    }
                else:
                    capture_result.update(raw_text="", text_status="pending", needs_revise=True)
                    captured[current_page] = capture_result
                    logger.info(f"Page {current_page} captured successfully")
            except Exception as e:
                logger.error(f"Error processing page {current_page}: {e}")
                captured[current_page] = {
                    "page_number": current_page,
                    "capture_status": "error",
                    "raw_text": "",
                    "text_status": "failed",
                    "error": str(e)
                }

            # Navigate to the next page if possible
            if current_page < total_pages:
                if not navigate_full_view_next_page(page):
                    logger.info(f"No more pages avaulable after page {current_page}")
                    report["stop_reason"] = "end_of_document"
                    break

                page_info = get_full_view_page_info(page)
                if page_info:
                    current_page = page_info["current_page"]
                else:
                    logger.error(f"Could not get updated page info for page {current_page}")
                    report["stop_reason"] = "page_info_error"
                    break
            else:
                report["stop_reason"] = (
                    "page_limit" if total_pages < report["expected_pages"] else "complete"
                )
                break

        # Check for timeout
        if time.monotonic() >= deadline:
            report["stop_reason"] = "time_limit"
            logger.warning(f"Full-view scraping exceeded time limit")
    except Exception as e:
        logger.error(f"Unexpected error in full-view scraping: {e}")
        report["stop_reason"] = "scrape_error"
        report["warnings"].append(f"Full-view scraping failed: {e}")
    finally:
        if entry_attempted:
            try:
                if not exit_full_view_mode(page):
                    report["warnings"].append("Failed to exit full-view mode cleanly")
            except Exception as e:
                logger.warning(f"Error during exit: {e}")
                report["warnings"].append(f"Could not exit full-view mode: {e}")

    # Compile results
    successful_pages = {number for number, entry in captured.items()
                        if entry["capture_status"] == "captured"}
    report["captured_pages"] = len(successful_pages)
    report["missing_pages"] = [n for n in range(1, report["expected_pages"] + 1)
                               if n not in successful_pages]
    report["capture_complete"] = bool(report["expected_pages"]) and not report["missing_pages"]
    if report["stop_reason"] == "complete" and not report["capture_complete"]:
        report["stop_reason"] = "capture_incomplete"

    for number in sorted(captured.keys()):
        report["pages"].append(captured[number])

    report["text_complete"] = report["capture_complete"] and all(
        page.get("text_status") == "extracted" for page in report["pages"]
    )
    logger.info(f"Full-view scraping complete: {report['captured_pages']}/{report['expected_pages']} pages; "
                f"text complete: {report['text_complete']}")

    return report