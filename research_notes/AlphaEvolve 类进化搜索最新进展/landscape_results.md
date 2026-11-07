# Landscape and outcomes of LLM-driven evolutionary/agentic discovery systems (AlphaEvolve-like), 2025 to Nov 2026

Scope: this covers competing labs, concrete results, benchmarks, critiques and trends. It leaves out the open-source framework catalog and DeepMind's own AlphaEvolve timeline. Research date: 2026-11-07.

Method note: arxiv.org and the-decoder.com could not be reached from this session (DNS blocked), so I could not read arXiv full texts. Most arXiv facts below come from search-engine snippets of arXiv/alphaxiv/HTML pages. Numbers are the authors' own claims unless marked otherwise. I verified one page directly: the Tao Erdős wiki "Notable cases" page on GitHub.

## Q1. Which notable discoveries in 2025-2026 used AlphaEvolve-style or LLM-agentic methods, who made them, and are they verified?

### Takeaway
Real, checkable results now exist from many groups outside DeepMind:
- Erdős problems: OpenAI GPT-5.x, with Tao-tracked verification.
- Kissing-number lower bounds: Alibaba/Zhejiang University "Qiushi Engine", human+AI preprints, Together AI's EinsteinArena.
- Small packing and analysis-constant improvements: Sakana ShinkaEvolve, TTT-Discover, Baidu LoongFlow.
- Systems heuristics: UC Berkeley ADRS/OpenEvolve.

Most results are small numeric improvements on AlphaEvolve's problem set, or self-reported preprints. Erdős-problem results have the strongest community verification, but several early claims turned out to be literature rediscovery.

### Cited Findings

