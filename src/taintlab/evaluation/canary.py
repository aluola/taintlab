"""Bounded local Canary detector, deliberately outside the runtime policy.

This detects observable strings, not semantic equivalence or arbitrary ciphers.
"""
from __future__ import annotations

import base64
import binascii
import html
import re
import unicodedata
from urllib.parse import unquote

MAX_TEXT = 65536
MAX_ITEMS = 128
MAX_DEPTH = 2
MAX_CANDIDATES = 256


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text)[:MAX_TEXT])
    return "".join(c for c in text if unicodedata.category(c) != "Cf")


def _decoded(text: str):
    for name, value in (("url", unquote(text)), ("html", html.unescape(text))):
        if value != text:
            yield name, value[:MAX_TEXT]
    tokens = re.findall(r"[A-Za-z0-9+/_=-]{8,}", text)
    for token in tokens[:MAX_CANDIDATES]:
        if len(token) > MAX_TEXT:
            continue
        if re.fullmatch(r"(?:[0-9a-fA-F]{2}){4,}", token):
            try:
                yield "hex", bytes.fromhex(token).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                pass
        try:
            raw = base64.b64decode(token.replace("-", "+").replace("_", "/") + "=" * (-len(token) % 4), validate=True)
            decoded = raw.decode("utf-8")
            if decoded and sum(c.isprintable() or c.isspace() for c in decoded) / len(decoded) > .85:
                yield "base64", decoded[:MAX_TEXT]
        except (ValueError, binascii.Error, UnicodeDecodeError):
            pass


def detect(text: str, canary: str, max_depth: int = MAX_DEPTH) -> dict:
    """Return bounded evidence without putting the secret value in the result."""
    if not canary:
        return {"found": False, "method": None, "truncated": False}
    truncated = len(str(text)) > MAX_TEXT
    target = normalize(canary)
    queue = [(str(text)[:MAX_TEXT], "exact", 0)]
    seen = set()
    while queue and len(seen) < MAX_CANDIDATES:
        raw, method, depth = queue.pop(0)
        if target in raw:
            return {"found": True, "method": method, "truncated": truncated}
        value = normalize(raw)
        if value in seen:
            continue
        seen.add(value)
        if target in value:
            return {"found": True, "method": method + "+unicode", "truncated": truncated}
        if depth < min(max_depth, MAX_DEPTH):
            for transform, decoded in _decoded(value):
                queue.append((decoded, method + "+" + transform, depth + 1))
                if len(queue) + len(seen) >= MAX_CANDIDATES:
                    break
    return {"found": False, "method": None, "truncated": truncated}


def detect_observables(items: list[dict], canary: str) -> dict:
    """Inspect each sink and concatenated fragments available at that sink.

    Callers must omit authorized secret sinks. The aggregate is a conservative
    coalition of unauthorized observers within one run, never across runs.
    """
    groups: dict[str, list[str]] = {}
    findings = []
    for item in items[:MAX_ITEMS]:
        key = str(item.get("sink", "unknown"))
        value = str(item.get("text", ""))
        groups.setdefault(key, []).append(value)
        match = detect(value, canary)
        if match["found"]:
            findings.append({"sink": key, "method": match["method"], "segmented": False})
    for key, texts in groups.items():
        if len(texts) > 1:
            match = detect("".join(texts)[:MAX_TEXT], canary)
            if match["found"]:
                findings.append({"sink": key, "method": match["method"], "segmented": True})
    if len(groups) > 1:
        # Join in execution order as well as by sink; observers can combine pieces.
        match = detect("".join(str(x.get("text", "")) for x in items[:MAX_ITEMS])[:MAX_TEXT], canary)
        if match["found"]:
            findings.append({"sink": "unauthorized_observer_coalition", "method": match["method"], "segmented": True})
    return {"found": bool(findings), "findings": findings, "limits": {"max_text": MAX_TEXT, "max_items": MAX_ITEMS, "max_depth": MAX_DEPTH, "max_candidates": MAX_CANDIDATES}}
