"""测试：CLI 与 pipeline 模块可导入。"""

import inspect
import json
from types import SimpleNamespace
from pathlib import Path

from typer.testing import CliRunner

from aarrr_agent.benchmark import (
    _case_passed,
    _derive_failure_types,
    _has_calibration_or_gate_signal,
    _input_error_for_case,
    evaluate_agent_run,
    evaluate_release_gates,
    run_benchmark,
)
from aarrr_agent.cli import app, bench, eval_run, main, phase1, run
from aarrr_agent.pipeline import run_phase1_pipeline, run_phase2_pipeline


def test_cli_app_importable():
    assert app is not None
    assert callable(main)
    assert callable(phase1)
    assert callable(run)
    assert callable(eval_run)
    assert callable(bench)
    assert callable(evaluate_agent_run)
    assert callable(run_benchmark)


def test_pipeline_functions_importable():
    assert callable(run_phase1_pipeline)
    assert callable(run_phase2_pipeline)


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "phase1" in result.stdout


def test_phase1_help():
    runner = CliRunner()
    result = runner.invoke(app, ["phase1", "--help"])
    assert result.exit_code == 0
    assert _has_option(phase1, "query", "--query")


def test_bench_help():
    runner = CliRunner()
    result = runner.invoke(app, ["bench", "--help"])
    assert result.exit_code == 0
    assert _has_option(bench, "manifest", "--manifest")


def _has_option(command, parameter_name: str, option_name: str) -> bool:
    parameter = inspect.signature(command).parameters[parameter_name]
    return option_name in getattr(parameter.default, "param_decls", ())


def test_domain_mismatch_failure_type_is_derived():
    failure_types = _derive_failure_types(
        {
            "phase1": {"issues": []},
            "phase2": {"issues": []},
            "groundedness": {"issues": []},
            "efficiency": {"issues": []},
            "safety": {"issues": []},
        },
        failure_type=None,
        category="domain_mismatch",
    )
    assert "domain_mismatch" in failure_types


def test_required_artifacts_block_case_pass():
    assert not _case_passed(
        {"status": "completed", "required_artifacts": ["phase1_output.pdf"]},
        100.0,
        100.0,
        [],
        "completed",
        missing_required_artifacts=["phase1_output.pdf"],
    )


def test_report_score_gates_require_grading_result():
    assert not _case_passed(
        {"status": "completed_or_gated", "max_report_score": 10},
        80.0,
        None,
        ["domain_mismatch"],
        "failed",
    )


def test_expected_error_code_must_match_observed_code():
    assert not _case_passed(
        {"status": "failed", "required_failure_type": "input_error", "expected_error_code": "E002"},
        0.0,
        None,
        ["input_error"],
        "failed",
        error_code="E005",
    )


def test_input_error_code_is_derived_from_missing_pdf(tmp_path):
    case = {"query": "query.txt", "pdf": "missing.pdf", "rubrics": "rubrics.json"}
    (tmp_path / "query.txt").write_text("query", encoding="utf-8")
    (tmp_path / "rubrics.json").write_text("{}", encoding="utf-8")
    assert _input_error_for_case(case, tmp_path / "manifest.json") == (
        "input_error",
        f"input path does not exist: {tmp_path / 'missing.pdf'}",
        "E002",
    )


def test_calibration_signal_requires_real_text_marker():
    result = SimpleNamespace(
        hard_constraints=[],
        soft_constraints=[SimpleNamespace(reason="looks fine", missing=[], score=4)],
        optional_constraints=[],
        overall_comment="",
    )
    assert not _has_calibration_or_gate_signal(result)
    result.soft_constraints[0].reason = "程序门控：附件领域不匹配"
    assert _has_calibration_or_gate_signal(result)


def test_release_gates_include_critical_and_grounding_rates():
    release = evaluate_release_gates(
        benchmark_score=90.0,
        success_rate=1.0,
        happy_path_success_rate=1.0,
        critical_case_pass_rate=0.5,
        grounding_failure_rate=0.2,
        failure_taxonomy={},
        gates={
            "min_benchmark_score": 80,
            "min_happy_path_success_rate": 0.95,
            "critical_case_pass_rate": 1.0,
            "max_grounding_failure_rate": 0.05,
        },
    )
    assert not release["passed"]
    assert any("critical_case_pass_rate" in failure for failure in release["failures"])
    assert any("grounding_failure_rate" in failure for failure in release["failures"])


def test_benchmark_manifest_example_is_valid_json():
    manifest = Path("fixtures/benchmarks/agent_cases.example.json")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["cases"]
    assert "release_gates" in data["defaults"]


def test_ui_exits_when_streamlit_missing():
    from unittest.mock import patch

    runner = CliRunner()
    with patch("aarrr_agent.cli.importlib.util.find_spec", return_value=None):
        result = runner.invoke(app, ["ui"])
    assert result.exit_code == 1
    assert "未安装 Web 依赖" in result.stdout
