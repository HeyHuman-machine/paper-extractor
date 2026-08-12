# PaperExtractor

批量解析学术论文 PDF 和少量 DOCX，调用可切换的 OpenAI 兼容 LLM 抽取
11 个结构化字段，并提供批量容错、SQLite 持久化、Excel/JSON 导出、FastAPI、
Streamlit 和可量化评测。

## 项目解决的问题

人工整理一篇论文的方法、实验条件和指标通常需要约15分钟。PaperExtractor 的
目标是把几十篇论文的对比整理从数小时压缩到几分钟，同时保留失败诊断、重试
记录和准确率评测，不把 LLM 输出当作天然正确的数据。

## 当前进度

- [x] M0：环境与项目骨架
- [x] M1：PDF / DOCX 文档解析
- [x] M2：LLM 客户端与 Prompt
- [x] M3：三级容错抽取器
- [x] M4：批量调度
- [x] M5：SQLite 持久化
- [x] M6：Excel / JSON 导出
- [ ] M7：FastAPI
- [ ] M8：Streamlit
- [ ] M9：准确率评测

当前已完成 M0～M6，不包含尚未验收模块的业务实现。

## 日常使用：自动处理输入文件夹

只需在 `.env` 中统一配置输入与输出目录：

```dotenv
# 自动读取该文件夹第一层的全部 PDF / DOCX
INPUT_DIR=data/inbox
# 生成论文对比表.xlsx 和论文完整数据.json
OUTPUT_DIR=data/output
# 保存批次历史；建议与输出目录分开
DB_PATH=storage/app.db
```

相对路径从项目根目录开始，也可以填写绝对路径，例如：

```dotenv
INPUT_DIR=E:/待处理论文
OUTPUT_DIR=E:/论文抽取结果
```

把论文拖入 `INPUT_DIR` 后，在 VS Code “运行和调试”中选择
`M1-M6：自动处理输入文件夹（调用 DeepSeek）` 并点击运行。程序会自动读取所有
`.pdf` 和 `.docx`，不需要把文件名写进 Python 代码。命令行等价操作为：

```powershell
.\.venv\Scripts\python.exe scripts\run_real_m1_m6.py
```

> 注意：这个入口会真实调用 DeepSeek；输入目录中有几篇论文，就会处理几篇。

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

## 检查论文解析结果

把电子版 PDF 或 DOCX 放入 `data/inbox`，然后执行：

```powershell
uv run python scripts/inspect_documents.py
```

也可以在命令末尾传入一个或多个文件路径。M1 会输出格式、页数、字符数和
前 500 字；加密、损坏、格式不支持或疑似扫描件都会得到明确错误信息。
详细解释见 [`docs/notes/M1_文档解析.md`](docs/notes/M1_文档解析.md)。

## 检查 DeepSeek 连接

先复制 `.env.example` 为 `.env`，在本机填写 API Key，再执行：

```powershell
uv run python scripts/check_llm.py
```

该脚本只发送内置的虚构论文短文本，不会读取 `data/inbox`。它会打印模型名、
token 用量、耗时、重试次数和通过 Pydantic 校验的 11 字段结果。详细解释见
[`docs/notes/M2_LLM客户端与Prompt.md`](docs/notes/M2_LLM客户端与Prompt.md)。

## 检查三级容错抽取

先运行完全本地的失败修正演示，不访问 DeepSeek、不产生费用：

```powershell
uv run python scripts/demo_m3_retries.py
```

再运行真实 M3 调用（只发送内置虚构短文本，会产生少量 token 费用）：

```powershell
uv run python scripts/check_extractor.py
```

M3 会清洗 JSON、使用 Pydantic 校验 11 个字段、把具体错误反馈给模型并重试；
重试耗尽后返回失败诊断，不让异常中断后续批处理。详细解释见
[`docs/notes/M3_三级容错抽取器.md`](docs/notes/M3_三级容错抽取器.md)。

## 检查批量调度

运行不访问 DeepSeek 的 10 文件本地演示：

```powershell
.\.venv\Scripts\python.exe scripts\demo_m4_batch.py
```

演示使用 3 个工作线程，模拟 8 篇成功、1 篇解析失败和 1 篇抽取失败，并逐篇输出
进度。M4 会保持最终结果与输入文件同序，单篇失败不会中断整批。详细解释见
[`docs/notes/M4_批量调度.md`](docs/notes/M4_批量调度.md)。

## 检查 SQLite 持久化

运行不访问 DeepSeek 的临时数据库演示：

```powershell
.\.venv\Scripts\python.exe scripts\demo_m5_database.py
```

脚本把 2 条成功结果和 1 条失败诊断写入 SQLite，再重新连接查询三张表，证明数据
已经落盘而不是只留在内存。详细解释见
[`docs/notes/M5_SQLite持久化.md`](docs/notes/M5_SQLite持久化.md)。

## 检查 Excel / JSON 导出

运行不访问 DeepSeek 的本地导出演示：

```powershell
.\.venv\Scripts\python.exe scripts\demo_m6_export.py
```

脚本先把演示批次保存到 SQLite，再按 `task_id` 生成可筛选的论文对比表和完整 JSON。
输出位于 `data/output/m6-demo`。Excel 包含论文结果、失败记录和任务概览三个工作表；
失败记录仍保持在第二页，方便和规格书约定一致。
详细解释见 [`docs/notes/M6_Excel与JSON导出.md`](docs/notes/M6_Excel与JSON导出.md)。

## 11 个目标字段

1. `title`
2. `authors`
3. `year`
4. `venue`
5. `doc_type`
6. `problem`
7. `method_name`
8. `experimental_conditions`
9. `main_results`
10. `limitations`
11. `summary`

正式 Schema 已在 M1 的 `app/models.py` 中实现，后续会由 LLM 输出校验、
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
