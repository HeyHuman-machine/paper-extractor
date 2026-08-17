# PaperExtractor

批量解析学术论文 PDF 和少量 DOCX，调用可切换的 OpenAI 兼容 LLM 抽取
11 个结构化字段，并提供批量容错、SQLite 持久化、Excel/JSON 导出、FastAPI、
Streamlit 和可量化评测。

## 项目解决的问题

人工整理一篇论文的方法、实验条件和指标通常需要约15分钟。PaperExtractor 的
目标是把几十篇论文的对比整理从数小时压缩到几分钟，同时保留失败诊断、重试
记录和准确率评测，不把 LLM 输出当作天然正确的数据。

## 系统架构

```mermaid
flowchart LR
    U["PDF / DOCX 论文"] --> M1["M1 文档解析"]
    M1 --> M3["M3 三级容错抽取"]
    M2["M2 DeepSeek 客户端\nJSON Mode + thinking disabled"] --> M3
    M3 --> M4["M4 批量调度"]
    M4 --> M5["M5 SQLite\n任务 / 结果 / 失败诊断"]
    M5 --> M6["M6 Excel / JSON 导出"]
    M5 --> M7["M7 FastAPI"]
    M7 --> M8["M8 Streamlit"]
    M3 --> M9["M9 冻结集评测\n字段级 P/R/F1"]
```

> GitHub 原生支持 Mermaid 渲染；完整模块说明见 [`docs/architecture.md`](docs/architecture.md)。

## 当前进度

- [x] M0：环境与项目骨架
- [x] M1：PDF / DOCX 文档解析
- [x] M2：LLM 客户端与 Prompt
- [x] M3：三级容错抽取器
- [x] M4：批量调度
- [x] M5：SQLite 持久化
- [x] M6：Excel / JSON 导出
- [x] M7：FastAPI
- [x] M8：Streamlit
- [x] M9：准确率评测（30 篇独立盲测已完成两轮真实运行与报告）

当前已完成 M0～M9。最终 `final-holdout-v1` 的 30 篇独立论文已冻结人工答案并完成真实运行；
所有 Prompt 优化只在 6 篇开发集完成，最终留出集不再用于调 Prompt 或抽取规则。

## M9 准确率评测

M9 用同一批人工答案比较两轮配置：① 无内容修正重试；② M3 三级容错。
网络层 HTTP 重试保持一致，避免把网络稳定性混进容错效果。

在 VS Code“运行和调试”中依次运行：

1. `M9-1：生成独立盲测空白模板`：只读取 `evaluation/` 文件名，不调用 DeepSeek，也不复制旧预测。
2. 逐篇依据 PDF 填写 `eval/ground_truth/evaluation/`，30 篇全部确认后冻结答案。
3. `M9-2：生成两轮预测（消耗 API）`：只对同一批 30 篇盲测论文真实调用 DeepSeek 两轮。
4. `M9-3：生成评测报告`：生成 Markdown、JSON 和 PNG 柱状图。

标题、方法名、期刊用模糊匹配；年份和文档类型精确匹配；作者、实验条件、主要
结果用原子事实集合 Precision/Recall/F1。研究问题、局限性、摘要是自由文本，不做不可靠
的自动评分。详见 [`docs/notes/M9_准确率评测.md`](docs/notes/M9_准确率评测.md)。

三级容错的 B0 消融实验已在 30 篇固定论文上真实运行：完整三级容错将事后 Schema 合法的
可用输出从 27/30 提升到 30/30，平均多消耗约 606 Token/篇。逐篇证据与解释边界见
[`eval/output/ablation-b0/ablation_report.md`](eval/output/ablation-b0/ablation_report.md)。

方法名称评分规则的 B1 校准不调用 API；它只平行比较旧版 0.90 模糊匹配与候选规则，候选
规则仅处理括号解释、通用后缀、显式缩写和同一主方法的轻微措辞差异。可在 VS Code 运行
`B1：方法名称评分规则校准（不花 API）`，或执行：

```powershell
.\.venv\Scripts\python.exe -m eval.run_method_rule_calibration
```

报告见 [`eval/output/rule-calibration-b1/rule_calibration.md`](eval/output/rule-calibration-b1/rule_calibration.md)。

## B2：结构化输出试点（准备完成，等待人工标注）

诊断显示模型/标注的条目数量比为实验条件 **0.65**、主要结果 **0.38**，切分粒度明显
不一致。因此 B2 不直接修改主项目的 11 字段 Schema，而是在独立评测试验层中把两个字段
改为对象列表：条件是 `{name, value, unit}`，结果是 `{metric, value, unit, condition}`。

固定随机种子已抽取 10 篇试点论文，空白模板位于
`eval/ground_truth_structured_trial/`。请只对照原论文填写模板中的两个列表，确认后将
`needs_review` 改为 `false`。随后依次在 VS Code 运行：

1. `B2-1：生成结构化试点标注模板（不花 API）`（模板已存在时不会覆盖）。
2. `B2-2：结构化输出试点（10 篇，消耗 API）`（会向 DeepSeek 发送 10 篇论文）。
3. `B2-3：结构化试点评测（不花 API）`。

第 3 步会把旧 V2 文本输出和 B2 新输出放到**同一份结构化人工答案**、同一套
partial-credit 规则下比较；同名同数值（允许 ±5%、单位一致）得 1.0，仅同名得 0.5，
避免因为一句话拆成几条就全部失分。

