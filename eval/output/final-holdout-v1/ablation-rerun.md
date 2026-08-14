# final-holdout-v1：串行无内容修正对照复现

> 该复现使用与三级容错轮相同的逐篇检查点串行执行模式；唯一开关差异是 `max_repair_retries=0`。

## 串行对照组结果

- 成功：29 / 30。
- 失败：1 / 30。

| 失败论文 | 阶段 | 字段/错误 |
|---|---|---|
| F26-soliton-crystals-imdd.pdf | schema_validate | 1 validation error for PaperRecord<br>limitations<br>  Value error, limitations 只能来自作者明确陈述，不能使用推测性措辞 [type=value_error, input_value='作者未明确陈述局限性。', input_type=str]<br>    For further information visit https://errors.pydantic.dev/2.13/v/value_error |

## 与原并发对照组的状态差异

| 论文 | 原并发对照 | 串行对照 |
|---|---|---|
| f21-self-coherent-mqam-ross.pdf | failed | success |
| f28-soliton-microcombs-fec-free.pdf | failed | success |

## 8 字段成绩表

| 字段 | 原并发无修正 | 串行无修正 | 三级容错 |
|---|---:|---:|---:|
| year | 46.67% | 46.67% | 46.67% |
| doc_type | 46.67% | 46.67% | 50.00% |
| title | 90.00% | 96.67% | 100.00% |
| method_name | 3.33% | 3.33% | 3.33% |
| venue | 20.00% | 30.00% | 20.00% |
| authors | 82.72% | 89.87% | 89.81% |
| experimental_conditions | 34.40% | 41.29% | 43.74% |
| main_results | 42.52% | 46.74% | 50.18% |
| **8 字段宏平均** | 45.79% | 50.15% | 50.47% |

## 归因结论

**在串行对照仍失败、而三级容错成功的论文有 1 篇：f26-soliton-crystals-imdd.pdf；这些篇目可归因于内容修正机制。**
**原并发失败但串行无修正成功的论文有 2 篇：f21-self-coherent-mqam-ross.pdf, f28-soliton-microcombs-fec-free.pdf；这些篇目不能排除运行间差异。**
