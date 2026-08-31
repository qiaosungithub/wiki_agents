# GCP GPU VMs (viscam-cloud)

Interactive SSH to the Viscam GPU VMs on Google Cloud (project `viscam-cloud`,
a **separate Cloud org** from corp). These are GCE instances (e.g. an A100-80GB
box) reached over the corp SSH relay, not Borg and not a TPU slice. `../jobs.md`
owns cluster jobs; this file owns hand-run GPU boxes.

## Reaching A VM Is Two Independent Gates

**Connectivity and authorization fail separately; diagnose them apart.** A
`Permission denied (publickey)` with the TCP handshake visible means the relay
worked and only auth failed. Do not chase the network.

| Gate | What it is | How to confirm |
|---|---|---|
| Network path | cloudtop/Mac cannot reach the VM's public IP on tcp:22 directly (egress blocked); it must traverse the SUP relay via `corp-ssh-helper`. | `corp-ssh-helper --proxy-mode=grue <ip> 22` returns rc=0; verbose ssh shows `Authenticating to <ip>:22`. |
| Authorization | The VM decides whether to accept the account/key. | The VM's serial console (`gcloud compute instances get-serial-port-output`) shows the real reason. |

IAP is not the path here. This project's firewall does not admit the IAP range
`35.235.240.0/20` on tcp:22, so `gcloud ... --tunnel-through-iap` fails with
"Connection closed"; the SUP range `172.253.30.0/23` is allowed. Ignore advice
to "grant iap.tunnelResourceAccessor".

## Connecting

**Prefer `gcloud compute ssh`; it resolves the current IP and sets the proxy for
you.** The VM's public IP can change on restart, so a hardcoded IP in
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

The login user depends on which key path the VM uses (see next section):
metadata keys log in as `qiaos@`, OS Login as `qiaos_google_com@`. The wrong one
is an instant `Permission denied`.

### From a personal/corp Mac
Same relay model. The Mac must be a corp machine with `corp-ssh-helper` and
`gcloud` (see `go/corp-ssh-helper`). Copy the private key over
(`scp qiaos@<cloudtop>:~/.ssh/google_compute_engine* ~/.ssh/`, then
`chmod 600`), then run `gcert`. Use the `gcloud compute ssh` form above, or an
`~/.ssh/config` block whose `ProxyCommand` is `corp-ssh-helper` and whose `User`
is `qiaos`.

## OS Login vs Metadata Keys — The Trap That Cost A Day

**A GCE VM authorizes SSH by either OS Login or instance/project metadata
ssh-keys, and `enable-oslogin=TRUE` makes the two mutually exclusive.** With OS
Login on, the VM ignores every metadata key. Decide which path is live before
touching keys.

Symptoms and meaning, read from the **serial console**:

| Serial log line | Meaning | Fix |
|---|---|---|
| `OS Login user <u> does not have login permission` / `Could not grant access to organization user` | OS Login path is active and rejecting you. For an external-org user this is org-level OS Login, *not* the project IAM binding. | Confirm the corp SSH groups (below). If OS Login itself is broken, switch to metadata keys. |
| `oslogin_cache_refresh: Failure getting users, quitting` (every ~6h) | The VM's OS Login guest agent cannot enumerate users, usually because the instance service account scope is too narrow (no `cloud-platform`). OS Login then rejects everyone. | VM owner fixes the VM: set instance SA scope to `cloud-platform`, or disable OS Login and use metadata keys. Adding groups to the user cannot fix a VM-side failure. |

The metadata-key workaround (fastest, needs the VM owner):
1. Owner sets `enable-oslogin=FALSE` on the instance, else keys are ignored.
2. Owner adds your public key under your username. `add-metadata` with the
   `ssh-keys` key replaces the whole instance-level list, so a naive add wipes
   any prior instance-level entry. Prefer project level (or the Console UI's
   Add-item) so one key reaches every VM and nobody is clobbered.
3. **Verify the key is actually yours**: the metadata line's comment and the
   base64 body must match your local `~/.ssh/google_compute_engine.pub`. A key
   filed under `qiaos:` whose comment is someone else's (`junhwahur@…`) is their
   key mislabelled; you have no matching private key and auth fails.

Note: per-user login is instance-level here. Other users reach these VMs via
project-level metadata keys, so editing one instance's `enable-oslogin` or its
instance-level keys leaves their access alone.

## Our Own Boxes (we created them; we can delete them)

**Three boxes, all `enable-oslogin=FALSE` + metadata ssh-key, so the login user
is `qiaos@`, not the `qiaos_google_com@` the OS-Login boxes want. All DLVM
`pytorch-2-9-cu129-ubuntu-2404-nvidia-580` (driver preinstalled, torch
2.9.1+cu129, NV12 all-pairs NVLink), on-demand STANDARD, not preemptible.**

| Box | Shape | Cards | Zone | Disk |
|---|---|---|---|---|
| `qiaos-4a100` | `a2-highgpu-4g` | 4×A100-SXM4-**40GB** | us-central1-f | 1TB pd-ssd |
| `qiaos-4a100-2` | `a2-highgpu-4g` | 4×A100-SXM4-**40GB** | us-east1-b | 1TB pd-ssd |
| `qiaos-4a100-3` | `a2-ultragpu-4g` | 4×A100-SXM4-**80GB** | us-central1-a | 1TB pd-ssd |

```bash
gcloud compute ssh qiaos@qiaos-4a100   --zone=us-central1-f --project=viscam-cloud
gcloud compute ssh qiaos@qiaos-4a100-2 --zone=us-east1-b     --project=viscam-cloud
gcloud compute ssh qiaos@qiaos-4a100-3 --zone=us-central1-a  --project=viscam-cloud
```

