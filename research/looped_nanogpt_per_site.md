# The idea page: per-site optimization for weight-shared models

**The research idea, its scope, and the looped-nanoGPT benchmark are defined by
the user in `hie1/` of the paper repo, and nowhere else.** These two files are
the idea page:

| File | Holds |
|---|---|
| `~/work/paper-with-agent/hie1/hie1-paper-scope.md` | The story and claims, the scope, the three loss designs, cost, the ablation message, the tuning protocol |
| `~/work/paper-with-agent/hie1/looped-nanogpt-details.md` | Benchmark architecture, loop weighting, step budget and TPP, the eval protocol |

hie1 is written by the user and is read-only for agents
(`../projects/paper_with_agent.md`). Do not copy its content into this wiki: the
user edits hie1 directly, so a copy drifts. If something in hie1 looks wrong or
unclear, tell the user.

## Where The Benchmark Code Lives

**The three loss designs are three branches of one repo,
`qiaosungithub/parcae-jax`, each checked out in its own directory.**

| Design | Branch | Checkout |
|---|---|---|
| parcae | `parcae` | `~/work/parcae-jax` |
| loopformer | `loopformer` | `~/work/loopformer`; its `origin` is the local `~/work/parcae-jax` clone, not GitHub |
| ouro | `ouro` | `~/work/ouro` |

hie1 states the intended design and the code states what actually runs. When
they disagree (norm design, input injection, prelude / coda, loop weighting),
report the difference to the user instead of silently following either one.
Results are logged per `result_logging.md` §Which Tab.
