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


def call(server, path, payload=None, *, raw=None, headers=None):
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}{path}", data=data,
        headers=headers or ({"Content-Type": "application/json"} if data is not None else {}),
    )
    try:
        response = urllib.request.urlopen(request, timeout=3)
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
    for path in ("/", "/style.css", "/app.js"):
        status, body = call(server, path)
        assert status == 200 and body
