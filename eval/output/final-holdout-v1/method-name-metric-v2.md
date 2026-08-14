# final-holdout-v1：方法名称度量 v2

> 本报告只复算评分，不调用 API、不修改 Prompt、阈值或抽取结果。v1 和 v2 永久并列保留。

## 严格协议

- 保持原 0.90 fuzzy 阈值不变。
- 只新增：双方为空时匹配；括号内纯缩写与另一侧匹配；纯缩写与另一侧首字母缩写匹配。
- 不加入同义词表、语义相似度、阈值调整或其他宽松规则。

## 得分对照

| 字段 | v1 规则 | v2 规则 | 差值 |
|---|---:|---:|---:|
| 方法名称（无修正重试） | 3.33% | 6.67% | +3.33% |
| 方法名称（三级容错） | 3.33% | 6.67% | +3.33% |
| 8 字段宏平均（无修正重试） | 45.79% | 46.21% | +0.42% |
| 8 字段宏平均（三级容错） | 50.47% | 50.88% | +0.42% |

## 发生变化的三级容错样例

| 论文 | 命中规则 | 人工标注 | 模型输出 |
|---|---|---|---|
| f01-dual-tap-optical-digital-ffe.pdf | parenthetical_acronym | Dual-tap optical-digital feedforward equalization (DT-ODFE) | DT-ODFE |

## v2 仍判错：28 条

| 论文 | 人工标注 | 模型输出 | 情况 |
|---|---|---|---|
| f02-autoencoder-pam-imdd.pdf | Autoencoder-based neural network (NN) | Autoencoder-based constellation optimization | no_match |
| f03-cap-cup-shaped-pam.pdf | Probabilistic shaped PAM-8 cap and cup variants | Cap and Cup Maxwell-Boltzmann probabilistic shaping | no_match |
| f04-ps-4pam-short-reach.pdf | Probabilistic amplitude shaping (PAS) | Probabilistic amplitude shaping (PAS) with peak power constraint | no_match |
| f05-volterra-complexity-reduction.pdf | Structural reduction of the number of kernels | Structural kernel reduction schemes (polynomial VNLE, 2-Sam VNLE, RI-d 2-Sam VNLE) | no_match |
| f06-ps-high-speed-unamplified-imdd.pdf | Probabilistic shaping (PS) PAM-8 using cap and cup Maxwell-Boltzmann (MB) distributions | Probabilistic amplitude shaping (PAS) with Maxwell-Boltzmann distributions | no_match |
| f07-pam6-short-reach.pdf | Probabilistically-shaped PAM-6 and a framed-cross QAM-32 constellation | FC-QAM-32 and DM-PAM-6 | no_match |
| f08-achievable-rates-short-reach.pdf | Computation of achievable rates using auxiliary channels | Auxiliary channel bounds and symbol-wise MAP detection | no_match |
| f09-wiener-filter-short-reach.pdf | Wiener filter (LMMSE estimator) analytical expression taking the nonlinear SLD into account | Wiener Filter (LMMSE estimator) | no_match |
| f10-bipolar-constellations-direct-detection.pdf | Optimizing bipolar transmission with a modulator bias offset and neural network equalization with successive interference cancellation | Neural network equalizer with successive interference cancellation (NN-SIC) | no_match |
| f11-low-cost-phase-precoding.pdf | Analog phase precoding using a single additional phase modulator optimized via MSE | Low-cost analog phase precoding | no_match |
| f12-end-to-end-deep-learning.pdf | End-to-end deep neural network transceiver optimization | End-to-end deep learning | no_match |
| f13-generative-imdd-optimization.pdf | End-to-end transceiver optimization using a generative adversarial network (GAN) | Generative adversarial network (GAN) based channel model for end-to-end optimization | no_match |
| f14-deep-learning-dispersive-channels.pdf | Sliding window bidirectional recurrent neural network (SBRNN) autoencoder with weighted sequence estimation | SBRNN autoencoder | no_match |
| f15-brnn-dispersive-imdd.pdf | Sliding window bidirectional deep recurrent neural network (SBRNN) autoencoder | SBRNN (Sliding window Bidirectional Recurrent Neural Network) | no_match |
| f16-spiking-neural-demapping.pdf | Spiking neural network (SNN) nonlinear demapper on analog neuromorphic hardware (BrainScaleS-2) | SNN nonlinear demapper on BrainScaleS-2 | no_match |
| f18-silicon-photonic-neural-network.pdf | Feed-forward photonic neural network (PNN) consisting of an 8-tap time-delayed complex perceptron | 8-tap time-delayed complex perceptron based photonic neural network | no_match |
| f19-pnn-multispan-equalization.pdf | Integrated feed-forward Photonic Neural Network (PNN) with an 8-tap Finite Impulse Response filter | Feed-Forward Photonic Neural Network (PNN) | no_match |
| f20-ross-imdd-receiver.pdf | Recurrent optical spectrum slicing (ROSS) accelerators through recurrent optical filter nodes | Recurrent Optical Spectrum Slicing (ROSS) receiver | no_match |
| f21-self-coherent-mqam-ross.pdf | Direct detection aided by the recurrent optical spectrum slicing (ROSS) photonic accelerator | ROSS-based self-coherent receiver | no_match |
| f22-jones-space-field-recovery.pdf | Four-dimensional Jones space optical field recovery (4-D JSFR) scheme without local oscillator, using deep neural network-aided field recovery | 4-D JSFR | no_match |
| f23-carrierless-phase-retrieval.pdf | Dual-polarization full-field recovery using phase retrieval techniques based on dispersive elements | Polarization-diversity phase retrieval receiver | no_match |
| f24-silicon-phase-retrieval-receiver.pdf | Direct-detection phase retrieval using strong dispersion and delay lines on a compact silicon photonic chip | Silicon photonic phase retrieval receiver | no_match |
| f25-dual-polarization-field-reconstruction.pdf | Full-field signal waveform reconstruction using intensity only measurements | Modified Gerchberg-Saxton phase retrieval algorithm | no_match |
| f26-soliton-crystals-imdd.pdf | Auxiliary-assisted cavity pumping method to access lower-order soliton crystal states | Auxiliary-assisted cavity pumping method | no_match |
| f27-microresonator-comb-imdd.pdf | Microresonator frequency combs pumped with a single laser applied to direct detection transmission | Microresonator frequency comb with Turing pattern | no_match |
| f28-soliton-microcombs-fec-free.pdf | Ultra-dense WDM using a continuous laser driven microresonator soliton microcomb | Dissipative Kerr soliton microcomb | no_match |
| f29-100g-silicon-dd-mzm.pdf | Silicon dual-drive Mach-Zehnder modulator (DD-MZM) with Kramers-Kronig (KK) direct detection and single sideband (SSB) modulation | Silicon dual-drive Mach-Zehnder modulator (DD-MZM) with Kramers-Kronig (KK) direct detection | no_match |
| f30-168g-pam4-silicon-mzm.pdf | Silicon travelling wave Mach-Zehnder modulator for PAM-4 direct detection | Post filter and maximum likelihood sequence detection (MLSD) | no_match |

> 本次规则修正在看过留出集失败样例后设计，存在轻微信息泄漏；严格验证必须在新数据集上进行。
