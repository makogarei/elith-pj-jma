import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from statistics import mean

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


GROUP_TRAINING_SAMPLE_PROGRAMS = [
    {
        "実施枠": "Day1 午前",
        "テーマ": "経営環境の俯瞰",
        "目的": "中長期の事業課題を言語化する",
        "形式": "講義 + グループ対話",
        "担当": "経営企画部",
    },
    {
        "実施枠": "Day1 午後",
        "テーマ": "ケーススタディ: 事業再構築",
        "目的": "意思決定とリスク整理をシミュレーションする",
        "形式": "ケース討議",
        "担当": "戦略推進室",
    },
    {
        "実施枠": "Day2 午前",
        "テーマ": "イノベーションワーク",
        "目的": "新規価値創出の構想を描く",
        "形式": "プロトタイピング演習",
        "担当": "DX推進部",
    },
]

GROUP_TRAINING_FEEDBACK_DIMENSIONS = [
    ("受講満足度", "プログラム全体の満足度"),
    ("理解度", "学んだ内容の理解度"),
    ("実践意欲", "現場での活用意欲"),
    ("チーム連携度", "他部署との連携意欲"),
]

GROUP_TRAINING_SAMPLE_FEEDBACK = [
    {
        "参加者名": "佐藤 花子",
        "所属 / 役職": "営業部 マネージャー",
        "受講満足度": 5,
        "理解度": 4,
        "実践意欲": 5,
        "チーム連携度": 4,
        "コメント": "経営視点の議論が有益で、部門間連携のヒントになった。",
    },
    {
        "参加者名": "田中 健",
        "所属 / 役職": "製造部 課長",
        "受講満足度": 4,
        "理解度": 4,
        "実践意欲": 4,
        "チーム連携度": 5,
        "コメント": "現場改善のアイデアを他部署と議論できた。",
    },
    {
        "参加者名": "山本 美咲",
        "所属 / 役職": "人材開発室",
        "受講満足度": 5,
        "理解度": 5,
        "実践意欲": 4,
        "チーム連携度": 5,
        "コメント": "アクションプランの共有で参加者の一体感が高まった。",
    },
]


EvaluationPayload = Dict[str, Any]


GOAL_SETTING_CRITERIA = [
    "ストレッチした目標表現に言及されている",
    "目的・目標を分けて明確な目標表現をしようとしている",
    "目標設定後メンバーから納得を引き出そうとしている",
    "目標設定がメンバーの行動を決めるとして重要性を理解している",
    "目標設定のための準備をしっかりと取ろうとしている",
    "目標設定の重要性を表記している",
    "目標設定は将来の成果を予め設定したものといった観点で表記されている",
    "方針やビジョンと関連させようとした目標設定にしている",
]


GROUP_TRAINING_SECTIONS = [
    (
        "講座情報",
        [
            ("course_url", "講座説明のURL", "text_input"),
        ],
    ),
    (
        "事前課題",
        [
            ("org_expectation", "会社または上司からの受講者への期待", "text_area"),
            ("participant_expectation", "受講に対する事前期待（受講者記入）", "text_area"),
        ],
    ),
    (
        "研修当日記入",
        [
            ("role_capability", "①管理者の役割と求められる能力・資質", "text_area"),
            ("goal_setting", "②目標設定能力を高めるには", "text_area"),
            ("planning", "③計画能力を伸ばすには", "text_area"),
            ("organization", "④組織化能力を高めるには", "text_area"),
            ("communication", "⑤コミュニケーション能力を高めるには", "text_area"),
            ("motivation", "⑥動機づけ能力を伸ばすには", "text_area"),
            ("development", "⑦使命としての部下・メンバー育成", "text_area"),
            (
                "reflection",
                "研修を振り返って、自分が目指す管理職になるため 取り組むことや取り組みたい事について記入してください。",
                "text_area",
            ),
        ],
    ),
]


GROUP_TRAINING_FIELD_KEYS = {
    "name": "group_training_name",
    "course_url": "group_training_course_url",
    "org_expectation": "group_training_org_expectation",
    "participant_expectation": "group_training_participant_expectation",
    "role_capability": "group_training_role_capability",
    "goal_setting": "group_training_goal_setting",
    "planning": "group_training_planning",
    "organization": "group_training_organization",
    "communication": "group_training_communication",
    "motivation": "group_training_motivation",
    "development": "group_training_development",
    "reflection": "group_training_reflection",
}


