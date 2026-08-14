# Claude 信息确认清单答复

> 整理日期：2026-08-14  
> 项目：PaperExtractor  
> 原则：所有最终成绩以 `final-holdout-v1` 为准；未持久化的数据明确标注为“不可审计”，不补猜。

---

## A. 数字口径

### A1. 两组结果是否来自同一批论文？

- 旧数据：V2 = **69.77%**、V6 = **69.75%**，来自旧的 `evaluation` 30 篇集。
  - 标签目录：`eval/ground_truth/evaluation/`（本地、Git 忽略）
  - 报告：`eval/output/v2-v6-evaluation/report.json`
  - 预测：`eval/predictions/v2-evaluation/predictions.json`、`eval/predictions/v6-evaluation/predictions.json`
- 最终数据：**45.79% → 50.47%**，来自新的 `final-holdout-v1` 30 篇最终留出集。
  - 标签目录：`eval/ground_truth_final_holdout/`（本地、Git 忽略）
  - 报告：`eval/output/final-holdout-v1/report.json`
  - 预测：`eval/predictions/final-holdout-v1/no_retry.json`、`eval/predictions/final-holdout-v1/with_retries.json`

两个 30 篇**不是同一批论文**。`eval/final_holdout_manifest.json` 明确说明最终留出集已与此前的 6 篇开发集和旧 30 篇评测集去重。

**明确结论：旧 30 篇的 69.77% / 69.75% 不再用于简历、答辩或对外的最终效果声明；只能作为已暴露评测集上的历史开发实验记录。**

因此，旧集中的“方法名称 30%、期刊 90%”与最终集的“方法名称 3.33%、期刊 20%”不是同一批论文审计后下降，而是语料、标注和领域分布都不同，不能直接横向解释为模型退步。

### A2. 最终留出集完整成绩表

来源：`eval/output/final-holdout-v1/report.json`。

| 字段 | 评测规则 | 无内容修正重试 | 三级容错 |
|---|---|---:|---:|
| 年份 | 精确匹配 | 46.67%（14/30） | 46.67%（14/30） |
| 文档类型 | 精确匹配 | 46.67%（14/30） | 50.00%（15/30） |
| 标题 | 归一化字符模糊匹配，阈值 0.90 | 90.00%（27/30） | 100.00%（30/30） |
| 方法名称 | 归一化字符模糊匹配，阈值 0.90 | 3.33%（1/30） | 3.33%（1/30） |
| 期刊/会议 | 归一化字符模糊匹配，阈值 0.90 | 20.00%（6/30） | 20.00%（6/30） |
| 作者 | 归一化集合 F1 | 82.72% | 89.81% |
| 实验条件 | 原子事实集合 F1 | 34.40% | 43.74% |
| 主要结果 | 原子事实集合 F1 | 42.52% | 50.18% |
| **8 字段宏平均** | 八字段等权平均 | **45.79%** | **50.47%** |

无内容修正组 30 篇中 27 篇成功；三级容错组 30/30 成功。缺失预测在自动字段中按 0 分处理。

---

## B. 关键实现参数

来源：`.env`、`app/config.py`、`app/llm.py`、`app/parser.py`。

| 项目 | 实际生效值 |
|---|---|
| `temperature` | `0.0` |
| 模型 | `deepseek-v4-flash` |
| JSON Mode | 开启，`response_format: {"type": "json_object"}` |
| Thinking | 关闭，`thinking: {"type": "disabled"}` |
| `LLM_MAX_RETRIES` | `2`；网络层最多 3 次 HTTP 尝试 |
| `BATCH_CONCURRENCY` | `3`；最终三级容错检查点运行采用串行处理 |
| `EXTRACT_MAX_CHARS` | `12000` 字符 |
| HTTP 超时 | `60` 秒 |
| 退避序列 | `1 秒 → 2 秒`；不会到 4 秒 |

超长文本截断的实际组成：

- 前 `8386` 字符；
- 后 `3595` 字符；
- 中间插入 `\n\n...[中间内容已截断]...\n\n`，长度为 19 字符。

