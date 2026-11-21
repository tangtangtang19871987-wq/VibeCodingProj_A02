"""`lkb bench` — measure the engine on a synthetic knowledge base (temporary directory).

Numbers that matter for "light, fast, low resource": cold/warm card index, incremental
re-index after one edit, BM25 search latency (cards and sections), unified tree build +
budgeted render (what the navigator sees), graph build and queries, wiki page assembly,
process memory. No LLM involved.
"""
from __future__ import annotations

import random
import resource
import statistics
import tempfile
import time

TERMS = ["光学邻近效应修正", "逆向光刻", "光源掩模协同优化", "掩模三维效应", "随机效应", "工艺窗口", "焦深", "曝光宽容度",
         "空间像", "光刻胶模型", "刻蚀偏差", "边缘放置误差", "热点检测", "模型校准", "轮廓量测", "部分相干成像", "传输交叉系数",
         "矢量成像", "偏振照明", "曲线掩模", "子分辨率辅助图形", "多重图形化", "全芯片运行时间", "GPU 加速", "High-NA",
         "EUV", "ArF 浸没", "OPC", "ILT", "SMO", "TCC", "SOCS", "EPE", "DOF", "CD-SEM", "Tachyon", "Calibre"]


def _sent(r: random.Random, n: int) -> str:
    return "，".join("".join(r.sample(TERMS, 2)) + r.choice(["的计算", "依赖", "影响", "用于", "取决于", "改善"])
                    for _ in range(n)) + "。"


def _timeit(fn, n=1):
    ts = []
    out = None
    for _ in range(n):
        t = time.perf_counter()
        out = fn()
        ts.append((time.perf_counter() - t) * 1000)
    return out, ts


