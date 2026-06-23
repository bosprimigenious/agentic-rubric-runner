# Development Manual: Truthful Benchmark Gates

This manual defines the next development target for `agentic-rubric-runner` after
`0.5.1`. The goal is to move from an auditable rubric runner to a trustworthy
Agent evaluation and release-gate platform.

## Version Target

Current public baseline: `0.5.1`.

当前公开基线：`0.5.1`。

The project may use a LoopPilot-style fine-grained internal version line after
`0.5.1`, but public package releases should remain readable.

`0.5.1` 之后，可以使用类似 LoopPilot 的细粒度内部版本线；但公开包版本仍应保持简洁、可读。

### Version Layers / 版本层级

| Layer | Format | Example | Meaning |
|---|---|---|---|
| Public release / 公开发布 | `MAJOR.MINOR.PATCH` | `0.5.2` | PyPI, GitHub release, README badge |
| Internal slice / 内部切片 | `MAJOR.MINOR.PATCH.SLICE` | `0.5.2.1` | One implementation slice under a public patch |
| Gate iteration / 门控迭代 | `MAJOR.MINOR.PATCH.SLICE.GATE` | `0.5.2.1.3` | Gate, manifest, or baseline refinement |
| Evidence run / 证据运行 | `MAJOR.MINOR.PATCH.SLICE.GATE.RUN` | `0.5.2.1.3.2` | A documented acceptance or benchmark run |

Use long versions for planning, iteration logs, and handoff prompts. Use short
versions for installable releases unless the packaging ecosystem explicitly
needs the longer identifier.

长版本用于计划、迭代日志和交接提示；正式可安装发布默认使用短版本，除非打包体系明确需要长标识。

### Version Semantics / 版本语义

```text
0.5.2.1.3.2
│ │ │ │ │ └─ evidence run / 验收运行编号
│ │ │ │ └─── gate iteration / 门控或基线迭代
│ │ │ └───── implementation slice / 实现切片
│ │ └─────── public patch / 公开 patch
│ └───────── public minor / 公开 minor
└─────────── public major / 公开 major
```

Rules:

- Increment `PATCH` for a user-visible stabilization bundle.
- Increment `SLICE` when a new implementation slice begins.
- Increment `GATE` when acceptance rules, benchmark manifest, or baseline
  changes.
- Increment `RUN` for reruns that change evidence but not code.
- Never use a longer version to hide a failed gate.

规则：

- 用户可见的稳定化包递增 `PATCH`。
- 新实现切片递增 `SLICE`。
- 验收规则、benchmark manifest 或 baseline 变化递增 `GATE`。
- 只改变验收证据、不改代码时递增 `RUN`。
- 不允许用更长版本号掩盖门控失败。

### Short-term Line / 短期版本线

| Version | Scope | Release meaning |
|---|---|---|
| `0.5.1.x` | Documentation, wording, schema, and test stabilization | Patch-level cleanup, no major behavior shift |
| `0.5.2.x` | Real benchmark manifest and artifact contract | Benchmark inputs become runnable, not only examples |
| `0.5.2.1.x` | Acceptance entrypoint and fail-closed manifest checks | Local and CI can run deterministic offline gate |
| `0.5.2.2.x` | Domain gate configuration | Rubric/config controls domain matching |
| `0.5.2.3.x` | Baseline regression gate | Release gate compares against stored baseline |
| `0.5.2.4.x` | Web evidence policy | Optional web checks are source-scoped and rubric-declared |
| `0.5.3.x` | Live acceptance prototype | Gate can report PASS or BLOCK from live benchmark output |
| `0.6.0` | Truthful benchmark gates | The project can honestly say whether a run or version is READY |

Do not mark the project READY merely because `run`, `eval-run`, or `bench`
finishes. READY is controlled only by the aggregate gate.

不要因为 `run`、`eval-run` 或 `bench` 单次完成就标记 READY。READY 只由总门控决定。

## Documentation System / 文档体系

The documentation system has three layers:

文档体系分三层：

| Layer | Path | Purpose |
|---|---|---|
| Development manual / 开发手册 | `docs/development/README.md` | Stable contracts: gates, artifacts, rubric rules, version rules |
| Iteration logs / 迭代日志 | `docs/development/iterations/` | Slice-level history, acceptance evidence, blockers, next actions |
| User README / 用户 README | `README.md` | Install, quick start, command reference, public status |

