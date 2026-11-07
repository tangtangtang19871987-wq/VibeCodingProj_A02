# 光刻自演化智能体仍缺一个 LangGraph 版本

截至 2026-11-07，**我们没有找到任何基于 LangGraph（或 LangChain）的计算光刻（ILT/OPC/SMO）自演化代码智能体**，论文和 GitHub 上都没有。GitHub 搜 "langgraph lithography" 得到 0 个仓库。离 ILT 最近的自演化系统是 **VPEvolve**（arXiv 2609.32473，2026-09），它在 Calibre 上进化 OPC recipe，并用 Skill Bank 积累实测经验。但它运行在 **Pi coding-agent harness**（`@earendil-works/pi-coding-agent`）上，配本地 Qwen 模型，**不是 LangGraph**。把范围放宽到 EDA、TCAD、CFD/FEA、光子逆设计、PLC 以后，格局很清楚：LangGraph 的确被大量采用（Foam-Agent、PDE-Agents、ChemGraph、CoreSmith、SiliconCrew、ORAssistant、EDA Pilot），但几乎都用来做**可审计的流程编排和单任务内的"执行→报错→修复"循环**。真正**跨任务**的自演化，包括 skill 文件进化、程序进化、经验库和 RL，出自自定义循环或 Codex CLI / Claude Code / Pi 这类 coding-agent 运行时。LangChain 官方的自我改进也有意放在"上下文层"（memory、skills、prompt 优化），没有发布 AlphaEvolve 或 DGM 式模板。这意味着 LangGraph 版 ILT 自演化智能体在公开文献中仍是空白。可借鉴的部件都已齐备：VPEvolve 的 actor→评估→reflector→curator→skill bank 闭环，metasurface MCE 的"固定求解器、只进化 skill 文件、按验证集择优"，Ptychi-Evolve 的固定接口代码槽位，以及 LangGraph 的 checkpointer、Store、`Send`、`interrupt()`。建议的路线是：用 OpenILT/LithoBench 作确定性评估器，搭"内环逐 clip 修复 + 外环 skill/代码演化 + held-out 门控 + 人工审批中断"的两环结构。

> **证据等级约定。** 【已核-代码】＝研究者直接读过仓库源码、README、依赖文件或结果 JSON。【摘要级】＝只读到 arXiv 或官方页面的搜索摘要，没读全文（本次会话 arxiv.org、alphaxiv.org、blog.langchain.com 均被网络策略封锁）。【二手】＝聚合站、博客或 AI 生成的评述。【背景】＝研究者已有知识或本对话早先的检索，本轮没有重新核对。**框架归属**分四档：**LangGraph 已确认**（源码或论文明确写出）、**LangGraph 仅描述级**（只有仓库描述或标签）、**其他框架已确认**、**未知**。

## 光刻领域唯一的自演化系统跑在 Pi harness 上

