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
| Web 控制台 | https://agentic-rubric-runner.streamlit.app/（可选演示层） |

**产品入口**

| 层级 | 入口 | 说明 |
|------|------|------|
| **Primary — CLI** | `agentic-rubric` | 核心产品：本地运行、批处理、可复现评审、CI 集成 |
| **Optional — Web UI** | `agentic-rubric ui` / Streamlit | 可选演示层：在线体验与面试展示，需额外安装 `[web]` |

CLI 是本项目的核心入口；Streamlit Web 控制台与 CLI 共用同一套 `pipeline` / `agent` / `grader` 后端，但不属于默认安装依赖。

---

## 功能概览

- **Phase 1 — 报告生成**：Agent 通过 Function Calling 依次读取 `query.txt`、PDF 附件，生成 Markdown 报告；程序解析固定章节后套入管理层 HTML/CSS 模板，导出 PDF（WeasyPrint，失败回退 ReportLab），同时保留 `.md` / `.html` 供审计与预览。
- **Phase 2 — Rubric 评分**：根据 `rubrics.json` 对 Phase 1 产物逐条打分，输出结构化 `grading_result.json`。
- **可审计轨迹**：每一步 LLM 请求与工具调用写入 `agent_trace.jsonl`，支持事后回放与排错。
- **程序重算分数**：`final_score` 由程序按权重公式计算，不直接信任模型给出的总分。
- **双入口**：Typer CLI（核心）与 Streamlit Web 控制台（可选）共用同一套 `pipeline` / `agent` / `grader` 后端。
- **分步执行**：支持只跑 Phase 1、只跑 Phase 2，或在 Web 上分步触发。

---

## 架构

CLI、Web 与 `solution.py` 共用同一套 `pipeline` / `agent` / `grader` 后端，不通过子进程调脚本。

```mermaid
flowchart TB
    subgraph entry [入口层]
        CLI["agentic-rubric CLI<br/>run · phase1 · grade · validate · ui"]
        WEB["Streamlit Console<br/>aarrr_agent/web_app.py"]
        SOL[solution.py]
    end

    subgraph core [核心层 aarrr_agent]
        PL["pipeline.py<br/>路径解析 · run_meta · 双阶段编排"]

        subgraph phase1 [Phase 1 — agent.py + 状态机]
            direction LR
            T1[read_text] --> T2[read_pdf] --> T3[extract_evidence_pack]
            T3 --> T4[self_check_report]
            T4 --> T5[write_structured_report]
        end

        subgraph phase2 [Phase 2 — grader.py]
            direction LR
            G0[检索式选页] --> G1[证据化评分] --> G2[附件门控/校准] --> G3[程序重算 final_score]
        end

        PL --> phase1
        PL --> phase2
    end

    subgraph inputs [输入]
        Q[query.txt]
        P[attachment.pdf]
        R[rubrics.json]
    end

    subgraph outputs [输出]
        MD[phase1_output.md]
        HTML[phase1_output.html]
        PDF[phase1_output.pdf]
        GR[grading_result.json]
        GRPT[grading_report.md/html]
        EV[evidence_pack.json]
        TR[agent_trace.jsonl]
        META[run_meta.json]
    end

    CLI --> PL
    WEB --> PL
    SOL --> CLI

    Q --> T1
    P --> T2
    T3 --> EV
    R --> G0
    T5 --> MD
    T5 --> HTML
    T5 --> PDF
    MD --> G1
    PDF --> G1
    G3 --> GR
    G3 --> GRPT
    phase1 --> TR
    PL --> META
    phase2 --> META
```

| 层 | 模块 | 职责 |
|----|------|------|
| **入口** | `cli.py` | `run` / `phase1` / `grade` / `validate` / `inspect-trace` / `init` / `ui` |
| **入口** | `web_app.py` | 分步调用 `run_phase1_pipeline` + `run_phase2_pipeline` |
| **编排** | `pipeline.py` | 输出路径、`run_meta`、Phase 1 / 2 串联 |
| **Phase 1** | `agent.py` + `phase1_state.py` | 状态机约束工具顺序：`read_text` → `read_pdf` → `extract_evidence_pack` → `write_structured_report` |
| **Phase 2** | `grader.py` + `attachment_relevance.py` | 检索式选页、证据化评分、附件门控、程序重算 `final_score` |
| **工具** | `tools.py` / `evidence.py` / `structured_report.py` | 证据包、结构化报告、HTML/PDF 渲染 |

**Phase 1 约束**

