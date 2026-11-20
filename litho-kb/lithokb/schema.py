"""SCHEMA.md — the knowledge base's own "compiler source" (the LLM-Wiki idea).

The compiler prompt has two parts:
  * a fixed *protocol* in code (grounding rules, epistemic labels, JSON contract) —
    what the machinery needs to verify and store the output;
  * this *schema*, a Markdown file owned by the domain experts: ontology (topics,
    card types, relation meanings), naming and writing conventions, what to compile
    and what to ignore. Editing it changes how knowledge is compiled, without code.

Every edit is versioned (history/schema/vN.md) and every compile/query trace
records the schema version + sha it ran with, so behaviour changes are attributable.
"""
from __future__ import annotations

import difflib
import json

from .store import KB, LOCK, atomic_write, now, sha256

DEFAULT_SCHEMA = """# LithoKB 编译规范 (SCHEMA)

本文件定义计算光刻知识库的结构与写作规范。知识编译器（LLM）每次编译都会完整阅读本文件。
管理员可在「编译规范」页面修改；每次修改都有版本记录，编译记录中会注明所用版本。

## 1. 领域主题骨架（topic 卡片，优先复用这些 id）
- `imaging-models` 成像模型：Abbe / Hopkins、TCC、SOCS、矢量成像、偏振
- `resist-models` 光刻胶与刻蚀模型：阈值、扩散、显影、紧凑模型、刻蚀偏差
- `opc` 光学邻近效应修正：基于规则 / 基于模型、片段切分、EPE、收敛
- `ilt` 逆向光刻：曲线掩模、梯度优化、水平集、掩模规则约束
- `smo` 光源掩模协同优化
- `mask-3d` 掩模三维效应（M3D）与 EUV 特有效应：阴影、吸收层、随机效应
- `hotspot-dfm` 热点检测与可制造性设计
- `metrology-calibration` 量测与模型校准：CD-SEM、轮廓、校准流程、误差指标
- `ml-litho` 机器学习在计算光刻中的应用
- `compute-platform` 计算平台与加速：GPU、分布式、全芯片运行时间
可以新增主题，但必须挂在上述某个主题之下或说明理由（写入 notes）。

## 2. 卡片类型的使用
- `summary`：每篇原始文档一张，概括该文档讲了什么、包含哪些知识点（OpenKB 的 summaries 层）。
- `concept / method / model / algorithm`：跨文档的核心知识（OpenKB 的 concepts 层）。同一概念只能有一张卡片。
- `parameter / metric`：必须写明单位、典型取值范围及其出处；没有出处就不写数值。
- `issue`：已知问题、失效模式、限制条件。
- `result`：实验 / 仿真结论，必须注明条件（节点、NA、波长、光源……）。

## 3. 命名与写作
- id：英文 kebab-case，使用业界通用名，如 `optical-proximity-correction` 而非 `opc-method-1`。
- 标题：中文为主，括号内附英文或缩写，如「光学邻近效应修正 (OPC)」。
- 正文：先一句话定义，再列要点；公式保留 LaTeX；不要堆砌原文，要提炼。
- 别名 aliases：列出缩写、英文全称、常见中文异名，用于去重与搜索。

## 4. 关系的含义
- `uses`：A 的计算过程用到 B；`depends_on`：A 的正确性依赖 B（如 OPC 依赖已校准模型）。
- `improves / alternative_to / contrasts_with`：只有原文明确比较时才用 extracted，否则标 inferred。
- `contradicts`：两处来源说法冲突，必须在正文说明双方观点与出处。

## 5. 不编译的内容
- 目录页、导航页、版权声明、纯链接列表（可只生成 summary 卡片）。
- 与计算光刻无关的行政信息。
"""


def _path(kb: KB):
    return kb.root / "SCHEMA.md"


def _hist(kb: KB):
    return kb.root / "history" / "schema"


def ensure(kb: KB) -> None:
    if not _path(kb).exists():
        save(kb, "system", DEFAULT_SCHEMA, note="initial default schema")


def current(kb: KB) -> dict:
    ensure(kb)
    text = _path(kb).read_text("utf-8")
    versions = history(kb)
    v = versions[-1]["version"] if versions else 0
    return {"text": text, "version": v, "sha": sha256(text.encode())[:12]}


def history(kb: KB) -> list[dict]:
    p = _hist(kb) / "versions.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else []


def save(kb: KB, actor: str, text: str, note: str = "") -> dict:
    text = text.replace("\r\n", "\n")
    if not text.strip():
        raise ValueError("schema cannot be empty")
    with LOCK:
        versions = history(kb)
        sha = sha256(text.encode())[:12]
        if versions and versions[-1]["sha"] == sha:
            return versions[-1]
        v = (versions[-1]["version"] + 1) if versions else 1
        atomic_write(_hist(kb) / f"v{v}.md", text)
        atomic_write(_path(kb), text)
        entry = {"version": v, "sha": sha, "by": actor, "at": now(), "note": note, "chars": len(text)}
        versions.append(entry)
        atomic_write(_hist(kb) / "versions.json", json.dumps(versions, ensure_ascii=False, indent=1))
    kb.event(actor, "schema.update", f"v{v}", sha=sha, note=note)
    return entry


def version_text(kb: KB, v: int) -> str:
    p = _hist(kb) / f"v{int(v)}.md"
    if not p.exists():
        raise FileNotFoundError(f"schema v{v}")
    return p.read_text("utf-8")


def diff(kb: KB, a: int, b: int) -> str:
    ta = version_text(kb, a).splitlines(True) if a else []
    tb = version_text(kb, b).splitlines(True)
    return "".join(difflib.unified_diff(ta, tb, f"v{a}", f"v{b}", n=2))
