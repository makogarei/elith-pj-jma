import streamlit as st
import anthropic
import json
from datetime import datetime
import pandas as pd

# ページ設定
st.set_page_config(
    page_title="研修評価デモ",
    page_icon="🎓",
    layout="wide"
)

# セッション状態の初期化
if 'system_mode' not in st.session_state:
    st.session_state.system_mode = None
if 'evaluations' not in st.session_state:
    st.session_state.evaluations = {}
if 'pre_task_answers' not in st.session_state:
    st.session_state.pre_task_answers = {}
if 'summary_sheet' not in st.session_state:
    st.session_state.summary_sheet = {}
if 'api_key' not in st.session_state:
    st.session_state.api_key = st.secrets.get("CLAUDE_API_KEY", "")
if 'exclude_keywords' not in st.session_state:
    st.session_state.exclude_keywords = []
if 'custom_evaluation_perspectives' not in st.session_state:
    st.session_state.custom_evaluation_perspectives = []
if 'evaluation_prompt_template' not in st.session_state:
    st.session_state.evaluation_prompt_template = """以下の受講者の事前課題回答とまとめシートを基に、評価基準それぞれについて5点満点で評価してください。

事前課題回答:
{pre_task_answers}

まとめシート:
{summary_sheet}

標準評価基準:
{evaluation_criteria}

カスタム評価観点:
{custom_perspectives}

各基準について1-5点で評価し、評価理由を記載してください。
事前課題とまとめシートの両方を考慮して総合的に評価してください。
カスタム評価観点がある場合は、それらも考慮に入れて評価してください。

JSON形式で出力してください：
{{
    "evaluations": [
        {{
            "criteria": "基準名",
            "score": 点数,
            "reason": "評価理由"
        }}
    ],
    "total_score": 合計点,
    "overall_feedback": "総合フィードバック",
    "custom_perspectives_feedback": "カスタム観点からのフィードバック"
}}"""

# === アセスメント評価用のプロンプト定義 ===
ASSESSMENT_PROMPTS = {
    "pr_norm_ja": {
        "step": "normalize",
        "name": "Normalize JA",
        "content": "入力テキストを以下のセクションに分類してください。各エントリは (1) summary: 120字以内の要約 と (2) text: 原文抜粋（逐語、改変禁止）を必ず含めます。出力は JSON: {\"items\":[{\"docId\":\"...\",\"section\":\"dept_status|dept_issues|solutions|vision|training_reflection|next1to2y\",\"summary\":\"...\",\"text\":\"...\"}], \"confidence\":\"low|med|high\"} のみ。"
    },
    "pr_evi_ja": {
        "step": "evidence",
        "name": "Evidence JA",
        "content": "提供された ORIGINAL_TEXT（原文）に基づき評価根拠を抽出。quote は ORIGINAL_TEXT からの逐語抜粋（サブストリング）であり、要約・言い換えは禁止。各抜粋は30～200字、targetは SF|VCI|OL|DE|LA|CV|MR|MN、polarityは pos|neg|neutral。出力は JSON: {\"list\":[{\"id\":\"EV-1\",\"docId\":\"...\",\"polarity\":\"pos\",\"target\":\"DE\",\"quote\":\"...\",\"note\":\"...\"}]} のみ。"
    },
    "pr_score_ja": {
        "step": "score",
        "name": "Score JA",
        "content": "Evidence(list)に基づき、以下の8項目について score(1-5), reason, evidenceIds を必ず返してください。JSONのみ。\n\n必須の構造:\n{\n  \"competencies\": {\n    \"SF\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [\"EV-1\", ...]},\n    \"VCI\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]},\n    \"OL\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]},\n    \"DE\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]},\n    \"LA\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]}\n  },\n  \"readiness\": {\n    \"CV\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]},\n    \"MR\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]},\n    \"MN\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]}\n  }\n}\n\n注: scoreは1〜5の整数。reasonは100〜180字。evidenceIdsは抽出済みEvidenceのidのみ。"
    }
}

ACQUISITION_FORMULAS = {
    "solution": {"VCI": 0.40, "DE": 0.30, "LA": 0.30},
    "achievement": {"DE": 0.50, "OL": 0.30, "LA": 0.20},
    "management": {"OL": 0.40, "SF": 0.40, "MR": 0.20}
}