**VPEvolve: A Self-Evolving Virtual Process Engineer for Computational Lithography**（Tianyi Li、Wenxuan Dong、…、Hao Geng，2026-09-26 提交，预印本，无会议信息）是目前与 ILT 最接近的自演化智能体 ([arXiv](https://arxiv.org/abs/2609.32473))【摘要级】。它的 harness 给一个**冻结的 LLM** 四种能力：查工艺手册、分析版图、编辑 recipe、调用商业工具评估。每次实测 trial 之后，LLM **reflector** 和 **curator** 把结果整理成"与证据挂钩的判断"写入 Skill Bank，**actor** 在下一次 trial 前检索这些判断。只有可行的改进才更新保留的 recipe。整个过程不训练、不做 RL，模型权重不变。

框架归属已在代码层面核实。`package.json`（包名 "vpevolve-pi-runtime"）只依赖 `@earendil-works/pi-coding-agent` 0.85.1。`pyproject.toml` 把项目描述为 "Evidence-guided OPC recipe evolution with a Pi agent harness"，Python 依赖只有 numpy 和 klayout。仓库内置 `pi/*.ts` harness 文件和 `skills/*.md`，还 vendor 了 ACE（Agentic Context Engineering）的 prompt。代码搜索没有发现 langgraph 或 langchain 的引用 ([package.json](https://raw.githubusercontent.com/True-Litianyi/VPEVOLVE_code/main/package.json)，[pyproject.toml](https://raw.githubusercontent.com/True-Litianyi/VPEVOLVE_code/main/pyproject.toml))【已核-代码】。每次运行都从**空的经验库**起步，只带固定的工程指导；recipe 本身同时接受全局编辑和局部规则编辑 ([README](https://raw.githubusercontent.com/True-Litianyi/VPEVOLVE_code/main/README.md))。评估器是授权的 **Calibre**（`calibre`、`pdl_lib_mgr`）加光学/光刻胶模型，测试集是 20 个 FreePDK45 派生的 GDS 窗口（Poly、Metal1 各 10 个）。仓库附带一个独立的可微光刻仿真器，但 README 明确说它不能替代商业 OPC 流程 ([README](https://raw.githubusercontent.com/vpevolve/vpevolve_code_and_data/main/README.md))。

定量结果来自项目公开的结果文件【已核-代码】。在每个 case 10 次 trial 的预算下，窗口最大 EPE 的均值在 **Poly 上从 18.294 nm 降到 5.361 nm**，在 **Metal1 上从 22.052 nm 降到 15.692 nm**；PVB 基本不变（6.148→6.210 ×10⁻³ µm（单位按结果文件原样））([final-results.json](https://raw.githubusercontent.com/vpevolve/vpevolve/main/assets/current/final-results.json))。同预算下的基线对比和消融如下：

| 方法（10 trial/case） | Poly max EPE (nm) | Metal1 max EPE (nm) | 说明 |
|---|---:|---:|---|
| **VPEvolve（完整）** | **5.36** | **15.69** | 20/20 通过终点复核 |
| ReAct | 16.50 | 17.77 | |
| ACE | 16.70 | 19.92 | playbook 式上下文演化 |
| raw history | 17.27 | 19.61 | |
| textual feedback | 17.30 | 18.97 | |
| ReasoningBank | 17.52 | 20.54 | |
| static | 17.58 | 19.88 | |
| Bayesian optimization | 17.91 | 21.77 | 仅 6/20 达标 |
| 消融：Frozen experience | 8.08 | 16.12 | 经验不再在线更新 |
| 消融：无 domain reflection | 6.21 | 16.28 | |
| 消融：无 condition-aware revision | 5.47 | 16.33 | |
| 消融：无 prospective advice | 5.87 | 16.15 | |

这组数字说明三件事。第一，增益几乎全部来自**在线、与证据挂钩的经验积累**：冻结经验后 Poly 退步约 2.7 nm，而 ACE、ReasoningBank 这类通用记忆方案几乎没有超过 static recipe。第二，改善集中在**最坏情况 EPE**，PVB 没有动，所以它是"修热点"，还没到"扩工艺窗口"。第三，成本可以算清：完整方法每层（10 个 case）约用 **120 次 OPC 调用、643–652 次 LLM 调用** ([final-results.json](https://raw.githubusercontent.com/vpevolve/vpevolve/main/assets/current/final-results.json))。也就是每次昂贵的仿真大约配 5 次 LLM 调用。这个比例很适合图编排：LLM 开销不是瓶颈，仿真才是。

ILT 方向的其他线索更弱。**NanWang-EE 的 "MASK / Agent Lab"**（2026-10，作者 Nan Wang 也是 VPEvolve 合著者）展示了一个像素级 ILT 掩模优化的 agent 循环：observe→propose→simulate→accept/rollback，共 15 轮，用 **OpenILT 评估器**（EPE 阈值 15 nm，另算 L2 和 PVB，PVB 上限为目标的 1.6 倍）。但它只有结果网站，没有 agent 代码，框架**未知** ([README](https://raw.githubusercontent.com/NanWang-EE/agent-mask-optimization-site/main/README.md))【已核-代码，仅站点】。**Intelligent OPC Engineer Assistant**（CUHK/NVIDIA，arXiv 2408.12775）先用 PPO 搜 OPC recipe，再由多模态 LLM 总结成 recipe。二手来源给出的 EPE 改善数字互相矛盾（8–13% / 12–24%），框架**未知**，自我改进靠 RL 而不是 agent 记忆 ([arXiv](https://arxiv.org/abs/2408.12775)，[Moonlight](https://www.themoonlight.io/review/intelligent-opc-engineer-assistant-for-semiconductor-manufacturing))【摘要级/二手】。**LithoDreamer**（ICML 2026）是物理先验的多阶段光刻 world model，**不是 LLM agent** ([ICML](https://icml.cc/virtual/2026/poster/63279))【摘要级】。本对话早先的检索也确认 ILT 里没有 AlphaEvolve 式工作。最近的是学习型掩模生成器：LithoGRPO ([2606.00228](https://arxiv.org/abs/2606.00228))、Yang & Ren 的生成式 RL ILT ([2602.19027](https://arxiv.org/html/2602.19027v1))、MorphOPC ([2605.12528](https://arxiv.org/abs/2605.12528))【背景】。它们优化的是模型权重，不是代码或 skill。

## LangGraph 在工程领域是流程编排器，不是演化引擎

LangGraph 的工业采用面很广，但"自演化"的深度很浅。下表按框架归属列出各领域代表系统；"自演化机制"一列刻意区分**单任务内修复**和**跨任务持续改进**。

| 系统 | 领域 | 框架归属 | 自演化机制 | 评估器/仿真器 | 定量结果 | 验证等级 |
|---|---|---|---|---|---|---|
| Foam-Agent ([2505.04997](https://arxiv.org/abs/2505.04997)，[v2](https://arxiv.org/html/2509.18178v2)) | CFD | **LangGraph 已确认**（论文原文）；v2 改为 MCP | 单任务内：reviewer 诊断求解器报错→修复 | OpenFOAM | 成功率 83.6%→88.2%（Claude 3.5 Sonnet），MetaOpenFOAM 55.5% | 摘要级 |
| PDE-Agents ([2606.07850](https://arxiv.org/pdf/2606.07850)) | FEM | **LangGraph 已确认**（supervisor + 3 agent） | 跨任务：Neo4j GraphRAG 存失败模式与运行历史 | FEM 求解器 | 1,369 次真实运行，97.8% 成功 | 摘要级 |
| ChemGraph ([2506.06363](https://arxiv.org/pdf/2506.06363)) | 计算化学 | LangGraph（背景知识，摘要只描述图结构） | 无持续演化，仅任务分解 | ASE/xTB/MACE/DFT | 13 个基准任务 | 摘要级+背景 |
| CoreSmith（Meta）([README](https://raw.githubusercontent.com/facebookexperimental/coresmith/main/README.md)) | RTL→GDS | **LangGraph 已确认** | 单任务内：debug agent 诊断后重试 | Verilator/Yosys/OpenROAD | 未报告 | 已核-代码 |
| SiliconCrew ([README](https://raw.githubusercontent.com/naman-ranka/siliconcrew/main/README.md)) | RTL→GDS | **LangGraph 已确认** + MCP | 单任务内 fix-verify | CVDP（92 题）、OpenROAD | 65.2% leak-gated pass@1 | 已核-代码 |
| EDA Pilot ([README](https://raw.githubusercontent.com/NileshModlier/EDA-Pilot-Agentic-AI/main/README.md)) | 时序收敛 | **LangGraph 已确认** + MCP | 仅运行内搜索 | ORFS Sky130HD | 通过时钟比随机搜索紧 14.5–30.3%，面积 +7–23% | 已核-代码 |
| ORAssistant ([retriever_graph.py](https://raw.githubusercontent.com/The-OpenROAD-Project/ORAssistant/master/backend/src/agents/retriever_graph.py)) | OpenROAD 问答 | **LangGraph 已确认** | 无 | 人工评估 | — | 已核-代码 |
| TurboAgent、MD-Simulation-Agent、Agentic-Robo-SWE、MechAgent 等 ([TurboAgent](https://github.com/wuyueteng/TurboAgent-prompts)) | 叶轮/MD/机器人 | **LangGraph 仅描述级** | 代理模型辅助优化或无 | CFD/仿真 | — | 仅仓库元数据 |
| VPEvolve ([arXiv](https://arxiv.org/abs/2609.32473)) | **OPC recipe** | **Pi harness（非 LangGraph）已确认** | 跨任务：Skill Bank + reflector/curator | Calibre | max EPE 18.29→5.36 nm（Poly） | 已核-代码 |
| GR-Evolve ([2604.22234](https://arxiv.org/abs/2604.22234)) | 全局布线 C++ | **Codex CLI 已确认** | 遗传循环改 OpenROAD 源码 | OpenROAD，7 设计×3 节点 | 绕线长度最多 −8.72% | 摘要级+代码 |
| GoalEvolve ([README](https://raw.githubusercontent.com/CODA-Team/GoalEvolve/main/README.md)) | PD 算法 C++ | **Codex CLI 已确认**（Teacher/Student） | mechanism card 检索 + 证据记忆 + 晋升 | OpenROAD ASAP7 | 未取到 | 已核-代码 |
| EvoDRC ([README](https://raw.githubusercontent.com/ASU-VDA-Lab/EvoDRC/main/README.md)) | DRC 修复 | **Claude Code 已确认** | 分层 repair skill 从经验中演化 | DAC26 DRC 基准 | 未取到 | 已核-代码 |
| Metasurface MCE ([2604.01480](https://arxiv.org/abs/2604.01480)，[LPOR](https://onlinelibrary.wiley.com/doi/full/10.1002/lpor.71739)) | **光子逆设计** | **自定义 harness 已确认** | meta-agent 改写 skill 文件，按验证集择优 | TorchRDIT（可微 RCWA） | 成功率 38%→74%，尝试次数 4.10→2.30 | 摘要级 |
| Ptychi-Evolve ([2603.05696](https://arxiv.org/abs/2603.05696)) | 叠层成像逆问题 | **自定义已确认** | 语义交叉/变异进化正则项代码 | Pty-Chi，SSIM/PSNR | 最多 +0.26 SSIM / +8.3 dB | 摘要级 |
| LLaMEA 光子学 ([2503.19742](https://arxiv.org/pdf/2503.19742)) | 多层膜逆设计 | **自定义已确认**（LLM+ES） | 进化优化器代码 | 传输矩阵 | 小规模演化出的算法在大规模问题上追平或超过 QODE | 摘要级 |
| AgenticTCAD ([2512.23742](https://arxiv.org/html/2512.23742v1)) | TCAD | **未知** | 微调 TCAD 代码模型 | Sentaurus 类脚本 | 2 nm NS-FET 达标 4.2 h vs 人工 7.1 天 | 摘要级 |
| czf-mq/agentic-tcad ([README](https://raw.githubusercontent.com/czf-mq/agentic-tcad/main/README.md)) | TCAD | **自定义已确认**（OpenAI SDK） | 运行内优化 | DEVSIM+Gmsh | 首个可行设计约 5 次评估 vs 约 11 次（约束 BO） | 已核-代码 |
| Agents4PLC ([2410.14209](https://arxiv.org/abs/2410.14209v2)) / LLM4PLC ([2401.05443](https://arxiv.org/html/2401.05443v1)) | PLC ST | **未知** / 自定义 | 编译 + 模型检查闭环；LLM4PLC 可人工介入 | MATIEC/NuSMV 类 | 未取到数字 | 摘要级 |
| PFAgent ([2604.10846](https://arxiv.org/html/2604.10846v1)) | 潮流计算 | **未知** | 已验证失败→prompt/规则更新，人在环 | ANDES | 缺数字 | 摘要级 |
| AutoFOAM ([2608.00003](https://arxiv.org/pdf/2608.00003)) | CFD | 自定义（微调 Qwen2.5-Coder-14B） | 七层自训练循环 + 防崩塌措施 | OpenFOAM | 自称 100% 执行成功 | 摘要级（日期不一致） |
| FEABench ([2504.06260](https://arxiv.org/abs/2504.06260v1)) | COMSOL FEA | 自定义 | 执行反馈修复 | COMSOL | 88% 可执行，**0 题完全求解** | 摘要级 |

规律很明显。被确认使用 LangGraph 的系统，除 PDE-Agents 的 GraphRAG 运行历史外，都没有跨任务持久演化。它们看重的是 LangGraph 的阶段门控、人工审核停靠点和条件重试边。2026 年 EDA 领域的自演化研究则整体转向 coding-agent CLI：GR-Evolve、GoalEvolve 用 Codex，EvoDRC、ResizerAgent 用 Claude Code，VPEvolve 用 Pi。自我改进的载体是文件（AGENTS.md、skills/*.md、mechanism card、证据日志），而不是图状态。光子和逆问题里最强的自演化结果（MCE 38→74%、Ptychi-Evolve +8.3 dB、LLaMEA）也都出自自定义循环。原因有两个推断。其一，coding-agent CLI 自带文件系统、shell 和 skill 加载，"改文件即演化"零成本。其二，进化搜索要做成千上万次评估，LangGraph 每步 checkpoint 的额外价值不大；所有成熟的进化代码系统（OpenEvolve ★7.7k、ShinkaEvolve、DGM）都用自定义 asyncio 循环，GitHub 上搜 "langgraph alphaevolve / openevolve / map-elites / dgm" 全部返回 0 个仓库 ([OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve)，[DGM](https://github.com/jennyzzt/dgm))【已核-代码】。

## LangChain 官方只做上下文层的自我改进，社区演化原型都不足 110 星

LangChain 官方生态有成熟的单任务自修正和跨会话记忆，但没有发布进化式或自改写代码的智能体。官方 code assistant 教程（仿 AlphaCodium）的图是 `generate → check_code → decide_to_finish → {end, reflect, generate}`，`max_iterations=3`。它自己的评测结论值得 ILT 设计者记住：**重试循环有用，但"先反思再重试"反而比直接把报错回传给 LLM 更差** ([notebook](https://github.com/langchain-ai/langgraph/blob/23961cff61a42b52525f3b20b4094d8d2fba1744/docs/docs/tutorials/code_assistant/langgraph_code_assistant.ipynb))【已核-代码】。LATS 教程在图状态里维护树，每次扩展从 UCB 最高的节点生成 N=5 个候选，并指出代码合成可以直接用执行结果作奖励 ([notebook](https://github.com/langchain-ai/langgraph/blob/23961cff61a42b52525f3b20b4094d8d2fba1744/docs/docs/tutorials/lats/lats.ipynb))。**Deep Agents**（★31k，基于 LangGraph）提供 sub-agent、文件系统、shell、持久记忆后端、按需加载的 Skills 和 HITL ([README](https://github.com/langchain-ai/deepagents))。**open-swe / Robin**（★11k）能"学习仓库特定的 review 偏好" ([README](https://github.com/langchain-ai/open-swe))。**LangMem**（★1.75k）提供与 LangGraph Store 原生集成的 prompt 优化器，有 gradient、metaprompt、prompt_memory 三种策略 ([README](https://github.com/langchain-ai/langmem))【已核-代码；策略细节摘要级】。二手转述称，Harrison Chase 2026-04 的文章把持续学习分成模型、harness、上下文三层，并认为生产收益主要来自上下文层 ([claw-times 摘要](https://claw-times.pages.dev/articles/langchain-continual-learning-openclaw-soul-md-agent-memory/))【二手】。这正好解释了为什么官方没有 DGM 或 AlphaEvolve 式模板。

真正做开放式自演化的 LangGraph 项目都是社区原型。**HyperFlow**（★9，"EXPERIMENTAL"）是最接近 DGM/HyperAgents 的 LangGraph 实现：JSONL archive → 选父代 → MetaAgent 改源码/工具/prompt → Docker 沙箱评估 → 入库。它的进化主循环 `core/generate_loop.py` 是**普通 Python 外环**，LangGraph 只做内层 ReAct agent ([README](https://github.com/lablnet/HyperFlow))【已核-代码】。**self-evolving-langgraph**（★1，alpha）每代由 architect 提出 3 个候选图拓扑和节点 prompt，用确定性评估器（退出码、stderr、产物文件）选出冠军 ([README](https://github.com/kooroshIM99/self-evolving-langgraph))。另外还有 ACE 的 LangGraph 复现 ace-langgraph（★45，单次提交 demo）([README](https://github.com/pingcy/ace-langgraph))、带 Voyager 式累积 skill 库的 I.S.A.A.C（★2，作者自承基准数字尚未证实）([README](https://github.com/Matheussoranco/I.S.A.A.C))、岛模型 GA 的 Mind-Evolution-PoC（★0）([README](https://github.com/AlanoHater/Mind-Evolution-PoC))，以及 MAP-Elites 进化 agent 配置的 qd-langchain-agents（★17）([README](https://github.com/FareedKhan-dev/qd-langchain-agents))。唯一明确用 LangGraph 的相关论文 arXiv 2502.18465 做的是带 ChromaDB 记忆的迭代修 bug，不是演化 ([arXiv](https://arxiv.org/abs/2502.18465))【摘要级】。成熟度呈两极：官方项目活跃但只做有界的自我改进，开放式演化项目都不到 10 星。

## 六种图模式从有界修复延伸到开放式演化

把所有系统的循环结构抽象出来，会反复出现六种模式。它们按成本和风险递增排列，ILT 智能体应该**按需叠加**，而不是一步到位。

| # | 模式 | LangGraph 原语 | 代表 | 收益 | 主要风险 |
|---|---|---|---|---|---|
| 1 | 生成→执行/测试→（反思）→重生成，带迭代上限 | 条件边 + 计数器 | 官方 code assistant、Foam-Agent、CoreSmith | 便宜、稳定；修复执行错误 | 单独的反思步可能有害；不跨任务 |
| 2 | 主 agent ↔ critic 子图 | 子图 + 终止条件 | langgraph-reflection、CADSmith（换更强模型当 judge） | 简单 | 质量取决于 critic，可能空转 |
| 3 | 候选树搜索（扩展 + 打分 + UCB 回传） | 状态里存树 + `Send` 扇出 | LATS 教程、langgraph-reflection-agent | 难题上质量更高 | 调用量成倍增加 |
| 4 | 运行后 reflector → curator → 持久经验库/skill | Store / checkpointer | **VPEvolve**、ACE、EvoDRC、PDE-Agents、Deep Agents Skills | 跨任务积累；VPEvolve 的主要增益来源 | 记忆漂移；PDE-Agents 发现"集成方式而非知识内容"决定记忆是帮还是害 |
| 5 | 基于 trace 的 prompt 优化节点 | 独立节点 + Store | LangMem、PFAgent | 无需改代码 | gradient 策略成本高；可能过拟合 |
| 6 | 外层进化循环（archive→选父→变异代码/prompt/拓扑→沙箱评估→入库） | 通常是 Python 外环包裹 LangGraph 内环 | HyperFlow、self-evolving-langgraph、Ptychi-Evolve、GR-Evolve、MCE 外环 | 能发现新算法组件 | 评估器被钻空子、回归、算力最贵 |

跨领域还有四条横切经验。第一，**确定性评估器胜过 LLM judge**：官方教程的反思结果、self-evolving-langgraph 的退出码评分、MCE 的确定性评估器、PLC 的形式化模型检查都说明这一点 ([MCE](https://arxiv.org/abs/2604.01480)，[LLM4PLC](https://arxiv.org/html/2401.05443v1))。第二，**固定接口的代码槽位**：MCE 让 LLM 只写 `solve_inverse_design()`，Ptychi-Evolve 只写 Pty-Chi `Object` 类的方法，物理求解器保持只读可信 ([Ptychi-Evolve](https://arxiv.org/html/2603.05696))。第三，**按验证集择优**：MCE 外环修改 skill 后只保留验证集上最好的版本，但 v1 在 held-out 族上的二值成功率只有边际变化 ([LPOR](https://onlinelibrary.wiley.com/doi/full/10.1002/lpor.71739))，说明泛化是最弱的一环。第四，**多保真度级联**：Grid-Mind 按 pandapower → ANDES → ParaEMT 逐级升保真 ([arXiv](https://arxiv.org/html/2602.20683))，LLaMEA 在小实例上演化、再迁移到大实例 ([arXiv](https://arxiv.org/pdf/2503.19742))。另外，FEABench 显示 agent 对商业工具 API 的事实性很差，COMSOL 题 0 道完全求解 ([Google Research](https://research.google/pubs/feabench-evaluating-language-models-on-real-world-physics-reasoning-ability/))。如果将来接入 Calibre 或 Proteus，必须配 API 文档检索和 tool-lookup 步骤。

## 一个 LangGraph 版 ILT 自演化智能体的架构草图

下面是基于上述证据的**设计提案，不是已验证系统**。核心判断是：**演化什么**比**用什么框架**更重要。VPEvolve 证明了经验/skill 演化在 OPC 上有效（冻结经验退步 2.7 nm），Ptychi-Evolve 和 MCE 证明了固定槽位的代码演化在逆问题上有效。因此 ILT 智能体分三层演化，按风险从低到高逐步开放：(a) skill bank，即按图形类别（line/space、contact、SRAF 策略、拐角/线端）沉淀的经验卡片；(b) 固定签名的代码槽位，演化对象是 ILT 的 loss 组合、正则项（curvature、TV）、步长/退火 schedule、二值化与 SRAF 启发式；(c) 超参数和 recipe。物理部分保持冻结：Hopkins/SOCS 光学核、光刻胶模型、指标代码、目标版图都放在 agent 写权限之外。

评估器选 **OpenILT**（开源 ILT 框架，ASICON 2023）和 **LithoBench**（NeurIPS 2023 D&B，超过 12 万 tile）([OpenILT](https://www.cse.cuhk.edu.hk/~byu/papers/C179-ASICON2023-OpenILT.pdf)，[LithoBench](https://proceedings.neurips.cc/paper_files/paper/2023/file/604b9fa9e1c16284e6517d923cf9ff20-Paper-Datasets_and_Benchmarks.pdf))。指标向量分开报告 L2、PVB、EPE 违例数（OpenILT 惯例阈值 15 nm）、最大 EPE、MRC 违例和运行时间，并带上相对冠军的 margin。VPEvolve 的经验是，最坏情况 EPE 才是自演化最能拉开差距的指标。MCE 的经验是，只看二值通过率会掩盖部分迁移。

```
                    ┌──────────────── 外环 EvolveGraph（每代一次）────────────────┐
                    │                                                              │
 [load_champion] → [propose_variants] ──Send×K──▶ [inner_ilt_subgraph(train clips)]
                    │      ▲  (meta-agent: 改 skill 卡片 / 代码槽位 diff)            │
                    │      │                                     ▼                  │
                    │  [curate_skills] ◀── [reflect_on_traces] ◀─ [aggregate_scores] │
                    │                                              │                 │
                    │                             [heldout_gate(frozen val clips)]   │
                    │                                    │pass            │fail      │
                    │                         interrupt("approve_promotion")  [rollback]
                    │                                    ▼                           │
                    │                         [promote → Store: skills@vN, code@vN]  │
                    └──────────────────────────────────────────────────────────────┘

 内环 inner_ilt_subgraph（每个 clip）：
 [retrieve_skills_and_nearest_clips] → [generate_or_patch_code] → [static_policy_check]
   → [fast_sim (GPU/低阶 SOCS, OpenILT)] → [validity_gate: MRC/轮廓合法/目标未改]
   → (可选 interrupt("approve_licensed_run") → [rigorous_sim (Calibre/TorchLitho 全核)])
   → [evaluate: L2/PVB/EPE/maxEPE/MRC/runtime] → 条件边: retry≤N 直接回传报错 | accept
```

关键接口可以写成如下骨架（API 名称遵循 LangGraph 的 `StateGraph`、`Send`、`interrupt`、checkpointer、`BaseStore`，具体签名以当前文档为准）：

```python
class ILTState(TypedDict):
    clip_id: str; target_path: str            # 只读
    code: str                                 # 槽位: optimize_mask(target, litho, cfg) -> mask
    skill_ids: list[str]; skill_version: str
    metrics: dict                             # L2, PVB, epe_viol, max_epe, mrc_viol, runtime
    errors: Annotated[list[str], add]; iters: int; budget: dict

inner = StateGraph(ILTState)
inner.add_node("retrieve", retrieve_skills)      # store.search(("skills", pattern_class))
inner.add_node("generate", generate_or_patch)    # 只允许改槽位函数
inner.add_node("policy", static_policy_check)    # AST：禁止 IO 写指标/目标/光刻模型
inner.add_node("fast_sim", openilt_eval)         # 沙箱子进程，超时 + 资源上限
inner.add_node("gate", validity_gate)            # MRC=0、目标哈希不变、评估区域不缩
inner.add_node("rigorous", rigorous_sim)         # 内含 interrupt() 以审批授权仿真
inner.add_conditional_edges("gate", route, {"retry": "generate", "rigorous": "rigorous", "done": END})

outer = StateGraph(EvolveState)
outer.add_conditional_edges("propose", lambda s: [Send("inner", v) for v in s["variants"]])
outer.add_node("heldout_gate", heldout_gate)     # 冻结 val 集；mean+max EPE 不劣、PVB 不劣、MRC=0
outer.add_node("approve", lambda s: interrupt({"diff": s["diff"], "val": s["val_report"]}))
app = outer.compile(checkpointer=PostgresSaver(...), store=PostgresStore(...))
```

几个设计选择需要说明理由。内环出错时**直接把报错回传给生成节点**，不插单独的反思步，因为官方教程测得反思步反而更差；反思放到外环，对整批 trace 做，和 VPEvolve 的 reflector/curator 分工一致。skill bank 放在 LangGraph Store 里，按 `("skills", pattern_class)` 分 namespace，每张卡片带"证据链接"（产生它的 trial id 和指标差值）。这对应 VPEvolve 的 evidence-linked judgment，也回应了 PDE-Agents "集成方式决定记忆利弊"的警告：卡片必须可追溯、可回滚。**held-out 门控**用冻结的、按图形族划分的验证 clip（训练与验证不能共享图形族），晋升条件是相对冠军"平均 EPE 与最大 EPE 都不劣、PVB 不劣、MRC 违例为 0"，以此防止靠单一指标钻空子。**`interrupt()`** 放在两处：skill/代码版本晋升前，以及消耗授权 Calibre 仿真前。checkpointer 让长时间仿真在中断或重启后可以恢复，这是 LangGraph 相对 Pi 或 Codex CLI 最实在的增量价值。防钻空子的硬约束包括：目标版图和光刻模型做哈希校验；禁止缩小评估区域；禁止跳过 MRC；按 clip 族做 held-out，防止核函数过拟合到测试 clip。这些 ILT 专属的作弊途径都来自对 MCE、Ptychi-Evolve、CADSmith 防御措施的类推 ([CAD 论文](https://arxiv.org/pdf/2603.26512))，尚无实测数据。

规模上可以拿 VPEvolve 作参照：10 个 case 约 120 次仿真、650 次 LLM 调用。若外环每代并行 K=4 个变体，每个变体跑 20 个训练 clip，再加 20 个验证 clip，每代就要约 100 次快速仿真。OpenILT 在 GPU 上可以承受，但最终结果必须用 Calibre 级严格仿真复核，否则无法与 VPEvolve 的数字比较。一个务实的替代方案是不在 LangGraph 里重写进化引擎，而是把 OpenEvolve 包成外环的一个工具或子图，LangGraph 只负责内环、门控、审批和持久化。这符合"LangGraph 是内层 agent 运行时，不是进化引擎"的现状。

## Conclusion

这次检索改变了问题的提法。"有没有 LangGraph 版光刻自演化智能体"的答案是没有。更有用的发现是，**自演化在工业领域的有效载体已经收敛到"冻结物理 + 冻结模型 + 演化文件化经验/固定槽位代码 + 确定性评估器 + 验证择优"**，与编排框架无关。VPEvolve、MCE、EvoDRC、Ptychi-Evolve 都符合这个模板，只是分别跑在 Pi、自定义 harness、Claude Code 上。所以 LangGraph 版 ILT 智能体的创新点不在"用了 LangGraph"，而在三处：用开源 OpenILT/LithoBench 替代 Calibre，让结果可复现；把 held-out 门控和人工审批做成图里的一等公民，而不是脚本约定；把演化对象从 recipe 扩展到 ILT 算法代码本身。需要警惕的是，现有证据全部是单篇、小样本（10–20 个 case）、无独立复现的结果；VPEvolve 的改善也只在最坏 EPE，PVB 没有变化。第一个里程碑应该是在 OpenILT 上复现"在线经验 vs 冻结经验"的差距，而不是直接追求开放式代码进化。

## 待讨论的开放问题

| # | 问题 | 为什么重要 | 当前倾向 |
|---|---|---|---|
| 1 | 首先演化什么：skill bank、ILT 代码槽位，还是二者并行？ | VPEvolve 证明 skill 有效，代码演化在 ILT 上尚无证据 | 先 skill，再开放 loss/正则/schedule 槽位 |
| 2 | OpenILT/LithoBench 的指标与 Calibre 的 EPE/PVB 定义能否对齐？ | 不对齐就无法与 VPEvolve 比较 | 需要一小组 Calibre 校准 clip |
| 3 | held-out 按什么划分：图形族、层（Poly/M1）、工艺节点？ | MCE 在 held-out 族上只有边际迁移 | 至少按图形族划分，另留一层作终测 |
| 4 | 进化外环用 LangGraph 原生实现，还是包一层 OpenEvolve？ | 每步 checkpoint 开销与可审计性的取舍（未实测） | 原型期包 OpenEvolve，门控与审批留在 LangGraph |
| 5 | `interrupt()` 审批粒度设多细？每次晋升都审，还是只审超过阈值的？ | 审批太频繁会抵消自动化收益 | 晋升必审，授权仿真按预算阈值审 |
| 6 | 用哪个 LLM，本地开源（如 Qwen）还是闭源 API？ | 涉及工艺数据保密；VPEvolve 用本地 Qwen | 生产用本地模型，研究期对比闭源 |
| 7 | 如何检测 ILT 专属的 reward hacking？ | 现有文献只有防御设计，没有事件统计 | 哈希校验 + 多指标 + 人工抽检日志 |
| 8 | skill 卡片的 schema 和老化/淘汰策略怎么定？ | VPEvolve 的 schema 未能核实；记忆漂移风险 | 证据链接 + 版本号 + 按验证贡献淘汰 |
| 9 | 是否把 SMO（光源-掩模协同）或 SRAF 插入纳入同一智能体？ | 搜索空间与评估成本都会大增 | 先单掩模 ILT，再扩展 |
