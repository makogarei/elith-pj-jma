import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import html

import plotly.graph_objects as go
import streamlit as st

try:
    from anthropic import Anthropic, APIError
except ImportError:  # Streamlit will surface this nicely to the user
    Anthropic = None
    APIError = Exception

COMPETENCY_LABELS = [
    ("戦略構想力", "戦略構想力"),
    ("価値創出力", "価値創出力"),
    ("組織運営力", "組織運営力"),
    ("実行力", "実行力"),
    ("学習・適用力", "学習・適用力"),
]

READINESS_LABELS = [
    ("キャリアビジョン", "キャリアビジョン"),
    ("使命感・志", "使命感・志"),
    ("ネットワーク形成力", "ネットワーク形成力"),
]


EvaluationPayload = Dict[str, Any]


@dataclass
class StudentRecord:
    name: str
    inputs: Dict[str, str]
    evaluation: Optional[EvaluationPayload] = None


@st.cache_resource(show_spinner=False)
def get_anthropic_client() -> Anthropic:
    api_key = st.secrets.get("ANTHROPIC_API_KEY") if hasattr(st, "secrets") else None
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("環境変数 ANTHROPIC_API_KEY が設定されていません。")
    if Anthropic is None:
        raise ImportError("anthropic パッケージが見つかりません。");
    return Anthropic(api_key=api_key)


def inject_global_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #F0F2F6;
            font-family: "Noto Sans JP", "Segoe UI", sans-serif;
        }
        .block-container {
            padding-top: 32px !important;
            padding-bottom: 40px !important;
            max-width: 1600px;
        }
        h1, h2, h3 {
            color: #0f172a !important;
        }
        div[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0d3b66 0%, #061b33 100%);
            color: #f8fafc;
            border-right: 1px solid rgba(255, 255, 255, 0.12);
        }
        div[data-testid="stSidebar"] * {
            color: #e2f3ff !important;
        }
        div[data-testid="stSidebar"] h1,
        div[data-testid="stSidebar"] h2,
        div[data-testid="stSidebar"] h3,
        div[data-testid="stSidebar"] label {
            color: #f1f5f9 !important;
        }
        div[data-testid="stHeader"],
        div[data-testid="stHeader"] * {
            background-color: #F0F2F6 !important;
            color: #0f172a !important;
        }
        section.main > div {
            background-color: #F0F2F6 !important;
        }
        .streamlit-expanderHeader {
            font-weight: 600;
            background-color: rgba(148, 163, 184, 0.15);
            border-radius: 12px;
        }
        .custom-divider {
            margin: 32px 0;
            border-bottom: 1px solid #d4dbe6;
        }
        .metric-chip {
            border-radius: 14px;
            padding: 4px 12px;
            background: rgba(59, 130, 246, 0.12);
            color: #1d4ed8;
            font-size: 12px;
            font-weight: 600;
        }
        .stTextInput > div > div > input,
        .stTextArea textarea {
            background: linear-gradient(135deg, #ffffff 0%, #eef2ff 100%);
            border: 1px solid #c7d2fe;
            border-radius: 12px;
            color: #0f172a;
        }
        .stTextInput > div > div > input:focus,
        .stTextArea textarea:focus {
            outline: 2px solid #6366f1;
            box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
        }
        .stTextInput > label,
        .stTextArea > label,
        label[class^="css-"] {
            color: #1f2937 !important;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def extract_json_from_text(text: str) -> Optional[str]:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for idx, char in enumerate(text[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def call_claude(student_inputs: Dict[str, str]) -> Dict[str, Dict[str, Dict[str, str]]]:
    client = get_anthropic_client()

    system_prompt = (
        "You are an executive coaching assistant. Evaluate participants "
        "in Japanese, returning concise, actionable feedback."
    )

    input_block = []
    for section, value in student_inputs.items():
        input_block.append(f"### {section}\n{value.strip() or '未記入'}")
    joined_inputs = "\n\n".join(input_block)

    user_prompt = f"""
あなたは経営リーダー育成プログラムの評価者です。以下の受講生の入力内容をもとに、各カテゴリを5点満点の整数で評価し、点数の根拠を明確に説明してください。根拠には「どのような行動・思考ができている／不足しているため何点なのか」を端的に示してください。必ず以下のJSONフォーマットのみを出力し、余計な説明は付けないでください。スコアは1〜5の整数を使用してください。

期待するJSON構造:
{{
  "competency": {{
    "戦略構想力": {{"score": 1-5, "reason": "..."}},
    "価値創出力": {{"score": 1-5, "reason": "..."}},
    "組織運営力": {{"score": 1-5, "reason": "..."}},
    "実行力": {{"score": 1-5, "reason": "..."}},
    "学習・適用力": {{"score": 1-5, "reason": "..."}}
  }},
  "readiness": {{
    "キャリアビジョン": {{"score": 1-5, "reason": "..."}},
    "使命感・志": {{"score": 1-5, "reason": "..."}},
    "ネットワーク形成力": {{"score": 1-5, "reason": "..."}}
  }},
  "overall_summary": "受講生の全体まとめ"
}}

受講生の入力:
{joined_inputs}
"""

    response = client.messages.create(
        model="claude-opus-4-20250514",
        max_tokens=1200,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": user_prompt,
            }
        ],
    )

    if not response.content:
        raise ValueError("Claudeの応答が空でした。")

    text_content = "".join(part.text for part in response.content if hasattr(part, "text"))
    if not text_content:
        raise ValueError("Claudeの応答にテキストが含まれていません。")

    try:
        payload = json.loads(text_content)
    except json.JSONDecodeError:
        json_candidate = extract_json_from_text(text_content)
        if json_candidate is None:
            preview = text_content[:200].replace("\n", " ")
            raise ValueError(
                f"Claudeの応答をJSONとして解釈できませんでした。応答内容: {preview}"
            )
        payload = json.loads(json_candidate)

    for section in ("competency", "readiness"):
        if section not in payload:
            raise ValueError(f"Claudeの応答に{section}セクションがありません。")
        for label, _ in (COMPETENCY_LABELS if section == "competency" else READINESS_LABELS):
            section_payload = payload[section]
            if label not in section_payload:
                raise ValueError(f"{label} の評価が欠落しています。")
            score = section_payload[label].get("score")
            if not isinstance(score, int) or not (1 <= score <= 5):
                raise ValueError(f"{label} のスコアが1〜5の整数ではありません: {score}")

    return payload


