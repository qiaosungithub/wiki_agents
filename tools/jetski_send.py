#!/usr/bin/env python3
"""Send messages to a Jetski conversation safely, and confirm the agent replied.

Owning guide: harness/skills/agent-messaging/SKILL.md

  jetski_send.py find <title-substring>            list matching conversations + status
  jetski_send.py status <conv>                     print the conversation's run status
  jetski_send.py send <conv> <text | @file>        wait for IDLE, send, wait for the reply
  jetski_send.py feed <conv> <file> [--first N] [--last M] [--notify SESSION]
                                                   send messages split on '===MSG===' one per turn
  jetski_send.py pty-send <conv> <text | @file>    for conversations hosted by a `gemini` helper PTY
                                                   daemon: type the message into the live CLI
  jetski_send.py live-status <conv>                read-only: PTY host + last steps from the live store

Safety rules this enforces (each one was a real failure):
  * `--model` is always passed. A conversation started by the `gemini` CLI helper
    has no model stored on the hub, and a send without `--model` dies with
    "plan model not specified" while the CLI still prints "Message sent".
  * A message is sent only after two consecutive IDLE polls. Sending while the
    conversation is RUNNING preempts the in-flight turn (its tool call is
    abandoned). `send --interrupt` skips the wait on purpose.
  * Success means an assistant `planner_response` step exists after the message
    once the conversation is IDLE again. Exit code 0 from the CLI proves nothing,
    and `error_message` steps are not failures by themselves (Jetski logs a
    retried 429/400 that way and still finishes the turn).
  * The status regex does not depend on `--verbose`: the plain line ends right
    after the status, with no trailing comma.
  * `send` refuses a conversation that a live `gemini` PTY daemon hosts
    (~/.gemini/jetski/pty/cid-<conv>.json with live pids). The hub's view of such a
    conversation can go stale (seen: hub stuck at step 732 and RUNNING while the
    live store had 1177 steps and was idle), so a hub send could start a second
    executor on an old copy. Use `pty-send`, or `send --force-hub` if you know better.
  * `pty-send` collapses the text to one line (Enter submits in the TUI), waits
    until the live store shows the agent idle, types the text, then a separate CR,
    and succeeds only when a user-input step with the text and an assistant step
    after it appear in ~/.gemini/jetski/conversations/<conv>.db.
Read-only commands: find, status, live-status. Exit code is non-zero on any failed check.
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time

JETSKI = os.environ.get("JETSKI_BIN", "/google/bin/releases/gemini-agents-jetski/jetski")
DEFAULT_MODEL = "Gemini 4 Argon (High)"
NOTIFY = os.path.expanduser("~/.amply/bin/amply_notify")
STATUS_RE = re.compile(r"Status: (CASCADE_RUN_STATUS_[A-Z_]+)")
IDLE = "CASCADE_RUN_STATUS_IDLE"
MAX_UNPARSED = 10
JROOT = pathlib.Path(os.environ.get("JETSKI_ROOT", "~/.gemini/jetski")).expanduser()
USER_INPUT, PLANNER_RESPONSE = 14, 15  # steps.step_type in the live sqlite store


def hub_address() -> str:
    """The local hub's port, read from the running jetski-hub-server's argv."""
    if os.environ.get("JETSKI_ADDRESS"):
        return os.environ["JETSKI_ADDRESS"]
    ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
    for line in ps.splitlines():
        if "jetski-hub-server" in line:
            m = re.search(r"--port[= ](\d+)", line)
            if m:
                return f"localhost:{m.group(1)}"
    return "localhost:5388"


class Jetski:
    def __init__(self, address: str, model: str, poll_sec: float):
        self.address, self.model, self.poll_sec = address, model, poll_sec
        self.unparsed = 0

    def run(self, *args: str, timeout: float = 120) -> subprocess.CompletedProcess:
        return subprocess.run([JETSKI, *args, f"--address={self.address}"],
                              capture_output=True, text=True, timeout=timeout)

    def listing(self, verbose: bool = False) -> list[str]:
        args = ["list-conversations", "--limit", "300"] + (["--verbose"] if verbose else [])
        return self.run(*args, timeout=90).stdout.splitlines()

    def status(self, conv: str) -> str | None:
        for line in self.listing():
            if line.startswith(f"Conversation: {conv},"):
                m = STATUS_RE.search(line)
                if m:
                    self.unparsed = 0
                    return m.group(1)
        self.unparsed += 1
        if self.unparsed >= MAX_UNPARSED:
            raise RuntimeError(f"status of {conv} unreadable for {self.unparsed} polls in a row")
        return None

    def wait_idle(self, conv: str, timeout: float) -> None:
        t0, streak = time.time(), 0
        while streak < 2:
            if time.time() - t0 > timeout:
                raise RuntimeError(f"{conv} not IDLE within {timeout:.0f}s")
            streak = streak + 1 if self.status(conv) == IDLE else 0
            if streak < 2:
                time.sleep(self.poll_sec)

    def transcript(self, conv: str) -> str:
        return self.run("get-conversation", f"--conversation={conv}").stdout

    def send_and_confirm(self, conv: str, text: str, *, interrupt: bool, timeout: float) -> str:
        if self.status(conv) is None:
            raise RuntimeError(f"conversation {conv} not found on {self.address}")
        if not interrupt:
            self.wait_idle(conv, timeout)
        p = self.run("send-message", f"--conversation={conv}", f"--model={self.model}", f"--prompt={text}")
        if p.returncode != 0:
            raise RuntimeError(f"send-message rc={p.returncode}: {p.stderr.strip().splitlines()[-1:]}")
        time.sleep(min(15.0, self.poll_sec * 2))
        self.wait_idle(conv, timeout)
        tr = self.transcript(conv)
        pos = tr.rfind(text.strip()[:60])
        if pos < 0:
            raise RuntimeError("message not found in the transcript after sending")
        after = tr[pos:]
        if "failed to construct executor" in after:
            raise RuntimeError(f"Jetski could not start the turn: {after[-300:]!r}")
        if "planner_response (Role: assistant" not in after:
            raise RuntimeError(f"turn ended without an assistant reply: {after[-400:]!r}")
        return after


def pty_host(conv: str) -> dict | None:
    """Metadata of the live `gemini` PTY daemon hosting *conv*, or None.

    Checks `cid-<conv>.json` first, then every per-daemon `d-*.json`: the cid index file
    can vanish while the daemon keeps running (seen on a 4-hour-old daemon), and the
    helper itself falls back the same way.
    """
    root = JROOT / "pty"
    for p in [root / f"cid-{conv}.json", *sorted(root.glob("d-*.json"))]:
        try:
            meta = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if meta.get("cid") != conv:
            continue
        pids_alive = all(pathlib.Path(f"/proc/{meta.get(k)}").exists() for k in ("daemon_pid", "cli_pid"))
        if pids_alive and os.path.exists(meta.get("sock_path", "")):
            return meta
    return None


class LiveStore:
    """Read-only view of a conversation's live sqlite store (copied before reading)."""

    def __init__(self, conv: str):
        self.src = JROOT / "conversations" / f"{conv}.db"
        if not self.src.exists():
            raise RuntimeError(f"no live store at {self.src}")

    def mtime(self) -> float:
        return max(os.path.getmtime(f"{self.src}{s}") for s in ("", "-wal")
                   if os.path.exists(f"{self.src}{s}"))

    def steps(self) -> list[tuple[int, int, str]]:
        """(idx, step_type, payload text) for every step."""
        with tempfile.TemporaryDirectory() as tmp:
            dst = os.path.join(tmp, "c.db")
            for s in ("", "-wal", "-shm"):
                if os.path.exists(f"{self.src}{s}"):
                    shutil.copy(f"{self.src}{s}", dst + s)
            con = sqlite3.connect(dst)
            try:
                rows = con.execute("select idx, step_type, step_payload from steps order by idx").fetchall()
            finally:
                con.close()
        return [(i, t, (p or b"").decode("utf-8", "ignore")) for i, t, p in rows]


