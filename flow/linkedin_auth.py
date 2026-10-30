import base64
import binascii
import random
import time
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError, sync_playwright

from common.logger import setup_logger
from common.config import (
    LINKEDIN_URL, LINKEDIN_USER, LINKEDIN_PASSWORD, CHROME_PATH,
    ENCODE_PROXY, PROXY_URL, DECRYPTION_KEY
)
from common.screenshot import capture_screenshot_on_error
from common.session_manager import is_session_file_valid, load_session_state, save_session_state
from encryption.credential_crypto import CredentialError, main as credential_crypto

logger = setup_logger(__name__)

DOC_STATE = "domcontentloaded"

# Define locators for LinkedIn here
# Sign In Page Locator
SIGN_IN_LOCATORS = [
    {"strategy": "role", "role": "link", "name": "Sign in"}
]

# Login Page Locators
USERNAME_LOCATORS = [
    {"strategy": "role", "role": "textbox", "name": "Email or phone"}
]
PASSWORD_LOCATORS = [
    {"strategy": "role", "role": "textbox", "name": "Password"}
]
SUBMIT_LOCATORS = [
    {"strategy": "role", "role": "button", "name": "Sign in"}
]

# Logged in Page Locators
LOGGED_IN_LOCATORS = [
    {"strategy": "role", "role": "button", "name": "Start a post"},
    {"strategy": "placeholder", "name": "Search"}
]

# Authenticated Keyworks for Login
AUTHENTICATED_URL_KEYWORDS = (
    "/feed",
    "/mynetwork",
    "/jobs",
    "/messaging",
    "/notifications"
)

def get_proxy_server():
    if not ENCODE_PROXY:
        logger.info(f"No proxy credentials configured. Launching browser without a proxy")
        return None
    encoded_proxy = credential_crypto("decrypt", DECRYPTION_KEY, ENCODE_PROXY)
    if not encoded_proxy:
        raise CredentialError("ENCODE_PROXY must not decrypt to an empty value")
    try:
        server = urlsplit(PROXY_URL)
        if not server.scheme or not server.hostname or server.username or server.password:
            raise ValueError
        username, separator, password = base64.b64decode(
            encoded_proxy, validate=True
        ).decode("utf-8").partition(":")
        if not separator or not username or not password:
            raise ValueError
    except (ValueError, UnicodeError, binascii.Error):
        raise CredentialError(
            "Invalid proxy configuration; check PROXY_URL and encrypted ENCODE_PROXY"
        ) from None

    logger.info(f"Using configured authentication proxy")
    return {
        "server": PROXY_URL,
        "username": username,
        "password": password
    }

def get_build_locators(root, definition):
    if definition.get('scope') is not None:
        root = get_build_locators(root, definition['scope'])

    strategy = definition['strategy']
    exact = definition.get("exact", True)
    if strategy == "role":
        return root.get_by_role(definition['role'], name=definition['name'], exact=exact)
    if strategy == "label":
        return root.get_by_label(definition['name'], exact=exact)
    if strategy == "placeholder":
        return root.get_by_role(definition['name'], exact=exact)
    if strategy == "css":
        return root.locator(definition['selector'])
    raise ValueError(f"Unsupported locator strategy: {strategy}")

def first_visible_locator(page, selectors, timeout=3000, poll_interval=250):
    deadline = time.monotonic() + (timeout/1000)
    last_error = None
    locators = [(definition, get_build_locators(page, definition)) for definition in selectors]

    # loop through all definition
    while time.monotonic() < deadline:
        for definition, locator in locators:
            try:
                count = locator.count()
                if count > 1:
                    raise RuntimeError(
                        f"Ambiguous locator: {definition!r} matched {count} elements. "
                        "Refine its role/name or add a scope"
                    )
                if count == 1 and locator.is_visible() and locator.is_enabled():
                    logger.info(f"Using locator: {definition}")
                    return locator, repr(definition)
            except PlaywrightError as e:
                last_error = e
                logger.warning(f"Locator not usable: {definition!r} - {e}")

    if last_error:
        logger.warning(f"No visible locator found. Last error: {last_error}")

    return None, None

def launch_browser(session):
    proxy_config = get_proxy_server()

    launch_kwargs = {
        "headless": False,
        "channel": "chrome",
        "args": ["--start-maximized"],
        "timeout": 30000,
        "ignore_default_args": ["--enable-automation"]
    }

    # Add proxy only if needed (generally within a corporate)
    if proxy_config is not None:
        launch_kwargs["proxy"] = proxy_config

    if CHROME_PATH != "chrome":
        launch_kwargs["executable_path"] = CHROME_PATH
        logger.info(f"Launching 'Chromium Browser' with custom executable path: %s", CHROME_PATH)

    try:
        return session.chrome.launch(**launch_kwargs)
    except PlaywrightError:
        raise RuntimeError(f"Browser launch failed; check browser and proxy configurations") from None

def create_browser_session():
    session = sync_playwright().start()

    try:
        browser = launch_browser(session)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Like Gecko) Chrome/120.0.0.0 Safari/537.36",
            no_viewport=True,
            ignore_https_errors=True
        )
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()
    except Exception as e:
        logger.error(f"Exception creating browser session/context: {e}")
        session.stop()
        raise

    logger.info(f"Stealth mode enabled; automation detection is masked")
    return page, browser, context, session

