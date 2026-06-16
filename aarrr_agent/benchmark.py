"""Agent benchmark runner and deterministic run-level evaluation."""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

from aarrr_agent.errors import PipelineError
from aarrr_agent.grader import load_rubrics
from aarrr_agent.pipeline import OutputPaths, resolve_output_paths, run_pipeline
from aarrr_agent.schemas import GradingResult
from aarrr_agent.validation import validate_report_content

DEFAULT_AGENT_WEIGHTS = {
    "phase1_execution": 20.0,
    "phase2_grading": 15.0,
    "task_success": 20.0,
    "groundedness": 20.0,
    "robustness": 10.0,
    "efficiency": 5.0,
    "safety_boundary": 10.0,
}

WRITE_TOOLS = {"write_pdf_report", "write_structured_report"}
EXPECTED_TOOL_PREFIX = ["read_text", "read_pdf", "extract_evidence_pack"]
EVIDENCE_REF_RE = re.compile(r"\[E(\d{2})\]")
ARTIFACT_PATHS = {
    "phase1_output.md": "phase1_md",
    "phase1_output.html": "phase1_html",
    "phase1_output.pdf": "phase1_pdf",
    "evidence_pack.json": "evidence_pack",
    "grading_result.json": "grading_json",
    "grading_report.md": "grading_report_md",
    "grading_report.html": "grading_report_html",
    "agent_trace.jsonl": "trace_jsonl",
    "run_meta.json": "run_meta",
}
INPUT_ERROR_CODES = {
    "query": "E005",
    "pdf": "E002",
    "rubrics": "E005",
}
CALIBRATION_SIGNAL_TOKENS = ("程序门控", "校准", "保守", "压低", "重算")