Rules:

- The development manual defines contracts; it should change only when the
  contract changes.
- Iteration logs record what happened in a slice; they may be more detailed and
  time-sensitive.
- README should describe only user-facing commands and truthful current status.
- If docs and code disagree, acceptance gate output wins.

规则：

- 开发手册定义合同，只在合同变化时修改。
- 迭代日志记录某个切片发生了什么，可以更细、更贴近当时状态。
- README 只描述用户命令和真实当前状态。
- 文档与代码冲突时，以 acceptance gate 输出为准。

## Product Direction

LoopPilot is a long-running project-management agent. This project should not
copy its loop scheduler. It should copy the stricter engineering posture:

- every run has traceable artifacts;
- every score has a contract;
- every release has a gate;
- every blocker is visible;
- every READY claim is earned.

The target product shape is:

```text
task + source files + rubric
  -> phase1 agent run
  -> report artifacts
  -> phase2 rubric grading
  -> run-level agent evaluation
  -> benchmark aggregation
  -> acceptance gate
  -> READY or NOT READY
```

### Difference From LoopPilot / 与 LoopPilot 的边界

| Area | LoopPilot | agentic-rubric-runner |
|---|---|---|
| Goal / 目标 | Long-running autonomous project loop | Bounded evaluation and release gate |
| Web behavior / 联网行为 | Proactively searches, monitors, and collects material | Uses only rubric-declared source scopes |
| State / 状态 | Project memory, tasks, schedules, recurring loops | Run artifacts, benchmark results, acceptance summaries |
| Output / 输出 | Work plans, reports, ongoing project actions | Scores, evidence, gates, pass/block decisions |
| Risk / 风险 | Over-expansion or stale autonomous actions | Unsupported scoring evidence or source leakage |

LoopPilot may ask "what should I look for next?" This project should ask "what
sources does this rubric explicitly allow, and did the evidence support the
score?"

LoopPilot 可以主动问“下一步要找什么”；本项目应该问“rubric 明确允许查哪些来源，证据是否支撑给分”。

## Artifact Contract

Every complete run should produce the following files:

| Artifact | Required for | Purpose |
|---|---|---|
| `phase1_output.md` | run, eval, bench | Human-readable generated report source |
| `phase1_output.html` | run, eval, bench | Preview artifact |
| `phase1_output.pdf` | run, eval, bench | Final report artifact |
| `evidence_pack.json` | eval, bench, gate | Source facts and evidence IDs |
| `agent_trace.jsonl` | eval, bench, gate | Tool sequence and execution audit |
| `run_meta.json` | eval, bench, gate | Model, input hashes, status, timing, costs |
| `grading_result.json` | phase2, eval, bench | Report-level rubric score |
| `grading_report.md` | phase2, eval, bench | Human-readable grading explanation |
| `grading_report.html` | phase2, eval, bench | Preview artifact |
| `agent_eval.json` | eval, bench, gate | Run-level agent score and failure taxonomy |
| `agent_benchmark_result.json` | bench, gate | Suite-level result and release status |
| `acceptance_summary.json` | gate | Final READY or NOT READY decision |

`run_meta.json` should be extended before `0.6.0` with:

- `terminal_reason`: `write_succeeded`, `phase1_done_seen`,
  `max_turns_exceeded`, `pipeline_error`, or `user_cancelled`;
- `error_code` and `error_message` when status is not completed;
- `token_usage` with prompt, completion, and total tokens when the provider
  returns usage;
- `estimated_cost` when model pricing is configured;
- `tool_calls`, `retry_count`, and `boundary_error_count`;
- `git_commit` and package version when available.

## Gate Design

The acceptance gate must be fail-closed. Missing data is a blocker unless the
gate explicitly marks it as optional.

### Gate Levels

| Level | Input | Output | Use |
|---|---|---|---|
| Run Gate | One `agent_eval.json` | `PASS` / `BLOCK` | Decide whether a single run is trustworthy |
| Benchmark Gate | One `agent_benchmark_result.json` | `PASS` / `BLOCK` | Decide whether a version passes case-suite checks |
| Release Gate | Benchmark plus baseline | `READY` / `NOT READY` | Decide whether a tag or release is acceptable |

