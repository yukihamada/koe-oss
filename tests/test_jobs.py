import pytest

from koe_oss.core.jobs import (
    Job,
    InvalidTransition,
    QUEUED,
    PREPARING,
    GENERATING,
    CHECKING,
    COMPLETED,
    FAILED,
    CANCELLED,
)


def make_job(total=3):
    j = Job(id="j1", voice_id="yuki")
    j.transition(PREPARING)
    j.set_total_chunks(total)
    return j


def test_happy_path():
    j = make_job(2)
    j.transition(GENERATING)
    j.mark_chunk_done(0)
    j.mark_chunk_done(1)
    j.transition(CHECKING)
    j.transition(COMPLETED)
    assert j.state == COMPLETED
    assert j.progress == 1.0


def test_illegal_transition_raises():
    j = Job(id="j", voice_id="v")
    with pytest.raises(InvalidTransition):
        j.transition(COMPLETED)


def test_terminal_states_are_final():
    for terminal in (COMPLETED, FAILED, CANCELLED):
        j = Job(id="j", voice_id="v", state=terminal)
        with pytest.raises(InvalidTransition):
            j.transition(GENERATING)


def test_cancel_from_active_states():
    for active in (QUEUED, PREPARING, GENERATING, CHECKING):
        j = Job(id="j", voice_id="v", state=active)
        j.transition(CANCELLED)
        assert j.state == CANCELLED


def test_progress_is_zero_until_chunks_known():
    j = Job(id="j", voice_id="v")
    assert j.progress == 0.0


def test_progress_counts_done_chunks():
    j = make_job(4)
    j.mark_chunk_done(0)
    j.mark_chunk_done(1)
    assert j.progress == 0.5


def test_remaining_chunks_for_resume():
    j = make_job(3)
    j.mark_chunk_done(1)
    assert j.remaining_chunks() == [0, 2]


def test_partial_progress_survives_failure():
    """The whole point: a failed job keeps what it finished, so it can resume."""
    j = make_job(5)
    j.transition(GENERATING)
    j.mark_chunk_done(0)
    j.mark_chunk_done(1)
    j.transition(FAILED, "engine crashed")
    assert j.state == FAILED
    assert j.error == "engine crashed"
    assert j.done_chunks == [0, 1]
    assert j.remaining_chunks() == [2, 3, 4]


def test_mark_chunk_is_idempotent():
    j = make_job(2)
    j.mark_chunk_done(0)
    j.mark_chunk_done(0)
    assert j.done_chunks == [0]


def test_mark_chunk_out_of_range():
    j = make_job(2)
    with pytest.raises(IndexError):
        j.mark_chunk_done(5)


def test_negative_total_rejected():
    j = Job(id="j", voice_id="v")
    with pytest.raises(ValueError):
        j.set_total_chunks(-1)


def test_cancel_request_is_cooperative():
    j = make_job(2)
    j.transition(GENERATING)
    j.request_cancel()
    assert j.cancel_requested is True
    assert j.state == GENERATING  # not killed mid-inference


def test_checking_can_go_back_to_generating():
    """A failed read-check sends the job back for one more pass."""
    j = make_job(1)
    j.transition(GENERATING)
    j.transition(CHECKING)
    j.transition(GENERATING)
    assert j.state == GENERATING


def test_completed_clears_error():
    j = make_job(1)
    j.transition(GENERATING)
    j.transition(FAILED, "boom")
    j2 = make_job(1)
    j2.transition(GENERATING)
    j2.mark_chunk_done(0)
    j2.transition(CHECKING)
    j2.transition(COMPLETED)
    assert j2.error is None


def test_to_dict_shape():
    j = make_job(2)
    d = j.to_dict()
    assert d["id"] == "j1"
    assert d["total_chunks"] == 2
    assert d["progress"] == 0.0
    assert "remaining_chunks" in d