# 表示用のラベルと順序（粕得度・準備度）
COMPETENCY_ORDER = ["SF", "VCI", "OL", "DE", "LA"]
READINESS_ORDER = ["CV", "MR", "MN"]
COMPETENCY_LABELS = {
    "SF": "戦略構想力",
    "VCI": "価値創出・イノベーション力",
    "OL": "人的資源・組織運営力",
    "DE": "意思決定・実行力",
    "LA": "学習・適応力",
}
READINESS_LABELS = {
    "CV": "キャリアビジョン",
    "MR": "使命感・責任感",
    "MN": "体制・ネットワーク",
}

# 8つの管理項目
MANAGEMENT_ITEMS = [
    "役割認識",
    "目標設定",
    "計画立案",
    "役割分担",
    "動機付け",
    "コミュニケーション",
    "成果管理",
    "部下指導"
]

# まとめシートの項目
SUMMARY_SHEET_ITEMS = [
    "リーダーのあり方",
    "目標による管理の進め方",
    "問題解決への取り組み方",
    "効果的なチーム運営",
    "メンバーのやる気を引き出す指導の進め方",
    "メンバーの成長を促す育成の進め方",
    "リーダーとしての自己成長"
]

# 評価基準（デフォルト）
DEFAULT_EVALUATION_CRITERIA = [
    "ストレッチした目標表現に言及されている",
    "目的・目標を分けて明確な目標表現をしようとしている",
    "目標設定後メンバーから納得を引き出そうとしている",
    "目標設定がメンバーの行動を決めると重要性を理解している",
    "目標設定のための準備をしっかりと取ろうとしている",
    "目標設定の重要性を表記している",
    "目標設定は将来の成果を予め設定したものといった観点で表記されている",
    "方針やビジョンと関連させようとした目標設定にしている"
]

def get_client():
    """Claude APIクライアントを取得"""
    if st.session_state.api_key:
        return anthropic.Anthropic(api_key=st.session_state.api_key)
    return None

def filter_text_with_exclude_keywords(text, exclude_keywords):
    """除外キーワードを含む文を削除"""
    if not exclude_keywords:
        return text
    
    lines = text.split('\n')
    filtered_lines = []
    
    for line in lines:
        should_exclude = False
        for keyword in exclude_keywords:
            if keyword.lower() in line.lower():
                should_exclude = True
                break
        if not should_exclude:
            filtered_lines.append(line)
    
    return '\n'.join(filtered_lines)

def generate_dummy_summary():
    """Claude APIを使用してダミーのまとめシートを生成"""
    client = get_client()
    if not client:
        st.error("APIキーが設定されていません")
        return None
    
    prompt = f"""
    管理職研修を受講した受講者として、まとめシートのダミーデータを作成してください。
    
    以下の項目について、現実的で具体的な内容を記載してください：
    
    1. 受講者への期待（講師からの期待として）: 50-100文字
    2. 受講に対する事前期待（受講者として）: 50-100文字
    3. 各学習項目（7項目）: 各100-150文字程度で学んだ内容や気づきを記載
    4. 職場で実践すること（2つのテーマ）: 各100-150文字程度で具体的な実践計画を記載
    
    必ずJSON形式で出力してください：
    {{
        "expectations_from_instructor": "講師からの期待",
        "expectations_from_participant": "受講者の事前期待",
        "learning_items": {{
            "リーダーのあり方": "学んだ内容",
            "目標による管理の進め方": "学んだ内容",
            "問題解決への取り組み方": "学んだ内容",
            "効果的なチーム運営": "学んだ内容",
            "メンバーのやる気を引き出す指導の進め方": "学んだ内容",
            "メンバーの成長を促す育成の進め方": "学んだ内容",
            "リーダーとしての自己成長": "学んだ内容"
        }},
        "practice_themes": [
            {{"theme": "テーマ1", "content": "具体的な実践内容"}},
            {{"theme": "テーマ2", "content": "具体的な実践内容"}}
        ]
    }}
    """
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.content[0].text
        
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        
        if json_match:
            try:
                dummy_summary = json.loads(json_match.group())
                return dummy_summary
            except json.JSONDecodeError:
                pass
        
        return None
        
    except Exception as e:
        st.error(f"ダミーデータの生成に失敗しました: {e}")
        return None