### Blocker Rules

Any of the following must return `NOT READY`:

- missing required artifact;
- invalid JSON schema;
- Phase 1 reads or appears to read rubric content;
- file access boundary violation;
- critical case failed;
- benchmark score below configured threshold;
- happy-path success rate below threshold;
- grounding failure rate above threshold;
- unknown evidence references in report;
- final score not reproducible by programmatic recomputation;
- regression against baseline worse than the configured tolerance;
- uncategorized failure.

The gate should output:

```json
{
  "status": "NOT_READY",
  "gate_version": "0.6.0",
  "source": "outputs/bench/agent_benchmark_result.json",
  "blockers": [
    {
      "id": "GATE-BLOCKER-001",
      "severity": "blocker",
      "reason": "critical case failed",
      "case_id": "aarrr_happy_path",
      "failure_types": ["grounding_error"]
    }
  ],
  "warnings": [],
  "required_next_actions": [
    "Fix citation validation and rerun the benchmark suite."
  ]
}
```

Use `READY` only when there are no blockers.

## Benchmark Manifest Contract

The benchmark manifest should move from example-only to runnable case suite.

Every case should include:

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Stable case ID |
| `category` | yes | `happy_path`, `domain_mismatch`, `missing_input`, `invalid_pdf`, `noisy_pdf`, `rubric_variant`, `adversarial_prompt`, or `run_isolation` |
| `severity` | yes | `critical`, `major`, or `minor` |
| `business_impact` | yes | Why this case matters |
| `owner` | yes | Responsible area |
| `weight` | yes | Benchmark aggregation weight |
| `query` | yes | Query file path |
| `pdf` | yes | Source PDF path |
| `rubrics` | yes | Rubric file path |
| `expected` | yes | Status, score thresholds, artifacts, and failure expectations |
| `limits` | optional | Tool-call, retry, duration, token, or cost limits |

Critical cases must be must-pass by default. A skipped critical case is a
blocker unless the manifest explains an explicit temporary waiver.

## Rubric Generation Standard

Rubric generation should produce a grading contract, not a loose checklist.

### Rubric Inputs

A rubric generator should read:

- task query;
- source attachment summaries or evidence pack;
- target output format;
- domain definition;
- forbidden behavior;
- desired scoring strictness;
- optional release-gate profile;
- optional web evidence policy.

Phase 1 must never read the generated rubric. Rubric generation is a setup step
or Phase 2 input, not a report-generation dependency.

## Web Evidence Policy / 联网证据策略

Internet access is useful, but it must be optional, explicit, and auditable.

联网有价值，但必须是可选、显式、可审计的。

### Default Rule / 默认规则

By default, scoring is document-grounded and offline:

默认情况下，评分以本地文档为准，并保持离线：

- Phase 1 does not browse the web.
- Phase 2 does not browse the web unless the rubric allows it.
- Benchmark and acceptance must have deterministic offline gates.
- Web evidence cannot override a missing source requirement from the attachment.

- Phase 1 不联网。
- Phase 2 只有在 rubric 允许时才联网。
- benchmark 和 acceptance 必须有 deterministic offline gate。
- 联网证据不能替代附件里必须存在的事实依据。

### Allowed Use Cases / 允许场景

Use web evidence only for:

仅在以下场景使用联网证据：

- verifying current external facts that may have changed;
- checking official standards, regulations, APIs, or release notes;
- validating whether a public citation or benchmark number exists;
- comparing submitted claims against authoritative public sources;
- enriching rubric generation when the task explicitly asks for current public
  context.

Do not use web evidence for:

不要用联网证据做以下事情：

- filling in facts that the assignment required the attachment to provide;
- rescuing a weak report by importing outside material;
- broad open-ended crawling;
- personal data collection;
- non-authoritative SEO pages when official sources exist.

### Source Registry / 来源注册表

Rubrics may declare a `web_evidence_policy`:

rubric 可以声明 `web_evidence_policy`：

```json
{
  "web_evidence_policy": {
    "enabled": false,
    "mode": "official_only",
    "allowed_domains": [
      "sec.gov",
      "sam.gov",
      "nist.gov",
      "iso.org",
      "w3.org",
      "python.org",
      "docs.github.com",
      "platform.openai.com"
    ],
    "disallowed_domains": [
      "content farms",
      "unsourced blogs",
      "forum reposts"
    ],
    "max_sources_per_item": 3,
    "require_citations": true,
    "cache_evidence": true
  }
}
```

