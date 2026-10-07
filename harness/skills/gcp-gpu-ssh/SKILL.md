---
name: gcp-gpu-ssh
description: SSH to a GCP GPU VM in `viscam-cloud`, fix `Permission denied` by telling OS Login from metadata keys, and create a new 4-card box with a hunt loop that holds no impossible targets.
---

# SSH To The GCP GPU VMs (viscam-cloud)

This skill relies on [knowledge/environment/gcp-gpu-vms.md](../../../knowledge/environment/gcp-gpu-vms.md)
for the two gates a connection passes, the boxes we own, how to read quota, and
the access grants. It owns connecting, the OS Login versus metadata-key fix,
creating a box, and the environment gotchas.

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

## OS Login vs Metadata Keys

**A GCE VM authorizes SSH by either OS Login or instance/project metadata
ssh-keys, and `enable-oslogin=TRUE` makes the two mutually exclusive.** With OS
Login on, the VM ignores every metadata key. Decide which path is live before
touching keys.

Symptoms and meaning, read from the **serial console**:

| Serial log line | Meaning | Fix |
|---|---|---|
| `OS Login user <u> does not have login permission` / `Could not grant access to organization user` | OS Login path is active and rejecting you. For an external-org user this is org-level OS Login, *not* the project IAM binding. | Confirm the corp SSH groups ([Access Prerequisites](../../../knowledge/environment/gcp-gpu-vms.md#access-prerequisites-usually-already-true)). If OS Login itself is broken, switch to metadata keys. |
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

## Creating A 4-Card Box

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

## Environment Gotchas

- **A restricted-LOAS shell (e.g. an agent worker) cannot self-serve Ganpati /
  aclcheck / F1.** They fail with `go/loas-restricted-credentials`, and
  `aclcheck` covers only prod groups, never `.corp` ones. Reading a `.corp`
  membership needs a normal cert or the group owner; do not retry from a
  restricted shell.
- Ganpati / AccessNow web pages need SSO. `curl` gets 302, `gbrowser --corp`
  gets ÜberProxy 403. Ask the owner for a screenshot instead of scraping.
