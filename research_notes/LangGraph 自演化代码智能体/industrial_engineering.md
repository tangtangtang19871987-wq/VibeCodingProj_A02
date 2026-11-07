# LLM code agents with self-improvement in industrial / engineering domains (non-EDA), up to 2026-11

Research date: 2026-11-07. Scope covers CAE/CFD/FEA, optics/photonics, computational imaging, CAD, PLC/industrial control, OR solvers, chemistry/materials, power systems and robotics. Semiconductor/EDA is excluded.

Method and access limits: arxiv.org and alphaxiv.org could not be fetched in this session (DNS blocked). The GitHub API repo-contents endpoint was also blocked; repo *search* worked. Most facts below therefore come from search-engine snippets of arXiv abstracts and HTML, Wiley, HF and EmergentMind pages, and GitHub search metadata.

Verification levels:
- **[V1]** confirmed from a primary-source snippet (arXiv, publisher or repo metadata).
- **[V2]** secondary summary only (themoonlight, liner, etc.; often AI-written).
- **[V3]** from my prior knowledge, not re-verified this session. Treat [V3] as needing a check.

---

## Q1. Which industrial-engineering code agents use LangGraph, and how do they self-improve?

### Takeaway
LangGraph is the de-facto orchestration layer for *workflow-style* simulator agents (Foam-Agent for CFD, PDE-Agents for FEM, ChemGraph for chemistry, plus many small 2026 GitHub projects). These agents mostly "self-improve" only inside a run: execute → error log → reviewer/reflector → patch → re-run. A few add persistent memory (GraphRAG run history).

Truly *cross-task* self-evolution comes mostly from custom harnesses, not LangGraph:
- skill-file evolution (metasurface MCE)
- evolutionary program search (LLaMEA, Ptychi-Evolve)
- verified-failure → prompt/rule updates (PFAgent)
- self-training with fine-tuning (AutoFOAM)

### Catalog (framework explicitly recorded)