Recommended source classes:

推荐来源类型：

| Task type | Preferred sources |
|---|---|
| Company filings / 公司披露 | `sec.gov`, official investor-relations pages |
| Government or policy / 政府政策 | official `.gov` sites, legislation portals, regulator pages |
| Standards / 标准 | `iso.org`, `w3.org`, `ietf.org`, `nist.gov`, official standards bodies |
| Software/API / 软件与 API | official docs, release notes, GitHub repositories, PyPI/npm metadata |
| Academic / 学术 | DOI landing pages, publisher pages, arXiv, PubMed, Google Scholar only as discovery |
| Security / 安全 | NVD, CISA, vendor advisories, official CVE records |
| Market or pricing / 市场价格 | official pricing pages, exchange/regulator sources, not scraped summaries |

### Web Evidence Artifacts / 联网证据工件

When web is enabled, every run should add:

启用联网时，每次运行应额外输出：

| Artifact | Purpose |
|---|---|
| `web_evidence_pack.json` | URLs, titles, timestamps, snippets, hashes, and allowed-domain status |
| `web_citation_map.json` | Which rubric item used which web source |
| `web_fetch_log.jsonl` | Fetch/query audit trail |

Each web evidence item should include:

每条联网证据应包含：

- URL;
- source type;
- retrieval timestamp;
- whether it matched an allowed domain;
- short excerpt or structured fact;
- hash of fetched content when available;
- rubric item IDs that used it.

### Gate Rules / 门控规则

The acceptance gate must block when:

acceptance gate 必须在以下情况阻断：

- web is used while `web_evidence_policy.enabled` is false;
- a scored item cites a disallowed domain;
- web evidence is missing citation metadata;
- current-fact scoring relies on stale cached evidence beyond rubric TTL;
- source count exceeds policy limits;
- web evidence contradicts attachment evidence and the report does not disclose
  the conflict.

Offline CI should not need network. Live release gate may run web-enabled cases
only when credentials and network are available.

离线 CI 不应依赖网络。只有 live release gate 在具备凭证和网络时才运行联网 case。

### Rubric Structure

Keep the existing three-group model:

| Group | Score range | Meaning |
|---|---:|---|
| `hard_constraints` | `0` or `1` | Mandatory requirements and safety boundaries |
| `soft_constraints` | `0` to `4` | Quality differences with clear scale anchors |
| `optional_constraints` | `0` or `1` | Extra quality signals that should not hide hard failures |

Recommended weights remain:

```text
final_score =
  hard_score / hard_max * 50
+ soft_score / soft_max * 30
+ optional_score / optional_max * 20
```

### Hard Constraint Rules

Hard constraints should cover:

- required output format;
- domain match;
- required sections or deliverables;
- use of source material;
- no unsupported outside facts;
- required evidence or citation behavior;
- safety and boundary requirements;
- task-specific must-haves.

Hard constraints should be binary. If partial credit is tempting, move that
requirement into soft constraints and keep a smaller binary hard condition.

### Soft Constraint Rules

Soft constraints should use explicit `0` to `4` anchors:

| Score | Meaning |
|---:|---|
| `0` | Missing or unusable |
| `1` | Present but shallow, incomplete, or generic |
| `2` | Partially complete and relevant |
| `3` | Mostly complete with specific detail |
| `4` | Complete, grounded, and operationally useful |

Every soft item should state what changes between adjacent scores. Avoid vague
phrases like "good", "reasonable", or "high quality" unless they are tied to
observable criteria.

### Evidence Rules

For each rubric item, include:

- `needs_reference`: `是` or `否`;
- `reference_facts`: the source facts needed to judge the item;
- `fact_source`: source filename and page or section when available.

If `needs_reference` is `是`, a nonzero score must be backed by either:

- a citation in the generated report;
- an evidence ID from `evidence_pack.json`;
- a quoted or summarized fact from the attachment.

Source-dependent items with no evidence should be capped or set to zero,
depending on severity.

### Domain Gate

Rubric generation should include a configurable domain gate:

