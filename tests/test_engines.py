"""Engine contract tests. No GPU required — these check declaration and wiring."""

import pytest

from koe_oss.core.capabilities import resolve_language
from koe_oss.core.voices import Voice, ConsentRecord
from koe_oss.engines.base import SynthRequest
from koe_oss.engines.mlx_qwen import MlxQwenEngine, _to_lang_name


def test_engine_declares_iso_codes():
    """Regression: declaring only 'Japanese' made every 'ja' request fail."""
    caps = MlxQwenEngine().capabilities()
    assert "ja" in caps.languages
    assert caps.supports("ja")


def test_engine_declares_full_names_too():
    caps = MlxQwenEngine().capabilities()
    assert caps.supports("Japanese")


def test_ja_resolves_for_mlx_engine():
    v = Voice(handle="a", ref_audio="/tmp/a.wav", ref_text="あ", lang="ja")
    v.consent = ConsentRecord(age_ok=True)
    assert resolve_language(None, v, MlxQwenEngine().capabilities()) == "ja"


def test_engine_reports_clone_support():
    caps = MlxQwenEngine().capabilities()
    assert caps.supports_clone is True
    assert caps.supports_ref_text_free is False


def test_lang_code_mapping():
    assert _to_lang_name("ja") == "Japanese"
    assert _to_lang_name("en") == "English"
    assert _to_lang_name("JA") == "Japanese"
    assert _to_lang_name("xx") == "Japanese"  # safe default, not a crash


def test_is_available_is_false_without_mlx(monkeypatch):
    """On a machine without MLX the engine must say so, not crash."""
    import builtins

    real_import = builtins.__import__

    def fake(name, *a, **kw):
        if name.startswith("mlx"):
            raise ImportError("no mlx here")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake)
    assert MlxQwenEngine().is_available() is False


def test_synth_request_carries_out_path():
    r = SynthRequest(text="あ", lang="ja", ref_audio="/tmp/a.wav", out_path="/tmp/o.wav")
    assert r.out_path == "/tmp/o.wav"
    assert r.temperature == 0.5
