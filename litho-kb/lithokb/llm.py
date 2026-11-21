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


def call(cfg: dict, system: str, user: str) -> LLMResult:
    backend = cfg.get("backend", "mock")
    t0 = time.time()
    if backend == "anthropic":
        r = _anthropic(cfg, system, user)
    elif backend == "openrouter":
        r = _openrouter(cfg, system, user)
    elif backend == "command":
        r = _command(cfg, system, user)
    elif backend == "mock":
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
        raise LLMError(f"rate limited: {e}") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError(f"connection error: {e}") from e
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
    """Any model on OpenRouter (OpenAI-compatible chat API), stdlib HTTP only.
    Key from $OPEN_ROUTER_API_KEY or $OPENROUTER_API_KEY. Reasoning text, when the model
    returns it, goes to the trace like Claude's thinking summary; OpenRouter's own
    usage accounting (tokens + cost) is recorded."""
    import urllib.error
    import urllib.request
    key = os.environ.get("OPEN_ROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise LLMError("backend 'openrouter' needs OPEN_ROUTER_API_KEY in the environment")
    model = cfg.get("openrouter_model") or "z-ai/glm-5.3-flash"
    body = {"model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": int(cfg.get("max_tokens", 64000)),
            "usage": {"include": True}}
    if cfg.get("json_mode", True):
        body["response_format"] = {"type": "json_object"}
    data = json.dumps(body).encode()
    last = None
    for attempt in range(4):
        req = urllib.request.Request(OPENROUTER_URL, data=data, method="POST",
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=int(cfg.get("timeout_s", 600))) as resp:
                out = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:800]
            last = f"HTTP {e.code}: {detail}"
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt * 2)
                continue
            raise LLMError(f"openrouter {last}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            last = str(e)
            if attempt < 3:
                time.sleep(2 ** attempt * 2)
                continue
            raise LLMError(f"openrouter connection error: {e}") from e
    if "error" in out:
        raise LLMError(f"openrouter error: {json.dumps(out['error'], ensure_ascii=False)[:800]}")
    choice = out["choices"][0]
    msg = choice.get("message", {})
    u = out.get("usage", {}) or {}
    usage = {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0)}
    if (u.get("completion_tokens_details") or {}).get("reasoning_tokens"):
        usage["reasoning_tokens"] = u["completion_tokens_details"]["reasoning_tokens"]
    if u.get("cost") is not None:
        usage["cost_usd_reported"] = u["cost"]
    finish = choice.get("finish_reason") or ""
    return LLMResult(text=msg.get("content") or "", model=out.get("model", model), backend="openrouter", usage=usage,
                     stop_reason={"length": "max_tokens", "stop": "end_turn"}.get(finish, finish),
                     thinking=msg.get("reasoning") or "", raw_meta={"id": out.get("id"), "provider": out.get("provider")})


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


def _terms(q: str) -> list[str]:
    """Question terms: ASCII words and Chinese character bigrams (no embeddings)."""
    words = [w.lower() for w in re.findall(r"[A-Za-z0-9]{2,}", q)]
    cjk = re.findall(r"[一-鿿]+", q)
    bigrams = [c[i:i + 2] for c in cjk for i in range(len(c) - 1)]
    stop = {"什么", "如何", "怎么", "为什", "哪些", "是否", "之间", "区别", "关系", "the", "what", "how"}
    return [t for t in dict.fromkeys(words + bigrams) if t not in stop]


def _mock(system: str, user: str) -> LLMResult:
    if "[[LKB:NAVIGATE]]" in system:
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
                      "title": f"文档摘要：{path}", "type": "summary", "parent": "", "aliases": [],
                      "summary": f"{path} 涵盖 {len(made)} 个知识点。",
                      "body_md": f"本文档以「{first[1].lstrip('# ').strip()}」开头 [E1]，包含：" +
                                 "".join(f"\n- [[{c['id']}]]" for c in made),
                      "relations": [{"rel": "covers", "target": c["id"], "basis": "extracted", "confidence": 1.0,
                                     "evidence": "E1"} for c in made],
                      "evidence": [{"id": "E1", "path": path, "lines": f"{first[0]}-{first[0]}", "quote": first[1].lstrip('# ').strip()}],
                      "confidence": 0.6, "change_note": f"mock summary of {path}"})
        notes.append(f"mock: {path}: {len(lines)} lines")
    return _fence({"cards": cards, "notes": "; ".join(notes)}), "headings→cards, first sentence→evidence"


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
                parts.append(f"- 原文：{mm.group(2).strip()[:200]} [{sid}]")
                break
    ans = ("根据知识库：\n" + "\n".join(parts)) if parts else "知识库中没有找到与该问题相关的内容。"
    return _fence({"answer_md": ans, "evidence": ev, "used_cards": used, "confidence": 0.4 if parts else 0.0,
                   "gaps": "" if parts else "无相关资料"}), "stitched summaries + matching lines"