最终 30 篇均来自 arXiv 公开 PDF，清单见 `eval/final_holdout_manifest.json`。标签审计报告记录总页数为 **295 页**，平均 **9.83 页/篇**，见 `eval/output/final-holdout-label-audit.json`。

运行产物没有持久化每篇论文的完整解析字符数，因此不存在可审计的“平均全文字符数”。实际送入 LLM 的正文上限是 12,000 字符，不能把这个上限写成论文平均长度。

---

## C. 成本与性能

来源：

- `eval/predictions/final-holdout-v1/no_retry.json`
- `eval/predictions/final-holdout-v1/with_retries.json`

| 指标 | 无内容修正重试 | 三级容错 |
|---|---:|---:|
| 发送论文数 | 30 | 30 |
| 成功数 | 27 | 30 |
| 总 Token | 163,764 | 169,370 |
| 总耗时 | 137.338 秒 | 258.845 秒 |
| 按总耗时折算吞吐 | 4.58 秒/篇 | 8.63 秒/篇 |
| 内容修正总次数 | 0 | 1 |
| 平均内容修正次数 | 0.000 次/篇 | 0.033 次/篇 |

Token 分项没有保存：运行产物只记录 `total_tokens`，没有汇总的输入 Token、输出 Token 字段。因此不能事后可靠拆分输入/输出，也不能可靠折算人民币成本；还缺少当时的模型价格和缓存计费快照。

三级容错的经验 Token 代价：

```text
169,370 - 163,764 = 5,606 Token
5,606 / 163,764 = 3.4232%
```

即：**三级容错多消耗 5,606 Token，增加 3.42%。**

时间不能直接作为“容错导致变慢”的因果结论：无内容修正组为 3 并发，最终三级容错组为逐篇检查点串行运行。三级容错成功输出中仅 F21 记录到一次内容修正；HTTP 级重试次数没有逐篇持久化。

---

## D. 错误分析

### D1. Precision / Recall / F1

| 字段 | 无内容修正重试 P / R / F1 | 三级容错 P / R / F1 |
|---|---|---|
| 实验条件 | 29.25% / 49.33% / 34.40% | 38.62% / 59.33% / 43.74% |
| 主要结果 | 40.18% / 51.79% / 42.52% | 46.95% / 61.79% / 50.18% |

两个字段均为 Recall 高于 Precision：既有漏抽，也有模型抽取出的原子事实未出现在人工金标准中的情况。

### D2. 典型失败样例

来源：最终留出集三级容错预测与人工标签。

#### 方法名称

| 论文编号 | 人工标注 | 模型输出 | 得分 |
|---|---|---|---:|
| F01 | Dual-tap optical-digital feedforward equalization (DT-ODFE) | DT-ODFE | 0% |
| F02 | Autoencoder-based neural network (NN) | Autoencoder-based constellation optimization | 0% |
| F03 | Probabilistic shaped PAM-8 cap and cup variants | Cap and Cup Maxwell-Boltzmann probabilistic shaping | 0% |
| F04 | Probabilistic amplitude shaping (PAS) | PAS with peak power constraint | 0% |
| F05 | Structural reduction of the number of kernels | Structural kernel reduction schemes… | 0% |

#### 期刊/会议

| 论文编号 | 人工标注 | 模型输出 | 得分 |
|---|---|---|---:|
| F01 | arXiv preprint | `null` | 0% |
| F02 | arXiv preprint | Journal of Lightwave Technology | 0% |
| F03 | European Conference on Optical Communication (ECOC) | `null` | 0% |
| F04 | Journal of Lightwave Technology | arXiv | 0% |
| F05 | 21th ITG-Symposium on Photonic Networks | `null` | 0% |

#### 实验条件

| 论文编号 | 人工标注 | 模型输出 | 得分 |
|---|---|---|---:|
| F04 | 无放大/无在线色散补偿；AWGN 与光纤信道 | 4-PAM、8–32 Gbaud、SSMF、峰值功率约束等 | 0% |
| F06 | O-band EML 无放大 IM/DD；接近零色散波长 | PAM-8、5 km、O-band、EML 等 | 0% |
| F07 | 短距 IM/DD；峰值功率约束 | 60/95.6 GBaud、1 km、1550 nm 等 | 0% |
| F09 | IM/DD 短距系统；纯色散链路；SLD | 20 km、PAM、SSMF | 0% |
| F10 | 短距直接检测光纤链路 | 8/6-ASK、130–230 GBaud、10 km 等 | 0% |

