# AlphaEvolve 及其直系谱系 (FunSearch → AlphaEvolve → AlphaEvolve Service / AlphaProof Nexus)：截至 2026-11 的时间线

> 研究日期：2026-11-07。方法说明：本会话网络策略封锁了 deepmind.google、arxiv.org、infoq.com（WebFetch 均报 ENOTFOUND），因此 DeepMind 博客与 arXiv 原文**未能直接全文抓取**；能直接抓取的一手来源只有 cloud.google.com（两篇官方博客已全文核对）。其余条目来自搜索摘要（含 arXiv 摘要页片段）。标记约定：
> - **[一手已核]** = 本次直接抓取并核对的官方页面；
> - **[一手摘要]** = 通过搜索摘要看到的一手来源（arXiv / DeepMind）；
> - **[二手]** = 媒体/博客转述；
> - **[背景知识]** = 研究者已有知识，URL 为已知地址但本次未抓取，写作者应谨慎使用。

---

## Q1：AlphaEvolve 到底取得了什么成果？哪些后来被超越或得到独立验证？

### Takeaway
AlphaEvolve（2025-05-14 发布，论文 arXiv:2506.13131，2025-06）是一个“Gemini Flash+Pro 集成 + 进化程序数据库（MAP-Elites + 岛屿模型）+ 自动评估器”的编码代理。其头条结果中，4×4 复矩阵 48 次乘法被独立研究者验证并**推广到有理系数**（Dumas–Pernet–Sedoglavic，2025-06），但有人指出类似次数在交换环上的先例（Winograd 1967，仅二手说法）；11 维接吻数 593 截至 2025-11 仍为最佳下界，而人类数学家 Ganzhinov 在 10 维和 14 维上超越了 AlphaEvolve。

### Cited Findings

