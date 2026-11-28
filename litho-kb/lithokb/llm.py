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


def degenerate_tail(text: str, window: int = 3000) -> str:
    """Why the end of a streamed answer looks degenerate ("" if it does not): a long run of whitespace, or one
    short pattern repeated over the whole window. Such output never recovers; aborting saves time and money."""
    tail = text[-window:]
    if len(tail) < window:
        return ""
    if not tail.strip():
        return f"{window} whitespace characters in a row"
    for n in range(1, 41):
        pat = tail[-n:]
        if pat.strip() and pat * (window // n) == tail[-(window // n) * n:]:
            return f"pattern {pat[:20]!r} repeated over {window} characters"
    return ""


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
            "max_tokens": int(cfg.get("max_tokens_override") or cfg.get("openrouter_max_tokens", 32000)),
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
    next_check = 4000  # degenerate-output check every 500 characters once the answer is long
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
                        if cchars >= next_check:
                            next_check = cchars + 500
                            why = degenerate_tail("".join(content)[-3000:])
                            if why:  # observed: a whitespace loop until max_tokens (4 minutes, answer lost)
                                raise TransientLLMError(f"degenerate output aborted after {cchars} chars: {why}")
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
    cjk = re.findall(r"[\u4e00-\u9fff]+", q)
    bigrams = [c[i:i + 2] for c in cjk for i in range(len(c) - 1)]
    # question words: Chinese (as \u escapes) and English
    stop = {"\u4ec0\u4e48", "\u5982\u4f55", "\u600e\u4e48", "\u4e3a\u4ec0", "\u54ea\u4e9b", "\u662f\u5426", "\u4e4b\u95f4", "\u533a\u522b", "\u5173\u7cfb", "the", "what", "how"}
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
    elif "[[LKB:ONTOLOGY]]" in system:
        text, note = _mock_ontology(user)
    elif "[[LKB:EXTRACT]]" in system:
        text, note = _mock_extract(user)
    elif "[[LKB:TOPICS]]" in system:
        text, note = _mock_topics(user)
    elif "[[LKB:INDEX]]" in system:
        text, note = _mock_index(user)
    elif "[[LKB:NAVIGATE]]" in system and "<tree>" in user:
        text, note = _mock_tree_navigate(user)
    elif "[[LKB:NAVIGATE]]" in system:
        text, note = _mock_navigate(user)
    elif "[[LKB:ANSWER]]" in system and "[[MOCK:PLACEHOLDER]]" in user and "# Correction" not in user:
        text, note = _fence({"answer_md": "...", "evidence": [], "used_cards": [], "gaps": ""}), "placeholder answer on purpose"
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
                sent = re.split(r"(?<=[.\u3002!?\uff01\uff1f])\s*", text.strip())[0]
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
        for n in re.findall(r"(\d+)\s*nm\s*(?:\u53ca\u4ee5\u4e0b|\u4ee5\u4e0b|and below|or below)", q):
            conds.append({"dim": "node", "value": f"{n}nm and below", "evidence": eid})
        for y in re.findall(r"((?:19|20)\d\d)\u5e74?", q):
            events.append({"when": y, "what": q[:60], "evidence": eid})
        for name, op, val, unit in re.findall(r"([A-Za-z]{2,6})\s*([<>≥≤]=?)\s*(\d+(?:\.\d+)?)\s*(nm|%)", q):
            facts.append({"name": name, "value": f"{op} {val}", "unit": unit, "evidence": eid})
    return _fence({"conditions": conds, "events": events, "facts": facts}), "regex facets from evidence"


def _mock_consolidate(user: str):
    """Drop the addendum headings (legacy Chinese form or "Addendum"), keep the evidence-marked paragraphs; split the second half off
    into one child card when the card is long."""
    m = re.search(r'<card id="([^"]+)">\ntitle: (.*?)\n.*?\n\n(.*)\n</card>', user, re.S)
    cid, title, body = m.group(1), m.group(2), m.group(3)
    paras = [p_.strip() for p_ in re.split(r"\n\s*\n", body) if p_.strip() and not re.match(r"#{1,6}\s*(?:\u8865\u5145|Addendum)", p_.strip())]
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
        nodes[nid] = (title + ": " + re.sub(r"[*`]", "", first))[:60]
    title = re.search(r'title="([^"]*)"', user)
    words = re.findall(r"\b([A-Z][a-z]+[A-Z][A-Za-z]+|[A-Z]{3,}[0-9]*)\b", body)
    ents = [{"name": w, "type": "tool", "aliases": [], "nodes": []} for w in dict.fromkeys(words)][:5]
    return _fence({"doc_summary": f"{title.group(1) if title else ''}: " + "; ".join(list(nodes.values())[:3])[:110],
                   "keywords": list(dict.fromkeys(_terms(title.group(1) if title else "")))[:6],
                   "nodes": nodes, "virtual_sections": [], "entities": ents}), "first line per section"


def _mock_ontology(user: str):
    """Ontology mock: two types and one relation, evidence = first non-empty line of the first sections."""
    secs = re.findall(r'<section handle="(E\d+)"[^>]*>\n(.*?)\n</section>', user, re.S)
    ev = []
    for h, body in secs[:2]:
        ln = next((x.strip() for x in body.splitlines() if len(x.strip()) > 8 and not x.startswith("#")), "")
        if ln:
            ev.append({"handle": h, "quote": ln[:100]})
    qs = re.findall(r"^(q\d+):", user, re.M)
    return _fence({"entity_types": [
        {"id": "method", "label": "Method", "definition": "A technique described in the documents.", "examples": [],
         "evidence": ev[:1], "questions": qs[:1]},
        {"id": "model", "label": "Model", "definition": "A physical or numerical model.", "examples": [],
         "evidence": ev[1:2] or ev[:1], "questions": qs[1:2]}],
        "entity_relations": [{"id": "depends_on_model", "label": "Depends on model", "domain": ["method"], "range": ["model"],
                              "definition": "The method needs the model.", "evidence": ev[:1], "questions": qs[:2]}],
        "uncovered": [], "notes": "mock"}), "two types from the first evidence lines"


def _mock_extract(user: str):
    """Extraction mock: instances = bold terms / title-case words that appear on numbered lines; one relation."""
    lines = re.findall(r"^\s*(\d+)\|(.*)$", user, re.M)
    types = re.findall(r"^- `([a-z_]+)` ", user, re.M)
    rels = re.findall(r"^- `([a-z_]+)`: ([a-z_|*]+) -> ([a-z_|*]+)", user, re.M)
    ents, seen = [], set()
    for n, ln in lines:
        for w in re.findall(r"\b([A-Z][A-Za-z]{2,}(?:[- ][A-Z][A-Za-z]+)*|[A-Z]{2,})\b", ln):
            if w not in seen and types:
                seen.add(w)
                ents.append({"name": w, "type": types[len(ents) % len(types)], "aliases": [],
                             "evidence": {"lines": n, "quote": ln.strip()[:120]}})
    out_rels = []
    if rels and len(ents) >= 2:
        rid, dom, rng = rels[0]
        a = next((e for e in ents if e["type"] in dom.split("|") or dom == "*"), None)
        b = next((e for e in ents if e is not a and (e["type"] in rng.split("|") or rng == "*")), None)
        if a and b:
            out_rels.append({"subject": a["name"], "predicate": rid, "object": b["name"],
                             "evidence": a["evidence"]})
    return _fence({"entities": ents[:12], "relations": out_rels}), "capitalised terms as instances"


def _mock_topics(user: str):
    """Topic mock: one topic per pair of documents, one subtopic per document; merge = identity."""
    if "# Partial leaves" in user:
        leaves = re.findall(r"^(p\d+-\S+) \| (.*?) - ", user, re.M)
        return _fence({"topics": [{"id": lid, "title": t, "summary": t, "subtopics": []} for lid, t in leaves],
                       "mapping": {lid: lid for lid, _ in leaves}}), "identity merge"
    docs: dict[str, list] = {}
    titles = {}
    for m in re.finditer(r'^(D(\d+)\.\S+) \| "([^"]*)"', user, re.M):
        docs.setdefault(m.group(2), []).append(m.group(1))
        titles[m.group(2)] = m.group(3)
    keys = sorted(docs, key=int)
    topics = []
    for i in range(0, len(keys), 2):
        pair = keys[i:i + 2]
        subs = [{"id": f"doc-{k}", "title": titles[k], "summary": titles[k], "sections": docs[k],
                 "representative": docs[k][:2]} for k in pair]
        topics.append({"id": f"theme-{i // 2 + 1}", "title": " / ".join(titles[k] for k in pair), "summary": "",
                       "subtopics": subs})
    if len(topics) == 1:
        topics.append({"id": "theme-extra", "title": "Misc", "summary": "", "sections": docs[keys[0]][:1],
                       "representative": docs[keys[0]][:1], "subtopics": []})
    return _fence({"topics": topics, "unassigned": [], "notes": "mock"}), "documents paired into themes"


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
    if "[[MOCK:LEAFEXPAND]]" in q:  # observed with real models: leaf sections listed under "expand"
        secs = [h for h in read if "/" in h]
        return _fence({"reasoning": "mock: leaf sections under expand", "read": [h for h in read if "/" not in h][:6],
                       "expand": secs[:4], "done": False}), "leaf sections under expand"
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
        parts.append(f"- [[{m.group(1)}]]: {m.group(3)}")
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
