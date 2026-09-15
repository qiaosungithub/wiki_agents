# MIT Email

Owns reading, searching, drafting, and sending mail from the MIT account on this
host. The general external-write rule is in `AGENTS.md` §Global Rules; this page
is its mail version.

Chapter 1 is how the account is wired; Chapter 2 is the read, draft, and send
procedures; Chapter 3 is the failures that look like a broken account.

---

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

---

## Chapter 2 — Reading, Drafting, And Sending

### Every mail write is a transaction

**Interpret `draft`, `save`, and `send` literally: saving a draft never grants
authority to send it.**

1. Establish the authenticated From identity and the exact recipients. Resolve an uncertain address from mailbox history or an authoritative directory; never guess.
2. Before creating anything, search the target folder for an equivalent item, so the write cannot duplicate one.
3. Make one minimal EWS write. XML-escape every user-derived field, or construct the SOAP body with an XML library.
4. Require HTTP success, EWS `ResponseClass="Success"`, and `ResponseCode="NoError"`. Capture the returned `ItemId` and `ChangeKey` in memory.
5. Read the item back by ID and verify the folder, From/To/Cc/Bcc, subject, and body. For a draft, also confirm that no matching item appeared in Sent.
6. If a request times out or the response is ambiguous, inspect Drafts and Sent before retrying. Never blindly repeat a mail write.

### Read or search mail

**Refresh the local index before claiming you searched current mail.** Run
`mbsync mit-inbox` and `notmuch new`, then query with `notmuch`, fetching only
the messages and fields the task needs. When Drafts or Sent matter, use
authenticated IMAP or EWS. Outlook localizes folder display names, so discover
server folders with IMAP `LIST` and select the ones carrying `\\Drafts` or
`\\Sent`.

### Save a draft

**Create a draft on the server with EWS `CreateItem`; a local Maildir draft
never reaches Outlook Drafts.** Use both of these settings:

```xml
<m:CreateItem MessageDisposition="SaveOnly">
  <m:SavedItemFolderId>
    <t:DistinguishedFolderId Id="drafts"/>
  </m:SavedItemFolderId>
  ...
</m:CreateItem>
```

Populate the message's `Subject`, `Body`, and recipient elements, and use no
send disposition anywhere in a draft request. Verify the saved fields with EWS
`GetItem` on the returned ID, then check Drafts and Sent as in the transaction.

### Send a message

**Send only when the user's current request explicitly authorizes sending.** Use
EWS `CreateItem` with `MessageDisposition="SendAndSaveCopy"` and
`SavedItemFolderId` set to the distinguished folder `sentitems`, then verify the
result in Sent. The saved sent copy is the normal audit record, so add a Bcc for
verification only when the user asked for one.

---

## Chapter 3 — Failures That Look Like A Broken Account

**None of these is a credential problem, so check this table before debugging
authentication.**

| Symptom | Cause | Do |
|---|---|---|
| `SmtpClientAuthentication is disabled` from `smtp.office365.com` | The tenant disabled SMTP submission | Do not retry SMTP; use EWS |
| A search misses mail you expect | Nothing syncs on a schedule | Run `mbsync mit-inbox` and `notmuch new`, then search again |
| A local Maildir draft never shows in Outlook Drafts | The `mbsync` channel mirrors only `INBOX` | Create the draft with EWS |
| No folder is named Drafts or Sent | Outlook localizes display names | Select by the `\\Drafts` or `\\Sent` flag from IMAP `LIST` |
| A write timed out or returned an ambiguous response | The item may exist anyway | Inspect Drafts and Sent before any retry |

The original local-agent memory is preserved verbatim at
`archive/legacy/mit_email_send_ews_memory.md` for provenance. This page is the
current source of truth.
