"""Unit tests for web.jobs — job registry and state machine.

All tests are hermetic (no HTTP, no engine, no API key): they exercise the
JobRegistry directly. The state-machine rules are: QUEUED → RUNNING → DONE or
FAILED. Registry.get() must return the same object across calls.
"""
from web.jobs import Job, JobStatus, JobRegistry


# --- JobRegistry.create -------------------------------------------------------

def test_create_returns_queued_job():
    reg = JobRegistry()
    job = reg.create()
    assert job.status == JobStatus.QUEUED


def test_create_assigns_unique_string_id():
    reg = JobRegistry()
    j1 = reg.create()
    j2 = reg.create()
    assert isinstance(j1.id, str) and len(j1.id) > 0
    assert j1.id != j2.id


def test_create_initialises_optional_fields_to_none():
    reg = JobRegistry()
    job = reg.create()
    assert job.report_id is None
    assert job.error is None


# --- JobRegistry.get ----------------------------------------------------------

def test_get_returns_same_object_as_create():
    reg = JobRegistry()
    job = reg.create()
    assert reg.get(job.id) is job


def test_get_unknown_id_returns_none():
    reg = JobRegistry()
    assert reg.get("does-not-exist") is None


# --- JobRegistry.update -------------------------------------------------------

def test_update_status_to_running():
    reg = JobRegistry()
    job = reg.create()
    reg.update(job.id, status=JobStatus.RUNNING)
    assert job.status == JobStatus.RUNNING


def test_update_to_done_sets_report_id():
    reg = JobRegistry()
    job = reg.create()
    reg.update(job.id, status=JobStatus.DONE, report_id=42)
    assert job.status == JobStatus.DONE
    assert job.report_id == 42


def test_update_to_failed_sets_error():
    reg = JobRegistry()
    job = reg.create()
    reg.update(job.id, status=JobStatus.FAILED, error="Stockfish not found")
    assert job.status == JobStatus.FAILED
    assert job.error == "Stockfish not found"


def test_update_unknown_id_is_a_noop():
    reg = JobRegistry()
    reg.update("ghost", status=JobStatus.DONE)  # must not raise


def test_update_is_reflected_via_get():
    reg = JobRegistry()
    job = reg.create()
    reg.update(job.id, status=JobStatus.DONE, report_id=7)
    fetched = reg.get(job.id)
    assert fetched.status == JobStatus.DONE
    assert fetched.report_id == 7


# --- JobStatus enum -----------------------------------------------------------

def test_status_values_are_lowercase_strings():
    assert JobStatus.QUEUED == "queued"
    assert JobStatus.RUNNING == "running"
    assert JobStatus.DONE == "done"
    assert JobStatus.FAILED == "failed"
