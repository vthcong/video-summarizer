"""Native Messaging host: starts the summarizer server on demand for the Chrome extension.

Chrome launches this process, sends one message, and waits for one reply. Messages are
JSON, each prefixed with its length as a 4-byte little-endian integer. Nothing else may
be written to stdout - the server's own output goes to logs/server.log.
"""

import getpass
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
PORT = 8000
HEALTH_URL = f"http://127.0.0.1:{PORT}/api/health"
PAGE_URL = f"http://localhost:{PORT}/"
IDLE_SHUTDOWN_MINUTES = 30  # the server stops itself after this long without use
STARTUP_TIMEOUT = 30  # seconds


def read_message() -> dict | None:
    header = sys.stdin.buffer.read(4)
    if len(header) < 4:
        return None
    (length,) = struct.unpack("<I", header)
    return json.loads(sys.stdin.buffer.read(length))


def send_message(message: dict) -> None:
    data = json.dumps(message).encode()
    sys.stdout.buffer.write(struct.pack("<I", len(data)) + data)
    sys.stdout.buffer.flush()


def server_state() -> str:
    """'ours' if the summarizer is answering, 'other' if something else holds the port, else 'down'."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=1) as resp:
            return "ours" if json.load(resp).get("app") == "video-summarizer" else "other"
    except urllib.error.HTTPError:
        return "other"
    except (urllib.error.URLError, OSError, ValueError):
        return "down"


def start_server() -> None:
    env = os.environ.copy()
    # Chrome starts us with a minimal PATH; the summarizer needs to find the `claude` CLI.
    extra = [str(Path.home() / ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin"]
    env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "/usr/bin:/bin")])
    # The `claude` CLI needs these to read its saved login from the macOS Keychain.
    env.setdefault("USER", getpass.getuser())
    env.setdefault("TMPDIR", tempfile.gettempdir())
    env["IDLE_SHUTDOWN_MINUTES"] = str(IDLE_SHUTDOWN_MINUTES)

    log_dir = PROJECT / "logs"
    log_dir.mkdir(exist_ok=True)
    with open(log_dir / "server.log", "w") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
            cwd=PROJECT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # keep running after Chrome closes this host process
        )

    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if server_state() == "ours":
            return
        if proc.poll() is not None and server_state() != "ours":
            raise RuntimeError(f"The server failed to start. See {log_dir / 'server.log'}")
        time.sleep(0.3)
    raise RuntimeError(f"The server didn't start within {STARTUP_TIMEOUT}s. See {log_dir / 'server.log'}")


def main() -> None:
    if read_message() is None:
        return
    try:
        state = server_state()
        if state == "other":
            raise RuntimeError(f"Port {PORT} is already used by another program.")
        if state == "down":
            start_server()
        send_message({"ok": True, "url": PAGE_URL})
    except Exception as e:
        send_message({"ok": False, "error": str(e)})


if __name__ == "__main__":
    main()
