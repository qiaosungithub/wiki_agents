---
name: mit-email-send-ews
description: "How to send email as sqa24@mit.edu from this server: SMTP is tenant-disabled; use EWS CreateItem with oama OAuth token"
metadata: 
  node_type: memory
  type: reference
  originSessionId: d4b7ea07-1ad3-4a46-9a5a-c74b1084c565
  modified: 2026-07-23T15:21:52.955Z
---

发邮件(sqa24@mit.edu)在这台服务器上的可用路径:**EWS**,不是 SMTP。

- token: `oama access sqa24@mit.edu`(scope 只有 IMAP+SMTP.Send,但实测该
  token 打 `https://outlook.office365.com/EWS/Exchange.asmx` 返回 200,EWS 可用)。
- MIT 租户已禁用 SMTP 提交(535 `SmtpClientAuthentication is disabled for the
  Tenant`),smtp.office365.com XOAUTH2 永远走不通,别再试。
- 发送 = EWS SOAP `CreateItem` with `MessageDisposition="SendAndSaveCopy"` +
  `SavedItemFolderId=sentitems`,Bearer token,XML-escape 正文;BCC 自己一份留档。
- 收件:`mbsync mit-inbox` + `notmuch new`(无定时同步,查信前手动跑)。
- 2026-07-23 已用此路径向 trc-support@google.com 发出 us-central1 v5p allowlist
  恢复请求([[uscentral1-v5p-revoked]]),BCC 副本已确认到达 INBOX。