def generate_dummy_answers():
    """Claude APIを使用してダミーの回答を生成"""
    client = get_client()
    if not client:
        st.error("APIキーが設定されていません")
        return None
    
    prompt = f"""
    管理職研修の事前課題に対して、現実的で具体的な回答を作成してください。
    
    各管理項目について、以下の観点で回答してください：
    - 実際の職場での具体的な問題認識
    - 現実的な改善提案
    - 中間管理職として直面しそうな悩み
    
    回答は日本語で、1つの回答につき100-200文字程度で作成してください。
    
    必ずJSON形式で出力してください：
    {{
        "役割認識": {{
            "問題認識": "何が問題だと思っているか",
            "改善案": "どうすれば良いと思うか"
        }},
        "目標設定": {{
            "問題認識": "何が問題だと思っているか",
            "改善案": "どうすれば良いと思うか"
        }},
        "計画立案": {{
            "問題認識": "何が問題だと思っているか",
            "改善案": "どうすれば良いと思うか"
        }},
        "役割分担": {{
            "問題認識": "何が問題だと思っているか",
            "改善案": "どうすれば良いと思うか"
        }},
        "動機付け": {{
            "問題認識": "何が問題だと思っているか",
            "改善案": "どうすれば良いと思うか"
        }},
        "コミュニケーション": {{
            "問題認識": "何が問題だと思っているか",
            "改善案": "どうすれば良いと思うか"
        }},
        "成果管理": {{
            "問題認識": "何が問題だと思っているか",
            "改善案": "どうすれば良いと思うか"
        }},
        "部下指導": {{
            "問題認識": "何が問題だと思っているか",
            "改善案": "どうすれば良いと思うか"
        }}
    }}
    """
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.content[0].text
        
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        
        if json_match:
            try:
                dummy_answers = json.loads(json_match.group())
                return dummy_answers
            except json.JSONDecodeError:
                pass
        
        return None
        
    except Exception as e:
        st.error(f"ダミーデータの生成に失敗しました: {e}")
        return None

def evaluate_participant(pre_task_answers, summary_sheet):
    """Claude APIを使用して受講者を評価（事前課題とまとめシート）"""
    client = get_client()
    if not client:
        st.error("APIキーが設定されていません")
        return None
    
    pre_task_answers_str = json.dumps(pre_task_answers, ensure_ascii=False, indent=2)
    summary_sheet_str = json.dumps(summary_sheet, ensure_ascii=False, indent=2)
    
    if st.session_state.exclude_keywords:
        pre_task_answers_str = filter_text_with_exclude_keywords(
            pre_task_answers_str, 
            st.session_state.exclude_keywords
        )
        summary_sheet_str = filter_text_with_exclude_keywords(
            summary_sheet_str,
            st.session_state.exclude_keywords
        )
    
    # 全評価基準を結合
    all_criteria = DEFAULT_EVALUATION_CRITERIA.copy()
    custom_perspectives = st.session_state.custom_evaluation_perspectives
    
    prompt = st.session_state.evaluation_prompt_template.format(
        pre_task_answers=pre_task_answers_str,
        summary_sheet=summary_sheet_str,
        evaluation_criteria=json.dumps(all_criteria, ensure_ascii=False, indent=2),
        custom_perspectives=json.dumps(custom_perspectives, ensure_ascii=False, indent=2) if custom_perspectives else "なし"
    )
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.content[0].text
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            return None
    except Exception as e:
        st.error(f"評価の生成に失敗しました: {e}")
        return None

# === アセスメント評価用の関数 ===
def _call_claude(client, system_prompt, user_content):
    """Claude API呼び出しの共通ラッパー"""
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[
                {"role": "user", "content": f"System: {system_prompt}\n\nUser: {user_content}\n\nPlease respond with valid JSON only."}
            ]
        )
        
        content = response.content[0].text
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        
        if json_match:
            return json.loads(json_match.group())
        else:
            return json.loads(content)
    except Exception as e:
        st.error(f"Claude API エラー: {e}")
        return None

def _calculate_acquisition_scores(scores):
    """獲得能力スコアを計算する"""
    acq_scores = {}
    base_scores = {**scores.get('competencies', {}), **scores.get('readiness', {})}
    
    for acq_name, formula in ACQUISITION_FORMULAS.items():
        total_score = 0
        for comp, weight in formula.items():
            total_score += base_scores.get(comp, {'score': 0}).get('score', 0) * weight
        acq_scores[acq_name] = round(total_score)
    return acq_scores

