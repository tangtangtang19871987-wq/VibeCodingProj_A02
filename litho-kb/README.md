# LithoKB — 轻量级计算光刻知识编译系统

把一堆 Markdown 文档，经 LLM「编译」成**可审阅、可追溯、可发布**的知识卡片网络（知识图谱 + 主题层级），
同时原文始终原样保留、可浏览、可追责。Web UI 面向读者 / 审阅者 / 管理员三种角色，CLI 可无界面完成全部流程。

```
./lkb init                         # 建库（创建管理员）
./lkb upload examples/litho-docs   # 第一层：上传 MD 文件夹
./lkb compile --backend mock       # 第二层：LLM 编译（mock 离线；anthropic 真实模型）
./lkb serve                        # Web UI → http://127.0.0.1:8765
python3 -m unittest discover -s tests -v
```

**依赖：Python ≥ 3.10 标准库，无其他依赖。** 只有使用真实 Claude 模型时才需要 `pip install anthropic`。
没有数据库、没有向量库、不切分文档、没有前端构建链。前端是 4 个静态文件（约 60 KB）。

---

## 0. 融合了哪些思想

| 来源 | 核心价值 | 在 LithoKB 中的落地 |
|---|---|---|
| **LLM Wiki**（Karpathy） | 原文不可变；LLM 维护持久的、互相链接的 wiki；**规则文件（schema）就是"编译器的源码"**；ingest / query / lint 三个操作；知识随使用不断累积 | 第一层原文永不改写；`SCHEMA.md` 由管理员编辑、有版本记录，每次编译记录所用版本；**问答（query）**的好答案可**回写**为「问答综合」卡片进入审阅；`lkb lint` 健康检查；人能直接读的 `compiled/log.md` |
| **OpenKB** | 两层 wiki：每篇文档一张 `summaries/` 摘要 + 跨文档的 `concepts/` 概念页；新文档**丰富**已有页面而不是孤立存在；`index.md` / `log.md` | 每篇原始文档强制生成一张 `summary` 卡片（id 确定，如 `summary-opc-ilt-md`），用 `covers` 关系指向它贡献的概念卡片；概念卡片跨文档共用；导出的 `index.md` 分「知识」与「文档摘要」两部分 |
| **PageIndex** | 不用向量、不切片：用文档自身的**目录树**，让 LLM 像人查目录一样**推理式导航** | 每篇文档确定性地生成标题目录树（节点带精确行号）；**问答先导航后作答**：模型阅读知识树与文档目录树，写出阅读计划，再精读选中内容；**超长文档按目录结构分章编译**（不是按长度机械切块），每章都能看到全文目录和前面章节已产出的卡片 |
| （补充）Graphify | 每条关系标注认识论状态 | 关系必须标注 `extracted / inferred / ambiguous` + 置信度；标为「原文明确」却没有有效证据的关系自动降级为「推断」；「存疑」的关系排在审阅队列最前面，图谱中用不同线型显示 |

## 1. 设计理念

| 理念 | 落地方式 |
|---|---|
| **人类友好 ⇒ Agent 友好** | 所有数据都是人能直接读的文件：原文是原样的 `.md`，知识卡片是带 frontmatter 的 `.md`，审阅与日志是一行一条的 JSONL。人能 `cat`/`grep`/`git diff`，Agent 也能。另外导出 `compiled/index.md` 与 `graph.json` 供 Agent 一次读完全库。 |
| **编译而非检索** | 不做切片、不做 embedding。每次调用把**整篇文档**（带行号）+ 全库卡片索引 + 已由该文档编译出的卡片全文交给 LLM，让模型**更新**已有知识而不是重复创建（Karpathy "LLM Wiki" 式的知识编译）。 |
| **LLM 只提议，人类决定** | LLM 产出的每个修订都进入审阅队列；读者只看到管理员发布过的修订。已发布卡片的新修订在审阅期间，旧的已发布版本继续对读者可见。 |
| **可核验，不靠信任** | 模型的每条结论必须附 `[E1]` 证据：原文路径 + 行号 + **逐字引用**。系统机械核对引用是否真的在那几行（精确 / 位置偏移 / 近似 / 未找到），把结果摆在审阅者面前。 |
| **全程可观测** | 每次 LLM 调用落盘：系统提示、用户提示（原样）、原始输出、模型思考摘要、用量、耗时、费用、解析结果、校验发现、写了哪些卡片。 |
| **轻量** | 单进程 `ThreadingHTTPServer`；卡片索引在内存、按文件增量更新；派生结构按状态缓存；静态资源 gzip。上万张卡片、两千篇文档实测见 1.5 节基准。 |

