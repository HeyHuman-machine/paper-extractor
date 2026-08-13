# B2 结构化试点标注说明

这里固定 10 篇试点论文，只标两个字段。所有 JSON 初始为 `needs_review: true`，不会参加评分。

## 填写规则

### 实验条件

每个对象只放一个明确条件：

```json
{"name": "modulation", "value": "16QAM", "unit": null}
{"name": "baud_rate", "value": "28", "unit": "Gbaud"}
{"name": "fiber_length", "value": "80", "unit": "km"}
```

### 主要结果

每个对象只放一个可核对的结果：

```json
{
  "metric": "BER",
  "value": "2.1e-3",
  "unit": null,
  "condition": "80 km SSMF"
}
```

`condition` 没有明确适用条件时可写 `null`。只记录论文原文明确给出的内容；找不到可保留空数组。

## 完成一篇后

1. 把该文件的 `needs_review` 改为 `false`。
2. 在 `annotation_meta` 中填入 `reviewed_by`、`reviewed_at`（可选但推荐）。
3. 十篇全部完成后，运行 VS Code 的 `B2-2`，再运行 `B2-3`。

不要查看或复制 B2 的模型输出作为标准答案。
