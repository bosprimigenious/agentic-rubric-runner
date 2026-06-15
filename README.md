# agentic-rubric-runner

面向社交电商平台 AARRR 指标方案的双阶段 Agent 流水线：Phase 1 通过 function calling 自主读文件并写报告，Phase 2 按 rubrics 评分。

## 结构

```
agentic-rubric-runner/
├── solution.py           # 双阶段入口
├── validate_grading.py   # 校验 grading_result.json
├── aarrr_agent/          # 核心实现
│   ├── agent.py          # Phase 1 tool-use loop
│   ├── tools.py          # read_text / read_pdf / write_report
│   ├── pdf_gen.py        # Markdown → PDF（reportlab + 中文字体）
│   ├── grader.py         # Phase 2 评分 + 分数重算
│   ├── schemas.py        # Pydantic 校验
│   └── config.py         # 权重与常量
└── fixtures/             # 题目材料
    ├── query.txt
    ├── rubrics.json
    ├── attachment.pdf
    └── TASK.md
```

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt

export DEEPSEEK_API_KEY="your_key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"

python solution.py \
  --query fixtures/query.txt \
  --pdf fixtures/attachment.pdf \
  --rubrics fixtures/rubrics.json \
  --phase1-out phase1_output.pdf \
  --grading-out grading_result.json \
  --trace-out agent_trace.jsonl

python validate_grading.py grading_result.json
```

## 评分公式

`final_score = (hard/15)×50 + (soft/24)×30 + (optional/3)×20`

程序在 Phase 2 结束后强制重算，不信任模型返回的 breakdown 数字。
