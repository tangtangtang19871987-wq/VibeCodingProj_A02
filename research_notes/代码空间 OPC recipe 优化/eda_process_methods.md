# LLM-in-the-loop optimization of EDA / semiconductor-process / industrial recipes as code or text (non-litho), to 2026-11

Research date: 2026-11-07. Access notes: arxiv.org and alphaxiv.org could not be reached from this session (DNS blocked), so paper content comes from search-engine snippets plus the **project READMEs on raw.githubusercontent.com**, which I read directly. Verification levels used below:
- **[V-repo]**: read in the official/companion GitHub README during this session.
- **[V-snip]**: abstract or snippet seen through web search. The full paper was not read.
- **[K]**: background knowledge of a well-known paper, not re-fetched this session. The writer should spot-check these.

---

## Q1. Where has LLM-driven search over recipe/config code beaten BO/GA, by how much, and at what evaluation budget?

### Takeaway
There is real evidence that LLM search wins in the **low-budget / cold-start regime** (about 10 to 300 expensive evaluations): EDA flow tuning (ORFS-agent, StateTune), TCAD device tuning (czf-mq/agentic-tcad), and categorical chemistry reaction search (Iron Mind study). The margins are usually small to moderate (about 1 to 13% QoR, or about 2x fewer evaluations to reach the first feasible point). Most results are self-reported preprints that use few seeds. The strongest "beats classical" results come from methods that **evolve the source code of heuristics** (GR-Evolve, the coding-agent OpenROAD work, GoalEvolve, self-evolved ABC). These are compared against the hand-written tool, not against BO, because BO cannot search code.

### Cited Findings — EDA flow / tool parameter tuning (artifact = ORFS `config.mk` / Tcl variables / tool options)

