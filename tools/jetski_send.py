#!/usr/bin/env python3
"""Send messages to a Jetski conversation safely, and confirm the agent replied.

Owning guide: harness/skills/agent-messaging/SKILL.md

  jetski_send.py find <title-substring>            list matching conversations + status
  jetski_send.py status <conv>                     print the conversation's run status
  jetski_send.py send <conv> <text | @file>        wait for IDLE, send, wait for the reply
  jetski_send.py feed <conv> <file> [--first N] [--last M] [--notify SESSION]
                                                   send messages split on '===MSG===' one per turn

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
Read-only commands: find, status. Exit code is non-zero on any failed check.
"""
import argparse
import os
import pathlib
import re
import subprocess
import sys
import time

JETSKI = os.environ.get("JETSKI_BIN", "/google/bin/releases/gemini-agents-jetski/jetski")
DEFAULT_MODEL = "Gemini 4 Argon (High)"
NOTIFY = os.path.expanduser("~/.amply/bin/amply_notify")
STATUS_RE = re.compile(r"Status: (CASCADE_RUN_STATUS_[A-Z_]+)")
IDLE = "CASCADE_RUN_STATUS_IDLE"
MAX_UNPARSED = 10


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
    f = sub.add_parser("feed")
    f.add_argument("conv")
    f.add_argument("file")
    f.add_argument("--first", type=int, default=0)
    f.add_argument("--last", type=int, default=None)
    f.add_argument("--notify", default=None, help="amply session id to notify on finish or failure")
    a = ap.parse_args()
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
