"""Loopback-only, dependency-free HTTP transport for the Python ALU session."""

from __future__ import annotations

import json
import hashlib
import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from simulators.cyclesim.viewer_model import AluSession, circuit_definition
from simulators.cyclesim.cpu_viewer_model import cpu_circuit
from simulators.cyclesim.breadboard import search, evaluate, PROFILE, LIMITATIONS, VERSION

WEB_ROOT = Path(__file__).with_name("viewer") / "web"
ASSETS = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/wiring.js": ("wiring.js", "text/javascript"), "/wiring.css": ("wiring.css", "text/css"),
          "/placement.js": ("placement.js", "text/javascript"), "/placement.css": ("placement.css", "text/css"),
          "/cpu.js": ("cpu.js", "text/javascript"), "/cpu.css": ("cpu.css", "text/css"),
          "/style.css": ("style.css", "text/css")}
MAX_BODY = 8192


class ViewerServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int = 8765):
        self.session = AluSession()
        self.session_lock = threading.Lock()
        self.placement_lock = threading.Lock()
        super().__init__(("127.0.0.1", port), ViewerHandler)


class ViewerHandler(BaseHTTPRequestHandler):
    server: ViewerServer

    def log_message(self, format, *args):
        pass

    def respond(self, status: int, data, mime="application/json"):
        raw = (json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
               if mime == "application/json" else data)
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def local_request(self) -> bool:
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if self.headers.get("Host") not in allowed:
            self.respond(403, {"error": "로컬 호스트 요청만 허용합니다."})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + host for host in allowed}:
            self.respond(403, {"error": "같은 로컬 화면에서 요청해 주세요."})
            return False
        return True

    def do_GET(self):
        if not self.local_request():
            return
        path = urlsplit(self.path).path
        if path == "/api/revision":
            digest = hashlib.sha256()
            for name, _ in ASSETS.values():
                digest.update((WEB_ROOT / name).read_bytes())
            self.respond(200, {"revision": f"{os.getpid()}:{digest.hexdigest()}"})
        elif path == "/api/placement/profile":
            self.respond(200, {"version": VERSION, "profile": PROFILE, "limitations": LIMITATIONS})
        elif path == "/api/circuit":
            self.respond(200, circuit_definition())
        elif path in ("/api/cpu/circuit", "/api/cpu/netlist"):
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            if set(query) - {"variant"} or ("variant" in query and query["variant"] not in (["24"], ["29"], ["35"])):
                self.respond(400, {"error": "variant는 24, 29, 35 중 하나만 지정하세요."})
                return
            try:
                circuit = cpu_circuit(query.get("variant", ["35"])[0])
            except (OSError, ValueError, KeyError, AssertionError):
                logging.exception("CPU topology evidence could not be verified")
                self.respond(503, {"error": "CPU 연결표 검증 자료를 불러올 수 없습니다. 서버 로그를 확인해 주세요."})
                return
            self.respond(200, circuit["board"] if path.endswith("netlist") else circuit)
        elif path == "/api/snapshot":
            with self.server.session_lock:
                snapshot = self.server.session.snapshot()
            self.respond(200, snapshot)
        elif path in ASSETS:
            filename, mime = ASSETS[path]
            self.respond(200, (WEB_ROOT / filename).read_bytes(), mime)
        else:
            self.respond(404, {"error": "경로를 찾을 수 없습니다."})

    def do_POST(self):
        if not self.local_request():
            return
        path = urlsplit(self.path).path
        if path not in ("/api/input", "/api/reset", "/api/placement/search", "/api/placement/evaluate"):
            self.respond(404, {"error": "경로를 찾을 수 없습니다."})
            return
        if self.headers.get_content_type() != "application/json":
            self.respond(415, {"error": "application/json 요청이 필요합니다."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                raise ValueError("요청 크기가 올바르지 않습니다.")
            self.connection.settimeout(5)
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("JSON 객체가 필요합니다.")
            request_id = payload.get("request_id")
            if type(request_id) is not int or request_id < 0:
                raise ValueError("request_id는 0 이상의 정수여야 합니다.")
            if path.startswith("/api/placement/"):
                if set(payload) != {"request_id", "settings"} and path.endswith("search"):
                    raise ValueError("탐색 요청에는 request_id, settings만 지정하세요.")
                if not self.server.placement_lock.acquire(blocking=False):
                    self.respond(409, {"error": "다른 배치 탐색이 실행 중입니다. 잠시 후 다시 시도하세요."})
                    return
                try:
                    if path.endswith("search"):
                        result = search(payload["settings"])
                    else:
                        result = {"candidate": evaluate({k:v for k,v in payload.items() if k!="request_id"}), "version": VERSION, "profile": PROFILE, "limitations": LIMITATIONS}
                finally:
                    self.server.placement_lock.release()
                self.respond(200, dict(result, request_id=request_id))
                return
            with self.server.session_lock:
                snapshot = (self.server.session.reset() if path == "/api/reset"
                            else self.server.session.update({k: v for k, v in payload.items() if k != "request_id"}))
            snapshot = dict(snapshot, request_id=request_id)
        except (ValueError, UnicodeError, TimeoutError) as exc:
            self.respond(400, {"error": str(exc)})
            return
        except Exception:
            logging.exception("ALU viewer request failed")
            self.respond(500, {"error": "시뮬레이션 요청에 실패했습니다. 서버 로그를 확인해 주세요."})
            return
        self.respond(200, snapshot)


def serve(port: int = 8765) -> None:
    with ViewerServer(port) as server:
        print(f"Swiver circuit viewer: http://127.0.0.1:{server.server_port}", flush=True)
        print(f"CPU topology: http://127.0.0.1:{server.server_port}/?view=cpu&variant=35", flush=True)
        print("Zero-delay functional model; Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
