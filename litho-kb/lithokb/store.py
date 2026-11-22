"""The knowledge base on disk. Plain files only — readable, greppable, git-able.

kbdata/
  config.json                 policy + LLM settings (human-edited)
  SCHEMA.md                   domain schema the compiler follows (versioned in history/schema/)
  users.json                  accounts and roles
  secret.key                  HMAC key for login tokens
  sources/<path>.md           Layer 0: original documents, verbatim (current version)
  meta/sources.json           provenance: uploader, time, sha256, version history
  history/sources/<path>@<n>  every superseded source version, kept forever
  compiled/cards/<id>.md      Layer 1: head revision of each knowledge card
  compiled/revisions/<id>/rNNNN.md   immutable revision snapshots
  compiled/index.md, graph.json      generated, for humans and agents
  reviews/<id>.jsonl          append-only review records
  traces/<run>/...            every LLM call: prompt, response, usage, validation
  log/events.jsonl            append-only audit log of every action
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import secrets
import tempfile
import threading

try:
    import fcntl
except ImportError:  # pragma: no cover (non-POSIX)
    fcntl = None
from pathlib import Path

class _WriterLock:
    """Writer lock for every mutation: a re-entrant thread lock *plus* an OS file lock
    (fcntl.flock on <root>/.lock) for each knowledge base opened in this process, so the
    web server, CLI runs and the MCP server can safely write the same knowledge base
    concurrently. Readers never lock: all writes are atomic renames."""

    def __init__(self):
        self._rl = threading.RLock()
        self._depth = 0
        self._roots: set[Path] = set()
        self._fds: list[int] = []

    def register(self, root: Path) -> None:
        with self._rl:
            self._roots.add(root)

    def __enter__(self):
        self._rl.acquire()
        self._depth += 1
        if self._depth == 1 and fcntl is not None:
            for r in sorted(self._roots):
                if r.exists():
                    try:
                        fd = os.open(r / ".lock", os.O_CREAT | os.O_RDWR, 0o644)
                    except OSError:
                        continue
                    fcntl.flock(fd, fcntl.LOCK_EX)
                    self._fds.append(fd)
        return self

    def __exit__(self, *exc):
        self._depth -= 1
        if self._depth == 0:
            for fd in reversed(self._fds):
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
            self._fds = []
        self._rl.release()
        return False


LOCK = _WriterLock()

DEFAULT_CONFIG = {
    "site_name": "LithoKB · Computational Lithography Knowledge Base",
    "public_read": True,  # anonymous visitors may read published knowledge + sources
    "review": {
        "required_approvals": 1,
        "allow_self_approval": False,
    },
    "llm": {
        "backend": "mock",  # mock | anthropic | openrouter | command
        "model": "claude-opus-5-5",
        "effort": "high",
        "max_tokens": 64000,
        "openrouter_model": "z-ai/glm-5.3-flash",  # for backend=openrouter
        "openrouter_reasoning": "low",  # none | low | medium | high — bounds hidden reasoning time/cost
        "reasoning_by_stage": {"compile": "low", "navigate": "low", "answer": "low"},  # per-stage override
        "reasoning_watchdog_chars": 20000,  # abort + retry one level lower if reasoning exceeds this with no output
        "openrouter_max_tokens": 32000,
        "command": "",  # for backend=command: prompt on stdin, response on stdout
        "price_per_mtok": {"claude-opus-5-5": [4.0, 20.0], "z-ai/glm-5.3-flash": [0.0399, 0.0784]},
    },
    "compile": {
        "files_per_call": 1,
        "max_doc_chars": 300_000,  # larger documents are compiled section-by-section along their outline
        "max_attempts": 2,  # one corrective retry when the model returns unusable JSON
    },
    "query": {"min_role": "reader", "unpublished_for_reviewers": True},
}


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())  # durable before it becomes visible
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with LOCK, open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text("utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


class KB:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()
        self.sources = self.root / "sources"
        self.meta = self.root / "meta"
        self.history = self.root / "history" / "sources"
        self.cards_dir = self.root / "compiled" / "cards"
        self.revs_dir = self.root / "compiled" / "revisions"
        self.reviews_dir = self.root / "reviews"
        self.traces_dir = self.root / "traces"
        self.events_path = self.root / "log" / "events.jsonl"
        self._cfg = None
        self._cfg_mtime = None
        LOCK.register(self.root)

    # ---- lifecycle -------------------------------------------------------
    def init(self) -> None:
        for d in (self.sources, self.meta, self.history, self.cards_dir, self.revs_dir,
                  self.reviews_dir, self.traces_dir, self.events_path.parent):
            d.mkdir(parents=True, exist_ok=True)
        cfg = self.root / "config.json"
        if not cfg.exists():
            atomic_write(cfg, json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2))
        key = self.root / "secret.key"
        if not key.exists():
            atomic_write(key, secrets.token_hex(32))
            os.chmod(key, 0o600)
        if not (self.root / "users.json").exists():
            atomic_write(self.root / "users.json", "{}")
        from . import schema
        schema.ensure(self)

    def exists(self) -> bool:
        return (self.root / "config.json").exists()

    @property
    def config(self) -> dict:
        p = self.root / "config.json"
        m = p.stat().st_mtime if p.exists() else None
        if self._cfg is None or m != self._cfg_mtime:
            raw = json.loads(p.read_text("utf-8")) if p.exists() else {}
            self._cfg, self._cfg_mtime = _merge(DEFAULT_CONFIG, raw), m
        return self._cfg

    def secret(self) -> bytes:
        return (self.root / "secret.key").read_text().strip().encode()

    # ---- audit log -------------------------------------------------------
    def event(self, actor: str, action: str, target: str = "", **detail) -> dict:
        ev = {"ts": now(), "actor": actor, "action": action, "target": target}
        if detail:
            ev["detail"] = detail
        append_jsonl(self.events_path, ev)
        return ev

    def events(self, limit: int = 500, target: str | None = None) -> list[dict]:
        evs = read_jsonl(self.events_path)
        if target:
            evs = [e for e in evs if e.get("target") == target]
        return evs[-limit:][::-1]