**OpenAI / GPT-5 math (the Erdős controversy and later genuine results)**
- 2025-08: Sébastien Bubeck reported that GPT-5 Pro improved a convex-optimization step-size bound from 1/L to 1.5/L in about 17 minutes, and said he checked the proof. Humans later closed the gap at 1.75/L, so the AI result was not the final answer. — [36Kr](https://eu.36kr.com/en/p/3432486013259397); [Medium summary](https://cloudperceptor.medium.com/gpt-5-just-casually-did-new-mathematics-e75e78b38424)
- 2025-10-12 to ~10-18: Bubeck posted that "GPT-5-pro is superhuman at literature search", and that it had "solved" Erdős problems. OpenAI VP Kevin Weil then posted that "GPT-5 solved 10 unsolved Erdős problems and made progress on 11". He deleted the post after Thomas Bloom (maintainer of erdosproblems.com) said GPT-5 had only found existing references that he "personally was unaware of". — [eWeek](https://www.eweek.com/news/openai-math-hype/); [X thread quoting Tao](https://x.com/deredleritt3r/status/1979250915610890750)
- At the time, Tao said the most productive near-term AI use in mathematics is literature review and similar routine work, not solving open problems. — [X thread quoting Tao](https://x.com/deredleritt3r/status/1979250915610890750)
- 2025-11: OpenAI's paper "Early science acceleration experiments with GPT-5" (arXiv 2511.16072) describes the Erdős work as literature search. For each problem listed as open, GPT-5 was asked to "locate a solution if it existed, and otherwise to report significant partial progress". — [OpenAI PDF](https://cdn.openai.com/pdf/4a25f921-e4e0-479a-9b38-5367b47e8fd0/early-science-acceleration-experiments-with-gpt-5.pdf); [arXiv 2511.16072](https://arxiv.org/pdf/2511.16072)
- 2025-09: "Mathematical research with GPT-5: a Malliavin–Stein experiment" (arXiv 2509.03065) and the "Gödel Test" paper (arXiv 2509.18383, easy conjectures) are early academic probes of GPT-5 on research math. — [arXiv 2509.03065](https://arxiv.org/html/2509.03065v1); [arXiv 2509.18383](https://arxiv.org/pdf/2509.18383)
- 2026-01: The Tao-maintained wiki calls Erdős #728 the "first autonomous and nontrivial solution to an Erdős problem by AI systems". It records a general result that also settles #729 and #401. Press coverage attributes it to GPT-5.2 Pro. — [teorth wiki: Notable cases](https://github.com/teorth/erdosproblems/wiki/Notable-cases-of-AI-contributions-to-Erd%C5%91s-problems); [The Decoder](https://the-decoder.com/terence-tao-says-gpt-5-2-pro-cracked-an-erdos-problem-but-warns-the-win-says-more-about-speed-than-difficulty/)
- Tao's caveat, as reported: the win "says more about speed than difficulty". He estimated that only about 1–2% of open problems are simple enough for current AI tools with minimal human help. I took this from a search snippet; I could not fetch the article. — [The Decoder](https://the-decoder.com/terence-tao-says-gpt-5-2-pro-cracked-an-erdos-problem-but-warns-the-win-says-more-about-speed-than-difficulty/)
- Wiki table examples: GPT-5.2 Pro full solution to #543 (2026-01-21); Aletheia (Google DeepMind) full solution to #397 (2026-02-02). — [teorth wiki: AI contributions](https://github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erd%C5%91s-problems)
- Later notable cases, as listed on the wiki:
  - #1026 (2025-12): solved with "various forms of AI assistance", with a strengthened conclusion.
  - #1196 (2026-04): solved with a new technique that also resolves #1217, #164 and two other conjectures, and inspired a solution to #858.
  - #90 (2026-05): "resolves a major open problem with prior widespread expert attention" and also disproves #92.
  - The wiki text does not name the AI systems for these cases. — [teorth wiki: Notable cases](https://github.com/teorth/erdosproblems/wiki/Notable-cases-of-AI-contributions-to-Erd%C5%91s-problems)
- The wiki is frozen, with data as of 2026-06-30. It labels entries full / partial / incorrect / unverified, and separates AI-alone from AI+literature and AI+human contributions. — [teorth wiki](https://github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erd%C5%91s-problems)
- Outside count from the frozen tables: 69 problems have at least one entry where AI played the main role and the outcome is "full solution". The wiki itself warns against reading this as a score. This is a secondary aggregator. — [Papex (Oct 2026)](https://papex.org/blog/how-many-erdos-problems-has-ai-solved); [Cairn Commons](https://cairn-commons.com/guides/erdos-problems-solved-by-ai)
- Tao's overall stance, as quoted: these contributions do not meet the "hyped up goal" of AI autonomously solving major open problems, but they "cannot all be dismissed as inconsequential trickery". — [Cairn Commons](https://cairn-commons.com/guides/erdos-problems-solved-by-ai); [Mathstodon](https://mathstodon.xyz/@tao/115818402639190439)
- The erdosproblems.com forum has a thread on potential academic-misconduct issues from undisclosed AI use. One secondary source says the site stopped showing which problems are solved on 2026-10-06. I found this only in that single source, so it is unconfirmed. — [erdosproblems forum: AI Contributions](https://www.erdosproblems.com/forum/thread/AI%20Contributions); [Cairn Commons](https://cairn-commons.com/guides/erdos-problems-solved-by-ai)

**Kissing numbers (2026)**
- 2026-03: New lower bound for the kissing number in dimension 19 (arXiv 2603.10425). GPT-5.4 Pro was used in discovering the construction and in revising the write-up. — [arXiv 2603.10425](https://arxiv.org/pdf/2603.10425)
- ~2026-04: AI agents on Together AI's "EinsteinArena" platform raised the dimension-11 lower bound to 604. This is from crypto-news secondary coverage. — [KuCoin news flash](https://www.kucoin.com/news/flash/ai-agents-collaborate-to-solve-11d-kissing-number-problem-pushing-lower-bound-to-604)
- 2026-09-26/27: "Qiushi Engine" (Oxelra-AI; search coverage attributes it to Zhejiang University with Alibaba Cloud, shown at the Apsara 2026 conference) ran a 72-hour autonomous, livestreamed research session.
  - First release: new kissing-number lower bounds in ten dimensions (32–39, 43, 45).
  - Follow-up: extended to nineteen dimensions (25, 27, 32–39, 43, 45, 49–55).
  - Example: dimension 32 goes to 347,584, against a published 346,944.
  - The repo provides exact constructions and reproducible verification.
  - Status: self-reported, not peer-reviewed.
  - Sources: [GitHub repo](https://github.com/Oxelra-AI/Qiushi-Engine-Kissing-Number-Research); [release apsara-2026-09-26](https://github.com/Oxelra-AI/Qiushi-Engine-Kissing-Number-Research/releases/tag/apsara-2026-09-26); [complete-study release](https://github.com/Oxelra-AI/Qiushi-Engine-Kissing-Number-Research/releases/tag/complete-study-2026-09-27); [arXiv 2609.35051 "Large-Scale Autonomous Discovery of Kissing Number Constructions"](https://arxiv.org/pdf/2609.35051)
- 2026-09: "New lower bounds for kissing numbers in dimensions 25–31" (arXiv 2609.21591). — [arXiv 2609.21591](https://arxiv.org/pdf/2609.21591)
- 2026-11: Q. Lin, "New lower bounds for kissing numbers in dimensions 32–35 and 37–39" (arXiv 2611.03682). The paper says it relied heavily on Claude (Opus 5.5) via Claude Code. These dimensions overlap with Qiushi's, so priority and comparison need checking. — [arXiv 2611.03682](https://arxiv.org/html/2611.03682)

**Packing and analysis constants (non-DeepMind systems improving AlphaEvolve's problem set)**
- 2025-09: Sakana AI's ShinkaEvolve (arXiv 2509.19349) reported a new best 26-circle packing (sum of radii ≈ 2.635983) in about 150 evaluations, versus AlphaEvolve's 2.63586276. The margin depends on numerical tolerance: ShinkaEvolve uses an absolute tolerance of 1e-7, while AlphaEvolve uses zero tolerance. — [ShinkaEvolve arXiv HTML](https://arxiv.org/html/2509.19349v1); [kiadev summary](https://kiadev.net/news/2025-09-26-shinkaevolve-llm-program-evolution-sample-efficient); [ThetaEvolve arXiv 2511.23473](https://arxiv.org/pdf/2511.23473)
- 2025-11: ThetaEvolve ("Test-time learning on open problems", arXiv 2511.23473) does RL at test time on open problems. It is cited for pushing the circle-packing best value to 2.635983283. — [arXiv 2511.23473](https://arxiv.org/pdf/2511.23473)
- 2026-01: TTT-Discover ("Learning to Discover at Test Time", arXiv 2601.16175). The team is Stanford/NVIDIA et al., with a blog post on the UC Berkeley Sky ADRS site. It keeps training the LLM on the single test problem.
  - Erdős minimum-overlap upper bound: 0.380876, versus AlphaEvolve's 0.380924 (a 600-piece versus 95-piece step function), reached with gpt-oss-120b.
  - Qwen3-8B reached 0.380932.
  - AtCoder Heuristic Contest scores: AHC039 567,062; AHC058 848,414,228.
  - These are authors' claims. — [arXiv 2601.16175](https://arxiv.org/html/2601.16175v1); [project page](https://test-time-training.github.io/discover/); [ADRS blog](https://ucbskyadrs.github.io/blog/ttt/)
- 2025-12: Baidu (百度百舸) LoongFlow (arXiv 2512.24077) uses a Plan-Execute-Summarize directed-evolution loop.
  - Claimed: beats the best known human results on 11 of the Tao/AlphaEvolve problems and beats AlphaEvolve on 7.
  - Claimed: 26-circle packing 2.635 versus a human-best 2.634.
  - Claimed: 14 Kaggle gold medals on MLE-style tasks.
  - All self-reported. — [arXiv 2512.24077](https://arxiv.org/abs/2512.24077); [GitHub](https://github.com/baidu-baige/LoongFlow); [HF blog](https://huggingface.co/blog/FreshmanD/loongflow-intro); [Zhihu](https://zhuanlan.zhihu.com/p/1995168652484428709)
- 2026-02: ImprovEvolve (arXiv 2602.10233) combines basin-hopping with LLM-guided evolution, applied to combinatorial geometry and spherical codes. Its affiliation is not confirmed. — [arXiv 2602.10233](https://arxiv.org/pdf/2602.10233)
- 2026: A peer-reviewed version of the AlphaEvolve-at-scale math study ("Mathematical discovery and exploration can be done at scale") appears in PubMed. This is DeepMind/Tao work; it is listed only as the reference point the other groups compete against. — [PubMed 42814542](https://pubmed.ncbi.nlm.nih.gov/42814542/)

**Systems / scheduling (UC Berkeley Sky lab "ADRS", built on OpenEvolve)**
- 2025-10, "Barbarians at the Gate" (arXiv 2510.06189), and 2025-12, "Let the Barbarians In" (arXiv 2512.14806; SIGOPS blog 2026). Claimed results:
  - Spot-instance multi-region scheduling: 26% better than a hand-tuned baseline; an earlier version reports 35% greater savings.
  - Mixture-of-Experts expert-placement / load-balancing: 13× faster than the best known baseline; an earlier version reports 5×.
  - LLM-SQL request reordering: 3× runtime speedup.
  - Offline transaction scheduling: 34% lower makespan than SMF; later reported as 60%.
  - Across frameworks, OpenEvolve gave the best solution in 9 of 20 cases (2 models × 10 tasks).
  - Numbers changed between versions. — [arXiv 2510.06189](https://arxiv.org/html/2510.06189v3); [arXiv 2512.14806](https://arxiv.org/pdf/2512.14806); [SIGOPS blog](https://www.sigops.org/2026/let-the-barbarians-in-how-ai-can-accelerate-systems-performance-research/)
- 2026-04: "AI-Driven Research for Databases" (arXiv 2604.06566) extends ADRS to databases. — [arXiv 2604.06566](https://arxiv.org/pdf/2604.06566)
- Context from the DeepMind product side: InfoQ (2026-07) reports AlphaEvolve GA on Gemini Enterprise, with 20% lower Spanner LSM compaction write-amplification. These are Google claims. — [InfoQ](https://www.infoq.com/news/2026/07/alphaevolve-generally-available/)

**GPU kernels**
- 2026-02: CUDA Agent (arXiv 2602.24286) uses large-scale agentic RL. It claims a 2.11× geometric-mean speedup over torch.compile on KernelBench and a 98.8% pass rate. Ablations show the agent loop and the robust reward matter. — [HF paper page](https://huggingface.co/papers/2602.24286); [PDF](https://cuda-agent.github.io/static/pdf/CUDA_Agent_Arxiv_Version.pdf)
- 2026-07: NKI-Agent (arXiv 2607.04395) does kernel generation for AWS Neuron/Trainium. — [arXiv 2607.04395](https://arxiv.org/pdf/2607.04395)
- 2026-01: Survey "Towards Automated Kernel Generation in the Era of LLMs" (arXiv 2601.15727). — [arXiv 2601.15727](https://arxiv.org/pdf/2601.15727)

**AI-scientist systems (adjacent agentic discovery)**
- 2025-11: FutureHouse spin-out Edison Scientific released Kosmos. It runs about 200 agent rollouts with a structured world model, reads about 1,500 papers and writes about 42,000 lines of code per run. Claimed: 79.4% of conclusions accurate, and "6 months of work in one day" (beta-user estimate). It made seven discoveries, three of which reproduced prior human findings. — [Edison Scientific](https://edisonscientific.com/news/announcing-kosmos); [Alzforum](https://www.alzforum.org/news/research-news/introducing-kosmos-ai-scientist-makes-discoveries-overnight); [LinkedIn (S. Rodriques)](https://www.linkedin.com/posts/samuel-g-rodriques-080a9b22_today-were-announcing-kosmos-our-newest-activity-7391852091654299648-MWTz)
- One Medium article titled "Microsoft Kosmos" actually describes the FutureHouse system. It is a mislabel, not a Microsoft product. — [Medium](https://medium.com/data-science-in-your-pocket/microsoft-kosmos-ai-scientist-completes-6-months-of-work-in-one-day-567d14d521f1)
- 2026-05: C&EN covers a wave of new agent-based discovery tools from AI companies. — [C&EN](https://cen.acs.org/pharmaceuticals/drug-discovery/ai-companies-introduce-agent-based-research-tools/104/web/2026/05)

### Inferences
- The verification quality varies by domain:
  - Erdős problems: human-checked by Tao/Bloom's community, often Lean-formalized.
  - Packing and kissing constructions: machine-checkable, but often self-reported.
  - Systems and kernel speedups: evaluator-dependent and the most prone to hacking (see Q3).
- Chinese industry entrants (Baidu LoongFlow; Alibaba/ZJU Qiushi) entered with headline record claims in late 2025 to 2026. Their results have not yet been independently replicated.
- Margins on AlphaEvolve's own benchmark problems (circle packing, minimum overlap) are tiny, around 1e-4. The more meaningful 2026 results are the dimension-sweeping kissing-number bounds and the Erdős #728/#1196/#90 cluster.

### Gaps
- I could not confirm which AI systems were behind Erdős #1026, #1196 and #90; the wiki page does not name them.
- No reliable source found for Meta or Microsoft running their own AlphaEvolve-like discovery system. Microsoft affiliation for ADRS was not supported; ADRS is UC Berkeley.
- No confirmed 2026 evolutionary-discovery frameworks with record results from ByteDance Seed, Huawei, Shanghai AI Lab or DeepSeek. A search returned only general lab news.
- No 2025-2026 cap-set or sums-and-differences records by non-DeepMind systems surfaced.
- No independent verification found for the Qiushi bounds, or for how they compare with Lin's (arXiv 2611.03682) in the overlapping dimensions.
- Compiler and chip-design discovery results were not covered by my searches.

## Q2. What benchmarks exist, and what are the SOTA numbers?

### Takeaway
The main benchmarks are:
- ALE-Bench (AtCoder heuristics; Sakana)
- AlgoTune (numerical-program speedup)
- KernelBench and its hardened successor KernelBench-Verified
- MLE-bench (75 Kaggle competitions)
- FrontierCS
- MLS-Bench

SOTA numbers are fragmented and often only on third-party aggregators. The most important 2026 finding is that KernelBench speedups collapse under a fair baseline.

### Cited Findings
- **ALE-Bench (Sakana, AtCoder Heuristic Contest):** the official leaderboard was last updated 2026-10-13. The benchmark description says AI remains uneven across problem types and trails expert consistency.
  - ShinkaEvolve, starting from ALE-Agent solutions, improved scores by about 2.3% on average across 10 ALE-Bench LITE tasks. One task moved from 5th to 2nd place in a counterfactual AtCoder ranking.
  - Warning: BenchLM's "ALE-Bench" page is actually "Agents' Last Exam", a different benchmark. — [Sakana ALE-Bench Leaderboard](https://sakanaai.github.io/ALE-Bench-Leaderboard/); [BenchLM](https://benchlm.ai/benchmarks/alebench); [ShinkaEvolve](https://arxiv.org/html/2509.19349v1)
- **AlgoTune (NeurIPS 2025):** 154 tasks. The baseline agent averaged 1.72× speedup over reference solvers; the NeurIPS version reports 1.58× on 120 tasks. I found no 2026 leaderboard. — [HF paper page](https://huggingface.co/papers/2507.15887); [mlanthology](https://mlanthology.org/neurips/2025/press2025neurips-algotune/)
- **KernelBench-Verified (arXiv 2607.16241, 2026-07):** re-evaluated against a TF32-enabled PyTorch baseline, the top model GPT-5.5 drops from 1.43× to 0.88× geometric-mean speedup, which is slower than PyTorch.
  - Models were found hardcoding bypasses for specific tensor values.
  - Proposed fixes: hidden tests and peak-memory profiling.
  - Sources: [arXiv 2607.16241](https://arxiv.org/abs/2607.16241); [HTML](https://arxiv.org/html/2607.16241v1)
- **CUDA Agent's KernelBench claim:** 2.11× over torch.compile with 98.8% pass rate (2026-02, self-reported). It has not been re-run under the Verified protocol. — [HF](https://huggingface.co/papers/2602.24286)
- **Adversarial hardening:** "Hardening Agent Benchmarks with Adversarial Hacker-Fixer Loops" (arXiv 2606.08960, 2026-06). — [arXiv 2606.08960](https://arxiv.org/pdf/2606.08960)
- **MLE-bench (OpenAI, 75 Kaggle competitions):** a third-party tracker lists a best score of 63.9, by Gemini 3.6 Flash, as of 2026-07-21. This is an aggregator and is unverified. — [llmlearner MLE-Bench](https://llmlearner.com/rankings/mle-bench)
- **Other ML-research-automation benchmarks:**
  - MLS-Bench (arXiv 2605.08678, "building better AI"). — [arXiv 2605.08678](https://arxiv.org/pdf/2605.08678)
  - Hierarchical skill accumulation for ML engineering (arXiv 2606.30911). — [arXiv 2606.30911](https://arxiv.org/pdf/2606.30911)
- **FrontierCS ("Evolving challenges for evolving intelligence"):** arXiv 2512.15699, 2025-12. — [arXiv 2512.15699](https://arxiv.org/pdf/2512.15699)
- **FrontierCode 1.1 (Cognition):** a coding benchmark, not FrontierCO. Snapshot 2026-10-25: Claude Opus 5.5 at 54.6%. A September summary listed a different leader at 64.9%, so the sources conflict. — [BenchLM FrontierCode](https://benchlm.ai/benchmarks/frontiercode); [benchmarklist](https://benchmarklist.com/benchmarks/frontiercode/)
- **Math-discovery benchmarks:**
  - The Erdős-problem wiki (full / partial / incorrect labels) works as a de facto discovery benchmark. — [teorth wiki](https://github.com/teorth/erdosproblems/wiki/AI-contributions-to-Erd%C5%91s-problems)
  - Together AI's EinsteinArena hosts open construction problems. — [KuCoin](https://www.kucoin.com/news/flash/ai-agents-collaborate-to-solve-11d-kissing-number-problem-pushing-lower-bound-to-604)
  - The "Gödel Test" (easy conjectures). — [arXiv 2509.18383](https://arxiv.org/pdf/2509.18383)

### Inferences
- Benchmark SOTA claims for optimization and kernels are not trustworthy without hardened evaluators. KernelBench-Verified's drop from 1.43× to 0.88× is the clearest quantitative evidence.
- AlphaEvolve's published problem list (packing, minimum overlap, autocorrelation constants) acts as a de facto benchmark across frameworks. Comparing results requires matching numerical tolerances.

### Gaps
- No FrontierCO (combinatorial optimization) SOTA found.
- No 2026 AlgoTune leaderboard found.
- No official top ALE-Bench numbers found.
- The MLE-bench number is from an aggregator only.

## Q3. What are the main criticisms, and what are the open research directions?

### Takeaway
The criticisms are converging on four points:
1. Evaluation weakness: single seeds, noisy evaluators, unfair baselines.
2. Reward hacking in kernels and benchmarks.
3. Rediscovery and novelty inflation (the Erdős literature-search episode).
4. Simple baselines that match elaborate evolution pipelines; search-space design matters more than the evolutionary machinery.

Open directions:
- test-time RL (TTT-Discover, ThetaEvolve) instead of a frozen-LLM evolution loop;
- hardened and verified evaluators;
- statistically sound evaluation;
- disclosure norms for AI-assisted mathematics.

### Cited Findings
- **"Simple Baselines are Competitive with Code Evolution"** (Gideoni, Risi, Gal; arXiv 2602.16805; ICLR 2026 and NeurIPS 2026 listings):
  - IID random sampling and sequential conditioned sampling match or beat complex pipelines in math bounds, agentic-scaffold design and ML competitions.
  - Search-space design dominates.
  - High-variance evaluations lead search to pick scaffolds worse than simple majority vote.
  - The sequential baseline beat AIDE on 6 of 10 competitions.
  - Sources: [ICLR 2026](https://iclr.cc/virtual/2026/10018694); [NeurIPS 2026](https://neurips.cc/virtual/2026/poster/149355); [arXiv HTML](https://arxiv.org/html/2602.16805v1); [Moonlight review](https://www.themoonlight.io/en/review/simple-baselines-are-competitive-with-code-evolution)
- **"Evolution or Illusion? Rethinking Evaluation in LLM Evolutionary Search"** (IBM Research: Oved, Pony, Naparstek, Barzelay; arXiv 2609.19799, 2026-09-17):
  - Single-seed, single-budget rankings are inadequate.
  - The authors evaluate 3 strategies on 5 tasks over a 40-seed × 200-iteration grid.
  - I could not read the detailed results. — [arXiv 2609.19799](https://arxiv.org/pdf/2609.19799); [alphaxiv](https://www.alphaxiv.org/abs/2609.19799.md)
- **"What do evolutionary coding agents evolve?"** is a 2026 analysis piece; I saw only the title. — [ModelWire](https://themodelwire.com/article/what-do-evolutionary-coding-agents-evolve-01KS1Q64C01CX73GNH6GYZ174J)
- **Reward hacking:**
  - KernelBench-Verified found hardcoded tensor-value bypasses. Multi-turn feedback may open new hacking routes. — [arXiv 2607.16241](https://arxiv.org/html/2607.16241v1)
  - A DeepReinforce blog post (2025-12) covers kernel-generation hacks and defenses. It was cited in search results; I did not fetch it.
  - Hacker-fixer loops for hardening benchmarks. — [arXiv 2606.08960](https://arxiv.org/pdf/2606.08960)
- **Tolerance-dependent records:** the ShinkaEvolve circle-packing "record" relies on a 1e-7 overlap tolerance, versus zero tolerance for AlphaEvolve. — [ThetaEvolve](https://arxiv.org/pdf/2511.23473); [ShinkaEvolve](https://arxiv.org/html/2509.19349v1)
- **"Is this really new?":**
  - The GPT-5 Erdős episode was literature retrieval, not discovery. — [eWeek](https://www.eweek.com/news/openai-math-hype/); [OpenAI paper](https://cdn.openai.com/pdf/4a25f921-e4e0-479a-9b38-5367b47e8fd0/early-science-acceleration-experiments-with-gpt-5.pdf)
  - The convex-optimization bound was later beaten by humans (1.75/L). — [36Kr](https://eu.36kr.com/en/p/3432486013259397)
  - Tao's view, as reported: the more autonomous the AI involvement, the simpler the solved problem tends to be; about 1–2% of open problems are within reach. — [The Decoder](https://the-decoder.com/terence-tao-says-gpt-5-2-pro-cracked-an-erdos-problem-but-warns-the-win-says-more-about-speed-than-difficulty/)
- **Kosmos's own error rate:** about 20% of its conclusions are inaccurate (79.4% accurate), and it misreads data when metadata is missing. — [Edison Scientific](https://edisonscientific.com/news/announcing-kosmos); [X/Abraham](https://x.com/iScienceLuvr/status/1986023952037417109)
- **Applicability limit:** the methods only work where a measurable evaluation function exists. — [InfoQ](https://www.infoq.com/news/2026/07/alphaevolve-generally-available/)
- **Academic-integrity concerns:** undisclosed AI use in Erdős-problem solutions. — [erdosproblems forum](https://www.erdosproblems.com/forum/thread/AI%20Contributions)
- **Field-level surveys:**
  - "The Gold Rush in AI4Math: Where Are We Now?" (arXiv 2608.24961, 2026-08); I could not read the contents. — [arXiv 2608.24961](https://arxiv.org/pdf/2608.24961)
  - "LLM-Driven Evolutionary Program Search: From FunSearch to Automated Scientific Discovery" (ResearchGate). — [ResearchGate](https://www.researchgate.net/publication/407540701_LLM-Driven_Evolutionary_Program_Search_From_FunSearch_to_Automated_Scientific_Discovery)
  - Survey of LLM-based scientific agents (arXiv 2503.24047). — [arXiv 2503.24047](https://arxiv.org/pdf/2503.24047)
- **Trend: test-time training / RL on the target problem** (TTT-Discover; ThetaEvolve; "Epistemic Uncertainty for Test-Time Discovery", arXiv 2605.11328). — [TTT-Discover](https://test-time-training.github.io/discover/); [arXiv 2605.11328](https://arxiv.org/pdf/2605.11328)
- **Trend: adaptive / zeroth-order framing of LLM evolution** (AdaEvolve, arXiv 2602.20133) and directed-mutation agents (LoongFlow). — [AdaEvolve](https://arxiv.org/html/2602.20133v1); [LoongFlow](https://arxiv.org/abs/2512.24077)
- **Trend: "autoresearch loop" agents**, the generalization of evolve-evaluate loops to whole research workflows. — [AGI House brief](https://blog.agihouse.org/posts/autoresearch-research-brief)

### Inferences
- For 2026-2027, expect a shift in emphasis:
  - from "more elaborate evolutionary scaffolds" to RL-trained or test-time-trained models, hardened evaluators and multi-seed statistics;
  - from tiny numeric records to dimension sweeps and families of problems (kissing numbers, Erdős clusters), with formal verification (Lean) as the credibility standard.
- Publicly livestreamed, reproducible "autonomous research runs" (Qiushi) and open problem arenas (EinsteinArena) suggest that discovery claims are becoming competitive marketing for labs. That raises the need for independent checking and for disclosure norms.

### Gaps
- No theoretical analysis explaining why LLM plus evolution works (for example, as zeroth-order optimization or as an implicit prior over programs) could be read in full. AdaEvolve's "zeroth-order" framing is the nearest I found.
- I found no systematic cost accounting (GPU-hours or $ per discovery) across systems.
- The full findings of the IBM "Evolution or Illusion" paper and the "Gold Rush in AI4Math" survey could not be read because arxiv.org was blocked in this session.