def ensure_session_state() -> None:
    if "students" not in st.session_state:
        st.session_state.students: List[StudentRecord] = []
    if "cohort_summary" not in st.session_state:
        st.session_state.cohort_summary = None
    if "registration_form_version" not in st.session_state:
        st.session_state.registration_form_version = 0


def add_student_record(name: str, inputs: Dict[str, str]) -> None:
    record = StudentRecord(name=name, inputs=inputs)
    st.session_state.students.append(record)
    st.session_state.cohort_summary = None


def set_student_evaluation(index: int, evaluation: EvaluationPayload) -> None:
    st.session_state.students[index].evaluation = evaluation
    st.session_state.cohort_summary = None


def render_radar_chart(
    title: str,
    labels: List[str],
    data_series: Dict[str, List[int]],
    *,
    chart_key: Optional[str] = None,
):
    fig = go.Figure()
    angles = labels + [labels[0]]
    for series_name, scores in data_series.items():
        values = scores + [scores[0]]
        fig.add_trace(
            go.Scatterpolar(r=values, theta=angles, fill="toself", name=series_name)
        )
    fig.update_layout(polar={"radialaxis": {"range": [0, 5], "tickmode": "linear", "dtick": 1}}, showlegend=True, title=title)
    st.plotly_chart(fig, use_container_width=True, key=chart_key)


def render_divider() -> None:
    st.markdown("<div class='custom-divider'></div>", unsafe_allow_html=True)


