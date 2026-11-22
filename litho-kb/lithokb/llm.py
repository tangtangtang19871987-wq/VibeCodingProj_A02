"""LLM backends. Each returns an LLMResult with everything the trace needs.

* anthropic — Claude via the official SDK (`pip install anthropic`), streaming,
  adaptive thinking with *summarized* thinking returned so reviewers can read
  how the model reasoned, server-side refusal fallback enabled.
* command   — any CLI that reads the prompt on stdin and prints the answer
  (a local model wrapper, `claude -p`, an internal gateway script…).
* mock      — deterministic offline compiler for tests/demos (no network).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field


@dataclass
class LLMResult:
    text: str
    model: str
    backend: str
    usage: dict = field(default_factory=dict)
    latency_s: float = 0.0
    stop_reason: str = ""
    thinking: str = ""
    raw_meta: dict = field(default_factory=dict)


class LLMError(Exception):
    pass


class TransientLLMError(LLMError):
    """Rate limit / server error / connection problem — the CALL graph backs off and retries."""


class WatchdogAbort(LLMError):
    """The model kept reasoning past the watchdog limit without writing any answer —
    the CALL graph retries one reasoning-effort level lower."""

    def __init__(self, info: dict):
        super().__init__(f"reasoning watchdog abort at effort {info.get('effort')}")
        self.info = info


def call(cfg: dict, system: str, user: str) -> LLMResult:
    """Every LLM call runs through the LangGraph CALL graph (flows.py): invoke → step_down /
    backoff → invoke … → finish. Providers below perform exactly one attempt."""
    from .flows import run_call
    return run_call(cfg, system, user)


def attempt(cfg: dict, system: str, user: str) -> LLMResult:
    """One attempt at one backend (no retries here — retries are graph edges)."""
    backend = cfg.get("backend", "mock")
    t0 = time.time()
    if backend == "anthropic":
        r = _anthropic(cfg, system, user)
    elif backend == "openrouter":
        r = _openrouter(cfg, system, user)
    elif backend == "command":
        r = _command(cfg, system, user)
    elif backend == "mock":
        _mock_faults(cfg, user)
        r = _mock(system, user)
    else:
        raise LLMError(f"unknown backend {backend}")
    r.latency_s = round(time.time() - t0, 3)
    return r


def _anthropic(cfg: dict, system: str, user: str) -> LLMResult:
    try:
        import anthropic
    except ImportError as e:
        raise LLMError("backend 'anthropic' needs `pip install anthropic`") from e
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY or `ant auth login` profile
    model = cfg.get("model", "claude-opus-5-5")
    try:
        with client.beta.messages.stream(
            model=model,
            max_tokens=int(cfg.get("max_tokens", 64000)),
            system=system,
            messages=[{"role": "user", "content": user}],
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": cfg.get("effort", "high")},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.RateLimitError as e:
        raise TransientLLMError(f"rate limited: {e}") from e
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            raise TransientLLMError(f"API error {e.status_code}: {e.message}") from e
        raise LLMError(f"API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise TransientLLMError(f"connection error: {e}") from e
    text = "".join(b.text for b in msg.content if b.type == "text")
    thinking = "\n\n".join(getattr(b, "thinking", "") or "" for b in msg.content if b.type == "thinking")
    u = msg.usage
    usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
             "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0}
    meta = {"id": msg.id, "served_model": msg.model}
    if msg.stop_reason == "refusal" and getattr(msg, "stop_details", None):
        meta["refusal"] = {"category": msg.stop_details.category, "explanation": msg.stop_details.explanation}
    return LLMResult(text=text, model=msg.model, backend="anthropic", usage=usage,
                     stop_reason=msg.stop_reason or "", thinking=thinking, raw_meta=meta)


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _openrouter(cfg: dict, system: str, user: str) -> LLMResult:
    """Any model on OpenRouter (OpenAI-compatible chat API), stdlib HTTP only, streamed.

    * Key from $OPEN_ROUTER_API_KEY or $OPENROUTER_API_KEY.
    * `openrouter_reasoning` (default "low") bounds hidden reasoning: cheap reasoning models
      otherwise think for many minutes before writing the JSON (measured: >100 s of reasoning
      with no output vs 42 s end-to-end at "low" for one chapter).
    * Streaming gives stall detection (`stall_s` without any byte → error) instead of one
      long blocking read; reasoning text goes to the trace as "thinking"; OpenRouter's own
      usage accounting (tokens, reasoning tokens, cost) is recorded."""
    import urllib.error
    import urllib.request
    key = os.environ.get("OPEN_ROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise LLMError("backend 'openrouter' needs OPEN_ROUTER_API_KEY in the environment")
    model = cfg.get("openrouter_model") or "z-ai/glm-5.3-flash"
    body = {"model": model, "stream": True,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": int(cfg.get("openrouter_max_tokens", 32000)),
            "usage": {"include": True}}
    if cfg.get("json_mode", True):
        body["response_format"] = {"type": "json_object"}
    stall = int(cfg.get("stall_s", 120))
    # reasoning watchdog: if the model keeps thinking past `reasoning_watchdog_chars` without having
    # written a single character of the answer, abort (WatchdogAbort) — the CALL graph steps down.
    effort = cfg.get("openrouter_reasoning", "low") or "none"
    effort = "none" if effort in ("off", False) else effort
    watchdog = int(cfg.get("reasoning_watchdog_chars", 20000))
    body["reasoning"] = {"enabled": False} if effort == "none" else {"effort": effort}
    req = urllib.request.Request(OPENROUTER_URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    content, reasoning, usage_raw, finish, served, gen_id = [], [], {}, "", model, ""
    rchars, cchars = 0, 0
    try:
        with urllib.request.urlopen(req, timeout=stall) as resp:  # timeout applies per read → stall detection
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                ev = json.loads(line[6:])
                if "error" in ev:
                    raise LLMError(f"openrouter error: {json.dumps(ev['error'], ensure_ascii=False)[:800]}")
                served, gen_id = ev.get("model", served), ev.get("id", gen_id)
                if ev.get("usage"):
                    usage_raw = ev["usage"]
                for ch in ev.get("choices") or []:
                    d = ch.get("delta") or {}
                    if d.get("content"):
                        content.append(d["content"])
                        cchars += len(d["content"])
                    if d.get("reasoning"):
                        reasoning.append(d["reasoning"])
                        rchars += len(d["reasoning"])
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
                if watchdog and cchars == 0 and rchars > watchdog and effort != "none":
                    raise WatchdogAbort({"effort": effort, "reasoning_chars": rchars,
                                         "reasoning_tail": "".join(reasoning)[-400:]})
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:800]
        if e.code in (429, 500, 502, 503, 504):
            raise TransientLLMError(f"openrouter HTTP {e.code}: {detail}") from e
        raise LLMError(f"openrouter HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise TransientLLMError(f"openrouter connection error / stalled > {stall}s: {e}") from e
    u = usage_raw or {}
    usage = {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0)}
    if (u.get("completion_tokens_details") or {}).get("reasoning_tokens"):
        usage["reasoning_tokens"] = u["completion_tokens_details"]["reasoning_tokens"]
    if u.get("cost") is not None:
        usage["cost_usd_reported"] = u["cost"]
    return LLMResult(text="".join(content), model=served, backend="openrouter", usage=usage,
                     stop_reason={"length": "max_tokens", "stop": "end_turn"}.get(finish, finish or "unknown"),
                     thinking="".join(reasoning), raw_meta={"id": gen_id, "reasoning_effort": effort})


def _command(cfg: dict, system: str, user: str) -> LLMResult:
    cmd = cfg.get("command") or os.environ.get("LKB_LLM_COMMAND", "")
    if not cmd:
        raise LLMError("backend 'command' needs llm.command in config.json")
    prompt = f"<system>\n{system}\n</system>\n\n{user}"
    p = subprocess.run(shlex.split(cmd), input=prompt, capture_output=True, text=True, timeout=1800)
    if p.returncode != 0:
        raise LLMError(f"command failed ({p.returncode}): {p.stderr[-2000:]}")
    est = {"input_tokens_est": len(prompt) // 3, "output_tokens_est": len(p.stdout) // 3}
    return LLMResult(text=p.stdout, model=cfg.get("model", cmd.split()[0]), backend="command", usage=est,
                     stop_reason="exit_0", raw_meta={"stderr": p.stderr[-4000:]})


# ---- mock: transparent deterministic stand-ins (offline tests & demos) -----------
_H_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")


_FLAKY: dict[str, int] = {}


def _mock_faults(cfg: dict, user: str) -> None:
    """Test hooks that exercise the CALL graph's recovery edges offline."""
    if "[[MOCK:WATCHDOG]]" in user and (cfg.get("openrouter_reasoning") or "low") in ("high", "medium"):
        raise WatchdogAbort({"effort": cfg.get("openrouter_reasoning"), "reasoning_chars": 99999,
                             "reasoning_tail": "(mock) still thinking…"})
    if "[[MOCK:FLAKY]]" in user:
        k = hashlib.md5(user.encode()).hexdigest()
        _FLAKY[k] = _FLAKY.get(k, 0) + 1
        if _FLAKY[k] == 1:
            raise TransientLLMError("(mock) HTTP 503")