## 1.5 核心技术：三种知识结构 + 一个引擎

卡片只是"页面"。系统真正的核心是在同一份经过审阅的知识上，同时维护三种互补的结构，再由一个轻量引擎支撑：

| 结构 | 回答的问题 | 实现（全部从文件派生，可随时重建） |
|---|---|---|
| **PageIndex 索引树**（`pageindex.py`） | "答案在哪里？"——像查手册目录一样逐层找到要读的内容 | **统一知识树**：`知识`（主题 → 卡片）+ `原文`（文件夹 → 文档 → 章节，带行号）。节点摘要分两级：结构摘要（标题 + 首句，免费）和 **LLM 编写的节点摘要**（`lkb index`：每篇文档一次调用，按 sha256 缓存，**增量**——文档不变就不再调用）。没有可用标题结构的长文档，由模型提出**虚拟章节**。问答时做**多轮树搜索**：在字符预算内广度优先渲染树（折叠节点标 `[+N]`），模型返回 `read / expand / done`；小库一轮看全，大库多一两次小调用——**提示词规模有上限，不随库增长**。 |
| **Wiki**（`wiki.py`） | "这个概念的全貌是什么？"——每一页都是导航枢纽 | 每张卡片组装成 Wiki 页：面包屑（主题路径）、下级页面、经审阅的双向类型化关系、互相提及的卡片、**原文中讨论此概念的章节**、涉及的实体、反向链接、尚不存在的页面（红链）。**实体页**：工具、设备、机构等不成卡的具名对象。**主题综述**：LLM 根据已发布的下级卡片写"主题地图"（op `hub`），经机械核验（链接必须存在、数字必须出现在下级卡片中）后**进入审阅**。**结构缺口**：有下级页面却没有综述的主题、图谱中紧密相连却分属不同主题的卡片群。`lkb export` 导出静态 Markdown Wiki（`compiled/wiki/`）。 |
| **知识图谱**（`graph.py`） | "它们之间是什么关系？怎么联系起来的？" | **分层的类型化图**，每条边带层与认识论标签：`reviewed`（审阅过的类型化关系、上下级、wiki 链接）· `linked`（**确定性实体链接**：文本中出现了某张卡片的标题或别名；歧义名不链接；按 idf 排序，每个来源最多保留 N 条——不会"提及爆炸"）· `indexed`（索引阶段识别的实体，名称须在原文中**逐字出现**，与卡片同名的实体即是该卡片）· `provenance`（出处）。**本体约束**写在 `SCHEMA.md` 第 8 节（实体类型；关系的主体 → 客体类型），违反项由 lint 报告。查询：k 跳邻居、**解释型最短路径**（优先走审阅过的关系）、自我中心子图、PageRank 中心度、标签传播社区。图谱同时参与问答导航（词匹配命中的卡片的强关系邻居作为线索）。 |
| **引擎**（`textindex.py`、`store.py`、`fsck.py`、`bench.py`） | 快、稳、可靠 | **BM25 全文检索**（中文二元切分，无需分词词典、无需空格），覆盖卡片与原文章节，增量更新。**增量卡片索引**（按文件 mtime/size，只重新解析变化的文件）。所有派生结构（检索、树、图谱）按"卡片代数 + 原文状态 + 规范版本"缓存。**跨进程写锁**（fcntl.flock，Web 服务、CLI、MCP 可同时写同一数据目录）+ **fsync 后原子替换**。`lkb fsck` 校验文件一致性（当前修订 vs 不可变修订、原文 sha、可解析性、中断写入残留），`--repair` 只清理残留、重建缓存，从不改动知识。`lkb bench` 合成库基准测试。 |

**基准**（`lkb bench`，单进程、纯 Python、无 LLM）：

| 规模 | 卡片索引（冷 / 改一张后） | 卡片检索 p50 | 原文章节检索 p50 | 图谱查询（2 跳 / 路径） | Wiki 页 | 图谱冷构建 / 改一张后 | 内存峰值 |
|---|---|---|---|---|---|---|---|
| 2 000 卡片 · 400 文档 · 6 011 章节 | 155 ms / 9 ms | 4.6 ms | 7 ms | 0.1 / 1 ms | 0.09 ms | 1.0 s / — | 118 MB |
| 10 000 卡片 · 2 000 文档 · 29 577 章节 | 640 ms / 52 ms | 24 ms | 46 ms | 0.2 / 8 ms | 0.1 ms | 4.7 s / 1.1 s | 532 MB |