def render_score_cards(section_title: str, entries: List[Any]) -> None:
    if not entries:
        return

    st.markdown(f"### {section_title}")
    columns = 2 if len(entries) > 2 else len(entries)
    cols = st.columns(columns or 1)

    def score_card_html(label: str, score: int, reason: str) -> str:
        safe_label = html.escape(label)
        safe_reason = html.escape(reason)
        return f"""
<div style=\"border:1px solid #d6e2ff; border-radius:18px; padding:18px; background:linear-gradient(145deg, #ffffff 0%, #f2f7ff 100%); height:100%; box-shadow:0 12px 22px rgba(15, 23, 42, 0.08);\">
  <div style=\"display:flex; justify-content:space-between; align-items:center;\">
    <div style=\"font-weight:600; font-size:15px; color:#1f2937;\">{safe_label}</div>
    <span style=\"font-size:12px; font-weight:600; color:#1d4ed8; background:rgba(29, 78, 216, 0.12); padding:4px 10px; border-radius:999px;\">評価</span>
  </div>
  <div style=\"margin:14px 0 12px; font-size:30px; font-weight:700; color:#1d4ed8;\">{score}点</div>
  <div style=\"font-size:13px; line-height:1.7; color:#0f172a;\">{safe_reason}</div>
</div>
"""

    for idx, (label, entry) in enumerate(entries):
        column = cols[idx % (columns or 1)]
        with column:
            st.markdown(score_card_html(label, entry["score"], entry["reason"]), unsafe_allow_html=True)


def render_metric_row(metrics: List[Dict[str, str]]) -> None:
    if not metrics:
        return

    cols = st.columns(len(metrics))

    def metric_html(title: str, value: str, caption: str, accent: str) -> str:
        safe_title = html.escape(title)
        safe_value = html.escape(value)
        safe_caption = html.escape(caption)
        return f"""
<div style=\"border-radius:16px; padding:18px 20px; background:{accent}; color:#0f172a; box-shadow:0 8px 18px rgba(15, 23, 42, 0.08);\">
  <div style=\"font-size:13px; font-weight:600; opacity:0.75;\">{safe_title}</div>
  <div style=\"font-size:30px; font-weight:700; margin:6px 0 10px;\">{safe_value}</div>
  <div style=\"font-size:12px; opacity:0.75;\">{safe_caption}</div>
</div>
"""

    accents = ["linear-gradient(135deg, #dce9ff 0%, #f1f6ff 100%)", "linear-gradient(135deg, #f7d9ff 0%, #fdefff 100%)", "linear-gradient(135deg, #dff8ff 0%, #f1fcff 100%)", "linear-gradient(135deg, #ffe5d4 0%, #fff3ea 100%)"]

    for idx, metric in enumerate(metrics):
        accent = accents[idx % len(accents)]
        with cols[idx]:
            st.markdown(
                metric_html(
                    metric["title"],
                    metric["value"],
                    metric.get("caption", ""),
                    accent,
                ),
                unsafe_allow_html=True,
            )


def render_evaluation_overview(records: List[StudentRecord]) -> None:
    total = len(records)
    evaluated = [record for record in records if record.evaluation]
    evaluated_count = len(evaluated)
    pending_count = total - evaluated_count

    metrics = [
        {
            "title": "登録済み受講生",
            "value": f"{total}名",
            "caption": "現在ダッシュボードに登録されている人数",
        },
        {
            "title": "評価完了",
            "value": f"{evaluated_count}名",
            "caption": f"未評価 {pending_count}名",
        },
    ]

    stats = compute_cohort_stats(records)
    if stats:
        comp_avg = sum(stats["avg_competency"].values()) / len(COMPETENCY_LABELS)
        readiness_avg = sum(stats["avg_readiness"].values()) / len(READINESS_LABELS)
        overall_avg = (comp_avg + readiness_avg) / 2
        metrics.append(
            {
                "title": "平均総合スコア",
                "value": f"{overall_avg:.1f}点",
                "caption": "コンピテンシーと経営者準備度の平均",
            }
        )

    render_metric_row(metrics)


