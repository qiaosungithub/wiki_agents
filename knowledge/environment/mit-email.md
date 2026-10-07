# MIT Email Account And Services

Account and service configuration for this host. Procedures and authorization
requirements are in [harness/skills/mit-email/SKILL.md](../../harness/skills/mit-email/SKILL.md). Inspect live configuration
before relying on these facts.

## Chapter 1 — How The Account Is Wired

### Identity and credentials

**The mailbox is `sqa24@mit.edu`, and its OAuth access token never leaves process
memory.** `oama` manages the credentials: get a token with
`oama access sqa24@mit.edu`. Never print the token, put it in a command-line
argument, or write it to a temporary file, and never display credential files.

### Which service does what

**Write through Exchange Web Services (EWS) and read incoming mail through the
local `notmuch` index.** Inspect the live configuration and a real service
response before relying on this table.

| Job | Service |
|---|---|
| Send, save a draft, read an item back by ID | EWS at `https://outlook.office365.com/EWS/Exchange.asmx` |
| Search incoming mail | `mbsync mit-inbox` mirrors `INBOX` only, `notmuch new` indexes it, `notmuch` queries it. Nothing syncs on a schedule |
| Look at Drafts or Sent | Authenticated IMAP or EWS; the local index does not cover them |
| SMTP submission | None. MIT has disabled authenticated SMTP submission for this tenant |
