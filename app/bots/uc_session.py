"""SeleniumBase UC Mode session helpers (bonus: lower ArCaptcha block rate)."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)


@contextmanager
def open_uc_session(*, headless: bool, url: str) -> Iterator:
    """
    Open a UC Mode browser session.

    Evidence from trials against demo.arcaptcha.co:
    - Plain remote Selenium Grid often ends with "Blocked! Are you robot?"
    - UC Mode (headed / Xvfb) typically avoids that immediate block and can
      obtain a challenge_id via uc_click on #input-checkbox.

    Docker/server: entrypoint provides DISPLAY=:99 + noVNC. Headful attaches
    there so reviewers can watch on :7900. Headless uses a private Xvfb
    (SeleniumBase-managed) instead of Chrome --headless, which fingerprints worse.
    """
    try:
        from seleniumbase import SB
    except ImportError as exc:  # pragma: no cover - optional dependency path
        raise RuntimeError(
            "seleniumbase is required for UC Mode. Install requirements.txt."
        ) from exc

    chrome_binary = os.environ.get("CHROME_BINARY") or None
    docker_display = (os.environ.get("DOCKER_UC_DISPLAY") or "").strip()

    if headless:
        # Avoid real --headless for UC; virtual display is harder to fingerprint.
        sb_kwargs: dict = {"uc": True, "headless": False, "xvfb": True, "test": False}
        logger.info("UC session: private Xvfb (headless request)")
    else:
        if docker_display:
            os.environ["DISPLAY"] = docker_display
            logger.info("UC session: shared display %s (headful / noVNC)", docker_display)
        sb_kwargs = {"uc": True, "headed": True, "test": False}

    if chrome_binary:
        sb_kwargs["binary_location"] = chrome_binary

    with SB(**sb_kwargs) as sb:
        sb.uc_open_with_reconnect(url, 5)
        yield sb