Others' boxes we are lent time on live in the same project and are NOT ours to
delete — notably `deepflow-4a100-40gb-junhwahur-1` (us-central1-b, 4×A100-40GB).
List what actually exists rather than trusting any table, including this one:
`gcloud compute instances list --project=viscam-cloud --filter="status=RUNNING"`.

**Creating a 4-card box is a capacity fight, not a quota fight.** Free quota
tells you nothing. Every 4-card shape in us-central1 can be STOCKOUT at once:
H100 `a3-highgpu-4g`, A100-80GB `a2-ultragpu-4g`, A100-40GB `a2-highgpu-4g`.
Two traps:

- `Internal error` usually means STOCKOUT, not a bug; some zones return it
  instead of the honest `ZONE_RESOURCE_POOL_EXHAUSTED`.
- A created VM can be a phantom. It reaches STAGING, then GCE reclaims it and
  the insert operation ends up `STOCKOUT`. Poll until `RUNNING` before believing
  it; check `gcloud compute operations list --filter="targetLink~<name>"`.

So retry in a loop across zones and shapes, drop optional attachments (8 local
SSDs sharply cut the odds), and verify `RUNNING` before reporting success. H100
quota exists only in us-central1 and europe-west4. Everywhere else
`GPUS_PER_GPU_FAMILY` is 0 and no amount of retrying helps.

## A Hunt Loop Silently Full Of Impossible Targets

**A retry loop hides its own dead entries: every target fails every round
anyway, so a permanently-impossible one is indistinguishable from a
contended one.** One loop ran 253 rounds with 4 of its 15 targets unable to
succeed under any circumstances. Audit a target list against three
INDEPENDENT gates, because passing one says nothing about the others:

| Gate | How a target dies | Check |
|---|---|---|
| Shape exists in that zone | `a2-ultragpu-4g` is absent from us-east4-a/b, `a2-highgpu-4g` from us-east1-c | `gcloud compute machine-types list --zones=<z> --filter="name=<mt>"` |
| Matching per-family quota > 0 | us-east7 offers `a2-highgpu-4g` but holds A100-**80GB** quota only, so `NVIDIA_A100_GPUS=0` | quota metric for the exact family, not "A100" generally |
| Boot disk fits regional disk quota | 1000GB pd-ssd against a 500GB `SSD_TOTAL_GB` limit (us-east7) | shrink size; **pd-balanced counts against `SSD_TOTAL_GB` too**, so switching type is not a fix, shrinking is |

**Read the error text as the instrument that tells you which gate you are
at.** Changing one variable and watching the error CHANGE is the cheap probe:
at us-east7 the 1000GB request said `Quota 'SSD_TOTAL_GB' exceeded` and the
400GB one said `STOCKOUT` — proof the quota gate had been passed and only
capacity remained. Same trick in reverse at europe-west4: shrinking the disk to
100GB surfaced `GPUS_PER_GPU_FAMILY exceeded`, proving the disk was never the
blocker there and the real one was H100 quota held by someone else's VM.

**Restarting a hunter resets counters it should inherit.** Seed "how many boxes
do I already hold" and "which names are taken" from the on-disk won-list, or a
restart re-wins its full quota on top of what it already has and reuses a live
VM's name.

## Quota Readings Are Stale; Only An Insert Is Evidence

**Cloud Quotas API reported `NVIDIA_H100 used=0` in a region where 8 of 8 were
held by a running VM.** The `limit` is trustworthy, the `usage` is not. To learn
whether capacity is obtainable, attempt the insert — the error text is the only
reliable reading. Also note H100/H200/B200 have **no** per-card quota metric:
they are all governed by `GPUS-PER-GPU-FAMILY` keyed on `gpu_family`, and legacy
`gcloud compute regions describe` cannot see them at all; use
`gcloud alpha quotas info describe GPUS-PER-GPU-FAMILY-per-project-region
--service=compute.googleapis.com`.

## Access Prerequisites (usually already true)

**"GCP SSH access" for an intern is several grants; verify each rather than
re-requesting the wrong one.** For an external-org user hitting `viscam-cloud`:

| Grant | Note | How to verify (read-only) |
|---|---|---|
| Corp SSH groups `gcp-approved-ssh-users-restricted.corp`, `ssh-domain-exception-users-restricted.corp` | Filed via GUTS intern-access ticket, host-approved. Membership persists (~90d). | Ganpati proposal page (owner can screenshot); the approval is org-level. |
| Project IAM `compute.instances.osLogin` | Comes with project editor via the project's users group. | `gcloud compute instances test-iam-permissions <vm> --zone=<z> --project=<p> --permissions=<perm>` **one perm per call** (see caveat). |
| SSH relay eligibility (`go/request-ssh`) | Sphinx; often already held. | `go/sshrelay-access`. |

**`gcloud ... test-iam-permissions` is unreliable when batched here.** Repeated
`--permissions=` flags collapse to the last one (a CLI quirk). The REST call may
also 401 with `ACCESS_TOKEN_TYPE_UNSUPPORTED` under a restricted LOAS cert.
Query one permission per invocation, and calibrate with a permission you know
you lack (e.g. `compute.instances.setIamPolicy` → empty) so a false "HAS" is
caught.

## Environment Gotchas

- **A restricted-LOAS shell (e.g. an agent worker) cannot self-serve Ganpati /
  aclcheck / F1.** They fail with `go/loas-restricted-credentials`, and
  `aclcheck` covers only prod groups, never `.corp` ones. Reading a `.corp`
  membership needs a normal cert or the group owner; do not retry from a
  restricted shell.
- Ganpati / AccessNow web pages need SSO. `curl` gets 302, `gbrowser --corp`
  gets ÜberProxy 403. Ask the owner for a screenshot instead of scraping.
