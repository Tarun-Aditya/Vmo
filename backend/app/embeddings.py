"""Embeddings: sentence-transformers when installed, else a deterministic hashed bag-of-words
(offline fallback, so seeding and demos work without model downloads)."""

from __future__ import annotations

import hashlib
import math
import re

from app.config import settings

DIM = settings.embedding_dim
_STOP = set(
    "the a an of to and or in on for by with is are be shall any this that its it as at "
    "from each other such".split()
)
# Tiny synonym groups so the offline embedder behaves a little semantically.
_GROUPS = [
    ("terminate", "termination", "cancel", "cancellation", "exit"),
    ("liability", "liable", "cap", "unlimited", "uncapped"),
    ("indemnify", "indemnity", "indemnification"),
    ("assign", "assignment", "transfer"),
    ("own", "owns", "owner", "ownership", "owned", "licence", "license"),
    ("breach", "incident", "violation"),
    ("govern", "governed", "governing", "law", "courts", "jurisdiction"),
    ("confidential", "confidentiality", "secret"),
    ("audit", "inspect", "inspection"),
    ("renew", "renews", "renewal", "automatically", "extension"),
    ("personal", "pii", "privacy"),
    ("pay", "payment", "invoice", "invoices"),
]
_CANON = {w: g[0] for g in _GROUPS for w in g}
_NUMS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "ten": "10"}
_CANON.update(_NUMS)
_model = None


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _hash_embed(text: str) -> list[float]:
    toks = [
        _CANON.get(_stem(t), _stem(t))
        for t in re.findall(r"[a-z0-9.]+", text.lower())
        if t not in _STOP
    ]
    feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
    vec = [0.0] * DIM
    for f in feats:
        h = int(hashlib.md5(f.encode()).hexdigest(), 16)
        w = (
            3.0 if re.search(r"\d", f) else 1.0
        )  # numbers (periods, caps, days) decide contract meaning
        vec[h % DIM] += w if (h >> 100) & 1 else -w
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def provider() -> str:
    global _model
    if settings.embedding_provider == "hash":
        return "hash"
    try:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(settings.embedding_model)
        return "local"
    except Exception:
        if settings.embedding_provider == "local":
            raise
        return "hash"


def embed(texts: list[str]) -> list[list[float]]:
    if provider() == "local":
        return [list(map(float, v)) for v in _model.encode(texts, normalize_embeddings=True)]
    return [_hash_embed(t) for t in texts]
