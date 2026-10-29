# LinkedIn Interview-Question Search

> **For users:** This guide describes the current project, its setup, and what to expect when you run it. AI coding-agent instructions are in [`Agents.md`](Agents.md).

## What this project does

This Python project is intended to use Playwright to open LinkedIn in a visible Chrome browser, attempt to authenticate, and navigate through search topics configured in `main.py`. The current search-results implementation is a starter flow, not a complete scraper: it does not yet collect question text or write the Markdown output filenames listed in `main.py`.

> **Current status:** The code has not been verified end-to-end and contains apparent startup blockers: the log formatter can fail on ordinary uncolored log levels, and the authentication module uses Playwright sync API attributes (`sync_playwright().session` and `session.chrome`) that are not part of the standard Python Playwright API. Do not rely on the run instructions below as proof that the current checkout can launch successfully.

## Requirements

- Python 3.10 or newer.
- Google Chrome installed on the machine. The default browser launch uses the Playwright `chrome` channel and runs visibly (not headless).
- A LinkedIn account and permission to use it with this workflow. Follow LinkedIn's terms and your organization's policies.
- Network access to LinkedIn.

## Setup

From the project directory, create and activate a virtual environment, then install the listed dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows PowerShell, activate with:

```powershell
.\.venv\Scripts\Activate.ps1
```

Create a `.env` file in the project root and set the required account credentials:

```dotenv
LINKEDIN_USER=your-email-or-phone
LINKEDIN_PASSWORD=your-password
```

Do not commit or share `.env`. The default configuration values are:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LINKEDIN_URL` | `https://in.linkedin.com/` | URL opened for authentication. |
| `LINKED_IN_SEARCH_URL` | `https://in.linkedin.com/` | Base string to which the encoded search term is appended. |
| `LINKEDIN_USER` | Empty | Required LinkedIn email or phone. |
| `LINKEDIN_PASSWORD` | Empty | Required LinkedIn password. |
| `SESSION_FILE` | `linked-in-session.json` | Playwright browser storage state, reused only while it is at most one day old. |
| `CHROME_PATH` | `chrome` | Leave as `chrome` to use the Chrome channel; set a local executable path to use a specific binary. |
| `CHROME_USER_DATA_DIR` | Empty | Loaded by configuration, but not currently used by the browser flow. |
| `ENCODE_PROXY` | Empty | Optional proxy-related setting; only configure it if you know the format expected by the current implementation. |
| `PROXY_URL` | Empty | Optional proxy server setting used with `ENCODE_PROXY`. |

Browser storage state contains authentication data. Keep it private, do not commit it, and remove the configured session file when you need to discard the saved session.

## Run

With the virtual environment active and `.env` configured:

```bash
python main.py
```

Chrome opens in a visible window. The configured flow navigates to LinkedIn and attempts login when it does not detect an existing authenticated session. Account verification requirements may prevent an automated login; the current code does not implement a dedicated MFA or CAPTCHA workflow.

## Search flow and configuration

The topics and search strings are currently hard-coded in the `queries` mapping in `main.py`. It contains `Playwright` and `SQL` topics. The program creates one browser session, invokes the search flow once per topic, and closes the session afterward.

`flow/question_scraper.py` constructs a URL by appending a URL-encoded search term to `LINKED_IN_SEARCH_URL` and waits for a LinkedIn post listing. Search extraction and Markdown file writing are not implemented yet, so running the current code should not be expected to produce the named interview-question files.

## Project layout

```text
.
├── main.py                  # Entrypoint and configured search topics
├── flow/
│   ├── linkedin_auth.py     # Browser setup and authentication/session flow
│   └── question_scraper.py  # Search navigation and in-progress results flow
├── common/
│   ├── config.py            # Environment variables and defaults
│   ├── logger.py            # Console logging
│   ├── session_manager.py   # Saved browser-state lifecycle
│   └── screenshot.py        # Error screenshot helper
└── requirements.txt         # Python dependencies
```

## Download and Setup EasyOcr
- For this project, I am using EasyOcr to scrape through the images
- You can use `pip install easyocr`
- If your system cannot directly download the models required for easyocr, follow this link to download the models
  - Link: https://www.jaided.ai/easyocr/modelhub/
  - Models: english_g2 (for English) and CRAFT (the major engine for text detection)
  - Note: In case yoour language is different, please choose a model from the page (if available)

## Initial Setup of Credentials and Key
- For LinkedIn, you need a valid login credential
- You can use the `encryption/credential_crypto.py` module to generate a key and encrypt your credentials
- Ensure you don't git-commit the files .cred and .key
- To generate a key and credential, follow the below steps (Call the crendential_crypto.py module as below)
  - Update the file generate_cred.py with your LinkedIn cred
  - Run the file
  - Once the cred are generate, verify if they are working fine
  - Remove the cred from the file (ensure the file is added to .gitignore)

## Troubleshooting and privacy

- **Missing-configuration error:** confirm both `LINKEDIN_USER` and `LINKEDIN_PASSWORD` are set in `.env` at the project root.
- **Chrome launch failure:** install Google Chrome or set `CHROME_PATH` to the correct browser executable.
- **Login or search failure:** inspect the console logs and check whether LinkedIn presented an account verification step or changed its page. Error screenshots may be created under `screenshots/`.
- **Sensitive files:** `.env`, `linked-in-session.json` (or your configured session filename), and screenshots may contain private account data. Keep them out of source control and share them only after reviewing their contents.

There is no documented automated test suite or test command in the current project.
