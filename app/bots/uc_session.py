"""SeleniumBase UC Mode session helpers (bonus: lower ArCaptcha block rate)."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)


@contextmanager
def open_uc_session(*, headless: bool, url: str) -> Iterator:
    """
    Open a UC Mode browser session.

    Evidence from local trials against demo.arcaptcha.co:
    - Plain remote Selenium Grid often ends with "Blocked! Are you robot?"
    - UC Mode (headed) typically avoids that immediate block message and can
      obtain a challenge_id via uc_click on #input-checkbox.
    """
    try:
        from seleniumbase import SB
    except ImportError as exc:  # pragma: no cover - optional dependency path
        raise RuntimeError(
            "seleniumbase is required for UC Mode. Install requirements.txt."
        ) from exc

    # Headless UC is much easier to fingerprint; prefer headed + OS display/Xvfb.
    with SB(uc=True, headless=bool(headless), test=False) as sb:
        sb.uc_open_with_reconnect(url, 5)
        yield sb
