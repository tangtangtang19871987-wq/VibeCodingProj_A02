# Self-evolving / code-generating LLM agents in semiconductor manufacturing and EDA (focus: LangGraph), status as of 2026-11-07

Method and verification levels. arxiv.org, alphaxiv.org and github.io pages could not be reached from this session (DNS blocked). The GitHub API was blocked for some repos (403), but raw.githubusercontent.com and GitHub search worked. Verification levels used below:
- **[V-code]**: checked directly in the repo source, README, package or dependency files (raw GitHub).
- **[V-snippet]**: taken from search-engine snippets of arXiv or official pages; the full PDF was not read.
- **[V-3rd]**: secondary or aggregator source only.
- **[U]**: unverified.

Framework labels: LangGraph / LangChain / AutoGen / custom / "coding-agent harness" (Codex CLI, Claude Code or Pi agent used as the agent runtime).

## Q1: Is there any LangGraph-based self-evolving code agent for ILT/OPC/lithography? If not, what is the nearest?

### Takeaway
No. I found no LangGraph (or LangChain) self-evolving agent for ILT, OPC, SMO or lithography in papers or on GitHub; a GitHub search for "langgraph lithography" returns 0 repos, and "langgraph OPC" returns only OPC-UA industrial or "one person company" projects. The nearest system is **VPEvolve** (arXiv 2609.32473, Sep 2026). It is a self-evolving OPC-recipe agent with a skill bank, but it runs on the **Pi coding-agent harness** (`@earendil-works/pi-coding-agent`) with a local Qwen model and Mentor/Siemens **Calibre**, not on LangGraph.

