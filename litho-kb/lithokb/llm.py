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


# ---- mock: a transparent heuristic "compiler" ----------------------------------
_H_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")


def _mock(system: str, user: str) -> LLMResult:
    """Reads the numbered source block(s) in the prompt; one card per H1/H2 heading,
    the first sentence after it as evidence. Deterministic — good for tests."""
    cards, notes = [], []
    for m in re.finditer(r'<source path="([^"]+)"[^>]*>\n(.*?)\n</source>', user, re.S):
        path, block = m.group(1), m.group(2)
        lines = []
        for ln in block.splitlines():
            mm = re.match(r"\s*(\d+)\|(.*)$", ln)
            if mm:
                lines.append((int(mm.group(1)), mm.group(2)))
        doc_topic = None
        current = None
        for n, text in lines:
            h = _H_RE.match(text)
            if h and len(h.group(1)) <= 2:
                title = h.group(2).strip()
                ascii_ = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
                stem = re.sub(r"[^a-z0-9]+", "-", path.lower().rsplit(".", 1)[0]).strip("-")
                cid = f"{stem}-{ascii_ or ''}-{hashlib.md5(title.encode()).hexdigest()[:4]}".replace("--", "-")
                current = {"action": "create", "id": cid[:70].strip("-"), "title": title,
                           "type": "topic" if len(h.group(1)) == 1 else "concept",
                           "parent": doc_topic or "", "aliases": [], "summary": "", "body_md": "",
                           "relations": [], "evidence": [], "confidence": 0.5,
                           "change_note": f"mock compile of {path}"}
                if len(h.group(1)) == 1:
                    doc_topic = current["id"]
                cards.append(current)
                continue
            if current and text.strip() and not current["summary"] and not text.lstrip().startswith(("|", "```", "!", "-", "*", ">")):
                sent = re.split(r"(?<=[.。!?！？])\s*", text.strip())[0]
                current["summary"] = sent[:240]
                current["body_md"] = f"{sent}\n\n证据 [E1]。"
                current["evidence"].append({"id": "E1", "path": path, "lines": f"{n}-{n}", "quote": sent[:200]})
        notes.append(f"mock: {path}: {len(lines)} lines")
    for c in cards:
        if c["parent"] and c["parent"] != c["id"]:
            c["relations"].append({"rel": "subtopic_of", "target": c["parent"]})
    text = "```json\n" + json.dumps({"cards": cards, "notes": "; ".join(notes)}, ensure_ascii=False, indent=1) + "\n```"
    return LLMResult(text=text, model="mock-heuristic", backend="mock",
                     usage={"input_tokens_est": len(system + user) // 3, "output_tokens_est": len(text) // 3},
                     stop_reason="end_turn", thinking="(mock backend: no reasoning — headings→cards, first sentence→evidence)")
