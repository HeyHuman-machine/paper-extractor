"""M8 Streamlit：PaperExtractor 的正式操作界面。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.api_client import APIClientError, PaperExtractorAPI  # noqa: E402
from ui.view_models import (  # noqa: E402
    failure_rows,
    result_summary_rows,
    task_rows,
)


load_dotenv(PROJECT_ROOT / ".env", override=False)
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="PaperExtractor",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
          --pe-ink: #1d2b3a;
          --pe-muted: #6d7b8b;
          --pe-line: #dce5ec;
          --pe-accent: #3c68ed;
          --pe-cyan: #5caed0;
          --pe-soft: #f4f7fb;
        }
        .stApp { background: #f7f9fc; color: var(--pe-ink); }
        [data-testid="stHeader"] { background: transparent; }
        [data-testid="stSidebar"] {
          background: linear-gradient(165deg, #0f1e38 0%, #173b68 100%);
          border-right: 1px solid rgba(125, 170, 220, .25);
        }
        [data-testid="stSidebar"] * { color: #eaf3ff; }
        [data-testid="stSidebar"] .stRadio label {
          padding: .58rem .7rem; border-radius: 10px; margin: .12rem 0;
        }
        [data-testid="stSidebar"] .stRadio label:hover {
          background: rgba(101, 137, 255, .15);
        }
        .block-container { max-width: 1480px; padding-top: 2rem; padding-bottom: 3rem; }
        h1, h2, h3 { color: var(--pe-ink); letter-spacing: -.02em; }
        .pe-brand { font-size: 1.45rem; font-weight: 760; margin: .45rem 0 .2rem; }
        .pe-subtle { color: var(--pe-muted); font-size: .95rem; margin-bottom: 1.35rem; }
        .pe-status-ok, .pe-status-off {
          display: inline-flex; align-items: center; gap: .45rem;
          padding: .42rem .72rem; border-radius: 9px; font-size: .88rem;
          border: 1px solid rgba(104, 157, 191, .35);
        }
        .pe-status-ok { background: #eaf8f2; color: #197555; }
        .pe-status-off { background: #fff1f1; color: #a53b43; }
        .pe-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
        [data-testid="stFileUploaderDropzone"] {
          min-height: 154px; background: #fbfdff; border: 1.5px dashed #87a8ef;
          border-radius: 14px;
        }
        [data-testid="stMetric"] {
          background: #fff; border: 1px solid var(--pe-line); border-radius: 12px;
          padding: .85rem 1rem;
        }
        [data-testid="stDataFrame"] {
          border: 1px solid var(--pe-line); border-radius: 12px; overflow: hidden;
          background: #fff;
        }
        .stButton > button[kind="primary"] {
          background: linear-gradient(100deg, #315fdc, #6279ef);
          border: 0; box-shadow: 0 8px 20px rgba(54, 91, 204, .18);
        }
        .stButton > button, .stDownloadButton > button { border-radius: 9px; }
        [data-testid="stAlert"] { border-radius: 11px; }
        .pe-section {
          border-top: 1px solid var(--pe-line); padding-top: 1.1rem; margin-top: 1.4rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource
def api_client() -> PaperExtractorAPI:
    return PaperExtractorAPI(API_BASE_URL)


def page_header(title: str, description: str) -> None:
    title_col, status_col = st.columns([5, 1.25], vertical_alignment="center")
    with title_col:
        st.title(title)
        st.markdown(f'<div class="pe-subtle">{description}</div>', unsafe_allow_html=True)
    with status_col:
        connected = api_client().health()
        css = "pe-status-ok" if connected else "pe-status-off"
        text = "M7 API 已连接" if connected else "M7 API 未连接"
        st.markdown(
            f'<div class="{css}"><span class="pe-dot"></span>{text}</div>',
            unsafe_allow_html=True,
        )


def task_metrics(task: dict[str, Any]) -> None:
    columns = st.columns(5)
    values = [
        ("任务 ID", task["id"]),
        ("文件总数", task["total_files"]),
        ("成功", task["success_count"]),
        ("失败", task["fail_count"]),
        ("总耗时", f"{task['duration_ms'] / 1000:.2f}s"),
    ]
    for column, (label, value) in zip(columns, values, strict=True):
        column.metric(label, value)


def exports(task_id: int, *, key_prefix: str) -> None:
    excel_col, json_col, _ = st.columns([1, 1, 4])
    try:
        excel, excel_name = api_client().download_export(task_id, "xlsx")
        json_data, json_name = api_client().download_export(task_id, "json")
    except APIClientError as exc:
        st.warning(f"导出文件暂不可用：{exc}")
        return
    excel_col.download_button(
        "下载 Excel",
        excel,
        file_name=excel_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key_prefix}-xlsx",
        width="stretch",
    )
    json_col.download_button(
        "下载 JSON",
        json_data,
        file_name=json_name,
        mime="application/json",
        key=f"{key_prefix}-json",
        width="stretch",
    )


def show_task_detail(payload: dict[str, Any], *, key_prefix: str) -> None:
    task = payload["task"]
    task_metrics(task)
    st.markdown("### 结构化结果")
    if payload["results"]:
        st.dataframe(
            pd.DataFrame(result_summary_rows(payload["results"])),
            hide_index=True,
            width="stretch",
            height=min(540, 92 + 70 * len(payload["results"])),
        )
        selected_index = st.selectbox(
            "查看论文完整字段",
            options=range(len(payload["results"])),
            format_func=lambda index: payload["results"][index]["filename"],
            key=f"{key_prefix}-paper",
        )
        show_record(payload["results"][selected_index])
    else:
        st.info("本任务没有成功结果，请到“失败诊断”查看原因。")
    exports(task["id"], key_prefix=key_prefix)


def show_record(record: dict[str, Any]) -> None:
    """用分区文本展示单篇完整字段，避免 12 列表格横向裁切。"""

    with st.expander("完整结构化字段", expanded=False):
        left, right = st.columns(2)
        left.markdown(f"**标题**  \n{record['title']}")
        left.markdown(f"**作者**  \n{'、'.join(record['authors'])}")
        left.markdown(f"**年份 / 期刊**  \n{record.get('year') or '—'} · {record.get('venue') or '—'}")
        left.markdown(f"**研究问题**  \n{record['problem']}")
        left.markdown(f"**方法名称**  \n{record.get('method_name') or '—'}")
        right.markdown("**实验条件**")
        right.markdown(_bullet_text(record.get("experimental_conditions", [])))
        right.markdown("**主要结果**")
        right.markdown(_bullet_text(record.get("main_results", [])))
        right.markdown(f"**局限性**  \n{record.get('limitations') or '论文未明确陈述'}")
        st.markdown(f"**摘要总结**  \n{record['summary']}")


def _bullet_text(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values) or "- 论文未明确给出"


def new_task_page() -> None:
    page_header("新建任务", "上传 PDF / DOCX，交给 M7 完成抽取、校验、入库与导出。")
    uploaded_files = st.file_uploader(
        "将论文拖到此处，或点击选择文件",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        help="支持一次选择多篇论文；只有开始处理后才会调用 DeepSeek。",
    )

    if uploaded_files:
        st.markdown(f"### 待处理文件（{len(uploaded_files)}）")
        file_rows = [
            {
                "文件名": file.name,
                "类型": Path(file.name).suffix.lower(),
                "大小": f"{file.size / 1024 / 1024:.2f} MB",
            }
            for file in uploaded_files
        ]
        st.dataframe(pd.DataFrame(file_rows), hide_index=True, width="stretch")

    if st.button(
        "开始处理",
        type="primary",
        disabled=not uploaded_files,
        width="content",
    ):
        if not api_client().health():
            st.error("M7 API 未启动。请先运行“ M7：启动 FastAPI ”。")
            return
        progress = st.progress(8, text="正在把论文安全上传到 M7…")
        with st.status("M7 正在处理论文", expanded=True) as status:
            st.write("M1：解析 PDF / DOCX 文本")
            st.write("M2～M3：DeepSeek 抽取并通过 Pydantic 校验")
            st.write("M4～M5：汇总结果并保存 SQLite")
            progress.progress(30, text="等待 M7 完成整批处理；请勿关闭页面…")
            try:
                payload = api_client().create_task(uploaded_files)
            except APIClientError as exc:
                progress.empty()
                status.update(label="处理失败", state="error", expanded=True)
                st.error(str(exc))
                return
            progress.progress(100, text="处理完成")
            status.update(label=f"任务 #{payload['task']['id']} 已完成", state="complete")
        st.session_state["latest_task"] = payload

    if "latest_task" in st.session_state:
        st.markdown('<div class="pe-section"></div>', unsafe_allow_html=True)
        show_task_detail(st.session_state["latest_task"], key_prefix="new-task")


def history_page() -> None:
    page_header("历史任务", "按 task_id 回看每次批处理，不会重新调用 DeepSeek。")
    try:
        payload = api_client().list_tasks()
    except APIClientError as exc:
        st.error(str(exc))
        return
    tasks = payload["items"]
    if not tasks:
        st.info("还没有历史任务。先到“新建任务”上传论文。")
        return
    st.dataframe(pd.DataFrame(task_rows(tasks)), hide_index=True, width="stretch")
    task_id = st.selectbox(
        "查看任务详情",
        options=[task["id"] for task in tasks],
        format_func=lambda value: f"任务 #{value}",
    )
    try:
        detail = api_client().get_task(task_id)
    except APIClientError as exc:
        st.error(str(exc))
        return
    show_task_detail(detail, key_prefix=f"history-{task_id}")


def failures_page() -> None:
    page_header("失败诊断", "按失败阶段定位解析、API、JSON 或 Schema 问题。")
    try:
        tasks = api_client().list_tasks()["items"]
    except APIClientError as exc:
        st.error(str(exc))
        return
    if not tasks:
        st.info("当前没有可诊断的任务。")
        return
    task_id = st.selectbox(
        "选择任务",
        options=[task["id"] for task in tasks],
        format_func=lambda value: f"任务 #{value}",
        key="failure-task",
    )
    try:
        failures = api_client().get_failures(task_id)["failures"]
    except APIClientError as exc:
        st.error(str(exc))
        return
    if not failures:
        st.success("这个任务没有失败文件。")
        return
    st.dataframe(pd.DataFrame(failure_rows(failures)), hide_index=True, width="stretch")
    st.markdown("### 原始诊断")
    for failure in failures:
        with st.expander(f"{failure['filename']} · {failure['error_type']}"):
            st.write(failure["error_msg"])
            st.code(failure.get("raw_output") or "没有模型原始输出", language="json")


def evaluation_page() -> None:
    page_header("评测", "M9 将在这里展示字段准确率和容错前后对比。")
    st.info("评测模块将在 M9 接入。当前不展示虚构准确率，避免把演示数据当成真实结果。")
    st.markdown(
        """
        ### M9 会提供

        - 20 篇人工标注论文的正确答案
        - 标题、年份、作者、实验条件等字段的准确率 / F1
        - 无重试与三级容错两轮结果对比
        - 可写入简历的真实评测报告和柱状图
        """
    )


def main() -> None:
    inject_styles()
    with st.sidebar:
        st.markdown('<div class="pe-brand">▣ PaperExtractor</div>', unsafe_allow_html=True)
        st.caption("光通信论文结构化抽取平台")
        page = st.radio(
            "功能导航",
            ["新建任务", "历史任务", "失败诊断", "评测"],
            label_visibility="collapsed",
        )
        st.divider()
        connected = api_client().health()
        st.caption("M7 API")
        st.write("● 已连接" if connected else "● 未连接")
        st.caption(f"模型：{os.getenv('LLM_MODEL', '未配置')}")

    pages = {
        "新建任务": new_task_page,
        "历史任务": history_page,
        "失败诊断": failures_page,
        "评测": evaluation_page,
    }
    pages[page]()


if __name__ == "__main__":
    main()