### Cited Findings
**VPEvolve: A Self-Evolving Virtual Process Engineer for Computational Lithography**
- **Paper and date.** arXiv 2609.32473, cs.AI/cs.SE, submitted 26 Sep 2026. Authors: Tianyi Li, Wenxuan Dong, Donger Luo, Nan Wang, Yanpeng Chen, Jiaqi Liu, Xinyun Zhang, Hao Geng. Hao Geng is a ShanghaiTech faculty member; the affiliation comes from my background knowledge and is not verified here. No venue is given (preprint). [V-snippet] — [arXiv abs](https://arxiv.org/abs/2609.32473)
- **Architecture.** A "Virtual Process Engineer harness" gives a *frozen* LLM four things: process manuals, layout analysis, recipe editing, and evaluation with a commercial tool. A Skill Bank stores measured engineering experience. An LLM **reflector** and **curator** turn each measured trial into evidence-linked judgments, and the **actor** retrieves these before its next trial. Feasible improvements update the retained recipe. Model weights stay fixed (no RL or fine-tuning). [V-snippet] — [arXiv abs](https://arxiv.org/abs/2609.32473)
- **Framework: NOT LangGraph.** `package.json` (named "vpevolve-pi-runtime") depends only on `@earendil-works/pi-coding-agent` 0.85.1. `pyproject.toml` describes the package as "Evidence-guided OPC recipe evolution with a Pi agent harness"; its Python dependencies are only numpy and klayout; it bundles harness files `pi/*.ts` and skills `skills/*.md`; and it vendors `ace_prompts` (prompts from ACE, Agentic Context Engineering) under their own license. Code search found no langgraph or langchain references, but search may be restricted for this repo. [V-code] — [VPEVOLVE_code package.json](https://raw.githubusercontent.com/True-Litianyi/VPEVOLVE_code/main/package.json), [pyproject.toml](https://raw.githubusercontent.com/True-Litianyi/VPEVOLVE_code/main/pyproject.toml)
- **What evolves.** An online experience store, the Skill Bank. Every run starts from an *empty* experience store plus fixed engineering guidance; nothing historical is preloaded. The OPC recipe itself is also edited, through both global edits and local rules. [V-code] — [README](https://raw.githubusercontent.com/True-Litianyi/VPEVOLVE_code/main/README.md)
- **Evaluator.** A licensed **Calibre** installation (`calibre`, `pdl_lib_mgr`) plus a lithography (optical and resist) model, served with a local Qwen model through vLLM. The repo also ships a standalone differentiable lithography simulator, but the README says it does not replace the commercial OPC correction and evaluation pipeline. Test data: 20 FreePDK45-derived GDS windows (10 Poly, 10 Metal1). [V-code] — [README](https://raw.githubusercontent.com/vpevolve/vpevolve_code_and_data/main/README.md)
- **Main results** (10 trials per case, as of 2026-09-26).
  - Mean window-maximum EPE fell from **18.294 to 5.361 nm on Poly** and from **22.052 to 15.692 nm on Metal1**. Overall it fell from 20.17 to 10.53 nm.
  - PVB was roughly unchanged (overall 6.148 to 6.210 ×10⁻³ µm).
  - All 20 full-method runs completed and passed the endpoint repeat check.
  - [V-code] — [project README](https://raw.githubusercontent.com/vpevolve/vpevolve/main/README.md), [final-results.json](https://raw.githubusercontent.com/vpevolve/vpevolve/main/assets/current/final-results.json)
- **Baselines** (same 20 cases, 10-trial budget; mean max EPE in nm, Poly / Metal1). VPEvolve is best on max EPE in both layers.

  | Method | Poly | Metal1 |
  |---|---:|---:|
  | VPEvolve (full) | **5.36** | **15.69** |
  | ReAct | 16.50 | 17.77 |
  | ACE | 16.70 | 19.92 |
  | raw history | 17.27 | 19.61 |
  | textual feedback | 17.30 | 18.97 |
  | ReasoningBank | 17.52 | 20.54 |
  | static | 17.58 | 19.88 |
  | Bayesian optimization | 17.91 | 21.77 |

  BO met the success criterion in only 6 of 20 cases. [V-code] — [final-results.json](https://raw.githubusercontent.com/vpevolve/vpevolve/main/assets/current/final-results.json)
- **Ablations** (Poly / Metal1 max EPE, nm).

  | Variant | Poly | Metal1 |
  |---|---:|---:|
  | Frozen experience | 8.08 | 16.12 |
  | without domain reflection (m1) | 6.21 | 16.28 |
  | without condition-aware revision (m2) | 5.47 | 16.33 |
  | without prospective advice (m3) | 5.87 | 16.15 |

  The full method used about 120 OPC calls and 643–652 LLM calls per layer (10 cases). [V-code] — [final-results.json](https://raw.githubusercontent.com/vpevolve/vpevolve/main/assets/current/final-results.json)
- **Other reported studies.**
  - A cross-model run where Claude, GPT, Gemini, DeepSeek, GLM and Gemma each fill all three roles.
  - 100-trial long-horizon runs: Poly02 Full and Frozen, Metal29 Full; Metal29 Frozen ended at trial 57.
  - A paired ACE-vs-VPEvolve experience study.
  - [V-code] — [project README](https://raw.githubusercontent.com/vpevolve/vpevolve/main/README.md)
- **Open source.** Apache-2.0 code, simulator and the 20 GDS windows. Calibre binaries, licenses and litho models are not distributed. Repos:
  - True-Litianyi/VPEVOLVE_code (created 2026-09-26)
  - vpevolve/vpevolve_code_and_data (created 2026-09-24)
  - project sites True-Litianyi/VPEVOLVE and vpevolve/vpevolve
  - [V-code] — [GitHub search / README](https://raw.githubusercontent.com/True-Litianyi/VPEVOLVE/main/README.md)

**Other OPC/ILT entries**
- **Intelligent OPC Engineer Assistant for Semiconductor Manufacturing** (arXiv 2408.12775, 23 Aug 2024). Authors: Guojin Chen, Haoyu Yang, Bei Yu, Haoxing Ren (CUHK and NVIDIA).
  - Method: RL (PPO) searches OPC recipes against an EPE+PVB loss, then a customized multi-modal LLM agent system summarizes the results into recipes.
  - Framework: not stated in the sources found.
  - Results: secondary summaries conflict. One gives 12% EPE-count and 24% EPE-distance reduction for RL; another gives 13%/15% for RL and 8%/12% for the LLM-generated recipe at baseline runtime.
  - Self-improvement is RL, not agent memory.
  - [V-snippet]/[V-3rd] — [arXiv](https://arxiv.org/abs/2408.12775), [Moonlight review](https://www.themoonlight.io/review/intelligent-opc-engineer-assistant-for-semiconductor-manufacturing)
- **NanWang-EE / "MASK / Agent Lab"** (GitHub, created 2026-10-07; Nan Wang is also a VPEvolve co-author).
  - Pixel/ILT-style mask optimization with an agent loop: observe → propose → simulate → accept/rollback, 15 proposal rounds.
  - Evaluator: the OpenILT (ASICON 2023) evaluator; EPE counted at a 15 nm threshold, plus L2 and PVB with a PVB ceiling of 1.6× the target's.
  - Models are labelled "Astra 6", "Sol 6", "Sol 5.6" (unclear what these are). Compared against OpenILT-paper baselines on case1/case2.
  - Framework not stated; it is a results website only, with no agent code. [V-code] — [README](https://raw.githubusercontent.com/NanWang-EE/agent-mask-optimization-site/main/README.md)
- **LithoDreamer** (ICML 2026 poster). A physics-informed *world model* for multi-stage computational lithography (layout → mask → resist → ADI), used for forward evolution and inverse planning. **Not an LLM agent.** [V-snippet] — [ICML page](https://icml.cc/virtual/2026/poster/63279)
- **Adjacent script-generation work.**
  - AST-guided LLM SVRF code synthesis (arXiv 2507.00352, 2025): RAG plus AST embeddings; code not released.
  - Rule2DRC (arXiv 2605.15669, 2026): benchmark for LLM agents synthesizing DRC scripts, with execution-guided tests.
  - Neither is an OPC agent. [V-snippet] — [2507.00352](https://arxiv.org/pdf/2507.00352), [2605.15669](https://arxiv.org/pdf/2605.15669)
- **Non-LLM ILT context.** OpenILT (open-source ILT framework, ASICON 2023), LithoBench (NeurIPS 2023 D&B, more than 120k tiles), MaskOpt dataset (arXiv 2512.20655, built with OpenILT), generative-RL ILT (arXiv 2602.19027, Feb 2026). [V-snippet] — [OpenILT PDF](https://www.cse.cuhk.edu.hk/~byu/papers/C179-ASICON2023-OpenILT.pdf), [LithoBench](https://proceedings.neurips.cc/paper_files/paper/2023/file/604b9fa9e1c16284e6517d923cf9ff20-Paper-Datasets_and_Benchmarks.pdf), [MaskOpt](https://arxiv.org/html/2512.20655v1), [2602.19027](https://arxiv.org/html/2602.19027v1)

### Inferences
- The leading lithography self-evolution work (VPEvolve) runs on a coding-agent harness plus a file-based skill bank, not a graph orchestrator. Its actor → evaluate (Calibre) → reflector → curator → skill-bank loop could be rebuilt as a LangGraph StateGraph with a persistent store, but nobody has published that.
- VPEvolve's advantage is mainly on worst-case (max) EPE; mean EPE and PVB barely move. Its gains come from online, evidence-linked experience: Frozen loses about 2.7 nm on Poly.
- For an open replication without Calibre, the natural evaluators are OpenILT, LithoBench and the VPEvolve standalone simulator. The NanWang-EE OpenILT agent loop shows this is feasible.

### Gaps
- I could not read the VPEvolve PDF. Exact LLM role assignment, the skill-bank schema, cost and token figures, and the cross-model table values are not verified.
- The VPEvolve venue (if any) is unknown.
- "Astra/Sol" model identities and the framework behind the NanWang-EE mask-agent experiments are unknown.
- I found no SMO-specific or lithography-simulation-code-generating LLM agent; searches returned none.
- I found no 知乎 (Zhihu) or 机器之心 (Synced) coverage. Those sites were not reachable or searched effectively.

## Q2: Which EDA/semiconductor agents use LangGraph, and what self-improvement mechanisms do they use?

### Takeaway
The LangGraph-based EDA systems I could confirm are mostly flow orchestrators or assistants (ORAssistant, Meta's CoreSmith, SiliconCrew, EDA Pilot, smaller hobby repos). Their "self-improvement" is limited to in-loop diagnose/fix/retry (reflection on tool errors). None keeps a persistent cross-run skill bank or evolves code over time. The genuinely self-evolving EDA systems of 2026 run on Codex CLI or Claude Code harnesses, or on custom or AutoGen code:
- code evolution: GR-Evolve, GoalEvolve, VPR-Evolve
- skill or memory evolution: EvoDRC, VPEvolve, AnalogAgent

### Cited Findings
**Confirmed LangGraph**
- **ORAssistant** (The-OpenROAD-Project, repo created 2024-06-05, 48 stars).
  - Architecture: an OpenROAD chatbot whose backend `retriever_graph.py` builds a `langgraph.graph.StateGraph(AgentState)`. A `classify` node routes to RAG, MCP or architecture-info tools. LangChain chat models: Vertex AI, Gemini, Ollama.
  - Self-improvement: none (RAG plus human-evaluation interface).
  - Open source. [V-code] — [README](https://raw.githubusercontent.com/The-OpenROAD-Project/ORAssistant/master/README.md), [retriever_graph.py](https://raw.githubusercontent.com/The-OpenROAD-Project/ORAssistant/master/backend/src/agents/retriever_graph.py)
- **CoreSmith** (facebookexperimental/coresmith, created 2026-04-13, MIT, 51 stars).
  - Architecture: "uses LangGraph to drive the full RTL-to-GDS flow": architecture/PRD → microarchitecture → LLM RTL generation → cocotb testbenches + Verilator → Yosys (Sky130) → OpenROAD/Magic/netgen place-and-route, DRC and LVS. A debug agent diagnoses failures and retries with corrective constraints. Daemon with human-review "parks"; driven from Claude Code or Codex.
  - Self-improvement: diagnose-and-retry only.
  - No quantitative results found. [V-code] — [README](https://raw.githubusercontent.com/facebookexperimental/coresmith/main/README.md)
- **SiliconCrew** (naman-ranka/siliconcrew, 2025-11 → 2026-09, MIT).
  - Architecture: LangGraph agent + MCP server. Spec (YAML) → RTL → self-checking testbench → waveform-based (VCD) debugging → OpenROAD (Sky130) to GDSII.
  - Results: on NVIDIA's CVDP (92 agentic no-commercial problems), 46.7% (Mar 2026) rising to **65.2% (60/92) leak-gated (Jul 2026)**, with Claude Sonnet 5 at pass@1. An earlier 68.5% was retired after a grader-leak audit.
  - Self-improvement: iterative fix-verify cycles only. [V-code] — [README](https://raw.githubusercontent.com/naman-ranka/siliconcrew/main/README.md)
- **EDA Pilot AI** (NileshModlier/EDA-Pilot-Agentic-AI, 2026-10, MIT, personal project).
  - Architecture: a LangGraph agent and a guarded MCP tool layer search ORFS settings for the smallest clock that signs off (Sky130HD; gcd, aes, ibex).
  - Results, best passing clock vs random search: gcd 2.867 vs 4.113 ns; aes 4.822 vs 6.261 ns; ibex 9.000 vs 10.531 ns. That is 14.5–30.3% tighter, at a cost of 7–23% more area and 30–71% more power. Signoff rates were similar overall: agent 7/19, random 11/30.
  - Self-improvement: none beyond the in-run search loop. [V-code] — [README](https://raw.githubusercontent.com/NileshModlier/EDA-Pilot-Agentic-AI/main/README.md)
- **Smaller LangGraph repos (from GitHub repo descriptions only).**
  - agentic-verilog-testbench (Sawaiz-zip): LangGraph multi-agent testbench generation with Pyverilog static checks and repair; self-reports 93% fault detection.
  - ChipMind (isakshay007; numaanahmed3110): RAG plus compiler-in-the-loop Verilog.
  - Agentic-RTL-Assistant: LangGraph + GraphRAG.
  - EDA-Log-Analyser-AI: LangGraph + FAISS + MCP.
  - [V-code: description only] — [GitHub search "langgraph verilog"](https://github.com/search?q=langgraph+verilog&type=repositories)
- **DAC hackathon template.** BryceNeil/DAC_Hackathon ships `solutions/your_agent_langgraph.py`, which suggests a DAC agent hackathon offered a LangGraph starter. [V-code: path only] — [GitHub code search](https://github.com/BryceNeil/DAC_Hackathon)

**Self-evolving EDA systems, non-LangGraph** (all 2026 unless noted)
- **GR-Evolve** (arXiv 2604.22234, 24 Apr 2026). Authors: Taizun Jafri and Vidya A. Chhabria (ASU); long version of an ICCAD 2026 submission.
  - Architecture: an agentic LLM edits OpenROAD global-router C++ source using QoR feedback, in a genetic loop.
  - Framework: **OpenAI Codex CLI** (`GeneticRunCodex.sh`, per-design `AGENTS.md`, Docker).
  - Results: up to **8.72% post-detailed-route wirelength reduction** vs baseline routers, across 7 designs and 3 tech nodes.
  - Open source (ASU-VDA-Lab/GR-Evolve). [V-snippet + V-code] — [arXiv](https://arxiv.org/abs/2604.22234), [README](https://raw.githubusercontent.com/ASU-VDA-Lab/GR-Evolve/main/README.md)
- **GoalEvolve** (arXiv 2608.16733, Aug 2026; CODA-Team/GoalEvolve, created 2026-07-29).
  - Architecture: goal-driven evolution of bounded OpenROAD C++ algorithms. Pipeline: frozen QoR contract → bottleneck diagnosis plus **mechanism-card retrieval** → Teacher plans and Student executes (**Codex CLI 0.146.0** workers) → isolated OpenROAD builds → post-placement optimization and global routing → QoR and validity checks → "EPD evidence" memory and promotion.
  - Benchmarks: ASAP7 (e.g., aes_cipher_top).
  - Quantitative results not retrieved. [V-code] — [README](https://raw.githubusercontent.com/CODA-Team/GoalEvolve/main/README.md), [arXiv html](https://arxiv.org/html/2608.16733)
- **VPR-Evolve** (arXiv 2607.24998, Jul 2026). Multi-agent algorithm evolution for FPGA place-and-route (VPR); repo ASU-VDA-Lab/VPR-Evolve. Details not retrieved. [V-snippet] — [arXiv](https://arxiv.org/html/2607.24998v1)
- **EvoDRC** (ASU-VDA-Lab, repo 2026-07-18).
  - Architecture: **skill-evolution** for agentic block-level DRC repair. Layer-specific repair skills are initialized from knowledge distilled from an unrelated design, then evolved from traceable repair experience on the target design.
  - Framework: **Claude Code** (claude-sonnet-4-6). Ablations: no prior experience, frozen experience, whole-design repair.
  - Evaluator: DAC26_DRC_Benchmark (7 blocks).
  - Numbers not retrieved. [V-code] — [README](https://raw.githubusercontent.com/ASU-VDA-Lab/EvoDRC/main/README.md)
- **ResizerAgent** (ASU-VDA-Lab, 2026-05). Closed-loop timing optimization driving OpenROAD Resizer `repair_timing`. Framework: **Claude Code CLI** (Opus 4.7 planner and selector, Sonnet 4.6 executor); ASAP7 and NanGate45. [V-code] — [README](https://raw.githubusercontent.com/ASU-VDA-Lab/ResizerAgent/main/README.md)
- **AgenticPD** (arXiv 2607.04758). Stage-aware agentic framework for physical-design QoR optimization; framework not retrieved. [V-snippet] — [arXiv](https://arxiv.org/pdf/2607.04758)
- **VerilogCoder** (NVIDIA, arXiv 2408.08927, Aug 2024; AAAI 2025 per my background knowledge, not verified).
  - Framework: **AutoGen**, confirmed by the paper snippet and 68 code hits for "autogen" in the repo.
  - Architecture: graph-based task planning plus an AST-based waveform-tracing tool.
  - Results: **94.2%** pass rate on VerilogEval-Human v2 (156 tasks) with GPT-4 Turbo, 33.9% above the prior state of the art; 67.3% with Llama3.
  - Self-improvement: none persistent.
  - Open source (NVlabs/VerilogCoder). [V-snippet + V-code] — [arXiv](https://arxiv.org/html/2408.08927v2), [README](https://raw.githubusercontent.com/NVlabs/VerilogCoder/main/README.md)
- **MCP4EDA** (arXiv 2507.19570, 2025; NellyW8/MCP4EDA, 112 stars).
  - Architecture: an MCP server exposing Yosys, Icarus, GTKWave, OpenLane and KLayout to Claude Desktop or Cursor, with "backend-aware synthesis optimization".
  - Framework: MCP, no orchestration framework.
  - Numbers not retrieved. [V-code] — [README](https://raw.githubusercontent.com/NellyW8/MCP4EDA/main/README.md)
- **AnalogCoder** (AAAI 2025 Oral; laiyao1/AnalogCoder, 211 stars). Training-free code generation for analog circuits. **AnalogCoder-Pro** (TCAD 2026) adds multimodal generation and optimization. Framework: custom. [V-code: repo descriptions] — [GitHub](https://github.com/laiyao1/AnalogCoderPro)
- **AnalogAgent** (arXiv 2603.23910, 2026).
  - Architecture: multi-agent with **self-evolving memory** for analog design.
  - Result: about 17 s to the first correct circuit with learned knowledge, vs about 7 min for AnalogCoder-Pro.
  - Framework not retrieved. [V-snippet] — [alphaxiv](https://www.alphaxiv.org/abs/2603.23910)
- **AnalogGym-Opt** (IEEE TCAD 2026). GRPO (RL)-based multi-objective analog sizing with ngspice and Sky130, exposed through Claude Code skills and an MCP server. [V-code: description] — [GitHub](https://github.com/Computing-Intelligent-Decision-Team/AnalogGym-Opt)
- **LayoutCopilot** (arXiv 2406.18873, 2024; Peking University). Multi-agent interactive analog layout; natural language to layout-tool commands. It cites AutoGen, but which framework it actually uses is unconfirmed. [V-snippet] — [arXiv](https://arxiv.org/abs/2406.18873v2)
- **AgenticTCAD** (arXiv 2512.23742; v1 26 Dec 2025, v2 13 Jan 2026; DATE 2026). Authors: Guangxi Fan et al. (XJTLU listed).
  - Architecture: multi-agent; a fine-tuned TCAD code-generation model plus a commercial reasoning model; open TCAD dataset (guangxifan/llm4tcad_flow, Sentaurus-style SDE scripts).
  - Result: 2 nm nanosheet FET reached IRDS-2024 specs in **4.2 h vs 7.1 days** for human experts.
  - Framework not stated in snippets. [V-snippet + V-code] — [arXiv](https://arxiv.org/html/2512.23742v1), [llm4tcad_flow](https://raw.githubusercontent.com/guangxifan/llm4tcad_flow/main/README.md)
- **czf-mq/agentic-tcad** (2026-08, open source; a different project with the same name).
  - Architecture: DeepSeek V4-Flash optimization loop over Gmsh and DEVSIM 100 nm nMOS; OpenAI SDK, custom loop.
  - Results (3 trials × 25 evaluations): first feasible design at 5/4/5 evaluations, vs 10/11/13 for constrained BO; random search and GP-EI succeeded in only 1/3 trials. The authors caution the sample is small. [V-code] — [README](https://raw.githubusercontent.com/czf-mq/agentic-tcad/main/README.md)

**Commercial**
- Commercial agentic EDA, 2026. Frameworks are not disclosed for any of these.
  - Synopsys **AgentEngineer**: "Level-4" multi-agent workflow.
  - Cadence **ChipStack AI Super Agent**: extended to "Level-5" at Computex 2026.
  - Siemens **Fuse EDA AI Agent**: "self-verification" against deterministic engines; the Questa One Agentic Toolkit works with Claude Code and Cursor.
  - NVIDIA partnered with all three (Mar 2026).
  - [V-3rd] — [Tom's Hardware](https://www.tomshardware.com/tech-industry/semiconductors/the-state-of-agentic-ai-in-chip-design-tools-in-2026-cadence-synopsys-and-siemens-all-pitch-autonomous-engineers), [Futurum](https://www.futurumgroup.com/insights/cadence-and-synopsys-accelerate-agentic-eda-race-at-computex)
- **ChipAgents** (Alpha Design AI, founded 2024). Agents for RTL design and verification. A third-party summary says it uses a task graph driving VCS and Xcelium; framework undisclosed. [V-3rd] — [SemiEngineering](https://semiengineering.com/entities/alpha-design-ai-chipagents/)

### Inferences
- In this domain LangGraph is used mainly for **deterministic, auditable flow orchestration**: stage gates, human-review parks, tool fix loops (CoreSmith, SiliconCrew, EDA Pilot), and routing (ORAssistant).
- 2026's "self-evolving" research in EDA has largely adopted **coding-agent CLIs** as the runtime (Codex: GR-Evolve, GoalEvolve; Claude Code: EvoDRC, ResizerAgent; Pi: VPEvolve). Self-improvement in these systems lives in files: AGENTS.md, skills/*.md, mechanism cards, evidence logs.
- Self-improvement mechanisms seen:
  - **source-code evolution** of EDA C++ (GR-Evolve, GoalEvolve, VPR-Evolve)
  - **skill or experience banks** (VPEvolve, EvoDRC, AnalogAgent memory)
  - **RL** (Intelligent OPC Engineer with PPO; AnalogGym-Opt with GRPO)
  - **fine-tuning** (AgenticTCAD's TCAD code model)
- A LangGraph re-implementation of a VPEvolve/EvoDRC-style loop (StateGraph + checkpointer + long-term Store as the skill bank) would be novel in lithography as of Nov 2026, as far as these searches show.

### Gaps
- Framework details for AgenticTCAD, LayoutCopilot, AnalogAgent, AgenticPD and VPR-Evolve could not be confirmed because arXiv full text was blocked.
- Quantitative results for GoalEvolve, EvoDRC, MCP4EDA and VPR-Evolve were not retrieved.
- The DAC hackathon's details (year, organizer) behind the LangGraph template are unknown.
- Vendor frameworks (Synopsys, Cadence, Siemens, ChipAgents) are not public.

## Q3: What evaluators/simulators and results are reported?

### Takeaway
Lithography work uses commercial Calibre (VPEvolve) or open OpenILT and LithoBench evaluators. Physical-design agents almost all use OpenROAD/ORFS (Sky130, ASAP7, NanGate45). RTL agents use VerilogEval v2 and CVDP. TCAD agents use Sentaurus-style SDE scripts or DEVSIM. Reported gains are mostly single-paper, small-sample results (10–20 cases, 3–7 designs).

### Cited Findings
| System | Domain | Framework | Evaluator / benchmark | Headline result | Open | Verif. |
|---|---|---|---|---|---|---|
| VPEvolve (2609.32473, 2026-09) | OPC recipe | Pi coding agent + local Qwen | Calibre + litho model; 20 FreePDK45 windows | max EPE 18.29→5.36 nm (Poly), 22.05→15.69 nm (M1); beats ReAct, ACE, ReasoningBank, BO | Yes (Apache-2.0) | V-code — [results](https://raw.githubusercontent.com/vpevolve/vpevolve/main/assets/current/final-results.json) |
| Intelligent OPC Engineer (2408.12775, 2024-08) | OPC recipe | RL (PPO) + MLLM agents, framework n/a | commercial OPC engine (unspecified) | ~8–12% EPE-count / 12–24% EPE-distance reduction (sources conflict) | not found | V-3rd — [Moonlight](https://www.themoonlight.io/review/intelligent-opc-engineer-assistant-for-semiconductor-manufacturing) |
| MASK/Agent Lab (2026-10) | ILT mask | unknown | OpenILT evaluator, 2 cases | EPE/PVB/L2 curves over 15 rounds; no headline number | site only | V-code — [README](https://raw.githubusercontent.com/NanWang-EE/agent-mask-optimization-site/main/README.md) |
| GR-Evolve (2604.22234, 2026-04) | global routing code | Codex CLI | OpenROAD/ORFS, 7 designs × 3 nodes | up to 8.72% post-DR wirelength reduction | Yes | V-snippet — [arXiv](https://arxiv.org/abs/2604.22234) |
| GoalEvolve (2608.16733, 2026-08) | PD algorithm code | Codex CLI Teacher/Student | OpenROAD, ASAP7 | not retrieved | Yes | V-code — [README](https://raw.githubusercontent.com/CODA-Team/GoalEvolve/main/README.md) |
| EvoDRC (2026-07) | DRC repair skills | Claude Code | DAC26_DRC_Benchmark | not retrieved | Yes | V-code — [README](https://raw.githubusercontent.com/ASU-VDA-Lab/EvoDRC/main/README.md) |
| EDA Pilot (2026-10) | timing closure | **LangGraph** + MCP | ORFS Sky130HD | 14.5–30.3% tighter passing clock than random search | Yes | V-code — [README](https://raw.githubusercontent.com/NileshModlier/EDA-Pilot-Agentic-AI/main/README.md) |
| SiliconCrew (2025-11→2026-09) | RTL→GDS | **LangGraph** + MCP | CVDP (92), OpenROAD | 65.2% leak-gated pass@1 | Yes | V-code — [README](https://raw.githubusercontent.com/naman-ranka/siliconcrew/main/README.md) |
| CoreSmith (Meta, 2026-04) | prompt→GDS | **LangGraph** | Verilator, Yosys, OpenROAD, Magic, netgen | none reported | Yes (MIT) | V-code — [README](https://raw.githubusercontent.com/facebookexperimental/coresmith/main/README.md) |
| ORAssistant (2024-06→) | OpenROAD Q&A | **LangGraph** + LangChain | human eval interface | n/a | Yes | V-code — [code](https://raw.githubusercontent.com/The-OpenROAD-Project/ORAssistant/master/backend/src/agents/retriever_graph.py) |
| VerilogCoder (2408.08927) | RTL | AutoGen | VerilogEval-Human v2 | 94.2% (GPT-4T), 67.3% (Llama3) | Yes | V-snippet — [arXiv](https://arxiv.org/html/2408.08927v2) |
| AgenticTCAD (2512.23742, DATE'26) | TCAD | multi-agent, framework n/a | Sentaurus-style TCAD; 2 nm NS-FET | IRDS-2024 spec in 4.2 h vs 7.1 days | dataset yes | V-snippet — [arXiv](https://arxiv.org/html/2512.23742v1) |
| czf-mq/agentic-tcad (2026-08) | TCAD | custom (OpenAI SDK, DeepSeek) | DEVSIM + Gmsh | first feasible design in ~5 evaluations vs ~11 for constrained BO | Yes | V-code — [README](https://raw.githubusercontent.com/czf-mq/agentic-tcad/main/README.md) |
| AnalogAgent (2603.23910) | analog | multi-agent + self-evolving memory | SPICE (presumed) | ~17 s vs ~7 min (AnalogCoder-Pro) to first correct circuit | ? | V-snippet — [alphaxiv](https://www.alphaxiv.org/abs/2603.23910) |

### Inferences
- In lithography, worst-case EPE under a fixed trial budget (about 10 Calibre runs per case) is the metric that self-evolving experience improves most clearly. BO and memory baselines (ReasoningBank, ACE) barely beat the starting recipe R0 in VPEvolve's setup.
- Open-source replications are blocked by commercial-tool dependence: Calibre for OPC, Sentaurus for TCAD. OpenILT, LithoBench and DEVSIM are the open substitutes.

### Gaps
- No independent replication found for any result listed.
- I did not find lithography-agent papers at SPIE Advanced Lithography 2025/2026; this was not searched successfully.
- Process-recipe (etch/deposition) LLM agents and fab-side LangGraph systems: none found beyond hobby repos (e.g., orcunku/lithography-ops-ai, "anomaly detection, RAG, agents").