### B2 试点结论：未通过，不推广

用户确认结构化答案后，B2 已对固定 10 篇论文真实调用 DeepSeek，**10 / 10 成功**，总计
**44,576 Token**、零内容修正。随后用同一份结构化人工答案评测：实验条件 F1 为
**31.57% → 29.76%**，主要结果 F1 为 **7.83% → 6.40%**，两字段平均 F1 为
**19.70% → 18.08%**。因此 B2 没有通过试点门槛，不替换 M1～M8 的主 Schema 或默认抽取路径。

逐篇复盘显示多篇 B2 输出为空列表，说明固定对象 Schema 解决不了“从长论文中找全证据”的
召回问题。原始输出与对照报告见
[`eval/predictions/b2-structured-pilot/predictions.json`](eval/predictions/b2-structured-pilot/predictions.json)
和 [`eval/output/b2-structured-pilot/report.md`](eval/output/b2-structured-pilot/report.md)。

## 启动可视化界面

在 VS Code“运行和调试”中选择 `M8：同时启动后端与界面`，一次启动 M7 与 M8，
然后打开 <http://127.0.0.1:8501>。界面支持上传论文、查看历史任务、失败诊断，
以及下载 Excel / JSON。

也可以分别选择 `M7：启动 FastAPI（打开 /docs）` 与
`M8：启动 Streamlit 界面`。详细流程见
[`docs/notes/M8_Streamlit界面.md`](docs/notes/M8_Streamlit界面.md)。

## 启动 FastAPI

在 VS Code“运行和调试”中选择 `M7：启动 FastAPI（打开 /docs）`，或执行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api:app --reload
```

打开 <http://127.0.0.1:8000/docs>，可直接上传多个 PDF / DOCX、查询任务和下载 Excel / JSON。接口流程说明见 [`docs/notes/M7_FastAPI接口.md`](docs/notes/M7_FastAPI接口.md)。

## Docker 启动（推荐用于环境复现）

Docker Desktop 启动后，在项目根目录的 VS Code 终端执行：

```powershell
docker compose up --build
```

这条命令会构建同一份项目镜像，并启动两个容器：

- `api`：FastAPI 后端，访问 <http://127.0.0.1:8000/docs>
- `ui`：Streamlit 界面，访问 <http://127.0.0.1:8501>

`data`、`storage` 和 `logs` 会挂载到宿主机项目目录，因此容器删除后，论文、SQLite
数据库、导出文件和日志仍然保留。容器内的 Streamlit 通过 `http://api:8000` 访问后端，
不需要把 `API_BASE_URL` 改成宿主机地址。

常用操作：

```powershell
# 后台启动
docker compose up -d --build
# 查看运行状态
docker compose ps
# 查看日志
docker compose logs -f api
# 停止并移除容器（不会删除挂载的数据）
docker compose down
```

> `.env` 只在启动时作为容器环境变量传入，不会复制进镜像，也不应提交到 GitHub。

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

## 最终 M9 评测摘要（冻结 30 篇留出集）

初始并发对照组为 **27/30** 成功、8 字段宏平均 **45.79%**；三级容错组为
**30/30** 成功、宏平均 **50.47%**。为排除并发模式差异，又以相同的串行逐篇检查点
模式复现无内容修正组，得到 **29/30** 成功、宏平均 **50.15%**。

| 指标 | 原并发无修正 | 串行无修正复现 | 三级容错 |
| --- | ---: | ---: | ---: |
| 成功抽取 | 27/30 | 29/30 | 30/30 |
| 8 字段宏平均 | 45.79% | 50.15% | 50.47% |
| 作者 F1 | 82.72% | 89.87% | 89.81% |
| 实验条件 F1 | 34.40% | 41.29% | 43.74% |
| 主要结果 F1 | 42.52% | 46.74% | 50.18% |

串行复现表明：F26 在串行无修正时仍失败、三级容错成功，可明确归因于内容修正机制；
F21、F28 在串行无修正时成功，因此原始 27→30 提升中的这两篇不能排除运行间差异。
方法名称另有一份受限的度量 v2 复算：只修正“全称（缩写）↔缩写”的明确误判，分数
从 3.33% 到 6.67%；该规则是在看过留出集后设计，保留 v1 数字且必须在新数据集验证。

详见：

- [`eval/output/final-holdout-v1/version-convention-analysis.md`](eval/output/final-holdout-v1/version-convention-analysis.md)
- [`eval/output/final-holdout-v1/atomic-fact-coverage.md`](eval/output/final-holdout-v1/atomic-fact-coverage.md)
- [`eval/output/final-holdout-v1/method-name-metric-v2.md`](eval/output/final-holdout-v1/method-name-metric-v2.md)
- [`eval/output/final-holdout-v1/ablation-rerun.md`](eval/output/final-holdout-v1/ablation-rerun.md)

## 已知局限

- 最终留出集已经用于度量缺陷诊断；后续任何规则改动都必须使用新的独立数据集验证。
- 方法名称的严格字符串规则仍会错过许多“核心方法相同但限定成分不同”的表达，不能把 v2 复算当成泛化提升。
- 原子事实指标只识别数值、单位、类别词与指标词；实验条件中 **13/30** 的人工标签没有可识别原子事实，定性事实会被低估。
- 项目只面向电子版 PDF / DOCX；扫描件未接入 OCR，单机部署也未引入 Docker、RAG 或多用户权限系统。