class PtySender:
    """Types into the CLI of a `gemini`-helper-hosted conversation via its PTY daemon socket.

    Daemon protocol (agent-island gemini-session-helper.sh): connect AF_UNIX, read one JSON
    handshake line, then frames of type(1 byte) + big-endian u32 length + payload; an 'I'
    frame is written verbatim to the PTY master. Several clients may attach at once, so a
    user's own attached terminal is not kicked off.
    """

    def __init__(self, conv: str, poll_sec: float):
        self.conv, self.poll_sec = conv, poll_sec
        self.meta = pty_host(conv)
        if self.meta is None:
            raise RuntimeError(f"{conv} has no live gemini PTY daemon; use `send` instead")
        self.store = LiveStore(conv)

    def is_idle_once(self) -> tuple[bool, float]:
        steps = self.store.steps()
        return bool(steps) and steps[-1][1] == PLANNER_RESPONSE, self.store.mtime()

    def wait_idle(self, timeout: float) -> None:
        """Idle = last step is an assistant response and the store did not change for 2 polls."""
        t0, streak, last_m = time.time(), 0, None
        while streak < 2:
            if time.time() - t0 > timeout:
                raise RuntimeError(f"{self.conv} not idle within {timeout:.0f}s")
            idle, m = self.is_idle_once()
            streak = streak + 1 if idle and m == last_m else 0
            last_m = m
            if streak < 2:
                time.sleep(self.poll_sec)

    def type_line(self, line: str) -> None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect(self.meta["sock_path"])
        try:
            hs = b""
            while b"\n" not in hs:
                chunk = s.recv(65536)
                if not chunk:
                    raise RuntimeError("PTY daemon closed the socket before the handshake")
                hs += chunk
            if json.loads(hs.split(b"\n", 1)[0]).get("full_id") != self.conv:
                raise RuntimeError(f"PTY daemon handshake is not for {self.conv}: {hs[:200]!r}")
            for payload in (line.encode("utf-8"), b"\r"):
                s.sendall(b"I" + struct.pack("!I", len(payload)) + payload)
                self._drain(s, 1.0)  # keep reading so the daemon never blocks on us
        finally:
            s.close()

    @staticmethod
    def _drain(s: socket.socket, seconds: float) -> None:
        end = time.time() + seconds
        s.settimeout(0.2)
        while time.time() < end:
            try:
                if not s.recv(65536):
                    return
            except socket.timeout:
                pass

    def send_and_confirm(self, text: str, *, interrupt: bool, timeout: float) -> str:
        line = " ".join(text.split())
        if not line:
            raise RuntimeError("empty message")
        if not interrupt:
            self.wait_idle(timeout)
        before = self.store.steps()
        n0 = before[-1][0] if before else -1
        self.type_line(line)
        key = line[:40]
        t0, user_idx = time.time(), None
        while user_idx is None:
            if time.time() - t0 > 120:
                raise RuntimeError("typed text never showed up as a user-input step (TUI busy or in a dialog?)")
            time.sleep(5)
            user_idx = next((i for i, t, p in self.store.steps()
                             if i > n0 and t == USER_INPUT and key in p), None)
        self.wait_idle(timeout)
        replies = [i for i, t, _ in self.store.steps() if i > user_idx and t == PLANNER_RESPONSE]
        if not replies:
            raise RuntimeError(f"no assistant step after user step {user_idx}")
        return f"user step {user_idx}, assistant steps {replies[0]}..{replies[-1]}"


