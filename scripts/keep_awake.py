"""Open the dashboard in a real (headless) browser so Streamlit Community Cloud doesn't put it to sleep.

If the app is already asleep, click Streamlit's wake-up button and wait until the leaderboard loads.
Loading the app also runs its queries, which keeps the Supabase project from pausing.

Run by .github/workflows/keep-awake.yml. Locally:
    pip install playwright && playwright install chromium
    python scripts/keep_awake.py
"""

import os
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

APP_URL = os.environ.get("APP_URL", "https://mahjongclubcompetitive.streamlit.app").rstrip("/")
WAKE_BUTTON = "Yes, get this app back up!"
LOADED_TEXT = "Leaderboard"          # a tab label that only appears once the app is running


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # The outer page is where Streamlit shows the "app is asleep" screen.
        page.goto(APP_URL, wait_until="domcontentloaded", timeout=60_000)
        wake = page.get_by_role("button", name=WAKE_BUTTON)
        try:
            wake.wait_for(timeout=15_000)
            print("App was asleep: waking it up.")
            wake.click()
        except PlaywrightTimeout:
            print("App is awake.")

        # The app itself is served at /~/+/ ; wait for it to actually render (waking can take a few minutes).
        page.goto(f"{APP_URL}/~/+/", wait_until="domcontentloaded", timeout=60_000)
        try:
            page.get_by_text(LOADED_TEXT, exact=True).first.wait_for(timeout=300_000)
        except PlaywrightTimeout:
            page.screenshot(path="keep_awake_failure.png", full_page=True)
            print("Dashboard did not load in time; screenshot saved.", file=sys.stderr)
            return 1

        print("Dashboard loaded.")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
