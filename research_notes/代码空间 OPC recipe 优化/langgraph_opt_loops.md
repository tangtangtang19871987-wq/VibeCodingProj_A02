# LangGraph as the outer optimizer over task artifacts (recipes / configs / code): catalog, patterns and pitfalls (as of 2026-11-07)

Method: GitHub repository and code search via `gh api search/*` (run 2026-11-07), READMEs and source files read from raw.githubusercontent.com, plus a few web searches. The `gh api repos/...` endpoint was blocked in this session, so star counts and dates come from the search API.
Verification labels: **V-code** = I read the source file(s). **V-snippet** = I read the README or docs only. **U** = search-result description only, not read.

## Q1. Which LangGraph-based optimization loops over task artifacts exist, and how mature are they?

### Takeaway
No mature, widely adopted (>100 stars) open-source project was found where LangGraph itself is the optimizer of a recipe or parameter set. The field is many small repos (0–20 stars, almost all from 2025–2026) plus two serious but tiny research codebases:
- **MADR**: hydrological-model calibration, with a paper.
- **Lifework-Health/auto-researcher**: LangGraph runs Optuna ask/tell and OpenEvolve step by step as graph nodes, with SQLite checkpoints and human approval.

The strong evolutionary code-search engines (OpenEvolve, about 7.7k stars; ShinkaEvolve, about 1.5k stars) are **not** LangGraph-based. They are plain Python asyncio loops. When they meet LangGraph, LangGraph sits *above* them as a control plane.

### Cited findings — catalog

