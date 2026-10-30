from common.logger import setup_logger
from common.config import validate_config
from common.screenshot import capture_screenshot_on_error
from flow.linkedin_auth import close_browser_session, login_to_linkedin
from flow.question_scraper import scrape_linked_in_with_search_term
from flow.output_generator import generate_all_outputs

logger = setup_logger(__name__)
queries = {
    "Playwright": {
        "search_term": "Playwright Interview Queries",
        "description": "Playwright Interview Questions",
        "file": "playwright-interview-questions.md"
    },
    "SQL": {
        "search_term": "SQL Interview Queries",
        "description": "SQL Interview Questions",
        "file": "sql-interview-questions.md"
    }
}

def main():
    page = None
    browser = None
    session = None

    try:
        logger.info("START: === LinkedIn Interview Questions Scraper ===")

        # Validate configurations
        validate_config()

        # Create one live authenticated session and reuse it across the run
        page, browser, _, session = login_to_linkedin()

        # Scrape questions
        questions = {}
        for key in queries.keys():
            search_term = queries[key]["search_term"]
            logger.info(f"Scraping LinkedIn for '{key}' | Search Term: '{search_term}'")
            questions[key] = scrape_linked_in_with_search_term(page, key, search_term)
            logger.info(f"Found {len(questions[key])} questions for '{key}' | Search Term: {search_term}")

        # Generate output files
        for key, question_list in questions.items():
            output_file = queries[key]["file"]
            description = queries[key]["description"]
            search_term = queries[key]["search_term"]
            logger.info(f"Generating output for '${key}' | Search Term: '${search_term}'")
            if not generate_all_outputs(question_list, output_file, description):
                logger.error(f"Failed to write the latest search results for '{description}' under output folder")
            logger.info(f"Generated output for '${key}' | Search Term: '${search_term}'")
    except Exception as e:
        logger.error(f"Execution Failed: {e}")
        capture_screenshot_on_error(page, error_type="execution_failure")
    finally:
        close_browser_session(browser, session)
        logger.info("END: === LinkedIn Interview Questions Scraper ===")

    return 0

if __name__ == "__main__":
    exit(main())
