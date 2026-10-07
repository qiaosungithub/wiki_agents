# GCP GPU VMs (viscam-cloud)

Interactive SSH to the Viscam GPU VMs on Google Cloud (project `viscam-cloud`,
a **separate Cloud org** from corp). These are GCE instances (e.g. an A100-80GB
box) reached over the corp SSH relay, not Borg and not a TPU slice. [The jobs pages](../infrastructure/cluster-jobs.md)
own cluster jobs; this page owns the facts about hand-run GPU boxes.
Connecting, fixing `Permission denied`, and creating a box are the
[gcp-gpu-ssh skill](../../harness/skills/gcp-gpu-ssh/SKILL.md); Borg GPU jobs are
[gpu-on-borg.md](../infrastructure/gpu-on-borg.md).

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

## Our Own Boxes (we can delete these)

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

Creating a new box is [§Creating A 4-Card Box](../../harness/skills/gcp-gpu-ssh/SKILL.md#creating-a-4-card-box) in the skill.

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
