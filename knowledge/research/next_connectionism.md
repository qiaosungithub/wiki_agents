# The Idea Page: The Next Connectionism

Owns the high-level research paradigm of The Next Connectionism and its
cross-domain generalization thesis, distilled from
[the-next-connectionism-v2.html](../../../the-next-connectionism-v2.html).
Sibling pages are the research index [README.md](README.md), the looped-nanoGPT
optimizer idea [looped_nanogpt_per_site.md](looped_nanogpt_per_site.md), and the
project codebase page
[knowledge/codebases/next-connectionism.md](../codebases/next-connectionism.md).
Chapter 1 is the paradigm shift across initialization, training, and inference;
Chapter 2 is the next level of generalization across task domains.

---

## Chapter 1 — The Paradigm Shift

### Raising the basic unit from a scalar neuron to a strong agent

**Previous connectionism builds intelligence out of simple numerical units,
whereas next connectionism starts from already capable agents and trains them to
form an organization.** Each lifecycle stage of a classical neural network maps
one level up when the basic unit is a frontier LLM agent.

| Stage | Previous Connectionism | The Next Connectionism |
|---|---|---|
| Basic unit | Scalar numerical operation with no prior knowledge or method | Capable agent that can reason, act, use tools, and communicate |
| 01 / Initialization | Random scalar parameters waiting to learn features | Capable minds waiting to learn how to collaborate as a network |
| Supervision signal | Sample pairs $(x, y)$ and a differentiable loss function | Open-ended tasks and environmental feedback (counterexamples, missing evidence, test failures) |
| 02 / Training | Gradient descent updates numeric weights | Feedback updates each agent's persistent memory and inter-agent connection patterns |
| Learned state | A static tensor of parameter values | An organization: differentiated per-agent experience and history-shaped connections |
| 03 / Inference | Freeze weights; new inputs produce new activations | Freeze persistent memory and connections; new tasks trigger dynamic interaction |
| Generalization | Unseen samples from the same distribution | Transferring a learned collective working method to a new task domain |

### 01 / Initialization: initializing minds instead of parameters

**Initialization instantiates a population of capable agents rather than random
weights, shifting the learning problem from acquiring basic skills to forming a
network.** Agents can start identical or with minor role differences. Even with
the same base model, receiving different inputs, interacting with different
neighbors, and handling different subtasks leads agents to accumulate distinct
memories and roles.

### 02 / Training: updating persistent memory and connection patterns

**Training replaces gradient updates on weights with feedback-driven updates to
each agent's persistent memory and to the inter-agent connection topology.** On
tasks such as proposing mathematical conjectures, reviewing literature, or
building software libraries, agents collaborate, make mistakes, and observe
counterexamples or failing tests. Experience changes two things at once:
1. Each agent updates its own persistent context or memory document (such as
   `AGENTS.md`) with lessons learned, such as checking boundary cases first.
2. The network reshapes its connection pattern, deciding who consults whom, how
   information routes, and how labor is divided (such as assigning conjecture
   generation and counterexample search to separate nodes).

### Beyond Hopfield dynamics: autonomous learning rules

**Unlike classical Hopfield networks with human-prescribed storage and retrieval
rules, agents in next connectionism autonomously decide how feedback rewrites
memory, reshapes relationships, and alters how they learn.** Hopfield (1982,
1985) showed that local interactions can yield collective computation and
associative memory without global gradient descent. Here humans provide only the
environment and action interfaces, and the trained artifact is the resulting
organization of differentiated memories and connections.

### 03 / Inference: freezing the learned organization

**Inference freezes the learned organization checkpoint across tasks while
allowing full dynamic reasoning, tool use, and messaging within each test task.**
Just as fixed weights still produce new activations on each input, agents with
frozen persistent memory still exchange messages and adjust current plans inside
temporary working state. When a test task finishes, temporary state is wiped so
the next task starts from the same frozen organization checkpoint.

---

## Chapter 2 — The Next Level Of Generalization

### Cross-domain transfer of a collective working method

**Next connectionism targets generalization across task domains by transferring
a learned collective working method rather than in-distribution features.**
Classical neural networks test whether fixed weights handle unseen samples from
the same distribution. Because agent units already have general base skills,
what training adds is an organizational method: how to decompose problems,
verify assumptions, route evidence, divide labor, and reorganize after failure.

### 6-Train + 3-Held-Out-OOD-Eval benchmark suite for cross-domain generalization

**To evaluate cross-domain transfer without relying on encyclopedic knowledge
or GPU simulators, `next_connectionism/suite_env.py` pairs 6 diverse CPU-only
training benchmarks (3,201 tasks) with 3 held-out OOD evaluation benchmarks
(783 tasks).**
- **6 Training Benchmarks (3,201 tasks)**: `enterpriseops_gym` (649 SQLite+MCP
  enterprise workflow tasks), `appworld` (750 9-app REST tasks), `bbeh_mini`
  (460 multi-step reasoning tasks), `ifbench` (300 OOD constraint tasks),
  `spreadsheetbench` (400 verified Excel manipulation tasks), and
  `swebench_pro` (642 multi-language SWE-bench Pro V2 tasks).
- **3 Held-Out OOD Evaluation Benchmarks (783 tasks)**: `arc_agi_2` (120 2D grid
  induction tasks — Far Paradigm OOD), `terminal_bench_4` (63 CPU Linux/Ops
  terminal tasks — System Environment OOD), and `automationbench` (600 Zapier
  18-connector SaaS tasks — Cross-Toolset OOD).