基准测试中发现并修复的问题：通用别名导致的"提及边爆炸"（530 万条边、1.7 GB → 1.2 万条边、118 MB）、每次调用都重新分类所有原文（403 ms → 7 ms 的章节检索）、名称扫描的线性前缀比较（图谱冷构建 10 s → 4.7 s，并按文本缓存，改一张卡片只重扫这一张）。

## 2. 两层知识结构

```
第一层  sources/        原始 Markdown（原样，版本化，带上传者）
            │  整篇 + 行号
            ▼
        LLM 知识编译器  ──→ traces/<run>/  （完整过程记录）
            │  JSON：卡片 + 关系 + 证据
            ▼
第二层  compiled/cards/   ① 文档摘要层：每篇文档一张 summary 卡片（OpenKB）
                          ② 知识层：概念 / 方法 / 模型 / 参数…（主题层级 + 类型化关系 + [[链接]] + 证据）
            │  审阅 → 发布
            ▼
        读者可见的知识库 / 图谱 / compiled/index.md / graph.json
```

### 第一层：原始文档（Layer 0）
- 上传单个文件、多个文件或整个文件夹（Web 端支持选择文件夹；CLI `lkb upload <dir>`），保持原目录结构。
- **永不改写**：同一路径重新上传且内容变化时，旧字节存入 `history/`，版本号 +1；记录每一版的上传者、时间、sha256、说明。停用（retire）也只是归档，不删除。
- **尊重作者的索引**：导航顺序依次参考目录下 `SUMMARY.md / index.md / README.md / _index.md` 中链接出现的顺序，再参考 frontmatter 的 `weight / nav_order / sidebar_position`，最后按标题。文档标题取 frontmatter `title` 或首个 `#` 标题。
- **链接照常工作**：相对链接（含 `../`、`#锚点`）、图片在 Web 中被解析到对应文档 / 资源；可切换"渲染视图"与"带行号原文"，可查看任意历史版本。
- 每篇文档页显示"由此文档编译的知识"，原文变化后相关卡片自动标记为**过时（stale）**。
- **HTML 原件**（课程网页、导出的 wiki 等）：原样保存为记录来源（可随时查看 / 下载，以 `sandbox` 方式提供，脚本不会执行），同时用内置转换器（`html2md.py`，仅标准库）生成同名 `.md` 作为编译对象。转换保留标题层级、列表、表格、代码、链接（同目录 `.html` 链接自动改为 `.md`），内嵌 SVG 示意图的文字标签保留为「图示文字」；frontmatter 记录 `converted_from`、原件 sha256 与转换器版本。导航中只显示转换后的文档，页面顶部提供原件链接；作者亲自写的同名 `.md` 永远不会被转换结果覆盖。

### 第二层：知识卡片（Layer 1）
一张卡片 = 一个概念 / 方法 / 模型 / 参数 / 指标 / 问题……（类型见 `cards.py: CARD_TYPES`），例如：

```markdown
---
id: "hopkins-imaging-model"
title: "Hopkins 部分相干成像模型"
type: "model"
parent: "imaging-models"                      ← 主题层级（topic 可嵌套）
aliases: ["Hopkins formula", "TCC"]
summary: "把光源与光瞳合并为 TCC 的部分相干成像标准模型。"
relations: [{"rel": "uses", "target": "socs-decomposition"}, ...]   ← 类型化关系（图谱的边）
evidence: [{"id": "E1", "path": "imaging/hopkins.md", "lines": "3-3",
            "quote": "Hopkins 公式是计算光刻中…", "check": "exact", ...}]
grounding: {"exact": 3, "missing": 0, "total": 3, "score": 1.0}
rev: 2                 status: "in_review"     published_rev: 1     lifecycle: "active"
origin: {"kind": "llm", "run": "20261120T…", "model": "claude-opus-5-5"}
---
Hopkins 模型把照明光源和投影光瞳合并为传输交叉系数 TCC [E1]，常用 SOCS 分解加速 [[socs-decomposition]] [E2]…
```

- **图谱** = `parent`（层级边）+ `relations`（18 种类型化关系，含 `contradicts` 用于标出冲突）+ 正文 `[[wikilink]]`。由内存索引实时生成，不需要图数据库。
- **层级** = topic 卡片构成的主题树（成像模型 → Hopkins → TCC 分解…），Web 左侧导航即此树。
- 每次修改（LLM 编译或人工编辑）生成不可变修订 `compiled/revisions/<id>/rNNNN.md`，可任意两版对比 diff。

## 3. 审阅与发布治理