| # | Name / URL | Dates (created/pushed) | Stars | Domain | What is optimized | Population/archive storage | Parallel eval | Numeric optimizer | Checkpoint / HITL | Verif. |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | [jovequli/MADR](https://github.com/jovequli/MADR) | 2026-06-02 / 2026-10-26 | 4 | Hydrology simulation calibration (VIC, SWAT+, CaMa-Flood, wflow) | Per-sub-basin model parameter sets | LangGraph state + **SQLite checkpointer** inside the run directory; round history and "search center" kept in state; `llm_calls.jsonl` provenance | Workers run sequentially in topological levels (Kahn's algorithm); multi-candidate rounds (3 candidates) in early rounds | None inside the graph. SCE-UA and NSGA-III are the *baselines* | `--resume` with the same `--output-root` and `--thread-id`; patience-based early stop plus a `max_rounds` hard cap | V-snippet |
| 2 | [Lifework-Health/auto-researcher](https://github.com/Lifework-Health/auto-researcher) | 2026-07-30 / 2026-08-28 | 0 | Scientific ML research (MRI segmentation, k-NN, synthetic) | Hyperparameters (Optuna) or **one declared mutable Python file** (OpenEvolve-style) | Typed `ResearchState`; Optuna study in **Optuna RDB storage (SQLite/PostgreSQL)**; OpenEvolve population "versioned" with lineage IDs; SQLite or Postgres coordination | "Parallel population evaluation is intentionally deferred" (sequential) | **Optuna ask/tell as separate graph nodes** (`optuna_ask_trial`, `optuna_tell_trial`, …); CMA-ES, GP and QMC extras; native OpenEvolve node also available | SQLite checkpoints, "each lifecycle boundary is a LangGraph checkpoint boundary"; `human_approval` node plus `interrupt_after`; budgets fail closed | **V-code** (builder.py, optuna backend) |
| 3 | [FabianKruger/molecule-optimization-agent](https://github.com/FabianKruger/molecule-optimization-agent) | 2025-12-01 / 2026-10-20 | 17 | Molecule design | SMILES string (single candidate) | `WorkflowState` (current SMILES, iteration count) | None (single-candidate loop) | None; pluggable oracle (`evaluate`, `build_feedback`, `is_done`) | `recursion_limit: 150` in config | **V-code** (builder.py) |
| 4 | [Rahul-8283/AURA](https://github.com/Rahul-8283/AURA) | 2026-07-21 / 2026-10-22 | 0 | Battery cathode materials | Material compositions (GA population of 20) | `current_population`, `best_candidates` (Hall of Fame, top 5) and `generation_history` **all in LangGraph TypedDict state** | Inside the node ("cached batched prediction"); Celery for knowledge tasks; `astream` to the UI | Hand-rolled GA (planner → mutator → predictor → loop) | Compiled **without checkpointer**; `recursion_limit = 2*generations + 10` | **V-code** (workflow.py, state.py) |
| 5 | [AlanoHater/Mind-Evolution-PoC](https://github.com/AlanoHater/Mind-Evolution-PoC) | 2026-02-23 | 0 | Scheduling / meeting planning | Plans (text solutions) | Islands with migration | Islands "evolve in parallel" (mechanism not read) | LLM crossover/mutation (Mind Evolution style) | ? | V-snippet |
| 6 | [FareedKhan-dev/qd-langchain-agents](https://github.com/FareedKhan-dev/qd-langchain-agents) (blog-style tutorial) | 2025-08-29 | 17 | Agent architecture search (legal-QA agents) | Genotype string compiled into a LangGraph `StateGraph` | **pyribs MOME archive** (MAP-Elites, multi-objective) *outside* LangGraph; LangGraph is the *artifact*, not the optimizer | Not read | pyribs emitters ("Graph Emitter for Architectural Mutation") | n/a | V-snippet |
| 7 | [michaelbarfoot/Mechanical_Agentic_Pipeline](https://github.com/michaelbarfoot/Mechanical_Agentic_Pipeline) | 2026-05-17 | 0 | Structural FEA (beam, gear), scikit-fem, gmsh | Geometry/design parameters | LangGraph state + "RAG over structured history" | None | Compared with scipy SLSQP: agent within 0.1% of scipy in 7 iterations | Not stated | V-snippet |
| 8 | [lablnet/HyperFlow](https://github.com/lablnet/HyperFlow) | 2026-04-09 / 2026-08-08 | 9 | Self-improving agents (inspired by Meta HyperAgents) | Agent code/prompts | **JSONL archive** (`archive.py`); parent selection from the archive | Not stated | MetaAgent acts as the LLM mutation operator | Not stated | V-snippet |
| 9 | [emanueleielo/open-fugu](https://github.com/emanueleielo/open-fugu) | 2026-06-30 | 4 | LLM routing coordinator | Weights of a tiny linear head (sep-CMA-ES) | sep-CMA-ES writes "a checkpoint per generation"; LangGraph is the *inference* graph | n/a | **sep-CMA-ES** training loop (outside the graph) | per-generation checkpoint files | V-snippet |
| 10 | [EstebanArenasG/BrewOptimizerAI](https://github.com/EstebanArenasG/BrewOptimizerAI) | 2026-09-17 / 2026-10-07 | 0 | Coffee **recipes** | Brew recipe parameters | SQLite (app) | n/a | **scikit-optimize GP BO** behind a FastAPI service; LangGraph + Ollama agent calls the API (BO marked "Pendiente", i.e. pending) | n/a | V-snippet |
| 11 | [Daniel-Humberto/NeuroEvolytics](https://github.com/Daniel-Humberto/NeuroEvolytics) | 2026-05-18 | 0 | LLMOps | LLM inference configs | ? (Airflow + LangGraph) | Airflow | GA | ? | U (README is 297 bytes) |
| 12 | [jovequli/MADR — SADR ablation](https://github.com/jovequli/MADR) | same | – | same | Deterministic rule-based worker in place of the LLM worker | same | same | step-decay + "three-tier escape protocol" | same | V-snippet |
| 13 | [Wendystar0628/Circuit-Design-AI-Assistant](https://github.com/Wendystar0628/Circuit-Design-AI-Assistant) | 2025-12-13 / 2026-09-06 | 3 | Analog circuits, SPICE | Netlist/parameters, "iterative optimization" | ? | ? | ? | ? | U (README not fetched) |
| 14 | [rahmanajumobi-ops/battery-parameter-agent](https://github.com/rahmanajumobi-ops/battery-parameter-agent) | 2026-09-21 | 0 | Battery parameters | Parameters via a surrogate model | 5-node LangGraph | – | Surrogate | – | V-snippet |
| 15 | [nousergon/crucible-backtester](https://github.com/nousergon/crucible-backtester) | 2026-03-09 / 2026-11-06 | 2 | Trading backtests | Strategy parameters via "sweep + VectorBT" | ? | ? | Sweep | ? | U |
| 16 | [dasein108/freqtrade_dev_mcp](https://github.com/dasein108/freqtrade_dev_mcp) | 2025-08-17 / 2026-09-22 | 10 | Trading | Freqtrade hyperopt exposed as tools, plus a LangGraph agent | ? | ? | Freqtrade hyperopt (Optuna-based) | ? | U |
| 17 | AutoML-with-Optuna repos, e.g. [RuthwikReddy09/AutoExperiment](https://github.com/RuthwikReddy09/AutoExperiment), [RapakaManoj99/agentic-ml-engineer](https://github.com/RapakaManoj99/agentic-ml-engineer), [StormDoragon/AutoForge](https://github.com/StormDoragon/AutoForge) | 2026 | 0–1 | ML hyperparameters | Model hyperparameters | Optuna typically called *inside one node* as a black box | – | Optuna study in a node | MLflow | U |
| 18 | [GenseeAI/cognify](https://github.com/GenseeAI/cognify) | 2024-11-26 / 2025-05-16 | 279 | Autotuning *of* LangChain/LangGraph/DSPy workflows | The workflow is the artifact (inverse direction) | – | – | Its own tuner | – | U |
| 19 | [liugangcode/deepevolve](https://github.com/liugangcode/deepevolve) | 2025-06-25 / 2025-10-11 | 146 | Scientific algorithm discovery | Code | OpenEvolve-style checkpoints `ckpt/checkpoint_{i}`, `best` | – | Evolution + deep research; acknowledges the Gemini LangGraph quick-start, so LangGraph is probably used only for the research sub-agent | `checkpoint_interval` | V-snippet (LangGraph role unclear) |
| 20 | [somedaybegreat/autonomous_researcher_human_orchestration](https://github.com/somedaybegreat/autonomous_researcher_human_orchestration) | 2026-08 | ? | Closed-loop experiments | ? | ? | ? | BoTorch + LHS closed-loop design doc (`docs/superpowers/specs/2026-08-10-botorch-lhs-closed-loop-design.md`) | ? | U (hit from code search) |
| 21 | [NVIDIA/GenerativeAIExamples — energy/simulation-workflow-agent](https://github.com/NVIDIA/GenerativeAIExamples/tree/main/industries/energy/simulation-workflow-agent) | ? | (large repo) | Energy simulation workflows | ? | ? | ? | pymoo mentioned in README | ? | U (code-search hit for "langgraph pymoo"; not read) |

Reference engines (not LangGraph):
- [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve): ★7728, created 2025-05-15, pushed 2026-11-05.
- [SakanaAI/ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve): ★1501, created 2025-09-17.
- Search for "langgraph openevolve", "langgraph alphaevolve" and "langgraph map-elites" returned **0 repositories** (gh search, 2026-11-07). The only OpenEvolve wrapped as a LangGraph node that I found is auto-researcher (`run_native_openevolve` node plus a step-wise OpenEvolve sub-loop) — [builder.py](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/src/auto_researcher/graph/builder.py).

### Cited findings — key details

**MADR (hydrology)**
- Leader Agent → Worker Agents structure, implemented in LangGraph. It "approaches the calibration accuracy of… SCE-UA, NSGA-III at less than 5% of their evaluation budget" — [MADR README](https://github.com/jovequli/MADR).
- Basin-average NSE: Gemini 0.744 and Claude 0.760 after 170 evaluations, against SCE-UA 0.764 and NSGA-III 0.772 after 4,000 evaluations. That is "about 23–36× less single-core wall-clock time at ~2.15 M tokens per run" — [MADR README](https://github.com/jovequli/MADR).
- The preprint is on Research Square, not arXiv, and may not be peer-reviewed — [Research Square rs-10106384](https://www.researchsquare.com/article/rs-10106384/v1).
- MADR versions: v0.1.0 (preprint), v0.2.0 (correctness fixes), v0.2.1 (round-budget semantics), v0.3.0 (wflow, provenance snapshot, tiered archiver that VACUUMs the checkpoint DB) — [MADR README](https://github.com/jovequli/MADR).
- An ablation (SADR) replaces the LLM Worker with a deterministic rule-based step executor. "Worker-level LLM reasoning consistently outperforms a deterministic rule-based executor" — [MADR README](https://github.com/jovequli/MADR).

**auto-researcher**
- "LangGraph owns the durable workflow… Direct, Optuna and OpenEvolve" search backends. It has "SQLite checkpoints and terminal replay" and "explicit approval, cost and experiment budgets, fail-closed readiness" — [auto-researcher README](https://github.com/Lifework-Health/auto-researcher).
- The Optuna backend is a "Replay-safe generic Optuna Study.ask/Study.tell backend". In its code, "LangGraph, not this class, owns the trial loop". It notes that "Optuna persists trials, not sampler RNG state", so it keeps one sampler-bearing Study object per study for the runtime. After a restart, it uses public `Study.tell(trial_number)` and never rebuilds Trial objects from private IDs — [optuna/backend.py](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/src/auto_researcher/search/optuna/backend.py).
- OpenEvolve in this graph: "OpenEvolve is a search backend inside the existing… graph. It is not a second execution engine… explicit graph nodes advance a versioned population."
- The lifecycle evaluates the immutable seed first. The baseline seed counts toward `maximum_candidate_evaluations`.
- "Model judgement is permitted only inside a configured mutation operator… The graph, identities, validation, budgets, eligibility, ranking, replacement, stopping, evaluation, and verification remain deterministic" — [OPENEVOLVE_SEARCH.md](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/docs/architecture/OPENEVOLVE_SEARCH.md).

**AURA**
- The whole GA population (20), the hall of fame and the per-generation history live in the LangGraph TypedDict state. The loop is `predictor → mutator` via a conditional edge, and `recursion_limit = 2*generations + 10` — [AURA workflow.py](https://raw.githubusercontent.com/Rahul-8283/AURA/main/backend/app/agents/workflow.py), [state.py](https://raw.githubusercontent.com/Rahul-8283/AURA/main/backend/app/agents/state.py).

**qd-langchain-agents**
- Uses LangChain plus pyribs MAP-Elites with a MOME archive. Each genotype string is compiled by `compile_genotype_to_graph` into a runnable `StateGraph`. The README advises using "a different model for evaluation than for generation" to reduce self-bias — [qd-langchain-agents README](https://github.com/FareedKhan-dev/qd-langchain-agents).

**Domain prior art for OPC**
- "Intelligent OPC Engineer Assistant" (AAAI 2025, arXiv 2408.12775) uses PPO on an OPC loss (EPE + PVB), then has an LLM distil a decision-tree recipe. Reported results: −11% EPE count and −19% EPE distance for the LLM recipe; −12% and −24% for the RL stage. It does not use LangGraph — [arXiv 2408.12775](https://arxiv.org/abs/2408.12775), [AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/34479).

### Inferences
- Maturity is low. The most rigorous LangGraph optimization loops (MADR, auto-researcher) have a paper or extensive docs but single-digit stars. Most other hits are one-commit portfolio projects.
- A recurring design split:
  - (a) **The LLM is the proposer** in a single-candidate refine loop (molecule-opt, mechanical, MADR workers).
  - (b) **A GA or Hall of Fame sits inside LangGraph state** (AURA, Mind-Evolution).
  - (c) **LangGraph is a durable control plane** that drives external numeric optimizers step by step (auto-researcher).

  Only (c) handles resume, budgets and replay rigorously.
- No public example was found that combines LangGraph with OPC or ILT recipes. An OPC/ILT optimizer in LangGraph would be novel.

### Gaps
- I did not find a LangGraph repo using the Send API to fan out population evaluation to a simulator in an optimization context. The code search `from langgraph.types import Send population` returned only general agent apps. The absence is not proven because GitHub code search is incomplete.
- BoTorch/Ax/nevergrad/DEAP/pymoo integrated *as LangGraph nodes*: searches returned only mentions (somedaybegreat BoTorch spec, NVIDIA pymoo README, Tidesign). These were not read, so the integrations are unverified.
- MADR graph code was not read: GitHub code search did not index it.

## Q2. How do these loops integrate numeric optimizers and parallel simulators? What are the engineering patterns and pitfalls?

### Takeaway
The only robust pattern observed has two parts:
1. Keep the optimizer's own state in its native durable store (Optuna RDB, a pyribs archive, OpenEvolve checkpoints, JSONL or SQLite). Do not keep it in the LangGraph channel state.
2. Expose **ask → evaluate → tell** as separate graph nodes, so every step boundary is a checkpoint.

Parallel simulator fan-out through Send is documented by LangGraph but was not observed in optimization repos. The careful projects either evaluate sequentially (auto-researcher defers parallelism explicitly) or batch inside a single node (AURA).

### Cited findings
**Optimizer integration**
- *auto-researcher*: seven separate Optuna nodes — prepare, ask, create_experiment, tell, record, decide, finalise — plus parallel OpenEvolve nodes (select_parent, propose, validate, prepare, record, decide, finalise) — [builder.py](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/src/auto_researcher/graph/builder.py).
- *auto-researcher* resume behaviour: "The graph resumes from its checkpoint. Study identity rejects changes to [config]". Untagged, foreign, duplicate-slot or multiple running trials are "not guessed" — [OPTUNA_SEARCH runbook](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/docs/runbooks/OPTUNA_SEARCH.md).
- *Pitfall — sampler RNG is not persisted* by Optuna. Recreating the Study on every node call resets the seeded sampler, so the backend caches one Study per runtime. On restart, the sampler stream necessarily differs — [backend.py](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/src/auto_researcher/search/optuna/backend.py).
- *Pitfall — idempotency on replay*: provenance event IDs are derived from semantic keys, so re-recording unchanged content is idempotent. "A changed scientific payload under the same semantic identity still fails closed" — [OPENEVOLVE_SEARCH.md](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/docs/architecture/OPENEVOLVE_SEARCH.md).
- *Pitfall — budget semantics*: the seed baseline counts toward the evaluation budget. A mutation-enabled budget of 1 "is rejected before graph… construction rather than being silently increased" — same source.
  - MADR also had to fix "round-budget semantics" in v0.2.1. The final "force-best" verification run is now explicitly *outside* the budget instead of "silently consuming the last optimization slot" — [MADR README](https://github.com/jovequli/MADR).
- *Pitfall — deterministic evaluator caching*: rounding the cache key to 100 nm resolution made SLSQP's finite-difference gradient look like zero, so a constraint was silently ignored. The fix was to use the exact float as the cache key — [Mechanical_Agentic_Pipeline README](https://github.com/michaelbarfoot/Mechanical_Agentic_Pipeline).

**Cost control and stopping**
- MADR combines `patience_rounds` (plateau stop) with a hard `max_rounds` cap and multi-candidate windows (`mc_rounds`). It reports about 2.15 M tokens per run for 170 simulator evaluations — [MADR README](https://github.com/jovequli/MADR).
- auto-researcher requires explicit provider, model, pricing, token and cost configuration, and "secret values never enter graph state" — [auto-researcher README](https://github.com/Lifework-Health/auto-researcher).

**recursion_limit**
- The limit counts supersteps, not loop iterations, and the default is 25 — [fast.io guide](https://fast.io/resources/langgraph-recursion-limit/), [LangChain reference: GraphRecursionError](https://reference.langchain.com/python/langgraph/errors/GraphRecursionError).
- Raising it to 1000 is a common "quick fix" that can mask non-termination — [fast.io](https://fast.io/resources/langgraph-recursion-limit/).
- The current step is readable at `config["metadata"]["langgraph_step"]` — [langchain-ai/docs PR 1166](https://github.com/langchain-ai/docs/pull/1166/files).
- Practice in the repos: AURA computes `2*generations+10` ([workflow.py](https://raw.githubusercontent.com/Rahul-8283/AURA/main/backend/app/agents/workflow.py)); molecule-opt uses a fixed 150 ([README](https://github.com/FabianKruger/molecule-optimization-agent)).

**Parallel fan-out**
- LangGraph documents Send as the mechanism for map-reduce fan-out to dynamic targets. Each Send launches a worker node or subgraph with its own state, and results are merged by a reducer such as `operator.add` — [LangGraph control-flow docs](https://docs.langchain.com/oss/python/langgraph/graph-api-control-flow.md).
- auto-researcher: "Parallel population evaluation is intentionally deferred" — [OPENEVOLVE_SEARCH.md](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/docs/architecture/OPENEVOLVE_SEARCH.md).

**State size**
- No source quantified checkpoint slowdown from large state; the search found nothing. AURA puts the full population and history into state with no checkpointer, so it avoids the write cost but cannot resume ([state.py](https://raw.githubusercontent.com/Rahul-8283/AURA/main/backend/app/agents/state.py)).
- MADR's archiver has to VACUUM the SQLite checkpoint DB after runs, which suggests checkpoint growth is a real operational issue — [MADR README](https://github.com/jovequli/MADR).

**Plain loop vs LangGraph vs OpenEvolve**
- OpenEvolve and ShinkaEvolve, the most adopted LLM-evolution engines (★7.7k and ★1.5k), are not LangGraph-based (gh search 2026-11-07: [openevolve](https://github.com/algorithmicsuperintelligence/openevolve), [ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve)).
- auto-researcher offers both a "native" OpenEvolve node (the engine runs its own loop inside one node) and a step-wise graph re-implementation — [builder.py](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/src/auto_researcher/graph/builder.py).

### Inferences
- **The LangGraph checkpoint is not a population database.** The checkpointer serializes channel state at every superstep. A population of N full recipes or simulation results, with history appended each generation, makes checkpoint writes grow with every generation (I found no benchmark of this). Keep only IDs, pointers and small summaries in state. Put candidates, scores and the archive in an external DB (SQLite/Postgres, Optuna RDB, or JSONL), keyed by a content hash of the recipe.
- **Make the evaluator cache key a canonical hash of the full recipe** plus simulator version, mask/layout clip ID and process-model version. Use exact values, not rounded ones (the SLSQP lesson). This gives replay-safety after resume and saves duplicate simulator runs when the LLM re-proposes a recipe it already tried.
- **Send fan-out for simulator jobs**: Send gives in-graph parallelism, but every worker's result passes through a reducer into state. For long, expensive, cluster-scheduled simulations (OPC/ILT runs of minutes to hours), the safer pattern is a node that submits a batch to a job queue (Slurm, Celery, Ray) and returns job IDs, followed by a polling node or an `interrupt` and resume. That keeps checkpoints small and survives process restarts.
- **Choosing the outer loop**:
  - Use **plain Python, OpenEvolve or Optuna** when the loop is pure numeric search or code evolution with no human gates.
  - Use **LangGraph** when you need durable multi-phase workflows, human approval, budget gates and audit trails around the search. In that case, follow auto-researcher: LangGraph orchestrates, the optimizer owns its state.

### Gaps
- No measured benchmarks for LangGraph checkpoint overhead against population size.
- No public evidence of Send fan-out to more than 100 parallel simulator jobs in an optimization loop.
- No repo found using `interrupt()` for engineer review *between generations* of an optimization loop, other than auto-researcher's approval gate before search.

## Q3. What architecture is recommended for an OPC/ILT recipe optimizer in LangGraph?

### Takeaway
Use the auto-researcher pattern, adding MADR-style LLM diagnostic proposals: a LangGraph control plane with explicit propose/ask → submit-simulation → collect → score → tell/record → decide nodes. The rules:
- Optimizer state lives in Optuna, Ax or BoTorch storage, or in a MAP-Elites/OpenEvolve archive, never in graph state.
- Simulations are submitted as batch jobs, with a content-hash cache.
- Human approval comes through `interrupt` at phase boundaries.
- The budget has a hard cap plus a patience stop.
- An LLM proposer and a numeric BO/CMA-ES proposer are mixed. MADR's evidence: LLM diagnostic proposals reach near-NSGA-III quality at under 5% of the evaluations.

This is my own synthesis. No OPC-specific LangGraph implementation exists to cite.

### Cited findings (design evidence)
- An LLM proposer guided by structured diagnostics (per-station errors → per-basin guidance) is sample-efficient with expensive simulators: 170 evaluations against 4,000 — [MADR](https://github.com/jovequli/MADR).
- MADR's parameter locking and topological processing keep coupled sub-problems consistent. This is analogous to coupled OPC recipe stages or neighbouring layout clips — [MADR](https://github.com/jovequli/MADR).
- Optuna ask/tell as graph nodes gives replay-safe, resumable search, provided you account for the unpersisted RNG and restart semantics — [auto-researcher backend.py](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/src/auto_researcher/search/optuna/backend.py).
- Restrict the LLM to the mutation operator and keep ranking, stopping and evaluation deterministic. Evaluate the immutable seed (the current production recipe) first, as the baseline — [OPENEVOLVE_SEARCH.md](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/docs/architecture/OPENEVOLVE_SEARCH.md).
- OPC losses used in the literature: Euclidean distance, EPE, PVB. A plain RL search improved EPE count by 12%, and an LLM-distilled recipe kept most of the gain (11%) — [arXiv 2408.12775](https://arxiv.org/abs/2408.12775).
- Quality-diversity archives (pyribs MAP-Elites/MOME) can hold diverse elites across behaviour descriptors outside LangGraph — [qd-langchain-agents](https://github.com/FareedKhan-dev/qd-langchain-agents).

### Inferences (proposed architecture, my synthesis)
1. **State**: `run_id`, `phase`, `generation`, `budget_used`, `best_ref`, and lists of `candidate_ids` and `job_ids`. Recipes and metrics go in an external SQLite/Postgres table keyed by `sha256(canonical_recipe_json + sim_version + clip_set_id)`. Use a Postgres or SQLite checkpointer with one `thread_id` per run.
2. **Nodes**:
   - `init`: load the production recipe as the seed and evaluate it as the baseline.
   - `diagnose`: an LLM summarises the EPE/PVB hotspots by pattern class.
   - `propose`: either an LLM-structured recipe delta (with a validated schema) or `optuna.ask` / Ax / BoTorch q-batch / CMA-ES.
   - `validate`: schema, physical bounds and recipe-DSL lint.
   - `cache_lookup`.
   - `submit_batch`: write recipes, submit to the OPC/ILT engine on the cluster, return job IDs.
   - `collect`: poll, or `interrupt` until callbacks arrive.
   - `score`: deterministic multi-objective metrics — EPE, PVB, MRC violations, runtime.
   - `tell/record`: update the optimizer storage and the archive.
   - `decide`: patience, max evaluations, cost cap, Pareto improvement.
   - `human_gate`: `interrupt` before promoting a recipe or moving to a full-chip phase.
3. **Parallelism**: in-node batch submission to the job scheduler is preferred over Send for long simulations. Use Send or subgraphs only for short per-clip scoring or LLM diagnosis per pattern class, with reducers that append *IDs*, not payloads.
4. **Limits**: set `recursion_limit` from the budget formula, e.g. nodes_per_generation × max_generations + margin, as AURA does. Rely on `decide` for termination.
5. **Outer-loop choice**: if all you need is a numeric search over continuous recipe knobs, run Optuna or BoTorch in a plain loop or as a single node. Choose LangGraph when you need multi-phase workflows, HITL, audit or mixed LLM and numeric proposers. If recipes are *code* (heuristic scripts), call OpenEvolve or ShinkaEvolve as a single node rather than re-implementing it.

### Gaps
- No public OPC/ILT recipe optimizer built on LangGraph, and no benchmark of LLM proposers against BO on lithography simulators, was found.
- Unknown: how commercial OPC tools (Calibre, Tachyon, Proteus) expose batch APIs for an agent loop. Not researched here.
