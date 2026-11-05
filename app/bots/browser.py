"""Shared Selenium WebDriver factory with optional stealth hardening."""

from __future__ import annotations

import logging
import random
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.remote.webdriver import WebDriver

from app.bots.base import BotContext

logger = logging.getLogger(__name__)

# Keep UA / platform consistent (Linux container → Linux UA).
LINUX_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Linux x86_64' });
Object.defineProperty(navigator, 'plugins', {
  get: () => {
    const fake = [
      { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
      { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
      { name: 'Native Client', filename: 'internal-nacl-plugin' },
    ];
    fake.item = (i) => fake[i];
    fake.namedItem = (n) => fake.find(p => p.name === n);
    fake.refresh = () => {};
    return fake;
  }
});
window.chrome = window.chrome || { runtime: {}, app: { isInstalled: false } };
const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
if (originalQuery) {
  window.navigator.permissions.query = (parameters) => (
    parameters && parameters.name === 'notifications'
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery(parameters)
  );
}
"""


def human_pause(enabled: bool, low: float = 0.25, high: float = 0.9) -> None:
    if enabled:
        time.sleep(random.uniform(low, high))


def build_chrome_options(context: BotContext) -> Options:
    options = Options()
    if context.headless:
        # New headless is easier to detect; still offered, but Headful is preferred.
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,900")
    options.add_argument("--lang=en-US")
    options.add_argument(f"--user-agent={LINUX_UA}")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-features=IsolateOrigins,site-per-process")

    if context.stealth:
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option(
            "prefs",
            {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
                "intl.accept_languages": "en-US,en",
            },
        )

    if context.chrome_binary:
        options.binary_location = context.chrome_binary

    return options


def _apply_stealth(driver: WebDriver) -> None:
    # Prefer CDP so the patch exists before any page script runs.
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": STEALTH_JS},
        )
        return
    except Exception:
        logger.debug("execute_cdp_cmd unavailable; trying raw CDP command", exc_info=True)

    try:
        driver.execute(
            "executeCdpCommand",
            {
                "cmd": "Page.addScriptToEvaluateOnNewDocument",
                "params": {"source": STEALTH_JS},
            },
        )
    except Exception:
        logger.debug("Raw CDP stealth injection failed", exc_info=True)


def create_driver(context: BotContext) -> WebDriver:
    options = build_chrome_options(context)

    if context.selenium_remote_url:
        driver: WebDriver = webdriver.Remote(
            command_executor=context.selenium_remote_url,
            options=options,
        )
    else:
        service = Service()
        driver = webdriver.Chrome(service=service, options=options)

    driver.set_page_load_timeout(context.page_load_timeout)
    driver.implicitly_wait(0)

    if context.stealth:
        _apply_stealth(driver)

    try:
        driver.set_window_size(1440, 900)
    except Exception:
        pass

    return driver
