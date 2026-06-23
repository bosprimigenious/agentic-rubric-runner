import json
from pathlib import Path

from aarrr_agent.acceptance import run_acceptance_gate


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_live_gate_fails_closed_without_manifest_or_result(tmp_path):
    summary = run_acceptance_gate(
        manifest_path=tmp_path / "missing_manifest.json",
        benchmark_result_path=tmp_path / "missing_result.json",
        out_path=tmp_path / "acceptance.json",
        mode="live",
    )
    assert summary["status"] == "NOT_READY"
    codes = {blocker["id"] for blocker in summary["blockers"]}
    assert "GATE-MANIFEST-MISSING" in codes
    assert "GATE-BENCHMARK-RESULT-MISSING" in codes


def test_offline_gate_validates_manifest_without_ready_claim(tmp_path):
    manifest = {
        "version": "test",
        "defaults": {},
        "cases": [
            {
                "id": category,
                "category": category,
                "severity": "critical" if category == "happy_path" else "major",
                "business_impact": "test",
                "owner": "test",
                "weight": 1,
                "query": "fixtures/query.txt",
                "pdf": "fixtures/attachment.pdf",
                "rubrics": "fixtures/rubrics.json",
                "expected": {},
            }
            for category in [
                "happy_path",
                "missing_input",
                "domain_mismatch",
                "adversarial_prompt",
                "rubric_variant",
            ]
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    _write(manifest_path, manifest)

    summary = run_acceptance_gate(
        manifest_path=manifest_path,
        benchmark_result_path=tmp_path / "missing_result.json",
        out_path=tmp_path / "acceptance.json",
        mode="offline",
    )
    assert summary["status"] == "OFFLINE_OK"
    assert not summary["blockers"]
    assert summary["warnings"]


def test_live_gate_blocks_score_regression_against_baseline(tmp_path):
    manifest_path = Path("fixtures/benchmarks/agent_cases.json")
    current = {
        "benchmark_score": 77.0,
        "success_rate": 1.0,
        "happy_path_success_rate": 1.0,
        "critical_case_pass_rate": 1.0,
        "grounding_failure_rate": 0.0,
        "failure_taxonomy": {},
        "release": {
            "passed": True,
            "failures": [],
            "gates": {"max_score_regression_points": 2},
        },
        "case_results": [
            {"case_id": "aarrr_happy_path", "passed": True, "failure_types": []},
            {"case_id": "missing_pdf", "passed": True, "failure_types": ["input_error"]},
            {"case_id": "aarrr_off_domain_pdf", "passed": True, "failure_types": ["domain_mismatch"]},
            {"case_id": "adversarial_query_read_rubric", "passed": True, "failure_types": []},
            {"case_id": "rubric_domain_variant", "passed": True, "failure_types": []},
        ],
    }
    result_path = tmp_path / "agent_benchmark_result.json"
    baseline_path = tmp_path / "baseline.json"
    _write(result_path, current)
    _write(baseline_path, {"benchmark_score": 80.0, "failure_taxonomy": {}, "case_results": current["case_results"]})

    summary = run_acceptance_gate(
        manifest_path=manifest_path,
        benchmark_result_path=result_path,
        baseline_path=baseline_path,
        out_path=tmp_path / "acceptance.json",
        mode="release",
    )
    assert summary["status"] == "NOT_READY"
    assert any(blocker["id"] == "GATE-BASELINE-SCORE-REGRESSION" for blocker in summary["blockers"])


def test_live_gate_requires_result_to_cover_manifest_cases(tmp_path):
    manifest_path = Path("fixtures/benchmarks/agent_cases.json")
    current = {
        "benchmark_score": 90.0,
        "success_rate": 1.0,
        "release": {"passed": True, "failures": [], "gates": {}},
        "case_results": [
            {"case_id": "aarrr_happy_path", "passed": True, "failure_types": []},
        ],
    }
    result_path = tmp_path / "agent_benchmark_result.json"
    _write(result_path, current)

    summary = run_acceptance_gate(
        manifest_path=manifest_path,
        benchmark_result_path=result_path,
        out_path=tmp_path / "acceptance.json",
        mode="live",
    )
    assert summary["status"] == "NOT_READY"
    assert any(blocker["id"] == "GATE-BENCHMARK-CASE-COVERAGE" for blocker in summary["blockers"])
