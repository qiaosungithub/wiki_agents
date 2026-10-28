# Research Knowledge

Owns the index of this branch's research pages: the research ideas and what
the experiments found. Running an experiment program cycle by cycle (the
research loop, durable run records, tracker evidence) is the experiment-loop
skill ([harness/skills/experiment-loop/SKILL.md](../../harness/skills/experiment-loop/SKILL.md)).
The paper written on the idea is [knowledge/codebases/paper-with-agent.md](../codebases/paper-with-agent.md).

| Read | When |
|---|---|
| [knowledge/research/looped_nanogpt_per_site.md](looped_nanogpt_per_site.md) | The looped-nanoGPT per-site optimizer idea page. Points at the user's `hie1/` files in `~/work/paper-with-agent`, which define the idea and the looped-nanoGPT benchmark, and lists where the parcae / loopformer / ouro code lives. |
| [knowledge/research/midtrain_loop_adaptation.md](midtrain_loop_adaptation.md) | The mid-training loop-adaptation idea page: retrofitting recurrence into a pretrained decoder (TinyLlama RR setting), the RR recipe end to end with its dirty points, why val loss and GSM8K/MATH disagree, the loop-depth distribution, and the ablation backlog. |
| [knowledge/research/looped_kv_literature.md](looped_kv_literature.md) | The screened literature for looping as per-token K/V or fast-weight refinement (last-K/V per-token recurrence, K/V sharing across loops, Jacobi vs Gauss-Seidel training): what kept papers establish, the kept and ignored lists, where the idea is still open. |
| [knowledge/research/next_connectionism.md](next_connectionism.md) | **The Next Connectionism** idea page ([the-next-connectionism-v2.html](../../../the-next-connectionism-v2.html)): the paradigm shift from scalar neurons and weight updates to capable agent units, persistent memory (`AGENTS.md`), and learned connection patterns, plus the next level of generalization (cross-domain organizational transfer). |

The other pages of the old `research/` directory are not research knowledge
and now live elsewhere:

| Read | When |
|---|---|
| [result-logging skill](../../harness/skills/result-logging/SKILL.md) | Writing a result into the shared experiment spreadsheet, or finding the chart for a job. Read it **every** time you log: headers and layout drift. |
| [knowledge/infrastructure/accelerator-choice.md](../infrastructure/accelerator-choice.md) | Choosing between v6p / v6e / v5p, or a preemptible slice keeps being lost: measured hold times, why a capacity table does not predict acquisition, and how to probe before committing. |
| [knowledge/infrastructure/v7-storage-placement.md](../infrastructure/v7-storage-placement.md) | Choosing a metro for a v7 run: the standing decision on which metros carry a full mirror, and how to regenerate the survey behind it. |
