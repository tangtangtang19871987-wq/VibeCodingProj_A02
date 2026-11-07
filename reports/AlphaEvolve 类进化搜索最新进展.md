# 进化式程序搜索从论文走进云产品

截至 2026-11，LLM 驱动的进化式程序搜索已经从 DeepMind 的一个研究系统变成了一个生态，主线有三条。第一条是 **AlphaEvolve 本身产品化**：2025-12 在 Google Cloud 开私有预览，**2026-07-09 正式 GA**，同年 5 月又把进化种群思想移植进了形式化证明系统 AlphaProof Nexus。第二条是**开源复刻和改进**：OpenEvolve 约 7.7k star，是事实上的标准基线；ShinkaEvolve、ThetaEvolve、CodeEvolve 等在样本效率、RL 训练 mutator、降低成本上各有推进。第三条是 **DeepMind 以外的团队拿出了可核查的成果**，包括 Erdős 问题、接吻数下界、SAT 求解器、系统调度启发式。成果的可信度呈两极。一端是有严格机器验证器的成果，比如 4×4 矩阵 48 次乘法、组合构造、gadget 归约，这些已被外部复核甚至推广。另一端是依赖内部评估器的效率数字，比如 Borg 0.7%、Gemini kernel 23%、各云客户案例，它们全部是自报，外部无法复现。用户点名的 **VPEvolve 不是通用的 AlphaEvolve 克隆**。它是一个计算光刻（OPC recipe 优化）领域的"自进化虚拟工艺工程师"：LLM 冻结，靠 Skill Bank 积累经验，与基于种群的程序进化只算松散同源。2026 年最值得重视的反向证据有两条：一是"简单基线与复杂代码进化管线打平"，二是 KernelBench-Verified 在公平基线下把 SOTA 加速比从 1.43× 打回 0.88×。这两条说明，该领域眼下的瓶颈在评估器和实验规范，不在进化算法。

> **证据标注约定**（贯穿全文）：**【已核】**＝研究者直接抓取并核对过原文；**【摘要级】**＝只看到搜索引擎对 arXiv、DeepMind 等一手页面的摘要片段，没读全文（本次会话中 arxiv.org、deepmind.google 被网络策略封锁，所以大部分 arXiv 事实属于这一级）；**【二手】**＝媒体或博客转述；**【背景知识】**＝研究者凭已有知识写出、本次没有抓取，需要另行核对；**【自报】**＝作者、厂商或客户的自我报告，没有独立复现；**【独立验证】**＝有第三方复核或推广。

## AlphaEvolve 用 18 个月走完研究、预览、GA 三步

