"""HTTP integration: real loopback server, validation and atomic observations."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from simulators.cyclesim.viewer_server import ViewerServer


@pytest.fixture
def server():
    with ViewerServer(0) as instance:
        thread = threading.Thread(target=instance.serve_forever, daemon=True)
        thread.start()
        yield instance
        instance.shutdown()
        thread.join(timeout=3)
        assert not thread.is_alive()


def call(server, path, payload=None, *, raw=None, headers=None, timeout=3):
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}{path}", data=data,
        headers=headers or ({"Content-Type": "application/json"} if data is not None else {}),
    )
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read()
        return response.status, (json.loads(body) if "application/json" in response.headers.get("Content-Type", "") else body)


def test_real_http_session(server):
    assert server.server_address[0] == "127.0.0.1"
    status, definition = call(server, "/api/circuit")
    assert status == 200 and len(definition["components"]) == 12
    _, initial = call(server, "/api/snapshot")
    status, added = call(server, "/api/input", {"request_id": 7, "a": 255, "b": 1, "mode": "preset", "operation": "ADD"})
    assert status == 200 and added["request_id"] == 7
    assert added["buses"]["y"]["value"] == 0
    assert added["signals"]["net_c_hi"] == "1"
    assert added["state_id"] > initial["state_id"]
    assert added["model_version"] == definition["model_version"]
    status, reset = call(server, "/api/reset", {"request_id": 8})
    assert status == 200 and reset["state_id"] > added["state_id"]
    assert reset["inputs"]["a"] == reset["inputs"]["b"] == 0


def test_cpu_topology_and_download_do_not_mutate_alu(server):
    _, before = call(server, "/api/snapshot")
    for variant in ("24", "29", "35"):
        status, circuit = call(server, f"/api/cpu/circuit?variant={variant}")
        assert status == 200 and circuit["total_ic"] == int(variant)
        status, board = call(server, f"/api/cpu/netlist?variant={variant}")
        assert status == 200 and board == circuit["board"]
    assert call(server, "/api/cpu/circuit")[1]["variant"] == "35"
    assert call(server, "/api/snapshot")[1] == before
    for path in ("/cpu.js", "/cpu.css"):
        assert call(server, path)[0] == 200
    for query in ("variant=23", "variant=", "variant=24&variant=35", "file=..", "variant=35&extra=1"):
        assert call(server, "/api/cpu/circuit?" + query)[0] == 400
    assert call(server, "/api/cpu/circuit?variant=35", headers={"Host": "example.com"})[0] == 403


def test_cpu_topology_failure_is_visible_and_does_not_break_alu(server, monkeypatch):
    from simulators.cyclesim import cpu_viewer_model
    monkeypatch.setattr(cpu_viewer_model, "EVIDENCE", cpu_viewer_model.EVIDENCE.with_name("absent.json"))
    status, error = call(server, "/api/cpu/circuit")
    assert status == 503 and error["error"]
    assert call(server, "/api/circuit")[0] == 200


@pytest.mark.parametrize("value", [-1, 256, True, None, 1.5, "12"])
def test_invalid_input_preserves_state(server, value):
    _, before = call(server, "/api/snapshot")
    status, error = call(server, "/api/input", {"request_id": 1, "a": value, "b": 0, "mode": "preset", "operation": "ADD"})
    assert status == 400 and error["error"]
    _, after = call(server, "/api/snapshot")
    assert before == after


def test_transport_rejects_malformed_and_foreign_requests(server):
    assert call(server, "/api/input", raw=b"{")[0] == 400
    assert call(server, "/api/input", raw=b"[]")[0] == 400
    assert call(server, "/api/reset", {"request_id": True})[0] == 400
    assert call(server, "/api/reset", {"request_id": 1}, headers={"Content-Type": "text/plain"})[0] == 415
    assert call(server, "/api/reset", {"request_id": 1}, headers={"Content-Type": "application/json", "Origin": "https://example.com"})[0] == 403
    assert call(server, "/api/snapshot", headers={"Host": "example.com"})[0] == 403
    assert call(server, "/../viewer_model.py")[0] == 404
    assert call(server, "/unknown", {"request_id": 1})[0] == 404


def test_direct_controls_and_rejected_control_are_atomic(server):
    payload = {"request_id": 1, "a": 0x12, "b": 0x34, "mode": "direct", "operation": "ADD",
               "controls": {"cin": 0, "bctrl": 0, "lgc": 10, "y_mux_sel": 1}}
    status, result = call(server, "/api/input", payload)
    assert status == 200
    assert result["buses"]["y"]["value"] == 0x12
    assert result["cpu_policy"]["acc_write"] is None
    assert result["comparison"]["match"] is True
    for control, value in (("cin", True), ("bctrl", 16), ("lgc", -1), ("y_mux_sel", 2)):
        bad = dict(payload, controls={**payload["controls"], control: value})
        assert call(server, "/api/input", bad)[0] == 400
    _, after = call(server, "/api/snapshot")
    assert after["state_id"] == result["state_id"]
    assert after["inputs"] == result["inputs"]


def test_assets_are_local_and_available(server):
    for path in ("/", "/style.css", "/app.js", "/placement.js", "/placement.css"):
        status, body = call(server, path)
        assert status == 200 and body


def test_placement_api_does_not_mutate_simulator(server):
    _, before = call(server, "/api/snapshot")
    status, profile = call(server, "/api/placement/profile")
    assert status == 200 and profile["profile"]["rows"] == 63
    # Collision-aware routing of up to eight candidates takes about 9 s.
    # Retain the suite's 30 s wall cap and the 3 s budget for ordinary APIs.
    status, result = call(server, "/api/placement/search", {"request_id": 2, "settings": {"iterations": 40}}, timeout=20)
    assert status == 200 and result["request_id"] == 2
    candidate = result["candidates"][0]
    payload = {"request_id": 3, "settings": result["settings"], "boards": candidate["boards"], "placements": candidate["placements"]}
    status, checked = call(server, "/api/placement/evaluate", payload)
    assert status == 200 and checked["candidate"]["id"] == candidate["id"]
    assert call(server, "/api/placement/search", {"request_id": 4, "settings": {"board_count": 1}})[0] == 400
    assert call(server, "/api/placement/evaluate", {"request_id": 4})[0] == 400
    with server.placement_lock:
        assert call(server, "/api/placement/search", {"request_id": 5, "settings": {}})[0] == 409
    _, after = call(server, "/api/snapshot")
    assert after == before