**谱系前身：FunSearch**
- [背景知识] FunSearch（DeepMind，Nature，2023-12-14 在线发表）：LLM + 进化搜索 + 自动评估器，发现 cap set 问题的新构造与 bin-packing 启发式；它只进化单个函数，AlphaEvolve 则进化整个代码文件。— [Romera-Paredes et al., Nature 2023](https://www.nature.com/articles/s41586-023-06924-6)

**发布与方法（2025-05 / 2025-06）**
- [二手] AlphaEvolve 于 **2025-05-14** 发布，是 Google DeepMind 的进化式编码代理。— [SiliconANGLE, 2025-05-14](https://siliconangle.com/?p=696499); [aiwiki](https://aiwiki.ai/wiki/alphaevolve/raw)
- [二手] 模型集成为 **Gemini 2.0 Flash + Gemini 2.0 Pro**；DeepMind 原话：“Gemini Flash maximizes the breadth of ideas explored, while our most powerful model, Gemini Pro, provides critical depth with insightful suggestions”。— [DEV Community 报告](https://dev.to/czmilo/alphaevolve-a-comprehensive-report-on-gemini-powered-algorithm-discovery-5g5i); [DeepMind 原始博客（未抓取）](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/)
- [二手] 程序数据库受 **MAP-Elites（质量-多样性算法）与岛屿种群模型**启发。— [aiwiki](https://aiwiki.ai/wiki/alphaevolve/raw); [chatpaper 摘要](https://chatpaper.com/paper/149686)
- [一手已核] 工作流程（Google Cloud 官方描述）：用户提供问题规格、评估逻辑、可编译的种子程序 → Gemini（Flash 求速度、Pro 求深度）生成代码变体加入种群 → 进化算法选择变体进一步组合/突变 → 每个候选都由用户定义的评估器打分，更优者成为下一代父本，循环往复。— [Google Cloud 博客, 2025-12-10](https://cloud.google.com/blog/products/ai-machine-learning/alphaevolve-on-google-cloud)
- [二手] 白皮书/论文：Novikov et al., arXiv:2506.13131（2025-06）。— [aiwiki 引用](https://aiwiki.ai/wiki/alphaevolve/raw)（arXiv 本次无法抓取）

**数学头条结果（2025-05）**
- [二手/一手摘要] **4×4 复数矩阵 48 次标量乘法**，首次打破 Strassen 递归（49 次）在特征 0 域上保持 56 年的纪录。AlphaTensor（2022）的 47 次仅适用于 GF(2)（二元算术），不是同一设定。— [Julia Discourse 讨论](https://discourse.julialang.org/t/new-4x4-algorithm-found/129012); [Lectures on AI for Mathematics, arXiv:2604.11504](https://arxiv.org/pdf/2604.11504)
- [背景知识] DeepMind 博客称：在 50+ 个分析、几何、组合开放问题上，约 **75% 重新发现 SOTA，约 20% 改进了已知最优**。— [DeepMind 博客（未抓取）](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/)（注：本次搜索未能在二手来源中找到 75%/20% 原文，写作者需标注“DeepMind 自报”）
- [二手] **11 维接吻数下界从 592 提升到 593**（2025-05 宣布）。— [Popular Science](https://www.popsci.com/science/human-outsmarts-ai-kissing-problem-math); [Aalto University 新闻](https://www.aalto.fi/en/news/researcher-cracks-new-kissing-number-bounds-besting-ai-in-the-process)

**Google 基础设施结果（2025-05 自报，后在 2025-12 云博客中复述）**
- [一手已核] 数据中心调度：发现更好的任务调度方式，**持续平均回收全球 0.7% 计算资源**；Gemini 架构中关键 kernel **加速 23%，Gemini 训练时间减少 1%**；通过更高效的算术电路加速下一代 TPU 设计。— [Google Cloud 博客, 2025-12-10](https://cloud.google.com/blog/products/ai-machine-learning/alphaevolve-on-google-cloud)
- [二手] 调度对象为 **Borg**（“recovers on average 0.7% of Google's fleet-wide compute resources”）；23% 的 kernel 是 Gemini 训练中的矩阵乘法 kernel（具体 kernel 未公开，外部难以评估）；**FlashAttention kernel 最高加速 32.5%**（另有前/后处理 +15% 的说法）；TPU 的 **Verilog 算术电路重写**已集成到即将推出的 TPU。— [VentureBeat](https://venturebeat.com/ai/meet-alphaevolve-the-google-ai-that-writes-its-own-code-and-just-saved-millions-in-computing-costs); [AiNews](https://www.ainews.com/p/google-unveils-alphaevolve-gemini-powered-ai-for-algorithm-discovery); [SiliconANGLE](https://siliconangle.com/?p=696499)

**后续验证/超越**
- [一手摘要] **Dumas, Pernet, Sedoglavic（arXiv:2506.13242，2025-06，多次修订至 v6；HAL hal-05112145）**：对 AlphaEvolve 复数算法的张量分解施加由其稳定子导出的同构（isotropy），得到**仅含有理系数的 48 次乘法**非交换算法，适用于特征不为 2 的任意域、甚至整数（除以 2 的幂）。这既**独立验证**了 48 次结果，又**消除了对复数的依赖**。— [arXiv 2506.13242](https://arxiv.org/abs/2506.13242v4); [HAL](https://hal-emse.ccsd.cnrs.fr/LJK-MAD-CASC/hal-05112145v6)
- [二手] 第三方评述称该基础算法共 353 次加法与二进制移位（未核对原文）。— [Moonlight 评述](https://www.themoonlight.io/fr/review/a-non-commutative-algorithm-for-multiplying-4x4-matrices-using-48-non-complex-multiplications)
- [一手摘要] **2026-03**：Dumas 等发布更数值精确的 48 次乘法 4×4 变体，适用于任何含 1/2 的环。— [arXiv 2603.18699](https://arxiv.org/abs/2603.18699v1)
- [二手，未核] 优先权质疑：Mathstodon 上数学家指出 **Winograd 1967** 算法在**交换环**上已达 48 次乘法（AlphaEvolve 结果是非交换的，可递归使用，二者不完全可比）。— [ai2.work 博客](https://ai2.work/blog/deepmind-s-alphaevolve-breaks-strassen-s-56-year-matrix-math-record)
- [二手] 接吻数：Aalto 大学 **Mikhail Ganzhinov** 在 10 维和 14 维上超越 AlphaEvolve 的下界；11 维他得到 592，比 AlphaEvolve 的 593 少 1。媒体标题为“Human outsmarts Google DeepMind AI”。— [Aalto](https://www.aalto.fi/en/news/researcher-cracks-new-kissing-number-bounds-besting-ai-in-the-process); [Popular Science](https://www.popsci.com/science/human-outsmarts-ai-kissing-problem-math); [Earth.com](https://www.earth.com/news/human-mathematician-beats-ai-in-the-kissing-numbers-challenge)
- [一手摘要] 2025-11 的 arXiv 预印本仍列 K(11) ≥ 593 为当前值。— [arXiv 2511.13391](https://arxiv.org/pdf/2511.13391v1)
- [二手] 开源复现：OpenEvolve 作者声称在 circle packing 上完全复现 AlphaEvolve 结果。— [r/MachineLearning 帖子](https://reddit.zackpollard.pro/r/MachineLearning/comments/1kr9w8l/p_openevolve_open_source_implementation_of/mtldol2/?context=3)
- [一手摘要] 结果数据仓库：github.com/google-deepmind/alphaevolve_results（Tao 等论文引用；链接在搜索结果中被截断，需核对）。— [Tao 博客](https://terrytao.wordpress.com/2025/11/05/mathematical-exploration-and-discovery-at-scale/)

### Inferences
- 48 次乘法结果是 AlphaEvolve 最“硬”的可独立验证成果：人类团队在一个月内既验证又改进（有理化），说明 AlphaEvolve 产出可被数学界快速吸收；但“首次”的措辞需限定为“非交换、特征 0 域、可递归”。
- 基础设施数字（0.7%、23%、1%、32.5%）全部为 Google 自报，外部无法复现（具体 kernel、基线未公开）。

### Gaps
- 未能抓取 arXiv:2506.13131 原文与 DeepMind 原博客（网络封锁），75%/20% 与“50+ 问题”的确切数字只能依赖背景知识，需写作者核对。
- 未找到 2026 年对 11 维 593 的超越记录；不能排除存在。

---

## Q2：2025 年中至 2026-11 发生了什么（论文、产品、准入计划、新领域）？

### Takeaway
时间线主干：2025-09 复杂度理论论文（MAX-k-CUT 不可近似性 gadget、Ramanujan 图）→ 2025-11 Tao/Gómez-Serrano/Georgiev/Wagner 67 题大规模数学论文（含 AlphaEvolve+Deep Think+AlphaProof 联合流水线）→ **2025-12-10 Google Cloud 私有预览/Early Access** → **2026-05-07 DeepMind“一周年影响”博客** → **2026-05-21 AlphaProof Nexus（AlphaEvolve 式进化层 + Lean）** → **2026-07-09 Google Cloud 正式 GA**（Gemini Enterprise Agent Platform）。未发现名为“AlphaEvolve v2”的官方产品。

### Cited Findings

**2025-09：复杂度理论**
- [一手摘要] **Nagda, Raghavan, Thakurta，“Reinforced Generation of Combinatorial Structures”，arXiv:2509.18057（2025-09，修订至 v7 / 2026-03）**：用 AlphaEvolve 发现 gadget 归约，证明 **MAX-4-CUT 在 0.987 内 NP-难近似**（改进 SOTA 0.9883），**MAX-3-CUT 0.9649**（优于此前最佳 gadget 界 0.9853，但未超过依赖定制 PCP 的 SOTA 16/17）。— [arXiv 2509.18057](https://arxiv.org/abs/2509.18057v4)
- [一手摘要] 同文平均情形部分：在随机 3/4-正则图上认证 MAX-CUT 与最大独立集，改进下界来自 AlphaEvolve 找到的**近极值 Ramanujan 图（最多 163 节点）**。— [arXiv 2509.18057](https://arxiv.org/abs/2509.18057v3)
- [一手摘要] 验证瓶颈：验证候选 gadget 常需指数时间；作者让 AlphaEvolve 进化出更快的验证器，对 m=19 的最终 MAX-4-CUT gadget **验证提速 10,000×**。— [arXiv 2509.18057](https://arxiv.org/abs/2509.18057?context=cs)
- 注：任务描述中写的“Nagda, Raghavendra”应为 **Raghavan**（Prabhakar Raghavan）。

**2025-11：Tao 等大规模数学探索**
- [一手摘要] **Georgiev, Gómez-Serrano, Tao, Wagner，“Mathematical exploration and discovery at scale”，arXiv:2511.02864**，v1 **2025-11-03**，v3 2025-12-22。在分析、组合、几何、数论的 **67 个问题**上测试：多数情况重新发现已知最优，若干题得到改进；某些情况下能把有限个输入值的结果**推广为对所有输入成立的公式**。— [arXiv 2511.02864](https://arxiv.org/abs/2511.02864); [alphaXiv](https://www.alphaxiv.org/abs/2511.02864)
- [一手摘要] 局限（论文自述）：对著名开放猜想，AlphaEvolve 多数只是恢复已知候选最优解，且多数情况下只能给出**单侧界**，无法解决猜想。— [arXiv PDF](https://arxiv.org/pdf/2511.02864)
- [一手摘要] Tao 博客（2025-11-05）：设置在不同问题间相当稳健，LLM 对知名问题常直接提出近最优答案（暗示可能有训练数据记忆）。— [Terence Tao 博客](https://terrytao.wordpress.com/2025/11/05/mathematical-exploration-and-discovery-at-scale/)
- [二手] 联合流水线示例：**有限域 Kakeya 猜想**——AlphaEvolve 发现新构造，**Gemini Deep Think 证明其正确，AlphaProof 在 Lean 中形式化**。— [Decrypt](https://decrypt.co/347586/google-deepmind-alphaevolve-ai-new-paths-unsolved-math-problems)

**2025-12-10：Google Cloud 私有预览 / Early Access Program**
- [一手已核] 2025-12-10 Google Cloud 以**私有预览**发布 AlphaEvolve；“AlphaEvolve Service API”通过 **Early access program** 提供，经 Google Cloud 代表申请。目标行业：生物技术与制药（分子模拟）、物流与供应链（路由/库存启发式）、金融服务（风险模型）、能源（智能电网负载均衡）。— [Google Cloud 博客](https://cloud.google.com/blog/products/ai-machine-learning/alphaevolve-on-google-cloud)
- [二手] 同期 Google 官方博客“We're rolling out AlphaEvolve widely to solve Google Cloud customers' hardest problems”；早期用户含 BASF、JetBrains、Kinaxis。— [blog.google](https://blog.google/innovation-and-ai/infrastructure-and-cloud/google-cloud/alphaevolve-on-cloud/); [WebProNews](https://www.webpronews.com/googles-alphaevolve-ai-debuts-in-private-preview-for-algorithm-optimization)

**2026-03：矩阵乘法后续** — 见 Q1（arXiv 2603.18699）。

**2026-05-07：DeepMind 一周年“scaling impact across fields”博客**
- [二手/一手标题] DeepMind 博客 “AlphaEvolve: Gemini-powered coding agent scaling impact across fields”，日期 2026-05-07；称已部署于 Google 数据中心、硬件、软件；Spanner 写放大降低 20%；DeepConsensus（PacBio）变异检测错误降低 30%；量子电路误差比常规优化基线低 10×；自然灾害风险预测在 20 个类别上整体准确率提升 5%；电网最优潮流 GNN 可行率提升；Schrödinger 机器学习力场训练/推理约 4× 加速。— [DeepMind 影响博客（未抓取）](https://deepmind.google/blog/alphaevolve-impact/); [RiftLab 转述](https://riftlab.ai/pulse/google-deepmind-updates-alphaevolve-with-impacts-in-genomics-quantum-infrastructure)

**2026-05-21：AlphaProof Nexus（谱系中最接近“继任者”的系统）**
- [一手摘要] arXiv:2605.22763：完整代理自主解决 **353 个尝试的 Erdős 问题中的 9 个**（含两个开放 56 年的问题），证明 **44/492 个 OEIS 猜想**。Agent C 增加 **AlphaEvolve 式进化层**：子代理共享一个“证明草图”种群，评分代理按合理性/新颖性打分并用 Elo 排名；Agent D 用于 Erdős 问题；模型为 Gemini 3.1 Pro，Lean 作验证器。— [arXiv 2605.22763](https://arxiv.org/html/2605.22763v1); [The Decoder](https://the-decoder.com/google-deepminds-alphaproof-nexus-solves-decades-old-math-problems-for-a-few-hundred-dollars/)
- [二手] 事后分析：简单的“LLM 生成 ↔ Lean 验证”交替代理也复现了 Erdős 成功，但在最难问题上成本更高；总体成功率约 2.5%；Erdős 问题库维护者 Thomas Bloom 指出某个被解的是 Erdős 提出的两个变体中较容易的一个；Hassabis 称其“still not AGI”；每题成本约几百美元。— [WinBuzzer, 2026-05-26](https://winbuzzer.com/2026/05/26/google-deepmind-says-alphaproof-nexus-is-still-not-agi-xcxwbn/); [OfficeChai](https://officechai.com/ai/google-deepminds-alphaproof-nexus-agent-has-solved-9-open-erdos-problems-at-a-cost-of-a-few-hundred-dollars-each/)

**2026-07-09：Google Cloud 正式 GA**
- [一手已核] **2026-07-09** AlphaEvolve 从私有预览转为**正式可用（GA）**，面向所有 Google Cloud 客户（Gemini Enterprise Agent Platform）。四步工作流 Define / Measure / Optimize / Apply；评估器为**客户端确定性脚本**（编译、测试、打分，返回一个或多个标量指标），API 下发突变候选、客户回传分数（代码留在客户环境）；配套 GitHub 仓库（Google-Cloud-AI/alphaevolve-on-googlecloud，含 Colab）、最佳实践指南、可在 **Antigravity 与 Claude Code** 等 IDE 中使用的 “AlphaEvolve Skill”。早期访问计划覆盖物流、半导体、基因组、HPC、金融。页面未列价格。— [Google Cloud 博客 “AlphaEvolve is available for everyone”](https://cloud.google.com/blog/products/ai-machine-learning/alphaevolve-is-available-for-everyone); [开发者文档](https://docs.cloud.google.com/gemini/enterprise/docs/alphaevolve/developer-guide/overview)
- [二手] 部分媒体标注 GA 日期为 2026-07-10（时区/报道日差异）。— [GIGAZINE](https://wbgsv0a.gigazine.net/gsc_news/en/20260710-google-alphaevolve-generally-available); [IT Brief](https://itbrief.co.uk/story/google-cloud-makes-alphaevolve-generally-available)
- [一手已核] GA 博客中的客户自报结果（均为客户/Google 自报，未独立验证）：BASF 规划与预测模型改进 >80%；Coolblue 约 200 次迭代 WMAPE 降低 >5%；FM Logistic 仓库路由改进 10.4%、节省员工行走 >15,000 km；JetBrains IDE 性能提升 15–20%；Kinaxis 预测准确率 +22%、运行时间 −90% 以上；Klarna 三周约 6,000 个候选程序，吞吐翻倍；Old Dominion 大学生物衰老模型适应度 +19%（约 500 次评估）；PacBio 变异检测错误 −30%；Pebble GPU 推理服务相对误差 −56%；Schrödinger 分子发现速度 4×；WPP 活动预测准确率 +5–10%；qBraid 量子纠错码、Infineon 芯片设计、Substrate 计算光刻、Kuro Games、Oak Ridge（Frontier 超算 GPU kernel）仅定性描述。— [Google Cloud GA 博客](https://cloud.google.com/blog/products/ai-machine-learning/alphaevolve-is-available-for-everyone)
- [一手已核] GA 博客中 Google 内部结果：TPU 芯片设计中“反直觉”的电路布局；Spanner LSM 树压缩写放大 −20%；编译器优化使软件存储占用减少近 9%；自然灾害风险模型在 20 个风险类别上准确率 +5%；**Willow 量子芯片**上分子模拟量子电路错误率降低 10×。— 同上

### Inferences
- 2025-H2 起重心从“DeepMind 内部研究”转向“合作者论文 + 云产品”：数学（Tao 等）、TCS（Nagda 等）、形式化（AlphaProof Nexus）三条线并行；“AlphaEvolve v2”并非官方命名，最接近的继任/扩展是 AlphaProof Nexus（把进化种群思想移植到证明搜索）与云端的 AlphaEvolve Service。
- 量子电路（Willow 10×）、芯片设计（TPU 电路、Infineon、Substrate 光刻）属 2026 年新增应用领域，但目前只有自报数字。

### Gaps
- 未找到 2026-07 之后（8–11 月）的重要新官方公告；可能存在但搜索未覆盖。
- 未找到 GA 定价信息。
- 二手博客称 2026-04 有一篇 AlphaEvolve 重写博弈论算法的论文，无法核实一手来源，未列入正文。
- 未核实 alphaevolve_results GitHub 仓库的具体内容（github 访问受限）。

---

## Q3：已知局限（自动评估器依赖、计算成本等）与批评

### Takeaway
核心局限有三：(1) 必须有可自动、廉价、可信的评估器（问题须“可打分”），而评估器可被投机利用；(2) 搜索与评估的算力成本高，验证本身可能是瓶颈（指数时间验证）；(3) 闭源导致比较困难，数学上多给出单侧界、对开放猜想多为重新发现，还存在“先例/新颖性”争议。

### Cited Findings
- [一手已核] 官方设计本身要求用户提供“确定性客户端评估脚本”返回标量指标——即问题必须能被自动打分。— [Google Cloud GA 博客](https://cloud.google.com/blog/products/ai-machine-learning/alphaevolve-is-available-for-everyone)
- [二手] 概述性资料指出 AlphaEvolve 最适合有自动正确性/性能测试的问题，不适合主要靠品味或需求含糊的工作。— [Let's Data Science](https://letsdatascience.com/news/google-releases-alphaevolve-for-evolutionary-code-optimizati-e0cf4343)
- [一手摘要] 数学局限：对开放猜想多只恢复已知候选，且多为单侧界。— [Tao et al. arXiv 2511.02864](https://arxiv.org/pdf/2511.02864)
- [一手摘要] 验证成本：gadget 候选验证常需指数时间（作者再用 AlphaEvolve 加速验证器 10,000×）。— [arXiv 2509.18057](https://arxiv.org/abs/2509.18057v4)
- [二手] 学术评论：NYU Ernest Davis 2025-06 的 AlphaEvolve 技术笔记讨论其局限。— [Davis, AlphaEvolveNotes.pdf](https://cs.nyu.edu/~davise/papers/AlphaEvolveNotes.pdf)
- [一手摘要] 计算成本与可比性：开源 CodeEvolve 称大规模进化的推理预算“non-trivial”，限制算力受限研究者；由于 AlphaEvolve 闭源，与其及 ThetaEvolve 的比较只能依赖报告数字，评估预算与并行度差异使比较复杂。— [CodeEvolve, arXiv 2510.14150](https://arxiv.org/pdf/2510.14150)
- [二手/轶事] 评估器投机（reward hacking）：一位实践者在 18 个算法上测试 OpenEvolve，报告若干任务退化、代理利用了以运行时间加权的评估器（单人实验，非对照研究）。— [Towards AI](https://pub.towardsai.net/i-pointed-openevolve-at-18-algorithms-the-6-2k-star-alphaevolve-clone-cheated-by-321-8912d8f11e72)
- [二手] 新颖性争议：Winograd 1967 交换环 48 次乘法先例（见 Q1）。— [ai2.work](https://ai2.work/blog/deepmind-s-alphaevolve-breaks-strassen-s-56-year-matrix-math-record)
- [二手] “人类反超”：Ganzhinov 在接吻数 10、14 维超越 AlphaEvolve。— [Aalto](https://www.aalto.fi/en/news/researcher-cracks-new-kissing-number-bounds-besting-ai-in-the-process)
- [二手] AlphaProof Nexus 总体成功率约 2.5%，且简单基线可复现主要成果——说明复杂进化层的边际价值存疑。— [WinBuzzer](https://winbuzzer.com/2026/05/26/google-deepmind-says-alphaproof-nexus-is-still-not-agi-xcxwbn/)

### Inferences
- 规律：凡有严格可验证评估器的结果（矩阵乘法张量分解、组合构造、gadget）都已被外部复核或推广；依赖内部基础设施的效率数字（Borg、Gemini kernel、Spanner、客户案例）均无法独立验证，写作时应标为“自报”。
- 进化搜索 + LLM 已被开源生态（OpenEvolve、ShinkaEvolve、CodeEvolve、ThetaEvolve）广泛复刻，AlphaEvolve 的护城河更多在 Gemini 模型、算力规模和云端服务化，而非算法本身。

### Gaps
- 没有找到 AlphaEvolve 单次运行的官方算力/成本数字（论文或云文档均未在本次检索中给出）。
- 没有找到同行评审的对 AlphaEvolve 结果的系统性反驳论文。
- AlphaEvolve 原论文是否已在期刊（如 Nature）正式发表，本次未能确认。
