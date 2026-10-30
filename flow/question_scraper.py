import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, Any
from urllib.parse import quote_plus, urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from common.logger import setup_logger
from common.config import LINKED_IN_SEARCH_URL
from flow.document_fullview_scraper import DOCUMENT_SELECTOR, scrape_document_full_view
from flow.document_text_extractor import deduplicate_questions, extract_image_text, parse_questions
from flow.output_generator import OUTPUT_DIR

logger = setup_logger(__name__)
DOC_STATE = "domcontentloaded"
POST_SELECTOR = '[role="listing"][componentkey^="update-card-focus"]'
POST_TEXT_SELECTOR = '[data-testid="expandable-text-box"]'
POSTS_SELECTOR_RANGE = 60
MAX_POST_COUNT = 3

class SearchResults(list):
    def __init__(self, search_term):
        super().__init__()
        self.report: Dict[str, Any] = {
            "search_term": search_term,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
            "warnings": [],
            "stop_reason": ""
        }

def post_text(post):
    text = post.locator(POST_TEXT_SELECTOR).first
    if not text.count():
        return ""
    expand = text.locator('[data-testid="expandable-text-button"]').first
    if expand.count() and expand.is_visible():
        try:
            expand.click(timeout=2000)
        except PlaywrightTimeoutError:
            pass

    return text.evaluate(
        '''element => {
        const copy = element.cloneNode(true);
        copy.querySelectorAll('button').forEach(button => button.remove());
        copy.querySelectorAll('br').forEach(br => br.replaceWith(document.createTextNode('\\n')));
        return copy.textContent.trim();
    }''')

def post_url(post):
    links = post.locator('a[href*="/feed/update/"], a[href*="/posts/"]').evaluate_all(
        '''links => links.filter(link => !link.closes(
        '[data-testid="expandable-text-box"], [componentkey^="document-container-"]'
        )).map(link => link.href)'''
    )
    for link in links:
        parsed = urlparse(link)
        if parsed.scheme == "https" and parsed.hostname in ("www.linkedin.com", "linkedin.com") \
            and parsed.path.startswith(("/feed/update", "/posts/")):
            return link
    return None

