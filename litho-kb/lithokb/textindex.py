"""Lexical retrieval without vectors: an in-memory BM25 inverted index.

* Tokens: lower-cased ASCII words / numbers (with `.`/`-` kept inside, so "13.5nm",
  "high-na", "193i" survive), overlapping CJK bigrams (single-character runs as unigrams) —
  the standard dictionary-free way to index Chinese. Queries need no spaces.
* Fields are weighted (title/aliases ≫ summary ≫ body) by repeating their tokens.
* Incremental: documents are (re)indexed by key + version signature; an unchanged
  document is never re-tokenised. Everything is derived and rebuilt on demand —
  the files stay the only source of truth (no database).

Used for: card search (UI / CLI / MCP), lexical seeds for tree-search navigation,
and section search inside source documents (author-defined sections — not chunks).
"""
from __future__ import annotations

import math
import re
import threading
from collections import Counter, defaultdict

_ASCII = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
# stop words: common Chinese function words (as \u escapes) and English ones
_STOP = {"\u7684", "\u4e86", "\u548c", "\u662f", "\u5728", "\u4e0e", "\u53ca", "\u6216", "\u7b49", "\u4e2d", "\u5bf9", "\u4e3a", "\u7531", "\u5176", "the", "a", "an", "of",
         "and", "or", "to", "in", "for", "is", "are", "on", "with", "by", "what", "how", "why", "\u4ec0\u4e48", "\u5982\u4f55",
         "\u600e\u4e48", "\u54ea\u4e9b", "\u4e3a\u4ec0\u4e48"}


def tokens(text: str) -> list[str]:
    s = (text or "").lower()
    out = [t for t in _ASCII.findall(s) if t not in _STOP]
    for run in _CJK.findall(s):
        if len(run) == 1:
            if run not in _STOP:
                out.append(run)
        else:  # overlapping bigrams (dictionary-free Chinese indexing); stop-bigrams dropped
            out.extend(b for b in (run[i:i + 2] for i in range(len(run) - 1)) if b not in _STOP)
    return out


class BM25:
    K1, B = 1.2, 0.75

    def __init__(self):
        self._lock = threading.RLock()
        self.docs: dict[str, tuple] = {}          # key → (sig, length, Counter, payload)
        self.post: dict[str, dict[str, int]] = defaultdict(dict)  # term → {key: tf}
        self.total_len = 0

    def __len__(self):
        return len(self.docs)

    def _drop(self, key: str):
        old = self.docs.pop(key, None)
        if old:
            self.total_len -= old[1]
            for t in old[2]:
                p = self.post.get(t)
                if p is not None:
                    p.pop(key, None)
                    if not p:
                        del self.post[t]

    def put(self, key: str, sig, fields: list[tuple[str, int]], payload=None) -> bool:
        """Index `fields` [(text, weight)] under `key`; no-op when `sig` is unchanged. Returns True if (re)indexed."""
        with self._lock:
            cur = self.docs.get(key)
            if cur and cur[0] == sig:
                if payload is not None:
                    self.docs[key] = (cur[0], cur[1], cur[2], payload)
                return False
            self._drop(key)
            tf: Counter = Counter()
            for text, w in fields:
                for t in tokens(text):
                    tf[t] += w
            n = sum(tf.values())
            self.docs[key] = (sig, n, tf, payload)
            self.total_len += n
            for t, c in tf.items():
                self.post[t][key] = c
            return True

    def sync(self, keys) -> None:
        """Remove every document not in `keys`."""
        with self._lock:
            for k in [k for k in self.docs if k not in keys]:
                self._drop(k)

    def search(self, query: str, limit: int = 20, allow=None) -> list[tuple[float, str]]:
        """Top documents by BM25. `allow(key, payload) -> bool` filters (permissions, scope)."""
        q = Counter(tokens(query))
        if not q:
            return []
        with self._lock:
            N = len(self.docs) or 1
            avg = (self.total_len / N) or 1.0
            scores: dict[str, float] = defaultdict(float)
            matched: dict[str, int] = defaultdict(int)
            for t, qn in q.items():
                p = self.post.get(t)
                if not p:
                    continue
                idf = math.log(1 + (N - len(p) + 0.5) / (len(p) + 0.5))
                for key, tf in p.items():
                    dl = self.docs[key][1]
                    scores[key] += qn * idf * tf * (self.K1 + 1) / (tf + self.K1 * (1 - self.B + self.B * dl / avg))
                    matched[key] += 1
            out = []
            for key, sc in scores.items():  # coordination: reward documents matching more distinct terms
                if allow is None or allow(key, self.docs[key][3]):
                    cov = matched[key] / len(q)
                    out.append((round(sc * (0.5 + cov), 4), key))
            out.sort(key=lambda x: -x[0])
            return out[:limit]

    def payload(self, key: str):
        d = self.docs.get(key)
        return d[3] if d else None
