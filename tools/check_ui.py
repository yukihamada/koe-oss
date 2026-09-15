"""Render the desktop UI against the live API and assert it actually works.

Launch the API first:
    KOE_DATA_DIR=/tmp/koe-cli-test PYTHONPATH=. python -m uvicorn \
        koe_oss.server.api:app --port 8801

Then:
    python tools/check_ui.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8902/index.html"
SHOTS = Path("/tmp/koe-ui-shots")


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    results = []

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 900, "height": 1100})
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(1500)

        # 1. status loaded
        status = page.inner_text("#status-body")
        results.append(("status rendered", bool(status.strip()), status[:80]))

        # 2. voices loaded from the API
        voices = page.inner_text("#voices")
        results.append(("voices rendered", "yuki" in voices, voices[:60].replace("\n", " ")))

        # 3. voice selector populated
        opts = page.eval_on_selector_all("#s-voice option", "els => els.map(e => e.value)")
        results.append(("voice select populated", "yuki" in opts, str(opts)))

        # 4. readings loaded
        readings = page.inner_text("#readings")
        results.append(("readings rendered", "弟子屈" in readings, readings[:60].replace("\n", " ")))

        # 5. add a reading rule through the UI
        page.fill("#r-word", "美留和")
        page.fill("#r-reading", "ミルワ")
        page.click("#r-add")
        page.wait_for_timeout(1200)
        results.append(("reading added", "ミルワ" in page.inner_text("#readings"), ""))

        # 6. synthesize through the UI
        page.select_option("#s-voice", "yuki")
        page.fill("#s-text", "美留和は静かな場所です。")
        page.click("#s-go")
        page.wait_for_timeout(60000)
        res = page.inner_text("#s-result")
        prog = page.inner_text("#s-progress")
        results.append(("synthesis completed", "audio" in page.inner_html("#s-result"),
                        f"{prog} | {res[:80].replace(chr(10), ' ')}"))

        page.screenshot(path=str(SHOTS / "main.png"), full_page=True)

        # 7. english toggle
        page.click("#lang-btn")
        page.wait_for_timeout(600)
        body = page.inner_text("body")
        results.append(("english toggle", "Your voice" in body, ""))
        page.screenshot(path=str(SHOTS / "en.png"), full_page=True)

        results.append(("no console errors", not errors, "; ".join(errors[:2])))
        b.close()

    ok = True
    for name, passed, detail in results:
        print(f"{'PASS' if passed else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
        ok = ok and passed
    print("\nshots:", SHOTS)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
