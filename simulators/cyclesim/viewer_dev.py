"""Opt-in development supervisor: restart Python after source edits."""
from pathlib import Path
import subprocess
import sys
import time


def signature():
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size)
                 for p in sorted(Path(__file__).parent.rglob("*.py")))


def serve_reload(port):
    if port == 0:
        raise ValueError("--reload requires a fixed port")
    child = None
    try:
        previous = signature()
        while True:
            if child is None:
                child = subprocess.Popen([sys.executable, "-m", "simulators.cyclesim", "viewer", "--port", str(port)])
            time.sleep(0.5)
            current = signature()
            if current != previous:
                time.sleep(0.3)
                child.terminate()
                child.wait(timeout=5)
                previous, child = signature(), None
                print("Python changed; restarting viewer (simulation resets).", flush=True)
            elif child.poll() is not None:
                raise RuntimeError(f"Viewer exited: {child.returncode}")
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait(timeout=5)