```
            submit            approve × N（可配置）       publish（管理员）
  draft ───────────▶ in_review ───────────────▶ approved ─────────────▶ published
                       │ request_changes          │ return 打回
                       ▼                          ▼
               changes_requested ◀────────────────┘ ── 编辑/重新编译 → 新修订 → in_review
                       reject ─▶ rejected ── reopen（管理员）─▶ in_review

  卡片整体生命周期（管理员）：active ──withdraw 下架──▶ withdrawn ──restore──▶ active
                                active ──supersede 替换为 X──▶ superseded（读者被引导到 X）
```

- **审阅者**：通过 / 要求修改 / 拒绝 / 仅评论；评语可锚定到某条证据或段落（如 `E2`）；可直接编辑卡片（生成新修订、来源记为本人，**不能自己批准自己的修改**——可配置）。
- **管理员**：发布、打回、否决、重新审阅、下架、恢复、替换；管理用户与角色（角色变更对已登录用户立即生效；系统拒绝移除最后一个管理员）。
- 投票按**修订**计：新修订会让旧票失效。规则：任一拒绝 → rejected；任一要求修改 → changes_requested；通过数 ≥ `review.required_approvals` → approved。
- 所有动作写入 `reviews/<id>.jsonl`（卡片维度）与 `log/events.jsonl`（全局审计），只追加、不修改。

## 4. LLM 知识编译器（`compiler.py`）

系统提示由两部分组成：**固定协议**（写在代码里：证据规则、认识论标签、输出 JSON 格式，系统靠它来核验和存储）+ **`SCHEMA.md`**（领域专家维护：主题骨架、卡片类型用法、命名写作规范、关系含义、不编译什么）。

每次调用的输入（不切片、不检索）：
1. **全库卡片索引**：`id | type | parent | title | summary`，让模型复用已有 id、建立关系、避免重复；
2. **已由这些文档编译出的卡片全文**（按出处确定性选取，不靠相似度）——重新编译时模型在此基础上更新；
3. **文档目录树**（标题层级 + 行号范围 + 每节首句）；
4. **完整原文**（或超长文档的某一章节），每行带行号，附版本、sha256、上传者；
5. 可选的操作员附加指令。

**超长文档**（超过 `compile.max_doc_chars`，默认 30 万字符）：沿目录树切分为若干章节，**按顺序**逐章编译。章节过大时下钻到子标题；只有单个叶子章节本身超长时才按行切分（这种情况会明确标注）。每章编译时都能看到全文目录，以及前面章节已产出的卡片全文（它们属于"由该文档编译出的卡片"），所以模型是在**更新**，而不是从零开始。只有最后一章成功后，该文档才算编译完成；中途失败则停止该文档的后续章节。

**关系的认识论标签**：每条关系为 `{rel, target, basis, confidence, evidence}`，其中 `basis ∈ extracted（原文明确，必须引用证据）/ inferred（推断）/ ambiguous（存疑，交给人判断）`。

输出是一个 JSON：`cards[]`（create/update、字段、关系、证据、置信度、修改说明）+ `notes`（给审阅者的不确定性 / 冲突说明）。
系统提示（`SYSTEM_PROMPT`）规定：原子化卡片、稳定的英文 kebab-case id、保持原文语言、**事实必须有逐字证据**、不得用模型自身知识断言事实、冲突用 `contradicts` 标出并降低置信度。

编译后的处理流水线：解析 → **校验**（id 规范化、批内重复、未知类型/关系、指向不存在的卡片、证据引用了非本次来源、正文引用了未定义证据……全部记录为 findings，不静默丢弃）→ **证据核验** → 写入新修订（`in_review`）→ 更新导出。

**增量**：只编译 sha256 自上次成功编译以来变化的文档（`lkb compile` 默认；`--all` 强制）。`compile.files_per_call` 可让多篇整文档在一次调用中一起编译，便于跨文档链接。

**ID 归一**：模型引用的 id 若不存在，按「卡片英文名 / 缩写 / 别名的 slug → 连字符首字母缩写（`optical-proximity-correction` → `opc`）」确定性地映射到已有卡片，每次映射都记入校验发现。

**推理预算**（推理型模型的共性问题：长输入 + 长结构化输出 + 多约束时，会在推理中把整份 JSON 先"打一遍草稿"）：
- `openrouter_reasoning` 默认 `low`，`reasoning_by_stage` 可分别设置编译 / 问答导航 / 作答；
- 协议要求"简短规划、不在推理中草拟输出"；
- **推理看门狗**：流式输出时推理超过 `reasoning_watchdog_chars`（默认 2 万字符）而正文仍为空，即中断并降一档重试，过程写入调用记录；
- 更进一步的方向（未实现）：把"决策"（建哪些卡、并入谁、关系）与"誊写"（正文、证据）拆成两次调用。

