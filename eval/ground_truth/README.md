# M9 标注目录

- `seed/`：6 篇开发集标签，用于冻结字段和证据口径，不进入最终成绩。
- `evaluation/`：30 篇独立盲测标签，全部确认后才进入正式评分。
- `_template.json`：单份标签结构示例。

正式顺序必须是：

1. 依据原始 PDF 独立填写 `evaluation/` 标准答案。
2. 将 30 份标签的 `needs_review` 全部改为 `false` 并冻结。
3. 再运行 DeepSeek，生成 `eval/predictions/no_retry.json` 和 `with_retries.json`。
4. 最后运行评测脚本。

不要先查看本轮预测再修改标准答案，否则会产生标注锚定和数据泄漏。
