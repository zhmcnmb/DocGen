# DocGen Agent

基于 LLM 的文档生成工具。读取多格式源文件（Word/PDF/Excel/Markdown），按自定义模板交互式生成结构化文档。

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env   # 编辑 OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
python docgen.py       # 启动后打开 http://localhost:5000
```

## 工作流程

1. **上传** — 拖拽上传模板文件和源文件，填写需求描述
2. **确认** — 查看解析出的章节结构，确认理解正确
3. **提取** — LLM 根据章节描述从源文件提取素材
4. **生成** — 逐章节实时生成文档内容（SSE 流式输出）
5. **审阅** — 逐章修改或全局修改，下载最终文档

## 支持的源文件格式

| 格式 | 依赖 |
|------|------|
| .docx | python-docx |
| .pdf  | pdfplumber |
| .xlsx | openpyxl |
| .md / .txt | 内置 |

## 配置

通过 `.env` 文件配置：

```
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your-key
OPENAI_MODEL=gpt-4o
```

支持任何 OpenAI 兼容 API（可配置 `OPENAI_BASE_URL` 指向本地模型或第三方服务）。

## 项目结构

```
docgen/
  config.py          配置管理
  template.py        模板解析
  parsers/           多格式文件解析
  llm.py             LLM 交互（同步 + 流式）
  session.py         会话持久化与恢复
  stream_bridge.py   SSE 事件桥接
  api.py             Flask REST API
frontend/
  index.html         前端 SPA
  css/style.css
  js/app.js
docgen.py            入口
```

## 会话持久化

所有中间产物保存在 `sessions/{session-id}/` 目录，包括模板结构、素材池、各章节内容和摘要。中断后可恢复。
