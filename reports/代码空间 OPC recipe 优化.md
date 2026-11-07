# 在代码空间优化 OPC recipe 仍是空白

截至 2026-11，公开文献里**只有一项工作真正让 LLM 在仿真闭环中直接编辑 OPC recipe 文本**，这就是 **VPEvolve**（arXiv 2609.32473，2026-09）。它的 recipe 是一份完整的 Calibre SVRF/LITHO deck，LLM 只能改两个 option block 中白名单内的行：**16 个有硬边界的数值参数**、开关，以及 fragmentation、feedback schedule、`OPC_ITERATION` 序列和 SRAF 规则等自由格式行。编辑以 JSON 操作提交，系统做**单父代、字典序的接受/拒绝**，每个 case 的预算是 **10 个候选、12 次 OPC 调用**。编排运行在 **Pi coding-agent harness** 上，不是 LangGraph。在这一结果上，Poly 层平均最大 EPE 从 18.29 nm 降到 5.36 nm，Metal1 从 22.05 nm 降到 15.69 nm。其余光刻工作要么用 RL 搜索、LLM 只负责把结果蒸馏成规则（AAAI 2025 的 OPC Engineer Assistant），要么让 LLM 直接改掩模几何而不是 recipe（MASK/Agent Lab）。**我们没有找到任何工作把 ILT recipe（loss 权重、正则项、步长/退火 schedule）或 SMO 设置当作代码来优化，没有找到基于 LangGraph 的光刻优化系统，也没有找到在 recipe 代码上做种群进化（AlphaEvolve/OpenEvolve 式）的工作。** 这三项合起来就是本报告要回答的空白。相邻领域的证据更多：EDA flow 调参（ORFS-agent、StateTune）、TCAD（AgenticTCAD、agentic-tcad）、化学配方（Iron Mind）。这些结果显示，LLM 在**冷启动、低预算（约 10–300 次评估）**下能胜过 BO/GA，但幅度通常不大（约 1–13%），优势主要体现在"到达首个可行解所需评估次数"上。表现最好的系统都是混合架构：LLM 负责结构与先验，GP/EHVI 负责选点与预算。LangGraph 在这类系统里的价值是**持久化控制平面**（checkpoint、预算门控、`interrupt()` 审批），不是搜索引擎本身。

> **证据等级约定。** 【代码级】＝研究者直接读过发布的源码、配置或结果文件。【摘要级】＝只读到 arXiv 摘要或搜索摘要，没读全文（本轮会话 arxiv.org、alphaxiv、semanticscholar、cse.cuhk.edu.hk 均被网络策略封锁）。【二手】＝EmergentMind、Liner、Moonlight 等聚合站的转述。【背景】＝研究者已有知识，本轮未重新核对。**框架归属**分三档：**LangGraph 已确认**、**其他框架已确认**、**未知**。

## 光刻领域只有 VPEvolve 在 recipe 文本上搜索