def render_student_card(
    record: StudentRecord,
    show_header: bool = True,
    *,
    key_prefix: Optional[str] = None,
):
    if record.evaluation is None:
        st.warning("まだ評価が実行されていません。")
        return

    if show_header:
        st.subheader(f"{record.name} の評価")

    competency_scores = []
    readiness_scores = []
    competency_entries = []
    readiness_entries = []

    for label, _ in COMPETENCY_LABELS:
        entry = record.evaluation["competency"][label]
        competency_scores.append(entry["score"])
        competency_entries.append((label, entry))

    for label, _ in READINESS_LABELS:
        entry = record.evaluation["readiness"][label]
        readiness_scores.append(entry["score"])
        readiness_entries.append((label, entry))

    comp_avg = sum(competency_scores) / len(COMPETENCY_LABELS)
    readiness_avg = sum(readiness_scores) / len(READINESS_LABELS)
    all_entries = competency_entries + readiness_entries
    top_area, top_entry = max(all_entries, key=lambda item: item[1]["score"])
    growth_area, growth_entry = min(all_entries, key=lambda item: item[1]["score"])

    render_metric_row(
        [
            {
                "title": "平均コンピテンシー",
                "value": f"{comp_avg:.1f}点",
                "caption": "全5指標の平均スコア",
            },
            {
                "title": "平均経営者準備度",
                "value": f"{readiness_avg:.1f}点",
                "caption": "全3指標の平均スコア",
            },
            {
                "title": "強み/伸びしろ",
                "value": f"{top_area} {top_entry['score']}点",
                "caption": f"課題: {growth_area} {growth_entry['score']}点",
            },
        ]
    )

    render_score_cards("コンピテンシー評価", competency_entries)
    render_score_cards("経営者準備度評価", readiness_entries)

    st.markdown("---")
    st.markdown(f"**受講生の全体まとめ:** {record.evaluation.get('overall_summary', '（未提供）')}")

    prefix = key_prefix or record.name
    normalized_prefix = prefix.replace(" ", "_")

    render_radar_chart(
        f"{record.name} - コンピテンシー評価",
        [label for label, _ in COMPETENCY_LABELS],
        {record.name: competency_scores},
        chart_key=f"{normalized_prefix}_competency_radar",
    )
    render_radar_chart(
        f"{record.name} - 経営者準備度",
        [label for label, _ in READINESS_LABELS],
        {record.name: readiness_scores},
        chart_key=f"{normalized_prefix}_readiness_radar",
    )


def compute_cohort_stats(records: List[StudentRecord]):
    evaluated_records = [record for record in records if record.evaluation]
    if not evaluated_records:
        return None

    competency_totals = {label: 0 for label, _ in COMPETENCY_LABELS}
    readiness_totals = {label: 0 for label, _ in READINESS_LABELS}

    for record in evaluated_records:
        for label, _ in COMPETENCY_LABELS:
            competency_totals[label] += record.evaluation["competency"][label]["score"]
        for label, _ in READINESS_LABELS:
            readiness_totals[label] += record.evaluation["readiness"][label]["score"]

    student_count = len(evaluated_records)
    competency_avg = {label: round(total / student_count, 2) for label, total in competency_totals.items()}
    readiness_avg = {label: round(total / student_count, 2) for label, total in readiness_totals.items()}

    return {
        "avg_competency": competency_avg,
        "avg_readiness": readiness_avg,
        "student_count": student_count,
    }


def build_cohort_summary(stats: Dict[str, Dict[str, float]]) -> str:
    competency_sorted = sorted(stats["avg_competency"].items(), key=lambda x: x[1], reverse=True)
    readiness_sorted = sorted(stats["avg_readiness"].items(), key=lambda x: x[1], reverse=True)

    top_comp = [label for label, score in competency_sorted if score == competency_sorted[0][1]]
    bottom_comp = [label for label, score in competency_sorted if score == competency_sorted[-1][1]]
    top_ready = [label for label, score in readiness_sorted if score == readiness_sorted[0][1]]
    bottom_ready = [label for label, score in readiness_sorted if score == readiness_sorted[-1][1]]

    summary_parts = [
        f"全{stats['student_count']}名の平均スコアで最も高かったのは {', '.join(top_comp)} です。",
        f"一方、伸びしろが大きいのは {', '.join(bottom_comp)} でした。",
        f"経営者準備度では {', '.join(top_ready)} が相対的に高く、 {', '.join(bottom_ready)} が課題として浮かび上がっています。",
    ]

    return " ".join(summary_parts)


