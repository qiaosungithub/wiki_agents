# ELT DiT: cached-latent switch + input prefetch + remat/_reldist fix (2026-09-11)

Task from operator: ELT trains with an ONLINE per-step SD-VAE encode; switch it to
read the already-cached ImageNet latents. Also (a) add end-of-pipeline batch
prefetch (fetch+H2D currently on the train thread), (b) the shared loop always
remats so backward recomputes the forward, and `_reldist` may run the backward
twice. Operator decisions: **no xflip** (drop the aug, cache has none anyway);
edit **ELT-sqa** on the latest branch (`main`) and push; delete `elt-resume-fix`
after preserving its one uncommitted hunk.

## Ground truth established

- Cache EXISTS + complete: `/cns/{is-d,nm-d,li-d,rs-d}/home/qiaos/elt_data/dit_latents_imagenet256_8ch/` (train, 1,281,167 ex, 313 shards, `_SUCCESS`) and `..._8ch_val/` (50,000 ex, 13 shards). array_record, one `tf.train.Example{latent bytes float32 C-order, latent_shape[3], label[1], index[1]}` per record. 8ch = `[:4]`posterior.mean (bit-exact to ELT online encode) + `[4:]`posterior.std. label = tfds_label+1 (same as `decode_imagenet`). VAE = `/cns/rs-d/home/gldm/sd/flax_v1-4_vae_asnumpy.npz`.
- Cache has NO xflip (num_examples == split size, one latent per image). Operator: drop xflip entirely.
- PROD recipe encode = `sample_posterior=True` + `apply_latent_scale=True` (SiT): `z = (mean + std*eps)*0.18215`, eps FRESH per step. So the consumer must RESAMPLE from cached mean+std each step, not read a fixed mean. `latent_scale=0.18215` (gldm/vae/sd_vae.py `_LATENT_SCALES['sd']`).
- Encoder AND decoder are FROZEN: 500k ckpt (`xid_282154744`) `_METADATA` tree is model-only (`opt_state/param_state/{params,ema,mu,nu}/model/...`), `decoder_opt_state` empty, tfevents only `train/model/*`,`train/total_loss`,`train/latents_l2`. So train step needs NO pixels. `compute_decoder_loss=False` at train (decoder params live in context, not in `params`).
- The ONLY pixel-dependent training quantity is `loss_denom = float(batch.image.size)` in `loss_terms_fn` (train_eval.py ~L281/L316). It divides the differentiated loss (`_finish_total` returns `total_loss/loss_denom`). Online = 512*256*256*3. Cached batch.image would be [B,32,32,8] → 24x smaller → MUST override to pixel count.
- FID reference stats are PIXEL space (eval/reference datasets). Only the TRAIN iterator switches to latents; `eval_dataset`, `sample_eval.cond_dataset`, `reference_datasets` STAY pixel `ImagenetSource`.

## Design (all behind a composable `_cache` mode token, default OFF)

1. `datasets/tfds.py`: new `LatentImagenetSource(split)` — reads array_record shards
   `dit_latents_imagenet256_8ch{,_val}/{train,validation}/shard-*.array_record` via
   tf.data ArrayRecordDataset; parse Example; `image`=latent[32,32,8] float32,
   `label`=int32, `mask`=True, `is_aug`=0. num_classes=1001. Root cell chosen by
   config (default is-d). Registered protocol key `latent_imagenet_src`.
2. `datasets/__init__.py`: the pixel normalize line `image = image/127.5-1` must be
   SKIPPED for latents. Add `Dataset.pixel_input: bool = True`; gate that line.
   (Prefetch also lives here — see below.)
3. `projects/latents/nn.py`: new `CachedLatentEncoder(DiffusionNetwork)`,
   `sample_posterior`/`apply_latent_scale` fields. `apply` reads `inputs.batch.image`
   [.,.,8], `mean=x[...,:4]`, `std=x[...,4:]`, `z=mean+std*normal(rng)` if
   sample_posterior else mean, `*0.18215` if apply_latent_scale, returns
   NetworkOutput(x_pred=z). Zero real params: `init`->`{'params':{}}`,
   `load_params`->`{}`. Registered key `cached_latent_encoder`. This keeps the exact
   `encode_fn(batch,params,rng).x_pred` interface, so loss_terms_fn is untouched
   except loss_denom.