这些样例表明，模型偏好输出可量化参数，而部分人工标注偏系统性或定性条件；在当前原子事实集合规则下，交集不足会直接形成低分。

### D3. 原子事实切分粒度

三级容错轮、最终 30 篇的每篇去重原子事实集合平均值：

| 字段 | 人工标注平均原子事实/篇 | 模型输出平均原子事实/篇 |
|---|---:|---:|
| 实验条件 | 1.43 | 4.20 |
| 主要结果 | 2.77 | 4.87 |

模型输出的原子事实数更高，与 Precision 低于 Recall 的现象一致。

### D4. 原子事实 F1 的实际实现

正式评测调用 `eval/metrics.py` 中的 `atomic_fact_precision_recall_f1`。它不做逐条语义理解，而是从两边文本中提取数值+单位、调制格式、器件、结果指标等 token，再做集合交集。

```python
def atomic_fact_precision_recall_f1(expected, actual):
    expected_facts = _atomic_facts(expected)
    actual_facts = _atomic_facts(actual)
    if not expected_facts and not actual_facts:
        return 1.0, 1.0, 1.0

    true_positive = len(expected_facts & actual_facts)
    precision = true_positive / len(actual_facts) if actual_facts else 0.0
    recall = true_positive / len(expected_facts) if expected_facts else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall else 0.0
    )
    return precision, recall, f1

def _atomic_facts(items):
    facts = set()
    for item in items or []:
        normalized = _normalize_scientific_notation(item).casefold()
        facts.update(normalize_text(match.group(0))
                     for match in _UNIT_FACT_PATTERN.finditer(normalized))
        facts.update(normalize_text(match.group(0))
                     for match in _SCIENTIFIC_VALUE_PATTERN.finditer(normalized))
        facts.update(match.group(0)
                     for match in _CATEGORY_FACT_PATTERN.finditer(normalized))
        facts.update(match.group(0)
                     for match in _METRIC_FACT_PATTERN.finditer(normalized))
    return facts
```

归一化包含 Unicode NFKC、小写化、去空格/标点，以及把 `2.1×10^-3`、`2.1 x 10−3` 统一为 `2.1e-3`。

限制：它不能理解“5 km”和“short-reach”是否语义等价；只有命中相同类型 token 才会得分。

---

## E. 标注一致性复核

已补齐最终留出集的独立复核入口：

- `eval/agreement.py`
- `eval/ground_truth_final_holdout_recheck/README.md`
- `eval/ground_truth_final_holdout_recheck/_template.json`

复核者应从最终 30 篇中抽 8 篇，只依据原始 PDF 重写三个字段：`method_name`、`experimental_conditions`、`main_results`，且不能查看原标注、模型输出和评测报告。

完成后运行：

```powershell
.\.venv\Scripts\python.exe -m eval.agreement `
  --ground-truth eval/ground_truth_final_holdout `
  --recheck-dir eval/ground_truth_final_holdout_recheck `
  --output eval/output/final-holdout-v1/human-agreement.json
