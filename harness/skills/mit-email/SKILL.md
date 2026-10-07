---
name: mit-email
description: Read, search, draft, or send MIT account email; sending requires the user to explicitly authorize sending.
---

# MIT Email Workflow

Read [knowledge/environment/mit-email.md](../../../knowledge/environment/mit-email.md) for identity, credentials, and service
configuration. General external-write rules are in [harness/policy.md](../../policy.md).

## Chapter 1 — Reading, Drafting, And Sending

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

## Chapter 2 — Failures That Look Like A Broken Account

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
[archive/legacy/mit_email_send_ews_memory.md](../../../archive/legacy/mit_email_send_ews_memory.md) for provenance. This page is the
current source of truth.