4. `projects/latents/train_eval.py`:
   - `init_context`: treat CachedLatentEncoder like StableDiffusionEncoder (set
     `context.encoder_params = encoder.load_params()` = {}).
   - `dev_init_state`: change `if encoder_params is not None:` -> `if encoder_params:`
     so an empty encoder subtree is NOT added to the opt tree (keeps tree == online).
     Verify online path (encoder_params is None there) is unchanged.
   - `loss_terms_fn`: `loss_denom` = `latents_cfg.image_pixels_per_example *
     batch.image.shape[0]` when set (>0), else `batch.image.size` (unchanged).
5. `projects/latents/types.py` `LatentsConfig`: add `image_pixels_per_example:int=0`.
6. `configs/load_config.py get_config`: add composable `_cache` token. When present:
   build a latent train Dataset (source=LatentImagenetSource, preprocessing=[DropCond(0.1)]
   ONLY, pixel_input=False), set `experiment.train.train_dataset` to it, set
   `experiment.encoder` to CachedLatentEncoder(sample_posterior,apply_latent_scale
   copied from whatever the base/`_sit` set), set `latents.image_pixels_per_example
   =256*256*3`. Leave sample_eval.cond_dataset + reference_datasets pixel.
   DropCond stays online (cheap, label-only). No xflip.

## Prefetch (issue: fetch+H2D on train thread)
`datasets/__init__.py`: `jax_iter`/`preprocess_and_pack_tf_dataset` currently
`next(it)` synchronously then `make_batch` does `make_array_from_process_local_data`
(H2D) inline. Add a device-side double-buffer prefetch wrapper around the final
iterator so step N+1's fetch+transfer overlaps step N compute. Keep it optional
(config `train.prefetch_depth:int=2`, 0=off) and correctness-neutral.

## remat / _reldist (issue: always-on remat; double backward recompute)
- `nn/blocks.py` repeat path wraps `reuse_fn` in `core.lift.remat(...)` on ALL
  branches (detached scan, main scan, full-unroll persite). `nn/layers.py
  scan_over_layers` also remats with a save_only policy. Repo note (load_config.py
  2026-09-05) CREDITS a "20% win" to the remat policy — so do NOT assume off is
  better; make it a flag and MEASURE. Default = current behavior.
- `_reldist` (`two_cotangent_grads`): one `jax.vjp` build, two `vjp_fn` pulls
  ((1,0),(0,1)). Two backward passes are REQUIRED (student grad must be
  right-aligned before summing). But with blanket remat, each pull RECOMPUTES the
  forward → forward runs ~3x. Fix: on the persite/_reldist path, run the loop
  WITHOUT remat so the single vjp's stored activations are reused by both pulls
  (forward once). Gate via config `model.network...remat` or a latents flag.
- Add `TransformerBlock.remat: bool = True` (or a config-level toggle threaded to
  the block); when False, call `reuse_fn`/scan without `core.lift.remat`.

## Test / ship
- Local CPU smoke of the actual train path with `_cache` on (DEBUG arch): init ->
  a few steps -> checkpoint save+restore -> assert loss_denom matches pixel path.
  Use JAX_PLATFORMS=cpu. Negative control: assert cached loss_denom == online
  loss_denom for same batch; assert CachedLatentEncoder(sample) mean over many eps
  ~ mean*scale.
- blaze build //experimental/qiaos/elt_dit_pkg:main ; import check.
- Commit on ELT-sqa main, push. Preserve elt-resume-fix's configclasses idempotent
  hunk (backed up in artifacts/elt_backup/) into ELT-sqa, then the two trees match
  and elt-resume-fix can be deleted (operator asked).
