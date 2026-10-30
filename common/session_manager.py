import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
from common.logger import setup_logger
from common.config import SESSION_FILE

logger = setup_logger(__name__)

SESSION_FILE_PATH = f"{SESSION_FILE}"
SESSION_MAX_AGE_DAYS = 1 # 1 Day expires

def is_session_file_valid() -> Tuple[ bool, str, Optional[float]]:
    """
    Check if LinkedIn session file exists and is not older than 1 day
    Returns:
    Tuple[bool, str, Optional[float]]
    """
    session_path = Path(SESSION_FILE_PATH)

    if not session_path.exists():
        logger.info(f"Session file not found: {SESSION_FILE_PATH}")
        return False, SESSION_FILE_PATH, None

    try:
        file_mtime = datetime.fromtimestamp(os.path.getmtime(session_path))
        current_time = datetime.now()
        age_seconds = (current_time - file_mtime).total_seconds()

        if (current_time - file_mtime) > timedelta(days=SESSION_MAX_AGE_DAYS):
            age_hours = float(age_seconds / 3600)
            logger.info(F"Session file is stale: {age_hours: .2f} hours old (max allowed: 24 hours)")
            return False, SESSION_FILE_PATH, None

        age_hours = float(age_seconds / 3600)
        logger.info(f" ^ Valid session file found: {age_hours: .2f} hours old")
        return True, SESSION_FILE_PATH, age_seconds
    except Exception as e:
        logger.warning(f" * Error checking session file age: {e}")
        return False, SESSION_FILE_PATH, None

def load_session_state(file_path: str = SESSION_FILE_PATH) -> Optional[str]:
    """
    Load session state from file
    Returns:
        str | None : Path to the session file if it exists, None otherwise
    """
    try:
        if os.path.exists(file_path):
            logger.info(f" ^ Loading session state from: {file_path}")
            return file_path
        else:
            logger.warning(f"Session state file not found: {file_path}")
            return None
    except Exception as e:
        logger.warning(f" * Error loading session state: {e}")
        return None

def save_session_state(context, file_path: str = SESSION_FILE_PATH) -> bool:
    """
    Save session state to file
    Returns:
        bool: True if save was successful, False otherwise
    """
    try:
        context.storage_state(path=file_path)
        logger.info(f" ^ Session state saved to: {file_path}")
        return True
    except Exception as e:
        logger.warning(f" * Error saving session state: {e}")
        return False

def delete_session_file(file_path: str = SESSION_FILE_PATH) -> bool:
    """
    Delete session file
    Returns:
         bool: True if delete was successful, False otherwise
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f" ^ Session state file deleted: {file_path}")
            return True
        else:
            logger.info(f"Session state file not found, nothing to delete: {file_path}")
            return False
    except Exception as e:
        logger.warning(f" * Error deleting session state: {e}")
        return False