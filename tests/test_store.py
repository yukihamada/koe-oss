"""Store tests. Persistence is easy to get subtly wrong; pin it down."""

import json

import pytest

from koe_oss.core.jobs import Job, GENERATING
from koe_oss.core.readings import ReadingDictionary
from koe_oss.core.store import Store
from koe_oss.core.voices import Voice, VoiceRegistry


def test_store_creates_dir(tmp_path):
    s = Store(tmp_path / "nested")
    assert s.dir.exists()


def test_voices_roundtrip(tmp_path):
    s = Store(tmp_path)
    reg = VoiceRegistry()
    reg.add(Voice(handle="yuki", ref_audio="/tmp/a.wav", ref_text="あ"))
    reg.grant_consent("yuki", age_ok=True)
    s.save_voices(reg)

    loaded = s.load_voices()
    assert loaded.get("yuki").consent_state == "current"


def test_readings_roundtrip(tmp_path):
    s = Store(tmp_path)
    d = ReadingDictionary()
    d.set_reading("弟子屈", "テシカガ")
    d.propose("市場", "イチバ")
    s.save_readings(d)

    loaded = s.load_readings()
    assert loaded.apply("弟子屈") == "テシカガ"
    assert len(loaded.proposed_entries()) == 1


def test_jobs_roundtrip(tmp_path):
    s = Store(tmp_path)
    j = Job(id="j1", voice_id="yuki", state=GENERATING)
    j.set_total_chunks(3)
    j.mark_chunk_done(0)
    s.save_jobs({"j1": j})

    loaded = s.load_jobs()["j1"]
    assert loaded.state == GENERATING
    assert loaded.done_chunks == [0]
    assert loaded.remaining_chunks() == [1, 2]


def test_missing_files_give_empty_store(tmp_path):
    s = Store(tmp_path)
    assert len(s.load_voices()) == 0
    assert s.load_readings().apply("あ") == "あ"
    assert s.load_jobs() == {}


def test_corrupt_file_does_not_crash(tmp_path):
    """A truncated store must not take the app down."""
    s = Store(tmp_path)
    (tmp_path / "voices.json").write_text("{not json")
    assert len(s.load_voices()) == 0
    assert (tmp_path / "voices.json.corrupt").exists()


def test_write_is_atomic(tmp_path):
    """No partial file should ever be visible at the real path."""
    s = Store(tmp_path)
    s.save_voices(VoiceRegistry())
    assert json.loads((tmp_path / "voices.json").read_text()) == {"voices": []}
    assert not list(tmp_path.glob("*.tmp"))


def test_delete_voice_data_removes_files(tmp_path):
    s = Store(tmp_path)
    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "yuki").mkdir()
    (tmp_path / "audio" / "yuki" / "out.wav").write_bytes(b"x")
    removed = s.delete_voice_data("yuki")
    assert not (tmp_path / "audio" / "yuki").exists()
    assert removed


def test_delete_unknown_voice_is_noop(tmp_path):
    s = Store(tmp_path)
    assert s.delete_voice_data("ghost") == []


def test_data_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("KOE_DATA_DIR", str(tmp_path / "x"))
    from koe_oss.core.store import default_data_dir

    assert default_data_dir() == tmp_path / "x"
