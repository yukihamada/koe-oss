"""Long-form pipeline tests. Uses a fake engine — no GPU needed."""

import pytest

from koe_oss.core.jobs import Job, COMPLETED, FAILED
from koe_oss.core.longform import synthesize_longform, _concat
from koe_oss.core.readings import ReadingDictionary
from koe_oss.core.voices import Voice, ConsentRecord
from koe_oss.engines.base import SynthEngine, SynthRequest, SynthResult
from koe_oss.engines.mlx_qwen import MlxQwenEngine


class WavEngine(SynthEngine):
    """Writes a real wav using only the standard library.

    Deliberately avoids numpy/soundfile: CI installs only the package's own
    dependencies, and a test that needs a GPU stack to assert control flow is
    a test that will fail for the wrong reason.
    """

    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def capabilities(self):
        return MlxQwenEngine().capabilities()

    def is_available(self):
        return True

    def synthesize(self, req: SynthRequest) -> SynthResult:
        import struct
        import wave
        from pathlib import Path

        self.calls.append(req)
        if self.fail_on is not None and len(self.calls) - 1 == self.fail_on:
            raise RuntimeError("boom")
        p = Path(req.out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # 0.1 s of silence at 24 kHz, mono, 16-bit.
        with wave.open(str(p), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(struct.pack("<2400h", *([0] * 2400)))
        return SynthResult(str(p), 24000, 0.1, "wav", 0.01)


@pytest.fixture()
def voice():
    v = Voice(handle="yuki", ref_audio="/tmp/ref.wav", ref_text="あ", lang="ja")
    v.consent = ConsentRecord(age_ok=True)
    return v


def test_longform_completes(voice, tmp_path):
    eng = WavEngine()
    r = synthesize_longform(eng, voice, "一です。二です。三です。", tmp_path)
    assert r.ok, r.errors
    assert r.job.state == COMPLETED
    assert len(r.chunk_paths) == 3
    assert (tmp_path / "merged.wav").exists()


def test_longform_applies_dictionary(voice, tmp_path):
    eng = WavEngine()
    d = ReadingDictionary()
    d.set_reading("弟子屈", "テシカガ")
    synthesize_longform(eng, voice, "弟子屈へ行く。", tmp_path, dictionary=d)
    assert eng.calls[0].text == "テシカガへ行く。"


def test_failure_keeps_completed_chunks(voice, tmp_path):
    """The reason this module exists: a crash must not lose finished work."""
    eng = WavEngine(fail_on=1)
    r = synthesize_longform(eng, voice, "一です。二です。三です。", tmp_path)
    assert r.job.state == FAILED
    assert r.job.done_chunks == [0]          # chunk 0 survived
    assert (tmp_path / "chunk_00000.wav").exists()
    assert not (tmp_path / "chunk_00001.wav").exists()


def test_resume_reuses_existing_audio(voice, tmp_path):
    eng = WavEngine(fail_on=1)
    synthesize_longform(eng, voice, "一です。二です。三です。", tmp_path)

    eng2 = WavEngine()
    r = synthesize_longform(eng2, voice, "一です。二です。三です。", tmp_path)
    assert r.ok, r.errors
    assert r.resumed == 1                     # chunk 0 reused, not regenerated
    assert len(eng2.calls) == 2                # only 1 and 2 were synthesized
    assert len(r.chunk_paths) == 3


def test_cancel_stops_between_chunks(voice, tmp_path):
    eng = WavEngine()
    job = Job(id="j", voice_id="yuki", lang="ja")

    def cancel_after_first(j):
        if len(j.done_chunks) == 1:
            j.request_cancel()

    r = synthesize_longform(
        eng, voice, "一です。二です。三です。", tmp_path,
        job=job, on_progress=cancel_after_first)
    assert r.job.state == FAILED
    assert "cancelled" in r.errors[0]
    # Cancel is cooperative: it takes effect at the next chunk boundary, so
    # exactly one chunk was generated before we stopped. Nothing is half-written.
    assert len(eng.calls) == 1
    assert (tmp_path / "chunk_00000.wav").exists()


def test_empty_script_fails_cleanly(voice, tmp_path):
    eng = WavEngine()
    r = synthesize_longform(eng, voice, "   ", tmp_path)
    assert r.job.state == FAILED
    assert not eng.calls


def test_manifest_written(voice, tmp_path):
    import json

    synthesize_longform(WavEngine(), voice, "一です。二です。", tmp_path)
    m = json.loads((tmp_path / "manifest.json").read_text())
    assert m["chunks"] == 2
    assert m["voice"] == "yuki"
    assert m["lang"] == "ja"


def test_merged_audio_is_valid_wav(voice, tmp_path):
    """Merged output must be a real wav, checked without external tools."""
    import wave

    r = synthesize_longform(WavEngine(), voice, "一です。二です。三です。", tmp_path)
    with wave.open(r.merged_path, "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 24000
        assert w.getnframes() == 3 * 2400  # three 0.1s chunks, nothing lost


def test_concat_single_file_copies(voice, tmp_path):
    src = tmp_path / "a.wav"
    src.write_bytes(b"RIFF" + b"\0" * 100)
    dst = tmp_path / "b.wav"
    _concat([src], dst)
    assert dst.read_bytes() == src.read_bytes()


def test_unsupported_language_fails_before_generating(voice, tmp_path):
    from koe_oss.core.capabilities import CapabilityError

    v = Voice(handle="x", ref_audio="/tmp/r.wav", ref_text="a", lang="xx")
    v.consent = ConsentRecord(age_ok=True)
    with pytest.raises(CapabilityError) as e:
        synthesize_longform(WavEngine(), v, "hello", tmp_path)
    assert e.value.reason == "unsupported_language"
