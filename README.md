# agentic-rubric-runner

**输入文档 + 评分标准 → Agent 生成报告 → 自动评分 → 输出结果**

适用于尽职调查审核、合规检查、提案评审、内容质量把关等文档评估场景。

- **Phase 1**：自实现 function calling tool-use loop（模型自主决定调用工具）
- **Phase 2**：严格 evaluator + Pydantic 校验 + 程序重算分数

## 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.10+ |
| 模型接口 | openai SDK（兼容 DeepSeek） |
| Agent 机制 | 自实现 tool-use loop |
| CLI | Typer + Rich |
| Web UI | Streamlit（可选） |
| PDF 读取 | PyMuPDF |
| PDF 生成 | ReportLab + NotoSansCJK / 系统字体 |
| JSON 校验 | Pydantic v2 |
| 审计轨迹 | agent_trace.jsonl |

不使用 LangGraph、LangChain、CrewAI、WeasyPrint。

## 安装

```bash
# 开发安装（推荐）
pip install -e .

# 含 Streamlit 界面
pip install -e ".[web]"

# 仅依赖文件安装
pip install -r requirements.txt
```

## CLI 用法

```bash
export DEEPSEEK_API_KEY="your_key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"

# 完整双阶段流水线
aarrr-agent run \
  --query fixtures/query.txt \
  --pdf fixtures/attachment.pdf \
  --rubrics fixtures/rubrics.json

# 仅 Phase 1
aarrr-agent run --query fixtures/query.txt --pdf fixtures/attachment.pdf \
  --rubrics fixtures/rubrics.json --skip-phase2

# 单独 Phase 2 评分
aarrr-agent grade \
  --phase1 phase1_output.pdf \
  --rubrics fixtures/rubrics.json \
  --query fixtures/query.txt \
  --attachment fixtures/attachment.pdf

# 校验评分结果
aarrr-agent validate grading_result.json

aarrr-agent --help
```

向后兼容：`python solution.py` 仍可用（转发到 CLI）。

## Streamlit 界面

```bash
pip install -e ".[web]"
streamlit run app.py
```

部署 Streamlit Cloud：Main file 填 `app.py`，Secrets 设置 `DEEPSEEK_API_KEY`。

## 项目结构

```
agentic-rubric-runner/
├── pyproject.toml
├── app.py                  # Streamlit 界面
├── aarrr_agent/
│   ├── cli.py              # Typer CLI
│   ├── agent.py            # Phase 1 tool-use loop
│   ├── tools.py
│   ├── grader.py
│   ├── errors.py           # E001/E002/E003
│   └── ...
├── fonts/
└── fixtures/
```

## Phase 隔离

| 阶段 | 可读输入 |
|------|---------|
| Phase 1 Agent | 仅 `query.txt` + 附件 PDF（代码级路径白名单） |
| Phase 2 Evaluator | Phase 1 产物 + rubrics.json + query + 附件 |

## 输出产物

| 文件 | 说明 |
|------|------|
| `phase1_output.pdf` | Phase 1 正式交付物 |
| `phase1_output.md` | Markdown 源（Phase 2 优先读取） |
| `grading_result.json` | Phase 2 评分结果 |
| `agent_trace.jsonl` | 工具调用审计轨迹 |

## 评分公式

```
total_score = hard_score + soft_score + optional_score
total_max   = hard_max + soft_max + optional_max
final_score = total_score / total_max × 100
```

分母从 `rubrics.json` **动态计算**（非硬编码 15/24/3）。程序强制重算，不信任模型 breakdown。

## 错误码

| 代码 | 含义 |
|------|------|
| E001 | API 调用失败 / 超时 |
| E002 | PDF 抽取无文本 |
| E003 | 评分 JSON 校验失败 |

## 中文字体

将 `NotoSansCJK-Regular.ttc` 放入 `fonts/`，或依赖系统字体（Windows 微软雅黑等）。

## Agent 工具链

```
read_text(query) → read_pdf(附件) → write_pdf_report → .md + .pdf
```

trace 含 `step`、`timestamp`、`duration_ms`。
