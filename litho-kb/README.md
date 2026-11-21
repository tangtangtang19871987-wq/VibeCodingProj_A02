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
| **轻量** | 单进程 `ThreadingHTTPServer`；卡片索引在内存，按目录 mtime 懒重建；静态资源 gzip。几千篇文档、上万张卡片在笔记本上即可流畅运行。 |

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

## 5. 问答：导航 → 精读 → 作答 → 回写（`ask.py`）

1. **导航**（PageIndex）：模型看到问题、知识树（按主题层级排列的卡片与一句话摘要）、每篇文档的目录树，**说明理由**地选出要读的卡片（≤12）与原文章节（≤8）。没有向量、没有相似度阈值。
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
| `lithokb/doctree.py` | 文档目录树（PageIndex 思路，确定性）、目录文本、按结构分章 |
| `lithokb/schema.py` | `SCHEMA.md` 的版本管理与差异 |
| `lithokb/ask.py` | 问答：导航 → 精读 → 作答 → 回写 |
| `lithokb/llm.py` | anthropic / command / mock 后端 |
| `lithokb/auth.py` | 用户、角色、pbkdf2 密码、HMAC 令牌 |
| `lithokb/server.py` | JSON API + 静态前端 |
| `lithokb/web/` | 单页前端（自带安全 Markdown 渲染器与力导向图谱，无框架） |
| `lithokb/cli.py` | CLI |
| `tests/test_lkb.py` | 端到端测试（离线） |

## 11. 当前边界与下一步

- 公式以 TeX 原文显示（未内置 KaTeX，保持离线零依赖；可后续按需本地引入）。原文中的 raw HTML 会被转义显示（安全优先）。
- 单进程写锁：适合一个服务实例；CLI 与服务同时写同一数据目录时，原子写保证文件不损坏，但不做跨进程锁。
- mock 后端只用于流程验证；真实编译质量需要接入 `anthropic`（或 `command`）后用真实资料评测——这正是下一阶段"真正意义上的测试"的内容：编译质量（证据核验率、重复率、审阅通过率）、性能（大库下的索引 / 编译吞吐）与提示词迭代（`PROMPT_VERSION` 已记录在每个 trace 中，便于对比）。