**后端**（`config.json → llm.backend`）：
- `anthropic`：官方 SDK，默认 `claude-opus-5-5`、流式、adaptive thinking 并返回**思考摘要**（供审阅者理解模型为何这样编译）、`effort` 可配、服务端拒答回退（server-side fallback）已启用。需 `ANTHROPIC_API_KEY`。
- `openrouter`：任意 OpenRouter 模型（默认 `z-ai/glm-5.3-flash`，极低成本），仅标准库、流式、记录推理文本与平台上报的费用。需环境变量 `OPEN_ROUTER_API_KEY`。
- `command`：任意命令行（标准输入收提示，标准输出给结果），可接本地模型 / 内网网关。
- `mock`：确定性启发式（标题→卡片，首句→证据），离线测试与演示用，**不代表真实编译质量**。

## 4.5 卡片粒度：什么值得做成一张卡片（`quality.py`、`consolidate.py`）

一张卡片 = 一个概念：读者一次读完（约 1–3 分钟），智能体一次加载（约 1–2 千 token）。篇幅按“阅读单位”计（一个汉字或一个英文单词，中英混排公平）：

| 界限 | 默认 | 含义 |
|---|---|---|
| `min_units` | 60 | 低于此是单一事实，不是概念 → 并入相关卡片 |
| `target_max` | 900 | 约 2–3 分钟、约 1.2k token，舒适上限 |
| `hard_max` | 1600 | 约 4 分钟、约 2k token，超过必须整合或拆分 |
| `max_evidence` | 24 | 证据过多通常意味着一张卡片装了多个概念 |
| `max_appends` | 3 | “补充（来自…）”段过多 → 读起来像摘抄堆叠 |

三层机制：
1. **预防**：`SCHEMA.md` 写明粒度规范；编译提示给出界限，并在每张已有卡片上标注当前篇幅（`units=…`）；卡片接近上限时，新内容建子概念卡（上级 = 原卡），而不是继续追加；编译时篇幅越界记入校验发现。
2. **纠正（LLM，整合重写 / 拆分）**：`lkb consolidate --list | ID | --auto [--from-rev N]` 或审阅工作台按钮。只允许使用卡片已有的、已核验的证据（不引入新事实）；未被引用的证据留在父卡，出处永不丢失；结果以新修订进入审阅。若整合后正文引用的证据不足一半，判为**高风险**（“可能丢失内容，考虑拆分”）。语义差异把“移至子卡片的证据”与“真正移除的证据”分开显示。
3. **合并（确定性，管理员）**：`lkb merge 薄卡 --into 目标卡`，薄卡标记为“已被替换”，读者自动跳转。

真实模型实测（glm-5.3-flash）：“工艺窗口”1143 → 274 字/词的概览 + 3 张子概念卡（FEM/PWQ、SMO 机制、签核准则）；“OPC 技术分类”1568 → 323 + 规则型 OPC（448）+ 模型型 OPC（562），证据覆盖 97%，全部 100% 可核验。

## 4.6 分级审阅与批量通过（`quality.assess`、`Cards.batch`）

每张卡片都有**审阅风险**（低 / 中 / 高）及可操作的理由：
- 高：证据无法核验（近似 / 未找到 / 来源缺失）、存疑或矛盾关系、原文已更新、无证据、置信度 < 0.5、篇幅超过硬上限、整合后证据覆盖不足一半。
- 中：省略式引用、跨文档合并、人工修改、问答回写、整合重写、修改已发布内容、置信度 0.5–0.7、推断关系占多数、数值/结论类知识、粒度偏长 / 过薄 / 补充段过多。
- 低：以上都没有。

**只有低风险卡片可以批量通过（服务器端强制）**；批量必须填写评语（≥10 字）；每张卡片各自留下审阅记录（带批次号），审计日志记录 `review.batch_approve` 事件（通过 / 跳过清单与判定标准快照）。管理员可批量发布已通过的卡片（同样必须写评语、留审计）。CLI：`lkb risk [ID]`、`lkb batch-approve --low-risk -m …`、`lkb batch-publish --all-approved -m …`。

## 4.7 多种形式展现知识：刻面与视图（`facets.py`、`annotate.py`）

同一份经审阅的知识，以七种视图呈现（「知识」页顶部切换，共用一个适用条件筛选栏）：

