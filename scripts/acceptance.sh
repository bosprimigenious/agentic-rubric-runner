#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-auto}"
MANIFEST="${MANIFEST:-fixtures/benchmarks/agent_cases.json}"
BENCH_OUT="${BENCH_OUT:-outputs/bench}"
BENCH_RESULT="${BENCH_RESULT:-${BENCH_OUT}/agent_benchmark_result.json}"
BASELINE="${BASELINE:-fixtures/benchmarks/baseline.json}"
ACCEPTANCE_OUT="${ACCEPTANCE_OUT:-outputs/acceptance_summary.json}"

python -m ruff check aarrr_agent tests app.py
python -m pytest -q
python -m build

if [[ "${MODE}" == "offline" ]]; then
  agentic-rubric acceptance \
    --mode offline \
    --manifest "${MANIFEST}" \
    --benchmark-result "${BENCH_RESULT}" \
    --out "${ACCEPTANCE_OUT}"
  exit 0
fi

if [[ -z "${DEEPSEEK_API_KEY:-}" && "${MODE}" == "release" ]]; then
  echo "DEEPSEEK_API_KEY is required for release acceptance."
  exit 1
fi

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "DEEPSEEK_API_KEY is not set; running deterministic offline gate only."
  agentic-rubric acceptance \
    --mode offline \
    --manifest "${MANIFEST}" \
    --benchmark-result "${BENCH_RESULT}" \
    --out "${ACCEPTANCE_OUT}"
  exit 0
fi

agentic-rubric bench \
  --manifest "${MANIFEST}" \
  --out "${BENCH_OUT}"

agentic-rubric acceptance \
  --mode "${MODE/auto/live}" \
  --manifest "${MANIFEST}" \
  --benchmark-result "${BENCH_RESULT}" \
  --baseline "${BASELINE}" \
  --out "${ACCEPTANCE_OUT}"
