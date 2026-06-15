"""测试：CLI 与 pipeline 模块可导入。"""

from typer.testing import CliRunner

from aarrr_agent.cli import app, main, phase1, run
from aarrr_agent.pipeline import run_phase1_pipeline, run_phase2_pipeline


def test_cli_app_importable():
    assert app is not None
    assert callable(main)
    assert callable(phase1)
    assert callable(run)


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
    assert "--query" in result.stdout