- Agent 只能访问 `query.txt` 与附件 PDF，**不读取** `rubrics.json`（避免评分标准泄露到生成阶段）。
- 状态机强制工具顺序；`write` 之后禁止再调工具；须输出 `PHASE1_DONE`。
- 报告关键事实须引用证据编号 `[E01]`，证据来自 `evidence_pack.json`。

**Phase 2 流程**

- 读取 Phase 1 产物（Markdown / PDF）与 `rubrics.json`。
- 检索式选取附件相关页（非简单截断）；每项输出 `evidence` / `missing`。
- 附件领域不匹配时程序门控压低分数；`final_score` 由程序重算。

---

## 安装

默认安装仅包含 **CLI 核心依赖**（`run` / `phase1` / `grade` / `validate` / `inspect-trace` 等完整可用）。如需 Streamlit Web UI，请额外安装 `[web]` extra。

### 从 GitHub 安装（推荐）

```bash
pip install "git+https://github.com/bosprimigenious/agentic-rubric-runner.git"
```

固定版本：

```bash
pip install "agentic-rubric-runner @ git+https://github.com/bosprimigenious/agentic-rubric-runner.git@v0.4.0"
```

### 可选：Web UI

```bash
pip install "agentic-rubric-runner[web] @ git+https://github.com/bosprimigenious/agentic-rubric-runner.git"
```

安装后可运行 `agentic-rubric ui` 或 `streamlit run app.py`。

### 全局 CLI（pipx）

```bash
pipx install "git+https://github.com/bosprimigenious/agentic-rubric-runner.git"
```

需要 Web 时：

```bash
pipx install "agentic-rubric-runner[web] @ git+https://github.com/bosprimigenious/agentic-rubric-runner.git"
```

### 本地开发

```bash
git clone https://github.com/bosprimigenious/agentic-rubric-runner.git
cd agentic-rubric-runner
pip install -e ".[dev]"          # CLI + 测试工具
pip install -e ".[dev,web]"      # 含 Streamlit Web UI
```

### 依赖清单文件说明

| 文件 | 用途 |
|------|------|
| `requirements.txt` | CLI / 核心运行时（**不是** Streamlit Cloud 默认文件） |
| `requirements-web.txt` | 核心 + Streamlit（本地 Web 开发） |
| `requirements-streamlit.txt` | Streamlit Cloud 部署专用（指向 `requirements-web.txt`） |

安装 CLI 请使用 `pip install .` 或 `pip install -e .`，不要直接 `pip install -r requirements.txt` 后再误以为已包含 Web。

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
| `PDF_RENDERER` | `auto` | PDF 渲染器：`auto`（WeasyPrint → ReportLab）、`html`、`reportlab` |

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

### 5. 启动 Web 控制台（可选，需 `[web]`）

