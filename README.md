# agentic-rubric-runner

面向社交电商平台 AARRR 指标方案的双阶段 Agent 流水线。

- **Phase 1**：自实现 function calling tool-use loop（模型自主决定调用工具）
- **Phase 2**：严格 evaluator + Pydantic 校验 + 程序重算分数

## 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.10+ |
| 模型接口 | openai SDK（兼容 DeepSeek） |
| Agent 机制 | 自实现 tool-use loop |
| PDF 读取 | PyMuPDF |
| PDF 生成 | ReportLab + NotoSansCJK / 系统字体 |
| JSON 校验 | Pydantic v2 |
| 审计轨迹 | agent_trace.jsonl |

不使用 LangGraph、LangChain、CrewAI、WeasyPrint。

## 结构

```
agentic-rubric-runner/
├── solution.py
├── validate_grading.py
├── aarrr_agent/
│   ├── agent.py          # Phase 1 tool-use loop
│   ├── tools.py          # read_text / read_pdf / write_pdf_report
│   ├── pdf_gen.py        # ReportLab 中文 PDF 渲染
│   ├── grader.py         # Phase 2 评分
│   ├── schemas.py
│   └── config.py
├── fonts/                # 可选：放入 NotoSansCJK-Regular.ttc
└── fixtures/             # 题目材料（rubrics 仅供 Phase 2）
```

## Phase 隔离

| 阶段 | 可读输入 |
|------|---------|
| Phase 1 Agent | 仅 `query.txt` + 附件 PDF（**代码级路径白名单**强制校验） |
| Phase 2 Evaluator | Phase 1 产物 + rubrics.json + query + 附件 |

开发者可在开发阶段阅读 `fixtures/rubrics.json` 设计代码，但 Agent 在 Phase 1 **不能**读取 rubrics——`Phase1ToolContext` 会在运行时拒绝非法路径。

## 输出产物

| 文件 | 说明 |
|------|------|
| `phase1_output.pdf` | Phase 1 正式交付物 |
| `phase1_output.md` | Markdown 源文件（**Phase 2 优先读取**，避免 PDF 反抽乱序） |
| `grading_result.json` | Phase 2 评分结果 |
| `agent_trace.jsonl` | 工具调用审计轨迹（含 step / timestamp / duration_ms） |

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt

# API Key 通过环境变量传入，不要写入代码或提交到 git
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

### 中文字体

`pdf_gen.py` 按以下顺序查找字体：

1. `fonts/NotoSansCJK-Regular.ttc`（项目内，推荐）
2. Linux / macOS / Windows 系统字体

如系统缺少中文字体，请下载 [Noto Sans CJK](https://github.com/googlefonts/noto-cjk) 并放入 `fonts/` 目录。

### 题目材料

将 `query.txt`、附件 PDF、`rubrics.json` 放入 `fixtures/`。若附件为面试方私发材料，请勿提交到公开仓库，README 中保留路径说明即可。

## 评分公式

```
total_score = hard_score + soft_score + optional_score
total_max   = hard_max + soft_max + optional_max
final_score = total_score / total_max × 100
```

其中分母**动态计算**（非硬编码）：

- `hard_max` = rubrics 中 hard_constraints 条数（每条最高 1 分）
- `soft_max` = soft_constraints 条数 × 4
- `optional_max` = optional_constraints 条数（每条最高 1 分）

程序在 Phase 2 结束后强制重算，不信任模型返回的 breakdown 数字。

## Agent 工具链

```
模型决定 read_text(query.txt)     → 白名单校验 → 返回 observation
模型决定 read_pdf(附件)           → 白名单校验 → 返回 observation
模型决定 write_pdf_report(...)    → 写 .md + 渲染 .pdf
```

trace 示例：

```json
{"step": 3, "tool": "write_pdf_report", "path": "phase1_output.pdf", "status": "ok", "duration_ms": 842, "timestamp": "2026-06-15T06:30:00Z"}
```
