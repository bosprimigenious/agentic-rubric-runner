# PDF 中文字体

仓库内置 `msyh.ttc`（微软雅黑），供 ReportLab 渲染 Phase 1 PDF 使用。

- **本地 / Streamlit Cloud**：优先加载本目录字体，不依赖系统路径。
- **Linux 云端备选**：若未打包字体，会尝试 `/usr/share/fonts` 下的 Noto CJK（`packages.txt` 中 `fonts-noto-cjk`）。
