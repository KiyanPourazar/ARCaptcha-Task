"""Selenium bot for the ARCaptcha demo login flow."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from app.bots.base import BotContext, BotResult, BrowserBot, RunOutcome
from app.bots.browser import create_driver, human_pause
from app.bots.registry import register_bot

logger = logging.getLogger(__name__)


class MissingChallengeIdError(RuntimeError):
    """Raised when the captcha checkbox flow never yields a challenge_id."""


class CaptchaBlockedError(RuntimeError):
    """Raised when ARCaptcha blocks the client or shows an unsolved challenge."""


class VerificationFailedError(RuntimeError):
    """Raised when form submit does not produce a verified success signal."""

    def __init__(self, message: str, challenge_id: str | None = None) -> None:
        super().__init__(message)
        self.challenge_id = challenge_id


class ArCaptchaSeleniumBot(BrowserBot):
    id = "arcaptcha_demo_selenium"
    name = "ARCaptcha Demo (Selenium)"
    description = (
        "Visits demo.arcaptcha.co, clicks I'm not robot, extracts challenge_id, "
        "submits demo credentials, and verifies login success."
    )
    engine = "selenium"

    def run(self, context: BotContext) -> BotResult:
        driver: WebDriver | None = None
        challenge_id: str | None = None

        try:
            driver = create_driver(context)
            challenge_id = self._execute_flow(driver, context)
            return BotResult(
                outcome=RunOutcome.SUCCESS,
                challenge_id=challenge_id,
                message="Login verified successfully after CAPTCHA challenge.",
            )
        except MissingChallengeIdError as exc:
            return BotResult(
                outcome=RunOutcome.FAILED,
                challenge_id=challenge_id,
                error_details=str(exc),
                message="challenge_id was not obtained",
            )
        except CaptchaBlockedError as exc:
            return BotResult(
                outcome=RunOutcome.BLOCKED,
                challenge_id=challenge_id,
                error_details=str(exc),
                message="CAPTCHA blocked or required an unsolved visual challenge",
            )
        except TimeoutException as exc:
            return BotResult(
                outcome=RunOutcome.TIMEOUT,
                challenge_id=challenge_id,
                error_details=f"Timeout: {exc}",
                message="Timed out waiting for page or CAPTCHA",
            )
        except VerificationFailedError as exc:
            return BotResult(
                outcome=RunOutcome.FAILED,
                challenge_id=exc.challenge_id or challenge_id,
                error_details=str(exc),
                message="Form submitted but verification did not succeed",
            )
        except WebDriverException as exc:
            return BotResult(
                outcome=RunOutcome.FAILED,
                challenge_id=challenge_id,
                error_details=f"WebDriver error: {exc}",
                message="Browser automation failed",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected bot failure")
            return BotResult(
                outcome=RunOutcome.FAILED,
                challenge_id=challenge_id,
                error_details=str(exc),
                message="Unexpected bot error",
            )
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:  # noqa: BLE001
                    logger.debug("Driver quit failed", exc_info=True)

    def _execute_flow(self, driver: WebDriver, context: BotContext) -> str:
        # A couple of attempts helps when ArCaptcha transiently blocks automation.
        attempts = 2
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                return self._run_once(driver, context, attempt=attempt)
            except CaptchaBlockedError as exc:
                last_error = exc
                logger.info("CAPTCHA blocked on attempt %s/%s: %s", attempt, attempts, exc)
                if attempt >= attempts:
                    break
                human_pause(True, 1.0, 2.0)

        assert last_error is not None
        raise last_error

    def _run_once(self, driver: WebDriver, context: BotContext, attempt: int) -> str:
        wait = WebDriverWait(driver, context.page_load_timeout)
        driver.get(context.target_url)
        wait.until(EC.presence_of_element_located((By.ID, "email")))
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#arc-checkbox, .arcaptcha-vue")))
        human_pause(context.humanize_delays, 1.2, 2.2)

        self._simulate_reading(driver, context)
        self._fill_credentials(driver, context)
        human_pause(context.humanize_delays, 0.5, 1.1)

        self._click_not_robot(driver, context)
        challenge_id = self._wait_for_challenge_id(driver, context)
        if not challenge_id:
            if self._is_blocked(driver):
                raise CaptchaBlockedError(
                    "ArCaptcha showed: Blocked! Are you robot? "
                    f"(attempt {attempt})"
                )
            raise MissingChallengeIdError(
                "CAPTCHA interaction finished without a challenge_id/token "
                f"(attempt {attempt})"
            )

        human_pause(context.humanize_delays, 0.3, 0.8)
        try:
            self._submit_and_verify(driver, context, challenge_id)
        except VerificationFailedError as exc:
            raise VerificationFailedError(str(exc), challenge_id=challenge_id) from exc
        return challenge_id

    def _fill_credentials(self, driver: WebDriver, context: BotContext) -> None:
        email_input = driver.find_element(By.ID, "email")
        password_input = driver.find_element(By.ID, "password")

        email_input.click()
        email_input.clear()
        self._type_human(email_input, context.username, context.humanize_delays)
        human_pause(context.humanize_delays, 0.2, 0.5)
        password_input.click()
        password_input.clear()
        self._type_human(password_input, context.password, context.humanize_delays)

    def _click_not_robot(self, driver: WebDriver, context: BotContext) -> None:
        wait = WebDriverWait(driver, context.captcha_wait_timeout)
        target = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "#input-checkbox, #arc-checkbox")
            )
        )

        # ArCaptcha tracks pointer entropy — move around before the click.
        self._wiggle_mouse(driver, context)
        human_pause(context.humanize_delays, 0.4, 0.9)

        try:
            ActionChains(driver).move_to_element(target).pause(
                random.uniform(0.25, 0.55)
            ).click().perform()
        except WebDriverException:
            # Visible box may intercept; click the outer arc-checkbox container.
            outer = driver.find_element(By.ID, "arc-checkbox")
            ActionChains(driver).move_to_element_with_offset(
                outer, 24, 22
            ).pause(0.3).click().perform()

    def _wait_for_challenge_id(self, driver: WebDriver, context: BotContext) -> str | None:
        deadline = time.time() + context.captcha_wait_timeout

        while time.time() < deadline:
            if self._is_blocked(driver):
                raise CaptchaBlockedError(
                    "ArCaptcha showed: Blocked! Are you robot? Please refresh the page and try again"
                )

            token = self._extract_challenge_id(driver)
            if token:
                return token

            if self._visual_challenge_open(driver):
                # Give the demo a short chance to auto-pass; otherwise report blocked.
                time.sleep(2.0)
                token = self._extract_challenge_id(driver)
                if token:
                    return token
                if self._is_blocked(driver):
                    raise CaptchaBlockedError("Blocked during visual challenge")
                if self._visual_challenge_open(driver):
                    raise CaptchaBlockedError(
                        "Visual CAPTCHA challenge appeared and was not auto-solved"
                    )

            time.sleep(0.35)

        if self._is_blocked(driver):
            raise CaptchaBlockedError(
                "Timed out after ArCaptcha block message appeared"
            )
        return None

    def _extract_challenge_id(self, driver: WebDriver) -> str | None:
        script = """
        const pick = (v) => (typeof v === 'string' && v.trim().length > 8 ? v.trim() : null);

        try {
          if (window.arcaptcha && typeof window.arcaptcha.getArcToken === 'function') {
            const ids = Object.keys(window.arcaptcha.widgets || {});
            for (const id of ids) {
              const t = pick(window.arcaptcha.getArcToken(id));
              if (t) return t;
            }
          }
        } catch (e) {}

        const el = document.getElementById('arcaptcha-token')
          || document.querySelector('input[name="arcaptcha-token"], input[name="captcha_token"]');
        if (el && pick(el.value)) return el.value.trim();
        return null;
        """
        try:
            value = driver.execute_script(script)
        except WebDriverException:
            return None
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _submit_and_verify(
        self, driver: WebDriver, context: BotContext, challenge_id: str
    ) -> None:
        driver.execute_script(
            """
            const token = arguments[0];
            window.__botLoginProbe = { status: null, body: null, statusCode: null };
            const hidden = document.getElementById('arcaptcha-token')
              || document.querySelector('input[name="arcaptcha-token"], input[name="captcha_token"]');
            if (hidden) {
              hidden.value = token;
              hidden.dispatchEvent(new Event('input', { bubbles: true }));
              hidden.dispatchEvent(new Event('change', { bubbles: true }));
            }
            if (!window.__botFetchPatched) {
              window.__botFetchPatched = true;
              const origFetch = window.fetch;
              if (origFetch) {
                window.fetch = async function(...args) {
                  const res = await origFetch.apply(this, args);
                  try {
                    const url = String(args[0] || '');
                    if (url.includes('/api/login')) {
                      const text = await res.clone().text();
                      window.__botLoginProbe = {
                        statusCode: res.status,
                        status: res.ok ? 'ok' : 'error',
                        body: text,
                      };
                    }
                  } catch (e) {}
                  return res;
                };
              }
              const OrigXHR = window.XMLHttpRequest;
              function WrappedXHR() {
                const xhr = new OrigXHR();
                const open = xhr.open;
                xhr.open = function(method, url, ...rest) {
                  this.__botUrl = String(url || '');
                  return open.call(this, method, url, ...rest);
                };
                xhr.addEventListener('loadend', function() {
                  if ((this.__botUrl || '').includes('/api/login')) {
                    window.__botLoginProbe = {
                      statusCode: this.status,
                      status: this.status >= 200 && this.status < 300 ? 'ok' : 'error',
                      body: this.responseText,
                    };
                  }
                });
                return xhr;
              }
              window.XMLHttpRequest = WrappedXHR;
            }
            """,
            challenge_id,
        )

        login_button = self._find_login_button(driver)
        if login_button is None:
            raise VerificationFailedError("Login button not found")

        human_pause(context.humanize_delays, 0.25, 0.6)
        try:
            ActionChains(driver).move_to_element(login_button).pause(0.2).click().perform()
        except Exception:
            login_button.click()

        deadline = time.time() + context.login_wait_timeout
        while time.time() < deadline:
            probe = {}
            try:
                probe = driver.execute_script("return window.__botLoginProbe || {};") or {}
            except WebDriverException:
                probe = {}

            if probe.get("status") == "ok":
                return
            if probe.get("status") == "error":
                raise VerificationFailedError(
                    f"Login API failed ({probe.get('statusCode')}): "
                    f"{str(probe.get('body') or '')[:240]}"
                )

            signals = self._read_verification_signals(driver)
            if signals.get("success"):
                return
            if signals.get("error"):
                raise VerificationFailedError(
                    f"Server rejected login: {signals['error']}"
                )
            time.sleep(0.35)

        raise VerificationFailedError(
            "No success confirmation observed after form submission "
            f"(challenge_id={challenge_id[:12]}…)"
        )

    def _read_verification_signals(self, driver: WebDriver) -> dict[str, Any]:
        script = """
        const toastSuccess = document.querySelector(
          '.Vue-Toastification__toast--success, .toast-success'
        );
        const toastError = document.querySelector(
          '.Vue-Toastification__toast--error, .toast-error'
        );
        if (toastSuccess) {
          return { success: true, error: null, detail: toastSuccess.innerText || 'success' };
        }
        if (toastError) {
          return { success: false, error: toastError.innerText || 'error', detail: null };
        }
        return { success: false, error: null, detail: null };
        """
        try:
            result = driver.execute_script(script) or {}
        except WebDriverException:
            return {}
        return result if isinstance(result, dict) else {}

    def _is_blocked(self, driver: WebDriver) -> bool:
        try:
            text = driver.execute_script("return document.body ? document.body.innerText : '';")
        except WebDriverException:
            return False
        lowered = (text or "").lower()
        return "blocked" in lowered and "robot" in lowered

    def _visual_challenge_open(self, driver: WebDriver) -> bool:
        script = """
        const frames = Array.from(document.querySelectorAll('iframe'));
        const challengeFrame = frames.some(f => (f.src || '').toLowerCase().includes('challenge'));
        const overlay = document.querySelector('.arcaptcha-challenge, [class*="challenge-modal"]');
        return Boolean(overlay || challengeFrame);
        """
        try:
            return bool(driver.execute_script(script))
        except WebDriverException:
            return False

    def _find_login_button(self, driver: WebDriver):
        for el in driver.find_elements(By.TAG_NAME, "button"):
            try:
                label = (el.text or "").strip().lower()
                if label == "login" and el.is_displayed() and el.is_enabled():
                    return el
            except WebDriverException:
                continue
        return None

    def _simulate_reading(self, driver: WebDriver, context: BotContext) -> None:
        if not context.humanize_delays:
            return
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            actions = ActionChains(driver)
            actions.move_to_element_with_offset(body, 200, 120).pause(0.2)
            for _ in range(4):
                actions.move_by_offset(
                    random.randint(-40, 60), random.randint(-20, 40)
                ).pause(random.uniform(0.05, 0.15))
            actions.perform()
        except WebDriverException:
            pass

    def _wiggle_mouse(self, driver: WebDriver, context: BotContext) -> None:
        try:
            widget = driver.find_element(By.CSS_SELECTOR, ".arcaptcha-vue, #arc-checkbox")
            actions = ActionChains(driver)
            actions.move_to_element(widget).pause(0.15)
            for _ in range(6):
                actions.move_by_offset(
                    random.randint(-18, 18), random.randint(-12, 12)
                ).pause(random.uniform(0.04, 0.12))
            actions.perform()
        except WebDriverException:
            if context.humanize_delays:
                time.sleep(0.3)

    @staticmethod
    def _type_human(element, text: str, enabled: bool) -> None:
        if not enabled:
            element.send_keys(text)
            return
        for ch in text:
            element.send_keys(ch)
            time.sleep(random.uniform(0.04, 0.14))


register_bot(ArCaptchaSeleniumBot())