def run_bench(n_cards: int = 2000, n_docs: int = 400, seed: int = 7) -> dict:
    from . import graph as G
    from . import pageindex as PI
    from . import sources as S
    from .cards import Cards, slug
    from .store import KB, atomic_write
    from . import fm
    from .wiki import Wiki
    r = random.Random(seed)
    res: dict = {"cards": n_cards, "docs": n_docs}
    with tempfile.TemporaryDirectory(prefix="lkb-bench-") as d:
        kb = KB(d)
        kb.init()
        t = time.perf_counter()
        items = []
        for i in range(n_docs):  # documents with a real heading structure
            parts = [f"# 文档 {i}：{r.choice(TERMS)}\n"]
            for j in range(r.randint(3, 8)):
                parts.append(f"\n## {j + 1}. {r.choice(TERMS)}与{r.choice(TERMS)}\n\n" + _sent(r, r.randint(3, 10)) + "\n")
                for k in range(r.randint(0, 3)):
                    parts.append(f"\n### {j + 1}.{k + 1} {r.choice(TERMS)}\n\n" + _sent(r, r.randint(2, 6)) + "\n")
            items.append({"path": f"set{i % 20}/doc{i}.md", "text": "".join(parts)})
        S.put(kb, "bench", items)
        res["write_sources_s"] = round(time.perf_counter() - t, 2)
        # cards written as files directly (the engine reads files; the write path is measured by tests)
        t = time.perf_counter()
        ids = [f"c{i}-" + slug(r.choice(TERMS))[:20] for i in range(n_cards)]
        topics = ids[: max(10, n_cards // 50)]
        for i, cid in enumerate(ids):
            title = f"{r.choice(TERMS)}{r.choice(['', '模型', '方法', '误差', '优化'])} {i}"
            meta = {"id": cid, "title": title, "type": "topic" if cid in topics else r.choice(["concept", "method", "model"]),
                    "parent": "" if cid in topics else r.choice(topics), "aliases": [r.choice(TERMS)],
                    "summary": _sent(r, 1), "status": "published", "rev": 1, "published_rev": 1, "lifecycle": "active",
                    "relations": [{"rel": r.choice(["uses", "depends_on", "improves", "contrasts_with"]),
                                   "target": r.choice(ids), "basis": "extracted"} for _ in range(r.randint(0, 4))],
                    "evidence": [], "sources": [{"path": f"set{(i % n_docs) % 20}/doc{i % n_docs}.md", "sha": ""}]}
            body = _sent(r, r.randint(8, 40)) + f"\n\n参见 [[{r.choice(ids)}]]。\n"
            text = fm.dump(meta, body)
            atomic_write(kb.cards_dir / f"{cid}.md", text)
            atomic_write(kb.revs_dir / cid / "r0001.md", text)
        res["write_cards_s"] = round(time.perf_counter() - t, 2)
        cards = Cards(kb)
        _, ts = _timeit(cards.index)
        res["index_cold_ms"] = round(ts[0], 1)
        _, ts = _timeit(cards.index, 20)
        res["index_warm_ms"] = round(statistics.median(ts), 3)
        p = kb.cards_dir / f"{ids[5]}.md"
        m, b, _ = fm.split(p.read_text("utf-8"))
        atomic_write(p, fm.dump({**m, "summary": "改过的摘要"}, b + "\n新增一句。"))
        _, ts = _timeit(cards.index)
        res["index_after_1_edit_ms"] = round(ts[0], 1)
        _, ts = _timeit(lambda: cards.text_index(False))
        res["bm25_build_cards_ms"] = round(ts[0], 1)
        qs = [r.choice(TERMS) + r.choice(TERMS) for _ in range(50)]
        lat = [_timeit(lambda q=q: cards.search(q, visible_only=False, limit=20))[1][0] for q in qs]
        res["search_cards_p50_ms"] = round(statistics.median(lat), 2)
        res["search_cards_p95_ms"] = round(sorted(lat)[int(len(lat) * 0.95) - 1], 2)
        _, ts = _timeit(lambda: PI.section_index(kb))
        res["bm25_build_sections_ms"] = round(ts[0], 1)
        res["sections"] = len(PI.section_index(kb))
        lat = [_timeit(lambda q=q: PI.section_index(kb).search(q, 20))[1][0] for q in qs]
        res["search_sections_p50_ms"] = round(statistics.median(lat), 2)
        tree, ts = _timeit(lambda: PI.KnowledgeTree(kb, cards, readers=False))
        res["tree_build_ms"] = round(ts[0], 1)
        res["tree_nodes"] = len(tree.nodes)
        H = PI.Handles(tree)
        (txt, _), ts = _timeit(lambda: tree.render(["k", "d"], H, 24000))
        res["tree_render_24k_ms"] = round(ts[0], 1)
        res["tree_render_lines"] = txt.count("\n") + 1
        g, ts = _timeit(lambda: G.build(kb, cards, readers=False))
        res["graph_build_cold_ms"] = round(ts[0], 1)
        _, ts = _timeit(lambda: G.build(kb, cards, readers=False), 5)
        res["graph_build_cached_ms"] = round(statistics.median(ts), 3)
        res["graph"] = {"nodes": len(g.nodes), "edges": len(g.edges)}
        p2 = kb.cards_dir / f"{ids[7]}.md"
        m2, b2, _ = fm.split(p2.read_text("utf-8"))
        atomic_write(p2, fm.dump(m2, b2 + "\n另一句新增内容。"))
        _, ts = _timeit(lambda: G.build(kb, cards, readers=False))
        res["graph_rebuild_after_1_edit_ms"] = round(ts[0], 1)
        lat = [_timeit(lambda c=c: g.neighbors(c, 2))[1][0] for c in r.sample(ids, 30)]
        res["graph_neighbors2_p50_ms"] = round(statistics.median(lat), 2)
        lat = [_timeit(lambda a=a, b=b: g.path(a, b))[1][0] for a, b in zip(r.sample(ids, 30), r.sample(ids, 30))]
        res["graph_path_p50_ms"] = round(statistics.median(lat), 2)
        _, ts = _timeit(lambda: g.pagerank())
        res["pagerank_ms"] = round(ts[0], 1)
        W = Wiki(kb, cards)
        lat = [_timeit(lambda c=c: W.page(c, readers=False))[1][0] for c in r.sample(ids, 20)]
        res["wiki_page_p50_ms"] = round(statistics.median(lat), 2)
        res["max_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    return res


__all__ = ["run_bench"]
