# PaperExtractor

批量解析学术论文 PDF 和少量 DOCX，调用可切换的 OpenAI 兼容 LLM 抽取
11 个结构化字段，并提供批量容错、SQLite 持久化、Excel/JSON 导出、FastAPI、
Streamlit 和可量化评测。

## 项目解决的问题

人工整理一篇论文的方法、数据集和指标通常需要约15分钟。PaperExtractor 的
目标是把几十篇论文的对比整理从数小时压缩到几分钟，同时保留失败诊断、重试
记录和准确率评测，不把 LLM 输出当作天然正确的数据。

## 当前进度

- [x] M0：环境与项目骨架
- [ ] M1：PDF / DOCX 文档解析
- [ ] M2：LLM 客户端与 Prompt
- [ ] M3：三级容错抽取器
- [ ] M4：批量调度
- [ ] M5：SQLite 持久化
- [ ] M6：Excel / JSON 导出
- [ ] M7：FastAPI
- [ ] M8：Streamlit
- [ ] M9：准确率评测

当前只完成 M0，不包含尚未验收模块的业务实现。

## Windows 快速开始

安装 `uv` 后，在项目目录执行：

```powershell
uv sync
uv run python hello.py
```

预期输出：

```text
PaperExtractor 环境准备完成
Python version: 3.11.x
```

详细解释见 [`docs/notes/M0_环境与骨架.md`](docs/notes/M0_环境与骨架.md)。

## 11 个目标字段

1. `title`
2. `authors`
3. `year`
4. `venue`
5. `doc_type`
6. `problem`
7. `method_name`
8. `datasets`
9. `main_results`
10. `limitations`
11. `summary`

正式 Schema 将在 M1 的 `app/models.py` 中实现，并在后续由 LLM 输出校验、
FastAPI 响应模型和评测脚本共同复用。

## 主动做出的设计取舍

| 不做 | 原因 |
|---|---|
| RAG / 向量数据库 | 单篇论文是定向字段抽取，文档可截断到上下文范围，引入检索会增加召回损失和系统复杂度 |
| OCR | 目标输入是电子版论文；扫描件会被识别并给出明确错误 |
| Docker / CI | 当前是单机、单用户项目，收益低于学习和维护成本 |
| PostgreSQL | 没有高并发写入需求，SQLite 足够 |
| 用户与权限系统 | 工具定位为单机单用户 |
| ORM | 只有三张表，手写 SQL 更容易学习并讲清数据模型 |

## 安全提醒

- 不要把真实 API Key 写入 `.env.example`。
- 本地 `.env` 已被 `.gitignore` 忽略。
- 用户上传的论文、数据库和日志不会提交到 Git。