def render_cohort_section(records: List[StudentRecord]):
    st.header("受講生全体の可視化")
    evaluated_records = [record for record in records if record.evaluation]
    stats = compute_cohort_stats(records)
    if not stats:
        st.session_state.cohort_summary = None
        st.info("まだ評価済みの受講生はいません。")
        return

    cohort_comp_avg = sum(stats["avg_competency"].values()) / len(COMPETENCY_LABELS)
    cohort_ready_avg = sum(stats["avg_readiness"].values()) / len(READINESS_LABELS)
    top_competency = max(stats["avg_competency"].items(), key=lambda item: item[1])
    top_readiness = max(stats["avg_readiness"].items(), key=lambda item: item[1])

    render_metric_row(
        [
            {
                "title": "平均コンピテンシー",
                "value": f"{cohort_comp_avg:.1f}点",
                "caption": "全受講生の5指標平均",
            },
            {
                "title": "平均経営者準備度",
                "value": f"{cohort_ready_avg:.1f}点",
                "caption": "全受講生の3指標平均",
            },
            {
                "title": "相対的な強み",
                "value": f"{top_competency[0]} / {top_readiness[0]}",
                "caption": "最もスコアが高かったカテゴリ",
            },
        ]
    )

    render_radar_chart(
        "平均コンピテンシー",
        [label for label, _ in COMPETENCY_LABELS],
        {
            "平均": [
                stats["avg_competency"][label]
                for label, _ in COMPETENCY_LABELS
            ]
        },
        chart_key="cohort_avg_competency",
    )
    render_radar_chart(
        "平均経営者準備度",
        [label for label, _ in READINESS_LABELS],
        {
            "平均": [
                stats["avg_readiness"][label]
                for label, _ in READINESS_LABELS
            ]
        },
        chart_key="cohort_avg_readiness",
    )

    multi_series_competency = {}
    multi_series_readiness = {}
    for record in evaluated_records:
        multi_series_competency[record.name] = [
            record.evaluation["competency"][label]["score"] for label, _ in COMPETENCY_LABELS
        ]
        multi_series_readiness[record.name] = [
            record.evaluation["readiness"][label]["score"] for label, _ in READINESS_LABELS
        ]

    render_radar_chart(
        "受講生比較 - コンピテンシー",
        [label for label, _ in COMPETENCY_LABELS],
        multi_series_competency,
        chart_key="cohort_compare_competency",
    )
    render_radar_chart(
        "受講生比較 - 経営者準備度",
        [label for label, _ in READINESS_LABELS],
        multi_series_readiness,
        chart_key="cohort_compare_readiness",
    )

    if st.session_state.cohort_summary is None:
        st.session_state.cohort_summary = build_cohort_summary(stats)

    st.markdown(f"**受講生全体まとめ:** {st.session_state.cohort_summary}")


def render_individual_results(records: List[StudentRecord]):
    st.subheader("受講生個別結果")
    evaluated_records = [record for record in records if record.evaluation]
    if not evaluated_records:
        st.info("まだ評価済みの受講生がありません。評価を実行してください。")
        return

    if len(evaluated_records) == 1:
        record = evaluated_records[0]
        st.markdown(f"### {record.name} の評価詳細")
        render_student_card(record, show_header=False, key_prefix=f"individual_single_{record.name}")
        return

    options = {record.name: record for record in evaluated_records}
    selected_name = st.selectbox(
        "結果を確認したい受講生を選択",
        list(options.keys()),
        key="individual_result_select",
        help="比較したい受講生を選択すると詳細が表示されます",
    )
    selected_record = options[selected_name]
    st.markdown(f"### {selected_record.name} の評価詳細")
    render_student_card(
        selected_record,
        show_header=False,
        key_prefix=f"individual_select_{selected_name}",
    )


REGISTRATION_FIELD_KEYS = {
    "name": "registration_name",
    "mgmt_action_1": "registration_mgmt_action_1",
    "mgmt_action_2": "registration_mgmt_action_2",
    "mgmt_result_1": "registration_mgmt_result_1",
    "mgmt_result_2": "registration_mgmt_result_2",
    "mgmt_learnings": "registration_mgmt_learnings",
    "manage_awareness_1": "registration_manage_awareness_1",
    "manage_awareness_2": "registration_manage_awareness_2",
    "manage_awareness_3": "registration_manage_awareness_3",
    "manage_ten_year": "registration_manage_ten_year",
    "vision": "registration_vision",
    "action_plan": "registration_action_plan",
    "values": "registration_values",
}


def reset_registration_form() -> None:
    st.session_state.registration_form_version += 1


