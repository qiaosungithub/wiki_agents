---
name: agent-messaging
description: Send a message to another agent session (a Jetski conversation, or an amply run or session) from a shell, a script, or another agent, and confirm it was received and answered.
---

# Messaging Jetski And Amply Sessions

How to get a message into another agent's conversation and prove it landed. The
behavior of each interface (ports, formats, what a send does to a running turn)
is owned by
[knowledge/codebases/local-agent-cli.md §Chapter 3 — Messaging Interfaces](../../../knowledge/codebases/local-agent-cli.md#chapter-3--messaging-interfaces).
The Jetski helper is [`tools/jetski_send.py`](../../../tools/jetski_send.py).

## Pick The Channel

**Choose by where the message comes from and what it should look like to the
recipient.**

| From → to | Channel | Recipient sees |
|---|---|---|
| Any shell or script → a Jetski conversation | `tools/jetski_send.py send <conv> "<text>"` (the `jetski` CLI against the local hub underneath) | a user message that starts a turn |
| An agent in an amply run → another session in the same run | the `send_message` tool, with the target session id | a peer message |
| A process with `AMPLY_RUN_ID` set (any bash child of an amply agent) → a session in that run | `~/.amply/bin/amply_notify <session_id> "<text>"` | an environment message |
| Anything outside amply (Jetski, cron, a script) → an amply run's chatbot, as the operator | `curl -X POST "$(cat ~/.amply/dashboard_url)/chat/send?run_id=<run_id>" --data-urlencode "content=<text>"` | an operator message, folded into a running turn |

Make every relayed message self-contained: the recipient did not see your
context, so name the files, paths, and what you want done.

## Procedure: Message A Jetski Conversation

**Use `tools/jetski_send.py`; it passes `--model`, sends only while the
conversation is idle, and exits 0 only when an assistant reply follows your
message.**

1. Find the conversation id by its title:
   `~/miniforge3/bin/python3 ~/work/wiki_agents/tools/jetski_send.py find "<title substring>"`.
2. Send one message and wait for the answer:
   `jetski_send.py send <conv> "<text>"`, or `send <conv> @message.md` for a long one.
   Add `--interrupt` only when you mean to cancel the agent's current turn.
3. Send several, one per turn: put them in one file separated by lines reading
   `===MSG===`, then run it detached so it survives your session:
   `setsid nohup ~/miniforge3/bin/python3 ~/work/wiki_agents/tools/jetski_send.py feed <conv> msgs.md --notify <your amply session id> > feed.log 2>&1 < /dev/null &`.
   It stops and notifies on the first failed check; `msgs.next_idx` holds the
   resume index for `--first`.
4. Read the answer: `jetski get-conversation --address=localhost:<hub port> --conversation=<conv>`
   (`--include_tool_calls` shows tool steps).

Without the helper, the raw command is
`jetski send-message --address=localhost:<hub port> --conversation=<conv> --model="Gemini 4 Argon (High)" --prompt="<text>"`,
with `jetski` at `/google/bin/releases/gemini-agents-jetski/jetski`. Its stderr
is init log spam, so redirect it to a file. You then own the idle check and the
reply check yourself.

## Procedure: Message An Amply Session

**Pick the channel from the table above, then confirm arrival in the
recipient's stream, not from the exit code.**

- `send_message` (in-run peers): confirmation is the target acting on it or
  replying; peek its session if it matters.
- `amply_notify` (scripts): needs only `AMPLY_RUN_ID` in the environment and a
  live worker for that run. Exit codes: `0` delivered, `1` argv or
  `AMPLY_RUN_ID` missing, `2` worker unreachable, `3` session unknown or
  terminal (usually a wrong session id). Never call `$AMPLY_NOTIFY`; it points
  at a release binary this account cannot read.
- `/chat/send` (outside callers): a 2xx reply (it returns 204) only means the gateway accepted it.
  Confirm by reading `GET <dashboard_url>/chat/messages?run_id=<run_id>` until
  the chatbot's reply appears.

## Verify Before You Claim A Message Arrived

**A send is done only when the recipient's transcript shows it and, for a
request, an answer after it.** For Jetski that is a `planner_response` step after
your `user_input` step; for amply it is the text in the target's event stream or
`/chat/messages`. A poller that only waits must also be able to say "I cannot
read the status": the helper exits after 10 unreadable polls in a row instead
of waiting forever.

## Traps

**Each row cost a real delivery; the helper already guards against all of
them.**

| Symptom | Cause | Fix |
|---|---|---|
| The CLI prints "Message sent", then the conversation logs `failed to construct executor: plan model not specified` and drops to IDLE | The conversation was started by the `gemini` CLI helper, so the hub holds no model for it | Always pass `--model="Gemini 4 Argon (High)"`; it is harmless on conversations that do store a model |
| Your message cancels work the agent was doing | You sent while the conversation was RUNNING; a send preempts the in-flight turn and abandons its tool call | Send only after two consecutive IDLE polls |
| A feeder waits forever and never sends | Its status regex expected a comma after the status, which only the `--verbose` listing has | Match `Status: (CASCADE_RUN_STATUS_[A-Z_]+)`, and fail after N unreadable polls |
| A checker reports failure although the agent answered | It treated any `error_message` step as failure; Jetski logs a retried 429 or 400 that way and still finishes the turn | Judge by the assistant reply after the message |
| `jetski` against a `cli` process's own ports returns 404 or 400 | Those embedded ports need their own CSRF token | Talk to the hub on the port in the `jetski-hub-server` argv |
| A background notification never arrives | The script called `$AMPLY_NOTIFY` | Use `~/.amply/bin/amply_notify` |