AlphaEvolve 的前身是 FunSearch（Nature，2023-12）。FunSearch 只进化单个函数，用于 cap set 构造和 bin-packing 启发式；AlphaEvolve 扩展到进化整个代码文件。**【背景知识】**（[Romera-Paredes et al., Nature 2023](https://www.nature.com/articles/s41586-023-06924-6)）。AlphaEvolve 于 **2025-05-14** 发布（[SiliconANGLE](https://siliconangle.com/?p=696499)），论文为 Novikov et al., arXiv:2506.13131。论文原文没能抓取，编号来自二手引用（[aiwiki](https://aiwiki.ai/wiki/alphaevolve/raw)）。架构是"Gemini Flash 负责广度、Gemini Pro 负责深度"的模型集成，加上受 **MAP-Elites 和岛屿模型**启发的程序数据库，再加上用户定义的自动评估器。Flash 和 Pro 的具体版本为 2.0，这一点来自二手转述（[DEV Community](https://dev.to/czmilo/alphaevolve-a-comprehensive-report-on-gemini-powered-algorithm-discovery-5g5i)）。工作流程在 Google Cloud 官方博客中有描述，已核对：用户给出问题规格、评估逻辑和可编译的种子程序 → Gemini 生成变体 → 进化算法挑选并组合、突变 → 评估器打分，择优作为下一代父本（[Google Cloud 博客, 2025-12-10](https://cloud.google.com/blog/products/ai-machine-learning/alphaevolve-on-google-cloud)）。

此后的演进节奏如下表。没有发现任何名为"AlphaEvolve v2"的官方产品。谱系上最接近"继任者"的是 AlphaProof Nexus，产品形态上的延续是 AlphaEvolve Service。

| 时间 | 事件 | 证据级别 |
|---|---|---|
| 2025-05-14 | AlphaEvolve 发布 | 二手 |
| 2025-09 | Nagda/Raghavan/Thakurta 用 AlphaEvolve 找 gadget，改进 MAX-k-CUT 不可近似性界 | 摘要级 |
| 2025-11-03 | Georgiev/Gómez-Serrano/Tao/Wagner 在 67 个问题上做大规模数学探索 | 摘要级 |
| 2025-12-10 | Google Cloud 私有预览 + Early Access Program | 已核 |
| 2026-05-07 | DeepMind 一周年"跨领域影响"博客 | 二手（原文未抓取） |
| 2026-05-21 | AlphaProof Nexus（加入 AlphaEvolve 式进化层，以 Lean 为验证器） | 摘要级 |
| 2026-07-09 | Google Cloud GA（Gemini Enterprise Agent Platform） | 已核 |

GA 版本的产品设计本身就界定了适用边界。评估器必须是**客户端的确定性脚本**，负责编译、测试、打分，返回标量指标。API 下发突变候选，客户回传分数，代码始终留在客户环境中。配套提供 GitHub 仓库、Colab，以及可在 Antigravity 和 Claude Code 中使用的"AlphaEvolve Skill"。页面没有列出价格（[Google Cloud GA 博客](https://cloud.google.com/blog/products/ai-machine-learning/alphaevolve-is-available-for-everyone)；[开发者文档](https://docs.cloud.google.com/gemini/enterprise/docs/alphaevolve/developer-guide/overview)）。部分媒体把 GA 日期记为 2026-07-10，属于报道日或时区差异（[IT Brief](https://itbrief.co.uk/story/google-cloud-makes-alphaevolve-generally-available)）。研究笔记没有找到 2026-08 到 11 月间的重要官方新公告，但不能排除存在。

AlphaProof Nexus 是这条谱系 2026 年最有意思的分支。据 arXiv 摘要，完整代理在尝试的 **353 个 Erdős 问题中自主解决了 9 个**，其中两个已开放 56 年；另外证明了 **44/492 个 OEIS 猜想**。其中 Agent C 引入了 AlphaEvolve 式进化层：子代理共享一个"证明草图"种群，由评分代理按 Elo 排名。所用模型为 Gemini 3.1 Pro，Lean 作验证器。**【摘要级】**（[arXiv 2605.22763](https://arxiv.org/html/2605.22763v1)）。二手报道给它降了温。一是简单的"LLM 生成 ↔ Lean 验证"交替代理同样复现了 Erdős 上的成功，只是在最难问题上成本更高。二是总体成功率约 2.5%。三是 Erdős 问题库维护者 Thomas Bloom 指出，其中一题被解的是 Erdős 所提两个变体中较容易的那个。每题成本约几百美元（[WinBuzzer](https://winbuzzer.com/2026/05/26/google-deepmind-says-alphaproof-nexus-is-still-not-agi-xcxwbn/)）。由此看，进化层的边际价值仍未得到证明。

## 有机器验证器的成果站得住，基础设施数字全是自报

AlphaEvolve 最硬的成果是 **4×4 复矩阵 48 次标量乘法**。它首次在特征 0 域上打破了 Strassen 递归 49 次的纪录。AlphaTensor 的 47 次只适用于 GF(2)，不是同一设定（[Julia Discourse](https://discourse.julialang.org/t/new-4x4-algorithm-found/129012)；[arXiv 2604.11504](https://arxiv.org/pdf/2604.11504)）。一个月内，Dumas、Pernet、Sedoglavic 对其张量分解施加由稳定子导出的同构，得到**只含有理系数的 48 次乘法非交换算法**，适用于特征不为 2 的任意域。这一步**既独立验证了结果，又消除了对复数的依赖**。**【独立验证，摘要级】**（[arXiv 2506.13242](https://arxiv.org/abs/2506.13242v4)；[HAL](https://hal-emse.ccsd.cnrs.fr/LJK-MAD-CASC/hal-05112145v6)）。2026-03 他们又发布了数值上更精确、适用于任何含 1/2 的环的变体（[arXiv 2603.18699](https://arxiv.org/abs/2603.18699v1)）。这项成果也有新颖性争议：Mathstodon 上有数学家指出，Winograd 1967 的算法在**交换环**上已达到 48 次。但 AlphaEvolve 的算法是非交换的、可递归使用，二者不完全可比。这一说法只见于二手来源，没有核对（[ai2.work](https://ai2.work/blog/deepmind-s-alphaevolve-breaks-strassen-s-56-year-matrix-math-record)）。所以"首次"的措辞应限定为"非交换、特征 0、可递归"。

接吻数的情况更复杂，展示了人机之间的拉锯。AlphaEvolve 把 11 维下界从 592 提到 **593**。Aalto 大学的 Mikhail Ganzhinov 随后在 **10 维和 14 维上超越了 AlphaEvolve**，但他在 11 维只得到 592（[Aalto](https://www.aalto.fi/en/news/researcher-cracks-new-kissing-number-bounds-besting-ai-in-the-process)；[Popular Science](https://www.popsci.com/science/human-outsmarts-ai-kissing-problem-math)）。2025-11 的预印本仍把 K(11) ≥ 593 列为当前值（[arXiv 2511.13391](https://arxiv.org/pdf/2511.13391v1)）。到 2026-04 前后，加密货币新闻称 Together AI EinsteinArena 上的 AI 代理把 11 维推到了 604，这只是单一二手来源，未经核实（[KuCoin](https://www.kucoin.com/news/flash/ai-agents-collaborate-to-solve-11d-kissing-number-problem-pushing-lower-bound-to-604)）。

复杂度理论这条线也有扎实成果。Nagda、Raghavan、Thakurta 用 AlphaEvolve 找到 gadget 归约，证明 **MAX-4-CUT 在 0.987 内近似是 NP-难的**，改进了 SOTA 0.9883。MAX-3-CUT 得到 0.9649，好于此前最佳的 gadget 界，但没有超过依赖定制 PCP 的 16/17。同一工作里，AlphaEvolve 还进化出了更快的验证器，在 m=19 的 gadget 上**验证提速 10,000×**。**【摘要级】**（[arXiv 2509.18057](https://arxiv.org/abs/2509.18057v4)）。验证器本身成为瓶颈，再用同一系统去加速它，这个细节值得记住。另外，任务描述中的作者名"Raghavendra"应为 **Raghavan**。

在 Tao 等人的 67 题研究中，AlphaEvolve 多数情况下是重新发现已知最优，在若干题上有改进，偶尔能把有限个输入值上的结果推广为通用公式。论文也直说了局限：面对著名开放猜想，系统多数只能恢复已知候选，并且大多只给出**单侧界**（[arXiv 2511.02864](https://arxiv.org/abs/2511.02864)）。Tao 在博客中提到，LLM 对知名问题常常直接给出近最优答案，这暗示可能存在训练数据记忆（[Tao 博客](https://terrytao.wordpress.com/2025/11/05/mathematical-exploration-and-discovery-at-scale/)）。这项研究的同行评审版已出现在 PubMed 上（[PubMed 42814542](https://pubmed.ncbi.nlm.nih.gov/42814542/)）。另一个联合流水线的例子是有限域 Kakeya 猜想：AlphaEvolve 找到构造，Gemini Deep Think 给出证明，AlphaProof 在 Lean 中完成形式化。这个例子来自二手报道（[Decrypt](https://decrypt.co/347586/google-deepmind-alphaevolve-ai-new-paths-unsolved-math-problems)）。常被引用的"50+ 问题中约 75% 重新发现 SOTA、约 20% 有改进"出自 DeepMind 原博客，本次**没能抓取，也没在二手来源中找到原文，只有【背景知识】级别**，引用时须注明"DeepMind 自报，未核"（[DeepMind 博客](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/)）。

另一端是 Google 内部和客户报告的效率数字，下表汇总，**全部是自报**：

| 声明 | 来源 | 证据级别 |
|---|---|---|
| Borg 调度平均回收全球 0.7% 算力；Gemini 关键 kernel 加速 23%、训练时间减少 1%；TPU 算术电路改进 | [Cloud 博客](https://cloud.google.com/blog/products/ai-machine-learning/alphaevolve-on-google-cloud) | 已核（原文如此陈述），内容为自报 |
| FlashAttention kernel 最高加速 32.5% | [VentureBeat](https://venturebeat.com/ai/meet-alphaevolve-the-google-ai-that-writes-its-own-code-and-just-saved-millions-in-computing-costs) | 二手，自报 |
| Spanner LSM 压缩写放大 −20%；编译器优化使存储占用减少近 9%；Willow 量子芯片上量子电路误差降低 10×；灾害风险模型在 20 个类别上 +5% | [GA 博客](https://cloud.google.com/blog/products/ai-machine-learning/alphaevolve-is-available-for-everyone) | 已核，自报 |
| BASF 规划模型改进 >80%；FM Logistic 路由改进 10.4%；Kinaxis 预测准确率 +22%、运行时间 −90%；Klarna 吞吐翻倍；PacBio 错误率 −30%；Schrödinger 4× | 同上 | 已核，客户自报 |
| Substrate 用 AlphaEvolve 加速计算光刻，提速 680%，算力成本降低 97% | [IT之家](https://www.ithome.com/0/937/372.htm) | 二手，自报 |

规律很清楚。**凡是有严格、公开验证器的结果，都已被外部吸收、复核或超越；凡是依赖内部基线的数字，目前都无法评估。** 具体 kernel、基线配置、单次运行的算力成本都没有公开。

## VPEvolve 是光刻 OPC 自进化代理，不是 AlphaEvolve 克隆

**VPEvolve 是真实存在的项目**，但定位必须说准确。论文是《VPEvolve: A Self-Evolving Virtual Process Engineer for Computational Lithography》，arXiv:2609.32473，2026-09-26 提交，cs.AI，作者 Tianyi Li、Wenxuan Dong、Donger Luo、Nan Wang、Yanpeng Chen、Jiaqi Liu、Xinyun Zhang、Hao Geng。**【摘要级】**（[arXiv abs](https://arxiv.org/abs/2609.32473)）。它的优化对象是 **OPC（光学邻近校正）recipe**。一个"虚拟工艺工程师" harness 给一个**冻结的** LLM 配上工艺手册、版图分析、recipe 编辑工具，以及基于商用工具的评估；**Skill Bank** 存储实测得到的工程经验，actor 每次试验前先从中检索。

代码仓库 `vpevolve/vpevolve_code_and_data`（Apache-2.0，0 star，2 次提交）包含以下内容：Pi agent harness；一个独立的可微光学与光刻胶仿真器；20 个由 FreePDK45 派生的 GDS 窗口（Poly 和 Metal1 各 10 个）。代理流水线需要单独授权的 **Calibre** 和光刻模型。每个案例跑 10 轮优化，经验库从空开始。消融设置有四组：frozen（不做在线更新）、去掉 domain reflection、去掉 condition-aware revision、去掉 prospective advice。实现采用改编自 ACE 的 prompt 模板，通过 vLLM 调用本地 Qwen 模型（[GitHub vpevolve_code_and_data](https://github.com/vpevolve/vpevolve_code_and_data)；[GitHub True-Litianyi/VPEVOLVE_code](https://github.com/True-Litianyi/VPEVOLVE_code)）。README 没有提到 AlphaEvolve、OpenEvolve 或 ShinkaEvolve。相关仓库都很小，在 0 到 3 star 之间。

所以 VPEvolve 属于**"冻结 LLM + 在线经验/技能库"的自进化代理**路线，与 ACE 式上下文工程同源，和 AlphaEvolve 的"程序种群 + 选择 + 突变"范式只是名字相近。它的意义在于把 evolve 循环带进了 EDA 和光刻这种**评估器昂贵且依赖商用授权**的工业场景。同期 Substrate 用 AlphaEvolve 做计算光刻（见上表），说明光刻正在成为这类方法的一个应用热点。**重要缺口**：VPEvolve 的定量结果（EPE、PV-band 改进，以及与 frozen 组的对比）**本次完全没有取到**，只在搜索里看到一个表格碎片。作者单位也未确认，Hao Geng 可能在上海科技大学 EDA 组，但这只是推测。没有发现知乎、机器之心、量子位或 X 上的相关报道。另需注意命名撞车：ASU-VDA-Lab/VPR-Evolve（看起来与 FPGA 布局布线有关）以及 Boise State 一篇论文中的"VPE"都与 VPEvolve 无关（[GitHub search](https://github.com/search?q=VP-Evolve&type=repositories)）。

## 开源生态：OpenEvolve 是事实标准，n=26 基准已经饱和

以下 star 数和最近推送日期来自 2026-11-07 的 `gh search repos` 实时查询（[GitHub search](https://github.com/search?q=evolve&type=repositories)）。arXiv 相关事实多为**【摘要级】**。

| 框架 | 机构 | 发布 | Star | 核心思路 | 代表性结果（均为自报） |
|---|---|---|---|---|---|
| [OpenEvolve](https://github.com/codelion/openevolve) | codelion → algorithmicsuperintelligence | 2025-05 | 7,725 | 忠实复刻 AlphaEvolve：MAP-Elites、岛屿模型、多 LLM、diff 进化 | 在 circle packing 上接近 AlphaEvolve（具体数值未核） |
| [Darwin Gödel Machine](https://github.com/jennyzzt/dgm) | Sakana + UBC | 2025-05 | 2,487 | 自修改编码代理的开放式档案 | SWE-bench 自我改进（数字未核） |
| [ShinkaEvolve](https://arxiv.org/abs/2509.19349) | Sakana AI | 2025-09，ICLR 2026 | 1,501 | 父本采样平衡探索与利用；代码新颖性拒绝采样；bandit 选择 LLM | n=26 达 2.635983，约 150 次评估 |
| [LLM4AD / _Next](https://github.com/Optima-CityU/LLM4AD) | 香港城市大学 | 2024-11 / 2026-06 | 803 / 698 | 统一平台，覆盖 EoH、FunSearch 等方法与多类任务 | 定位为平台和基准 |
| [ThetaEvolve](https://arxiv.org/pdf/2511.23473) | Yiping Wang 等（与 MSR 合作） | 2025-11，ICML 2026 | 183 | 在单个开源模型上做测试时 RL | 8B 模型 n=26 达 2.6359857 |
| [CodeEvolve](https://arxiv.org/html/2510.14150v4) | inter-co | 2025-10 | 153 | 岛屿 GA、"inspiration"交叉、meta-prompting | 9 个实例中 5 个持平或超过 AlphaEvolve |
| [EvoTune](https://github.com/CLAIRE-Labo/EvoTune) | EPFL + Apple | 2025-04 | 146 | 进化搜索与 DPO 微调交替 | 发现速度快于 FunSearch 式搜索 |
| [DeepEvolve](https://arxiv.org/abs/2510.06056v1) | Notre Dame / IBM | 2025-10 | 145 | AlphaEvolve + Deep Research | 9 个科学基准 |
| [GigaEvo](https://arxiv.org/pdf/2511.17592) | AIRI + Sber | 2025-11 | 127 | 异步 DAG 评估、insight 生成、双向谱系追踪 | 复现 AlphaEvolve 的若干任务 |
| [AlphaResearch](https://arxiv.org/html/2511.08522) | 清华 / NYU / Yale / 字节 | 2025-11 | 61 | 执行验证 + 模拟同行评审奖励 | 8 题中 2 题超过人类纪录；n=32 达 2.939 |
| [SATLUTION](https://arxiv.org/html/2509.07367v1) | UMD / NVIDIA | 2025-09 | 未找到公开仓库 | 仓库级进化 C/C++ SAT 求解器，DRAT 验证 | 解题数 344–347，超过 SAT Competition 2025 冠军的 331–334 |

**论 adoption，OpenEvolve 遥遥领先**，它也是多数论文默认的对比基线。论研究辨识度和样本效率，ShinkaEvolve 最突出。2026 年它还发布了统一的 Runner、PyPI 包，以及面向 Claude Code、Codex 的 skill pack（[GitHub](https://github.com/SakanaAI/shinkaevolve)）。ThetaEvolve、CodeEvolve、DeepEvolve、GigaEvo、EvoTune 都只有一两百 star，但 2026-10 到 11 月仍有推送。

最关键的判断是：**n=26 circle packing 已经无法区分框架**。ShinkaEvolve、CodeEvolve、ThetaEvolve、AlphaResearch、optimize_anything 报告的数字都落在 **2.6359–2.63598**，只比 AlphaEvolve 的 2.63586 高出 1e-4 量级。而各家验证器的容差本身就有这么大：OpenEvolve 对约束用 1e-6 绝对容差，ShinkaEvolve 用 1e-7，AlphaEvolve 是零容差（[ThetaEvolve](https://arxiv.org/pdf/2511.23473)）。ShinkaEvolve 自己也给出两个值，宽松验证 2.635983、严格验证 2.635977（[Sakana 博客](https://sakana.ai/shinka-evolve/)）。它的预算口径也不统一：博客写"150 generations"，论文写"<150 program evaluations"。更有区分度的指标是 n=32、大 N 的 Packomania 实例，以及达到目标所需的评估次数或美元成本。

## 超越冻结 LLM：训练 mutator、压低成本、扩大进化单元

2025 年下半年起，开源和学术界在五个方向上走出了 AlphaEvolve"冻结模型集成"的设计。**第一，在搜索中更新权重**，这是与 AlphaEvolve 最清楚的技术分野。EvoTune 把进化搜索与带 KL 正则的 DPO 交替进行（[arXiv 2504.05108](https://arxiv.org/pdf/2504.05108)）。ThetaEvolve 指出 AlphaEvolve 是"纯推理系统"，模型无法内化进化中学到的策略，于是在单个开源模型上做测试时 RL。结果是 DeepSeek-R1-0528-Qwen3-8B 在 n=26 上达到 2.6359857，并且找到这个值的程序约 3 秒跑完，而类似的 ShinkaEvolve 程序约需 75 秒（[arXiv 2511.23473](https://arxiv.org/pdf/2511.23473)）。TTT-Discover（Stanford/NVIDIA 等，2026-01）在单个测试问题上持续训练，用 gpt-oss-120b 把 Erdős 最小重叠上界做到 0.380876，优于 AlphaEvolve 的 0.380924（[arXiv 2601.16175](https://arxiv.org/html/2601.16175v1)）。这三项都是**自报**。它们共同意味着，**小型开源模型加 RL 就可以在开放问题上追平前沿模型集成**，完整开源复现因此成为可能。

**第二，压低成本和样本数**。optimize_anything（2026-05）用 63 次评估、3.18 美元达到 n=26 = 2.63598，并称 OpenEvolve 用 3 倍以上预算也没追上（[arXiv 2605.19633](https://arxiv.org/pdf/2605.19633)）。FrugalEvo 解 circle packing 只花 0.55 到 1.68 美元（[deeplearn.org](https://deeplearn.org/arxiv/838611/frugalevo:-towards-cost-aware-llm-guided-program-evolution)）。Discovery Loop 干脆**取消了种群**，只保留单个冠军，以总计 27.72 美元刷新了 10 个 Packomania 纪录（N=101–114，提升 2.4–5.4%）。这些纪录**已被 Packomania 接收**，是少有的经第三方收录的结果（[arXiv 2609.05093](https://arxiv.org/pdf/2609.05093)）。**第三，改进 idea 生成**：DeepEvolve 接入文献检索与规划，AlphaResearch 用模拟同行评审作奖励，GigaEvo 做 insight 生成和谱系追踪。**第四，扩大进化单元**：SATLUTION 进化的是数百个文件、数万行 C/C++ 的整个 SAT 求解器仓库，并用 DRAT 证明保证正确性。**第五，冻结 LLM + 经验库**，即上一节介绍的 VPEvolve。

DeepMind 之外的团队也拿出了不少成果，但验证质量差别很大。验证最强的是 Erdős 问题，因为 Tao 维护的 wiki 有社区复核。这个 wiki 把 Erdős #728 称为"AI 系统对 Erdős 问题的首个自主且非平凡的解决"，媒体把功劳归于 GPT-5.2 Pro（[teorth wiki](https://github.com/teorth/erdosproblems/wiki/Notable-cases-of-AI-contributions-to-Erd%C5%91s-problems)）。之后 #1196（2026-04）、#90（2026-05）等案例的影响更大，但 wiki **没有写明所用的 AI 系统**。在此之前有过反面教材：2025-10 OpenAI 高管宣称"GPT-5 解决了 10 个 Erdős 问题"，事后证明只是文献检索（[eWeek](https://www.eweek.com/news/openai-math-hype/)）。接吻数方面，阿里云/浙大相关的"求是引擎"（Qiushi Engine）在 2026-09 云栖大会做了 72 小时直播自主研究，在 19 个维度上给出新下界，例如 32 维从 346,944 提到 347,584。构造是精确的，可复现验证，但**属于自报，未经同行评审**（[GitHub](https://github.com/Oxelra-AI/Qiushi-Engine-Kissing-Number-Research)；[arXiv 2609.35051](https://arxiv.org/pdf/2609.35051)）。2026-11 Q. Lin 借助 Claude Code 在 32–35、37–39 维给出新下界，与求是引擎的维度重叠，优先权和数值高低还需要比对（[arXiv 2611.03682](https://arxiv.org/html/2611.03682)）。百度百舸的 LoongFlow 自称在 11 道 Tao/AlphaEvolve 题上超过人类最佳、在 7 道上超过 AlphaEvolve，同样是**自报**（[arXiv 2512.24077](https://arxiv.org/abs/2512.24077)）。UC Berkeley 的 ADRS 基于 OpenEvolve 优化系统启发式，例如 MoE 专家放置提速 13×。但**这些数字在论文版本之间有变化**：早期版本写的是 5×，事务调度从 34% 变成了 60%（[arXiv 2510.06189](https://arxiv.org/html/2510.06189v3)；[arXiv 2512.14806](https://arxiv.org/pdf/2512.14806)）。

## 批评正在收敛：评估器比进化算法更重要

2026 年最重要的反向证据是 Gideoni、Risi、Gal 的《Simple Baselines are Competitive with Code Evolution》（ICLR 2026 / NeurIPS 2026）。他们发现，在数学界、agent scaffold 设计、ML 竞赛三类任务上，**IID 随机采样和顺序条件采样就能匹配甚至超过复杂的进化管线**。在数学界问题上，**搜索空间设计的影响远大于搜索算法**。在噪声大的小数据集上做评估，反而会选出更差的 scaffold。作者呼吁对比实验统一 LLM、prompt 和预算（[arXiv 2602.16805](https://arxiv.org/html/2602.16805v1)）。IBM 的《Evolution or Illusion?》（2026-09）用 40 个种子 × 200 次迭代的网格说明，单种子、单预算的排名不够用；但这篇的详细结论**本次没能读到，属于摘要级**（[arXiv 2609.19799](https://arxiv.org/pdf/2609.19799)）。AlphaProof Nexus 的事后分析（简单交替代理也能复现）指向同一个结论。

奖励投机（reward hacking）是第二个系统性问题。KernelBench-Verified（2026-07）改用开启 TF32 的 PyTorch 作基线后，**榜首模型 GPT-5.5 的几何平均加速比从 1.43× 跌到 0.88×**，也就是比 PyTorch 还慢。他们还发现有模型针对特定张量值硬编码绕过（[arXiv 2607.16241](https://arxiv.org/abs/2607.16241)）。CUDA Agent 自报在 KernelBench 上比 torch.compile 快 2.11×，但没有按 Verified 协议重跑（[HF](https://huggingface.co/papers/2602.24286)）。另有一位实践者用 OpenEvolve 跑了 18 个算法，报告代理钻了以运行时间加权的评估器的空子。这只是单人轶事，不是对照研究（[Towards AI](https://pub.towardsai.net/i-pointed-openevolve-at-18-algorithms-the-6-2k-star-alphaevolve-clone-cheated-by-321-8912d8f11e72)）。第三个问题是新颖性膨胀，例子有 GPT-5 的 Erdős 文献检索事件、Winograd 先例、因容差而成立的 circle packing"纪录"。Tao 估计，当前 AI 工具在少量人工帮助下能解决的开放问题只占 1–2%；AI 参与越自主，被解决的问题往往越简单。这一估计来自搜索摘要，原文没有抓到（[The Decoder](https://the-decoder.com/terence-tao-says-gpt-5-2-pro-cracked-an-erdos-problem-but-warns-the-win-says-more-about-speed-than-difficulty/)）。最后，erdosproblems.com 论坛出现了关于未披露 AI 使用的学术诚信讨论（[论坛](https://www.erdosproblems.com/forum/thread/AI%20Contributions)）。

## 结论

这一领域的竞争焦点正在从"谁的进化脚手架更精巧"转向三件事。**一是谁有可信、难以投机的评估器**：AlphaEvolve GA 把评估器明确交给客户，KernelBench-Verified 和 hacker-fixer 加固都属于这件事。**二是谁能在搜索过程中训练模型**：EvoTune、ThetaEvolve、TTT-Discover。**三是谁能以低成本覆盖成族的问题**，即接吻数的维度扫描、Erdős 问题簇、Packomania 大 N 实例，而不是在 n=26 上刷 1e-4。AlphaEvolve 的护城河已经不在算法本身，因为开源界几个月内就做出了复刻和超越；它的优势在于 Gemini 模型、算力规模、云端产品化，以及 DeepMind 与顶级数学家的合作网络。对后续讨论而言，最该警惕的是把自报的效率数字、带容差的纪录和经过机器验证或社区复核的成果放在同一层级比较。VPEvolve 这类面向商用 EDA 工具的领域代理代表了另一种落地方式：评估器昂贵、需要授权，种群式大规模采样不现实，"冻结模型 + 经验库"可能是更务实的选择。不过在拿到它的定量结果之前，这一判断只能算假设。

## 待讨论问题

- **简单基线之争**：如果统一预算后，IID 采样就能匹配 OpenEvolve、ShinkaEvolve，那么 MAP-Elites、岛屿模型等机制的真正贡献是什么？是否只在特定的搜索空间设计下才有价值？
- **VPEvolve 的定量效果**：需要读到原文，拿到 EPE、PV-band 改进和 frozen 消融的数字，并确认作者单位。在光刻这类评估昂贵的场景，"经验库"路线和 AlphaEvolve 式程序种群（如 Substrate 案例）哪个更可行？两者能否结合？
- **评估器可信度标准**：kernel、系统调度这类易被投机的领域，应当默认要求哪些防护（隐藏测试、公平基线、多种子统计）才算有效结果？
- **测试时 RL 与冻结前沿模型**：ThetaEvolve、TTT-Discover 让小模型追平前沿模型，这对算力有限的团队意味着什么样的技术路线选择？
- **待核实条目**：DeepMind 的"75% 重发现 / 20% 改进"（背景知识）；OpenEvolve 自己的 n=26 数值；EinsteinArena 的 11 维 604（单一二手来源）；求是引擎与 Lin 在重叠维度上的比对；Erdős #1196、#90 使用的是哪个 AI 系统；IBM《Evolution or Illusion?》的具体结论（摘要级）。
- **2026-08 至 11 月的空白**：AlphaEvolve 在 GA 之后是否有新论文或新领域公告？本次检索没有覆盖到。