| # | System | Date | Org | Domain | Framework | Architecture | Self-evolution mechanism | Evaluator / simulator | Key results | Open source | Verif. |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Foam-Agent** ([arXiv 2505.04997](https://arxiv.org/abs/2505.04997); v2 [2509.18178](https://arxiv.org/html/2509.18178v2); [NeurIPS ML4PS 2025](https://ml4physicalsciences.github.io/2025/files/NeurIPS_ML4PS_2025_244.pdf)) | 2025-05 (v1); 2025-09 (v2) | RPI (csml-rpi) | CFD / OpenFOAM | **LangGraph**; later version modularized as **MCP** server | Six primary agents (architect/planner, meshing (blockMesh/snappyHexMesh/Gmsh), input-file writer, runner, reviewer); dynamic adaptive workflow topology; RAG over OpenFOAM tutorials | Within-run iterative error correction: reviewer diagnoses solver failures and proposes fixes, no human. No persistent cross-task learning | OpenFOAM execution + logs | 83.6% success (v1), 88.2% (v2), both with Claude 3.5 Sonnet; MetaOpenFOAM 55.5%, OpenFOAM-GPT 37.3% on the same benchmark | Yes: [csml-rpi/Foam-Agent](https://github.com/csml-rpi/Foam-Agent) (≈364★, created 2025-05-06) | V1 |
| 2 | **MetaOpenFOAM** ([review](https://www.themoonlight.io/fr/review/metaopenfoam-an-llm-based-multi-agent-framework-for-cfd)) | 2024-07 | Tsinghua (Chen et al.) [V3 for org] | CFD | **MetaGPT** (assembly-line SOP) + RAG | Architect / InputWriter / Runner (writes Allrun) / Reviewer | Reviewer → InputWriter loop on errors | OpenFOAM | 55.5% on Foam-Agent's benchmark | Yes: [Terry-cyx/MetaOpenFOAM](https://github.com/Terry-cyx/MetaOpenFOAM) (≈210★) | V1/V2 |
| 3 | **OpenFOAMGPT** (1.0/2.0) | 2025 | Pedro / Yupeng Qi et al. [V3] | CFD | Custom (RAG + GPT-4o/o1) [V3] | Generator + executor + error-feedback | Iterative correction | OpenFOAM | 37.3% on Foam-Agent's benchmark ([source](https://arxiv.org/abs/2505.04997)) | Website repo only ([YupengQI99/openfoamgpt-website](https://github.com/YupengQI99/openfoamgpt-website)) | V2/V3 |
| 4 | **AutoFOAM: The Self-Refining Autonomous OpenFOAM Agent** ([arXiv 2608.00003](https://arxiv.org/pdf/2608.00003)) | 2026 (search snippet says May 2026; ID implies Aug 2026, so the date is inconsistent) | unknown | CFD | Custom; fine-tuned **Qwen2.5-Coder-14B** | Generate → check → run → revise | "Seven-layer self-evolution loop" with repeated self-training. Model collapse is avoided via RAG-augmented retry context, "surgical dictionary-level patching" and prompt-diversity paraphrasing | OpenFOAM | Reported 100% execution success; 96.4% solver-routing precision on out-of-distribution prompts | unknown | V2 (snippet only) |
| 5 | **Case-Bundle Operating Model for Coding Agents in OpenFOAM CFD** ([arXiv 2609.11941](https://arxiv.org/pdf/2609.11941)) | 2026-09 | unknown | CFD | Agent Skills (SKILL.md progressive disclosure) on generic coding agents | Skill files hold discovery metadata, core instructions and lazily loaded references/scripts; one skill selects nearby OpenFOAM tutorial cases before building a case | Skill library (curated; evolution not confirmed) | OpenFOAM | n/a | unknown | V2 |
| 6 | **ChatCFD** ([arXiv 2506.02019](https://arxiv.org/pdf/2506.02019v3)) | 2025-06 | unknown [V3: Peking U.] | CFD | Custom multi-agent | Multi-agent + OpenFOAM knowledge base + iterative reflection | Reflection loop | OpenFOAM | not retrieved | unknown | V2 |
| 7 | **HarnessFOAM** ([GitHub](https://github.com/isabecurtis023-lang/HarnessFOAM)) | 2026-08 | individual | CFD | Claims "end-to-end composable multi-agent" (Foam-Agent derivative; matched a "langgraph CFD" repo search) | — | — | OpenFOAM | — | Yes (≈17★) | V1 metadata only |
| 8 | **PDE-Agents** ([arXiv 2606.07850](https://arxiv.org/pdf/2606.07850); [HF](https://huggingface.co/papers/2606.07850)) | 2026-06-05 | Adhikari et al. (MatPro-IFE) | FEM simulations | **LangGraph supervisor** + 3 agents (Simulation, Analytics, Database); local Qwen3-Coder-Next + Llama 4 Scout on 2× RTX PRO 6000 | Generator + FEM executor + analytics + GraphRAG memory (Neo4j, 768-d embeddings: material properties, failure patterns, prior run history) | Persistent run-history / failure-pattern memory | FEM solver | 1,369 real simulation runs, 97.8% success. Finding: *integration pattern, not knowledge content*, decides whether GraphRAG helps or hurts | Yes: github.com/MatPro-IFE/pde-agents | V1 |
| 9 | **FEABench** ([arXiv 2504.06260](https://arxiv.org/abs/2504.06260v1); [Google Research](https://research.google/pubs/feabench-evaluating-language-models-on-real-world-physics-reasoning-ability/)) | 2024-12 (NeurIPS'24 workshop); 2025-04 arXiv | Google | FEA / COMSOL Multiphysics API | Custom agent (ToolLookup, execution feedback) [V3 for details] | Generator + COMSOL executor + feedback | Iterative execution-feedback correction | COMSOL (licensed) | Best strategy produced executable API calls 88% of the time; **no model or agent fully solved any problem**. Gold = 15 problems, Large = 200. Later version: closed models 60–79% executability | Yes: github.com/google/feabench | V1 |
| 10 | **AbaqusAgent** / **VFEAgent** ([search listing](https://www.opentrain.ai/papers/a-multi-ai-agent-framework-enabling-end-to-end-finite-element-analysis-for-solid--arxiv-2606.00138/); [VFEAgent review](https://www.themoonlight.io/tw/review/vfeagent-a-multimodal-agent-framework-for-end-to-end-automated-finite-element-analysis)) | 2026-05/06 (arXiv 2606.00138) | unknown | Solid mechanics FEA, Abaqus | Not stated | VFEAgent: Perception (OCR / geometry detection), Reasoning, **Validation** agent, Orchestrator | Validation-agent loop | Abaqus (commercial) | not retrieved | unknown | V2 |
| 11 | **Metasurface self-evolving agentic framework (MCE)** ([arXiv 2604.01480](https://arxiv.org/abs/2604.01480); [Laser & Photonics Reviews, DOI 10.1002/lpor.71739](https://onlinelibrary.wiley.com/doi/full/10.1002/lpor.71739)) | 2026-04-01 (v1); journal 2026 | Huang, Zheng, Dong, Tang, Zhao, Shawon, **Hualiang Zhang** (UMass Lowell [V3]) | Metasurface / metaoptics inverse design | **Custom** harness (repo `mce/`); both agents are Claude Sonnet 4.6 | Meta-agent (edits skill files) + coding agent (writes `solve_inverse_design()`) + **deterministic evaluator** (`meta_design/`) | **Skill-file evolution**: after each iteration the meta-agent reads rollout logs and validation summaries and rewrites human-readable skill files. Weights and solver stay fixed. Inner loop retries a failed program; outer loop revises skills and **keeps the best version on validation**. 4 evolution iterations | **TorchRDIT** (differentiable RCWA-type solver) | In-distribution task success 38%→74%; criteria pass fraction 0.510→0.870; avg attempts 4.10→2.30. Held-out families: v1 shows marginal binary change but better margin/error composition. Journal/v2 reportedly 0.92→0.90 and 0.20→0.90 (not cross-checked) | Yes: [yi-huang-1/evo-metaoptics](https://github.com/yi-huang-1/evo-metaoptics) | V1 |
| 12 | **LLaMEA for photonics** ([arXiv 2503.19742](https://arxiv.org/pdf/2503.19742); [GECCO HUMIES slides](https://www.human-competitive.org/sites/default/files/2_van_stein_slides.pdf)) | 2025-03; GECCO 2025 | Leiden (LIACS): Yin, Kononova, Bäck, van Stein | Multilayer photonics: Bragg mirror, ellipsometry inverse, solar-cell anti-reflection coating | **Custom** (LLaMEA: LLM + (μ,λ)/(μ+λ) ES) | LLM generates optimizer code; executor/benchmark evaluator; self-debugging mutation | **Evolutionary algorithm discovery**: ES configs (1,5), (1+5), (2,10), (2+10), (5+5); auto-extracted problem insights added to prompts | Photonic simulators (transfer matrix) | Algorithms evolved on small instances match or beat quasi-oppositional DE on large real instances | Yes: [XAI-liacs/LLaMEA](https://github.com/XAI-liacs/LLaMEA) (≈133★); BLADE benchmark | V1 |
| 13 | **Ptychi-Evolve** ([arXiv 2603.05696](https://arxiv.org/abs/2603.05696)) | 2026-03-05 | Argonne (APS) + Rice: Yin, Du, Deng, Yang, Han, Yi Jiang | Computational imaging: ptychography reconstruction regularizers | **Custom** (repo [xyin-anl/Ptychi-Evolve](https://github.com/xyin-anl/Ptychi-Evolve), created 2025-10) | LLM generates Python regularizers as methods of Pty-Chi's `Object` class (fixed interface); evaluator runs reconstruction; lineage/metadata store | **LLM-guided evolution**: semantic crossover and mutation (add components / change math while keeping core function); also tunes parameters | Pty-Chi reconstruction engine; SSIM/PSNR | Up to +0.26 SSIM and +8.3 dB PSNR vs. unregularized Pty-Chi; 3 cases (X-ray multislice, X-ray IC, electron apoferritin) | Yes (≈1★) | V1 |
| 14 | **Agents4PLC** ([arXiv 2410.14209](https://arxiv.org/abs/2410.14209v2)) | 2024-10 | Zhejiang U. (Luo et al.) [V3 for org] | PLC / IEC 61131-3 Structured Text | Custom multi-agent [V3]; the framework is not stated in the retrieved snippets | Retrieval, planning, coding, debugging and **verification** agents in a closed loop | Code ↔ debug loop until compile + formal verification pass | Compiler (e.g. MATIEC/ruSTy) + model checker (nuXmv/PLCverif) [V3]; benchmark with human-verified formal specs | "Superior results across increasingly rigorous metrics" (no numbers retrieved) | Yes: [Luoji-zju/Agents4PLC_release](https://github.com/Luoji-zju/Agents4PLC_release) (≈83★) | V1/V2 |
| 15 | **LLM4PLC** ([arXiv 2401.05443](https://arxiv.org/html/2401.05443v1)) | 2024-01 (ICSE-SEIP'24 [V3]) | UC Irvine (AICPS) | PLC ST | Custom pipeline | LLM agent + grammar checker + compiler + SMV model checker; **optional human intervention** | Verifier errors fed back for refinement | Compiler + NuSMV | not retrieved (reported earlier as improving pass rate [V3]) | Yes: [AICPS/LLM_4_PLC](https://github.com/AICPS/LLM_4_PLC) (≈72★) | V1 |
| 16 | **OptiMUS** (0.1→0.3) ([ICML'24 arXiv 2402.10172](https://arxiv.org/pdf/2402.10172.pdf); [0.3: 2407.19633](https://arxiv.org/html/2407.19633v3)) | 2023-10 → 2024-07 | Stanford (AhmadiTeshnizi, Gao, Udell) | OR: (MI)LP modeling | Custom modular agent | Formulator, programmer, evaluator, debugger; **connection graph** so each constraint/objective is handled independently (long descriptions, big data files) | Evaluate generated solutions → fix model/code (within task) | Gurobi/solver execution | 0.3 beats prior SOTA by >22% on existing datasets and by 24% on the new hard set; beats GPT-4o alone by >38%/40% on easy sets. NL4Opt 78.8% vs. Chain-of-Experts 64.2% (secondary) | Yes (Stanford) [V3] | V1/V2 |
| 17 | **ChemGraph** ([arXiv 2506.06363](https://arxiv.org/pdf/2506.06363); [Commun. Chem. / PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12824235/)) | 2025-06; journal 2025 | Argonne ALCF | Computational chemistry (semi-empirical, ML potentials, DFT via ASE) | **LangGraph** (state/nodes/edges graph design; LangGraph named in repo docs [V3]) | Single- and multi-agent (planner / executor / aggregator) | Task decomposition; no persistent self-evolution | ASE / xTB / MACE / DFT codes | 13 benchmark tasks; multi-agent decomposition helps small LLMs [V3] | Yes (argonne-lcf/ChemGraph [V3]) | V1/V3 |
| 18 | **ChemCrow** / **MDCrow** | 2023 / 2025 | EPFL + Rochester (White lab) | Chemistry / molecular dynamics | **LangChain** (ChemCrow, well known); MDCrow is also LangChain-based [V3] | Tool-calling ReAct agents | None (tool use only) | RDKit, OpenMM, etc. | — | Yes | V3 |
| 19 | **PFAgent** ([arXiv 2604.10846](https://arxiv.org/html/2604.10846v1); [review](https://www.themoonlight.io/en/review/pfagent-a-tractable-and-self-evolving-power-flow-agent-for-interactive-grid-analysis)) | 2026-04 | She, Chen, Guo, Li | Power systems: steady-state power flow | Not stated | RAG grounding + AI-assisted debugging + verification | **Verified failures and deployment feedback → continuous prompt/rule updates** (no retraining); human-in-the-loop feedback | **ANDES** | RAG grounding is the key factor for multi-turn reliability; self-evolution recovers dominant failure modes. One commentary says the self-evolution metrics are thin | unknown | V1/V2 |
| 20 | **Grid-Mind** ([arXiv 2602.20683](https://arxiv.org/html/2602.20683)) | 2026-02 | unknown | Power-grid interconnection studies | Not stated | LLM orchestrator + multi-fidelity solver layer (pandapower AC/OPF, ANDES dynamics, ParaEMT EMT) + **physics-grounded violation checking** + lessons/memory | Lessons memory feedback | pandapower / ANDES / ParaEMT | Not retrieved | unknown | V1 |
| 21 | **Feedback-driven multi-agent for power system simulation** ([arXiv 2411.16707](https://pdf.arxiv.org/abs/2411.16707)) | 2024-11 | unknown [V3: Univ. Washington / PNNL?] | Power system simulation | Custom | Error-feedback loop + RAG | Error-feedback | DALINE / MATPOWER-type tools [V3] | not retrieved | — | V2 |
| 22 | **CADCodeVerify** ([ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/file/81a934cd364e18ea6fdeaf57a93c17d4-Paper-Conference.pdf)) | 2024-10 (arXiv 2410.05340) | Georgia Tech / Autodesk [V3] | CAD (CadQuery) | Custom, training-free | VLM generates CadQuery → render → self-generated verification questions → feedback | Within-task visual self-verification | CadQuery render; CADPrompt (200 objects) | GPT-4: −7.30% point-cloud distance, +5.5% successful generation | Yes [V3] | V1 |
| 23 | **CADSmith / CADReasoner / IterCAD** ([2603.26512](https://arxiv.org/pdf/2603.26512), [2603.29847](https://arxiv.org/pdf/2603.29847), [IterCAD review](https://www.themoonlight.io/es/review/itercad-an-iterative-multimodal-agent-for-visually-grounded-cad-generation-and-editing)) | 2026-03 | various | CAD | Custom | CADSmith uses a **separate, stronger judge (Claude Opus)** to avoid self-confirmation. CADReasoner adds metric point-cloud geometric feedback because visual feedback can't resolve dimensional errors. IterCAD layers compiler + execution + visual feedback | Within-task refinement | CadQuery / B-Rep geometry | not retrieved | — | V2 |
| 24 | **TurboAgent** ([prompts repo](https://github.com/wuyueteng/TurboAgent-prompts)) | 2026-03 | individual / academic | Compressor blade aerodynamic design | **LangGraph** multi-agent (README description) | Diffusion generator (CDDPM) + ViT surrogate + GA/PSO/LLM optimizer + CFD | Surrogate-assisted optimization | CFD + surrogate | — | Prompts only | V1 metadata |
| 25 | Small 2025–26 LangGraph engineering repos: [MD-Simulation-Agent](https://github.com/wkk990914-droid/MD-Simulation-Agent) (LangChain + LangGraph, MD), [cfd-simulation-assistant](https://github.com/A2ELAOUDI/cfd-simulation-assistant) (LangGraph, CFD log/convergence analysis), [Agentic-Robo-SWE](https://github.com/Matt14-mander/Agentic-Robo-SWE) (LangGraph, simulation-in-the-loop robotics debugging, 2026-06), [MechAgent](https://github.com/elouansalaun/MechAgent) (2026-11, spec → verified mechanical part with simulation) | 2025-12 → 2026-11 | individuals | various | LangGraph (per descriptions) | — | — | — | — | Yes (0–2★) | V1 metadata only |
| 26 | **Eureka** (robotics reward-code evolution) | 2023-10 | NVIDIA / UPenn | Robotics RL reward design | Custom | GPT-4 writes reward code → Isaac Gym RL training → reward reflection (training statistics) → next generation | Evolutionary in-context search + reward reflection | GPU-parallel simulation (Isaac Gym) | Beat human expert rewards on 83% of 29 tasks; 52% avg normalized improvement | Yes | V3 |

### Cited findings (key items)
- Foam-Agent is "a multi-agent system built on LangGraph, where each agent performs a specialized task within the CFD pipeline." Success: 83.6% (v1) / 88.2% (v2) with Claude 3.5 Sonnet, vs. MetaOpenFOAM 55.5% and OpenFOAM-GPT 37.3%. The later version uses six agents, dynamic topology and MCP — [arXiv 2505.04997](https://arxiv.org/html/2505.04997), [arXiv 2509.18178](https://arxiv.org/pdf/2509.18178v1)
- MetaOpenFOAM uses the MetaGPT assembly-line paradigm, with a Runner that writes the Allrun file — [themoonlight review](https://www.themoonlight.io/fr/review/metaopenfoam-an-llm-based-multi-agent-framework-for-cfd)
- PDE-Agents: a LangGraph supervisor over Simulation/Analytics/Database agents with Neo4j GraphRAG (failure patterns, run history); 1,369 runs at 97.8% success; "integration pattern, not knowledge content, determines whether GraphRAG augmentation helps or hinders" — [arXiv 2606.07850](https://arxiv.org/pdf/2606.07850), [HF](https://huggingface.co/papers/2606.07850)
- The metasurface MCE meta-agent revises skill files from rollout logs and validation summaries without changing weights or the solver. The coding agent writes `solve_inverse_design()` for TorchRDIT. Success 38%→74%, attempts 4.10→2.30, Claude Sonnet 4.6, 4 iterations — [arXiv 2604.01480](https://arxiv.org/abs/2604.01480), [Wiley LPOR](https://onlinelibrary.wiley.com/doi/full/10.1002/lpor.71739), [repo](https://github.com/yi-huang-1/evo-metaoptics)
- Ptychi-Evolve evolves executable regularizers (fixed `Object`-class interface) with LLM-semantic crossover and mutation, and records lineage; up to +0.26 SSIM / +8.3 dB PSNR — [arXiv 2603.05696](https://arxiv.org/abs/2603.05696)
- PFAgent turns verified failures and deployment feedback into prompt/rule updates, with human-in-the-loop, on ANDES — [arXiv 2604.10846](https://arxiv.org/html/2604.10846v1)
- AutoFOAM claims a seven-layer self-evolution loop on fine-tuned Qwen2.5-Coder-14B, with collapse guards (RAG retry context, dictionary-level patching, paraphrase diversity) — [arXiv 2608.00003](https://arxiv.org/pdf/2608.00003) (snippet only)
- FEABench: no LLM or agent fully solved any COMSOL problem; best executability was 88% — [Google Research](https://research.google/pubs/feabench-evaluating-language-models-on-real-world-physics-reasoning-ability/), [arXiv](https://arxiv.org/abs/2504.06260v1)

### Inferences
- LangGraph systems in this space (Foam-Agent, PDE-Agents, ChemGraph, TurboAgent) treat LangGraph as a **stateful DAG with conditional retry edges** (run → review → rewrite → run). Their "self-improvement" is mostly intra-episode repair. PDE-Agents' GraphRAG run history is the clearest LangGraph example of persistent experience.
- The strongest *self-evolution* results (MCE 38→74%, LLaMEA, Ptychi-Evolve, Eureka) come from custom loops. Nothing stops these from being expressed in LangGraph: an outer graph over evolution iterations plus an inner per-task subgraph, with checkpointers for long-running state.

### Gaps
- I could not confirm the framework for Agents4PLC, AutoFOAM, PFAgent, Grid-Mind, VFEAgent/AbaqusAgent or ChatCFD; the snippets don't name one, and full texts were blocked.
- ChemGraph's LangGraph basis is from prior knowledge; the search snippet only described a graph state/node design.
- No LangChain official case study on industrial-engineering simulation agents was found (not searched in depth because of the tool budget).
- Siemens (Industrial Copilot), ANSYS (SimAI / AnsysGPT), Autodesk and COMSOL industry agents were not covered. No reliable public detail on their self-evolution or framework was retrieved.
- OR-LLM-Agent, OptiTree, ORLM and LLMOPT returned no results this session.

---

## Q2. What are the strongest results and the common architecture patterns?

### Takeaway
The strongest quantitative results are:
- CFD workflow automation: Foam-Agent 88.2%, PDE-Agents 97.8% over 1,369 FEM runs, AutoFOAM's claimed 100% execution.
- Cross-task skill evolution: metasurface MCE, 38%→74% success with ~44% fewer attempts.
- Evolved algorithms beating hand-designed baselines: Ptychi-Evolve +8.3 dB PSNR; LLaMEA photonics matching QODE; Eureka beating humans on 83% of tasks.

The hardest open problem is commercial multiphysics FEA. FEABench reports 0 problems fully solved.

The common architecture: **generator (coder) → deterministic simulator/executor → evaluator (hard criteria + log parsing) → reflector/reviewer → memory (RAG over tutorials/manuals, run history, skill files) → outer evolution loop that selects on held-out validation.**

### Cited findings
- **Ranked results** (headline numbers from the table above):
  - PDE-Agents: 97.8% over 1,369 runs — [arXiv 2606.07850](https://arxiv.org/pdf/2606.07850)
  - Foam-Agent: 88.2% vs. MetaOpenFOAM 55.5% — [arXiv 2509.18178](https://arxiv.org/html/2509.18178v2)
  - MCE: 38→74% success; pass fraction 0.51→0.87 — [arXiv 2604.01480](https://arxiv.org/abs/2604.01480)
  - Ptychi-Evolve: +0.26 SSIM / +8.3 dB — [arXiv 2603.05696](https://arxiv.org/abs/2603.05696)
  - OptiMUS-0.3: +22% / +24% vs. prior SOTA — [arXiv 2407.19633](https://arxiv.org/html/2407.19633v3)
  - FEABench: 88% executable, 0 solved — [arXiv 2504.06260](https://arxiv.org/abs/2504.06260v1)
- **Pattern: role-specialized pipelines.** Architect → mesher → input writer → runner → reviewer (Foam-Agent, MetaOpenFOAM). OptiMUS's connection graph decomposes per-constraint to keep prompts small — [Foam-Agent](https://arxiv.org/html/2505.04997), [OptiMUS](https://arxiv.org/pdf/2402.10172.pdf)
- **Pattern: fixed-interface code slots.** `solve_inverse_design()` (MCE) and Pty-Chi `Object` methods (Ptychi-Evolve) put the LLM's freedom inside a sandboxed function, while the physics solver stays fixed and trusted — [MCE](https://onlinelibrary.wiley.com/doi/full/10.1002/lpor.71739), [Ptychi-Evolve](https://arxiv.org/html/2603.05696)
- **Pattern: formal or deterministic verifiers as the reward.** Compilers plus SMV/nuXmv model checking (LLM4PLC, Agents4PLC); a deterministic evaluator with per-task criteria (MCE); physics-grounded violation checks (Grid-Mind) — [LLM4PLC](https://arxiv.org/html/2401.05443v1), [Agents4PLC](https://arxiv.org/abs/2410.14209v2), [Grid-Mind](https://arxiv.org/html/2602.20683)
- **Pattern: multi-fidelity simulation.** Grid-Mind cascades pandapower (steady state) → ANDES (dynamics) → ParaEMT (EMT) — [Grid-Mind](https://arxiv.org/html/2602.20683)
- **Pattern: example-first retrieval / skills.** The case-bundle model loads nearby OpenFOAM tutorials before building a case, via progressive-disclosure skills; Foam-Agent and MetaOpenFOAM use RAG over tutorials — [arXiv 2609.11941](https://arxiv.org/pdf/2609.11941)
- **Pattern: an independent judge.** CADSmith uses a stronger, different model (Claude Opus) as judge to avoid self-confirmation. CADReasoner adds metric geometric checks because visual feedback can't resolve dimensional errors — [search summary of 2603.x CAD papers](https://arxiv.org/pdf/2603.26512)

### Inferences
- Success rates are benchmark-specific and not comparable across papers. Foam-Agent's 88% and PDE-Agents' 97.8% measure "ran and met the workflow criteria," not physics fidelity.
- The MCE result is the closest analogue to an ILT agent: a differentiable EM solver, a code-writing agent producing an optimizer, and skill evolution judged by a deterministic evaluator.

### Gaps
- No standardized cost data (tokens, simulator CPU-hours per improvement) was retrieved for any system.
- Held-out generalization of evolved skills is weak or contested: MCE v1 showed only marginal binary transfer, and journal figures could not be cross-checked.

---

## Q3. What lessons transfer to an ILT/OPC self-evolving code agent?

### Takeaway
Build it as a LangGraph two-loop system.

- **Inner loop (per task / clip):** code generation in a fixed-signature slot (for example `optimize_mask(target, litho_model, cfg)`) → lithography simulation → deterministic evaluator (EPE, PV-band, MRC/manufacturability, runtime) → reflector → patch.
- **Outer loop:** a meta-agent rewrites skill files and memory from logs. Accept a change only if it improves a frozen held-out validation set.

Add multi-fidelity simulation, physics/rule validity gates, anti-reward-hacking guards and human-approval interrupts.

### Cited findings → transferable design patterns
1. **Freeze the physics, evolve only code and skills.** MCE keeps the solver and weights fixed and evolves human-readable skill files. Ptychi-Evolve evolves only regularizer functions behind a standard interface. For ILT, keep the litho model (Hopkins/SOCS kernels, resist model) and metric code read-only and outside the agent's write scope — [MCE](https://arxiv.org/abs/2604.01480), [Ptychi-Evolve](https://arxiv.org/abs/2603.05696)
2. **Deterministic evaluator with multi-criteria pass fraction, not just pass/fail.** MCE reports both binary success and criteria pass fraction and margin, which exposed partial transfer that binary metrics missed. For ILT, report EPE, PV-band, L2 and MRC violations separately, with margins — [MCE](https://arxiv.org/abs/2604.01480)
3. **Validation-gated skill updates (keep best on validation).** Guards against skill drift and overfitting to the training clips — [Wiley LPOR summary](https://onlinelibrary.wiley.com/doi/full/10.1002/lpor.71739)
4. **Expensive simulators → multi-fidelity cascade.** Grid-Mind escalates fidelity. Eureka and LLaMEA evaluate cheaply on small instances and transfer up (LLaMEA evolved on small problems, then beat QODE on large ones). For ILT: a fast low-kernel or GPU (TorchLitho-style) model for screening, then full-chip rigorous simulation for finalists — [Grid-Mind](https://arxiv.org/html/2602.20683), [LLaMEA photonics](https://arxiv.org/pdf/2503.19742)
5. **License-restricted tools (COMSOL, Abaqus, ANSYS, commercial OPC such as Calibre/Proteus).** Wrap them as a tool server; Foam-Agent v2 moved to MCP, and a 2026 fork does "brain out, hands in" with a key-free MCP server plus Docker. Limit agent calls by budget and queue licensed runs. FEABench shows agents hallucinate API details for commercial tools (interface factuality is a weak spot), so provide API docs/RAG and a tool-lookup step — [Foam-Agent v2](https://arxiv.org/html/2509.18178v2), [apekshhaa/Foam-Agent](https://github.com/apekshhaa/Foam-Agent), [FEABench](https://arxiv.org/abs/2504.06260v1)
6. **Physics validity checks as hard gates.** Grid-Mind uses physics-grounded violation checking. Agents4PLC/LLM4PLC use formal model checking. CADReasoner uses metric geometry because rendered images were "lossy." For ILT: MRC/DRC checks, mask-rule manufacturability, contour sanity, energy/dose conservation and process-window checks before any score counts — [Grid-Mind](https://arxiv.org/html/2602.20683), [LLM4PLC](https://arxiv.org/html/2401.05443v1)
7. **Reward-hacking defenses:**
   - Fixed interfaces and a read-only evaluator (MCE, Ptychi-Evolve).
   - An independent stronger judge rather than self-judgment (CADSmith).
   - Held-out task families (MCE).
   - Metric diversity, so improving one metric can't hide degradation (SSIM *and* PSNR in Ptychi-Evolve).
   - Collapse guards in self-training (AutoFOAM's paraphrase diversity and surgical patching).

   ILT-specific hacks to guard against: shrinking the evaluated region, skipping MRC, overfitting kernels to a test clip, and editing the target. Sources: [CAD papers](https://arxiv.org/pdf/2603.26512), [AutoFOAM](https://arxiv.org/pdf/2608.00003)
8. **Experience and skill banks:**
   - PDE-Agents' Neo4j GraphRAG stores failure patterns and run history, but warns that *how* memory is integrated decides whether it helps.
   - The case-bundle model uses progressive-disclosure skill files and retrieves the nearest example case first.
   - PFAgent converts *verified* failures into rules.

   For ILT: a skill bank per pattern class (line/space, contacts, SRAF strategies), a failure-pattern store keyed by layout features, and retrieval of the nearest solved clip. Sources: [PDE-Agents](https://huggingface.co/papers/2606.07850), [Case-bundle](https://arxiv.org/pdf/2609.11941), [PFAgent](https://arxiv.org/html/2604.10846v1)
9. **Evolutionary program search for algorithm components.** LLaMEA uses (μ+λ) ES configs with self-debugging mutation. Ptychi-Evolve uses semantic crossover and mutation with lineage tracking (reproducibility/interpretability). Eureka adds reflection on training statistics. These map to evolving ILT loss terms, regularizers (curvature, TV), step-size schedules and SRAF heuristics — [LLaMEA](https://arxiv.org/pdf/2503.19742), [Ptychi-Evolve](https://arxiv.org/html/2603.05696)
10. **Human-in-the-loop.** LLM4PLC allows human intervention in the verification loop; PFAgent folds human deployment feedback into rule updates. In LangGraph, use `interrupt()` before promoting a new skill version or before spending expensive licensed simulation — [LLM4PLC](https://arxiv.org/html/2401.05443v1), [PFAgent](https://arxiv.org/html/2604.10846v1)
11. **Problem decomposition to bound context.** OptiMUS's connection graph handles each constraint independently. Analogue: tile or clip-level decomposition with stitching checks — [OptiMUS](https://arxiv.org/pdf/2402.10172.pdf)

### Inferences (proposed LangGraph mapping for ILT)
- **State:** task spec, current code, sim results, metric vector, skill version, budget counters.
- **Nodes:** `retrieve_skills_and_cases` → `generate_code` → `static_check` (sandbox / AST policy: no writes to evaluator or target files) → `fast_sim` → `gate(validity)` → `rigorous_sim` (licensed, queued, maybe `interrupt`) → `evaluate` → `reflect` → conditional edge (retry ≤ N | accept).
- **Outer graph:** `meta_agent_update_skills` → `validate_on_heldout` → `promote_or_rollback`. Use a LangGraph checkpointer (Postgres/SQLite) so long simulation runs survive restarts.
- **Expected weak spots,** from FEABench and MCE transfer results:
  - generalization to unseen pattern families
  - API factuality for commercial OPC tools

  Budget for curated API docs and held-out families from day one.

### Gaps
- No found paper applies a self-evolving LLM code agent to ILT/OPC itself (excluded by scope; covered elsewhere).
- No retrieved study quantifies reward-hacking incidents in industrial simulator-in-the-loop agents. The defenses above are design choices reported by papers, not measured comparisons.
- Concrete simulator-cost accounting (e.g., simulations per accepted skill update) is missing from all retrieved sources.