def render_registration_page() -> None:
    version = st.session_state.registration_form_version

    def widget_key(field: str) -> str:
        return f"{REGISTRATION_FIELD_KEYS[field]}_{version}"

    st.header("受講生の登録")
    st.caption("必要事項を入力して受講生を登録してください。評価は別ページで実行できます。")
    st.markdown("<span class='metric-chip'>STEP 1</span> 受講生情報の入力", unsafe_allow_html=True)
    st.write("各セクションを展開し、現状の取り組みや気づきを整理してください。")

    with st.form("student_form"):
        name = st.text_input(
            "受講生名",
            key=widget_key("name"),
            placeholder="例：田中 太郎",
            help="評価結果に表示される氏名を入力してください",
        )

        with st.expander("管理課題", expanded=True):
            mgmt_col1, mgmt_col2 = st.columns(2)
            with mgmt_col1:
                mgmt_action_1 = st.text_area(
                    "①具体的な取り組み(ｱｸｼｮﾝﾗｰﾆﾝｸﾞの学びから)",
                    key=widget_key("mgmt_action_1"),
                    placeholder="研修で学んだ内容をどのように実践したかを入力",
                )
                mgmt_action_2 = st.text_area(
                    "②具体的な取り組み（職場で実践したこと）",
                    key=widget_key("mgmt_action_2"),
                    placeholder="現場での具体的なアクションや仕組み化の内容",
                )
            with mgmt_col2:
                mgmt_result_1 = st.text_area(
                    "①の対してのプロセス・結果",
                    key=widget_key("mgmt_result_1"),
                    placeholder="取り組みのプロセスや成果・課題を入力",
                )
                mgmt_result_2 = st.text_area(
                    "②の対してのプロセス・結果",
                    key=widget_key("mgmt_result_2"),
                    placeholder="実践の結果やチームへの影響など",
                )
            mgmt_learnings = st.text_area(
                "①②に対しての気づき",
                key=widget_key("mgmt_learnings"),
                placeholder="取り組みを通じて得た学びや次のアクション",
            )

        with st.expander("経営課題", expanded=True):
            manage_awareness_col1, manage_awareness_col2 = st.columns(2)
            with manage_awareness_col1:
                manage_awareness_1 = st.text_area(
                    "①私の危機感・機会感",
                    key=widget_key("manage_awareness_1"),
                    placeholder="事業・組織に関する危機感やチャンスを入力",
                )
                manage_awareness_3 = st.text_area(
                    "③私の危機感・機会感",
                    key=widget_key("manage_awareness_3"),
                    placeholder="視座を変えた第三の視点があれば記載",
                )
            with manage_awareness_col2:
                manage_awareness_2 = st.text_area(
                    "②私の危機感・機会感",
                    key=widget_key("manage_awareness_2"),
                    placeholder="他部署や市場環境に関する気づきなど",
                )
                manage_ten_year = st.text_area(
                    "10年先を見通した全社課題",
                    key=widget_key("manage_ten_year"),
                    placeholder="長期の経営課題や必要な変革について",
                )

        with st.expander("経営宣言", expanded=True):
            vision = st.text_area(
                "夢、ビジョン",
                key=widget_key("vision"),
                placeholder="自分が描く理想の組織・未来像",
            )
            action_plan = st.text_area(
                "ビジョン実現のために、自身はどう行動するか。そのために自己をどう変えていくのか",
                key=widget_key("action_plan"),
                placeholder="実現に向けた具体的な行動と変化させたい点",
            )
            values = st.text_area(
                "経営リーダーとして大切にしたい価値観（軸）、信念",
                key=widget_key("values"),
                placeholder="意思決定で守りたい価値観や信念",
            )

        submitted = st.form_submit_button("受講生を登録する", type="primary")

        if submitted:
            if not name.strip():
                st.error("受講生名を入力してください。")
            else:
                student_inputs = {
                    "受講生名": name.strip(),
                    "管理課題 ①具体的な取り組み": mgmt_action_1,
                    "管理課題 ①プロセス・結果": mgmt_result_1,
                    "管理課題 ②具体的な取り組み": mgmt_action_2,
                    "管理課題 ②プロセス・結果": mgmt_result_2,
                    "管理課題 気づき": mgmt_learnings,
                    "経営課題 ①危機感・機会感": manage_awareness_1,
                    "経営課題 ②危機感・機会感": manage_awareness_2,
                    "経営課題 ③危機感・機会感": manage_awareness_3,
                    "経営課題 10年先の全社課題": manage_ten_year,
                    "経営宣言 夢・ビジョン": vision,
                    "経営宣言 行動と変化": action_plan,
                    "経営宣言 価値観・信念": values,
                }
                add_student_record(name.strip(), student_inputs)
                st.success(f"{name.strip()} を登録しました。評価は『評価ダッシュボード』ページで実行できます。")
                reset_registration_form()

    render_divider()

    st.subheader("登録済み受講生")
    if st.session_state.students:
        for record in st.session_state.students:
            status = "評価済み" if record.evaluation else "未評価"
            st.markdown(f"- {record.name} （{status}）")
    else:
        st.info("まだ受講生が登録されていません。")