```bash
pip install -e ".[web]"   # 若尚未安装 Web 依赖
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
| `ui` | 启动 Streamlit 文档评审控制台（需 `[web]` extra） |

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

**在线体验：** [agentic-rubric-runner.streamlit.app](https://agentic-rubric-runner.streamlit.app/)

**文档评审控制台** 提供与 CLI 相同的后端能力：

1. 上传 `query.txt`、PDF 附件、`rubrics.json`
2. 在页面输入 DeepSeek API Key（密钥仅存于当前会话）
3. 运行 Phase 1（报告生成）与 Phase 2（Rubric 评分）
4. 查看评分摘要，下载 PDF / JSON / 审计轨迹（下载不触发重新运行）

本地启动：`agentic-rubric ui` 或 `streamlit run app.py`

### Streamlit Cloud 部署与排错

应用地址：[https://agentic-rubric-runner.streamlit.app/](https://agentic-rubric-runner.streamlit.app/)

应用已创建后，若页面**空白 / 只有灰色背景 / 看不见内容**，按下面顺序排查（多数情况是云端配置未更新，而非代码未部署）：

#### 第一步：核对 Streamlit Cloud 应用设置

在 [share.streamlit.io](https://share.streamlit.io/) 打开你的应用 → 右下角 **Manage app** → **Settings**：

你贴的是 **General** 标签。白屏还需要检查 **Sharing** 标签：

| 设置项 | 正确值 |
|--------|--------|
| **Sharing → Who can view this app** | **This app is public and searchable** |

**General 标签（你已打开）：**

| 设置项 | 正确值 |
|--------|--------|
| Main file path | `app.py` |
| Requirements file | `requirements-streamlit.txt` |
| Python version | **3.11**（**不要选 3.14**，当前日志显示 3.14.6 可能导致白屏） |

> **已部署但整页空白 / 控制台报 `Unable to preload CSS`：** 多半是应用仍为 **Private**（仅工作区成员可访问）。此时静态资源会 303 跳转到 `share.streamlit.io/-/auth/app`，浏览器加载不了 CSS/JS，页面只剩灰色壳子。  
> **处理：** Settings → **Visibility → Public** → Save → **Clear cache and redeploy**。

改完后点击 **Save**，再点 **Clear cache and redeploy**（或 **Reboot app**），等待 2–5 分钟，浏览器 **Ctrl+Shift+R** 硬刷新。

#### 第二步：看构建日志

**Manage app** → **Logs**，确认末尾有 `Processed dependencies!` 且无红色报错。常见错误：

| 日志关键词 | 处理 |
|------------|------|
| `ModuleNotFoundError: aarrr_agent` | Requirements file 填错或 `main` 未拉到最新代码 → 改为 `requirements-streamlit.txt` 并 redeploy |
| `No such file: requirements-streamlit.txt` | 拉取最新 `main`，或改用 `requirements-web.txt` |
| `apt install` 失败 / `libgdk-pixbuf` | 勿在 `packages.txt` 添加易随 Debian 版本变化的 WeasyPrint 系统包；仅保留 `fonts-noto-cjk` |
| `pip install` 失败 | 检查 Python 版本是否为 3.11 |

#### 第三步：区分浏览器警告与真实故障

控制台里 `Unrecognized feature: 'battery'` / `'vr'` 等是 Chrome 对 Streamlit iframe 的**无害警告**，可忽略。

若出现 `Unable to preload CSS` 或整页只有灰色背景：在 Streamlit 控制台 **Reboot app**；仍不行则 **Delete app → 用同样配置重新 Create app**。

#### 首次部署步骤（新建应用时）

1. 登录 [share.streamlit.io](https://share.streamlit.io/)（GitHub 账号）
2. **Create app** → Repository: `bosprimigenious/agentic-rubric-runner`，Branch: `main`，Main file: `app.py`
3. Advanced → Requirements file: `requirements-streamlit.txt`；Secrets **留空**（用户在页面输入 API Key）
4. **Deploy** → Visibility 设为 **Public**

**云端构建依赖**

| 文件 | 作用 |
|------|------|
| `requirements.txt` | CLI / 核心 Python 依赖 |
| `requirements-web.txt` | 核心 + Streamlit（本地 Web） |
| `requirements-streamlit.txt` | Streamlit Cloud 部署入口（推荐填此项） |
| `packages.txt` | 系统包：仅 `fonts-noto-cjk`（PDF 在云端走 ReportLab 回退，不装 WeasyPrint 系统依赖） |
| `app.py` | Streamlit 入口 |
| `.streamlit/config.toml` | 主题配置 |

**运行时错误码（应用内）**

| 代码 | 含义 |
|------|------|
| E006 | 中文字体缺失 → 确认 `packages.txt` 含 `fonts-noto-cjk` |
| E001 | 未输入 API Key 或 API 调用失败 |

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
| `phase1_output.html` | 管理层 HTML 模板渲染（可直接浏览器打开） |
| `phase1_output.pdf` | WeasyPrint 导出 PDF（失败时回退 ReportLab） |
| `grading_result.json` | Phase 2 评分结果（含逐条 reason） |
| `grading_report.md` | 评审报告（管理层摘要、缺口、改进建议） |
| `grading_report.html` | 评审报告 HTML 版（可直接浏览器打开） |
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
│   ├── grading_report.py     # 评审报告、总评清洗、管理层摘要
│   ├── pipeline.py           # 双阶段编排与输出路径
│   ├── tools.py              # read_text / read_pdf / write_pdf_report
│   ├── html_report.py        # Jinja2 管理层 HTML 模板
│   ├── html_pdf.py           # WeasyPrint PDF + ReportLab fallback
│   ├── md_report_parser.py   # Markdown → 结构化报告
│   ├── pdf_gen.py            # ReportLab PDF 渲染（fallback）
│   ├── templates/            # executive_report.html
│   ├── assets/               # executive_report.css
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
├── requirements.txt            # CLI / 核心依赖
├── requirements-web.txt        # 核心 + Streamlit
├── requirements-streamlit.txt  # Streamlit Cloud 部署
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
- Web 控制台由用户在浏览器输入 Key，不在 Streamlit Secrets 中存储。
- `fixtures/` 为演示材料；生产环境请替换为自有文档与评分标准。
- Agent 工具层对文件路径有白名单校验，限制可读文件范围。

---

## License

MIT — 详见 [LICENSE](LICENSE)。
