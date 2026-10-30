import os
import time
from common.logger import setup_logger

logger = setup_logger(__name__)

def capture_screenshot_on_error(page, error_type="error"):
    try:
        if page:
            timestamp = int(time.time())
            filename = f"screenshots/{error_type}_{timestamp}.png"
            os.makedirs("screenshots", exist_ok=True)
            page.screenshot(path=filename)
            logger.info(f"Screenshot saved to {filename}")
            return filename
    except Exception as e:
        logger.warning(f"Failed to capture screenshot: {e}")

    return None