**VPEvolve: A Self-Evolving Virtual Process Engineer for Computational Lithography**（Tianyi Li 等 8 位作者，arXiv 2609.32473）的设计是"冻结 LLM + Skill Bank"。每次实测 trial 之后，reflector 和 curator 两个 LLM 角色把结果整理成与证据挂钩的判断，actor 在下一轮提案前检索这些判断，模型权重始终不变 ([arXiv](https://arxiv.org/abs/2609.32473))【摘要级】。真正值得细看的是它的 recipe 表示，这部分已从发布的 zip 包中逐文件核实 ([repo zip](https://raw.githubusercontent.com/vpevolve/vpevolve_code_and_data/main/downloads/vpevolve-full-source-0.4.0.zip))【代码级】。每个 case 有一份初始 recipe `R0.svrf` 和一份 `layout.gds`。R0 是完整的 Calibre deck，注释为"Auto-generated Metal MBSRAF + DenseOPC + OPCVerify deck"，包含 `RET MBSRAF`、`LITHO DENSEOPC` 和 `LITHO OPCVERIFY` 三段。

**可编辑空间是一个带类型的 DSL 补丁空间，而不是自由代码。** `recipe_validation.py` 只承认 `denseopc_options METAL_OPTS` 和 `sraf_options METAL_SRAF_OPTS` 两个 block 内可识别的行，其他内容都属于"protected physical contract"。如果子代改变了受保护部分的投影，或者"No physical change"，就直接拒绝。可编辑的行分三类。第一类是 **16 个有界数值参数**：OPC 侧 7 个（jog_freeze ∈ [0, 0.05]、jog_ignore_metric、max_opc_move ∈ [0.001, 0.10]、max_iter_movement ∈ [0.0001, 0.03]、fragment_min、fragment_grid、fragment_minjog），SRAF 侧 9 个（minwidth、maxwidth、maxlength、extension、minlength、minsquarelength、minoffset、maxoffset、minfeaturespace）。第二类是枚举开关，例如 line_end_fragment on/off。第三类是**自由格式行族**：`fragment_max`、`fragment_corner`、`feedback`（逐迭代 schedule，R0 中为 `-0.3 -0.4 … -0.2`）、`OPC_ITERATION` 序列、`sraf_sites_create`、`sraf_print_avoidance`。正是第三类让它区别于经典参数调优：GA 或 BO 处理的是固定长度的数值向量，而 feedback schedule 和迭代序列在结构上是可变的。

**提案是带假设的 JSON 编辑操作。** 每个提案必须带 `parent_sha256`，以及 `diagnosis`、`expected`、`falsification` 三个推理字段，形式上就是一个可证伪的实验设计。正文是一组 `operations`，每个操作对一个编目过的可编辑行 id 执行 `replace`、`delete` 或 `insert_after`，不允许出现花括号。提案还可以附带最多 6 条 `local_rules`，这是在最终 OPC 之后、验证之前对单个源边做的局部位移，本质上是热点修补动作。actor 能调用的工具包括 inspect_state、query_trials、read_evidence、compile_candidate、run_trial、query_experience、update_experience 等 ([repo zip](https://raw.githubusercontent.com/vpevolve/vpevolve_code_and_data/main/downloads/vpevolve-full-source-0.4.0.zip))【代码级】。

**搜索是单轨迹爬山，不是种群进化。** `objective.py` 只保留一个父代。子代必须先满足硬约束：MRC 结果数为 0、SRAF 可印刷违例为 0、平均 EPE 与 PVB 不超过 R0 的 1.02 倍（`quality_ratio 1.02`）。满足后，再按（最大 EPE，top-10 平均 EPE，平均 EPE，每目标边 PVB 面积）做字典序比较，严格更好才接受。配置中 `evolution_strategy: "search_guided"` 维护一个已测可行折中的"search board"，`decision_policy: "advisory"`。所以 VPEvolve 名字里的"evolve"指的是经验/skill 的演化，不是 recipe 种群的演化。预算写在 `configs/experiments/poly_01/full.json` 中：`candidates: 10, model_calls: 180, opc_calls: 12, pattern_jobs: 10`，并注明"10 optimization rounds from R0"、初始经验库为空。12 次 OPC 调用应该是 10 个候选加上 R0 评估和一次 `terminal_repeat` 复核，这一拆分是研究者的推断。默认模型是本地 vLLM 部署的 `Qwen/Qwen3.6-27B`，temperature 0；reflector/curator 的 prompt 改编自 **ACE（Agentic Context Engineering）**；harness 是 `@earendil-works/pi-coding-agent` 0.85.1；整个发布包 grep 不到 "langgraph" ([repo zip](https://raw.githubusercontent.com/vpevolve/vpevolve_code_and_data/main/downloads/vpevolve-full-source-0.4.0.zip))【代码级】。评估器必须是授权的 **Siemens Calibre** 加用户自备的光学/光刻胶模型；README 明确写出"No substitute model or simulated evaluation is used"，自带的 `diff_litho` 可微仿真器（TCC，focus −30/0/+30 nm）也"不能替代"商业流程 ([README](https://raw.githubusercontent.com/vpevolve/vpevolve_code_and_data/main/README.md))【代码级】。

**结果。** 在 20 个 FreePDK45 衍生窗口（10 Poly、10 Metal1）上，每个 case 10 次商业工具评估后，平均最大 EPE 在 Poly 上从 **18.294 降到 5.361 nm**（约 −71%），在 Metal1 上从 **22.052 降到 15.692 nm**（约 −29%）。最强的 agent 基线 ReAct 分别为 16.501 和 17.775 nm ([arXiv HTML](https://arxiv.org/html/2609.32473))【摘要级】。项目站的 `final-results.json` 给出了完整对照：ACE 16.70/19.92，ReasoningBank 17.52/20.54，static 17.58/19.88，**Bayesian optimization 17.91/21.77，且只有 6/20 个 case 达标**。消融中冻结经验退到 8.08/16.12。全方法每层（10 个 case）约用 120 次 OPC 调用、643–652 次 LLM 调用。PVB 基本没变，总体从 6.148 变为 6.210（×10⁻³ µm）([final-results.json](https://raw.githubusercontent.com/vpevolve/vpevolve/main/assets/current/final-results.json))【代码级，来自本对话早先一轮】。需要标出三处不一致。第一，摘要里"最终平均 EPE 在 Poly 上几乎不变、Metal1 更低（0.693 vs 0.698 nm）"一句文字是乱的，不应引用。第二，README 说"Empty-start runs are a different protocol from earlier source-seeded results"，说明仓库协议可能和论文数字的来源不同 ([README](https://raw.githubusercontent.com/vpevolve/vpevolve_code_and_data/main/README.md))。第三，项目站结果文件里有 BO 一行，但发布代码登记的基线只有 raw、static、react、textual、reasoningbank、ace、vpevolve，没有 BO；BO 用了哪些维度、什么代理模型、怎样初始化、怎样处理字典序目标，都没有文档 ([repo zip](https://raw.githubusercontent.com/vpevolve/vpevolve_code_and_data/main/downloads/vpevolve-full-source-0.4.0.zip))。因此，**"VPEvolve 胜过 BO"目前是一个不可复现的数字，公平的 BO 基线实际上仍然缺失**。

另外两项光刻工作都处在"代码空间优化 recipe"这一定义的边缘。**Intelligent OPC Engineer Assistant**（Guojin Chen、Haoyu Yang、Bei Yu、Haoxing Ren；arXiv 2408.12775；AAAI 2025）分两步：先用 PPO 搜索 EPE 测量点和 fragmentation 点的放置，loss 由距离、EPE 和 PVB 组成；再由多模态 LLM 给 RL 结果打特征标签，构建决策/回归树，生成运行时间与纯 OPC 引擎相同的规则式 recipe ([arXiv](https://arxiv.org/abs/2408.12775)，[AAAI](https://ojs.aaai.org/index.php/AAAI/article/view/34479)，[作者 Notion](https://gjchen.notion.site/Agent-System-with-LLM-labeled-Regression-Tree-44ae87a389524ba3b32682af5b45a54d))【摘要级/二手】。这里搜索者是 RL，LLM 只做蒸馏。它的数字在各转述之间冲突：一处说 ICCAD13 上 LLM recipe 使 EPE 违例减少约 11%、EPE 距离减少约 19%，另一处给的是 RL 阶段 12%/约 24%，NVDLA 上则是 RL 13%/15%、LLM recipe 8%/12% ([EmergentMind](https://www.emergentmind.com/papers/2408.12775)，[Liner](https://liner.com/review/intelligent-opc-engineer-assistant-for-semiconductor-manufacturing))【二手】。**MASK/Agent Lab**（NanWang-EE，静态展示站，"2026-10"的日期未独立确认）在 OpenILT 上跑 observe → propose → simulate → accept/rollback。但 LLM 返回的是逐边段的几何移动（`edge_id`、1 nm 网格上的 `delta_grid`、可选的 `cuts_grid` 和 SRAF 操作），**改的是掩模本身，不是 ILT recipe**，而且 prompt 禁止模型调用仿真器 ([site-data.js](https://raw.githubusercontent.com/NanWang-EE/agent-mask-optimization-site/main/data/site-data.js))【代码级】。两个 case、15 轮之后，"Astra 6"把 EPE 违例从 86 和 84 降到 **0 和 0**，但 PVB 从 45,874 升到 63,908（case 1）。OpenILT 论文中的 MultiLevel 基线是 4 / 38,577 / 47,367。站点自己也承认这一比较"contextual, not a claim of controlled, identical experimental conditions" ([README](https://raw.githubusercontent.com/NanWang-EE/agent-mask-optimization-site/main/README.md))。此外，LLM-SRAF（DATE 2025）和 AST 引导的 SVRF 代码合成（arXiv 2507.00352）都是一次性生成模型，没有优化闭环。后者还报告通用 LLM 在 SVRF 上幻觉严重、公开数据稀缺 ([LLM-SRAF](https://www.cse.cuhk.edu.hk/~byu/papers/C256-DATE2025-LLM-SRAF.pdf)，[arXiv 2507.00352](https://arxiv.org/pdf/2507.00352))【摘要级】。

| 工作 | recipe 表示 | 可编辑空间 | 搜索算法 | 框架 | 评估器 / 预算 | 结果与基线 | 开源 | 核实 |
|---|---|---|---|---|---|---|---|---|
| VPEvolve (2609.32473) | Calibre SVRF/LITHO deck | 16 个有界数值 + 开关 + 6 类自由格式行 + ≤6 条局部规则 | LLM 假设式提案，单父代字典序接受；ACE 式经验库 | **其他（Pi harness）** | Calibre；10 候选 / 12 OPC / 180 LLM 调用每 case | max EPE 18.29→5.36（Poly）、22.05→15.69（M1）；ReAct 16.50/17.78；BO 17.91/21.77（配置未公开） | Apache-2.0（不含 Calibre 与模型） | 代码级 + 摘要级 |
| OPC Engineer Assistant (2408.12775) | 测量点/分段点策略 → 决策树规则 recipe | 分段与测量点放置 | PPO；LLM 打标签 + 回归树蒸馏 | 未知 | OPC 引擎不明；ICCAD13、NVDLA | EPE 违例 −8%~−12%，距离 −12%~−24%（转述冲突）；对照为初始 recipe | 未找到 | 二手 |
| MASK/Agent Lab | 掩模边段几何 JSON（非 recipe） | 边段移动、细分、SRAF | LLM 提案，单轨迹接受/回滚 | 未知（自定义控制器） | OpenILT；2 case × 15 轮 | EPE 违例 86→0、84→0，PVB 变差；与 OpenILT 基线非受控比较 | 仅展示站与数据 | 代码级 |

## EDA 与工艺领域的 recipe 搜索已有十余个先例

把范围放宽到相似的工业工程领域，"把 recipe 当文本/代码交给 LLM 搜索"的例子明显更多，并且分成两个流派。第一个流派优化**数值/类别配置文件**，可以和 BO 正面比较。第二个流派演化**工具源码**，BO 在结构上无法进入这个空间，所以只能和手写工具比较。

**参数流派。** ORFS-agent（UCSD Kahng 组，arXiv 2506.08332）调的是 OpenROAD-flow-scripts 的 `config.mk` 和带约束的 `opt_config.json`，例如 `CORE_UTIL` 取整数 [20, 99]。它的 LLM 把 GP 建模、kernel 选择和 scikit-optimize BO 当工具调用。默认预算是 6 轮串行 × 50 路并行，约 300 次 flow 运行，每次 45 分钟超时；框架是自定义 Python/shell ([README](https://github.com/ABKGroup/ORFS-Agent))【代码级】。它的数字有冲突，**必须标红**：arXiv 摘要说相对 OR-AutoTuner 的增益约为 WL 1.0%、ECP 1.3%、联合优化 **2.7%**，且迭代少 40% ([arXiv](https://arxiv.org/pdf/2506.08332))【摘要级】；README 却称相对"baseline Bayesian optimization"提升 **超过 13%**，同样少 40% 迭代 ([README](https://github.com/ABKGroup/ORFS-Agent))。可能的原因是两者的参照不同（默认 ORFS 还是 AutoTuner），但这一点没有核实。**StateTune**（arXiv 2608.23601）在 Cadence Genus/Innovus 的 19 个选项上，用一个带类型化持久记忆、有五种模式的 LLM Knowledge Agent 提案，再用多保真 GP 按 EHVI/运行时 UCB 决定哪些候选晋升到完整布线。在 6 个 block 上，它的最终 hypervolume、WNS、功耗全部最好，面积最好或并列最好，对照组包括 **BO-qEHVI、Optuna-TPE、Random、RankTuner、CROP**。消融显示，去掉证据门控 hypervolume 掉 43.4%，去掉 RAG 掉 46.1%。预算为每 block 192 thread·h，6 个 block 共约 6.0M token ([README](https://github.com/C-YuLong/stateTune))【代码级；对 BO 的 hypervolume 具体差距未获得】。第三方的 OpenROAD 移植还发现了两个上游 bug：qLogEHVI 被当成原始 EHVI 使用，导致前沿稳定后不再有候选晋升；ns 与 ps 单位检查错误，误判了 7 次 ASAP7-IBEX 运行中的 3 次 ([OPENROAD_PORT.md](https://github.com/XH2567/statetune-openroad))【代码级】。**EDA Pilot AI** 是本次检索中唯一用 LangGraph 编排 EDA 调参的项目。但它的基准是一个确定性的时钟二分 advisor，原文写明"No chat model made decisions in this study"，AutoTuner 基线也因为 Ray 无法导入 HyperOpt 而一次都没跑出来 ([BENCHMARK_RESULTS.md](https://github.com/NileshModlier/EDA-Pilot-Agentic-AI/blob/main/BENCHMARK_RESULTS.md))【代码级】，**所以它不能作为 LLM 胜过 BO 的证据**。

**源码流派。** GR-Evolve（ASU，arXiv 2604.22234）用 Codex CLI 按设计逐个演化 FastRoute、CUGR、SPRoute 的源码，按（详细布线后 WL，via 数，GR 运行时）打分，在 7 个设计 × 3 个节点上最多减少 **8.72%** 的布线后 WL。它的 GA 式循环是 `GeneticRunCodex.sh`，45 个 router-设计-PDK 组合各跑一个 Docker 容器 ([arXiv](https://arxiv.org/pdf/2604.22234)，[repo](https://github.com/ASU-VDA-Lab/GR-Evolve))【摘要级/代码级】。用 coding agent 改进 OpenROAD QoR 的工作（arXiv 2601.06268）报告 WL 最多减少 5.9%、ECP 最多减少 10.0%，而且 WL 增益来自一次仓库级修改，不是逐设计调参 ([arXiv](https://arxiv.org/html/2601.06268))【摘要级】。GoalEvolve 在有界范围内演化 OpenROAD 的 C++ 算法，用 Teacher/Student Codex worker 和证据式晋升；它的 arXiv 编号 2608.16733 无法检索到，数值结果也未读到 ([README](https://github.com/CODA-Team/GoalEvolve))【代码级；编号未核实】。

**工艺/TCAD 与化学。** AgenticTCAD（arXiv 2512.23742，DATE 2026）生成 Sentaurus SDE/SDevice 代码，让一个 2 nm NS-FET 在 **4.2 小时**内达到 IRDS-2024 规格，人类专家需要 7.1 天；但对照是人，不是 BO ([arXiv](https://arxiv.org/html/2512.23742v1))【摘要级】。czf-mq/agentic-tcad 在 Gmsh/DEVSIM 上对 100 nm nMOS 做了 3 组 × 25 次评估的小实验。**到达首个可行点所需评估次数：LLM 中位数 5，约束 BO 中位数 11**；随机搜索和标量 BO 各在 3 组中失败 2 组。作者提醒样本太小，不足以宣称优越性，而且被评测的方法实际是"V4-Flash + 验证/修复 + 回退"，72 步中有 4 步走了确定性回退 ([README](https://github.com/czf-mq/agentic-tcad))【代码级】。Iron Mind 研究在 6 个完全枚举的类别型反应数据集（768–5,684 个实验）上发现，LLM 引导的优化整体不输 BO，**BO 只在显式多目标折中上保持优势** ([arXiv 2509.00103](https://arxiv.org/abs/2509.00103))【摘要级】。刻蚀、沉积、CMP 方面没有找到用 LLM 当优化器的 2025–2026 论文；最接近的是经典 BO 刻蚀 recipe 工作，把 recipe 开发成本降低 75% 以上 ([NSF PAR](https://par.nsf.gov/biblio/10224478))【摘要级】。

| 工作 | 产物 | 搜索 | 框架 | 预算 | 对照与结果 | 开源 | 核实 |
|---|---|---|---|---|---|---|---|
| ORFS-agent | ORFS `config.mk` | LLM + GP/BO 工具 | 其他（自定义） | 约 6×50 次 flow | vs AutoTuner 1–2.7%（摘要）或 vs BO >13%（README），**冲突** | 是 | 摘要级 + 代码级 |
| StateTune | 19 个 Innovus 选项 | LLM 提案 + 多保真 GP EHVI/cost 晋升 | 其他（BoTorch） | 192 thread·h/block，6M token | 6/6 block 全胜 BO-qEHVI、TPE 等 | 是 | 代码级 |
| EDA Pilot AI | ORFS 设置 | 实测为确定性二分 | **LangGraph 已确认** | 10 次运行/设计 | 比随机搜索时钟紧 14.5–30.3%；无 LLM 决策 | 是 | 代码级 |
| GR-Evolve | router C++ 源码 | Codex CLI，GA 式 | 其他 | 45 个容器 | WL 最多 −8.72%，对照为手写 router | 是 | 摘要级 + 代码级 |
| AgenticTCAD | Sentaurus 脚本 | 多 agent 生成 | 未知 | — | 4.2 h vs 人类 7.1 天 | 数据集 | 摘要级 |
| agentic-tcad | DEVSIM 参数 JSON | LLM + 修复 + 回退 | 其他 | 3×25 次评估 | 首个可行点 5 vs 约束 BO 11 | 是 | 代码级 |
| MADR（水文） | 子流域参数集 | Leader/Worker LLM | **LangGraph 已确认** | 170 次评估 | NSE 0.744–0.760 vs SCE-UA/NSGA-III 0.764/0.772（4,000 次） | 是 | README 级 |

## LLM 搜索只在冷启动和结构化编辑上胜过 BO

把这些证据放在一起，可以得出一个比"LLM 胜过 BO"更精确的判断。**LLM 的优势集中在三种情形。** 第一，评估极贵、预算只有约 10–30 次时的冷启动：agentic-tcad 到达可行点快约 2 倍，ORFS-agent 少用 40% 迭代，LLAMBO 在观测稀少的早期迭代中最强 ([arXiv 2402.03921](https://arxiv.org/pdf/2402.03921))【摘要级】。第二，类别型、先验知识丰富的空间，例如 Iron Mind 的化学反应。第三，**BO 无法表达的结构化编辑**，例如源码修改（GR-Evolve、OpenROAD coding agent）以及 VPEvolve 的 feedback schedule 和 `OPC_ITERATION` 序列。反过来，**BO 在两种情形下仍然更好或不可替代**：显式多目标 Pareto 折中（Iron Mind 的结论），以及预算放大之后的渐近最优值（ORFS-agent 摘要中对 AutoTuner 只多出 1–3%）。MADR 是这一模式在 LangGraph 上的例子：用 4% 左右的评估量追平 SCE-UA，但最终 NSE 0.744–0.760 仍略低于 NSGA-III 的 0.772 ([MADR](https://github.com/jovequli/MADR))【README 级】。

这对 VPEvolve 的意义很直接。它报告的 Poly max EPE 增益（18.29 → 5.36 nm）恰好落在 LLM 最擅长的区域：10 次评估，加上大量结构化自由格式行。但由于没有公平的 BO 基线，**我们分不清这部分增益来自哪里**：是 LLM 在 16 维数值空间里本来就更会采样，是自由格式行（schedule、迭代序列、局部规则）贡献了 BO 碰不到的那一块，还是经验库在跨 trial 地积累知识？消融只回答了第三个问题：冻结经验后 Poly 退到 8.08 nm，说明在线经验贡献了约 2.7 nm ([final-results.json](https://raw.githubusercontent.com/vpevolve/vpevolve/main/assets/current/final-results.json))。前两个问题至今没人回答。还要注意一个反向论点：VPEvolve 的 BO 行（17.91/21.77）几乎没有比 R0 好多少。这可能说明 BO 在 10 次评估、16 维以上、带硬约束的空间里本来就无力，也可能只说明那个 BO 配置得不好（例如没有把 R0 作为初始点、没有处理约束）。在配置公开之前，两种解释都成立。

**混合设计方面，表现最好的都让概率代理模型掌管选点和预算。** StateTune 用 LLM 提出候选、修复失败、维护规则，再由多保真 GP 按 EHVI/(运行时 UCB + ε) 决定哪些候选值得做完整评估 ([README](https://github.com/C-YuLong/stateTune))。ADO-LLM 让 LLM 提案和 GP-BO 提案共享同一份数据集，在模拟电路 FOM 上胜过单独使用任一方 ([arXiv 2406.18770](https://arxiv.org/html/2406.18770v1))；LLM-USO 用 BO 的不确定度给 LLM 建议排序 ([ar5iv](https://ar5iv.labs.arxiv.org/html/2502.02764))；GOLLuM 通过 GP 边际似然微调 LLM embedding，在 Buchwald–Hartwig 上 50 轮内把 top-5% 覆盖率从 24% 提到 43% ([arXiv 2504.06265](https://arxiv.org/html/2504.06265v1))【均为摘要级；GOLLuM 与 Nature MI 版本的对应关系未核实】。对于代码结构的产物，有效模式则是**把 LLM 代码变异放进进化种群，配自动评估器**，例如 LLaMEA-BO 生成的 BO 算法在 BBOB-5D 的 24 个函数中有 19 个胜过 HEBO、TuRBO 和 CMA-ES ([arXiv 2505.21034](https://arxiv.org/abs/2505.21034v1))【摘要级】。至于"LLM 提出结构、CMA-ES 精修数值"这一组合，**没有任何来源在 EDA 或工艺任务上直接比较过它与"LLM 提案、GP 选点"**，哪个更好仍是推断。研究者的倾向是：在约 10 次评估的预算下，CMA-ES 的种群统计量根本来不及收敛，所以 GP/TPE 比 CMA-ES 更适合做精修；CMA-ES 只在开源快速仿真器、几百次评估以上时才有意义。

## LangGraph 的价值在控制平面而非搜索引擎

LangGraph 生态里没有成熟的 recipe 优化器。超过 100 星的 LLM 进化引擎（OpenEvolve 约 7.7k 星，ShinkaEvolve 约 1.5k 星）都是普通 Python asyncio 循环，GitHub 搜 "langgraph openevolve"、"langgraph alphaevolve"、"langgraph map-elites" 得到 0 个仓库 ([OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve)，[ShinkaEvolve](https://github.com/SakanaAI/ShinkaEvolve))【代码级，2026-11-07 检索】。最严谨的两个 LangGraph 优化循环星数都是个位数。第一个是 **auto-researcher**，它把 Optuna 拆成 prepare、ask、create_experiment、tell、record、decide、finalise 七个图节点，把 OpenEvolve 拆成 select_parent、propose、validate、record、decide 等节点，让"每个生命周期边界都是一个 checkpoint 边界"，并设 `human_approval` 节点和 `interrupt_after` ([builder.py](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/src/auto_researcher/graph/builder.py))【代码级】。它的设计原则值得原样照搬："Model judgement is permitted only inside a configured mutation operator"，排序、替换、停止、评估、验证全部保持确定性 ([OPENEVOLVE_SEARCH.md](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/docs/architecture/OPENEVOLVE_SEARCH.md))。第二个是 **MADR**（水文模型率定），用 SQLite checkpointer 支持 `--resume`，并结合 patience 早停和 `max_rounds` 硬上限 ([MADR](https://github.com/jovequli/MADR))。社区仓库里的 LangGraph 优化循环可以归为三种模式：LLM 做单候选提案的精修循环（molecule-opt、MADR worker）；GA 种群直接放在 TypedDict 状态里（AURA）；LangGraph 作为持久控制平面，逐步驱动外部数值优化器（auto-researcher）。只有第三种严格处理了恢复、预算和重放。

这些项目踩过的坑可以直接转成 OPC 优化器的设计约束。**第一，Optuna 只持久化 trial，不持久化 sampler 的 RNG 状态。** 每次节点调用都重建 Study 会重置随机流，所以 auto-researcher 每个运行时只缓存一个 Study；重启后用公开的 `Study.tell(trial_number)` 补记，绝不用私有 id 重建 Trial ([backend.py](https://raw.githubusercontent.com/Lifework-Health/auto-researcher/main/src/auto_researcher/search/optuna/backend.py))。**第二，预算语义容易出错。** auto-researcher 把种子基线计入评估预算；MADR 在 v0.2.1 修正了"最终 force-best 复核悄悄占用最后一个优化名额"的问题，把复核明确放到预算之外 ([MADR](https://github.com/jovequli/MADR))。这和 VPEvolve 的 10 候选 / 12 OPC 调用正好对应，公平比较时必须让所有方法采用同一套计数规则。**第三，缓存键必须用精确值。** Mechanical_Agentic_Pipeline 把缓存键舍入到 100 nm，结果 SLSQP 的有限差分梯度变成零，一个约束被悄悄忽略 ([README](https://github.com/michaelbarfoot/Mechanical_Agentic_Pipeline))。OPC 参数本身就在 0.0001 µm 这个量级（max_iter_movement 的下界），这个坑在光刻里只会更危险。**第四，checkpoint 不是种群数据库。** checkpointer 在每个 superstep 序列化通道状态，MADR 已经需要在运行后对 checkpoint 库做 VACUUM；AURA 把整个种群放进状态，并干脆不用 checkpointer，代价是无法恢复 ([AURA state.py](https://raw.githubusercontent.com/Rahul-8283/AURA/main/backend/app/agents/state.py))。**第五，`recursion_limit` 计的是 superstep，不是循环轮数，默认 25**，粗暴调到 1000 会掩盖不终止的问题 ([fast.io](https://fast.io/resources/langgraph-recursion-limit/))。**第六，`Send` 适合动态扇出**，每个 worker 的结果都要经 reducer 合并回状态 ([LangGraph 文档](https://docs.langchain.com/oss/python/langgraph/graph-api-control-flow.md))。但本次检索没有发现任何优化仓库用 `Send` 扇出仿真任务，auto-researcher 还明确写了"Parallel population evaluation is intentionally deferred"。**第七，单位和指标语义需要单独测试。** StateTune 移植中的 ns/ps 错误、qLogEHVI 误用都属于这一类；VPEvolve 的 EPE 用 nm、PVB 用 10⁻³ µm，是同一类风险。

## 一个 LangGraph 版 OPC/ILT recipe 优化器的设计

下面是研究者基于上述证据的**设计提案，不是已验证的系统**。它要同时填上三处空白：LangGraph 编排、recipe 代码上的种群搜索、ILT/SMO recipe 作为可编辑对象。核心原则是**两种运行模式共用一张图**。模式 A 用于商业 Calibre：评估昂贵、受 license 限制（VPEvolve 设 `max_concurrent_jobs: 1`），预算约 10 次，采用 VPEvolve 式单父代加 BO 混合。模式 B 用于开源快速仿真（OpenILT、VPEvolve 自带的 `diff_litho`），预算可以到几百次，启用岛模型或 MAP-Elites 种群。两种模式最后都由严格仿真复核，再进入人工审批。

**recipe 表示与可编辑空间。** OPC 直接复用 VPEvolve 的补丁 DSL：可编辑行目录、受保护投影哈希、数值边界、JSON 编辑操作。它已经是一个现成的变异算子加沙箱。ILT 这一侧目前没有先例，建议定义一份类型化的 `ilt_recipe.yaml`，并给它配一个固定签名的代码槽位。数值部分包括 loss 权重（L2、PVB、EPE 代理项）、正则系数（曲率、TV、MRC 惩罚）、步长和迭代数、sigmoid 陡度与二值化退火 schedule、多分辨率层级。结构部分包括 schedule 的分段形状、初始化策略（目标图或 SRAF 种子），以及一个签名固定的 `schedule(step, metrics) -> cfg` Python 函数。光学核、光刻胶模型、指标代码和目标版图全部只读。SMO 作为第二阶段扩展，可编辑项是光源像素化参数和源/掩模交替的 schedule。这样，"数值维度交给 BO，结构维度交给 LLM"的分工在 OPC 和 ILT 上是同构的。

```
[init: 载入 R0, 评估基线(计入预算)] → [diagnose: LLM 按图形类汇总 EPE/PVB 热点]
   → [route_proposer] ─┬→ [llm_propose: JSON 编辑 + diagnosis/expected/falsification]
                       ├→ [bo_ask: Optuna/BoTorch ask, 只覆盖数值子空间, 结构行固定为当前父代]
                       └→ [evo_select_parent: 岛/MAP-Elites 选父 (仅模式 B)]
   → [validate: 白名单/边界/受保护投影哈希/DSL lint/去重] → [cache_lookup: sha256 键]
   → [submit_batch: 写 deck, 提交 Slurm/Ray/Calibre 队列, 只返回 job_id]
   → [collect: 轮询 或 interrupt 等回调] → [score: 确定性 EPE/PVB/MRC/SRAF print/runtime]
   → [tell_record: Optuna tell + 档案库写入 + reflector→curator 写 Store]
   → [decide: 字典序接受/拒绝 或 种群替换; 预算/patience/成本上限]
        ├→ 继续 → diagnose
        └→ [rigorous_verify: 多保真晋升, Calibre 复核 + terminal repeat(不计入预算)]
             → [heldout_gate: 冻结的 held-out clip 族] → interrupt("approve_promotion") → END
```

**状态与存储。** LangGraph 状态里只放小对象：`run_id`、`mode`、`phase`、`round`、`budget_used`（分 opc_calls、llm_calls、tokens 三项）、`parent_ref`、`candidate_ids`、`job_ids`。recipe 全文、仿真结果和档案库放在外部 Postgres/SQLite 表中，主键为 `sha256(规范化 recipe + 仿真器版本 + 光学/光刻胶模型版本 + clip 集 id)`，参数用精确值，不做舍入。Optuna 状态留在它自己的 RDB 存储里，种群档案放在 pyribs 或 OpenEvolve 的原生存储里。skill bank 放在 LangGraph `Store`，按 `("skills", layer, pattern_class)` 分 namespace，每张卡片带产生它的 trial id 和指标差值，可以追溯、可以回滚。checkpointer 用 PostgresSaver，一个运行对应一个 `thread_id`。

**并行仿真。** Calibre 级的长任务不走 `Send`：由 `submit_batch` 节点把一批 deck 提交到作业调度器，状态里只回填 job id，`collect` 节点轮询，或用 `interrupt()` 挂起、等回调后恢复。这样即使仿真跑几个小时，进程重启也不会丢失进度。`Send` 只用于短任务，例如按图形类并行做 LLM 诊断、逐 clip 做快速评分，reducer 只追加 id，不追加结果本身。`recursion_limit` 按"每轮节点数 × 最大轮数 + 余量"计算，真正的终止由 `decide` 负责。

**数值优化器集成。** 模式 A 采用"LLM 定结构、BO 填数值"的交替：LLM 每轮决定改哪些自由格式行，并圈定一个数值子空间（例如只开放 max_opc_move、max_iter_movement、feedback 的幅度）；BO 在这个子空间里，以当前父代为初始点给出数值。LLM 提案和 BO 提案写入同一个 Optuna study（ADO-LLM 的共享数据集模式），由带约束的 EI 或 EHVI/cost 决定哪个候选送去 Calibre（StateTune 的晋升模式）。模式 B 在快速仿真器上跑种群进化，LLM 作为变异算子；数值精修可以加 CMA-ES，因为这时预算才足够 CMA-ES 收敛。auto-researcher 的硬规则贯穿始终：LLM 只出现在提案节点里，排序、接受、停止全部是确定性代码。

**门控与 HITL。** 门控分四层。第一层是 `validate`，规则直接沿用 VPEvolve：白名单、边界、受保护投影不变、必须有物理变化。第二层是可行性：MRC = 0、SRAF 印刷 = 0、平均 EPE 与 PVB 不超过 1.02 × R0。第三层是 held-out 门：按图形族划分，训练族和验证族不重叠，晋升要求 max EPE、mean EPE、PVB 都不劣于当前冠军。第四层是 terminal repeat 复核，排除仿真噪声。`interrupt()` 放在两处：一是每批消耗授权 Calibre 仿真之前，可以按预算阈值放行；二是 recipe 晋升到生产或进入全芯片阶段之前。审批载荷包括 diff、held-out 报告和 LLM 的 falsification 字段。

**缺失的公平基线实验。** 这是整份提案中最先该做、也最便宜的一步。它不需要 LangGraph，只需要 VPEvolve 的 20 个 case 和 Calibre。设计要点如下。

| 维度 | 设定 |
|---|---|
| 空间 | 臂 1：16 个数值参数 + line_end_fragment 开关，自由格式行固定为 R0。臂 2：再加上 feedback schedule 的参数化（例如 10 个幅度值，或"峰值 + 衰减"两个参数），让 BO 也能触及 schedule |
| 预算 | 与 VPEvolve 完全相同：R0 计入（或统一不计）、10 个候选、terminal repeat 不计入；同时报告 30 次和 100 次评估的扩展预算，对应 VPEvolve 已有的 100-trial 长程运行 |
| 方法 | Random（同一边界盒）；Sobol 3 点 + GP-EI 7 点（BoTorch，R0 作为首个观测）；TPE；SMAC（随机森林，适合混合变量）；带约束 BO（MRC、SRAF、1.02× 约束作为 outcome constraint）；VPEvolve-numeric-only（禁止自由格式行和 local_rules）；VPEvolve full；混合（前 5 个 LLM、后 5 个 BO，或逐轮交替） |
| 目标 | BO 用 max EPE 作主目标，约束单独建模；最终统一按 VPEvolve 的字典序规则选出报告 recipe |
| 统计 | 每个随机方法每 case ≥ 5 个种子；LLM 方法在 temperature 0 下再取 3 个不同种子或不同 backbone；20 个 case 做配对 Wilcoxon 检验；报告 best-so-far 随评估次数的曲线及曲线下面积、达标 case 数、token 与墙钟成本 |
| 归因 | numeric-only 与 BO 的差值，衡量 LLM 在同一空间里采样是否更好；full 与 numeric-only 的差值，衡量结构化编辑的贡献；full 与 frozen 的差值，衡量经验库（已知约 2.7 nm） |
| 开源复现 | 在 `diff_litho`/OpenILT 上重跑同一组实验，并报告它与 Calibre 结果的排序一致性（Kendall τ），用来决定模式 B 的结论能否迁移到模式 A |

这个实验能把"VPEvolve 胜过 BO"从一个配置不明的数字，变成三个可归因的量。它还会直接决定 LangGraph 优化器在模式 A 下的默认路由：如果 numeric-only 不敌 BO，就应该让 BO 掌管数值，LLM 只做结构编辑；如果反过来，混合的价值就主要在于用 BO 的不确定度给 LLM 提案排序。

## Conclusion

这轮检索最重要的修正是：**在光刻领域，"代码空间优化 recipe"目前的真实形态，是在一个高度受约束的类型化补丁空间里做低预算、带假设的爬山**，而不是 AlphaEvolve 式的开放代码进化。VPEvolve 把 LLM 的作用压缩成"对白名单 DSL 补丁的提案算子"，这一选择是 Calibre 的成本和 license 并发限制逼出来的。这意味着种群进化、ILT/SMO recipe 代码化、LangGraph 编排三处空白**只能借助开源快速仿真器才能填上**，而且要先证明快速仿真器上的方法排序能迁移到 Calibre。另一个被低估的问题是**基线卫生**。本报告涉及的定量结论中，至少有五处存在冲突或无法复现：ORFS-agent 的 2.7% 与 >13%，OPC Assistant 的三组转述数字，VPEvolve 摘要里乱码的 mean EPE，仓库协议与论文协议的差异，以及配置不明的 BO 行。所以在这个领域，最有价值的贡献未必是一个更聪明的智能体，而是一个公开、等预算、多种子、能做归因的 BO/LLM/混合对照基准。LangGraph 恰好适合承载这样的基准：checkpoint、预算节点和审批中断让每一次昂贵仿真都可以审计和重放。

## 待讨论的开放问题

| # | 问题 | 为什么重要 | 当前倾向 |
|---|---|---|---|
| 1 | VPEvolve 的 BO 行究竟用了什么空间、代理模型、初始化和约束处理？能否向作者索取配置？ | 决定"LLM 胜过 BO"是否成立 | 先自己按上表重做，同时联系作者 |
| 2 | VPEvolve 的增益中，数值采样、结构化自由格式行、经验库各占多少？ | 决定混合架构中 LLM 和 BO 的分工 | 用 numeric-only / full / frozen 三臂归因 |
| 3 | `diff_litho`/OpenILT 上的方法排序与 Calibre 是否一致？ | 决定模式 B（种群进化）的结论能否用于生产 | 先用 20 个 case 测 Kendall τ |
| 4 | ILT recipe 应先开放哪些维度：数值权重和 schedule，还是 `schedule()` 代码槽位？ | 没有先例，搜索空间和作弊面同时扩大 | 先数值 + 分段 schedule，再开放代码槽位 |
| 5 | 在约 10 次评估的预算下，种群方法是否有意义？还是只能用单父代 + BO？ | Calibre license 并发为 1 | 模式 A 保持单父代，种群只在模式 B 使用 |
| 6 | 字典序目标（max EPE 优先）对 BO 不友好，是否改成带约束的单目标或 EHVI？ | 目标定义不同会让对比失真 | 搜索时用约束 BO，报告时统一用字典序 |
| 7 | 进化外环用 LangGraph 原生节点实现，还是把 OpenEvolve 包成一个节点？ | 涉及可审计性与工程量的取舍 | 模式 B 原型期包一层 OpenEvolve，门控和审批留在图里 |
| 8 | `interrupt()` 审批粒度：每批 Calibre 任务都审，还是只审晋升？ | 审批太频繁会抵消自动化收益 | 晋升必审，仿真按预算阈值审 |
| 9 | 是否要求每个 LLM 提案都带 falsification 字段，并统计假设被证伪的比例？ | 这是衡量 LLM 是否真在"推理"而非随机采样的直接指标 | 是，作为 tell_record 节点的标准日志 |
| 10 | SMO 是否纳入同一优化器？源/掩模交替 schedule 能否当作 recipe 代码？ | 搜索空间和评估成本都会大幅增加 | 等 OPC 与 ILT 两条线跑通之后再考虑 |