def run_student_evaluation(index: int) -> bool:
    try:
        evaluation = call_claude(st.session_state.students[index].inputs)
    except (ValueError, ImportError, APIError) as exc:
        st.error(f"評価の呼び出し中にエラーが発生しました: {exc}")
        return False
    set_student_evaluation(index, evaluation)
    return True


def render_evaluation_page() -> None:
    st.header("評価ダッシュボード")
    st.markdown("<span class='metric-chip'>STEP 2</span> Claude評価と分析", unsafe_allow_html=True)

    if not st.session_state.students:
        st.info("『受講生登録』ページで受講生を登録すると、ここで評価できます。")
        return

    students = st.session_state.students
    pending_indices = [idx for idx, record in enumerate(students) if record.evaluation is None]

    if pending_indices:
        if st.button("未評価の受講生を一括評価", type="primary"):
            completed_names = []
            with st.spinner("未評価の受講生を順番に評価しています..."):
                for idx in pending_indices:
                    if run_student_evaluation(idx):
                        completed_names.append(students[idx].name)
                    else:
                        break
            if completed_names:
                st.success("、".join(completed_names) + " の評価が完了しました。")

    render_evaluation_overview(students)
    render_divider()

    single_student_mode = len(students) == 1

    if single_student_mode:
        record = students[0]
        st.subheader(f"{record.name} の評価")
        if record.evaluation:
            render_student_card(
                record,
                show_header=False,
                key_prefix=f"single_mode_{record.name}",
            )
        else:
            st.info("まだ評価が実行されていません。下記の内容を確認し、評価を実行してください。")
            st.markdown("**登録内容プレビュー**")
            for section, value in record.inputs.items():
                st.markdown(f"- {section}: {value.strip() or '未記入'}")
            if st.button("Claudeで評価する", type="primary", key="single_student_evaluate"):
                with st.spinner(f"{record.name} を評価しています..."):
                    if run_student_evaluation(0):
                        st.success(f"{record.name} の評価が完了しました。")
        return

    render_individual_results(students)

    render_divider()

    for idx, record in enumerate(students):
        expanded = record.evaluation is None
        with st.expander(record.name, expanded=expanded):
            status = "評価済み" if record.evaluation else "未評価"
            st.markdown(f"**評価ステータス**: {status}")
            if record.evaluation:
                render_student_card(
                    record,
                    show_header=False,
                    key_prefix=f"expander_{idx}_{record.name}",
                )
            else:
                st.markdown("**登録内容プレビュー**")
                for section, value in record.inputs.items():
                    st.markdown(f"- {section}: {value.strip() or '未記入'}")
                if st.button("Claudeで評価する", key=f"evaluate_{idx}"):
                    with st.spinner(f"{record.name} を評価しています..."):
                        if run_student_evaluation(idx):
                            st.success(f"{record.name} の評価が完了しました。")

    evaluated_records = [record for record in students if record.evaluation]
    if evaluated_records:
        render_divider()
        render_cohort_section(students)
    else:
        st.info("まだ評価済みの受講生がありません。未評価の受講生を評価してください。")


PAGE_TITLE = "受講生評価ダッシュボード"
st.set_page_config(page_title=PAGE_TITLE, page_icon="📊", layout="wide")
ensure_session_state()
inject_global_styles()

st.sidebar.title("ナビゲーション")
NAVIGATION_OPTIONS = ["受講生登録", "評価ダッシュボード"]
current_page = st.sidebar.radio("ページを選択してください", NAVIGATION_OPTIONS)

st.title(PAGE_TITLE)

if current_page == NAVIGATION_OPTIONS[0]:
    render_registration_page()
else:
    render_evaluation_page()
