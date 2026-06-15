# agentic-rubric-runner

**轻量、可审计的文档约束型 Agent 工作流**：输入任务说明 + PDF 附件 + 评分标准 → Agent 生成 PDF 报告 → Evaluator 自动评分 → 输出 JSON + 审计 trace。

```
agentic-rubric-runner
├── 可作为面试题 solution.py 一键运行
├── 可作为 pip/pipx 安装的 CLI 工具
├── 可作为 Streamlit Web App 上传文件运行
├── 可通过 GitHub Actions 自动测试、打包、发布
└── 保留 agent_trace.jsonl 审计能力
```

## 版本路线

| 版本 | 能力 |
|------|------|
| V0.1 | `solution.py` 面试题交付 |
| V0.2 | 路径白名单、trace、API 重试、.md 优先评分、章节完整性检查 |
| V0.3 | `pip install` + `agentic-rubric` CLI + 加权评分 |
| V0.4 | Streamlit Web UI |

## 安装

```bash
pip install agentic-rubric-runner          # PyPI（tag 发布后）
pip install -e .                           # 开发安装
pip install -e ".[web]"                    # 含 Streamlit
pip install -e ".[dev,web]"                # 含 pytest / ruff / build
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

`solution.py` 自动转发到 `agentic-rubric run ...`，满足题目交付要求。

### 2. CLI 工具模式（推荐）

```bash
# 完整流水线（默认输出到 outputs/<run_id>/，不覆盖历史）
agentic-rubric run \
  --query fixtures/query.txt \
  --pdf fixtures/attachment.pdf \
  --rubrics fixtures/rubrics.json

# 指定输出目录
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

网页上传 `query.txt`、`attachment.pdf`、`rubrics.json`，点击 Run，下载 PDF / JSON / trace。

## 输出产物

```
outputs/20260615_153000/
├── phase1_output.pdf
├── phase1_output.md
├── grading_result.json
├── agent_trace.jsonl
└── run_meta.json          # run_id + input sha256 + 耗时
```

## 评分公式

`hard_max`、`soft_max`、`optional_max` 从 `rubrics.json` **动态计算**（不写死 15/24/3）。程序强制重算，不信任模型 breakdown。

```
final_score =
  (hard_score / hard_max) × 50
+ (soft_score / soft_max) × 30
+ (optional_score / optional_max) × 20
```

其中 `soft_max = soft 条数 × 4`。

## 企业级特性

- **可审计**：`agent_trace.jsonl` 含 step / timestamp / duration_ms / args_preview（长 content 截断 120 字）
- **工具沙箱**：Phase 1 仅可读 query + 附件 PDF，禁止读 rubrics
- **确定性校验**：Pydantic + 分数重算 + 缺失项补 0
- **run 元数据**：`run_meta.json` 含 input hash，便于复现对比
- **API 韧性**：超时 + 重试；Phase 1 失败时保存 `agent_trace_emergency.jsonl`
- **报告完整性**：15 个关键词 + 最短长度检查（E004 警告）

## 错误码

| 代码 | 含义 |
|------|------|
| E001 | LLM/API 失败或缺少 API Key |
| E002 | PDF 抽取无文本 |
| E003 | Agent 未调用必要工具 |
| E004 | 报告内容不完整（警告，非致命） |
| E005 | Grading JSON 校验失败 |
| E006 | 中文字体未找到 |
| E006 | 中文字体未找到 |

## 测试与构建

```bash
pytest -q
python -m build
pip install dist/agentic_rubric_runner-*.whl
agentic-rubric --help
```

CI：`.github/workflows/ci.yml`（push 自动 pytest + 打包 artifact）

发布：打 tag `v*` 触发 `.github/workflows/publish.yml`（PyPI）

## 环境变量

复制 `.env.example` 为 `.env`（勿提交）：

```
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

CLI 与 Streamlit 启动时自动加载项目根目录 `.env`。

## 项目结构

```
aarrr_agent/
├── agent.py        # Phase 1 tool-use 循环
├── grader.py       # Phase 2 Rubric 评分
├── tools.py        # read_text / read_pdf / write_pdf_report + trace
├── pipeline.py     # 共享流水线 + run_meta
├── cli.py          # Typer CLI
├── llm.py          # API 超时重试
├── validation.py   # 报告关键词检查
└── pdf_gen.py      # Markdown → PDF
app.py              # Streamlit UI
solution.py         # 面试题兼容入口
fixtures/           # 题目样例材料
tests/              # pytest
```

## License

MIT