| 视图 | 回答的问题 | 数据来源 |
|---|---|---|
| 卡片（Wiki） | 这个概念是什么 | 卡片正文 + 证据 |
| 主题树 | 知识如何组织 | parent 层级 |
| 图谱 | 概念之间如何关联 | 类型化关系（认识论线型） |
| 思维导图 | 以某主题为中心的全貌 | 下级概念 + 相关概念，可逐级展开 |
| 时间线 | 技术如何演进 | 事件刻面（按年份；无年份的按工艺节点由大到小） |
| 对比表 | 参数 / 指标在不同方法、条件下的取值 | 事实刻面（取值、单位、条件，逐条链接原文） |
| 文档目录 | 原文结构 | 文档目录树（PageIndex） |

**刻面**（卡片的结构化附加信息），每一条都必须引用卡片中已核验的证据：
- **适用条件** `conditions [{dim, value, evidence}]`：维度由 `SCHEMA.md`「适用条件维度」声明（默认：工艺节点、波长、NA、图层、掩模、应用）。工艺节点按区间匹配（“≤7nm”覆盖“5nm”），波长有同义词（EUV = 13.5nm）。筛选时：明确符合的显示，原文未说明条件的视为**通用**照常显示，标明适用于其他条件的排除。问答按条件导航，并要求答案说明结论成立的条件。
- **事件** `events [{when, what, evidence}]` → 时间线；**事实** `facts [{name, value, unit, conditions, evidence}]` → 对比表。
- **支持检查（机械）**：数值必须出现在所引原文中，词语多数出现；事件和条件也可出现在所引行前后 3 行（表格同行、小节标题）。未通过的刻面不删除（治理留痕），但视图与筛选不使用、读者看不到，审阅者看到“原文不支持”标记且风险升为中。`lkb reverify` 会刷新支持标记。
- 新编译直接产出刻面；已有卡片用 `lkb annotate --auto`（回填）与 `--unsupported`（重做）补齐，结果作为新修订进入审阅。

## 4.8 问题登记簿（`issues.py`）

矛盾、开放问题、知识缺口、读者报告是独立条目（`issues/*.json`），有状态（未解决 / 已解决 / 不处理）与处理记录，同一问题自动去重（记“出现 N 次”）：
- 编译器报告的矛盾与开放问题、每条 `contradicts` 关系 → 自动登记；
- 问答中的“资料缺口” → 知识缺口（告诉管理员该补哪些文档）；
- 读者在卡片上“报告问题” → 读者报告。
未解决的矛盾与开放问题显示在相关卡片上，**所有读者可见**（知识库不粉饰矛盾）。CLI：`lkb issues`、`lkb issue ID resolve -m …`、`lkb report CARD 标题`。

## 4.9 原文处理策略

每篇原文有处理策略：**编译**、**仅参考**（可浏览、可在问答中导航，不编译成卡片）、**排除**。目录页 / 导航页 / 链接列表自动识别为“仅参考”（ASML 资料中的课程目录页即如此），管理员可覆盖：`lkb policy PATH compile|reference|exclude|auto`。

## 4.10 面向智能体：MCP 服务（`mcp.py`）

`lkb --user reader1 mcp` 以标准输入输出提供 MCP 工具（仅标准库）：`search_knowledge`、`get_card`、`knowledge_tree`、`list_documents`、`document_outline`、`read_source`、`verify_quote`、`facts`、`timeline`、`list_issues`、`search_sections`（原文章节 BM25）、`browse_tree`（PageIndex 逐层浏览）、`wiki_page`、`graph_neighbors`、`graph_path`、`ask`。权限随配置用户：读者身份只能看到**已发布修订**的内容；所有工具都支持适用条件；每次调用写入审计日志。接入 Claude Code：
```
claude mcp add lithokb -- python3 /path/to/litho-kb/lkb --root /path/to/kbdata --user reader1 mcp
```

## 5. 问答：导航 → 精读 → 作答 → 回写（`ask.py`）

1. **导航**（PageIndex 树搜索，`lkb-ask/2`）：模型在**统一知识树**上推理（见 1.5），同时看到线索（BM25 命中的卡片与原文章节、图谱中的强关系邻居），**说明理由**地选出要读的卡片（≤12）与原文章节（≤8）；树放不下时先展开折叠节点，最多 `query.nav_max_rounds` 轮，每轮提示词不超过 `query.nav_budget_chars`。每一轮（展开了什么、读了什么、提示词多大）都记录在 trace 中。没有向量、没有相似度阈值。
2. **精读作答**：只读选中的卡片全文与章节原文（带行号），回答中用 `[[卡片]]` 链接，原文事实用 `[S1]` 引用——引用同样被逐字核验。资料不足时必须说明缺口。
3. **回写**（LLM Wiki 的知识复利）：审阅者可把好的问答提交为 `synthesis`（问答综合）卡片，`[S1]` 自动转为 `[E1]` 证据，进入正常的审阅 → 发布流程。
- 读者只能基于**已发布**知识提问；审阅者可选择包含审阅中的卡片。两次 LLM 调用都完整记录（`nav-*` 与 `ans-*` 文件）。