def _terms(q: str) -> list[str]:
    """Question terms: ASCII words and Chinese character bigrams (no embeddings)."""
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9]{2,}", q)]
    cjk = re.findall(r"[一-鿿]+", q)
    bigrams = [c[i:i + 2] for c in cjk for i in range(len(c) - 1)]
    stop = {"什么", "如何", "怎么", "为什", "哪些", "是否", "之间", "区别", "关系", "the", "what", "how"}
    return [t for t in dict.fromkeys(words + bigrams) if t not in stop]


def _mock(system: str, user: str) -> LLMResult:
    if "[[LKB:ANNOTATE]]" in system:
        text, note = _mock_annotate(user)
    elif "[[LKB:CONSOLIDATE]]" in system:
        text, note = _mock_consolidate(user)
    elif "[[LKB:HUB]]" in system:
        pages = re.findall(r'<page id="([^"]+)"[^>]*>\n# (.*?)\n(.*?)\n', user)
        body = "This topic covers:\n\n" + "\n".join(f"- [[{i}]]: {s}" for i, t, s in pages)
        text, note = _fence({"summary": "Topic overview", "body_md": body}), "list of sub-pages"
    elif "[[LKB:INDEX]]" in system:
        text, note = _mock_index(user)
    elif "[[LKB:NAVIGATE]]" in system and "<tree>" in user:
        text, note = _mock_tree_navigate(user)
    elif "[[LKB:NAVIGATE]]" in system:
        text, note = _mock_navigate(user)
    elif "[[LKB:ANSWER]]" in system:
        text, note = _mock_answer(user)
    else:
        text, note = _mock_compile(user)
    return LLMResult(text=text, model="mock-heuristic", backend="mock",
                     usage={"input_tokens_est": len(system + user) // 3, "output_tokens_est": len(text) // 3},
                     stop_reason="end_turn", thinking=f"(mock backend, no reasoning) {note}")


def _fence(obj) -> str:
    return "```json\n" + json.dumps(obj, ensure_ascii=False, indent=1) + "\n```"


def _mock_compile(user: str):
    if "[[MOCK:DEGENERATE]]" in user and "# Correction" not in user:  # test hook: first answer unusable
        return '{"": [""], "notes": "planned but did not write cards"}', "degenerate on purpose"
    """headings→cards, first sentence→evidence, plus one summary card per document."""
    cards, notes = [], []
    for m in re.finditer(r'<source path="([^"]+)"[^>]*>\n(.*?)\n</source>', user, re.S):
        path, block = m.group(1), m.group(2)
        sid = "summary-" + re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-")
        lines = [(int(mm.group(1)), mm.group(2)) for ln in block.splitlines()
                 if (mm := re.match(r"\s*(\d+)\|(.*)$", ln))]
        stem = re.sub(r"[^a-z0-9]+", "-", path.lower().rsplit(".", 1)[0]).strip("-")
        doc_topic, current, made = None, None, []
        for n, text in lines:
            h = _H_RE.match(text)
            if h and len(h.group(1)) <= 2:
                title = h.group(2).strip()
                ascii_ = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
                cid = f"{stem}-{ascii_}-{hashlib.md5(title.encode()).hexdigest()[:4]}".replace("--", "-")
                current = {"action": "create", "id": cid[:70].strip("-"), "title": title,
                           "type": "topic" if len(h.group(1)) == 1 else "concept",
                           "parent": doc_topic or "", "aliases": [], "summary": "", "body_md": "",
                           "relations": [], "evidence": [], "confidence": 0.5,
                           "change_note": f"mock compile of {path}"}
                if len(h.group(1)) == 1:
                    doc_topic = current["id"]
                cards.append(current)
                made.append(current)
                continue
            if current and text.strip() and not current["summary"] and not text.lstrip().startswith(("|", "```", "!", "-", "*", ">", "$")):
                sent = re.split(r"(?<=[.。!?！？])\s*", text.strip())[0]
                current["summary"] = sent[:240]
                current["body_md"] = f"{sent} [E1]"
                current["evidence"].append({"id": "E1", "path": path, "lines": f"{n}-{n}", "quote": sent[:200]})
        for c in made:
            if c["parent"] and c["parent"] != c["id"]:
                c["relations"].append({"rel": "subtopic_of", "target": c["parent"], "basis": "extracted",
                                       "confidence": 1.0, "evidence": "E1"} if c["evidence"] else
                                      {"rel": "subtopic_of", "target": c["parent"], "basis": "inferred", "confidence": 0.7})
        first = next(((n, t) for n, t in lines if t.strip()), (1, ""))
        cards.append({"action": "update" if f'<card id="{sid}">' in user else "create", "id": sid,
                      "title": f"Document summary: {path}", "type": "summary", "parent": "", "aliases": [],
                      "summary": f"{path} covers {len(made)} knowledge item(s).",
                      "body_md": f"This document opens with “{first[1].lstrip('# ').strip()}” [E1] and contains:" +
                                 "".join(f"\n- [[{c['id']}]]" for c in made),
                      "relations": [{"rel": "covers", "target": c["id"], "basis": "extracted", "confidence": 1.0,
                                     "evidence": "E1"} for c in made],
                      "evidence": [{"id": "E1", "path": path, "lines": f"{first[0]}-{first[0]}", "quote": first[1].lstrip('# ').strip()}],
                      "confidence": 0.6, "change_note": f"mock summary of {path}"})
        notes.append(f"mock: {path}: {len(lines)} lines")
    return _fence({"cards": cards, "notes": "; ".join(notes)}), "headings→cards, first sentence→evidence"


def _mock_annotate(user: str):
    """Deterministic facets from evidence quotes: EUV/193nm/NNnm mentions → conditions, years → events,
    'NAME > number unit' → facts."""
    conds, events, facts = [], [], []
    for m in re.finditer(r"^(E\d+) \| [^|]+ \| (.*)$", user, re.M):
        eid, q = m.group(1), m.group(2)
        if "EUV" in q:
            conds.append({"dim": "wavelength", "value": "EUV", "evidence": eid})
        for n in re.findall(r"(\d+)\s*nm\s*(?:及以下|以下|and below|or below)", q):
            conds.append({"dim": "node", "value": f"{n}nm and below", "evidence": eid})
        for y in re.findall(r"((?:19|20)\d\d)年?", q):
            events.append({"when": y, "what": q[:60], "evidence": eid})
        for name, op, val, unit in re.findall(r"([A-Za-z]{2,6})\s*([<>≥≤]=?)\s*(\d+(?:\.\d+)?)\s*(nm|%)", q):
            facts.append({"name": name, "value": f"{op} {val}", "unit": unit, "evidence": eid})
    return _fence({"conditions": conds, "events": events, "facts": facts}), "regex facets from evidence"


def _mock_consolidate(user: str):
    """Drop the addendum headings (legacy "补充" or "Addendum"), keep the evidence-marked paragraphs; split the second half off
    into one child card when the card is long."""
    m = re.search(r'<card id="([^"]+)">\ntitle: (.*?)\n.*?\n\n(.*)\n</card>', user, re.S)
    cid, title, body = m.group(1), m.group(2), m.group(3)
    paras = [p_.strip() for p_ in re.split(r"\n\s*\n", body) if p_.strip() and not re.match(r"#{1,6}\s*(?:补充|Addendum)", p_.strip())]
    split = len(paras) >= 6
    keep, rest = (paras[: len(paras) // 2], paras[len(paras) // 2:]) if split else (paras, [])
    children = []
    if rest:
        ids = sorted(set(re.findall(r"\[(E\d+)\]", "\n".join(rest))), key=lambda x: int(x[1:]))
        children.append({"id": f"{cid}-details", "title": f"{title}: details", "type": "concept",
                         "summary": "Details split off from the original card.", "body_md": "\n\n".join(rest), "evidence": ids})
    out = {"decision": "split" if children else "rewrite",
           "card": {"title": title, "summary": "Consolidated card.", "body_md": "\n\n".join(keep), "aliases": []},
           "children": children, "notes": "mock consolidation"}
    return _fence(out), "dropped addendum headings; halves when long"


def _mock_index(user: str):
    """PageIndex mock: node summary = first non-empty text line after the heading; entities = CamelCase /
    ALL-CAPS product-like words that occur in the text."""
    toc = re.search(r"# Table of contents\n(.*?)\n# Text\n", user, re.S)
    body = user.split("# Text\n", 1)[-1]
    lines = {int(m.group(1)): m.group(2) for m in re.finditer(r"^\s*(\d+)\|(.*)$", body, re.M)}
    nodes = {}
    for m in re.finditer(r"^\s*(n\d+) \[L(\d+)-(\d+)\] #+ (.*?)(?: — .*)?$", toc.group(1) if toc else "", re.M):
        nid, a, b, title = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
        first = next((lines[i].strip() for i in range(a + 1, b + 1) if i in lines and lines[i].strip()
                      and not lines[i].lstrip().startswith("#")), "")
        nodes[nid] = (title + "：" + re.sub(r"[*`]", "", first))[:60]
    title = re.search(r'title="([^"]*)"', user)
    words = re.findall(r"\b([A-Z][a-z]+[A-Z][A-Za-z]+|[A-Z]{3,}[0-9]*)\b", body)
    ents = [{"name": w, "type": "tool", "aliases": [], "nodes": []} for w in dict.fromkeys(words)][:5]
    return _fence({"doc_summary": f"{title.group(1) if title else ''}：" + "；".join(list(nodes.values())[:3])[:110],
                   "keywords": list(dict.fromkeys(_terms(title.group(1) if title else "")))[:6],
                   "nodes": nodes, "virtual_sections": [], "entities": ents}), "first line per section"


def _mock_tree_navigate(user: str):
    """Tree-search mock: read nodes whose line matches question terms (hints first); expand matching
    collapsed nodes in the first round."""
    q = re.search(r"<question>(.*?)</question>", user, re.S).group(1)
    terms = _terms(q)
    rnd = int((re.search(r'<round n="(\d+)"', user) or [0, 1])[1])
    read, expand = [], []
    for block in (re.search(r"<hints>\n(.*?)\n</hints>", user, re.S), re.search(r"<tree>\n(.*?)\n</tree>", user, re.S)):
        for ln in (block.group(1).splitlines() if block else []):
            m = re.match(r"\s*(\S+) \[([^\]]+)\]", ln)
            if not m or m.group(1) in ("k", "d"):
                continue
            h, tag = m.group(1), m.group(2)
            hit = sum(t in ln.lower() for t in terms)
            if not hit:
                continue
            if "[+" in ln and rnd == 1 and tag in ("dir", "doc", "topic") and h not in expand:
                expand.append(h)
            if tag not in ("dir", "doc") and h not in read:
                read.append(h)
    done = not expand or rnd >= 2
    return _fence({"reasoning": f"mock round {rnd}: matched terms {terms[:6]}", "read": read[:10],
                   "expand": [] if done else expand[:4], "done": done}), "term matching over the tree"


def _mock_navigate(user: str):
    q = re.search(r"<question>(.*?)</question>", user, re.S).group(1)
    terms = _terms(q)
    idx = re.search(r"<card-index>\n(.*?)\n</card-index>", user, re.S)
    cards = []
    for ln in (idx.group(1).splitlines() if idx else []):
        m = re.match(r"\s*- (\S+) \[", ln)
        if m and any(t in ln.lower() for t in terms):
            cards.append(m.group(1))
    sections = []
    for d in re.finditer(r'<doc path="([^"]+)"[^>]*>\n(.*?)\n</doc>', user, re.S):
        for ln in d.group(2).splitlines():
            m = re.match(r"\s*(n\d+) \[", ln)
            if m and any(t in ln.lower() for t in terms):
                sections.append({"path": d.group(1), "node": m.group(1), "why": "heading/gist matches question terms"})
    return _fence({"reasoning": f"mock: matched terms {terms[:8]}", "cards": cards[:8], "sections": sections[:4]}), \
        "term matching over the trees"


def _mock_answer(user: str):
    q = re.search(r"<question>(.*?)</question>", user, re.S).group(1)
    terms = _terms(q)
    parts, ev, used = [], [], []
    for m in re.finditer(r'<card id="([^"]+)"[^>]*>\n# (.*?)\n(.*?)\n', user):
        used.append(m.group(1))
        parts.append(f"- [[{m.group(1)}]]：{m.group(3)}")
    for m in re.finditer(r'<section path="([^"]+)"[^>]*>\n(.*?)\n</section>', user, re.S):
        for ln in m.group(2).splitlines():
            mm = re.match(r"\s*(\d+)\|(.*)$", ln)
            if mm and mm.group(2).strip() and not mm.group(2).startswith("#") and any(t in mm.group(2).lower() for t in terms):
                sid = f"S{len(ev) + 1}"
                ev.append({"id": sid, "path": m.group(1), "lines": f"{mm.group(1)}-{mm.group(1)}", "quote": mm.group(2).strip()[:200]})
                parts.append(f"- Source: {mm.group(2).strip()[:200]} [{sid}]")
                break
    ans = ("From the knowledge base:\n" + "\n".join(parts)) if parts else "Nothing in the knowledge base relates to this question."
    return _fence({"answer_md": ans, "evidence": ev, "used_cards": used, "confidence": 0.4 if parts else 0.0,
                   "gaps": "" if parts else "no relevant material"}), "stitched summaries + matching lines"