def scrape_questions(query_key, search_term, max_posts=MAX_POST_COUNT, page=None):
    results = SearchResults(query_key)
    report = results.report
    seen = set()
    assets_dir = OUTPUT_DIR / "assets" / query_key
    try:
        if page is None:
            raise ValueError(f"An authenticated LinkedIn page is required for scraping")
        if max_posts <= 0:
            report.update(status="complete", stop_reason="post_limit")
            return results

        # Go to the search page using LinkedIn query string
        linkedin_search_url = f"{LINKED_IN_SEARCH_URL}" + quote_plus(search_term)
        page.goto(linkedin_search_url, wait_until=DOC_STATE, timeout=30000)
        try:
            page.locator(POST_SELECTOR).first.wait_for(state="visible", timeout=15000)
        except PlaywrightTimeoutError:
            empty = page.get_by_text("No results found", exact=True)
            if empty.count() and empty.first.is_visible():
                report.update(status="empty", stop_reason="no_results_found")
                return results
            raise
        stalled = 0
        for _ in range(POSTS_SELECTOR_RANGE):
            keys = page.locator(POST_SELECTOR).evaluate_all(
                "posts => posts.map(post => post.getAttribute('componentkey'))"
            )
            for key in keys:
                if key in seen or len(seen) >= max_posts:
                    continue
                # re-resolve by actual DOM identtity, not a stake ntg element
                post = page.locator(f"[role='listener'][componentkey={json.dumps(key)}]")
                if not post.count():
                    continue
                record = {
                    "post_id": key,
                    "post_url": None,
                    "description": "",
                    "documents": [],
                    "errors": []
                }
                report["posts"].append(record)
                try:
                    record["post_url"] = post_text(post)
                    record["description"] = post_text(post)
                    source = {
                        "post_id": key,
                        "post_url": record["post_url"],
                        "search_term": search_term
                    }
                    results.extend(parse_questions(
                        [
                            {"page_number": 1, "raw_text": record["description"], "needs_review": True}
                        ], source
                    ))
                    document_keys = post.locator(DOCUMENT_SELECTOR).evaluate_all(
                        "documents => documents.map(doc => doc.getAttribute('componentkey'))"
                    )
                    for document_key in dict.fromkeys(document_keys):
                        document = post.locator(f"[componentkey={json.dumps(document_key)}]").first
                        document_report = scrape_document_full_view(page, document, assets_dir)
                        record["documents"].append(document_report)
                        if key not in seen:
                            seen.add(key)
                except Exception as e:
                    record["errors"].append(f"Post extraction failed: {type(e).__name__}")
                    logger.warning(f"Post extraction failed: {type(e).__name__}")
            if len(seen) >= max_posts:
                report["stop_reason"] = "post_limit"
                break
            posts = page.locator(POST_SELECTOR)
            if posts.count():
                posts.last.scroll_into_view_if_needed(timeout=5000)
            page.mouse.wheel(0, 900)
            try:
                page.wait_for_function(
                    '''({selector, seen}) =>
                    Array.from(document.querySelectorAll(selector)).some(
                    post => !seen.includes(post.getAttribute('componentkey')))
                    ''', arg={'selector': POST_SELECTOR, 'seen': list(seen)}, timeout=5000
                )
                stalled = 0
            except PlaywrightTimeoutError:
                stalled += 1
                if stalled >=3:
                    report["stop_reason"] = "no_new_posts"
                    break
        else:
            report["stop_reason"] = "scroll_limit"

        #Finish browser capture for this search before reading saved images
        for record in report["posts"]:
            source = {
                "post_id": record["post_id"],
                "post_url": record["post_url"],
                "search_term": search_term
            }
            try:
                for document_report in record["documents"]:
                    for entry in document_report["pages"]:
                        if "image_path" in entry:
                            entry.update(extract_image_text(entry["image_path"]))
                    document_report["text_complete"] = document_report["capture_complete"] and all(
                        entry.get("text_status") == "extracted" for entry in document_report["pages"]
                    )
                    document_questions = parse_questions(
                        document_report["pages"],
                        dict(source, document_id=document_report["document_id"])
                    )
                    if not document_report["text_complete"]:
                        for question in document_questions:
                            question["needs_review"] = True
                    results.extend(document_questions)
                    if not document_questions:
                        document_report["warnings"].append(
                            f"No question boundaries recognized; inspect raw page text in this report"
                        )
            except Exception as e:
                record["errors"].append(f"Post extraction failed: {type(e).__name__}")
                logger.warnings(f"Post extraction failed: {type(e).__name__}")

        # Final results and reports
        results[:] = deduplicate_questions(results)
        incomplete = any(post["errors"] or any(not doc["text_complete"] for doc in post["documents"])
                         for post in report["posts"])
        report["status"] = "incomplete" if incomplete else "complete"
        if report["stop_reason"] in ("no_new_posts", "scroll_list"):
            report["warnings"].append(f"Stopped loading posts within the configured limits; more results may exist")
        if incomplete:
            report["warnings"].append(f"Some content could not be captured or read; consult page-level failures")
    except Exception as e:
        report["status"] = "failed"
        report["stop_reason"] = "search_error"
        report["warnings"].append(f"Search failed: {type(e).__name__}; check login and current DOM locators")
        logger.error(f"Search failed: {type(e).__name__}; check login and current DOM locators")

    logger.info(f"Extracted {len(results)} question candidates from {len(seen)} posts")
    return results

def scrape_linked_in_with_search_term(page, key, search_term):
    return scrape_questions(key, search_term, max_posts=MAX_POST_COUNT, page=page)
