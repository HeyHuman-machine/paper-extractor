# 光通信论文库（36 篇开发/旧评测 + 30 篇最终留出集）

本库按用途隔离为 **6 篇种子/开发论文**、**30 篇已使用的旧评测论文**，以及 **30 篇最终留出论文**。这样既保留课题组论文用于调试与建立抽取规则，又避免它们及其已有标注进入盲测集造成数据泄漏。

## 数据集划分

| 目录 | 数量 | 用途 | 是否参与最终评测 |
|---|---:|---|---|
| `seed/` | 6 | 需求分析、规则调试、提示词开发、人工标注范例 | 否 |
| `evaluation/` | 30 | 未见论文上的批量抽取、鲁棒性和准确率评测 | 是 |
| `final_holdout/` | 30 | 冻结后的最终泛化验证 | 是；但在完成独立标注前不得统计准确率 |

此前的 30 篇 `evaluation/` 已经参与过诊断与规则调优，因此不再属于严格盲测。最终报告应将它们与 `final_holdout/` 分开：**开发集 6 篇、旧评测集 30 篇、冻结最终留出集 30 篇**。不得将三组混合后报告一个“总体准确率”。

## 技术覆盖

- 独立双/三/四边带、Twin-SSB 与零保护带传输
- 单光电探测器直接检测、SSBI 抑制、KK 与迭代式光场恢复
- 自相干/载波无关相位恢复、神经网络均衡
- PON、短距互连与光子辅助毫米波/太赫兹光纤无线融合

## 文件说明

- `seed/01`–`seed/06`：项目原有种子论文副本，原件仍保留在 `data/inbox/`。
- `evaluation/07`–`evaluation/30`：上一轮扩展的 24 篇公开全文。
- `evaluation/31`–`evaluation/36`：本轮补充的 6 篇正式期刊论文。
- `download-manifest.csv`：30 篇独立评测论文的题录、DOI、分类与实际下载地址。
- `validation-report.json`：36 份 PDF 的分组、签名、页数、SHA-256 与首页文本验收结果。
- 作者接收稿或 arXiv 对应正式论文时，引用应优先使用清单中的正式期刊 DOI。

## 推荐使用方式

1. 只在 `seed/` 上设计字段、调试解析链路和查看人工答案。
2. 冻结规则、模型版本和提示词后，再一次性运行 `evaluation/`。
3. 分别统计文档成功率、字段级准确率、缺失率和异常样本，不用种子集成绩替代盲测成绩。
4. 当前 30 篇盲测集足以支撑项目演示和简历中的初步量化；若要形成论文级实验，建议扩充到 50–100 篇，并按期刊、年份、版式和技术方向分层抽样。

## 最终留出集（F01–F30）

- 清单：`eval/final_holdout_manifest.json`（arXiv ID、题名、年份、分类）；下载版本可通过 SHA-256 报告复现。
- 下载：在项目根目录运行 `uv run python -m eval.download_final_holdout`；脚本会下载到 `final_holdout/`，检查 PDF 文件头和最小大小，并生成 `validation-report.json`。
- 标注模板：运行 `uv run python -m eval.prepare_final_holdout_labels`。模板预填的仅是清单中的题名、年份和来源；研究内容字段必须从 PDF 独立标注。
- 纪律：冻结集不得用于继续修改 Prompt、解析策略、后处理规则或字段匹配器。任何 AI 初标只能标记为待复核，不能对外表述为人工金标准。

## 新增 6 篇（31–36）

| 编号 | 论文 | 年份 | 补充维度 |
|---:|---|---:|---|
| 31 | Accurate Field Reconstruction at Low CSPR Condition Based on a Modified KK Receiver With Direct Detection | 2020 | 低 CSPR、改进 KK |
| 32 | Digital Subcarrier Multiplexing for Carrier-Free Phase-Retrieval Coherent Receiver | 2023 | 载波无关相位恢复 |
| 33 | Multi-Twin-SSB Modulation with Direct Detection Based on Kramers-Kronig Scheme for Long-Reach PON Downstream | 2019 | Twin-SSB、PON |
| 34 | Filter-Assisted Self-Coherent Detection Field Recovery Scheme for Dual-Polarization Complex-Valued Double-Sideband Signals | 2025 | 双偏振自相干恢复 |
| 35 | Advanced Neural Network-Based Equalization in Intensity-Modulated Direct-Detection Optical Systems: Current Status and Future Trends | 2024 | 神经网络均衡综述 |
| 36 | Zero-guard band dual-SSB PAM4 signal transmission with joint equalization scheme | 2020 | 零保护带 Dual-SSB |
