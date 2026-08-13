"""Apply only PDF-confirmed corrections to imported Gemini final-holdout drafts."""

from __future__ import annotations

import json
from pathlib import Path


CORRECTIONS = {
    "F02-autoencoder-pam-imdd.pdf": {
        "main_results": [
            "Optimized constellations improve required signal-to-noise ratio by 4 dB for ASE-limited PAM4 and PAM8.",
            "At 53 Gbaud, simulations extend PAM4 reach by 4-8 km when combining an optimized constellation with an NN decoder.",
            "Experimental validation confirmed a 4 dB improvement for ASE-limited PAM4 at 60 Gbaud.",
        ],
        "summary": (
            "论文使用自编码器优化放大 IM/DD 链路中的 PAM 星座和神经网络解码器，"
            "在不增加主要系统复杂度的前提下改善 ASE 受限场景。53 Gbaud 仿真将 PAM4 传输距离"
            "延长 4-8 km，并在 60 Gbaud 实验中验证了 4 dB 改善。"
        ),
        "evidence": {
            "pdf_page": 1,
            "location": "Abstract and contribution list",
            "basis": "States 53 Gbaud PAM4 reach extension of 4-8 km and 60 Gbaud experimental 4 dB improvement.",
        },
    },
    "F22-jones-space-field-recovery.pdf": {
        "authors": ["Qi Wu", "Yixiao Zhu", "Hexun Jiang", "Mengfan Fu", "Yikun Zhang", "Qunbi Zhuge", "Weisheng Hu"],
        "evidence": {
            "pdf_page": 1,
            "location": "Title block and Abstract",
            "basis": "Confirms the complete author list and the 4-D JSFR method without a local oscillator.",
        },
    },
    "F25-dual-polarization-field-reconstruction.pdf": {
        "title": "Dual Polarization Full-Field Signal Waveform Reconstruction Using Intensity Only Measurements for Coherent Communications",
        "authors": ["Haoshuo Chen", "Nicolas K. Fontaine", "Joan M. Gene", "Roland Ryf", "David T. Neilson", "Gregory Raybon"],
        "experimental_conditions": [
            "Polarization-multiplexed 30-Gbaud QPSK transmission over a 520-km standard single-mode fiber span.",
            "Direct intensity measurements before and after a dispersive element, followed by a modified Gerchberg-Saxton phase-retrieval algorithm and 2x2 MIMO equalization.",
        ],
        "main_results": [
            "The modified Gerchberg-Saxton phase-retrieval algorithm has a simulated OSNR penalty below 4 dB at a BER of 2x10^-2 compared with theory.",
            "The experiment demonstrates detection and subsequent 2x2 MIMO equalization of polarization-multiplexed 30-Gbaud QPSK over 520 km SSMF using direct intensity measurements.",
        ],
        "summary": (
            "论文提出仅依赖直接强度测量的双偏振全场重建方案：利用色散元件前后的测量值和改进的"
            "Gerchberg-Saxton 相位恢复算法恢复相位，并完成 2x2 MIMO 均衡。实验展示了 30 Gbaud "
            "偏振复用 QPSK 在 520 km 标准单模光纤上的传输。"
        ),
        "evidence": {
            "pdf_page": 1,
            "location": "Title block and Abstract",
            "basis": "Confirms the title, six authors, 30-Gbaud QPSK/520-km setup, and the sub-4 dB simulated OSNR penalty.",
        },
    },
}


def apply_confirmed_corrections(label_dir: Path | str) -> list[Path]:
    """Update the three facts contradicted or incomplete in the external draft."""

    changed: list[Path] = []
    for filename, changes in CORRECTIONS.items():
        path = Path(label_dir) / f"{Path(filename).stem}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["record"].update({key: value for key, value in changes.items() if key != "evidence"})
        payload.setdefault("evidence", {}).setdefault("local_pdf_corrections", []).append(changes["evidence"])
        payload["annotation_meta"]["review_status"] = "external_ai_draft_corrected_pending_complete_audit"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed.append(path)
    return changed


if __name__ == "__main__":
    updated = apply_confirmed_corrections(Path("eval/ground_truth_final_holdout"))
    print(f"Corrected {len(updated)} final-holdout drafts using local PDF evidence.")
