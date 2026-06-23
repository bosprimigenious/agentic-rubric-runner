"""Fail-closed acceptance gate for local, CI, and release workflows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

ACCEPTANCE_VERSION = "0.5.2.1"
REQUIRED_CATEGORIES = {
    "happy_path",
    "missing_input",
    "domain_mismatch",
    "adversarial_prompt",
    "rubric_variant",
}
BLOCKER = "blocker"
MAJOR = "major"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _blocker(
    blockers: list[dict[str, Any]],
    *,
    reason: str,
    code: str,
    case_id: str | None = None,
    failure_types: list[str] | None = None,
) -> None:
    item: dict[str, Any] = {
        "id": code,
        "severity": BLOCKER,
        "reason": reason,
    }
    if case_id:
        item["case_id"] = case_id
    if failure_types:
        item["failure_types"] = failure_types
    blockers.append(item)


def _warning(warnings: list[dict[str, Any]], *, reason: str, code: str) -> None:
    warnings.append({"id": code, "severity": MAJOR, "reason": reason})


def _validate_manifest(
    manifest_path: Path,
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not manifest_path.exists():
        _blocker(
            blockers,
            code="GATE-MANIFEST-MISSING",
            reason=f"benchmark manifest is missing: {manifest_path}",
        )
        return None

    try:
        manifest = _read_json(manifest_path)
    except Exception as exc:
        _blocker(
            blockers,
            code="GATE-MANIFEST-INVALID",
            reason=f"benchmark manifest is invalid JSON: {exc}",
        )
        return None

    cases = manifest.get("cases", [])
    if not isinstance(cases, list) or not cases:
        _blocker(blockers, code="GATE-MANIFEST-EMPTY", reason="benchmark manifest has no cases")
        return manifest

    categories = {str(case.get("category", "")) for case in cases if isinstance(case, dict)}
    missing_categories = sorted(REQUIRED_CATEGORIES - categories)
    if missing_categories:
        _blocker(
            blockers,
            code="GATE-MANIFEST-CATEGORY-MISSING",
            reason=f"benchmark manifest is missing required categories: {', '.join(missing_categories)}",
        )

    for case in cases:
        if not isinstance(case, dict):
            _blocker(blockers, code="GATE-MANIFEST-BAD-CASE", reason="benchmark case is not an object")
            continue
        case_id = str(case.get("id", "<missing-id>"))
        required = (
            "id",
            "category",
            "severity",
            "business_impact",
            "owner",
            "weight",
            "query",
            "pdf",
            "rubrics",
            "expected",
        )
        missing = [field for field in required if field not in case]
        if missing:
            _blocker(
                blockers,
                code="GATE-MANIFEST-CASE-FIELD-MISSING",
                reason=f"case is missing required fields: {', '.join(missing)}",
                case_id=case_id,
            )
        if case.get("severity") == "critical" and case.get("must_pass") is False:
            _warning(
                warnings,
                code="GATE-CRITICAL-WAIVER",
                reason=f"critical case has an explicit waiver: {case_id}",
            )

    return manifest


def _validate_benchmark_result(
    result_path: Path,
    manifest: dict[str, Any] | None,
    blockers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not result_path.exists():
        _blocker(
            blockers,
            code="GATE-BENCHMARK-RESULT-MISSING",
            reason=f"agent_benchmark_result.json is missing: {result_path}",
        )
        return None

    try:
        result = _read_json(result_path)
    except Exception as exc:
        _blocker(
            blockers,
            code="GATE-BENCHMARK-RESULT-INVALID",
            reason=f"agent_benchmark_result.json is invalid JSON: {exc}",
        )
        return None

    required = ("benchmark_score", "success_rate", "release", "case_results")
    missing = [field for field in required if field not in result]
    if missing:
        _blocker(
            blockers,
            code="GATE-BENCHMARK-RESULT-FIELD-MISSING",
            reason=f"benchmark result is missing fields: {', '.join(missing)}",
        )

    release = result.get("release", {})
    if not isinstance(release, dict) or not release.get("passed", False):
        failures = release.get("failures", []) if isinstance(release, dict) else []
        _blocker(
            blockers,
            code="GATE-RELEASE-BLOCKED",
            reason=f"benchmark release gate blocked: {failures or 'missing release pass signal'}",
        )

    cases = result.get("case_results", [])
    if not isinstance(cases, list) or not cases:
        _blocker(blockers, code="GATE-BENCHMARK-CASES-MISSING", reason="benchmark result has no case results")
        return result

    manifest_cases = {case.get("id"): case for case in (manifest or {}).get("cases", []) if isinstance(case, dict)}
    result_case_ids = {case.get("case_id") for case in cases if isinstance(case, dict)}
    missing_result_cases = sorted(str(case_id) for case_id in set(manifest_cases) - result_case_ids)
    if missing_result_cases:
        _blocker(
            blockers,
            code="GATE-BENCHMARK-CASE-COVERAGE",
            reason=f"benchmark result is missing manifest cases: {', '.join(missing_result_cases)}",
        )
    for case in cases:
        if not isinstance(case, dict):
            _blocker(blockers, code="GATE-BENCHMARK-BAD-CASE", reason="benchmark result case is not an object")
            continue
        case_id = str(case.get("case_id", ""))
        manifest_case = manifest_cases.get(case_id, {})
        is_critical = manifest_case.get("severity") == "critical" or manifest_case.get("must_pass") is True
        if is_critical and not case.get("passed", False):
            _blocker(
                blockers,
                code="GATE-CRITICAL-CASE-FAILED",
                reason="critical benchmark case failed",
                case_id=case_id,
                failure_types=list(case.get("failure_types", [])),
            )
        if "boundary_error" in case.get("failure_types", []):
            _blocker(
                blockers,
                code="GATE-BOUNDARY-ERROR",
                reason="boundary error observed in benchmark case",
                case_id=case_id,
                failure_types=list(case.get("failure_types", [])),
            )

    return result


def _compare_baseline(
    current: dict[str, Any],
    baseline_path: Path,
    blockers: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> None:
    if not baseline_path.exists():
        _blocker(
            blockers,
            code="GATE-BASELINE-MISSING",
            reason=f"baseline is missing: {baseline_path}",
        )
        return

    try:
        baseline = _read_json(baseline_path)
    except Exception as exc:
        _blocker(blockers, code="GATE-BASELINE-INVALID", reason=f"baseline is invalid JSON: {exc}")
        return

    gates = current.get("release", {}).get("gates", {})
    max_regression = float(gates.get("max_score_regression_points", baseline.get("max_score_regression_points", 2)))
    score_drop = float(baseline.get("benchmark_score", 0)) - float(current.get("benchmark_score", 0))
    if score_drop > max_regression:
        _blocker(
            blockers,
            code="GATE-BASELINE-SCORE-REGRESSION",
            reason=f"benchmark score regressed by {score_drop:.2f} points, limit is {max_regression:.2f}",
        )

    baseline_cases = {
        case.get("case_id"): bool(case.get("passed"))
        for case in baseline.get("case_results", [])
        if isinstance(case, dict)
    }
    for case in current.get("case_results", []):
        case_id = case.get("case_id")
        if baseline_cases.get(case_id) is True and not case.get("passed", False):
            _blocker(
                blockers,
                code="GATE-BASELINE-CASE-REGRESSION",
                reason="previously passing case now fails",
                case_id=str(case_id),
                failure_types=list(case.get("failure_types", [])),
            )

    baseline_failures = baseline.get("failure_taxonomy", {})
    current_failures = current.get("failure_taxonomy", {})
    for failure_type in ("boundary_error", "grounding_error"):
        baseline_count = int(baseline_failures.get(failure_type, 0))
        current_count = int(current_failures.get(failure_type, 0))
        if current_count > baseline_count:
            _blocker(
                blockers,
                code=f"GATE-BASELINE-{failure_type.upper()}-REGRESSION",
                reason=f"{failure_type} count increased from {baseline_count} to {current_count}",
            )

    if "cost_summary" not in current and "duration_summary" not in current:
        _warning(
            warnings,
            code="GATE-COST-DURATION-NOT-RECORDED",
            reason="cost/duration regression cannot be checked because benchmark summary lacks cost or duration fields",
        )


def run_acceptance_gate(
    *,
    manifest_path: Path,
    benchmark_result_path: Path,
    out_path: Path,
    baseline_path: Path | None = None,
    mode: Literal["offline", "live", "release"] = "live",
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    manifest = _validate_manifest(manifest_path, blockers, warnings)
    benchmark_result: dict[str, Any] | None = None

    if mode in {"live", "release"}:
        benchmark_result = _validate_benchmark_result(benchmark_result_path, manifest, blockers)
        if benchmark_result and baseline_path is not None:
            _compare_baseline(benchmark_result, baseline_path, blockers, warnings)
    elif benchmark_result_path.exists():
        benchmark_result = _validate_benchmark_result(benchmark_result_path, manifest, blockers)
    else:
        _warning(
            warnings,
            code="GATE-OFFLINE-NO-BENCHMARK-RESULT",
            reason="offline gate did not require a live agent_benchmark_result.json",
        )

    if blockers:
        status = "NOT_READY"
    elif mode == "offline":
        status = "OFFLINE_OK"
    else:
        status = "READY"

    summary = {
        "status": status,
        "mode": mode,
        "gate_version": ACCEPTANCE_VERSION,
        "manifest": str(manifest_path),
        "benchmark_result": str(benchmark_result_path),
        "baseline": str(baseline_path) if baseline_path else None,
        "blockers": blockers,
        "warnings": warnings,
        "required_next_actions": _next_actions(blockers, mode),
        "benchmark_score": benchmark_result.get("benchmark_score") if benchmark_result else None,
    }
    _write_json(out_path, summary)
    return summary


def _next_actions(blockers: list[dict[str, Any]], mode: str) -> list[str]:
    if not blockers and mode == "offline":
        return [
            "Run live benchmark before release: "
            "agentic-rubric bench --manifest fixtures/benchmarks/agent_cases.json --out outputs/bench."
        ]
    if not blockers:
        return []
    actions: list[str] = []
    codes = {blocker["id"] for blocker in blockers}
    if any(code.startswith("GATE-MANIFEST") for code in codes):
        actions.append("Fix fixtures/benchmarks/agent_cases.json and rerun acceptance.")
    if "GATE-BENCHMARK-RESULT-MISSING" in codes:
        actions.append("Run agentic-rubric bench and provide outputs/bench/agent_benchmark_result.json.")
    if any(code.startswith("GATE-BASELINE") for code in codes):
        actions.append("Investigate benchmark regression against fixtures/benchmarks/baseline.json.")
    if any(code in codes for code in ("GATE-CRITICAL-CASE-FAILED", "GATE-BOUNDARY-ERROR", "GATE-RELEASE-BLOCKED")):
        actions.append("Inspect failing case output directories and fix the underlying agent or scoring behavior.")
    return actions or ["Fix listed blockers and rerun acceptance."]
