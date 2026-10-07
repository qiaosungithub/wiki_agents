# Trapezoid Schedule Follow-up Observations

Preserved research observations accompanying [looped_nanogpt_per_site.md](looped_nanogpt_per_site.md).
The original note did not state an absolute date.

Follow-up (same day, 70 Parcae arms incl. psm magma/skip):
- Spearman(core lr*wd, drop 6144->6399) = 0.954; within one lr*wd the drop agrees to ~0.005 ppl.
- Leader flips vs final from step 3072: same lr*wd 7/189, ratio<=1.5 87/536, ratio>1.5 635/1166.
  From 6144: 0/189, 1/536, 138/1166.
- Picking the winner early: at 5632 (lr 25%) the final winner ranks 14/70; at 6144 (lr 9%) 3/70, top-5 overlap 3/5.
- At equal nominal lr*wd, `skip` arms drop ~0.035 more in the last segment than `magma`/`wns`: per-site
  methods shift the effective timescale.
- Rule written into [looped_nanogpt_per_site.md](looped_nanogpt_per_site.md#reading-curves-under-the-trapezoid-schedule).