# === ダミー生成ユーティリティ ===
def _generate_dummy_evidence(original_text: str):
    try:
        import re
        # 文切り出し（簡易）
        sentences = [s.strip() for s in re.split(r"[。\n\r]", original_text or "") if s.strip()]
        if not sentences:
            chunk = (original_text or "入力がありません").strip()
            sentences = [chunk[:80]]
        ev_list = []
        codes = COMPETENCY_ORDER + READINESS_ORDER
        for i, code in enumerate(codes):
            sent = sentences[i % len(sentences)]
            if not sent:
                sent = "（ダミー）入力文からの抜粋"
            ev_list.append({
                "id": f"EV-{code}-{i+1}",
                "target": code,
                "quote": sent
            })
        return {"list": ev_list}
    except Exception:
        # 最低限のフォールバック
        ev_list = []
        for i, code in enumerate(COMPETENCY_ORDER + READINESS_ORDER):
            ev_list.append({"id": f"EV-{code}-{i+1}", "target": code, "quote": "（ダミー）原文抜粋"})
        return {"list": ev_list}

def _generate_dummy_scores(evidence: dict):
    ev_list = evidence.get("list", []) if isinstance(evidence, dict) else []
    by_target = {code: [] for code in (COMPETENCY_ORDER + READINESS_ORDER)}
    for ev in ev_list:
        tgt = ev.get("target")
        if tgt in by_target:
            by_target[tgt].append(ev.get("id"))

    comp = {}
    for code in COMPETENCY_ORDER:
        label = COMPETENCY_LABELS.get(code, code)
        comp[code] = {
            "score": 4,
            "reason": f"{label}に関する記述が入力文から確認されました。",
            "evidenceIds": by_target.get(code, [])
        }
    ready = {}
    for code in READINESS_ORDER:
        label = READINESS_LABELS.get(code, code)
        ready[code] = {
            "score": 3,
            "reason": f"{label}に関する記述が入力文から確認されました。",
            "evidenceIds": by_target.get(code, [])
        }
    return {"competencies": comp, "readiness": ready}

def _generate_dummy_normalized(original_text: str):
    return {
        "items": [
            {"docId": "D-1", "section": "summary", "summary": "入力内容のダミー要約", "text": (original_text or "")[:120]}
        ],
        "confidence": "low"
    }

def _generate_dummy_assessment(full_text: str, original_text: str):
    evidence = _generate_dummy_evidence(original_text)
    scores = _generate_dummy_scores(evidence)
    return {
        "normalized": _generate_dummy_normalized(original_text),
        "evidence": evidence,
        "scores": scores,
        "meta": {"dummy": True}
    }

def run_assessment_evaluation_pipeline(user_input_df):
    """3ステップの評価パイプラインを実行するオーケストレーター"""
    full_text = ""
    raw_concat = []
    for _, row in user_input_df.iterrows():
        text_val = row.get('あなたの考え', '') if isinstance(row, dict) else row['あなたの考え']
        if text_val and str(text_val).strip():
            # ユーザー原文（逐語）を別途連結
            raw_concat.append(str(text_val))
            # 既存の正規化入力用テキストは従来どおり見出し付きで構築
            full_text += f"## {row['項目']}\n\n{text_val}\n\n"
    original_text = "\n\n".join(raw_concat)

    if not full_text:
        st.warning("入力がありません。")
        return None

    try:
        client = get_client()
        # ドライランまたはAPIキー未設定時はダミー出力へ
        if st.session_state.get('dry_run') or not client:
            st.info("ドライラン（ダミー出力）で実行します。")
            return _generate_dummy_assessment(full_text, original_text)
            
        final_result = {}

        # st.statusの使用方法を変更（expandパラメータを削除）
        with st.spinner("評価パイプラインを実行中..."):
            # ステップ1
            st.info("ステップ1/3: テキストを正規化しています...")
            normalized_data = _call_claude(
                client,
                ASSESSMENT_PROMPTS["pr_norm_ja"]["content"],
                f"入力データ(JSON):\n{json.dumps({'input': {'text': full_text}})}"
            )
            if not normalized_data:
                st.warning("正規化処理に失敗しました。ダミー出力に切替えます。")
                return _generate_dummy_assessment(full_text, original_text)
            final_result["normalized"] = normalized_data
            st.success("ステップ1/3: 正規化完了")

            # ステップ2
            st.info("ステップ2/3: 評価エビデンスを抽出しています...")
            evidence_data = _call_claude(
                client,
                ASSESSMENT_PROMPTS["pr_evi_ja"]["content"],
                f"正規化入力:\n{json.dumps(normalized_data)}\n---\nORIGINAL_TEXT:\n{original_text}"
            )
            if not evidence_data:
                st.warning("エビデンス抽出に失敗しました。ダミー出力に切替えます。")
                return _generate_dummy_assessment(full_text, original_text)
            final_result["evidence"] = evidence_data
            st.success("ステップ2/3: エビデンス抽出完了")

            # ステップ3
            st.info("ステップ3/3: 最終スコアを算出しています...")
            user_content = f"正規化入力:\n{json.dumps(normalized_data)}\n---\nエビデンス:\n{json.dumps(evidence_data)}"
            scores = _call_claude(
                client,
                ASSESSMENT_PROMPTS["pr_score_ja"]["content"],
                user_content
            )
            
            if not scores:
                st.warning("コメント算出に失敗しました。ダミー出力に切替えます。")
                return _generate_dummy_assessment(full_text, original_text)
                
            acquisition_scores = _calculate_acquisition_scores(scores)
            scores["acquisition"] = acquisition_scores
            final_result["scores"] = scores
            st.success("ステップ3/3: スコア算出完了")
            
            st.success("✅ 評価パイプライン完了！")

        return final_result

    except Exception as e:
        st.error(f"予期せぬエラーが発生しました: {e}")
    
    return None

