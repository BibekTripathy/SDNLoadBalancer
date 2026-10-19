"""
Phase 6: the /api/tcp-lab endpoints and the live cwnd stream on /ws/events.

Every test points the API at a temporary results folder (TCP_LAB_RESULTS_DIR)
filled with a real simulator run of S1 and a small fake Mininet run of S3,
so nothing depends on the results/ folder of the machine running the tests.
"""

import csv
import json
import os

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.tcp_lab import live
from tcp_lab.mininet.ss_sampler import SS_COLUMNS
from tcp_lab.run_sim_scenarios import run_scenario
from tcp_lab.simulator.scenarios import SCENARIOS


def write_fake_mininet_run(results_dir):
    """S3 loss_1pct, run 1: one flow; ss shows the handshake, then cwnd 1, 2, 4."""
    run_dir = os.path.join(results_dir, "S3", "loss_1pct", "mininet_run1")
    os.makedirs(run_dir)
    with open(os.path.join(run_dir, "run.json"), "w") as handle:
        json.dump({"flows": [{"flow": 0, "client": "c1", "ss": {"local": "10.0.0.11:4000"}}]},
                  handle)
    samples = [
        (1.10, "SYN-SENT", 10, "", ""),          # handshake: must be left out
        (1.15, "ESTAB", 1, "", 40.1),
        (1.20, "ESTAB", 2, "", 40.2),
        (1.25, "ESTAB", 4, "", 40.3),
    ]
    with open(os.path.join(run_dir, "ss_c1.csv"), "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SS_COLUMNS)
        writer.writeheader()
        for time_s, state, cwnd, ssthresh, rtt in samples:
            writer.writerow({"time": time_s, "local": "10.0.0.11:4000",
                             "peer": "10.0.0.21:5201", "state": state, "cc": "reno",
                             "cwnd": cwnd, "ssthresh": ssthresh, "rtt_ms": rtt})
    with open(os.path.join(results_dir, "S3", "mininet_summary.json"), "w") as handle:
        json.dump({"scenario": "S3", "source": "mininet", "variants": []}, handle)


@pytest.fixture(scope="module")
def results_dir(tmp_path_factory):
    folder = str(tmp_path_factory.mktemp("results"))
    run_scenario("S1", ["tahoe", "reno", "newreno"], folder, make_plots=False)
    write_fake_mininet_run(folder)
    return folder


@pytest.fixture
def client(results_dir, monkeypatch):
    monkeypatch.setenv("TCP_LAB_RESULTS_DIR", results_dir)
    # "with" keeps one event loop for requests AND the WebSocket, as under uvicorn
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Reading results
# ---------------------------------------------------------------------------
def test_scenarios_say_which_results_exist(client):
    items = client.get("/api/tcp-lab/scenarios").json()
    by_id = {}
    for item in items:
        by_id[item["id"]] = item
    assert list(by_id.keys()) == list(SCENARIOS.keys())
    assert by_id["S1"]["has_simulator_results"] is True
    assert by_id["S1"]["has_mininet_version"] is False
    assert by_id["S3"]["has_mininet_results"] is True
    assert by_id["S2"]["has_simulator_results"] is False
    assert by_id["S2"]["variants"][0]["label"] == "2_losses"


def test_scenario_results_are_labelled(client):
    data = client.get("/api/tcp-lab/results/S1").json()
    assert data["simulator"]["source"] == "simulator"
    assert data["mininet"] is None
    assert client.get("/api/tcp-lab/results/S9").status_code == 404


def test_timeseries_from_both_sources(client):
    data = client.get("/api/tcp-lab/results/S1/1_loss/timeseries").json()
    assert data["simulator"]["source"] == "simulator"
    assert set(data["simulator"]["algorithms"]) == {"tahoe", "reno", "newreno"}
    assert data["mininet"] is None

    data = client.get("/api/tcp-lab/results/S3/loss_1pct/timeseries").json()
    assert data["mininet_runs"] == [1]
    cwnd = data["mininet"]["cwnd"]
    assert data["mininet"]["source"] == "mininet"
    # handshake sample dropped, times start at 0 for flow 0
    assert [point["cwnd"] for point in cwnd] == [1, 2, 4]
    assert cwnd[0]["time"] == 0.0
    assert cwnd[2]["time"] == pytest.approx(0.1)


def test_unknown_or_unsafe_names_are_404(client):
    for url in ["/api/tcp-lab/results/S1/nope/timeseries",
                "/api/tcp-lab/results/S1/..%2F..%2Fetc/timeseries",
                "/api/tcp-lab/analysis/plots/..%2Freport.md",
                "/api/tcp-lab/analysis/plots/report.md",
                "/api/tcp-lab/analysis"]:          # no analysis written in this folder
        assert client.get(url).status_code == 404, url
    assert client.get("/api/tcp-lab/analysis/plots").json() == []


# ---------------------------------------------------------------------------
# Live stream
# ---------------------------------------------------------------------------
def read_until(ws, message_type):
    received = []
    while True:
        message = ws.receive_json()
        received.append(message)
        if message["type"] == message_type:
            return received


def test_live_simulation_streams_cwnd_and_losses(client):
    with client.websocket_connect("/ws/events") as ws:
        answer = client.post("/api/tcp-lab/live/simulate",
                             json={"scenario": "S2", "variant": "3_losses", "speed": 40})
        assert answer.status_code == 200
        assert answer.json()["state"] == "running"
        received = read_until(ws, "TCP_LAB_RUN_FINISHED")

    assert received[0]["type"] == "TCP_LAB_RUN_STARTED"
    assert received[0]["source"] == "simulator"
    samples = [m for m in received if m["type"] == "TCP_CWND_SAMPLE"]
    losses = [m for m in received if m["type"] == "TCP_LOSS_EVENT"]
    # 3 algorithms x 4 s / 50 ms
    assert 230 <= len(samples) <= 240
    assert {m["algorithm"] for m in samples} == {"tahoe", "reno", "newreno"}
    assert all(m["source"] == "simulator" for m in samples)
    times = [m["time"] for m in samples]
    assert times == sorted(times)
    # every algorithm sees the 3 scripted drops
    assert len([m for m in losses if m["event"] == "DROP_SCRIPTED"]) == 9
    finished = received[-1]["results"]
    timeouts = {row["algorithm"]: row["timeouts"] for row in finished}
    assert timeouts == {"tahoe": 0, "reno": 1, "newreno": 0}
    assert client.get("/api/tcp-lab/live").json()["state"] == "finished"


def test_replay_and_stop(client):
    with client.websocket_connect("/ws/events") as ws:
        answer = client.post("/api/tcp-lab/live/replay",
                             json={"scenario": "S3", "variant": "loss_1pct", "run": 1, "speed": 0.25})
        assert answer.json()["source"] == "mininet"
        started = ws.receive_json()
        first = ws.receive_json()
        assert started["type"] == "TCP_LAB_RUN_STARTED"
        assert first["type"] == "TCP_CWND_SAMPLE"
        assert first["algorithm"] == "linux_reno" and first["cwnd"] == 1
        assert first["state"] is None         # ss does not report the TCP state machine
        stop = client.post("/api/tcp-lab/live/stop").json()
        assert stop["stopped"] is True
        assert read_until(ws, "TCP_LAB_RUN_STOPPED")[-1]["reason"] == "stopped by user"
    assert client.post("/api/tcp-lab/live/stop").json()["stopped"] is False


def test_live_request_checks(client):
    def simulate(body):
        return client.post("/api/tcp-lab/live/simulate", json=body).status_code

    assert simulate({"scenario": "S2", "variant": "nope"}) == 404
    assert simulate({"scenario": "S2", "variant": "3_losses", "algorithms": ["cubic"]}) == 404
    assert simulate({"scenario": "S2", "variant": "3_losses", "speed": 0}) == 422
    assert simulate({"scenario": "S2", "variant": "3_losses", "algorithms": []}) == 422
    # S1 was never run on Mininet
    assert client.post("/api/tcp-lab/live/replay",
                       json={"scenario": "S1", "variant": "1_loss"}).status_code == 404


def test_simulated_messages_are_in_time_order():
    variant = SCENARIOS["S1"]["variants"][0]
    messages, rows = live.simulated_messages(variant, ["newreno"], 1, "test")
    times = [m["time"] for m in messages]
    assert times == sorted(times)
    assert rows[0]["source"] == "simulator" and rows[0]["retransmissions"] == 1
