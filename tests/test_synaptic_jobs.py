"""Job journal used by Synaptic Model Manager to recover a synthesis after
losing its transport (synaptic_jobs.py). No model is loaded."""

import time

import pytest
from fastapi.testclient import TestClient

import synaptic_jobs
from server import app


@pytest.fixture(autouse=True)
def journal_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SYNAPTIC_JOBS_DIR", str(tmp_path))
    monkeypatch.delenv("SYNAPTIC_REQUIRE_JOB_ID", raising=False)
    return tmp_path


def test_result_is_recorded_even_if_nobody_awaits_the_response():
    gate = __import__("threading").Event()

    def work():
        gate.wait(5)
        return b"RIFFfake-audio"

    future = synaptic_jobs.submit("job-aaaaaaaa", "wav", work)
    assert synaptic_jobs.begin("job-aaaaaaaa", "wav") is None  # claimed for this boot
    assert synaptic_jobs.begin("job-aaaaaaaa", "wav")["status"] == "running"
    gate.set()  # the HTTP caller may already be gone; the thread finishes anyway
    future.result(5)
    deadline = time.time() + 5
    while synaptic_jobs.get("job-aaaaaaaa")["status"] != "succeeded" and time.time() < deadline:
        time.sleep(0.01)
    record = synaptic_jobs.get("job-aaaaaaaa")
    assert record["status"] == "succeeded" and record["bytes"] == len(b"RIFFfake-audio")
    assert synaptic_jobs.audio("job-aaaaaaaa") == b"RIFFfake-audio"
    assert synaptic_jobs.begin("job-aaaaaaaa", "wav")["status"] == "succeeded"  # idempotent replay


def test_failure_is_recorded_and_job_can_be_retried():
    def work():
        raise RuntimeError("engine exploded")

    future = synaptic_jobs.submit("job-bbbbbbbb", "wav", work)
    with pytest.raises(RuntimeError):
        future.result(5)
    deadline = time.time() + 5
    while (synaptic_jobs.get("job-bbbbbbbb") or {}).get("status") != "failed" and time.time() < deadline:
        time.sleep(0.01)
    assert "engine exploded" in synaptic_jobs.get("job-bbbbbbbb")["error"]
    assert synaptic_jobs.begin("job-bbbbbbbb", "wav") is None


def test_running_entry_from_previous_process_is_reported_lost(monkeypatch):
    assert synaptic_jobs.begin("job-cccccccc", "wav") is None
    monkeypatch.setattr(synaptic_jobs, "BOOT_ID", "another-boot")
    assert synaptic_jobs.get("job-cccccccc")["status"] == "lost"
    assert synaptic_jobs.begin("job-cccccccc", "wav") is None  # lost work may be re-run


def test_tampered_audio_is_not_served(journal_dir):
    synaptic_jobs.finish("job-dddddddd", b"RIFFgood", "wav")
    (journal_dir / "job-dddddddd.wav").write_bytes(b"RIFFevil")
    assert synaptic_jobs.audio("job-dddddddd") is None


def test_http_contract_for_job_lookup():
    client = TestClient(app)
    missing = client.get("/api/jobs/job-eeeeeeee")
    assert missing.status_code == 404 and missing.json()["boot_id"] == synaptic_jobs.BOOT_ID
    synaptic_jobs.finish("job-eeeeeeee", b"RIFFdone", "wav")
    found = client.get("/api/jobs/job-eeeeeeee").json()
    assert found["status"] == "succeeded" and found["server"]["boot_id"] == synaptic_jobs.BOOT_ID
    assert client.get("/api/jobs/job-eeeeeeee/audio").content == b"RIFFdone"
    assert client.get("/api/jobs/bad id!").status_code in (400, 404)


def test_require_job_id_closes_direct_generation(monkeypatch):
    monkeypatch.setenv("SYNAPTIC_REQUIRE_JOB_ID", "1")
    client = TestClient(app)
    direct = client.post("/tts", json={"text": "Hola", "voice_mode": "predefined",
                                       "predefined_voice_id": "Elena.wav"})
    assert direct.status_code == 403
    openai = client.post("/v1/audio/speech", json={"input": "Hola", "voice": "Elena.wav"})
    assert openai.status_code in (403, 422)
    bad = client.post("/tts", headers={"X-Synaptic-Job-Id": "x"}, json={"text": "Hola"})
    assert bad.status_code == 400
