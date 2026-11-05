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
        # Prefer UC Mode: measured to avoid immediate ArCaptcha "Blocked!" on desktop.
        use_uc = (context.driver_mode or "uc").lower() == "uc"
        if use_uc:
            try:
                return self._run_uc(context)
            except RuntimeError as exc:
                # Missing seleniumbase — fall through to classic WebDriver.
                logger.warning("UC Mode unavailable (%s); falling back to remote/local WebDriver", exc)

        driver: WebDriver | None = None
        challenge_id: str | None = None

        try:
            driver = create_driver(context)
            challenge_id = self._execute_flow(driver, context)
            return BotResult(
                outcome=RunOutcome.SUCCESS,
                challenge_id=challenge_id,
                message="Login verified successfully after CAPTCHA challenge.",
                metadata={"driver_mode": "remote"},
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

    def _run_uc(self, context: BotContext) -> BotResult:
        """Run the demo flow with SeleniumBase UC Mode (anti-detect chromedriver)."""
        from app.bots.uc_session import open_uc_session

        challenge_id: str | None = None
        try:
            with open_uc_session(headless=context.headless, url=context.target_url) as sb:
                sb.sleep(1.5 if context.humanize_delays else 0.4)
                sb.wait_for_element("#email", timeout=context.page_load_timeout)
                sb.wait_for_element("#input-checkbox", timeout=context.page_load_timeout)

                sb.type("#email", context.username)
                sb.sleep(0.35 if context.humanize_delays else 0.05)
                sb.type("#password", context.password)
                sb.sleep(0.8 if context.humanize_delays else 0.1)

                # Hover path gives ArCaptcha's mouse tracker some entropy.
                for sel in ("#email", "#password", ".arcaptcha-vue", "#input-checkbox"):
                    try:
                        sb.hover(sel)
                        sb.sleep(0.2 if context.humanize_delays else 0.05)
                    except Exception:  # noqa: BLE001
                        pass

                sb.uc_click("#input-checkbox", reconnect_time=6)

                challenge_id, solved_visual = self._uc_wait_for_challenge(
                    sb, context.captcha_wait_timeout
                )
                if self._uc_is_blocked(sb):
                    return BotResult(
                        outcome=RunOutcome.BLOCKED,
                        challenge_id=challenge_id,
                        error_details="ArCaptcha showed: Blocked! Are you robot?",
                        message="CAPTCHA blocked or required an unsolved visual challenge",
                        metadata={"driver_mode": "uc", "solved_visual": solved_visual},
                    )
                if not challenge_id:
                    return BotResult(
                        outcome=RunOutcome.FAILED,
                        challenge_id=None,
                        error_details="UC Mode click finished without challenge_id/token",
                        message="challenge_id was not obtained",
                        metadata={"driver_mode": "uc"},
                    )

                self._uc_sync_token(sb, challenge_id)
                ok, detail = self._uc_submit_and_verify(sb, context, challenge_id)
                if ok:
                    return BotResult(
                        outcome=RunOutcome.SUCCESS,
                        challenge_id=challenge_id,
                        message="Login verified successfully after CAPTCHA challenge.",
                        metadata={
                            "driver_mode": "uc",
                            "solved_visual": solved_visual,
                        },
                    )
                return BotResult(
                    outcome=RunOutcome.FAILED,
                    challenge_id=challenge_id,
                    error_details=detail,
                    message="Form submitted but verification did not succeed",
                    metadata={
                        "driver_mode": "uc",
                        "solved_visual": solved_visual,
                    },
                )
        except MissingChallengeIdError as exc:
            return BotResult(
                outcome=RunOutcome.FAILED,
                challenge_id=challenge_id,
                error_details=str(exc),
                message="challenge_id was not obtained",
                metadata={"driver_mode": "uc"},
            )
        except CaptchaBlockedError as exc:
            return BotResult(
                outcome=RunOutcome.BLOCKED,
                challenge_id=challenge_id,
                error_details=str(exc),
                message="CAPTCHA blocked or required an unsolved visual challenge",
                metadata={"driver_mode": "uc"},
            )
        except TimeoutException as exc:
            return BotResult(
                outcome=RunOutcome.TIMEOUT,
                challenge_id=challenge_id,
                error_details=f"Timeout: {exc}",
                message="Timed out waiting for page or CAPTCHA",
                metadata={"driver_mode": "uc"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("UC Mode bot failure")
            # Surface site connectivity problems clearly for reviewers.
            text = str(exc)
            if "ERR_CONNECTION" in text or "chrome-error" in text:
                return BotResult(
                    outcome=RunOutcome.FAILED,
                    challenge_id=challenge_id,
                    error_details=text,
                    message="Could not reach demo.arcaptcha.co",
                    metadata={"driver_mode": "uc"},
                )
            return BotResult(
                outcome=RunOutcome.FAILED,
                challenge_id=challenge_id,
                error_details=text,
                message="Unexpected UC Mode bot error",
                metadata={"driver_mode": "uc"},
            )

    @staticmethod
    def _uc_is_blocked(sb) -> bool:
        try:
            text = (sb.get_text("body") or "").lower()
        except Exception:  # noqa: BLE001
            return False
        return "blocked" in text and "robot" in text

    def _uc_wait_for_challenge(self, sb, timeout: int) -> tuple[str | None, bool]:
        deadline = time.time() + timeout
        last_token: str | None = None
        solved_visual = False
        while time.time() < deadline:
            if self._uc_is_blocked(sb):
                return last_token, solved_visual
            info = sb.execute_script(
                """
                const t = document.getElementById('arcaptcha-token');
                const img = document.getElementById('checked-in-the-box');
                let tok = null;
                try {
                  for (const id of Object.keys((window.arcaptcha || {}).widgets || {})) {
                    const v = window.arcaptcha.getArcToken(id);
                    if (v) tok = v;
                  }
                } catch (e) {}
                const imgShown = !!(img && getComputedStyle(img).display !== 'none'
                  && getComputedStyle(img).visibility !== 'hidden');
                return { token: (t && t.value) || tok || null, imgShown };
                """
            ) or {}
            token = info.get("token")
            if token:
                last_token = token
            if info.get("imgShown") and token:
                return token, True
            # Keep the first challenge_id even if visual checkmark never appears.
            if token and time.time() + 8 >= deadline:
                return token, False
            sb.sleep(0.35)
        return last_token, solved_visual

    @staticmethod
    def _uc_sync_token(sb, token: str) -> None:
        sb.execute_script(
            """
            const token = arguments[0];
            const hidden = document.getElementById('arcaptcha-token');
            if (hidden) {
              hidden.value = token;
              hidden.dispatchEvent(new Event('input', { bubbles: true }));
              hidden.dispatchEvent(new Event('change', { bubbles: true }));
            }
            const app = document.querySelector('#app');
            const stack = [];
            if (app && app.__vueParentComponent) stack.push(app.__vueParentComponent);
            if (app && app.__vue_app__ && app.__vue_app__._instance) {
              stack.push(app.__vue_app__._instance);
            }
            while (stack.length) {
              const n = stack.pop();
              if (!n) continue;
              if (n.ctx && n.ctx.form) n.ctx.form.captcha_token = token;
              if (n.subTree && n.subTree.component) stack.push(n.subTree.component);
              const kids = n.subTree && n.subTree.children;
              if (Array.isArray(kids)) {
                for (const c of kids) if (c && c.component) stack.push(c.component);
              }
            }
            """,
            token,
        )

    def _uc_submit_and_verify(
        self, sb, context: BotContext, challenge_id: str
    ) -> tuple[bool, str]:
        # Prefer verifying through the same browser login API the SPA uses.
        probe = sb.execute_script(
            """
            const token = arguments[0];
            const user = arguments[1];
            const pass = arguments[2];
            try {
              const xhr = new XMLHttpRequest();
              xhr.open('POST', 'https://demo.arcaptcha.co/api/login', false);
              xhr.setRequestHeader('Content-Type', 'application/json');
              xhr.send(JSON.stringify({
                username: user,
                password: pass,
                captcha_token: token
              }));
              return { status: xhr.status, body: xhr.responseText || '' };
            } catch (e) {
              return { status: 0, body: String(e) };
            }
            """,
            challenge_id,
            context.username,
            context.password,
        ) or {}

        status = int(probe.get("status") or 0)
        body = str(probe.get("body") or "")
        if 200 <= status < 300:
            return True, body

        # Also click the UI Login button as a secondary signal.
        try:
            sb.click("button")
            sb.sleep(1.2)
            if sb.is_element_present(".Vue-Toastification__toast--success"):
                return True, sb.get_text(".Vue-Toastification__toast--success")
            if sb.is_element_present(".Vue-Toastification__toast--error"):
                return False, sb.get_text(".Vue-Toastification__toast--error")
        except Exception as exc:  # noqa: BLE001
            logger.debug("UI login click failed: %s", exc)

        return False, f"Login API status={status} body={body[:240]}"

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
