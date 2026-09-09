# MIT Email

Use this guide when the user asks to read, search, draft, or send mail from the
MIT account configured on this host.

## Live Setup

- The configured mailbox is `sqa24@mit.edu`.
- OAuth credentials are managed by `oama`; obtain an access token with
  `oama access sqa24@mit.edu`. Keep the token in process memory and never print
  it, put it in a command-line argument, or write it to a temporary file.
- The working service endpoint is Exchange Web Services (EWS):
  `https://outlook.office365.com/EWS/Exchange.asmx`.
- MIT has disabled authenticated SMTP submission for this tenant. Do not retry
  `smtp.office365.com` after the known `SmtpClientAuthentication is disabled`
  failure; use EWS.
- Incoming mail is mirrored with `mbsync mit-inbox`, then indexed with
  `notmuch new`. There is no scheduled sync, so refresh before claiming to have
  searched current mail.
- The current `mbsync` channel mirrors only `INBOX`. A local Maildir draft will
  not reach Outlook Drafts; create server-side drafts with EWS.

Inspect the live configuration and service response before relying on these
facts. Do not display credential files or token contents.

## Transaction Rules

1. Interpret `draft`, `save`, and `send` literally. Saving a draft never grants
   authority to send it.
2. Establish the authenticated From identity and the exact recipients. Use
   mailbox history or an authoritative directory to resolve uncertain
   addresses; do not guess.
3. Before creating anything, search the target folder for an equivalent item
   to avoid duplicates.
4. Make one minimal EWS write. XML-escape all user-derived fields or construct
   the SOAP body with an XML library.
5. Require HTTP success, EWS `ResponseClass="Success"`, and
   `ResponseCode="NoError"`. Capture the returned `ItemId` and `ChangeKey` in
   memory.
6. Read the item back by ID and verify the intended folder, From/To/Cc/Bcc,
   subject, and body. For a draft, also confirm that no matching item appeared
   in Sent.
7. If a request times out or the response is ambiguous, inspect Drafts/Sent
   before retrying. Never blindly repeat a mail write.

## Read or Search Mail

Run `mbsync mit-inbox` and `notmuch new`, then query the local index with
`notmuch`. Fetch only the messages and fields needed for the task. The local
index does not cover Drafts or Sent; use authenticated IMAP or EWS when those
folders matter.

Outlook localizes folder display names. Discover server folders with IMAP
`LIST` and select the folders carrying `\\Drafts` or `\\Sent`; do not assume
their visible names are English.

## Save a Draft

Use EWS SOAP `CreateItem` with both of these settings:

```xml
<m:CreateItem MessageDisposition="SaveOnly">
  <m:SavedItemFolderId>
    <t:DistinguishedFolderId Id="drafts"/>
  </m:SavedItemFolderId>
  ...
</m:CreateItem>
```

Populate the message's `Subject`, `Body`, and recipient elements. Do not use a
send disposition anywhere in a draft request. After creation, use EWS
`GetItem` with the returned ID to verify the saved fields, then check Drafts
and Sent as described above.

## Send a Message

Send only when the user's current request explicitly authorizes sending. Use
EWS SOAP `CreateItem` with `MessageDisposition="SendAndSaveCopy"` and
`SavedItemFolderId` set to the distinguished folder `sentitems`. Verify the
result in Sent. Do not add a Bcc recipient merely for verification unless the
user requested it; the saved sent copy is the normal audit record.

The original local-agent memory is preserved verbatim at
`archive/legacy/mit_email_send_ews_memory.md` for provenance. This guide is the
current source of truth.
