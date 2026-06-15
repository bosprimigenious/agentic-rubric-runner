# agentic-rubric-runner

可审计的文档约束型 Agent 流水线：读取任务说明与 PDF 附件，生成结构化中文报告，按 Rubric 自动评分，并输出完整工具调用轨迹。

适用于「给定参考文档 + 明确任务要求 + 结构化评分标准」的文档生成与质量评估场景，例如增长指标方案、研究报告摘要、合规性检查等。

| 项目信息 | |
|----------|--|
| 版本 | 0.4.0 |
| Python | 3.10+（Streamlit Cloud 推荐 3.11） |
| 默认模型 | DeepSeek `deepseek-chat`（OpenAI 兼容 API） |
| 许可证 | MIT |

| 资源 | 链接 |
|------|------|
| 展示页 | https://bosprimigenious.github.io/agentic-rubric-runner/ |
| 源码 | https://github.com/bosprimigenious/agentic-rubric-runner |
| Web 控制台 | 见下方 [Streamlit Cloud 部署](#streamlit-cloud-部署) |

---

## 功能概览

- **Phase 1 — 报告生成**：Agent 通过 Function Calling 依次读取 `query.txt`、PDF 附件，生成 Markdown 报告并渲染为 PDF。
- **Phase 2 — Rubric 评分**：根据 `rubrics.json` 对 Phase 1 产物逐条打分，输出结构化 `grading_result.json`。
- **可审计轨迹**：每一步 LLM 请求与工具调用写入 `agent_trace.jsonl`，支持事后回放与排错。
- **程序重算分数**：`final_score` 由程序按权重公式计算，不直接信任模型给出的总分。
- **双入口**：Typer CLI 与 Streamlit Web 控制台共用同一套 `pipeline` / `agent` / `grader` 后端。
- **分步执行**：支持只跑 Phase 1、只跑 Phase 2，或在 Web 上分步触发。

---

## 工作原理

```mermaid
flowchart TB
    subgraph inputs [输入]
        Q[query.txt]
        P[attachment.pdf]
        R[rubrics.json]
    end

    subgraph phase1 [Phase 1 — Agent]
        T1[read_text]
        T2[read_pdf]
        T3[write_pdf_report]
        T1 --> T2 --> T3
    end

    subgraph phase2 [Phase 2 — Grader]
        G[逐条约束评分]
        S[程序重算 final_score]
        G --> S
    end

    subgraph outputs [输出]
        MD[phase1_output.md]
        PDF[phase1_output.pdf]
        GR[grading_result.json]
        TR[agent_trace.jsonl]
        META[run_meta.json]
    end

    Q --> T1
    P --> T2
    T3 --> MD
    T3 --> PDF
    R --> G
    MD --> G
    PDF --> G
    phase1 --> TR
    phase2 --> GR
    phase1 --> META
    phase2 --> META
```

**Phase 1 约束**

- Agent 只能访问 `query.txt` 与附件 PDF，**不读取** `rubrics.json`（避免评分标准泄露到生成阶段）。
- 必须依次调用 `read_text` → `read_pdf` → `write_pdf_report` 三个工具；缺少任一步会触发错误码 E003。
- 报告内容须覆盖 query 中的全部要求，指标数据须来自 PDF 附件。

**Phase 2 流程**

- 读取 Phase 1 的 Markdown / PDF 与 `rubrics.json`。
- 对 hard / soft / optional 三类约束逐条评分（0 或 1）。
- 用 Pydantic 校验输出结构，缺失条目自动补 0 分。
- 按权重公式重算 `final_score` 并写入结果文件。

---

## 安装

安装 Web 能力需带 `[web]` 额外依赖（Streamlit），否则 `agentic-rubric ui` 不可用。

### 从 GitHub 安装（推荐）

```bash
pip install "agentic-rubric-runner[web] @ git+https://github.com/bosprimigenious/agentic-rubric-runner.git"
```

固定版本：

```bash
pip install "agentic-rubric-runner[web] @ git+https://github.com/bosprimigenious/agentic-rubric-runner.git@v0.4.0"
```

### 全局 CLI（pipx）

```bash
pipx install "agentic-rubric-runner[web] @ git+https://github.com/bosprimigenious/agentic-rubric-runner.git"
```

### 本地开发

```bash
git clone https://github.com/bosprimigenious/agentic-rubric-runner.git
cd agentic-rubric-runner
pip install -e ".[dev,web]"
```

---

## 快速开始

### 1. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
```

PowerShell 临时设置：

```powershell
$env:DEEPSEEK_API_KEY = "sk-..."
```

可选环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | — | DeepSeek API 密钥（CLI 必需） |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容端点 |
| `DEEPSEEK_MODEL` | `deepseek-chat` | 模型名称 |

### 2. 运行完整流水线

仓库自带 `fixtures/` 样例数据，可直接验证：

```bash
agentic-rubric run \
  --query fixtures/query.txt \
  --pdf fixtures/attachment.pdf \
  --rubrics fixtures/rubrics.json
```

输出写入 `outputs/<run_id>/`，包含 PDF、评分 JSON、审计轨迹等。

### 3. 校验评分结果

```bash
agentic-rubric validate outputs/<run_id>/grading_result.json
```

### 4. 查看 Agent 轨迹

```bash
agentic-rubric inspect-trace outputs/<run_id>/agent_trace.jsonl
```

### 5. 启动 Web 控制台

```bash
agentic-rubric ui
# 或
streamlit run app.py
```

---

## CLI 命令参考

| 命令 | 说明 |
|------|------|
| `run` | Phase 1 + Phase 2 完整流水线 |
| `phase1` | 仅生成报告（不读取 rubrics） |
| `grade` | 仅 Phase 2 评分（需已有 Phase 1 产物） |
| `validate` | 校验 `grading_result.json` 结构与分数一致性 |
| `inspect-trace` | 格式化查看 `agent_trace.jsonl` |
| `init` | 在当前目录生成任务模板（query / rubrics 骨架） |
| `ui` | 启动 Streamlit Document Evaluation Console |

**常用选项**

```bash
# 指定输出目录
agentic-rubric run --query q.txt --pdf doc.pdf --rubrics rubrics.json --out outputs/demo

# 分步执行
agentic-rubric phase1 --query q.txt --pdf doc.pdf --out outputs/demo
agentic-rubric grade --rubrics rubrics.json --phase1-md outputs/demo/phase1_output.md --out outputs/demo

# 切换模型
agentic-rubric run ... --model deepseek-chat
```

`solution.py` 为兼容入口，等价于 `agentic-rubric run`。

---

## Web 控制台

**Document Evaluation Console** 提供与 CLI 相同的后端能力，面向非命令行用户：

1. 上传 `query.txt`、PDF 附件、`rubrics.json`
2. 在页面输入 DeepSeek API Key（公开 Demo 不在服务端存储密钥）
3. 分步运行 Phase 1（生成报告）与 Phase 2（Rubric 评分）
4. 在线预览评分摘要，下载 PDF / JSON / trace

本地启动：`agentic-rubric ui` 或 `streamlit run app.py`

### Streamlit Cloud 部署

> 若访问链接提示 “You do not have access” 或返回 404，说明应用尚未在 Streamlit Cloud 创建，或可见性未设为 Public。URL 需在部署成功后从控制台复制。

1. 登录 [share.streamlit.io](https://share.streamlit.io/)（GitHub 账号，需有仓库权限）
2. **Create app**，填写：

| 字段 | 值 |
|------|-----|
| Repository | `bosprimigenious/agentic-rubric-runner` |
| Branch | `main` |
| Main file path | `app.py` |

3. **Advanced settings → Secrets**：留空（公开 Demo，用户页面输入 Key）
4. 点击 **Deploy**，等待构建（约 2–5 分钟）
5. 将应用 Visibility 设为 **Public**，复制分配的真实 URL

**云端构建依赖**

| 文件 | 作用 |
|------|------|
| `requirements.txt` | Python 依赖 |
| `packages.txt` | 系统包 `fonts-noto-cjk`（PDF 中文渲染） |
| `app.py` | Streamlit 入口（注入 `sys.path` 后加载 `aarrr_agent`） |
| `.streamlit/config.toml` | 主题与页面配置 |

**常见构建问题**

| 现象 | 处理 |
|------|------|
| `ModuleNotFoundError: aarrr_agent` | 确认 `main` 含 `aarrr_agent/` 且入口为根目录 `app.py` |
| 中文字体 E006 | 确认根目录 `packages.txt` 含 `fonts-noto-cjk` |
| 需要登录才能访问 | 应用设置中改为 **Public** |

---

## 输入格式

### query.txt

纯文本任务描述，说明期望 Agent 产出的文档类型、结构与覆盖范围。示例见 `fixtures/query.txt`。

### attachment.pdf

参考文档。Agent 在 Phase 1 中通过 `read_pdf` 提取文本；评分阶段也会读取 PDF 以核对事实引用。

### rubrics.json

结构化评分标准，顶层字段：

```json
{
  "rubric_summary": "评分标准总体说明",
  "rubric": {
    "hard_constraints": [ ... ],
    "soft_constraints": [ ... ],
    "optional_constraints": [ ... ]
  }
}
```

每条约束包含：

| 字段 | 说明 |
|------|------|
| `description` | 约束描述 |
| `score_0` / `score_1` | 0 分与 1 分的判定标准 |
| `needs_reference` | 是否需对照 PDF 事实（`"是"` / `"否"`） |
| `reference_facts` | 参考事实摘要（`needs_reference` 为是时使用） |
| `fact_source` | 事实出处（页码或章节） |

评分项 ID 规则：硬约束 `H01`…、软约束 `S01`…、可选约束 `O01`…

---

## 输出格式

默认输出目录：`outputs/<run_id>/`（`run_id` 格式 `YYYYMMDD_HHMMSS`）

| 文件 | 说明 |
|------|------|
| `phase1_output.md` | Agent 生成的 Markdown 报告 |
| `phase1_output.pdf` | ReportLab 渲染的 PDF |
| `grading_result.json` | Phase 2 评分结果（含逐条 reason） |
| `agent_trace.jsonl` | 每行一条 JSON，记录 LLM 与工具调用 |
| `run_meta.json` | 运行元数据（耗时、输入哈希、模型、状态） |

`grading_result.json` 主要字段：

```json
{
  "final_score": 93.5,
  "score_breakdown": {
    "hard_score": 10, "hard_max": 10,
    "soft_score": 8, "soft_max": 9,
    "optional_score": 2, "optional_max": 3
  },
  "hard_constraints": [{ "id": "H01", "score": 1, "reason": "..." }],
  "soft_constraints": [...],
  "optional_constraints": [...]
}
```

---

## 评分公式

三类约束按权重折算为 0–100 分，分母从 `rubrics.json` 动态计算：

```
final_score =
  (hard_score / hard_max) × 50
+ (soft_score / soft_max) × 30
+ (optional_score / optional_max) × 20
```

- **硬约束**（hard）：必须满足的核心要求，权重 50%
- **软约束**（soft）：质量区分项，权重 30%
- **可选约束**（optional）：加分项，权重 20%

若某一类约束在 rubrics 中为空，对应项不参与计算（动态调整有效分母）。程序在写入前强制重算 `final_score`，与模型原始输出不一致时以程序结果为准。

---

## 错误码

| 代码 | 含义 | 常见原因 |
|------|------|----------|
| E001 | API 失败或缺少 Key | 未设置 `DEEPSEEK_API_KEY` 或网络 / 配额问题 |
| E002 | PDF 无文本 | 扫描件或未提取到可解析文本 |
| E003 | Agent 未调用必要工具 | 跳过 `read_text` / `read_pdf` / `write_pdf_report` |
| E004 | 报告可能不完整 | 章节缺失等警告（不中断流水线） |
| E005 | 评分 JSON 无效 | Phase 2 输出无法通过 Pydantic 校验 |
| E006 | 中文字体缺失 | 本地或云端未安装 CJK 字体 |

---

## 项目结构

```
agentic-rubric-runner/
├── aarrr_agent/              # 核心 Python 包
│   ├── agent.py              # Phase 1 Agent 工具循环
│   ├── grader.py             # Phase 2 Rubric 评分
│   ├── pipeline.py           # 双阶段编排与输出路径
│   ├── tools.py              # read_text / read_pdf / write_pdf_report
│   ├── pdf_gen.py            # ReportLab PDF 渲染
│   ├── cli.py                # Typer CLI
│   ├── web_app.py            # Streamlit UI
│   ├── schemas.py            # Pydantic 数据模型
│   ├── validation.py         # 评分结果校验
│   └── ...
├── app.py                    # Streamlit Cloud 入口
├── solution.py               # run 兼容入口
├── fixtures/                 # 样例 query / PDF / rubrics
├── docs/                     # GitHub Pages 静态站
├── tests/                    # pytest 测试套件
├── .github/workflows/        # CI、Pages、PyPI 发布
├── requirements.txt            # Streamlit Cloud 依赖清单
├── packages.txt                # 云端系统字体包
└── pyproject.toml
```

---

## 开发与测试

```bash
# 运行测试（当前 18 项）
pytest -q

# 打包 wheel
python -m build

# 代码格式化（dev 依赖）
ruff check aarrr_agent tests
black aarrr_agent tests
```

**CI/CD（GitHub Actions）**

| Workflow | 触发 | 作用 |
|----------|------|------|
| `ci.yml` | push / PR | pytest + 构建检查 |
| `pages.yml` | push `main` | 部署 GitHub Pages 展示页 |
| `publish.yml` | 推送 `v*` tag | 发布到 PyPI |

---

## 安全说明

- 勿将 `.env` 或真实 API Key 提交到版本库。
- Web 公开 Demo 由用户在浏览器输入 Key，不在 Streamlit Secrets 中存储。
- `fixtures/` 为演示材料；生产环境请替换为自有文档与评分标准。
- Agent 工具层对文件路径有白名单校验，限制可读文件范围。

---

## License

MIT — 详见 [LICENSE](LICENSE)。