```

程序要求恰好 8 篇共同论文。方法名称使用当前模糊匹配 Accuracy；实验条件与主要结果使用当前原子事实 P/R/F1。

此前 `ground_truth_recheck` 中已有的 8 篇是旧评测集的独立 AI 复核，不是人类自一致性，不能作为“人类天花板”。新结果产生后，应称为“独立标注一致性”，不宜夸大为严格统计意义上的人类上限。

---

## F. 交付状态

1. 已推送 GitHub：<https://github.com/HeyHuman-machine/paper-extractor>；当前公开，默认分支为 `main`。
2. README 有项目简介、快速开始和设计取舍说明。架构图在 `docs/architecture.md` 的 Mermaid 图中，没有直接嵌入 README。
3. `.env` 已被 `.gitignore` 忽略；`git log --all -- .env` 无输出，说明未进入历史提交。
4. 已进行干净 clone 验证：`uv sync` 与 `uv run python hello.py` 成功。真实 LLM 功能仍需使用者自行填写自己的 `.env` API Key。
5. Streamlit 四个主要页面截图位于 `docs/screenshots/`：
   - `m8-new-task-final.png`
   - `m8-upload-ready-final.png`
   - `m8-history-final.png`
   - `m8-failures.png`
6. 当前测试结果：**149 passed, 1 warning**。覆盖配置、解析、LLM、重试、Schema 容错、批处理、数据库、导出、FastAPI、Streamlit、评测、检查点、最终集审计、B2、标注一致性等模块。未生成行覆盖率报告，不能声称具体覆盖率百分比。

---

## G. 面试可直接表述

### G1. 三级容错

我把三级容错分为 JSON 解析、Pydantic Schema 校验和带错误反馈的内容修正。第一层负责处理模型返回的 Markdown 代码块或包裹文本；最终 30 篇中没有记录到真实 JSON 解析失败，所以不会虚构这个案例。第二层在 F21、F26、F28 中拦截了不合规字段，例如把“作者未明确陈述局限性”写进局限性字段。第三层会把具体校验错误反馈给模型重新生成，最终把可用结果从 27/30 提升到 30/30。

### G2. F21 / F26 / F28 的具体失败原因

F21 的失败字段是 `limitations`：模型写了“作者未明确陈述局限性”，这属于推测性表述，不允许作为作者明确声明的局限性。F26 是相同类型的 `limitations` 错误。F28 同时在 `experimental_conditions` 中写入了 `fiber_type: not specified`、`fiber_length: not specified`，并在 `limitations` 中写了“当前实验未明确陈述局限性”。三级容错轮会把这些 Pydantic 错误带回模型，要求只保留原文明确给出的证据。

### G3. 为什么不推广 B2 结构化对象输出

我没有推广 B2，因为它在固定 10 篇试点中没有带来提升。实验条件 F1 从 31.57% 降到 29.76%，主要结果从 7.83% 降到 6.40%，两字段平均从 19.70% 降到 18.08%。复盘发现多篇 B2 输出为空列表，说明固定对象 Schema 并不能解决长论文中的证据召回问题。因此我保留这个负结果，而没有为了结构更整齐就替换主流程。

### G4. 再给两周的优先事项

我会优先建立新的、未看过的评测集，并完成 8 篇独立人工复核的一致性评测。因为当前最终留出集已经被看过，继续针对它调 Prompt 会形成数据泄漏，分数不再代表泛化能力。在新评测集冻结前，我不会再宣称任何优化有效。之后我会针对方法名称增加“缩写—全称—原文证据”三元抽取与可审计匹配，而不是继续盲目堆 Prompt。

---

## 2026-08-14 收尾复现更新

- 版本口径分析显示：年份 16 个错误中，`模型年份 = arXiv 提交年且人工为其他年` 为 **0/16**；因此年份低分不能主要归因于版本口径。文档类型 15 个错误中，**14/15** 是预印本与正式发表类型的方向冲突。
- 原子事实覆盖分析显示：实验条件有 **13/30**、主要结果有 **7/30** 的人工标签无法抽取任何可识别原子事实；这些样例的指标会结构性低估定性事实抽取。
- 方法名称仅按“空值对齐、括号缩写、首字母缩写”复算一次，且保持 0.90 阈值不变：三级容错方法名称从 **3.33%** 到 **6.67%**，八字段宏平均从 **50.47%** 到 **50.88%**。该规则在看过留出集后设计，必须在新数据集重新验证。
- 串行无内容修正复现为 **29/30** 成功、宏平均 **50.15%**；其中 F26 仍失败而三级容错成功，可明确归因于内容修正。F21 与 F28 的原始失败无法排除运行间差异。

对应报告：`eval/output/final-holdout-v1/version-convention-analysis.md`、`atomic-fact-coverage.md`、`method-name-metric-v2.md`、`ablation-rerun.md`。