def notify(session: str | None, msg: str) -> None:
    print(msg, flush=True)
    if session:
        subprocess.run([NOTIFY, session, msg], capture_output=True, timeout=60)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--address", default=None, help="hub address (default: from jetski-hub-server argv)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--poll-sec", type=float, default=30.0)
    ap.add_argument("--timeout", type=float, default=6 * 3600, help="max wait per message, seconds")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("find").add_argument("pattern")
    sub.add_parser("status").add_argument("conv")
    s = sub.add_parser("send")
    s.add_argument("conv")
    s.add_argument("text")
    s.add_argument("--interrupt", action="store_true", help="send even if RUNNING (preempts the turn)")
    s.add_argument("--force-hub", action="store_true", help="send via the hub even if a PTY daemon hosts it")
    ps = sub.add_parser("pty-send")
    ps.add_argument("conv")
    ps.add_argument("text")
    ps.add_argument("--interrupt", action="store_true", help="type even if the agent is busy")
    sub.add_parser("live-status").add_argument("conv")
    f = sub.add_parser("feed")
    f.add_argument("conv")
    f.add_argument("file")
    f.add_argument("--first", type=int, default=0)
    f.add_argument("--last", type=int, default=None)
    f.add_argument("--notify", default=None, help="amply session id to notify on finish or failure")
    a = ap.parse_args()
    if a.cmd == "live-status":
        meta = pty_host(a.conv)
        print("PTY host:", json.dumps(meta) if meta else "none (hub-hosted or stopped)")
        store = LiveStore(a.conv)
        steps = store.steps()
        print(f"live store: {len(steps)} steps, last write {time.ctime(store.mtime())}")
        print("last steps (idx, type):", [(i, t) for i, t, _ in steps[-6:]])
        return 0
    if a.cmd == "pty-send":
        text = pathlib.Path(a.text[1:]).read_text(encoding="utf-8") if a.text.startswith("@") else a.text
        try:
            print("OK:", PtySender(a.conv, a.poll_sec).send_and_confirm(text, interrupt=a.interrupt,
                                                                         timeout=a.timeout))
        except Exception as e:
            print(f"FAILED: {e}", file=sys.stderr)
            return 1
        return 0
    if a.cmd in ("send", "feed") and pty_host(a.conv) and not getattr(a, "force_hub", False):
        print(f"REFUSED: {a.conv} is hosted by a live gemini PTY daemon; the hub view may be stale. "
              "Use `pty-send` (or `send --force-hub`).", file=sys.stderr)
        return 2
    js = Jetski(a.address or hub_address(), a.model, a.poll_sec)

    if a.cmd == "find":
        hits = [l for l in js.listing(verbose=True) if a.pattern.lower() in l.lower()]
        for l in hits:
            print(l[:300])
        return 0 if hits else 1
    if a.cmd == "status":
        st = js.status(a.conv)
        print(st or "NOT FOUND")
        return 0 if st else 1
    if a.cmd == "send":
        text = pathlib.Path(a.text[1:]).read_text(encoding="utf-8") if a.text.startswith("@") else a.text
        try:
            after = js.send_and_confirm(a.conv, text, interrupt=a.interrupt, timeout=a.timeout)
        except Exception as e:
            print(f"FAILED: {e}", file=sys.stderr)
            return 1
        print(after[-1500:])
        print("OK: assistant replied")
        return 0
    msgs = [m.strip() for m in pathlib.Path(a.file).read_text(encoding="utf-8").split("===MSG===")]
    last = len(msgs) - 1 if a.last is None else a.last
    state = pathlib.Path(a.file).with_suffix(".next_idx")
    try:
        for idx in range(a.first, last + 1):
            js.send_and_confirm(a.conv, msgs[idx], interrupt=False, timeout=a.timeout)
            state.write_text(str(idx + 1))
            print(f"{time.strftime('%H:%M:%S')} message {idx} answered", flush=True)
    except Exception as e:
        notify(a.notify, f"[jetski_send feed] STOPPED at message {idx}: {e}")
        return 1
    notify(a.notify, f"[jetski_send feed] all messages {a.first}..{last} answered in {a.conv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