## 6. 可观测性（"LLM 做了什么"）

`traces/<run>/`：`run.json`（类型 compile/query、模型、effort、提示词版本、**SCHEMA 版本**、分章信息、来源 sha、上下文规模、用量、耗时、费用估算、stop_reason、时间线、校验发现、核验统计、写出的卡片）· `system.md` · `prompt.md` · `response.md` · `thinking.md` · `parsed.json` · `error.txt`。

Web「LLM观测」页：总调用 / tokens / 费用 / 平均耗时 / 引用可核验率、常见校验问题排行、关系认识论状态分布、**按 SCHEMA 版本对比可核验率**（修改规范后效果是否变好一目了然）、按模型统计；单次运行可逐页查看原始提示与输出。
审阅工作台右侧直接显示：该卡片的证据核验（模型声称的行 vs. 实际找到的行，原文高亮）、编译器对这张卡片的校验发现、编译备注与思考摘要。
「健康检查」页（`lkb lint`）：悬空关系 / 链接 / 上级、原文已变化、引用未找到、无证据、存疑关系、缺少摘要卡片、**原始文档高度重复**（字符 4-gram 指纹：Jaccard 相似度或包含度，忽略排版与链接）等。

## 7. 三种用户与 Web UI

| 页面 | 读者 | 审阅者 | 管理员 |
|---|:-:|:-:|:-:|
| 首页、知识（主题树 + 卡片 + 文档摘要层）、图谱、原始文档（树 / 目录树 / 渲染 / 行号 / 历史版本）、搜索 | ✓ | ✓ | ✓ |
| 问答（基于已发布知识；阅读计划与引用核验可见） | 登录后 ✓ | ✓（可含未发布） | ✓ |
| 上传文档；审阅队列（存疑关系优先）与审阅工作台（卡片 / 差异 / 编辑 / 审阅记录 + 证据核验 + 认识论状态）；问答回写；LLM 观测；健康检查；查看编译规范 | | ✓ | ✓ |
| 发布台（发布 / 打回 / 下架 / 恢复 / 替换）；知识编译（选文档、选后端、附加指令、任务进度）；**编辑编译规范**；用户管理；审计日志；停用原文 | | | ✓ |

`config.json → public_read`：为 `true` 时匿名访客可阅读已发布知识与原文；设为 `false` 则必须登录。

## 8. CLI（无界面，完整流程）

```
lkb init [--admin NAME]                     lkb serve [--host H --port P]
lkb user add|list|set NAME [--role R --password P --disable --enable]
lkb upload PATH [--prefix DIR --note TXT]   lkb sources tree|ls|show|history|retire [PATH] [--version N]
lkb compile [PATHS…] [--all --backend B --files-per-call N --instructions TXT --dry-run]
lkb queue | cards [--status S] | show ID [--rev N|--published] | diff ID A B | reviews ID
lkb approve|request-changes|reject|comment|submit ID -m "评语"
lkb publish|return|reopen|withdraw|restore ID [-m ...]   lkb supersede ID --by OTHER
lkb traces [ls|show RUN [--part prompt|response|thinking|system|parsed]|stats]
lkb ask 问题… [--all --file-back [标题]]   lkb queries   lkb file-back RUN [--title T --parent P]
lkb schema [show|set FILE -m 说明|history|diff --a N --b M]   lkb outline PATH
lkb search 词…   lkb lint   lkb log [--target ID]   lkb export      （全局：--root --user --json）
lkb index [PATHS…] [--status --force]      PageIndex：为变化的文档编写节点摘要 + 识别实体（增量）
lkb tree [--budget N --open ID…]           导航模型所见的统一知识树
lkb wiki home|page ID|entities|entity ID|gaps|export|hubs [ID|--auto]
lkb kg stats|neighbors ID|path A B|central|communities|findings [--depth N --layers reviewed,linked]
lkb fsck [--repair]   lkb bench [--cards N --docs M]   lkb ask … --cond wavelength:EUV,node:5nm
```
CLI 以 `--user`（或 `LKB_USER`）身份操作，同一套角色与流程规则约束（能运行 CLI 即已拥有数据目录的文件权限，因此信任其声明的身份）。

