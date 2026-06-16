# Streamlit Cloud Deployment

本页记录 Streamlit Cloud 部署与排错步骤。README 只保留 Web 控制台入口；云端配置、白屏排查和构建日志问题统一放在这里。

## 应用地址

[https://agentic-rubric-runner.streamlit.app/](https://agentic-rubric-runner.streamlit.app/)

## 首次部署

1. 登录 [share.streamlit.io](https://share.streamlit.io/)（GitHub 账号）。
2. **Create app**。
3. Repository: `bosprimigenious/agentic-rubric-runner`。
4. Branch: `main`。
5. Main file: `app.py`。
6. Advanced → Requirements file: `requirements-streamlit.txt`。
7. Secrets 留空；用户在页面输入 API Key。
8. Deploy 后将 Visibility 设为 Public。

## 推荐设置

### Sharing / Visibility

| 设置项 | 正确值 |
|--------|--------|
| Sharing → Who can view this app | This app is public and searchable |

### General

| 设置项 | 正确值 |
|--------|--------|
| Main file path | `app.py` |
| Requirements file | `requirements-streamlit.txt` |
| Python version | 3.11 |

不要选 Python 3.14。Streamlit Cloud 上 3.14 可能带来依赖或运行时兼容问题。

## 白屏排查

应用已创建后，如果页面空白、只有灰色背景、看不见内容，通常是云端配置或权限问题，而不是代码没有部署。

### 1. 检查是否为 Public

如果浏览器控制台出现 `Unable to preload CSS`，常见原因是应用仍为 Private。此时静态资源可能会 303 跳转到 `share.streamlit.io/-/auth/app`，浏览器无法加载 CSS/JS，页面只剩灰色外壳。

处理方式：

1. 打开 Streamlit Cloud → Manage app → Settings。
2. Visibility / Sharing 设置为 Public。
3. Save。
4. Clear cache and redeploy，或 Reboot app。
5. 等待 2-5 分钟后，浏览器使用 Ctrl+Shift+R 硬刷新。

### 2. 检查构建日志

Manage app → Logs，确认末尾有 `Processed dependencies!` 且无红色报错。

| 日志关键词 | 处理 |
|------------|------|
| `ModuleNotFoundError: aarrr_agent` | Requirements file 填错或 `main` 未拉到最新代码；改为 `requirements-streamlit.txt` 并 redeploy |
| `No such file: requirements-streamlit.txt` | 拉取最新 `main`，或临时改用 `requirements-web.txt` |
| `apt install` 失败 / `libgdk-pixbuf` | 不要在 `packages.txt` 添加易随 Debian 版本变化的 WeasyPrint 系统包；仅保留 `fonts-noto-cjk` |
| `pip install` 失败 | 检查 Python 版本是否为 3.11 |

### 3. 区分浏览器警告与真实故障

Chrome 控制台里的 `Unrecognized feature: 'battery'`、`'vr'` 等通常是 Streamlit iframe 的无害警告，可以忽略。

真正需要处理的是：

- `Unable to preload CSS`
- 整页灰色背景
- 构建日志中有 Python import error
- 页面反复重启

## 云端依赖文件

| 文件 | 作用 |
|------|------|
| `requirements.txt` | CLI / 核心 Python 依赖 |
| `requirements-web.txt` | 核心 + Streamlit，本地 Web 开发 |
| `requirements-streamlit.txt` | Streamlit Cloud 部署入口，推荐填此项 |
| `packages.txt` | 系统包；仅 `fonts-noto-cjk` |
| `app.py` | Streamlit 入口 |
| `.streamlit/config.toml` | Streamlit 主题配置 |

## 应用内错误码

| 代码 | 含义 | 处理 |
|------|------|------|
| E001 | 未输入 API Key 或 API 调用失败 | 检查页面输入的 Key、额度、网络与模型端点 |
| E006 | 中文字体缺失 | 确认 `packages.txt` 含 `fonts-noto-cjk` 并重新部署 |

