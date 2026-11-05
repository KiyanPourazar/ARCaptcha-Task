"""ArCaptcha slider-puzzle solver (drag piece into the gap)."""

from __future__ import annotations

import io
import logging
import re
from typing import Any

import numpy as np
import requests
from PIL import Image

logger = logging.getLogger(__name__)


def find_puzzle_offset(bg_bytes: bytes, piece_bytes: bytes, y_hint: int = 70) -> tuple[int, float]:
    """
    Estimate horizontal drag distance (px) so the piece fits the gap.

    Uses edge-map correlation between the piece and a horizontal band of the
    background image at the piece's known top offset.
    """
    bg = Image.open(io.BytesIO(bg_bytes)).convert("RGB")
    piece = Image.open(io.BytesIO(piece_bytes)).convert("RGB")
    bg_a = np.asarray(bg).astype(np.float32)
    pc_a = np.asarray(piece).astype(np.float32)
    ph, pw = pc_a.shape[:2]
    bh, bw = bg_a.shape[:2]
    y0 = max(0, min(int(y_hint), max(0, bh - ph)))

    bg_edges = np.abs(np.diff(bg_a.mean(axis=2), axis=1))
    pc_edges = np.abs(np.diff(pc_a.mean(axis=2), axis=1))
    band = bg_edges[y0 : y0 + ph, :]

    best_corr = -1.0
    best_x = 0
    for x in range(0, max(1, bw - pw)):
        window = band[:, x : x + pw - 1]
        if window.shape != pc_edges.shape:
            continue
        w = window - window.mean()
        p = pc_edges - pc_edges.mean()
        denom = (np.linalg.norm(w) * np.linalg.norm(p)) + 1e-6
        corr = float((w * p).sum() / denom)
        if corr > best_corr:
            best_corr = corr
            best_x = x
    return best_x, best_corr


def _parse_px(value: str | None, default: int = 0) -> int:
    if not value:
        return default
    m = re.search(r"-?\d+", str(value))
    return int(m.group(0)) if m else default


def extract_puzzle_assets(driver_or_sb) -> dict[str, Any] | None:
    """Read puzzle image URLs / geometry from the open ArCaptcha challenge DOM."""
    try:
        data = driver_or_sb.execute_script(
            """
            const root = document.querySelector('.arc-puzzle');
            if (!root) return null;
            const imgs = [...root.querySelectorAll('img')];
            const bg = imgs.find(i => (i.naturalWidth || i.width) >= 200) || imgs[0];
            const piece = root.querySelector('img.puzzle');
            const knob = root.querySelector('.draggable');
            if (!bg || !piece || !knob) return null;
            return {
              bg: bg.src,
              piece: piece.src,
              top: piece.style.top || '',
              left: piece.style.left || '',
              trackWidth: (root.querySelector('.tw-relative.tw-flex.tw-justify-center') || {}).clientWidth || 260
            };
            """
        )
    except Exception:  # noqa: BLE001
        logger.debug("extract_puzzle_assets failed", exc_info=True)
        return None
    return data if isinstance(data, dict) else None


def download(url: str, timeout: int = 20) -> bytes:
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def solve_arcaptcha_slider(driver_or_sb, *, humanize: bool = True) -> dict[str, Any]:
    """
    If a puzzle challenge is visible, drag `.draggable` to the computed offset.

    Works with both SeleniumBase SB and raw WebDriver (needs drag_and_drop_with_offset
    on SB, or ActionChains on WebDriver).
    """
    assets = extract_puzzle_assets(driver_or_sb)
    if not assets:
        return {"solved": False, "reason": "no_puzzle"}

    y_hint = _parse_px(assets.get("top"), 70)
    bg_bytes = download(assets["bg"])
    piece_bytes = download(assets["piece"])
    offset, score = find_puzzle_offset(bg_bytes, piece_bytes, y_hint=y_hint)
    offset = max(1, int(offset))
    logger.info("Puzzle offset=%s score=%.3f", offset, score)

    def _drag(delta: int) -> None:
        if hasattr(driver_or_sb, "drag_and_drop_with_offset"):
            driver_or_sb.drag_and_drop_with_offset(".draggable", delta, 0)
        else:
            from selenium.webdriver.common.action_chains import ActionChains
            from selenium.webdriver.common.by import By

            knob = driver_or_sb.find_element(By.CSS_SELECTOR, ".draggable")
            ActionChains(driver_or_sb).click_and_hold(knob).pause(0.15).move_by_offset(
                delta, 0
            ).pause(0.1).release().perform()

    def _puzzle_gone() -> bool:
        try:
            return not bool(
                driver_or_sb.execute_script(
                    "return !!document.querySelector('.arc-puzzle .draggable');"
                )
            )
        except Exception:  # noqa: BLE001
            return False

    if humanize and hasattr(driver_or_sb, "sleep"):
        driver_or_sb.sleep(0.35)

    # Try primary estimate, then small nudges if the modal is still open.
    attempts = [offset, max(1, offset - 6), offset + 6, max(1, offset - 12), offset + 12]
    used = offset
    for i, delta in enumerate(attempts):
        # After a failed attempt the knob may already be mid-track; reset via refresh button if present.
        if i > 0:
            try:
                # Click the puzzle reset icon (second control in the footer) if available.
                driver_or_sb.execute_script(
                    """
                    const btns = document.querySelectorAll('.arc-puzzle img.tw-cursor-pointer, .arc-puzzle .tw-cursor-pointer img');
                    // Heuristic: refresh/reset is usually present; click the first footer control.
                    if (btns.length) btns[0].click();
                    """
                )
                if hasattr(driver_or_sb, "sleep"):
                    driver_or_sb.sleep(1.0)
                else:
                    import time

                    time.sleep(1.0)
                # Recompute against possibly new images after reset.
                assets2 = extract_puzzle_assets(driver_or_sb)
                if assets2:
                    y2 = _parse_px(assets2.get("top"), 70)
                    off2, score = find_puzzle_offset(
                        download(assets2["bg"]), download(assets2["piece"]), y_hint=y2
                    )
                    delta = max(1, int(off2))
                    score = score
            except Exception:  # noqa: BLE001
                logger.debug("Puzzle reset/recompute failed", exc_info=True)

        used = delta
        _drag(delta)
        if hasattr(driver_or_sb, "sleep"):
            driver_or_sb.sleep(1.6)
        else:
            import time

            time.sleep(1.6)
        if _puzzle_gone():
            return {"solved": True, "offset": used, "score": score}

    return {"solved": _puzzle_gone(), "offset": used, "score": score}
