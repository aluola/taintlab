"""Read-only Git history/content audit. Reports never contain matched values.

This is a bounded pattern audit, not a proof that every possible secret is absent.
It does not commit, rewrite history, contact a remote, or write inside .git.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = {
    "github_token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{20,255}|github_pat_[A-Za-z0-9_]{30,255})\b",
    "provider_api_key": rb"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,255}|AIza[0-9A-Za-z_-]{30,60})\b",
    "aws_access_key": rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
    "slack_token": rb"\bxox[baprs]-[A-Za-z0-9-]{20,255}\b",
    "private_key_material": rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    "literal_auth_field": rb"(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|session[_-]?secret|password|authorization|cookie)[\"']?\s*[:=]\s*[\"']([^\"'\r\n]{8,512})[\"']",
    "jwt_token": rb"\beyJ[A-Za-z0-9_-]{12,1024}\.[A-Za-z0-9_-]{12,2048}\.[A-Za-z0-9_-]{12,1024}\b",
}
PRIVATE_ENVIRONMENT = re.compile(rb"(?i)\b[A-Z]:[\\/]+(?:Users|Desktop)[\\/][^\r\n\"<>]{1,240}")
CANARY = re.compile(rb"(?i)\b(?:SIM[_-])?CANARY[_-][A-Za-z0-9_-]{4,128}\b")
CONTACT = re.compile(rb"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")


def git(root: Path, *arguments: str) -> bytes:
    return subprocess.check_output(["git", *arguments], cwd=root, stderr=subprocess.PIPE)


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def simulated_value(value: bytes) -> bool:
    lower = value.lower()
    return bool(
        re.match(rb"(?:test|fake|dummy|mock|example|placeholder|synthetic)(?:[_ :<-]|$)", lower)
        or b"canary" in lower
        or re.fullmatch(rb"(?:bearer\s+)?(?:test|fake|dummy|example)[-_a-z0-9]*", lower)
        or re.fullmatch(rb"[<{].*[>}]", lower)
        or (len(set(value)) <= 3 and len(value) >= 16)
    )


def scan_content(content: bytes) -> dict[str, int]:
    """Return categories/counts only; neither snippets nor token hashes escape."""
    findings = Counter()
    for category, pattern in SECRET_PATTERNS.items():
        for match in re.finditer(pattern, content):
            value = match.group(1) if category == "literal_auth_field" else match.group(0)
            # Reviewed project constant naming an HTTP cookie, not its value.
            if category == "literal_auth_field" and re.match(rb"(?i)cookie[\"']?\s*[:=]", match.group(0)) and re.fullmatch(rb"taintlab_[a-z_]+", value):
                findings["nonsecret_cookie_name"] += 1
            elif simulated_value(value):
                findings["simulated_or_obvious_fixture:" + category] += 1
            else:
                findings["credential_candidate:" + category] += 1
    findings["simulated_canary"] += len(CANARY.findall(content))
    findings["private_environment_path"] += len(PRIVATE_ENVIRONMENT.findall(content))
    for match in CONTACT.finditer(content):
        domain = match.group(1).lower()
        if re.fullmatch(rb"page@[a-f0-9]+\.webm", match.group(0)):
            findings["noncontact_browser_recording_filename"] += 1
        elif domain.endswith((b".invalid", b".example", b".test")) or domain in {b"example.com", b"example.org", b"example.net"}:
            findings["simulated_contact"] += 1
        else:
            findings["contact_address_review"] += 1
    return {key: count for key, count in sorted(findings.items()) if count}


def path_categories(name: str) -> list[str]:
    path = Path(name.replace("\\", "/"))
    parts = [part.lower() for part in path.parts]
    result = []
    if any(part in {"web_private", ".git", "node_modules", "vendor", "models"} or part.startswith(".venv") for part in parts):
        result.append("private_or_runtime_dependency_path")
    if path.name.lower().startswith(".env") or path.name.lower() in {"credentials.json", "secrets.toml", "owners.json"}:
        result.append("credential_file_path")
    if path.suffix.lower() in {".sqlite", ".sqlite3", ".db", ".pid", ".log", ".webm", ".wav"} or "raw" in parts:
        result.append("runtime_or_intermediate_evidence_path")
    if any(part in {"reference", "references", "reference_source", "upstream_repo", "third_party", "third-party"} for part in parts):
        result.append("third_party_material_review")
    return result


def history_inventory(root: Path) -> tuple[list[str], dict[str, dict]]:
    commits = git(root, "rev-list", "--all").decode("ascii").splitlines()
    inventory = {}
    # Every tree is visited so renamed aliases of the same blob remain visible.
    for commit in commits:
        for entry in git(root, "ls-tree", "-r", "-l", "-z", commit).split(b"\0"):
            if not entry:
                continue
            metadata, raw_name = entry.split(b"\t", 1)
            mode, kind, oid, raw_size = metadata.split()
            if kind != b"blob":
                continue
            name = raw_name.decode("utf-8", "surrogateescape")
            item = inventory.setdefault(oid.decode("ascii"), {"bytes": int(raw_size), "paths": set()})
            item["paths"].add(name)
    return commits, inventory


def audit_history(root: Path) -> tuple[dict, dict]:
    commits, inventory = history_inventory(root)
    total_findings = Counter()
    paths_with_findings = {}
    detailed = []
    process = subprocess.Popen(["git", "cat-file", "--batch"], cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for oid, metadata in sorted(inventory.items()):
            process.stdin.write((oid + "\n").encode("ascii")); process.stdin.flush()
            header = process.stdout.readline().decode("ascii").split()
            if len(header) != 3 or header[1] != "blob":
                raise ValueError("Unexpected Git blob response")
            count = int(header[2]); content = process.stdout.read(count)
            if len(content) != count or process.stdout.read(1) != b"\n":
                raise ValueError("Truncated Git blob response")
            findings = scan_content(content)
            total_findings.update(findings)
            names = sorted(metadata["paths"])
            for name in names:
                path_flags = path_categories(name)
                if findings or path_flags:
                    paths_with_findings[name] = {"categories": sorted(set(findings) | set(path_flags))}
            detailed.append({"blob": oid, "bytes": count, "paths": names, "finding_counts": findings})
    finally:
        process.stdin.close(); process.wait(timeout=30)
        process.stdout.close(); process.stderr.close()
    credential_count = sum(count for key, count in total_findings.items() if key.startswith("credential_candidate:"))
    review_count = sum(count for key, count in total_findings.items() if key in {"private_environment_path", "contact_address_review"})
    path_risk = any(path_categories(name) for row in inventory.values() for name in row["paths"])
    public = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "All reachable refs and every commit tree; each unique blob scanned once as bytes. No history mutation, no remote access, no credential values in output.",
        "reachable_commits": len(commits), "unique_blobs": len(inventory),
        "unique_paths": len({p for row in inventory.values() for p in row["paths"]}),
        "unique_blob_bytes": sum(row["bytes"] for row in inventory.values()),
        "finding_counts": dict(sorted(total_findings.items())),
        "paths_requiring_review": paths_with_findings,
        "credential_candidates": credential_count,
        "verified_active_credentials": "not_tested_no_network_auth_attempts",
        "recommendation_reason": "Use a reviewed allowlist snapshot to avoid publishing historical private-environment diagnostics; local paths are not credentials." if review_count or path_risk else "No extra history isolation reason from the bounded scan; credential candidates still require review.",
        "recommendation": "independently_reviewed_snapshot" if credential_count or review_count or path_risk else "original_history_candidate_after_manual_review",
        "limitations": ["Pattern detection does not prove absence of every credential type or secrets hidden in compressed/media data.", "A credential candidate is not a verified active credential. Simulation and obvious fixture values are counted separately.", "Original Git history is preserved; this audit does not authorize pushing it."],
    }
    private = {"kind": "local_readonly_history_inventory", "commits": commits, "blobs": detailed, "public_summary": public}
    return public, private


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results/publication")
    args = parser.parse_args(argv)
    public, private = audit_history(args.root.resolve())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in (("history_audit_public.json", public), ("private_history_audit.json", private)):
        (args.output_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: public[key] for key in ("reachable_commits", "unique_blobs", "unique_paths", "unique_blob_bytes", "finding_counts", "credential_candidates", "recommendation")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
