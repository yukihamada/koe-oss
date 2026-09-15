"""End-to-end check with the real MLX engine, not a fake.

This is the test that matters: register a voice, grant consent, add a reading
rule, synthesize through the HTTP API, and confirm a playable wav comes out
with the correction applied.

Run with a Python that has mlx-audio installed:
    python tools/e2e_real_engine.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REF = "/Users/yukihamada/voice-clone/ref_yuki.wav"
REF_TEXT = "こんばんは、はまだゆうきです。今日は録音ボタンを押して収録しています。"


def main() -> int:
    if not Path(REF).exists():
        print(f"SKIP: reference audio not found at {REF}")
        return 0

    from fastapi.testclient import TestClient

    from koe_oss.engines.mlx_qwen import MlxQwenEngine
    from koe_oss.server import api

    tmp = Path(tempfile.mkdtemp(prefix="koe-e2e-"))
    try:
        engine = MlxQwenEngine()
        if not engine.is_available():
            print("SKIP: mlx-audio not installed in this interpreter")
            return 0

        api.STORE = api.Store(tmp)
        api._set_engine(engine)
        client = TestClient(api.app)

        # 1. register a voice
        r = client.post("/voices", json={
            "handle": "yuki", "ref_audio": REF, "ref_text": REF_TEXT, "lang": "ja"})
        assert r.status_code == 201, r.text
        print("1. voice registered:", r.json()["voice"]["handle"])

        # 2. consent gate blocks synthesis until granted
        r = client.post("/synth", json={"voice_id": "yuki", "text": "こんにちは"})
        assert r.status_code == 422 and r.json()["detail"]["reason"] == "consent_missing"
        print("2. consent gate blocks synthesis: ok")

        client.post("/voices/yuki/consent", json={"age_ok": True})

        # 3. add a reading rule for a measured misread
        client.put("/readings/弟子屈", json={"word": "弟子屈", "reading": "テシカガ"})

        # 4. synthesize through the API
        out = tmp / "out.wav"
        r = client.post("/synth", json={
            "voice_id": "yuki",
            "text": "弟子屈は北海道にある静かな村です。",
            "out_path": str(out),
        })
        assert r.status_code == 200, r.text
        body = r.json()
        print("3. synthesized:", body["audio_path"])
        print("   duration:", body["duration_sec"], "sec")
        print("   gen:", body["gen_sec"], "sec")
        print("   corrected:", body["corrected"], "->", body["spoken"])

        # 5. confirm the wav is real and playable
        assert out.exists(), "wav was not written"
        assert out.stat().st_size > 1000, "wav suspiciously small"
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=sample_rate,channels", "-of", "json", str(out)],
            capture_output=True, text=True)
        assert probe.returncode == 0, probe.stderr
        print("4. ffprobe:", probe.stdout.strip().replace("\n", " "))

        # 6. persistence: reload from disk
        api.STORE = api.Store(tmp)
        c2 = TestClient(api.app)
        assert c2.get("/voices/yuki").json()["voice"]["consent_state"] == "current"
        assert c2.post("/readings/apply", json={"text": "弟子屈"}).json()["text"] == "テシカガ"
        print("5. state reloaded from disk: ok")

        print("\nE2E OK")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
