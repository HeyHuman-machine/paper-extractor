# 最终留出集：独立人工复核

此目录用于测量标注者之间的一致性，**不参与模型准确率计算**。

1. 从 `eval/ground_truth_final_holdout/` 随机选 8 篇 PDF；复制本目录的 `_template.json` 为对应文件名的 JSON。
2. 只依据原始 PDF 填写 `method_name`、`experimental_conditions`、`main_results`；不要查看原标注、模型输出或评测报告。
3. 完成后将 `needs_review` 改为 `false`。
4. 在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -m eval.agreement `
  --ground-truth eval/ground_truth_final_holdout `
  --recheck-dir eval/ground_truth_final_holdout_recheck `
  --output eval/output/final-holdout-v1/human-agreement.json
```

输出中的方法名称是归一化文本模糊匹配 Accuracy；实验条件和主要结果是与主评测相同的原子事实 Precision / Recall / F1。只有 8 篇都有 `needs_review: false` 时，才可将该报告作为“标注一致性”的补充证据；它不是严格统计意义上的人类天花板。
