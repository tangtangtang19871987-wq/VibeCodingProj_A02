"""LithoKB — a lightweight, file-native knowledge compiler for computational lithography.

Layer 0  sources/   : original Markdown, verbatim, versioned, with provenance.
Layer 1  compiled/  : LLM-compiled knowledge cards (Markdown + frontmatter), typed
                      relations (graph), topic hierarchy, evidence quotes that are
                      mechanically verified against the source lines they cite.
Governance          : per-revision review workflow, publish / withdraw / supersede.
Observability       : every LLM call is traced to disk (prompt, response, thinking
                      summary, usage, latency, validation, grounding).

Zero third-party dependencies. The Anthropic SDK is optional (only for the
`anthropic` LLM backend).
"""

__version__ = "0.1.0"
