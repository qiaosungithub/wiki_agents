# GCP GPU VMs (viscam-cloud)

Interactive SSH to the Viscam GPU VMs on Google Cloud (project `viscam-cloud`,
a **separate Cloud org** from corp). These are GCE instances (e.g. an
A100-80GB box), reached over the corp SSH relay — not Borg, not a TPU slice.
`../jobs.md` owns cluster jobs; this file owns hand-run GPU boxes.

## Reaching A VM Is Two Independent Gates

**Connectivity and authorization fail separately; diagnose them apart.** A
`Permission denied (publickey)` with the TCP handshake visible means the relay
worked and only auth failed — do not chase the network.

| Gate | What it is | How to confirm |
|---|---|---|
| Network path | cloudtop/Mac cannot reach the VM's public IP on tcp:22 directly (egress blocked). Must traverse the **SUP relay** via `corp-ssh-helper`. | `corp-ssh-helper --proxy-mode=grue <ip> 22` returns rc=0; verbose ssh shows `Authenticating to <ip>:22`. |
| Authorization | The VM decides whether to accept the account/key. | The VM's serial console (`gcloud compute instances get-serial-port-output`) shows the real reason. |

IAP is **not** the path here: this project's firewall does not admit the IAP
range `35.235.240.0/20` on tcp:22, so `gcloud ... --tunnel-through-iap` fails
with "Connection closed". The SUP range `172.253.30.0/23` *is* allowed, so
`corp-ssh-helper` works. Ignore advice to "grant iap.tunnelResourceAccessor".

## Connecting

**Prefer `gcloud compute ssh` — it resolves the current IP and sets the proxy
for you.** The VM's public IP can change on restart; a hardcoded IP in
`~/.ssh/config` goes stale.

```bash
gcert   # daily; corp cert. On a box without LOAS: gcert -corpssh=true -loas2=false
gcloud compute ssh qiaos@deepflow-1a100-80gb-jh-baseline \
  --zone=us-east4-c --project=viscam-cloud
```

Raw ssh (when you need explicit control) goes through the relay:

```bash
ssh -i ~/.ssh/google_compute_engine \
  -o "ProxyCommand=/usr/bin/corp-ssh-helper --proxy-mode=grue %h %p" \
  qiaos@<current-ip>
```

**The login user depends on which key path the VM uses** (see next section):
metadata keys log in as `qiaos@`; OS Login logs in as `qiaos_google_com@`.
Using the wrong one is an instant `Permission denied`.

### From a personal/corp Mac
Same relay model; the Mac must be a corp machine with `corp-ssh-helper` and
`gcloud` (see `go/corp-ssh-helper`). Copy the private key over
(`scp qiaos@<cloudtop>:~/.ssh/google_compute_engine* ~/.ssh/` then
`chmod 600`), `gcert`, then use the `gcloud compute ssh` form above, or an
`~/.ssh/config` block whose `ProxyCommand` is `corp-ssh-helper` and whose
`User` is `qiaos`.

## OS Login vs Metadata Keys — The Trap That Cost A Day

**A GCE VM authorizes SSH by EITHER OS Login OR instance/project metadata
ssh-keys, and `enable-oslogin=TRUE` makes the two mutually exclusive: with OS
Login on, the VM ignores every metadata key.** Decide which path is live before
touching keys.

Symptoms and meaning, read from the **serial console**:

| Serial log line | Meaning | Fix |
|---|---|---|
| `OS Login user <u> does not have login permission` / `Could not grant access to organization user` | OS Login path is active and rejecting you. For an **external-org** user this is org-level OS Login, *not* the project IAM binding. | Confirm the corp SSH groups (below). If OS Login itself is broken, switch to metadata keys. |
| `oslogin_cache_refresh: Failure getting users, quitting` (every ~6h) | The VM's **OS Login guest agent cannot enumerate users** — usually the instance **service account scope is too narrow** (no `cloud-platform`). OS Login will reject *everyone*; a serial log where no user ever logs in via OS Login confirms it. | VM owner fixes the VM: set instance SA scope to `cloud-platform`, or disable OS Login and use metadata keys. Adding groups to the user cannot fix a VM-side failure. |

**The metadata-key workaround (fastest, needs the VM owner):**
1. Owner sets `enable-oslogin=FALSE` on the instance (else keys are ignored).
2. Owner adds **your** public key under your username. `add-metadata` with the
   `ssh-keys` key **REPLACES the whole instance-level list** — a naive add wipes
   any prior instance-level entry. Prefer adding at **project level** (or via
   the Console UI's Add-item) so one key reaches every VM and nobody is
   clobbered.
3. **Verify the key is actually yours**: the metadata line's comment and the
   base64 body must match your local `~/.ssh/google_compute_engine.pub`. A key
   filed under `qiaos:` whose comment is someone else's (`junhwahur@…`) is that
   person's key mislabelled — you have no matching private key and auth fails.

Note: per-user login is instance-level here; other users reach these VMs via
**project-level** metadata keys, so editing one instance's `enable-oslogin` or
its instance-level keys does not touch their access.

## Access Prerequisites (usually already true)

**"GCP SSH access" for an intern is several grants; verify each rather than
re-requesting the wrong one.** For an external-org user hitting `viscam-cloud`:

| Grant | Note | How to verify (read-only) |
|---|---|---|
| Corp SSH groups `gcp-approved-ssh-users-restricted.corp`, `ssh-domain-exception-users-restricted.corp` | Filed via GUTS intern-access ticket, host-approved. Membership persists (~90d). | Ganpati proposal page (owner can screenshot); the approval is org-level. |
| Project IAM `compute.instances.osLogin` | Comes with project editor via the project's users group. | `gcloud compute instances test-iam-permissions <vm> --zone=<z> --project=<p> --permissions=<perm>` **one perm per call** (see caveat). |
| SSH relay eligibility (`go/request-ssh`) | Sphinx; often already held. | `go/sshrelay-access`. |

**`gcloud ... test-iam-permissions` is unreliable when batched here.** Repeated
`--permissions=` flags collapse to only the **last** one (a CLI quirk), and the
REST call may 401 with `ACCESS_TOKEN_TYPE_UNSUPPORTED` under a restricted LOAS
cert. Query **one permission per invocation** and calibrate with a permission
you know you lack (e.g. `compute.instances.setIamPolicy` → empty) so a false
"HAS" is caught.

## Environment Gotchas

- **A restricted-LOAS shell (e.g. an agent worker) cannot self-serve Ganpati /
  aclcheck / F1.** They fail with `go/loas-restricted-credentials`. `aclcheck`
  also only covers **prod** groups, never `.corp` ones. To read a `.corp`
  membership you need a normal cert or the group owner. Don't burn turns
  retrying these from a restricted shell.
- **Ganpati / AccessNow web pages need SSO**; `curl` gets 302, `gbrowser --corp`
  gets ÜberProxy 403. Ask the owner for a screenshot instead of scraping.