## 9. 数据目录

```
kbdata/
  config.json  users.json  secret.key
  SCHEMA.md                       编译规范（history/schema/vN.md 保存每一版）
  sources/…                       原文（当前版本）
  meta/sources.json               出处：版本、上传者、时间、sha256、历史
  history/sources/<path>@<v>      所有旧版本
  compiled/cards/<id>.md          卡片当前修订 + 流程状态
  compiled/revisions/<id>/rNNNN.md 不可变修订快照
  compiled/index.md  graph.json   已发布知识的导出（给人 / 给 Agent）
  compiled/log.md                 人可读的时间线：收录 / 编译 / 发布 / 下架 / 规范修改
  reviews/<id>.jsonl              审阅记录
  traces/<run>/…                  LLM 调用全记录
  log/events.jsonl                审计日志
```
整个目录可直接放进 git 做备份与差异审计。

## 10. 代码结构

| 文件 | 职责 |
|---|---|
| `lithokb/store.py` | 数据目录、配置、原子写、写锁、审计日志 |
| `lithokb/fm.py` | frontmatter 读写（无 YAML 依赖） |
| `lithokb/sources.py` | 第一层：上传、版本、出处、尊重索引的层级树、路径安全、HTML 收录 |
| `lithokb/html2md.py` | HTML → Markdown 转换（原件保留，转换结果带出处） |
| `lithokb/cards.py` | 第二层：卡片、修订、审阅状态机、证据核验、图谱、搜索、lint、导出 |
| `lithokb/compiler.py` | 协议 + SCHEMA 提示构建、分章编译、解析、校验（含认识论标签）、写入、trace、统计 |
| `lithokb/doctree.py` | 文档目录树（确定性）、目录文本、按结构分章 |
| `lithokb/pageindex.py` | 统一知识树、LLM 节点摘要与实体（增量）、预算内渲染、原文章节 BM25 |
| `lithokb/wiki.py` | Wiki 页 / 实体页 / 首页 / 结构缺口、主题综述（LLM + 机械核验）、静态导出 |
| `lithokb/graph.py` | 分层知识图谱：确定性实体链接、本体约束、邻居 / 路径 / 中心度 / 社区 |
| `lithokb/textindex.py` | BM25 倒排索引（中文二元切分，增量） |
| `lithokb/fsck.py` · `bench.py` | 文件一致性检查与修复 · 性能基准 |
| `lithokb/schema.py` | `SCHEMA.md` 的版本管理与差异 |
| `lithokb/ask.py` | 问答：导航 → 精读 → 作答 → 回写 |
| `lithokb/quality.py` | 卡片粒度度量与审阅风险分级 |
| `lithokb/consolidate.py` | 整合重写 / 拆分（LLM）与合并（确定性） |
| `lithokb/facets.py` | 刻面：适用条件匹配、支持检查、筛选 |
| `lithokb/annotate.py` | 已有卡片的刻面回填（LLM） |
| `lithokb/issues.py` | 问题登记簿 |
| `lithokb/mcp.py` | MCP 服务（智能体工具） |
| `lithokb/llm.py` | anthropic / command / mock 后端 |
| `lithokb/auth.py` | 用户、角色、pbkdf2 密码、HMAC 令牌 |
| `lithokb/server.py` | JSON API + 静态前端 |
| `lithokb/web/` | 单页前端（自带安全 Markdown 渲染器与力导向图谱，无框架） |
| `lithokb/cli.py` | CLI |
| `tests/test_lkb.py` · `test_core.py` | 端到端测试 · 核心引擎测试（树搜索、图谱、Wiki、跨进程锁、fsck；离线） |

## 11. 当前边界与下一步

- 公式以 TeX 原文显示（未内置 KaTeX，保持离线零依赖；可后续按需本地引入）。原文中的 raw HTML 会被转义显示（安全优先）。
- 写锁是跨进程的（fcntl.flock，POSIX）；读不加锁（全部写入都是 fsync 后的原子替换）。Windows 上退化为进程内锁。
- 图谱在卡片变化后整体重建（文本扫描结果有缓存，1 万张卡片约 1 秒）；更大规模可做按卡片的增量图谱。
- mock 后端只用于流程验证；真实编译质量需要接入 `anthropic`（或 `command`）后用真实资料评测——这正是下一阶段"真正意义上的测试"的内容：编译质量（证据核验率、重复率、审阅通过率）、性能（大库下的索引 / 编译吞吐）与提示词迭代（`PROMPT_VERSION` 已记录在每个 trace 中，便于对比）。
