"""Signal 3: semantic drift.

Uses dependency-free hashed character n-gram vectors so `promptlock check`
runs offline in CI with no embedding API. Swap `embed()` for a real embedding
model when you want cross-lingual / paraphrase sensitivity (see LIMITATIONS.md).
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter

DIM = 512
NGRAM = 4


def embed(text: str) -> list[float]:
    text = " ".join(text.lower().split())
    grams = [text[i:i + NGRAM] for i in range(max(1, len(text) - NGRAM + 1))]
    vec = [0.0] * DIM
    for g, n in Counter(grams).items():
        h = int(hashlib.md5(g.encode()).hexdigest()[:8], 16)
        vec[h % DIM] += math.log1p(n)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def distance(a: str, b: str) -> float:
    return 1.0 - cosine(embed(a), embed(b))


def self_distance(texts: list[str]) -> float:
    """Mean pairwise distance among a case's own k runs == its natural noise floor."""
    if len(texts) < 2:
        return 0.0
    ds = [
        distance(texts[i], texts[j])
        for i in range(len(texts))
        for j in range(i + 1, len(texts))
    ]
    return sum(ds) / len(ds)


def cross_distance(old: list[str], new: list[str]) -> float:
    """Mean distance between every baseline run and every new run."""
    if not old or not new:
        return 0.0
    ds = [distance(o, n) for o in old for n in new]
    return sum(ds) / len(ds)
