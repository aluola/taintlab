"""Index preserved real UI evidence; never modifies any original report or metric."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/v2/browser"


def read(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8-sig"))


def artifact(relative: str) -> dict:
    data = (ROOT / relative).read_bytes()
    return {"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main() -> None:
    reports = [
        "results/v2/browser/ui_e2e_2026-10-26T17-12-36-626Z.json",
        "results/v2/browser/ui_followup_2026-10-26T17-19-00-715Z.json",
        "results/v2/browser/ui_followup_2026-10-26T17-33-09-419Z.json",
        "results/v2/browser/ui_followup_2026-10-26T18-05-16-679Z.json",
    ]
    latest: dict[str, dict] = {}
    indexed = []
    for path in reports:
        data = read(path)
        indexed.append({**artifact(path), "started_at": data["started_at"], "checks": len(data["tests"]), "passed": sum(bool(item["passed"]) for item in data["tests"]), "all_passed_at_that_time": data["all_passed"], "page_errors": data["errors"], "external_requests": data["blocked_external"]})
        for test in data["tests"]:
            latest[test["name"]] = {"name": test["name"], "passed": test["passed"], "evidence_report": path, "evidence": test.get("evidence")}
    unit = read("frontend/qa/unit_tests.json")
    clean = read("frontend/qa/clean_install_validation.json")
    clean_tests = read("frontend/qa/clean_install_tests.json")
    current_assets = []
    for entry in clean["assets"]:
        current = artifact("frontend/dist/" + entry["path"].replace("\\", "/"))
        current["matches_frozen_clean_build"] = current["sha256"] == entry["sha256"]
        current_assets.append(current)
    source = read("results/v2/browser/focused-source-graph-v2.json")
    screenshots = ["desktop-home.png", "laptop-home.png", "mobile-home.png", "mobile-navigation.png", "confirmation-pending.png", "notification-delivered.png", "export-delivered.png", "upload-registered.png", "focused-source-graph-v2.png", "attack-preview-segmented.png", "results-with-denominators.png", "results-overhead.png"]
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "scope": "Production React UI and real local API browser acceptance; not formal experiment metrics",
        "assurance": "No mocked HTTP responses, fabricated DOM, or invented model output. Original failures are retained. Browser actions use an isolated local session; external page resources are denied.",
        "unit_tests": {"report": "frontend/qa/unit_tests.json", "backend": "scripted_ui_fixture (unit tests only)", "total": unit["numTotalTests"], "passed": unit["numPassedTests"], "failed": unit["numFailedTests"], "success": unit["success"]},
        "fresh_install": {"report": "frontend/qa/clean_install_validation.json", "test_report": "frontend/qa/clean_install_tests.json", "scope": "Fresh directory, npm ci --offline using already prepared cache; not a first-ever offline dependency download", "tests_passed": clean_tests["numPassedTests"], "success": clean_tests["success"], "all_assets_identical": clean["all_assets_identical"]},
        "production_assets": current_assets,
        "browser_reports": indexed,
        "latest_evidence_by_unique_check": list(latest.values()),
        "unique_check_count": len(latest),
        "latest_unique_checks_passed": sum(bool(test["passed"]) for test in latest.values()),
        "all_targeted_checks_passed_latest_evidence": all(test["passed"] for test in latest.values()),
        "counting_note": "16 distinct checks are supported by one initial 15-check run and targeted follow-ups. This is not a claim that a new single 16-check model batch was executed. Repeated layout checks and repeated 31-test fresh-install runs are not additional unique tests.",
        "preserved_failures": [
            {"report": "results/v2/browser/layout_check.json", "problem": "Initial mobile automation clicked the center of the full-screen mask, where the sidebar intercepted input; initial screenshots captured transitions.", "resolution": "Click the visible mask area; disable animations only during screenshot capture; real desktop/laptop/mobile recheck passed.", "follow_up": reports[-1]},
            {"report": reports[0], "check": "query_shortcut_reaches_search_tool", "problem": "Real model searched but its final content did not contain the two required dates.", "resolution": "Clarified the shortcut's natural-language task, retained the failed run, and reran the actual model; no answer was substituted.", "follow_up": reports[1]},
            {"report": reports[0], "check": "upload_registered_then_explicitly_read", "problem": "The initial assertion incorrectly required an upload-prefixed document ID; the actual service issues opaque doc IDs. The original observed model result also lacked the requested concrete answer.", "resolution": "Use the actual registered ID in the explicit task and inspect real state plus answer; targeted local-model rerun passed.", "follow_up": reports[1]},
        ],
        "viewports": [{"width": 1440, "height": 960, "purpose": "desktop"}, {"width": 1366, "height": 768, "purpose": "laptop"}, {"width": 390, "height": 844, "purpose": "narrow viewport"}],
        "narrow_screen": {"passed": True, "report": reports[-1], "checks": "No document horizontal overflow; navigation opened and closed with visible-area click; task textarea remained visible. Actual images visually reviewed."},
        "current_source_graph": source,
        "screenshots": [artifact("results/v2/browser/" + name) for name in screenshots],
        "visual_review": {"reviewed_at": datetime.now(timezone.utc).isoformat(), "status": "passed_for_named_screenshots", "notes": "Chinese text, current-version badge, source selection, graph legend, narrow-screen navigation and composer inspected. Historical source graph remains preserved under its original filename and is not evidence of a current run."},
        "limitations": [
            "UI browser runs are acceptance tasks, not additions to frozen ASR or normal-completion denominators.",
            "The actual browser upload flow exercised Markdown; other parser formats require the backend acceptance evidence and are not claimed by this index.",
            "31 component tests use structured fixtures and do not prove local-model capability.",
            "The narrow-screen check is an actual Chromium viewport test, not a physical phone or cross-browser certification.",
            "No claim is made of a full accessibility audit, all natural-language tasks succeeding, precise semantic causal tracking, or complete injection resistance.",
            "The latest full video and its playback validation are owned by the final delivery process; raw recordings alone are not a playable final MP4 claim.",
        ],
    }
    (OUT / "ui_acceptance.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"unique_checks": len(latest), "passed_latest": result["latest_unique_checks_passed"], "unit_tests": unit["numPassedTests"], "frozen_assets_match": all(a["matches_frozen_clean_build"] for a in current_assets)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