- **ORFS-agent** (ABKGroup / UCSD Kahng lab; arXiv 2506.08332, Jun 2025, v2 later). An LLM agent tunes OpenROAD-flow-scripts parameters on ASAP7 and Sky130HD with the designs AES, IBEX and JPEG. The objectives are effective clock period (ECP), wirelength (WL) or a weighted combination. The search snippet reports gains over OR-AutoTuner of about 1.0% WL, 1.3% ECP and 2.7% on co-optimization, with 40% fewer iterations, and says open-weight models came within 0.24% of the best closed model — [arXiv 2506.08332](https://arxiv.org/pdf/2506.08332) [V-snip]. The README instead claims "improvements in wirelength and effective clock period by over 13% while using 40% fewer optimization iterations compared to baseline Bayesian optimization approaches" — [ABKGroup/ORFS-Agent README](https://github.com/ABKGroup/ORFS-Agent) [V-repo]. **These two figures conflict (about 1 to 3% vs >13%).** One possible reason is that one figure is measured against default ORFS and the other against AutoTuner. This was not resolved.
  - Artifact: ORFS `config_{INT_PARAM}.mk` plus `opt_config.json` constraints (for example `CORE_UTIL` int [20,99] and `PIN_LAYER_ADJUST` float [0.2,0.7]).
  - Search: hybrid. The LLM (Anthropic / OpenAI APIs) proposes and uses tools, including `modelfuncs.py` "Gaussian Process modeling, kernel selection" and scikit-optimize BO. In effect the LLM calls a GP/BO surrogate as a tool.
  - Framework: custom Python plus shell drivers. No LangGraph.
  - Budget (default): `TOTAL_ITERS=6` serial iterations × `PARALLEL_RUNS=50`, a 45-minute timeout per run, on 110 vCPU / 220 GB — [README](https://github.com/ABKGroup/ORFS-Agent) [V-repo]. That is about 300 flow runs in total.
  - Open source: yes.
- **StateTune** ("Transforming LLM-Assisted EDA Flow Tuning into a Stateful, Closed-Loop Process"; arXiv 2608.23601, Aug 2026). On a Cadence Genus/Innovus industrial flow over 6 blocks (ASAP7 and NanGate45 × AES, JPEG, IBEX), it attains "the best final hypervolume on all six blocks, the best WNS and best power on all six, and best-or-tied-best area on all six" against **BO-qEHVI, Optuna-TPE, Random, RankTuner (ICCAD'24) and CROP (ICCAD'25)** — [C-YuLong/stateTune README](https://github.com/C-YuLong/stateTune) [V-repo]. A hypervolume margin vs BO was not available.
  - Search: an LLM "Knowledge Agent" with typed persistent memory (prior, rules, failures, sensitivities, history, Pareto set, runtime) and five modes (explore, exploit, diversify, repair, promote). Promotion is by **EHVI(x)/runtime-UCB** from a multi-fidelity GP (BoTorch qLogEHVI, SingleTaskMultiFidelityGP) plus a kNN runtime model. The quick stage stops at CTS and only promoted candidates get the full route. It uses two models: Qwen3-235B-thinking for reasoning and DeepSeek-V3.2 for generation.
  - Ablations: removing evidence gating costs 43.4% hypervolume, and removing RAG (the RAG-EDA corpus) costs 46.1% — [README](https://github.com/C-YuLong/stateTune) [V-repo].
  - Budget: 192 thread·h per block (4 threads × 48 h), and about 6.0M LLM tokens for the 6-block suite. Search space: 19 Innovus options. Framework: custom Python (pydantic, BoTorch). No LangGraph.
  - Third-party **OpenROAD port** (XH2567/statetune-openroad, 2026-10-26): the full loop ran on ORFS with 12 ORFS variables (`ABC_AREA`, `CORE_UTILIZATION`, `PLACE_DENSITY_LB_ADDON`, `CTS_CLUSTER_*`, `ROUTING_LAYER_ADJUSTMENT`, and others) using DeepSeek-flash. WNS, area and power beat the ORFS defaults on all 6 cases, but the author warns the absolute numbers are not comparable to the paper. The port also found upstream bugs: qLogEHVI was being treated as raw EHVI, so after the front stabilised no candidates were promoted any more, and an ns-vs-ps unit check misjudged 3 of 7 ASAP7-IBEX runs — [statetune-openroad docs/OPENROAD_PORT.md](https://github.com/XH2567/statetune-openroad) [V-repo].
- **EDA Pilot AI** (NileshModlier/EDA-Pilot-Agentic-AI, GitHub, about 2026-10-30; an individual project, not a paper). It searches ORFS settings for the smallest clock that still signs off on Sky130HD `gcd`, `aes` and `ibex` with a budget of 10 runs. Best passing clocks were 2.867 / 4.822 / 9.000 ns vs random search at 4.113 / 6.261 / 10.531 ns, which is 14.5 to 30.3% tighter. Default ORFS signed off 0 of 3 designs. The cost was 7 to 23% more area, 30 to 71% more power and 1.5 to 5.5× runtime. Total: 52 scored ORFS runs, about 21 h — [README](https://github.com/NileshModlier/EDA-Pilot-Agentic-AI) [V-repo].
  - **Critical caveat:** "The benchmarked agent ran in offline-advisor mode … No chat model made decisions in this study … An LLM advisor has not been benchmarked yet." The "agent" was a deterministic clock bisection. The OpenROAD AutoTuner baseline produced no scored trials (Ray could not import HyperOpt) — [BENCHMARK_RESULTS.md](https://github.com/NileshModlier/EDA-Pilot-Agentic-AI/blob/main/BENCHMARK_RESULTS.md) [V-repo]. It is therefore **not evidence that LLMs beat BO**.
- **ResizerAgent** (UCSD VLSI CAD pub. c428). An LLM acts as a closed-loop controller around OpenROAD's Resizer for timing repair. It reports better WNS/TNS than both the default flow and AutoTuner at roughly the same compute — [UCSD c428 PDF](https://vlsicad.ucsd.edu/Publications/Conferences/428/c428.pdf) [V-snip].
- **OpenROAD AutoTuner** is the classical baseline: open source, no human in the loop, using Ray Tune search algorithms (hyperopt/TPE, Ax, Optuna, PBT and others) — [METRICS2.1 & flow tuning, UCSD c388](https://vlsicad.ucsd.edu/Publications/Conferences/388/c388.pdf) [V-snip].
- **ChatEDA** (wuhy68/ChatEDA, TCAD'24 / NAACL'25). An LLM agent (AutoMage) that writes EDA-flow scripts for OpenROAD tasks. It is task automation rather than a QoR-vs-BO optimization study — [GitHub](https://github.com/wuhy68/ChatEDA) [V-repo listing; details K].

### Cited Findings — heuristic / tool source-code evolution (artifact = C++/Python source)
- **GR-Evolve** (Taizun Jafri and Vidya A. Chhabria, ASU VDA Lab; arXiv 2604.22234, 2026-04-24). An LLM coding CLI (Codex) evolves global-router source code (FastRoute, CUGR, SPRoute) per design. Candidates are scored by post-detailed-routing WL, then vias, then GR runtime. Evaluation covered 7 designs × 3 nodes and reported **up to 8.72% post-DR wirelength reduction** vs the baseline routers. Routers evolved on small designs warm-start the evolution on larger ones — [arXiv 2604.22234](https://arxiv.org/pdf/2604.22234) [V-snip]. The repo runs 45 router-design-PDK pairs, one Docker container each. `GeneticRunCodex.sh` is the GA-style loop, `AGENTS.md` holds per-design context and `METRICS_TABLE.md` is the QoR log — [ASU-VDA-Lab/GR-Evolve](https://github.com/ASU-VDA-Lab/GR-Evolve) [V-repo]. Framework: custom shell + Codex CLI. Baseline: the hand-written routers, not BO.
- **GoalEvolve** (CODA-Team; arXiv 2608.16733 per the task brief. A web search for that ID returned nothing, so the ID is not verified). "Goal-driven evolution of bounded OpenROAD C++ algorithms toward specified QoR targets." The pipeline is a frozen QoR contract → bottleneck diagnosis and mechanism-card retrieval → Teacher planning / Student Codex workers → bounded C++ edits with isolated OpenROAD builds → post-placement optimization (rsz/rmp, power-aware) and global routing → validity checks → evidence-based promotion. Targets are TNS, dynamic power and leakage power. There are 8 released evolved source artifacts, and the AES-evolved binary was transferred to 7 other contest designs — [CODA-Team/GoalEvolve README](https://github.com/CODA-Team/GoalEvolve) [V-repo]. Numerical results were not found in the README (they are in paper/GoalEvolve.pdf, which was not read).
- **Automated QoR improvement in OpenROAD with coding agents** (arXiv 2601.06268, Jan 2026). A coding-agent loop achieved routed-WL reductions of up to 5.9% and ECP reductions of up to 10.0%. The WL gains came from one repository-level modification the agent discovered, not from per-design parameter tuning. AutoTuner is cited as the ML baseline — [arXiv 2601.06268](https://arxiv.org/html/2601.06268) [V-snip].
- **Multi-Agent Self-Evolved ABC** (NVIDIA Research + UMD; arXiv 2604.15082, Apr 2026). Multiple LLM agents rewrite sub-components of ABC's source code, with correctness checks and QoR checks in the loop — [arXiv 2604.15082](https://arxiv.org/pdf/2604.15082) [V-snip; no numbers seen].
- **Synthesis recipes (ABC command sequences).** The classical state of the art is ABC-RL (ICLR 2024, retrieval-guided RL + MCTS over sequences of 7 ABC transforms) — [ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/file/96bbdd0ed2a9e7cd2fb7caf2fae15f3d-Paper-Conference.pdf) [V-snip]. **I found no paper that uses an LLM directly as the ABC-recipe generator and compares it against BO or RL.** Related work: RTLScout (arXiv 2606.06530), where an LLM picks which subcircuits get curated ABC recipes such as `&deepsyn` — [arXiv 2606.06530](https://arxiv.org/pdf/2606.06530) [V-snip]; and "Rethinking Logic Optimization Operators" (arXiv 2607.23672), an agentic analysis of operator source code — [arXiv 2607.23672](https://arxiv.org/pdf/2607.23672) [V-snip].

### Cited Findings — analog sizing (LLM + BO)
- **ADO-LLM** (arXiv 2406.18770, 2024). LLM in-context proposals are injected into GP-BO's shared dataset. On a two-stage differential amplifier and a hysteresis comparator it reports better figures of merit than GP-BO with random initialization, and than an LLM with only zero-shot initialization — [arXiv 2406.18770](https://arxiv.org/html/2406.18770v1) [V-snip].
- **LLM-USO** (arXiv 2502.02764, 2025). Circuit knowledge is stored as structured text, and **BO uncertainty ranks LLM-generated suggestions**. It is evaluated with transfer across circuits — [ar5iv 2502.02764](https://ar5iv.labs.arxiv.org/html/2502.02764) [V-snip]. LEDRO, where the LLM iteratively shrinks the design space, is mentioned in the same results [V-snip].

### Cited Findings — semiconductor process / TCAD
- **AgenticTCAD** (Guangxi Fan + 5 co-authors, XJTLU-affiliated; arXiv 2512.23742, 2025-12-26, v2 2026-01-13; accepted at DATE 2026). An expert-curated open TCAD dataset trains a fine-tuned TCAD code-generation LLM, which is paired with a commercial reasoning model in a multi-agent loop. The artifact is **Sentaurus SDE/SDevice code**. A 2 nm NS-FET reached IRDS-2024 specs in **4.2 h, vs 7.1 days** for human experts with commercial tools. Energy-band diagrams are extracted automatically for interpretability — [arXiv 2512.23742](https://arxiv.org/html/2512.23742v1), [XJTLU scholar](https://scholar.xjtlu.edu.cn/en/publications/agentictcad-a-llm-based-multi-agent-framework-for-automated-tcad-/) [V-snip]. The baseline is human experts, not BO. Companion dataset repo: 22 baseline device families covering MOSFET, FinFET, GAAFET, TFET and others — [guangxifan/llm4tcad_flow](https://github.com/guangxifan/llm4tcad_flow) [V-repo].
- **czf-mq/agentic-tcad** (GitHub, 2026-08-25, Apache-2.0; independent). Gmsh/DEVSIM simulation of a 100 nm planar nMOS, comparing DeepSeek-V4-Flash, random search, scalar GP/EI BO and constrained BO. Setup: 3 trials × 25 TCAD evaluations each. **Evaluations to first feasible point: LLM 5/4/5 (median 5), constrained BO 10/11/13 (median 11)**, while random search and scalar BO each failed 2 of 3 trials (penalized median 26). The authors caution that the sample is too small for a superiority claim, and that the evaluated method is "V4-Flash + validation/repair + fallback" (4 of 72 steps used the deterministic fallback) — [README](https://github.com/czf-mq/agentic-tcad) [V-repo]. Framework: custom Python CLI, with JSON proposals.
- Other TCAD agent repos found, not assessed: [odokumaci/tcad-optimization-agent](https://github.com/odokumaci/tcad-optimization-agent) (2026-07) and [starlight-w/claude-sentaurus-skill](https://github.com/starlight-w/claude-sentaurus-skill) (2026-06, an agent skill for Sentaurus) [V-repo listing only].
- **Etch / deposition / CMP recipes:** **I found no 2025–2026 paper that applies an LLM as the optimizer for etch, deposition or CMP recipes.** The closest work is classical: BO/model-based etch recipe work that cuts recipe-creation cost by 75% or more on a 3D-NAND channel etch — [NSF PAR](https://par.nsf.gov/biblio/10224478); the Nature 2023 human–machine plasma-etch study (humans better early, computers better later) — [Nature s41586-023-05773-7](https://www.nature.com/articles/s41586-023-05773-7.pdf); and an Applied Materials patent on Bayesian process-recipe optimization — [US 12693652](https://patents.justia.com/patent/12693652) [V-snip]. I found nothing on LLMs for fab APC.

### Cited Findings — chemistry / industrial recipes
- **Iron Mind study** ("Pre-trained knowledge elevates LLMs beyond traditional chemical reaction optimizers"; arXiv 2509.00103, 2025). Six fully enumerated categorical reaction datasets (768 to 5,684 experiments) compared LLM-guided optimization against BO and random search. **BO retains superiority only for explicit multi-objective trade-offs.** It releases the Iron Mind platform with leaderboards — [arXiv 2509.00103](https://arxiv.org/abs/2509.00103) [V-snip].
- **GOLLuM** (arXiv 2504.06265; Nature Machine Intelligence version). LLM embeddings are fine-tuned through the GP marginal likelihood. On Buchwald–Hartwig it raises top-5% coverage from 24% to 43% in 50 iterations, vs static LLM embeddings, and the authors say it is the only LLM-based method in their comparison that beats traditional BO on sample efficiency — [arXiv 2504.06265](https://arxiv.org/html/2504.06265v1), [Nat. Mach. Intell.](https://www.nature.com/articles/s42256-026-01283-z) [V-snip]. Note: the Nature MI link title is "LLMs as uncertainty-calibrated optimizers for experimental discovery". Its mapping to GOLLuM came from the search summary and was not confirmed.
- **LGBO** (preference-guided LLM-in-BO; arXiv 2605.17976, May 2026) reports that LLAMBO does not achieve LGBO's acceleration — [arXiv 2605.17976](https://arxiv.org/html/2605.17976v1) [V-snip]. **LABO** (LLM-Accelerated BO through broad exploration and selective experimentation; arXiv 2605.22054) is another 2026 hybrid — [arXiv 2605.22054](https://arxiv.org/pdf/2605.22054) [V-snip; no numbers seen].
- **SAGA** (arXiv 2512.21782, Dec 2025, v2 Mar 2026). An outer LLM loop evolves the objectives and scoring functions, while an inner loop optimizes the solutions. Domains include **chemical process optimization**. It reports +37.2% average Pareto-front quality and 2.8× faster discovery — [arXiv 2512.21782](https://arxiv.org/abs/2512.21782) [V-snip].
- I found no sources in this session for CNC, additive-manufacturing, PLC or CFD/FEA setup optimization with LLMs.

### Cited Findings — general "LLM as optimizer" methods, and benchmark evidence
- **LLAMBO** (ICLR 2024; arXiv 2402.03921). The LLM does warm-start, surrogate and candidate sampling inside BO. It was best overall in HPO benchmarks, and **particularly strong in early iterations when observations are scarce**. It has a much larger compute footprint, and results are sensitive to the choice of LLM — [arXiv 2402.03921](https://arxiv.org/pdf/2402.03921) [V-snip].
- **LLaMEA** (IEEE TEVC 2025; arXiv 2405.20132). LLM-generated metaheuristic code was competitive with default CMA-ES, tuned CMA-ES and DE on BBOB 5-D — [arXiv 2405.20132](https://arxiv.org/html/2405.20132v4) [V-snip]. **LLaMEA-BO** (arXiv 2505.21034, May 2025): LLM-generated BO algorithms beat state-of-the-art BO baselines (HEBO, TuRBO1, VanillaBO, CMA-ES) on **19 of 24 BBOB functions in 5-D**. Limitations: possible bias toward trust-region methods and reliance on one LLM — [arXiv 2505.21034](https://arxiv.org/abs/2505.21034v1) [V-snip].
- A systematic study of LLM-centred evolutionary program search found that "a dedicated search component is essential, as stand-alone prompting is rarely competitive" [V-snip via search summary; exact paper URL not isolated].
- Background [K] (not re-fetched; URLs from memory):
  - OPRO, "LLMs as Optimizers" (Google DeepMind, 2023) — https://arxiv.org/abs/2309.03409
  - FunSearch (DeepMind, Nature 2023), evolutionary program search with an LLM — https://www.nature.com/articles/s41586-023-06924-6
  - AlphaEvolve (DeepMind, May 2025), LLM-ensemble code evolution with automated evaluators — https://deepmind.google/discover/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/
  - EoH, Evolution of Heuristics (ICML 2024) — https://arxiv.org/abs/2401.02051
  - ReEvo, reflective evolution (NeurIPS 2024) — https://arxiv.org/abs/2402.01145
  - EvoPrompt (ICLR 2024) — https://arxiv.org/abs/2309.08532

### Inferences
- Across the EDA and TCAD evidence, the LLM advantage is largest in **evaluations-to-first-feasible / cold start**: about 2× fewer evaluations in agentic-tcad, 40% fewer iterations in ORFS-agent, and early-stage strength in LLAMBO. It is smaller in the asymptotic best value: about 1 to 3% QoR vs AutoTuner per the ORFS-agent abstract.
- Code-space evolution (GR-Evolve 8.72% WL, coding agents 5.9% WL / 10% ECP) produces gains that parameter BO structurally cannot reach. The fair baseline for that work is the hand-crafted tool or other program-search methods, not BO.
- On categorical recipe spaces with strong priors (chemistry), LLMs match or beat BO except on explicit multi-objective trade-offs (Iron Mind). That suggests a hybrid design where BO/EHVI is kept for the Pareto part.

### Gaps
- No independent, multi-seed, equal-budget benchmark of LLM vs BO/TPE for ORFS tuning was found. The ORFS-agent "1–3% vs AutoTuner" vs ">13% vs BO" discrepancy is unresolved because arXiv was blocked.
- StateTune's numerical hypervolume margins over BO-qEHVI were not obtained.
- GoalEvolve's arXiv ID 2608.16733 and its numeric results were not verified.
- No LLM-for-etch/CMP/deposition/APC paper was found. Nothing was found for CNC, additive manufacturing, PLC or CFD within the call budget.
- No LLM-as-ABC-recipe-generator vs RL/BO study was found.

---

## Q2. Which use LangGraph to orchestrate the optimization loop?

### Takeaway
Among the works checked, only **EDA Pilot AI** (a GitHub project, not peer-reviewed) uses LangGraph. Its published benchmark ran without an LLM in the decision nodes. The research systems (ORFS-agent, StateTune, GR-Evolve, GoalEvolve, AgenticTCAD, czf-mq/agentic-tcad) all use custom Python/shell loops or coding-agent CLIs (Codex).

### Cited Findings
- EDA Pilot AI uses a LangGraph five-node loop: `analyse → propose → validate → run → check`. Only `analyse` and `propose` may call a model. Each proposal is limited to 3 changes, each with a reason. The loop stops at the budget or when the passing-clock gap drops below 0.05 ns. Tools are exposed through an **MCP server** (`list_params`, `run_flow`, `get_metrics`, `read_report`), protected by an allowlist, `shell=False` and a file-locked run budget. Dependencies are `langgraph>=1` and `mcp>=2` — [README](https://github.com/NileshModlier/EDA-Pilot-Agentic-AI) [V-repo]. The benchmark used the offline bisection advisor rather than an LLM — [BENCHMARK_RESULTS.md](https://github.com/NileshModlier/EDA-Pilot-Agentic-AI/blob/main/BENCHMARK_RESULTS.md) [V-repo].
- ORFS-agent is custom: `optimize.py`, `prompts.py`, `maindriver.sh`, Anthropic/OpenAI SDKs, scikit-optimize — [README](https://github.com/ABKGroup/ORFS-Agent) [V-repo].
- StateTune is custom Python (pydantic, BoTorch, its own LLM client and CoT parser) — [README](https://github.com/C-YuLong/stateTune) [V-repo].
- GR-Evolve uses the Codex CLI inside Docker with `GeneticRunCodex.sh` — [README](https://github.com/ASU-VDA-Lab/GR-Evolve) [V-repo]. GoalEvolve uses Codex CLI 0.146.0 Teacher/Student workers — [README](https://github.com/CODA-Team/GoalEvolve) [V-repo].
- MCP for EDA (no LangGraph): MCP4EDA (arXiv 2507.19570, Jul 2025) is "the first MCP server" for open-source RTL-to-GDSII toolchains — [arXiv 2507.19570](https://www.arxiv.org/pdf/2507.19570) [V-snip].
- A GitHub repository search for "LLM OpenROAD tuning langgraph" returned no results (gh search, this session).

### Inferences
- LangGraph is an engineering convenience here, mainly for state checkpointing and guarded tool nodes, not a source of QoR. The patterns that improved QoR were persistent typed memory, multi-fidelity promotion and surrogate-guided ranking, and those are framework-agnostic. A LangGraph implementation could copy EDA Pilot's guardrail design (code-only validate/run nodes, an allowlist, MCP tools) together with StateTune's memory and EHVI promotion.

### Gaps
- I did not search exhaustively for LangGraph in chemistry or self-driving-lab optimizers (ChemCrow uses LangChain [K], but it is not a recipe optimizer with a BO comparison).

---

## Q3. Which hybrid designs (LLM proposes + BO/GA/CMA-ES refines numeric params) work best?

### Takeaway
The best-documented hybrids keep a **probabilistic surrogate (GP/EHVI) in charge of selection and budget**. The LLM supplies priors, candidates, repairs and rules: StateTune (LLM + multi-fidelity GP EHVI/runtime promotion), ORFS-agent (LLM with GP/BO tools), ADO-LLM and LLM-USO (LLM candidates ranked by BO uncertainty), and LLAMBO/GOLLuM (LLM inside the BO surrogate). For code-structured artifacts, the winning pattern is **LLM code mutation inside a GA/evolutionary population with an automated evaluator** (GR-Evolve, GoalEvolve, LLaMEA, EoH, ReEvo, AlphaEvolve).

### Cited Findings
- StateTune ranks candidates by EHVI(x)/(t̂_ucb(x)+ε) with a multi-fidelity GP. Ablations show memory gating (−43.4% HV without it) and RAG (−46.1% HV without it) both matter. It beat pure BO-qEHVI and TPE on all 6 blocks — [README](https://github.com/C-YuLong/stateTune) [V-repo].
- ORFS-agent's LLM has access to GP modelling and kernel selection and to scikit-optimize BO. It reached its results with 40% fewer iterations — [README](https://github.com/ABKGroup/ORFS-Agent) [V-repo].
- ADO-LLM: LLM proposals plus a GP-BO proposer sharing one dataset. It beat GP-BO and LLM-only on analog FOM — [arXiv 2406.18770](https://arxiv.org/html/2406.18770v1) [V-snip]. LLM-USO uses BO uncertainty to rank LLM suggestions — [ar5iv 2502.02764](https://ar5iv.labs.arxiv.org/html/2502.02764) [V-snip].
- LLAMBO is strongest early, with high compute cost — [arXiv 2402.03921](https://arxiv.org/pdf/2402.03921) [V-snip]. GOLLuM (GP-trained LLM embeddings) is reported as the only LLM method in its comparison to beat BO on sample efficiency — [arXiv 2504.06265](https://arxiv.org/html/2504.06265v1) [V-snip]. LGBO claims to beat LLAMBO — [arXiv 2605.17976](https://arxiv.org/html/2605.17976v1) [V-snip].
- czf-mq/agentic-tcad shows the "LLM + validation/repair + deterministic fallback" pattern beating constrained BO on evaluations-to-feasible (median 5 vs 11) — [README](https://github.com/czf-mq/agentic-tcad) [V-repo].
- In the chemistry benchmark, BO is still better for explicit multi-objective trade-offs — [arXiv 2509.00103](https://arxiv.org/abs/2509.00103) [V-snip].
- LLaMEA-BO (LLM evolves the BO algorithm itself) won 19 of 24 BBOB-5D functions vs HEBO, TuRBO and CMA-ES — [arXiv 2505.21034](https://arxiv.org/abs/2505.21034v1) [V-snip].
- Program-search studies say a dedicated search component, rather than plain prompting, is essential [V-snip, URL not isolated].

### Inferences
- A practical recipe for a text/code-recipe optimizer:
  1. The LLM handles structure and categorical choices, cold-start priors, and failure diagnosis and repair.
  2. A GP/TPE or CMA-ES refines continuous knobs.
  3. EHVI/UCB-per-cost acquisition decides which candidates get expensive full-fidelity evaluation.
  4. Evidence-gated memory holds rules learned from failures.
  5. A validator/allowlist sits before execution.
- No source in this set directly compares "LLM proposes structure, then CMA-ES refines numerics" against StateTune-style "LLM proposes, GP selects". Which is best is therefore an inference, not an established result.

### Gaps
- There is no head-to-head comparison of the hybrid families (LLM+GP selection vs LLM+CMA-ES refinement vs LLM-inside-surrogate) on the same EDA or process task.
- Evidence for LLM + CMA-ES hybrids in EDA or process recipes specifically was not found.
- Cost accounting is rarely reported. StateTune is the exception at about 6M tokens and 192 thread·h per block.
