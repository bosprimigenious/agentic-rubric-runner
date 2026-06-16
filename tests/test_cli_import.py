"""测试：CLI 与 pipeline 模块可导入。"""

import inspect
import json
from pathlib import Path

from typer.testing import CliRunner

from aarrr_agent.benchmark import (
    _case_passed,
    _derive_failure_types,
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
