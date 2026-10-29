# Instructions for AI Coding Agents

> **Audience:** AI agents working on this repository. Follow this file as project-specific guidance; it is not end-user setup documentation. `Readme.md` is the user guide.

## Project purpose

This is a Python project using Playwright's synchronous API to open LinkedIn in a visible Chrome browser, attempt authentication, and begin a search-results flow for interview-question topics. Treat the scraper as work in progress: do not describe planned or incomplete behavior as already working.

## Repository map

- `main.py` — entry point, validates configuration, opens one authenticated session, loops over the configured search topics, and closes the browser.
- `flow/linkedin_auth.py` — browser launch, locator definitions, LinkedIn login detection and submission, and reuse of saved browser state.
- `flow/question_scraper.py` — search navigation and the in-progress results/report structure.
- `common/config.py` — environment-variable loading and defaults.
- `common/session_manager.py` — reads, validates, writes, and deletes the Playwright storage-state file. The default state is considered stale after one day.
- `common/logger.py` — shared console logger.
- `common/screenshot.py` — captures error screenshots under `screenshots/`.
- `requirements.txt` — Python dependencies.

## Runtime flow

1. `main.py` calls `validate_config()`; `LINKEDIN_USER` and `LINKEDIN_PASSWORD` must be set.
2. `login_to_linkedin()` attempts to reuse a storage-state file that is no more than one day old. If it cannot reuse an authenticated state, it launches visible Chrome, navigates to LinkedIn, checks for login or authenticated-page locators, and attempts a credential-based login.
3. The context state is saved to `SESSION_FILE`.
4. `main.py` iterates the fixed `queries` mapping (`Playwright` and `SQL`) and passes each configured search string to `scrape_linked_in_with_search_term()`.
5. The browser and Playwright session are closed in `finally`; login/execution errors trigger screenshot attempts.

## Current implementation status

The search-results flow is incomplete. `question_scraper.py` currently navigates to the configured search URL and waits for a listing or a timeout; it does not yet extract and return completed question results. `main.py` does not write the configured Markdown filenames. Do not claim that scraping, report generation, or file export is complete unless the implementation has actually been added and verified.

The current checkout also has apparent runtime blockers outside the search flow: `common/logger.py`'s formatter assumes every log level has a color, and `flow/linkedin_auth.py` uses `sync_playwright().session` and `session.chrome`, which are not the standard Python Playwright sync API. Treat run instructions as intended usage, not evidence that the current checkout completes startup. If asked to fix these issues, inspect the installed/API version and add focused validation before documenting the flow as runnable.

## Change guidance

- Keep changes within the requested scope. Do not alter application code when asked only to write or revise documentation.
- Before changing behavior, read the relevant flow and its callers; update directly related documentation when behavior changes.
- Preserve the synchronous Playwright approach and the existing separation between `main.py`, `flow/`, and `common/` unless the task calls for a deliberate redesign.
- Prefer accessible Playwright locators (roles, labels, and placeholders); use CSS selectors only when the page provides no suitable accessible locator. Wait for observable page states rather than adding arbitrary delays.
- Use the existing logger and session/screenshot helpers. Keep browser cleanup reliable, including on failure.
- Do not print, commit, or include `.env`, credentials, proxy credentials, browser storage state, or screenshots containing account data. Treat the storage-state JSON as an authentication secret.
- Do not add CAPTCHA/MFA bypasses, automation-detection evasion, or behavior intended to circumvent LinkedIn controls. Keep usage compliant with applicable site terms and account policies.
- Be precise about supported configuration and limitations. Verify any documented command or output against the current code rather than assuming the flow is complete.

## Validation

For Python changes, use the smallest relevant check available and report what was run. This repository currently has no visible test suite or project-defined test command. Do not run the LinkedIn workflow as a validation step unless explicitly requested; it opens a real browser and uses the configured account.
