# agentic-rubric-runner

**轻量、可审计的文档约束型 Agent 工作流**：输入任务说明 + PDF 附件 + 评分标准 → Agent 生成 PDF 报告 → Evaluator 自动评分 → 输出 JSON + 审计 trace。

适用场景：尽职调查审核、合规检查、提案评审、内容质量把关。

## 版本路线

| 版本 | 能力 |
|------|------|
| V0.1 | `solution.py` 面试题交付 |
| V0.2 | 路径白名单、trace、API 重试、.md 优先评分、章节完整性检查 |
| V0.3 | `pip install` + `agentic-rubric` CLI |
| V0.4 | Streamlit Web UI |

## 安装

```bash
pip install -e .              # 开发安装
pip install -e ".[web]"       # 含 Streamlit
pip install -e ".[dev]"       # 含 pytest / ruff
```

## 三种运行方式

### 1. 面试题模式（保留）

```bash
export DEEPSEEK_API_KEY="your_key"

python solution.py \
  --query fixtures/query.txt \
  --pdf fixtures/attachment.pdf \
  --rubrics fixtures/rubrics.json
```

### 2. CLI 工具模式（推荐）

```bash
# 完整流水线，输出到目录
agentic-rubric run \
  --query fixtures/query.txt \
  --pdf fixtures/attachment.pdf \
  --rubrics fixtures/rubrics.json \
  --out outputs/demo

# 仅 Phase 2
agentic-rubric grade \
  --phase1 outputs/demo/phase1_output.pdf \
  --query fixtures/query.txt \
  --attachment fixtures/attachment.pdf \
  --rubrics fixtures/rubrics.json

agentic-rubric validate outputs/demo/grading_result.json
agentic-rubric inspect-trace outputs/demo/agent_trace.jsonl
agentic-rubric init my-task
agentic-rubric ui
```

别名：`aarrr-agent` 与 `agentic-rubric` 等价。

### 3. Web UI

```bash
pip install -e ".[web]"
streamlit run app.py
# 或
agentic-rubric ui
```

## 输出产物

```
outputs/demo/
├── phase1_output.pdf
├── phase1_output.md
├── grading_result.json
├── agent_trace.jsonl
└── run_meta.json          # run_id + input sha256 + 耗时
```

## 评分公式

```
final_score = (hard_score + soft_score + optional_score)
            / (hard_max + soft_max + optional_max) × 100
```

`hard_max` / `soft_max` / `optional_max` 从 `rubrics.json` 动态计算。程序强制重算，不信任模型 breakdown。

## 企业级特性（已实现）

- **可审计**：`agent_trace.jsonl` 含 step / timestamp / duration_ms
- **工具沙箱**：Phase 1 仅可读 query + 附件 PDF
- **确定性校验**：Pydantic + 分数重算 + 缺失项补 0
- **run 元数据**：`run_meta.json` 含 input hash，便于复现对比

## 错误码

| 代码 | 含义 |
|------|------|
| E001 | LLM/API 失败或缺少 API Key |
| E002 | PDF 抽取无文本 |
| E003 | Agent 未调用必要工具 |
| E005 | Grading JSON 校验失败 |

## 测试

```bash
pytest -q
python -m build
```

CI：`.github/workflows/ci.yml`（push 自动测试 + 打包 artifact）

## 环境变量

复制 `.env.example` 为 `.env`（勿提交）：

```
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

## 技术栈

Python 3.10+ · OpenAI SDK · DeepSeek · PyMuPDF · ReportLab · Pydantic v2 · Typer · Rich · Streamlit

不使用 LangGraph / LangChain / WeasyPrint。