# === メインアプリケーション ===
def main():
    if st.session_state.system_mode == "assessment":
        st.title("📊 サクセッション評価")
    elif st.session_state.system_mode == "training":
        st.title("📚 集合研修評価")
    else:
        st.title("")
    
    # システム選択
    if st.session_state.system_mode is None:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📚 集合研修評価")
            st.write("研修の事前課題、まとめシート、受講者評価を管理します。")
            if st.button("集合研修評価を使用", type="primary", use_container_width=True):
                st.session_state.system_mode = "training"
                st.rerun()
        
        with col2:
            st.subheader("📊 サクセッション評価01")
            st.write("サクセッション評価を3ステップで実行します。")
            if st.button("サクセッションを使用", type="primary", use_container_width=True):
                st.session_state.system_mode = "assessment"
                st.rerun()
    
    # 集合研修評価
    elif st.session_state.system_mode == "training":
        # サイドバー
        with st.sidebar:
            st.header("📋 メニュー")
            
            if st.button("🏠 システム選択に戻る"):
                st.session_state.system_mode = None
                st.rerun()
            
            st.divider()
            
            # APIキー設定
            # with st.expander("🔑 API設定", expanded=not st.session_state.api_key):
            #     api_key_input = st.text_input(
            #         "Claude API Key",
            #         value=st.session_state.api_key,
            #         type="password",
            #         help="Anthropic Claude APIのキーを入力してください"
            #     )
            #     if st.button("APIキーを保存", type="primary"):
            #         if api_key_input:
            #             st.session_state.api_key = api_key_input
            #             st.success("✅ APIキーを保存しました")
            #             st.rerun()
            #         else:
            #             st.error("APIキーを入力してください")
            
            if not st.session_state.api_key:
                st.warning("⚠️ APIキーを設定してください")
            else:
                st.success("✅ API設定済み")
            
            st.divider()
            
            menu = st.radio(
                "機能を選択",
                ["事前課題", "まとめシート", "受講者評価", "評価設定"]
            )
        
        # APIキーチェック
        if not st.session_state.api_key:
            st.error("🔑 この機能を使用するにはAPIキーの設定が必要です。")
            return
        
        # 各機能の実装
        if menu == "事前課題":
            st.header("📝 事前課題")
            
            # ダミーデータ生成ボタン
            if st.button("🤖 ダミーデータ作成", type="secondary"):
                with st.spinner("ダミーデータを生成中..."):
                    dummy_answers = generate_dummy_answers()
                    if dummy_answers:
                        st.session_state.pre_task_answers = dummy_answers
                        st.success("✅ ダミーデータを生成しました")
                        st.rerun()
            
            st.info("各管理項目について、①何が問題だと思っているか、②どうすれば良いと思うか、を記載してください。")
            
            answers = {}
            tabs = st.tabs(MANAGEMENT_ITEMS)
            
            for idx, item in enumerate(MANAGEMENT_ITEMS):
                with tabs[idx]:
                    st.markdown(f"### {item}")
                    
                    existing_answer = st.session_state.pre_task_answers.get(item, {})
                    
                    st.markdown("**① 何が問題だと思っているか:**")
                    problem = st.text_area(
                        "回答",
                        key=f"problem_{item}",
                        height=120,
                        value=existing_answer.get('問題認識', ''),
                        placeholder="現在直面している問題や課題を具体的に記載してください..."
                    )
                    
                    st.divider()
                    
                    st.markdown("**② どうすれば良いと思うか:**")
                    solution = st.text_area(
                        "回答",
                        key=f"solution_{item}",
                        height=120,
                        value=existing_answer.get('改善案', ''),
                        placeholder="問題を解決するための改善策や対応方法を記載してください..."
                    )
                    
                    answers[item] = {
                        "問題認識": problem,
                        "改善案": solution
                    }
            
            st.divider()
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("💾 回答を保存", type="primary", use_container_width=True):
                    st.session_state.pre_task_answers = answers
                    st.success("✅ 回答を保存しました")
        
        elif menu == "まとめシート":
            st.header("📄 まとめシート")
            
            # ダミーデータ生成ボタン
            if st.button("🤖 ダミーデータ作成", type="secondary"):
                with st.spinner("ダミーデータを生成中..."):
                    dummy_summary = generate_dummy_summary()
                    if dummy_summary:
                        st.session_state.summary_sheet = dummy_summary
                        st.success("✅ ダミーデータを生成しました")
                        st.rerun()
            
            summary_sheet = {}
            existing_data = st.session_state.summary_sheet
            
            st.markdown("### 【受講者への期待】")
            expectations_from_instructor = st.text_area(
                "受講者への期待",
                key="exp_instructor",
                height=100,
                value=existing_data.get('expectations_from_instructor', ''),
                placeholder="この研修を通じて習得してほしいことや期待する成長..."
            )
            summary_sheet['expectations_from_instructor'] = expectations_from_instructor
            
            st.markdown("### 【受講に対する事前期待】《受講者記入》")
            expectations_from_participant = st.text_area(
                "受講者の事前期待",
                key="exp_participant",
                height=100,
                value=existing_data.get('expectations_from_participant', ''),
                placeholder="この研修で学びたいことや課題解決への期待..."
            )
            summary_sheet['expectations_from_participant'] = expectations_from_participant
            
            st.divider()
            
            st.markdown("### 【研修当日ご記入欄】")
            
            tabs = st.tabs(SUMMARY_SHEET_ITEMS)
            learning_items = {}
            
            for idx, item in enumerate(SUMMARY_SHEET_ITEMS):
                with tabs[idx]:
                    st.markdown(f"#### {idx + 1}. {item}")
                    
                    existing_value = existing_data.get('learning_items', {}).get(item, '')
                    
                    content = st.text_area(
                        f"学んだ内容・気づき",
                        key=f"item_{item}",
                        height=150,
                        value=existing_value,
                        placeholder="このテーマで学んだことや新たな気づきを記載してください..."
                    )
                    learning_items[item] = content
            
            summary_sheet['learning_items'] = learning_items
            
            st.divider()
            
            st.markdown("### 【職場で実践すること】")
            
            practice_themes = []
            existing_themes = existing_data.get('practice_themes', [{}, {}])
            
            for i in range(2):
                st.markdown(f"#### テーマ{i+1}")
                
                existing_theme_data = existing_themes[i] if i < len(existing_themes) else {}
                
                col1, col2 = st.columns([1, 2])
                with col1:
                    theme = st.text_input(
                        f"テーマ名",
                        key=f"theme_{i}",
                        value=existing_theme_data.get('theme', ''),
                        placeholder="実践テーマ"
                    )
                with col2:
                    content = st.text_area(
                        f"具体的な実践内容",
                        key=f"practice_{i}",
                        height=100,
                        value=existing_theme_data.get('content', ''),
                        placeholder="いつ、どのように実践するか具体的に記載..."
                    )
                
                practice_themes.append({
                    "theme": theme,
                    "content": content
                })
            
            summary_sheet['practice_themes'] = practice_themes
            
            st.divider()
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("💾 まとめシートを保存", type="primary", use_container_width=True):
                    st.session_state.summary_sheet = summary_sheet
                    st.success("✅ まとめシートを保存しました")
        
        elif menu == "受講者評価":
            st.header("📊 受講者評価")
            
            # データ入力状況の確認
            has_pre_task = bool(st.session_state.pre_task_answers)
            has_summary = bool(st.session_state.summary_sheet)
            
            col1, col2 = st.columns(2)
            with col1:
                if has_pre_task:
                    st.success("✅ 事前課題: 入力済み")
                else:
                    st.error("❌ 事前課題: 未入力")
            with col2:
                if has_summary:
                    st.success("✅ まとめシート: 入力済み")
                else:
                    st.error("❌ まとめシート: 未入力")
            
            st.divider()
            
            # カスタム評価観点の表示
            if st.session_state.custom_evaluation_perspectives:
                st.info("💡 カスタム評価観点が設定されています")
                with st.expander("設定されているカスタム観点を確認"):
                    for perspective in st.session_state.custom_evaluation_perspectives:
                        st.write(f"• **{perspective['name']}**: {perspective['description']}")
            
            if st.button("🤖 AI評価を実行", type="primary", disabled=not (has_pre_task and has_summary)):
                if has_pre_task and has_summary:
                    with st.spinner("評価を生成中..."):
                        evaluation = evaluate_participant(
                            st.session_state.pre_task_answers,
                            st.session_state.summary_sheet
                        )
                        
                        if evaluation:
                            st.session_state.evaluations['ai_evaluation'] = evaluation
                            st.success("✅ 評価を完了しました")
                else:
                    st.warning("事前課題とまとめシートの両方が必要です")
            
            # 評価結果の表示
            if 'ai_evaluation' in st.session_state.evaluations:
                st.subheader("評価結果")
                
                ai_eval = st.session_state.evaluations['ai_evaluation']
                
                # 基準数に応じた満点の計算
                num_criteria = len(ai_eval.get('evaluations', []))
                max_score = num_criteria * 5
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("総合スコア", f"{ai_eval.get('total_score', 0)}/{max_score}点")
                with col2:
                    avg_score = ai_eval.get('total_score', 0) / num_criteria if num_criteria > 0 else 0
                    st.metric("平均スコア", f"{avg_score:.1f}/5.0")
                with col3:
                    percentage = (ai_eval.get('total_score', 0) / max_score) * 100 if max_score > 0 else 0
                    st.metric("達成率", f"{percentage:.0f}%")
                
                st.subheader("詳細評価")
                
                for eval_item in ai_eval.get('evaluations', []):
                    with st.expander(f"{eval_item['criteria']} - {eval_item['score']}/5点"):
                        st.write(f"**評価理由:** {eval_item['reason']}")
                
                st.subheader("総合フィードバック")
                st.info(ai_eval.get('overall_feedback', ''))
                
                # カスタム観点のフィードバック
                if ai_eval.get('custom_perspectives_feedback'):
                    st.subheader("カスタム観点からのフィードバック")
                    st.success(ai_eval.get('custom_perspectives_feedback'))
        
        elif menu == "評価設定":
            st.header("⚙️ 評価設定")
            
            tab1, tab2, tab3 = st.tabs(["カスタム評価観点", "除外キーワード設定", "評価プロンプト設定"])
            
            with tab1:
                st.subheader("🎯 カスタム評価観点設定")
                st.info("評価の際に重視したい独自の観点を追加できます。これらの観点は標準評価基準に加えて考慮されます。")
                
                # 新しい観点の追加
                with st.expander("新しい評価観点を追加", expanded=True):
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        new_perspective_name = st.text_input(
                            "観点名",
                            placeholder="例: チームワーク重視",
                            key="new_perspective_name"
                        )
                    with col2:
                        new_perspective_description = st.text_area(
                            "観点の説明",
                            placeholder="例: チーム全体の協調性を重視し、メンバー間の連携や協力体制構築に関する記述を評価する",
                            height=100,
                            key="new_perspective_desc"
                        )
                    
                    importance_level = st.select_slider(
                        "重要度",
                        options=["低", "中", "高", "最重要"],
                        value="中",
                        key="importance_level"
                    )
                    
                    if st.button("➕ 観点を追加", type="primary"):
                        if new_perspective_name and new_perspective_description:
                            new_perspective = {
                                "name": new_perspective_name,
                                "description": new_perspective_description,
                                "importance": importance_level
                            }
                            st.session_state.custom_evaluation_perspectives.append(new_perspective)
                            st.success(f"✅ 「{new_perspective_name}」を追加しました")
                            st.rerun()
                        else:
                            st.error("観点名と説明の両方を入力してください")
                
                # 登録済みのカスタム観点
                if st.session_state.custom_evaluation_perspectives:
                    st.write("**登録済みのカスタム評価観点:**")
                    for idx, perspective in enumerate(st.session_state.custom_evaluation_perspectives):
                        with st.container():
                            col1, col2, col3, col4 = st.columns([3, 5, 2, 1])
                            with col1:
                                st.write(f"**{perspective['name']}**")
                            with col2:
                                st.write(f"{perspective['description'][:50]}...")
                            with col3:
                                importance_badge = {
                                    "低": "🟢",
                                    "中": "🟡", 
                                    "高": "🟠",
                                    "最重要": "🔴"
                                }
                                st.write(f"{importance_badge[perspective['importance']]} {perspective['importance']}")
                            with col4:
                                if st.button("削除", key=f"del_perspective_{idx}"):
                                    st.session_state.custom_evaluation_perspectives.pop(idx)
                                    st.rerun()
                            st.divider()
                else:
                    st.write("カスタム評価観点は設定されていません")
                
                # プリセット観点の提案
                with st.expander("おすすめの評価観点"):
                    st.write("以下のような観点を追加することができます：")
                    preset_perspectives = [
                        {"name": "イノベーション志向", "desc": "新しいアイデアや革新的な取り組みへの意欲"},
                        {"name": "顧客視点", "desc": "顧客満足度向上への意識と具体的な施策"},
                        {"name": "データ活用", "desc": "データに基づく意思決定や分析力"},
                        {"name": "多様性への配慮", "desc": "多様な価値観の尊重とインクルーシブな組織作り"},
                        {"name": "持続可能性", "desc": "長期的視点での組織運営と社会的責任"}
                    ]
                    
                    for preset in preset_perspectives:
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.write(f"• **{preset['name']}**: {preset['desc']}")
                        with col2:
                            if st.button("追加", key=f"add_preset_{preset['name']}"):
                                new_perspective = {
                                    "name": preset['name'],
                                    "description": preset['desc'],
                                    "importance": "中"
                                }
                                st.session_state.custom_evaluation_perspectives.append(new_perspective)
                                st.rerun()
            
            with tab2:
                st.subheader("🚫 除外キーワード設定")
                st.info("評価時に無視するキーワードを設定できます。")
                
                new_keyword = st.text_input(
                    "除外キーワードを追加",
                    placeholder="例: ダミー、テスト、サンプル"
                )
                if st.button("➕ キーワードを追加", type="primary"):
                    if new_keyword and new_keyword not in st.session_state.exclude_keywords:
                        st.session_state.exclude_keywords.append(new_keyword)
                        st.success(f"✅ 「{new_keyword}」を追加しました")
                        st.rerun()
                
                if st.session_state.exclude_keywords:
                    st.write("**登録済み除外キーワード:**")
                    for idx, keyword in enumerate(st.session_state.exclude_keywords):
                        col1, col2 = st.columns([5, 1])
                        with col1:
                            st.write(f"• {keyword}")
                        with col2:
                            if st.button("削除", key=f"del_kw_{idx}"):
                                st.session_state.exclude_keywords.pop(idx)
                                st.rerun()
                else:
                    st.write("除外キーワードは設定されていません")
            
            with tab3:
                st.subheader("📝 評価プロンプト設定")
                
                default_prompt = """以下の受講者の事前課題回答とまとめシートを基に、評価基準それぞれについて5点満点で評価してください。

事前課題回答:
{pre_task_answers}

まとめシート:
{summary_sheet}

標準評価基準:
{evaluation_criteria}

カスタム評価観点:
{custom_perspectives}

各基準について1-5点で評価し、評価理由を記載してください。
事前課題とまとめシートの両方を考慮して総合的に評価してください。
カスタム評価観点がある場合は、それらも考慮に入れて評価してください。

JSON形式で出力してください：
{{
    "evaluations": [
        {{
            "criteria": "基準名",
            "score": 点数,
            "reason": "評価理由"
        }}
    ],
    "total_score": 合計点,
    "overall_feedback": "総合フィードバック",
    "custom_perspectives_feedback": "カスタム観点からのフィードバック"
}}"""
                
                edited_prompt = st.text_area(
                    "評価プロンプト",
                    value=st.session_state.evaluation_prompt_template,
                    height=400
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("💾 保存", type="primary"):
                        st.session_state.evaluation_prompt_template = edited_prompt
                        st.success("✅ 保存しました")
                        st.rerun()
                
                with col2:
                    if st.button("🔄 デフォルトに戻す"):
                        st.session_state.evaluation_prompt_template = default_prompt
                        st.success("✅ デフォルトに戻しました")
                        st.rerun()
    
    # アセスメント評価システム
    elif st.session_state.system_mode == "assessment":
        from succession.ui import render_assessment_ui
        render_assessment_ui()

if __name__ == "__main__":
    main()
