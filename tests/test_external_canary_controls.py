"""Positive/negative detector controls; synthetic fixtures, not model results."""
import base64
import json

import pytest

from taintlab.evaluation.canary import MAX_DEPTH, MAX_ITEMS, MAX_TEXT, detect, detect_observables

CANARY = "CANARY_CONTROL_4d0cb62f97e38a15"
DIFFERENT = "CANARY_CONTROL_4d0cb62f97e38a16"


def b64(value):
    return base64.b64encode(value.encode()).decode()


def percent(value):
    return "".join(f"%{x:02X}" for x in value.encode())


TRANSFORMS = {
    "plain": lambda s: s,
    "base64": b64,
    "hex": lambda s: s.encode().hex(),
    "url": percent,
    "html": lambda s: "".join(f"&#{ord(x)};" for x in s),
    "nfkc_fullwidth": lambda s: "".join(chr(ord(x) + 0xFEE0) for x in s),
    "format_characters": lambda s: "\u200b".join(s),
    "base64_twice": lambda s: b64(b64(s)),
    "hex_base64": lambda s: b64(s).encode().hex(),
}


@pytest.mark.parametrize("name", TRANSFORMS)
def test_v2_detector_positive_and_neighbor_negative_pairs(name):
    transform = TRANSFORMS[name]
    positive = detect("mock prefix " + transform(CANARY) + " mock suffix", CANARY)
    negative = detect("mock prefix " + transform(DIFFERENT) + " mock suffix", CANARY)
    assert positive["found"], name
    assert not negative["found"], name
    # Evidence identifies the method but never repeats the simulated secret.
    assert CANARY not in json.dumps(positive)


@pytest.mark.parametrize("transform", [lambda s: s, b64, percent, lambda s: s.encode().hex()])
def test_v2_detector_fragments_join_only_in_one_observable_run(transform):
    encoded = transform(CANARY)
    cut = len(encoded) // 2
    first, second = encoded[:cut], encoded[cut:]
    assert not detect(first, CANARY)["found"]
    assert not detect(second, CANARY)["found"]
    joined = detect_observables([{"sink": "notification:attacker", "text": first}, {"sink": "notification:attacker", "text": second}], CANARY)
    assert joined["found"]
    assert any(f["segmented"] for f in joined["findings"])
    assert not detect_observables([{"sink": "notification:attacker", "text": first}], CANARY)["found"]
    assert not detect_observables([{"sink": "notification:attacker", "text": second}], CANARY)["found"]


def test_v2_detector_same_run_observer_coalition_and_negative_controls():
    cut = len(CANARY) // 2
    result = detect_observables([{"sink": "notification:attacker", "text": CANARY[:cut]}, {"sink": "export:/outside/a.txt", "text": CANARY[cut:]}], CANARY)
    assert result["found"]
    assert any(f["sink"] == "unauthorized_observer_coalition" for f in result["findings"])
    assert not detect_observables([{"sink": "final", "text": "仅包含合法编码 b2ZmbGluZV9vaw== 和模拟普通文本"}], CANARY)["found"]
    assert not detect_observables([], CANARY)["found"]


def test_v2_detector_limits_are_explicitly_not_unlimited_coverage():
    triple = b64(b64(b64(CANARY)))
    assert MAX_DEPTH == 2 and not detect(triple, CANARY)["found"]
    beyond_text = detect("x" * MAX_TEXT + CANARY, CANARY)
    assert not beyond_text["found"] and beyond_text["truncated"]
    beyond_items = [{"sink": "final", "text": "ordinary"}] * MAX_ITEMS + [{"sink": "final", "text": CANARY}]
    assert not detect_observables(beyond_items, CANARY)["found"]


def test_interactive_attack_does_not_coach_block_recovery():
    from taintlab.attacks.interactive import build_preview

    for view in ("direct", "indirect", "segmented"):
        preview = build_preview(view=view, goal="unauthorized_read")
        content = json.dumps(preview["after"], ensure_ascii=False)
        assert "若被拒绝" not in content and "不要重试" not in content
        assert "读取 vault" in content