```json
{
  "domain_gate": {
    "target_domain": "social_commerce_growth",
    "positive_signals": ["AARRR", "获客", "激活", "留存", "变现", "传播"],
    "negative_signals": ["DNS", "网络协议", "编译器"],
    "min_positive_hits": 2,
    "max_negative_hits": 1,
    "on_mismatch": {
      "status": "gated",
      "max_report_score": 10,
      "failure_type": "domain_mismatch"
    }
  }
}
```

Before `0.7.0`, hard-coded domain keywords should be migrated into this
rubric/config structure.

## Agent Evaluation Standard

Run-level evaluation should remain 100 points:

| Dimension | Weight | Primary judge |
|---|---:|---|
| Phase 1 execution | 20 | Programmatic |
| Phase 2 grading | 15 | Programmatic |
| Task success | 20 | Programmatic |
| Groundedness | 20 | Programmatic first, hybrid if needed |
| Robustness | 10 | Benchmark category checks |
| Efficiency | 5 | Programmatic |
| Safety boundary | 10 | Programmatic |

At least 70% of the benchmark score should come from programmatic or hybrid
checks. Pure LLM judge output should not directly set total scores.

## Rubric Generator Acceptance Criteria

A rubric generator is acceptable only when it satisfies all of the following:

- generated JSON validates against the rubric schema;
- every item has a unique stable ID;
- all hard constraints are binary;
- every soft constraint has all five anchors from `0` to `4`;
- every source-dependent item declares `needs_reference = 是`;
- domain gate is configurable rather than hard-coded;
- generated rubric contains no source facts that cannot be traced to the input
  attachment summary or evidence pack;
- generated rubric can be used by Phase 2 without changing Phase 1 inputs;
- the generator emits a short `rubric_summary` explaining scope and strictness;
- tests include at least one happy path, one domain mismatch, and one
  adversarial query case.

## Implementation Slices

### Slice 1: Artifact and Status Contract

- Extend `run_meta.json`.
- Add schema tests for `terminal_reason`, error fields, and token/cost fields.
- Update README wording to avoid premature READY claims.

### Slice 2: Acceptance Gate

- Add an `acceptance` CLI command.
- Read `agent_benchmark_result.json`.
- Emit `acceptance_summary.json`.
- Return nonzero exit code on `NOT_READY`.
- Add anti-cheat tests for missing artifacts and fake green benchmark output.

Canonical local and CI entrypoint:

```bash
scripts/acceptance.sh offline
scripts/acceptance.sh release
```

`offline` validates deterministic contracts such as manifest shape, required
case categories, and schema parseability. It may return `OFFLINE_OK`, but never
claims `READY`.

`release` requires a live API key, runs the benchmark suite, compares against
baseline, and fails closed on blockers. It must not downgrade to offline mode.

### Slice 3: Runnable Benchmark Manifest

- Convert example benchmark cases into runnable fixtures.
- Add `must_pass` or infer it from `severity = critical`.
- Add domain mismatch, missing input, adversarial prompt, and rubric variant
  cases.

### Slice 4: Rubric Generator

- Add a rubric generation module or CLI command.
- Generate hard, soft, optional constraints plus domain gate.
- Validate generated rubric before writing it.
- Add tests for schema, evidence requirements, and domain gate behavior.

### Slice 5: Baseline Regression

- Store a previous benchmark result as baseline.
- Compare benchmark score, category scores, grounding failure rate, and cost.
- Block release when regression exceeds configured tolerance.

Baseline checks must block:

- benchmark score regression beyond threshold;
- critical or must-pass case changing from pass to fail;
- new boundary or grounding failures;
- missing cost/duration data should be a warning until those fields exist, then
  become an approval gate.

## Done Definition for `0.6.0`

`0.6.0` is done only when:

- `bench` can run a non-placeholder manifest;
- `acceptance` produces `READY` or `NOT_READY`;
- critical failures always block;
- missing artifacts always block;
- rubric generation rules are documented and tested;
- `run_meta.json` exposes terminal reason and failure details;
- README points users to the truthful gate;
- tests cover the gate's fail-closed behavior.

Until then, the honest status is:

```text
0.5.x: benchmark-capable, acceptance gate in progress.
Full truthful benchmark gates: NOT READY.
```