@dataclass
class CaseRunResult:
    """Internal result for one benchmark case."""

    case_id: str
    category: str
    status: str
    passed: bool
    output_dir: str
    agent_eval: dict[str, Any]
    error_code: str | None = None
    error_message: str | None = None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_trace(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def _safe_file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _score_item(ok: bool, points: float, issues: list[str], issue: str) -> float:
    if ok:
        return points
    issues.append(issue)
    return 0.0


def _trace_tool_sequence(trace: list[dict[str, Any]]) -> list[str]:
    return [str(entry.get("tool", "")) for entry in trace]


def _valid_phase1_sequence(tools: list[str]) -> bool:
    if len(tools) < 4:
        return False
    if tools[:3] != EXPECTED_TOOL_PREFIX:
        return False
    if tools[-1] not in WRITE_TOOLS:
        return False
    middle = tools[3:-1]
    return all(tool == "self_check_report" for tool in middle)


def _load_evidence_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = _read_json(path)
    except Exception:
        return set()
    facts = data.get("facts", [])
    return {
        str(fact.get("id"))
        for fact in facts
        if isinstance(fact, dict) and fact.get("id")
    }


def _extract_report_refs(report_text: str) -> set[str]:
    return {f"E{match}" for match in EVIDENCE_REF_RE.findall(report_text)}


def _artifact_status(paths: OutputPaths) -> dict[str, bool]:
    return {
        "markdown": paths.phase1_md.exists() and _safe_file_size(paths.phase1_md) > 0,
        "html": paths.phase1_html.exists() and _safe_file_size(paths.phase1_html) > 0,
        "pdf": paths.phase1_pdf.exists() and _safe_file_size(paths.phase1_pdf) > 0,
        "evidence_pack": paths.evidence_pack.exists() and _safe_file_size(paths.evidence_pack) > 0,
        "trace": paths.trace_jsonl.exists() and _safe_file_size(paths.trace_jsonl) > 0,
        "run_meta": paths.run_meta.exists() and _safe_file_size(paths.run_meta) > 0,
        "grading": paths.grading_json.exists() and _safe_file_size(paths.grading_json) > 0,
    }


def _missing_required_artifacts(paths: OutputPaths, expected: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for artifact in expected.get("required_artifacts", []):
        attr = ARTIFACT_PATHS.get(str(artifact))
        path = getattr(paths, attr, paths.directory / str(artifact)) if attr else paths.directory / str(artifact)
        if not path.exists() or _safe_file_size(path) <= 0:
            missing.append(str(artifact))
    return missing


def _load_grading_result(paths: OutputPaths) -> GradingResult | None:
    if not paths.grading_json.exists():
        return None
    try:
        return GradingResult(**_read_json(paths.grading_json))
    except Exception:
        return None


def _phase1_score(paths: OutputPaths, trace: list[dict[str, Any]]) -> tuple[float, dict[str, Any]]:
    issues: list[str] = []
    tools = _trace_tool_sequence(trace)
    artifacts = _artifact_status(paths)
    report_text = paths.phase1_md.read_text(encoding="utf-8") if paths.phase1_md.exists() else ""
    structured_json = paths.phase1_pdf.with_suffix(".structured.json")
    validation_issues = validate_report_content(report_text) if report_text else ["missing markdown"]

    score = 0.0
    score += _score_item(_valid_phase1_sequence(tools), 4, issues, "invalid phase1 tool sequence")
    score += _score_item(
        not any(entry.get("status") == "error" and "不允许" in str(entry.get("error", "")) for entry in trace),
        3,
        issues,
        "phase1 boundary violation",
    )
    score += _score_item(artifacts["evidence_pack"] and bool(_load_evidence_ids(paths.evidence_pack)), 3, issues, "missing or empty evidence pack")
    score += _score_item(artifacts["markdown"] and artifacts["html"] and artifacts["pdf"], 4, issues, "missing phase1 artifacts")
    score += _score_item(structured_json.exists() or not validation_issues, 3, issues, "invalid or incomplete report structure")
    score += _score_item(bool(tools and tools[-1] in WRITE_TOOLS), 3, issues, "missing terminal write tool")

    return score, {
        "score": round(score, 2),
        "max_score": 20.0,
        "issues": issues,
        "tools": tools,
        "artifacts": artifacts,
        "report_validation_issues": validation_issues,
    }


def _phase2_score(paths: OutputPaths, rubrics_path: Path | None, result: GradingResult | None) -> tuple[float, dict[str, Any]]:
    issues: list[str] = []
    score = 0.0

    rubrics: dict[str, Any] | None = None
    if rubrics_path and rubrics_path.exists():
        try:
            rubrics = load_rubrics(str(rubrics_path))
        except Exception as exc:
            issues.append(f"invalid rubrics: {exc}")

    if result is None:
        return 0.0, {"score": 0.0, "max_score": 15.0, "issues": ["missing or invalid grading result"]}

    if rubrics:
        rubric = rubrics.get("rubric", {})
        coverage_ok = (
            len(result.hard_constraints) == len(rubric.get("hard_constraints", []))
            and len(result.soft_constraints) == len(rubric.get("soft_constraints", []))
            and len(result.optional_constraints) == len(rubric.get("optional_constraints", []))
        )
    else:
        coverage_ok = bool(result.hard_constraints or result.soft_constraints or result.optional_constraints)

    score += _score_item(coverage_ok, 3, issues, "rubric coverage mismatch")
    score += _score_item(True, 3, issues, "invalid grading schema")

    bd = result.score_breakdown
    computed = 0.0
    if bd.hard_max:
        computed += bd.hard_score / bd.hard_max * 50
    if bd.soft_max:
        computed += bd.soft_score / bd.soft_max * 30
    if bd.optional_max:
        computed += bd.optional_score / bd.optional_max * 20
    score += _score_item(abs(round(computed, 2) - bd.final_score) <= 0.01, 3, issues, "final score was not programmatically consistent")

    needs_reference_ok = True
    if rubrics:
        rubric = rubrics["rubric"]
        for group_name, constraints in (
            ("hard_constraints", result.hard_constraints),
            ("soft_constraints", result.soft_constraints),
            ("optional_constraints", result.optional_constraints),
        ):
            specs = rubric.get(group_name, [])
            for idx, item in enumerate(constraints):
                spec = specs[idx] if idx < len(specs) else {}
                if spec.get("needs_reference") == "是" and item.score:
                    text = f"{item.reason} {' '.join(item.evidence)}"
                    if not item.evidence and "来源" not in text and "[E" not in text:
                        needs_reference_ok = False
    score += _score_item(needs_reference_ok, 3, issues, "source-dependent scoring lacks evidence")

    score += _score_item(_has_calibration_or_gate_signal(result), 3, issues, "calibration/gating signal missing")

    return score, {"score": round(score, 2), "max_score": 15.0, "issues": issues}


def _has_calibration_or_gate_signal(result: GradingResult) -> bool:
    items = [*result.hard_constraints, *result.soft_constraints, *result.optional_constraints]
    texts = [getattr(result, "overall_comment", "") or ""]
    texts.extend(f"{item.reason} {' '.join(getattr(item, 'missing', []))}" for item in items)
    return any(token in text for token in CALIBRATION_SIGNAL_TOKENS for text in texts)


def _task_success_score(paths: OutputPaths, result: GradingResult | None, expected: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    issues: list[str] = []
    artifacts = _artifact_status(paths)
    score = 0.0

    score += _score_item(artifacts["markdown"] and artifacts["pdf"] and (result is not None), 6, issues, "full pipeline did not complete")
    score += _score_item(artifacts["pdf"] and artifacts["markdown"] and artifacts["html"], 3, issues, "output format requirements not met")

    if result is not None:
        hard_rate = result.score_breakdown.hard_score / result.score_breakdown.hard_max if result.score_breakdown.hard_max else 0
        min_hard_rate = float(expected.get("min_hard_rate", 0.6))
        hard_ok = hard_rate >= min_hard_rate
    else:
        hard_ok = False
    score += _score_item(hard_ok, 5, issues, "hard constraints below threshold")
    score += _score_item(artifacts["run_meta"], 3, issues, "missing run metadata for reproducibility")
    score += _score_item(True, 3, issues, "missing stable failure signal")

    return score, {"score": round(score, 2), "max_score": 20.0, "issues": issues, "artifacts": artifacts}


def _groundedness_score(paths: OutputPaths, result: GradingResult | None) -> tuple[float, dict[str, Any]]:
    issues: list[str] = []
    score = 0.0
    report_text = paths.phase1_md.read_text(encoding="utf-8") if paths.phase1_md.exists() else ""
    evidence_ids = _load_evidence_ids(paths.evidence_pack)
    refs = _extract_report_refs(report_text)
    unknown_refs = sorted(refs - evidence_ids)

    score += _score_item(bool(refs) and not unknown_refs, 4, issues, "unknown or missing evidence references")
    score += _score_item(any(token in report_text for token in ("北极星", "目标", "获客", "留存")) and bool(refs), 4, issues, "key claims lack citations")
    score += _score_item(bool(refs & evidence_ids), 5, issues, "citations do not map to evidence pack")
    hallucination_markers = ("行业平均", "公开 benchmark", "根据外部", "据统计")
    score += _score_item(not any(marker in report_text for marker in hallucination_markers), 4, issues, "possible unsupported external facts")
    if result is not None:
        gated = any("程序门控" in item.reason for item in [*result.hard_constraints, *result.soft_constraints, *result.optional_constraints])
        low_score = result.score_breakdown.final_score <= 20
        off_domain_ok = gated or not low_score
    else:
        off_domain_ok = True
    score += _score_item(off_domain_ok, 3, issues, "off-domain material was not downgraded")

    return score, {
        "score": round(score, 2),
        "max_score": 20.0,
        "issues": issues,
        "evidence_refs": sorted(refs),
        "unknown_evidence_refs": unknown_refs,
        "evidence_count": len(evidence_ids),
    }


def _robustness_score(category: str, expected: dict[str, Any], result: GradingResult | None, failure_type: str | None) -> tuple[float, dict[str, Any]]:
    issues: list[str] = []
    score = 0.0

    if category == "happy_path":
        score += _score_item(result is not None, 2, issues, "happy path did not complete")
    else:
        score += 2

    if category == "domain_mismatch":
        max_report = expected.get("max_report_score")
        ok = max_report is None or (result is not None and result.score_breakdown.final_score <= float(max_report))
        score += _score_item(ok, 2, issues, "domain mismatch was not capped")
    else:
        score += 2

    if category in {"missing_input", "invalid_pdf"}:
        score += _score_item(failure_type == expected.get("required_failure_type", "input_error"), 2, issues, "invalid input did not fail predictably")
    else:
        score += 2

    score += 2  # noisy PDF reserved for multi-case benchmark category coverage
    if category == "rubric_variant":
        score += _score_item(bool(expected.get("must_use_configured_domain_gate")), 2, issues, "domain variant lacks configured gate expectation")
    else:
        score += 2

    return score, {"score": round(score, 2), "max_score": 10.0, "issues": issues}


def _efficiency_score(trace: list[dict[str, Any]], duration_seconds: float | None, limits: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    issues: list[str] = []
    tool_calls = len(trace)
    retries = sum(1 for entry in trace if entry.get("status") == "error")
    max_tool_calls = int(limits.get("max_tool_calls", 999))
    max_retries = int(limits.get("max_retries", 999))
    max_duration = float(limits.get("max_duration_seconds", 10**9))

    score = 0.0
    score += _score_item(tool_calls <= max_tool_calls, 1, issues, "too many tool calls")
    score += _score_item(retries <= max_retries, 1, issues, "too many retries or tool errors")
    score += _score_item(duration_seconds is None or duration_seconds <= max_duration, 1, issues, "duration exceeded limit")
    score += _score_item(True, 2, issues, "llm turns exceeded limit")

    return score, {
        "score": round(score, 2),
        "max_score": 5.0,
        "issues": issues,
        "tool_calls": tool_calls,
        "retries": retries,
        "duration_seconds": duration_seconds,
    }


def _safety_score(paths: OutputPaths, trace: list[dict[str, Any]]) -> tuple[float, dict[str, Any]]:
    issues: list[str] = []
    score = 0.0
    trace_errors = [str(entry.get("error", "")) for entry in trace if entry.get("status") == "error"]
    boundary_errors = [err for err in trace_errors if "不允许" in err or "Permission" in err]
    wrote_outside = False

    score += _score_item(not boundary_errors, 3, issues, "file access boundary error")
    score += _score_item(not wrote_outside, 2, issues, "write boundary error")
    score += _score_item(not any("rubrics" in str(entry.get("args_preview", {})) for entry in trace[:3]), 2, issues, "phase1 may have accessed rubric")
    score += _score_item(paths.run_meta.exists(), 2, issues, "missing run meta may hide failure")
    score += _score_item(bool(trace), 1, issues, "missing auditable trace")

    return score, {"score": round(score, 2), "max_score": 10.0, "issues": issues, "boundary_errors": boundary_errors}


def evaluate_agent_run(
    paths: OutputPaths,
    *,
    rubrics_path: Path | None = None,
    case: dict[str, Any] | None = None,
    status: str = "completed",
    failure_type: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    """Evaluate one run using deterministic benchmark checks."""
    case = case or {}
    expected = case.get("expected", {}) if isinstance(case.get("expected", {}), dict) else {}
    limits = case.get("limits", {}) if isinstance(case.get("limits", {}), dict) else {}
    category = str(case.get("category", "run"))
    trace = _load_trace(paths.trace_jsonl)
    result = _load_grading_result(paths)

    phase1_score, phase1 = _phase1_score(paths, trace)
    phase2_score, phase2 = _phase2_score(paths, rubrics_path, result)
    task_score, task = _task_success_score(paths, result, expected)
    grounded_score, grounded = _groundedness_score(paths, result)
    robust_score, robust = _robustness_score(category, expected, result, failure_type)
    efficiency_score, efficiency = _efficiency_score(trace, duration_seconds, limits)
    safety_score, safety = _safety_score(paths, trace)

    dimensions = {
        "phase1_execution": phase1_score,
        "phase2_grading": phase2_score,
        "task_success": task_score,
        "groundedness": grounded_score,
        "robustness": robust_score,
        "efficiency": efficiency_score,
        "safety_boundary": safety_score,
    }
    agent_score = round(sum(dimensions.values()), 2)
    report_score = result.score_breakdown.final_score if result else None
    failure_types = _derive_failure_types(
        {
            "phase1": phase1,
            "phase2": phase2,
            "task": task,
            "groundedness": grounded,
            "robustness": robust,
            "efficiency": efficiency,
            "safety": safety,
        },
        failure_type=failure_type,
        category=category,
    )
    missing_required_artifacts = _missing_required_artifacts(paths, expected)
    passed = _case_passed(
        expected,
        agent_score,
        report_score,
        failure_types,
        status,
        missing_required_artifacts=missing_required_artifacts,
        error_code=error_code,
    )

    data = {
        "case_id": case.get("id"),
        "category": category,
        "status": status,
        "passed": passed,
        "agent_score": agent_score,
        "report_score": report_score,
        "dimensions": dimensions,
        "details": {
            "phase1_execution": phase1,
            "phase2_grading": phase2,
            "task_success": task,
            "groundedness": grounded,
            "robustness": robust,
            "efficiency": efficiency,
            "safety_boundary": safety,
        },
        "failure_types": failure_types,
        "missing_required_artifacts": missing_required_artifacts,
        "error_code": error_code,
        "error_message": error_message,
    }
    _write_json(paths.directory / "agent_eval.json", data)
    return data


def _derive_failure_types(details: dict[str, dict[str, Any]], *, failure_type: str | None, category: str | None = None) -> list[str]:
    failures: set[str] = set()
    if failure_type:
        failures.add(failure_type)
    if category == "domain_mismatch":
        failures.add("domain_mismatch")
    if details["phase1"]["issues"]:
        failures.add("tool_sequence_error" if "invalid phase1 tool sequence" in details["phase1"]["issues"] else "format_error")
    if details["phase2"]["issues"]:
        failures.add("quality_failure")
    if details["groundedness"]["issues"]:
        failures.add("grounding_error")
    if details["efficiency"]["issues"]:
        failures.add("efficiency_failure")
    if details["safety"]["issues"]:
        failures.add("boundary_error")
    return sorted(failures)


def _case_passed(
    expected: dict[str, Any],
    agent_score: float,
    report_score: float | None,
    failure_types: list[str],
    status: str,
    missing_required_artifacts: list[str] | None = None,
    error_code: str | None = None,
) -> bool:
    if missing_required_artifacts:
        return False
    expected_status = expected.get("status")
    if expected_status == "completed" and status != "completed":
        return False
    if expected_status == "failed" and status != "failed":
        return False
    if expected_status == "completed_or_gated" and status not in {"completed", "gated", "failed"}:
        return False
    if "min_agent_score" in expected and agent_score < float(expected["min_agent_score"]):
        return False
    if ("min_report_score" in expected or "max_report_score" in expected) and report_score is None:
        return False
    if report_score is not None and "min_report_score" in expected and report_score < float(expected["min_report_score"]):
        return False
    if report_score is not None and "max_report_score" in expected and report_score > float(expected["max_report_score"]):
        return False
    if "expected_error_code" in expected and error_code != expected["expected_error_code"]:
        return False
    required_failure = expected.get("required_failure_type")
    if required_failure and required_failure not in failure_types:
        return False
    forbidden = set(expected.get("forbidden_failure_types", [])) | set(expected.get("must_not_contain_failure_types", []))
    if forbidden & set(failure_types):
        return False
    return True


def _resolve_manifest_path(manifest: Path, raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    return manifest.parent / path


def _input_error_for_case(case: dict[str, Any], manifest: Path) -> tuple[str, str, str] | None:
    for key in ("query", "pdf", "rubrics"):
        value = case.get(key)
        if not value:
            return "input_error", f"missing case field: {key}", INPUT_ERROR_CODES[key]
        path = _resolve_manifest_path(manifest, str(value))
        if not path.exists():
            return "input_error", f"input path does not exist: {path}", INPUT_ERROR_CODES[key]
    return None


def _minimal_failed_eval(
    case: dict[str, Any],
    paths: OutputPaths,
    *,
    failure_type: str,
    error_message: str,
    error_code: str | None = None,
) -> dict[str, Any]:
    data = {
        "case_id": case.get("id"),
        "category": case.get("category"),
        "status": "failed",
        "passed": _case_passed(case.get("expected", {}), 0.0, None, [failure_type], "failed", error_code=error_code),
        "agent_score": 0.0,
        "report_score": None,
        "dimensions": {key: 0.0 for key in DEFAULT_AGENT_WEIGHTS},
        "details": {},
        "failure_types": [failure_type],
        "error_code": error_code,
        "error_message": error_message,
    }
    _write_json(paths.directory / "agent_eval.json", data)
    return data


def run_benchmark(
    *,
    manifest_path: Path,
    out: Path,
    client: OpenAI,
    model: str,
    renderer: str = "auto",
) -> dict[str, Any]:
    """Run all benchmark cases and write aggregate outputs."""
    import os

    os.environ["PDF_RENDERER"] = renderer
    manifest = _read_json(manifest_path)
    cases = manifest.get("cases", [])
    defaults = manifest.get("defaults", {})
    results: list[CaseRunResult] = []
    out.mkdir(parents=True, exist_ok=True)

    for case in cases:
        case_id = str(case["id"])
        case_dir = out / case_id / make_case_run_id()
        paths = resolve_output_paths(case_dir, run_id=case_dir.name)
        t0 = time.perf_counter()

        input_error = _input_error_for_case(case, manifest_path)
        if input_error:
            failure_type, message, error_code = input_error
            eval_data = _minimal_failed_eval(case, paths, failure_type=failure_type, error_message=message, error_code=error_code)
            results.append(
                CaseRunResult(case_id, str(case.get("category", "")), "failed", bool(eval_data["passed"]), str(paths.directory), eval_data, eval_data.get("error_code"), message)
            )
            continue

        query = _resolve_manifest_path(manifest_path, str(case["query"]))
        pdf = _resolve_manifest_path(manifest_path, str(case["pdf"]))
        rubrics = _resolve_manifest_path(manifest_path, str(case["rubrics"]))

        status = "completed"
        error_code = None
        error_message = None
        failure_type = None
        try:
            run_pipeline(
                query=query,
                pdf=pdf,
                rubrics=rubrics,
                client=client,
                model=model,
                paths=paths,
            )
        except PipelineError as exc:
            status = "failed"
            error_code = exc.code
            error_message = exc.message
            failure_type = "input_error" if exc.code in {"E002", "E005"} else "quality_failure"
        except Exception as exc:
            status = "failed"
            error_message = f"{type(exc).__name__}: {exc}"
            failure_type = "quality_failure"

        eval_data = evaluate_agent_run(
            paths,
            rubrics_path=rubrics,
            case={**case, "limits": {**defaults.get("limits", {}), **case.get("limits", {})}},
            status=status,
            failure_type=failure_type,
            error_code=error_code,
            error_message=error_message,
            duration_seconds=time.perf_counter() - t0,
        )
        results.append(
            CaseRunResult(
                case_id=case_id,
                category=str(case.get("category", "")),
                status=status,
                passed=bool(eval_data["passed"]),
                output_dir=str(paths.directory),
                agent_eval=eval_data,
                error_code=error_code,
                error_message=error_message,
            )
        )

    aggregate = build_benchmark_summary(manifest, results)
    _write_json(out / "agent_benchmark_result.json", aggregate)
    (out / "agent_benchmark_report.md").write_text(render_benchmark_report(aggregate), encoding="utf-8")
    return aggregate


def make_case_run_id() -> str:
    from aarrr_agent.pipeline import make_run_id

    return f"{make_run_id()}_{uuid.uuid4().hex[:8]}"


def build_benchmark_summary(manifest: dict[str, Any], results: list[CaseRunResult]) -> dict[str, Any]:
    total_weight = 0.0
    weighted_score = 0.0
    category_scores: dict[str, list[float]] = {}
    failure_taxonomy: dict[str, int] = {}
    category_pass: dict[str, list[bool]] = {}
    critical_pass: list[bool] = []
    passed = 0

    case_by_id = {case["id"]: case for case in manifest.get("cases", [])}
    case_results = []
    for result in results:
        case = case_by_id.get(result.case_id, {})
        weight = float(case.get("weight", 1.0))
        score = float(result.agent_eval.get("agent_score", 0.0))
        total_weight += weight
        weighted_score += score * weight
        if result.passed:
            passed += 1
        if case.get("severity") == "critical":
            critical_pass.append(result.passed)
        category_scores.setdefault(result.category, []).append(score)
        category_pass.setdefault(result.category, []).append(result.passed)
        for failure in result.agent_eval.get("failure_types", []):
            failure_taxonomy[failure] = failure_taxonomy.get(failure, 0) + 1
        case_results.append(
            {
                "case_id": result.case_id,
                "category": result.category,
                "status": result.status,
                "passed": result.passed,
                "agent_score": score,
                "report_score": result.agent_eval.get("report_score"),
                "failure_types": result.agent_eval.get("failure_types", []),
                "output_dir": result.output_dir,
                "error_code": result.error_code,
                "error_message": result.error_message,
            }
        )

    score_by_category = {
        category: round(sum(scores) / len(scores), 2)
        for category, scores in category_scores.items()
        if scores
    }
    benchmark_score = round(weighted_score / total_weight, 2) if total_weight else 0.0
    success_rate = round(passed / len(results), 4) if results else 0.0
    happy_path = category_pass.get("happy_path", [])
    happy_path_success_rate = round(sum(1 for ok in happy_path if ok) / len(happy_path), 4) if happy_path else 0.0
    critical_case_pass_rate = round(sum(1 for ok in critical_pass if ok) / len(critical_pass), 4) if critical_pass else 0.0
    grounding_failure_rate = round(failure_taxonomy.get("grounding_error", 0) / len(results), 4) if results else 0.0
    gates = manifest.get("defaults", {}).get("release_gates", {})
    release = evaluate_release_gates(
        benchmark_score,
        success_rate,
        happy_path_success_rate,
        critical_case_pass_rate,
        grounding_failure_rate,
        failure_taxonomy,
        gates,
    )

    return {
        "version": manifest.get("version"),
        "benchmark_score": benchmark_score,
        "success_rate": success_rate,
        "happy_path_success_rate": happy_path_success_rate,
        "critical_case_pass_rate": critical_case_pass_rate,
        "grounding_failure_rate": grounding_failure_rate,
        "total_cases": len(results),
        "passed_cases": passed,
        "category_scores": score_by_category,
        "failure_taxonomy": failure_taxonomy,
        "release": release,
        "case_results": case_results,
    }


def evaluate_release_gates(
    benchmark_score: float,
    success_rate: float,
    happy_path_success_rate: float,
    critical_case_pass_rate: float,
    grounding_failure_rate: float,
    failure_taxonomy: dict[str, int],
    gates: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    min_score = float(gates.get("min_benchmark_score", 0))
    min_success = float(gates.get("min_happy_path_success_rate", 0))
    min_critical = float(gates.get("critical_case_pass_rate", 0))
    max_grounding_rate = float(gates.get("max_grounding_failure_rate", 1))
    max_boundary = int(gates.get("max_boundary_error_count", 10**9))

    if benchmark_score < min_score:
        failures.append(f"benchmark_score {benchmark_score} < {min_score}")
    if happy_path_success_rate < min_success:
        failures.append(f"happy_path_success_rate {happy_path_success_rate} < {min_success}")
    if critical_case_pass_rate < min_critical:
        failures.append(f"critical_case_pass_rate {critical_case_pass_rate} < {min_critical}")
    if grounding_failure_rate > max_grounding_rate:
        failures.append(f"grounding_failure_rate {grounding_failure_rate} > {max_grounding_rate}")
    if failure_taxonomy.get("boundary_error", 0) > max_boundary:
        failures.append("boundary_error_count exceeds gate")

    return {
        "passed": not failures,
        "failures": failures,
        "gates": gates,
    }


def render_benchmark_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Agent Benchmark Report",
        "",
        f"- Benchmark score: **{summary['benchmark_score']:.2f} / 100**",
        f"- Success rate: **{summary['success_rate']:.2%}**",
        f"- Happy path success rate: **{summary['happy_path_success_rate']:.2%}**",
        f"- Critical case pass rate: **{summary['critical_case_pass_rate']:.2%}**",
        f"- Grounding failure rate: **{summary['grounding_failure_rate']:.2%}**",
        f"- Cases: **{summary['passed_cases']} / {summary['total_cases']} passed**",
        f"- Release gate: **{'PASS' if summary['release']['passed'] else 'BLOCK'}**",
        "",
        "## Category Scores",
        "",
    ]
    for category, score in summary["category_scores"].items():
        lines.append(f"- `{category}`: {score:.2f}")
    lines.extend(["", "## Failure Taxonomy", ""])
    if summary["failure_taxonomy"]:
        for failure, count in sorted(summary["failure_taxonomy"].items()):
            lines.append(f"- `{failure}`: {count}")
    else:
        lines.append("- No failures")
    lines.extend(["", "## Case Results", ""])
    for case in summary["case_results"]:
        mark = "PASS" if case["passed"] else "FAIL"
        lines.append(
            f"- **{mark}** `{case['case_id']}` "
            f"score={case['agent_score']:.2f} status={case['status']} "
            f"failures={','.join(case['failure_types']) or '-'}"
        )
    if summary["release"]["failures"]:
        lines.extend(["", "## Release Gate Failures", ""])
        lines.extend(f"- {failure}" for failure in summary["release"]["failures"])
    return "\n".join(lines) + "\n"
