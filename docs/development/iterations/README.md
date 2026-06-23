# Iteration Log

This directory records development slices for `agentic-rubric-runner`.

本目录记录 `agentic-rubric-runner` 的细粒度迭代切片。

Each iteration note should include:

- version or internal slice ID;
- scope;
- changed contracts;
- acceptance command used;
- benchmark manifest and baseline used;
- known blockers;
- next actions.

Use these logs to keep READY claims tied to actual gate evidence.

## Naming / 命名

Use this pattern:

```text
<version>-<short-scope>.md
```

Examples:

```text
0.5.2-gates.md
0.5.2.1-offline-acceptance.md
0.5.2.2-domain-gate-config.md
0.5.2.3-baseline-regression.md
```

## Required Template / 必填模板

Each iteration log should use this structure:

````markdown
# <version> <title>

## Scope / 范围

What changed in this slice.

## Contracts / 合同变化

Changed artifacts, commands, schemas, manifests, or gates.

## Acceptance / 验收

Command used:

```bash
scripts/acceptance.sh offline
```

Result:

```text
OFFLINE_OK / READY / NOT_READY
```

## Evidence / 证据

- manifest:
- baseline:
- output:
- commit:

## Blockers / 阻断项

List blockers honestly. If none, write `None`.

## Next / 下一步

Next slice and why.
````

## READY Rule / READY 规则

Do not write READY in an iteration log unless the relevant gate produced READY.

除非对应门控真实输出 READY，否则迭代日志不能写 READY。
