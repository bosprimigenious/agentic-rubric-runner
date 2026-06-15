# 面试题

## 文件

- `query.txt` — 任务描述
- `attachment.pdf` — 附件（原：基于AARRR模型的社交电商平台用户增长策略研究.pdf）
- `rubrics.json` — 评分标准

---

## 任务

分两个阶段完成：

**Phase 1 — 用 Agent 做题**
- 输入：`query.txt` + 附件（仅这两项）
- 输出：模型产物文件
- 必须通过 Agent 执行，不允许裸调用 LLM 直接返回答案
- 模型使用 DeepSeek V4 Pro（`deepseek-chat`）或 DeepSeek Flash 或者其他模型都行（根据自己的能力，deepseek flash很便宜）

**Phase 2 — 用 Rubrics 打分**
- 输入：Phase 1 生成的文件 + `rubrics.json`+ query.txt + 附件
- 输出：`grading_result.json`

---

## 打分 Prompt

```
You are a strict evaluator. Grade the submitted document against the rubrics below.

RUBRICS:
{rubrics.json content}

SUBMITTED DOCUMENT:
{Phase 1 output content}

SCORING:
- hard_constraints: 0 (fail) or 1 (pass) per item
- soft_constraints: 0–4 per item based on tier descriptions
- optional_constraints: 0 (absent) or 1 (present) per item

Output ONLY valid JSON:
{
  "hard_constraints":     [{"id": "H01", "score": 1, "reason": "..."}],
  "soft_constraints":     [{"id": "S01", "score": 3, "reason": "..."}],
  "optional_constraints": [{"id": "O01", "score": 1, "reason": "..."}],
  "score_breakdown": {
    "hard_score": 14, "hard_max": 15,
    "soft_score": 18, "soft_max": 24,
    "optional_score": 2, "optional_max": 3,
    "final_score": 82.5
  },
  "overall_comment": "..."
}
```

---

## 实现思路

可以接入现成 Agent，也可以自己实现：

- **Claude Code** / **Codex** / **OpenCode** 等现成 coding agent
- 自实现 ReAct 循环：用 function calling 挂载 read_pdf / write_pdf 等工具

Phase 2 打分用模型调用配合结构化 prompt 即可。

---

## 交付

| 文件 | 说明 |
|------|------|
| `solution.py` | 完整双阶段实现代码 |
| `grading_result.json` | Phase 2 评分结果 |

## 其他

可以任意借助 AI coding 工具实现。