def normalize_session_state(page=None, browser=None, context=None, session=None):
    if page is not None:
        return page, browser, context or page.context, session

    if context is not None:
        return context.new_page(), browser, context, session

    return create_browser_session()

def open_linkedin_home(page):
    page.goto(LINKEDIN_URL, wait_until=DOC_STATE)
    page.wait_for_load_state(DOC_STATE)
    logger.info(f"Navigated to LinkedIn: {LINKEDIN_URL}")

def is_logged_in(page):
    page.wait_for_load_state(DOC_STATE)

    username_locator, _ = first_visible_locator(page, USERNAME_LOCATORS, 1500, 200)
    password_locator, _ = first_visible_locator(page, PASSWORD_LOCATORS, 1500, 200)
    if username_locator and password_locator:
        return False

    logged_in_locator, logged_in_selector = first_visible_locator(
        page,
        LOGGED_IN_LOCATORS,
        3000,
        200
    )
    if logged_in_locator:
        logger.info(f"User logged in: {logged_in_selector}")
        return True

    if any(keyword in page.url for keyword in AUTHENTICATED_URL_KEYWORDS):
        logger.info(f"User logged in: {page.url}")
        return True

    return False

def submit_login(page):
    sign_in_locator, sign_in_selector = first_visible_locator(page, SIGN_IN_LOCATORS, timeout=5000)
    if sign_in_locator:
        logger.info(f"Sign in button/link detected with locator: {sign_in_selector}")
        page.wait_for_timeout(1000) # Human like behavior, since linkedin is bot sensitive
        sign_in_locator.click()
    else:
        logger.info(f"No sign in button detected; Checking if login page is available")

    page.wait_for_load_state(DOC_STATE)
    username_locator, username_selector = first_visible_locator(page, USERNAME_LOCATORS, 10000)
    password_locator, password_selector = first_visible_locator(page, PASSWORD_LOCATORS, 10000)
    if not username_locator or not password_locator:
        raise RuntimeError(
            f"Unable to find LinkedIn login locators. "
            f"Username tried: {USERNAME_LOCATORS} | Password tried: {PASSWORD_LOCATORS}"
        )

    # Login in now to LinkedIn
    page.wait_for_timeout(500)
    username_locator.click()
    page.wait_for_timeout(random.randint(1000, 2500))
    for char in LINKEDIN_USER:
        username_locator.type(char)
        page.wait_for_timeout(random.randint(100, 500)) # Human behavior, type with realistic speed

    page.wait_for_timeout(500)
    password_locator.click()
    page.wait_for_timeout(random.randint(1000, 2500))

    for char in LINKEDIN_PASSWORD:
        password_locator.type(char)
        page.wait_for_timeout(random.randint(100, 500))  # Human behavior, type with realistic speed


    logger.info(f"Credentials entered, attempting login now...")
    page.wait_for_timeout(random.randint(1000, 2500))

    submit_locator, submit_selector = first_visible_locator(page, SUBMIT_LOCATORS, 5000)
    if not submit_locator:
        raise RuntimeError(
            f"Unable to find LinkedIn submit button locators. "
            f"Additional verification maybe required"
        )

    logger.info("Submitted login successfully")

def close_browser_session(browser=None, session=None):
    if browser is not None:
        try:
            browser.close()
        except Exception as e:
            logger.warning(f"Failed to close playwright browser cleanly: {e}")

    if session is not None:
        try:
            session.stop()
        except Exception as e:
            logger.warning(f"Failed to stop playwright browser cleanly: {e}")

def login_to_linkedin(page=None, browser=None, context=None, session=None):
    logger.info(f"Ensuring LinkedIn authentication....")
    # Check if a valid session exists (1 day old session state file)
    session_is_valid, session_file, session_age = is_session_file_valid()
    if session_is_valid:
        logger.info(f"Attempting to re-use session file")
        try:
            session_temp = sync_playwright().start()
            session = session_temp
            session_file_path = load_session_state(session_file)
            # Check if the session file exists
            if session_file_path:
                browser = launch_browser(session_temp)
                context = browser.new_context(storage_state=session_file_path, no_viewport=True, ignore_https_errors=True)
                page = context.pages[0] if context.pages else context.new_page()
                session = session_temp

                # Verify the session is still valid by checking if we are logged in
                open_linkedin_home(page)
                if is_logged_in(page):
                    logger.info(f"Saved session is still valid and authenticated")
                    return page, browser, context, session
                else:
                    logger.warning(" * Saved session exists, but authentication failed; starting fresh login")
                    close_browser_session(browser, session)
                    page, browser, context, session = normalize_session_state(page=None, browser=None, context=None, session=None)
        except CredentialError:
            close_browser_session(browser, session_temp)
            raise
        except Exception as e:
            logger.warning(f" * Could not reuse saved session: {e}. Starting fresh login.")
            close_browser_session(browser, session)
            page, browser, context, session = normalize_session_state(page=None, browser=None, context=None, session=None)
    else:
        logger.info(f"No valid session state detected; Starting login flow now")
        page, browser, context, session = normalize_session_state(page=None, browser=None, context=None, session=None)

    # Perform fresh login now
    try:
        open_linkedin_home(page)

        if is_logged_in(page):
            logger.info("Existing linked in session detected in brwoser")
        else:
            submit_login(page)

        # Save this session state post login
        save_session_state(context)

        return page, browser, context, session
    except Exception as e:
        logger.warning(f" * Login Failed: {e}")
        capture_screenshot_on_error(page, error_type="login_failed")
        raise