GROUP_TRAINING_NAV_OPTIONS = ["受講者入力", "評価デモ(JMA様用)", "評価デモ(クライアント用)"]


@dataclass
class StudentRecord:
    name: str
    inputs: Dict[str, str]
    evaluation: Optional[EvaluationPayload] = None


@dataclass
class GroupTrainingParticipant:
    name: str
    inputs: Dict[str, str]
    evaluation: Optional[Dict[str, Any]] = None


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


def call_goal_setting_evaluation(participant_inputs: Dict[str, str]) -> Dict[str, Any]:
    client = get_anthropic_client()
    system_prompt = (
        "You are an experienced facilitator for management training. "
        "Score participants' goal-setting capability in Japanese."
    )

    input_block = []
    for section, value in participant_inputs.items():
        input_block.append(f"### {section}\n{value.strip() or '未記入'}")
    joined_inputs = "\n\n".join(input_block)

    criteria_lines = "\n".join(
        f"    \"{label}\": {{\"score\": 1-5, \"reason\": \"...\"}}" for label in GOAL_SETTING_CRITERIA
    )

    user_prompt = f"""
あなたは管理職研修の評価者です。以下の受講者入力を分析し、目標設定能力に関する8観点を5点満点の整数で評価してください。各観点について、観点ごとの行動や記述の有無を踏まえた評価根拠を簡潔に記載してください。必ず下記のJSONフォーマットのみを出力し、余分な文章は含めないでください。

期待するJSON構造:
{{
  "goal_setting": {{
{criteria_lines}
  }},
  "overall_summary": "観点全体を踏まえた講評"
}}

受講者の入力:
{joined_inputs}
"""

    response = client.messages.create(
        model="claude-opus-4-20250514",
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
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

    goal_section = payload.get("goal_setting")
    if not isinstance(goal_section, dict):
        raise ValueError("goal_setting セクションが見つからないか不正です。")

    for label in GOAL_SETTING_CRITERIA:
        if label not in goal_section:
            raise ValueError(f"{label} の評価が欠落しています。")
        entry = goal_section[label]
        score = entry.get("score") if isinstance(entry, dict) else None
        reason = entry.get("reason") if isinstance(entry, dict) else None
        if not isinstance(score, int) or not (1 <= score <= 5):
            raise ValueError(f"{label} のスコアが1〜5の整数ではありません: {score}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{label} の評価根拠が不正です。")

    summary = payload.get("overall_summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("overall_summary が欠落しているか不正です。")

    return payload


def ensure_session_state() -> None:
    if "students" not in st.session_state:
        st.session_state.students: List[StudentRecord] = []
    if "cohort_summary" not in st.session_state:
        st.session_state.cohort_summary = None
    if "registration_form_version" not in st.session_state:
        st.session_state.registration_form_version = 0
    if "group_training_programs" not in st.session_state:
        st.session_state.group_training_programs = [dict(item) for item in GROUP_TRAINING_SAMPLE_PROGRAMS]
    if "group_training_feedback" not in st.session_state:
        st.session_state.group_training_feedback = [dict(item) for item in GROUP_TRAINING_SAMPLE_FEEDBACK]
    if "group_training_participants" not in st.session_state:
        st.session_state.group_training_participants: List[GroupTrainingParticipant] = []
    if "group_training_form_version" not in st.session_state:
        st.session_state.group_training_form_version = 0


def add_student_record(name: str, inputs: Dict[str, str]) -> None:
    record = StudentRecord(name=name, inputs=inputs)
    st.session_state.students.append(record)
    st.session_state.cohort_summary = None


def set_student_evaluation(index: int, evaluation: EvaluationPayload) -> None:
    st.session_state.students[index].evaluation = evaluation
    st.session_state.cohort_summary = None


def add_group_training_participant(name: str, inputs: Dict[str, str]) -> None:
    participant = GroupTrainingParticipant(name=name, inputs=inputs)
    st.session_state.group_training_participants.append(participant)


def set_group_training_evaluation(index: int, evaluation: Dict[str, Any]) -> None:
    st.session_state.group_training_participants[index].evaluation = evaluation


def reset_group_training_form() -> None:
    st.session_state.group_training_form_version += 1


def run_goal_setting_evaluation(index: int) -> bool:
    try:
        evaluation = call_goal_setting_evaluation(
            st.session_state.group_training_participants[index].inputs
        )
    except (ValueError, ImportError, APIError) as exc:
        st.error(f"評価の呼び出し中にエラーが発生しました: {exc}")
        return False
    set_group_training_evaluation(index, evaluation)
    return True


def render_goal_setting_result(
    participant: GroupTrainingParticipant,
    *,
    key_prefix: str,
) -> None:
    if participant.evaluation is None:
        st.warning("まだ評価が実行されていません。")
        return

    goal_section = participant.evaluation.get("goal_setting", {})
    entries = []
    scores: List[int] = []
    for label in GOAL_SETTING_CRITERIA:
        entry = goal_section.get(label, {"score": 0, "reason": ""})
        entries.append((label, entry))
        scores.append(entry.get("score", 0))

    avg_score = sum(scores) / len(scores) if scores else 0.0
    top_label, top_entry = max(entries, key=lambda item: item[1].get("score", 0))
    growth_label, growth_entry = min(entries, key=lambda item: item[1].get("score", 0))

    render_metric_row(
        [
            {"title": "平均スコア", "value": f"{avg_score:.1f}点", "caption": "8観点の平均"},
            {
                "title": "強み",
                "value": f"{top_label} {top_entry.get('score', 0)}点",
                "caption": "最もスコアが高い観点",
            },
            {
                "title": "伸びしろ",
                "value": f"{growth_label} {growth_entry.get('score', 0)}点",
                "caption": "優先的に強化したい観点",
            },
        ]
    )

    render_score_cards("評価詳細", entries)

    summary_text = participant.evaluation.get("overall_summary", "（未提供）")
    st.markdown(f"**総評:** {summary_text}")

    # normalized_prefix = key_prefix.replace(" ", "_")
    # render_radar_chart(
    #     f"{participant.name} - 目標設定能力",
    #     GOAL_SETTING_CRITERIA,
    #     {participant.name: scores},
    #     chart_key=f"{normalized_prefix}_goal_setting_radar",
    # )


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

    # prefix = key_prefix or record.name
    # normalized_prefix = prefix.replace(" ", "_")

    # render_radar_chart(
    #     f"{record.name} - コンピテンシー評価",
    #     [label for label, _ in COMPETENCY_LABELS],
    #     {record.name: competency_scores},
    #     chart_key=f"{normalized_prefix}_competency_radar",
    # )
    # render_radar_chart(
    #     f"{record.name} - 経営者準備度",
    #     [label for label, _ in READINESS_LABELS],
    #     {record.name: readiness_scores},
    #     chart_key=f"{normalized_prefix}_readiness_radar",
    # )


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

    # render_radar_chart(
    #     "平均コンピテンシー",
    #     [label for label, _ in COMPETENCY_LABELS],
    #     {
    #         "平均": [
    #             stats["avg_competency"][label]
    #             for label, _ in COMPETENCY_LABELS
    #         ]
    #     },
    #     chart_key="cohort_avg_competency",
    # )
    # render_radar_chart(
    #     "平均経営者準備度",
    #     [label for label, _ in READINESS_LABELS],
    #     {
    #         "平均": [
    #             stats["avg_readiness"][label]
    #             for label, _ in READINESS_LABELS
    #         ]
    #     },
    #     chart_key="cohort_avg_readiness",
    # )

    # multi_series_competency = {}
    # multi_series_readiness = {}
    # for record in evaluated_records:
    #     multi_series_competency[record.name] = [
    #         record.evaluation["competency"][label]["score"] for label, _ in COMPETENCY_LABELS
    #     ]
    #     multi_series_readiness[record.name] = [
    #         record.evaluation["readiness"][label]["score"] for label, _ in READINESS_LABELS
    #     ]

    # render_radar_chart(
    #     "受講生比較 - コンピテンシー",
    #     [label for label, _ in COMPETENCY_LABELS],
    #     multi_series_competency,
    #     chart_key="cohort_compare_competency",
    # )
    # render_radar_chart(
    #     "受講生比較 - 経営者準備度",
    #     [label for label, _ in READINESS_LABELS],
    #     multi_series_readiness,
    #     chart_key="cohort_compare_readiness",
    # )

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


def render_succession_registration_page() -> None:
    version = st.session_state.registration_form_version

    def widget_key(field: str) -> str:
        return f"{REGISTRATION_FIELD_KEYS[field]}_{version}"

    st.header("受講生の登録")
    st.caption("必要事項を入力して受講生を登録してください。評価は別ページで実行できます。")
    render_divider()
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
                st.success(f"{name.strip()} を登録しました。評価は『評価デモ』ページで実行できます。")
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


def render_succession_evaluation_page() -> None:
    st.header("評価デモ")
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


SUCCESSION_NAV_OPTIONS = ["受講生登録", "評価デモ"]


def render_succession_demo(sidebar_container) -> None:
    with sidebar_container:
        st.markdown("**サクセッションデモ**")
        # st.caption("次世代リーダー候補の登録とAI評価を切り替えます。")
        current_page = st.radio(
            "サクセッションデモ内のページを選択",
            SUCCESSION_NAV_OPTIONS,
            key="succession_nav",
            label_visibility="collapsed",
            format_func=lambda opt: "📋 " + opt if opt == SUCCESSION_NAV_OPTIONS[0] else "🧭 " + opt,
        )

    st.title("サクセッションデモ")
    if current_page == SUCCESSION_NAV_OPTIONS[0]:
        render_succession_registration_page()
    else:
        render_succession_evaluation_page()


def render_group_training_input_page() -> None:
    st.caption("研修前後の入力を整理し、AI評価の材料を準備します。")

    render_divider()

    version = st.session_state.group_training_form_version

    def widget_key(field: str) -> str:
        return f"{GROUP_TRAINING_FIELD_KEYS[field]}_{version}"

    st.subheader("受講者入力フォーム")
    st.markdown("<span class='metric-chip'>STEP 1</span> 研修情報と振り返りの入力", unsafe_allow_html=True)
    st.write("講座情報・事前課題・研修当日の振り返りを整理し、AI評価の材料とします。")

    with st.form("group_training_participant_form"):
        name = st.text_input(
            "受講者名",
            key=widget_key("name"),
            placeholder="例：山田 花子",
            help="レポートに表示される氏名を入力してください",
        )

        form_values: Dict[str, str] = {}
        for section_title, field_defs in GROUP_TRAINING_SECTIONS:
            with st.expander(section_title, expanded=True):
                for field_key, label, widget_type in field_defs:
                    if widget_type == "text_input":
                        form_values[field_key] = st.text_input(
                            label,
                            key=widget_key(field_key),
                            value="https://school.jma.or.jp/products/detail.php?product_id=100132",
                            # placeholder="https://example.com/training",
                        )
                    else:
                        form_values[field_key] = st.text_area(
                            label,
                            key=widget_key(field_key),
                            placeholder="このセクションでの気づきや考えを自由に記入してください。",
                            height=160,
                        )

        action_cols = st.columns([2, 1])
        with action_cols[0]:
            submitted = st.form_submit_button("受講者を登録する", type="primary")
        with action_cols[1]:
            cleared = st.form_submit_button("入力をクリアする")

        if cleared:
            reset_group_training_form()
            st.info("フォームをクリアしました。再度入力してください。")

        if submitted:
            if not name.strip():
                st.error("受講者名を入力してください。")
            else:
                participant_inputs: Dict[str, str] = {"受講者名": name.strip()}
                for _, field_defs in GROUP_TRAINING_SECTIONS:
                    for field_key, label, _ in field_defs:
                        participant_inputs[label] = form_values.get(field_key, "")
                add_group_training_participant(name.strip(), participant_inputs)
                st.success(f"{name.strip()} を登録しました。AI評価は『AI評価』ページで実行できます。")
                reset_group_training_form()

    render_divider()

    participants = st.session_state.group_training_participants
    st.subheader("登録済み受講者")
    if participants:
        for participant in participants:
            status = "評価済み" if participant.evaluation else "未評価"
            st.markdown(f"- {participant.name} （{status}）")
    else:
        st.info("まだ受講者が登録されていません。フォームから入力してください。")


def render_group_training_evaluation_page() -> None:
    st.caption("登録済みの入力内容をもとに、Claudeによる目標設定能力評価を実行します。")

    participants = st.session_state.group_training_participants
    if not participants:
        render_divider()
        st.info("まだ受講者が登録されていません。『受講者入力』ページで登録してください。")
        return

    render_divider()

    st.subheader("受講者一覧とAI評価")

    pending_indices = [idx for idx, record in enumerate(participants) if record.evaluation is None]
    if pending_indices:
        if st.button("未評価の受講者を一括評価", type="primary"):
            completed_names: List[str] = []
            with st.spinner("未評価の受講者を順番に評価しています..."):
                for idx in pending_indices:
                    if run_goal_setting_evaluation(idx):
                        completed_names.append(participants[idx].name)
                    else:
                        break
            if completed_names:
                st.success("、".join(completed_names) + " の評価が完了しました。")

    evaluated = [record for record in participants if record.evaluation]
    metrics = [
        {
            "title": "登録済み受講者",
            "value": f"{len(participants)}名",
            "caption": "現在ダッシュボードに登録されている人数",
        },
        {
            "title": "評価完了",
            "value": f"{len(evaluated)}名",
            "caption": f"未評価 {len(participants) - len(evaluated)}名",
        },
    ]

    criterion_averages: Dict[str, float] = {}
    if evaluated:
        for label in GOAL_SETTING_CRITERIA:
            scores = [record.evaluation["goal_setting"][label]["score"] for record in evaluated]
            criterion_averages[label] = mean(scores)
        overall_avg = sum(criterion_averages.values()) / len(GOAL_SETTING_CRITERIA)
        metrics.append(
            {
                "title": "平均スコア",
                "value": f"{overall_avg:.1f}点",
                "caption": "目標設定能力8観点の平均",
            }
        )

    render_metric_row(metrics)

    if evaluated:
        score_table: List[Dict[str, Any]] = []
        reason_table: List[Dict[str, str]] = []
        for label in GOAL_SETTING_CRITERIA:
            score_row: Dict[str, Any] = {"観点": label}
            reason_row: Dict[str, str] = {"観点": label}
            for record in evaluated:
                entry = record.evaluation["goal_setting"][label]
                score_row[record.name] = entry["score"]
                reason_row[record.name] = entry["reason"]
            score_table.append(score_row)
            reason_table.append(reason_row)

        st.markdown("### スコア比較表")
        st.table(score_table)

        st.markdown("### 評価根拠表")
        st.dataframe(reason_table, use_container_width=True)

        # render_radar_chart(
        #     "平均スコアレーダーチャート",
        #     GOAL_SETTING_CRITERIA,
        #     {"平均スコア": [criterion_averages[label] for label in GOAL_SETTING_CRITERIA]},
        #     chart_key="goal_setting_average_radar",
        # )

    render_divider()

    for idx, participant in enumerate(participants):
        expanded = participant.evaluation is None
        with st.expander(participant.name, expanded=expanded):
            status = "評価済み" if participant.evaluation else "未評価"
            st.markdown(f"**評価ステータス**: {status}")
            if participant.evaluation:
                render_goal_setting_result(
                    participant,
                    key_prefix=f"group_training_{idx}_{participant.name}",
                )
            else:
                st.markdown("**登録内容プレビュー**")
                for label, value in participant.inputs.items():
                    st.markdown(f"- {label}: {value.strip() or '未記入'}")
                if st.button("Claudeで評価する", key=f"group_training_evaluate_{idx}"):
                    with st.spinner(f"{participant.name} を評価しています..."):
                        if run_goal_setting_evaluation(idx):
                            st.success(f"{participant.name} の評価が完了しました。")


def render_group_training_demo(sidebar_container) -> None:
    with sidebar_container:
        st.markdown("**集合研修デモ**")
        # st.caption("研修入力とAI評価を段階的に確認します。")
        current_page = st.radio(
            "集合研修デモ内のページを選択",
            GROUP_TRAINING_NAV_OPTIONS,
            key="group_training_nav",
            label_visibility="collapsed",
            format_func=lambda opt: "📝 " + opt if opt == GROUP_TRAINING_NAV_OPTIONS[0] else "✨ " + opt,
        )

    st.title("集合研修デモ")
    if current_page == GROUP_TRAINING_NAV_OPTIONS[0]:
        render_group_training_input_page()
    else:
        render_group_training_evaluation_page()


def main() -> None:
    st.set_page_config(page_title="日本能率協会様デモ", page_icon="📊", layout="wide")
    ensure_session_state()
    inject_global_styles()

    with st.sidebar:
        # st.title("ナビゲーション")
        st.divider()

        demo_options = ["サクセッションデモ", "集合研修デモ"]
        selected_demo = st.radio(
            "デモを選択してください",
            demo_options,
            key="demo_selector",
            label_visibility="collapsed",
            format_func=lambda opt: "👥 " + opt if opt == demo_options[0] else "🏫 " + opt,
        )

        st.divider()
        sidebar_section = st.container()

    if selected_demo == demo_options[0]:
        render_succession_demo(sidebar_section)
    else:
        render_group_training_demo(sidebar_section)


if __name__ == "__main__":
    main()
