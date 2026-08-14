# final-holdout-v1：版本口径分析

> 只读分析冻结标签与既有三级容错预测；不修改 Prompt、阈值或抽取参数。

## 年份判错样例

| 论文编号 | 人工标注年份 | 模型输出年份 | arXiv 提交年份 |
|---|---:|---:|---:|
| f01-dual-tap-optical-digital-ffe.pdf | 2024 | null | 2024 |
| f03-cap-cup-shaped-pam.pdf | 2022 | null | 2022 |
| f04-ps-4pam-short-reach.pdf | 2020 | 2021 | 2020 |
| f05-volterra-complexity-reduction.pdf | 2020 | null | 2020 |
| f11-low-cost-phase-precoding.pdf | 2025 | null | 2025 |
| f13-generative-imdd-optimization.pdf | 2019 | 2020 | 2019 |
| f14-deep-learning-dispersive-channels.pdf | 2019 | 2020 | 2019 |
| f18-silicon-photonic-neural-network.pdf | 2024 | null | 2024 |
| f21-self-coherent-mqam-ross.pdf | 2025 | 2026 | 2025 |
| f22-jones-space-field-recovery.pdf | 2022 | null | 2022 |
| f25-dual-polarization-field-reconstruction.pdf | 2019 | null | 2019 |
| f26-soliton-crystals-imdd.pdf | 2024 | null | 2024 |
| f27-microresonator-comb-imdd.pdf | 2021 | null | 2021 |
| f28-soliton-microcombs-fec-free.pdf | 2021 | 2022 | 2021 |
| f29-100g-silicon-dd-mzm.pdf | 2018 | null | 2018 |
| f30-168g-pam4-silicon-mzm.pdf | 2018 | null | 2018 |

## 文档类型判错样例

| 论文编号 | 人工标注文档类型 | 模型输出文档类型 |
|---|---|---|
| f01-dual-tap-optical-digital-ffe.pdf | preprint | journal_article |
| f02-autoencoder-pam-imdd.pdf | preprint | journal_article |
| f04-ps-4pam-short-reach.pdf | journal_article | preprint |
| f07-pam6-short-reach.pdf | conference_paper | preprint |
| f10-bipolar-constellations-direct-detection.pdf | preprint | conference_paper |
| f11-low-cost-phase-precoding.pdf | preprint | journal_article |
| f12-end-to-end-deep-learning.pdf | journal_article | preprint |
| f16-spiking-neural-demapping.pdf | journal_article | conference_paper |
| f20-ross-imdd-receiver.pdf | preprint | journal_article |
| f22-jones-space-field-recovery.pdf | preprint | journal_article |
| f23-carrierless-phase-retrieval.pdf | preprint | conference_paper |
| f26-soliton-crystals-imdd.pdf | preprint | journal_article |
| f27-microresonator-comb-imdd.pdf | preprint | journal_article |
| f29-100g-silicon-dd-mzm.pdf | preprint | journal_article |
| f30-168g-pam4-silicon-mzm.pdf | preprint | conference_paper |

## 统计

- 年份判错：16 / 30。
- 其中“模型年份 = arXiv 提交年，且人工年份为其他年份”：0 / 16 （0.00%）。
- 文档类型判错中，preprint 与 journal/conference 的版本方向冲突：14 / 15。
- 期刊/会议判错：24 / 30；其中人工为 arXiv 预印本、模型给正式载体：1；人工为正式载体、模型给 arXiv：2；模型未给载体：17。
- 人工标注为正式发表载体的 arXiv 预印本：17 / 30。
- 人工标注为 arXiv 预印本或未给出正式载体：13 / 30。

## 结论

**文档类型与期刊中存在显著的预印本/正式发表版本口径冲突，但年份 16 个错误中 0 个符合“模型取 arXiv 年、人工取发表年”；因此三个字段的低分不能整体归因于版本口径，年份主要仍是模型抽取或标签口径问题。**
