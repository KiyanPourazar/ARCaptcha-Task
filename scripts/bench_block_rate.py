#!/usr/bin/env python3
"""Measure ArCaptcha block rate for UC vs remote drivers.

Example:
  DRIVER_MODE=uc python scripts/bench_block_rate.py --runs 5 --headed
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.bots.arcaptcha_selenium import ArCaptchaSeleniumBot  # noqa: E402
from app.bots.base import BotContext  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--mode",
        choices=("uc", "remote"),
        default=os.getenv("DRIVER_MODE", "uc"),
    )
    args = parser.parse_args()

    bot = ArCaptchaSeleniumBot()
    counts: Counter[str] = Counter()

    for i in range(1, args.runs + 1):
        ctx = BotContext(
            headless=not args.headed,
            username=os.getenv("BOT_USERNAME", "demo"),
            password=os.getenv("BOT_PASSWORD", "demo"),
            target_url=os.getenv("TARGET_URL", "https://demo.arcaptcha.co"),
            selenium_remote_url=os.getenv("SELENIUM_REMOTE_URL") or None,
            driver_mode=args.mode,
            stealth=True,
            humanize_delays=True,
        )
        result = bot.run(ctx)
        counts[result.outcome.value] += 1
        print(
            f"[{i}/{args.runs}] mode={args.mode} outcome={result.outcome.value} "
            f"challenge_id={bool(result.challenge_id)} detail={result.error_details or result.message}"
        )

    total = sum(counts.values()) or 1
    blocked = counts.get("blocked", 0)
    print("---")
    print(dict(counts))
    print(f"block_rate={blocked}/{total} = {blocked / total:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
