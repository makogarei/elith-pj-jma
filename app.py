import streamlit as st
import requests
from bs4 import BeautifulSoup
import anthropic
import json
from datetime import datetime
import pandas as pd
import os
from typing import Dict, List
import PyPDF2
import io
import base64

# ページ設定
st.set_page_config(
    page_title="研修評価デモ",
    page_icon="🎓",
    layout="wide"
)

# セッション状態の初期化
if 'system_mode' not in st.session_state:
    st.session_state.system_mode = None
if 'course_info' not in st.session_state:
    st.session_state.course_info = None
if 'participants' not in st.session_state:
    st.session_state.participants = []
if 'evaluations' not in st.session_state:
    st.session_state.evaluations = {}
if 'pre_tasks' not in st.session_state:
    st.session_state.pre_tasks = {}
if 'summary_sheets' not in st.session_state:
    st.session_state.summary_sheets = {}
if 'debug_mode' not in st.session_state:
    st.session_state.debug_mode = False
if 'pdf_files' not in st.session_state:
    st.session_state.pdf_files = {}
if 'dummy_answers' not in st.session_state:
    st.session_state.dummy_answers = {}
if 'dummy_summary' not in st.session_state:
    st.session_state.dummy_summary = {}
if 'api_key' not in st.session_state:
    st.session_state.api_key = st.secrets["CLAUDE_API_KEY"]
if 'exclude_keywords' not in st.session_state:
    st.session_state.exclude_keywords = []
if 'dry_run' not in st.session_state:
    st.session_state.dry_run = False
if 'evaluation_prompt_template' not in st.session_state:
    st.session_state.evaluation_prompt_template = """以下の受講者の事前課題回答とまとめシートを基に、8つの評価基準それぞれについて5点満点で評価してください。

事前課題回答:
{pre_task_answers}

まとめシート:
{summary_sheet}

評価基準:
{evaluation_criteria}

各基準について1-5点で評価し、評価理由を記載してください。
事前課題とまとめシートの両方を考慮して総合的に評価してください。

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
    "overall_feedback": "総合フィードバック"
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
        "content": "提供された ORIGINAL_TEXT（原文）に基づき評価根拠を抽出。quote は ORIGINAL_TEXT からの逐語抜粋（サブストリング）であり、要約・言い換えは禁止。各抜粋は30〜200字、targetは SF|VCI|OL|DE|LA|CV|MR|MN、polarityは pos|neg|neutral。出力は JSON: {\"list\":[{\"id\":\"EV-1\",\"docId\":\"...\",\"polarity\":\"pos\",\"target\":\"DE\",\"quote\":\"...\",\"note\":\"...\"}]} のみ。"
    },
    "pr_score_ja": {
        "step": "score",
        "name": "Score JA",
        "content": "Evidence(list)に基づき、以下の8項目についてコメント（理由）と関連エビデンスIDを返してください。数値スコアは任意、JSONのみで返答。\n\n必須の構造:\n{\n  \"competencies\": {\n    \"SF\": {\"reason\": \"...\", \"evidenceIds\": [\"EV-1\", ...]},\n    \"VCI\": {\"reason\": \"...\", \"evidenceIds\": [...]},\n    \"OL\": {\"reason\": \"...\", \"evidenceIds\": [...]},\n    \"DE\": {\"reason\": \"...\", \"evidenceIds\": [...]},\n    \"LA\": {\"reason\": \"...\", \"evidenceIds\": [...]}\n  },\n  \"readiness\": {\n    \"CV\": {\"reason\": \"...\", \"evidenceIds\": [...]},\n    \"MR\": {\"reason\": \"...\", \"evidenceIds\": [...]},\n    \"MN\": {\"reason\": \"...\", \"evidenceIds\": [...]}\n  }\n}\n\n注: reasonは100〜180字。evidenceIdsは抽出済みEvidenceのidのみ。"
    }
}

ACQUISITION_FORMULAS = {
    "solution": {"VCI": 0.40, "DE": 0.30, "LA": 0.30},
    "achievement": {"DE": 0.50, "OL": 0.30, "LA": 0.20},
    "management": {"OL": 0.40, "SF": 0.40, "MR": 0.20}
}

# 表示用のラベルと順序（獲得度・準備度）
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

# 評価基準
EVALUATION_CRITERIA = [
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
    # st.session_state.api_key=st.secrets["CLAUDE_API_KEY"]
    if st.session_state.api_key:
        return anthropic.Anthropic(api_key=st.session_state.api_key)
    return None

def scrape_course_info(url):
    """講座情報をスクレイピング"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title = soup.find('h1') or soup.find('title')
        title_text = title.text.strip() if title else "講座情報"
        
        description = ""
        for tag in soup.find_all(['p', 'div']):
            text = tag.text.strip()
            if len(text) > 50:
                description += text + "\n"
                if len(description) > 1000:
                    break
        
        return {
            "title": title_text,
            "description": description[:1500],
            "url": url
        }
    except Exception as e:
        st.error(f"URLから情報を取得できませんでした: {e}")
        return None

def extract_text_from_pdf(pdf_file):
    """PDFファイルからテキストを抽出"""
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"PDF読み込みエラー: {e}")
        return None

def save_pdf_to_session(pdf_file, course_id):
    """PDFファイルをセッション状態に保存"""
    if pdf_file is not None:
        pdf_bytes = pdf_file.read()
        pdf_file.seek(0)
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        
        if 'pdf_files' not in st.session_state:
            st.session_state.pdf_files = {}
        
        st.session_state.pdf_files[course_id] = {
            'filename': pdf_file.name,
            'data': pdf_base64,
            'uploaded_at': datetime.now().isoformat()
        }
        return True
    return False

def get_pdf_from_session(course_id):
    """セッション状態からPDFデータを取得"""
    if 'pdf_files' in st.session_state and course_id in st.session_state.pdf_files:
        pdf_data = st.session_state.pdf_files[course_id]
        pdf_bytes = base64.b64decode(pdf_data['data'])
        return pdf_bytes, pdf_data['filename']
    return None, None

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

def generate_dummy_summary(participant_name, course_info):
    """Claude APIを使用してダミーのまとめシートを生成"""
    client = get_client()
    if not client:
        st.error("APIキーが設定されていません")
        return None
    
    prompt = f"""
    以下の研修を受講した「{participant_name}」として、まとめシートのダミーデータを作成してください。
    
    講座情報:
    タイトル: {course_info.get('title', '研修')}
    内容: {course_info.get('description', '')[:500]}
    
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

def generate_dummy_answers(pre_tasks, participant_name, course_info):
    """Claude APIを使用してダミーの回答を生成"""
    client = get_client()
    if not client:
        st.error("APIキーが設定されていません")
        return None
    
    prompt = f"""
    以下の事前課題に対して、受講者「{participant_name}」として現実的で具体的な回答を作成してください。
    
    講座情報:
    タイトル: {course_info.get('title', '研修')}
    内容: {course_info.get('description', '')[:500]}
    
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
        // 他の7項目も同様
    }}
    
    事前課題の内容:
    {json.dumps(pre_tasks, ensure_ascii=False, indent=2)}
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

def generate_pre_tasks(course_info, participant_name):
    """Claude APIを使用して事前課題を生成"""
    client = get_client()
    if not client:
        st.error("APIキーが設定されていません")
        return None
    
    additional_content = ""
    if 'pdf_content' in course_info and course_info['pdf_content']:
        additional_content = f"\n\nPDF資料の内容:\n{course_info['pdf_content'][:2000]}"
    
    prompt = f"""
    以下の講座情報を基に、受講者「{participant_name}」向けの事前課題を作成してください。

    講座タイトル: {course_info['title']}
    講座内容: {course_info['description'][:500]}
    {additional_content}

    以下の8つの管理項目それぞれについて、具体的な事前課題を作成してください。
    各項目について「問題認識」と「改善案」の2つの質問を作成してください。

    必ず以下の形式のJSONで出力してください：
    {{
        "役割認識": {{
            "問題認識": "役割認識において現在どのような問題があると認識していますか？",
            "改善案": "その問題を解決するためにどのような改善策が必要だと思いますか？"
        }},
        "目標設定": {{
            "問題認識": "目標設定において現在どのような問題があると認識していますか？",
            "改善案": "その問題を解決するためにどのような改善策が必要だと思いますか？"
        }},
        "計画立案": {{
            "問題認識": "計画立案において現在どのような問題があると認識していますか？",
            "改善案": "その問題を解決するためにどのような改善策が必要だと思いますか？"
        }},
        "役割分担": {{
            "問題認識": "役割分担において現在どのような問題があると認識していますか？",
            "改善案": "その問題を解決するためにどのような改善策が必要だと思いますか？"
        }},
        "動機付け": {{
            "問題認識": "動機付けにおいて現在どのような問題があると認識していますか？",
            "改善案": "その問題を解決するためにどのような改善策が必要だと思いますか？"
        }},
        "コミュニケーション": {{
            "問題認識": "コミュニケーションにおいて現在どのような問題があると認識していますか？",
            "改善案": "その問題を解決するためにどのような改善策が必要だと思いますか？"
        }},
        "成果管理": {{
            "問題認識": "成果管理において現在どのような問題があると認識していますか？",
            "改善案": "その問題を解決するためにどのような改善策が必要だと思いますか？"
        }},
        "部下指導": {{
            "問題認識": "部下指導において現在どのような問題があると認識していますか？",
            "改善案": "その問題を解決するためにどのような改善策が必要だと思いますか？"
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
                tasks = json.loads(json_match.group())
                for item in MANAGEMENT_ITEMS:
                    if item not in tasks:
                        tasks[item] = {
                            "問題認識": f"{item}において現在どのような問題があると認識していますか？具体的に記載してください。",
                            "改善案": f"その問題を解決するためにどのような改善策が必要だと思いますか？実現可能な方法を記載してください。"
                        }
                return tasks
            except json.JSONDecodeError:
                pass
        
        tasks = {}
        for item in MANAGEMENT_ITEMS:
            tasks[item] = {
                "問題認識": f"{item}において現在どのような問題があると認識していますか？具体的に記載してください。",
                "改善案": f"その問題を解決するためにどのような改善策が必要だと思いますか？実現可能な方法を記載してください。"
            }
        return tasks
        
    except Exception as e:
        st.error(f"事前課題の生成に失敗しました: {e}")
        tasks = {}
        for item in MANAGEMENT_ITEMS:
            tasks[item] = {
                "問題認識": f"{item}において現在どのような問題があると認識していますか？具体的に記載してください。",
                "改善案": f"その問題を解決するためにどのような改善策が必要だと思いますか？実現可能な方法を記載してください。"
            }
        return tasks

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
    
    prompt = st.session_state.evaluation_prompt_template.format(
        pre_task_answers=pre_task_answers_str,
        summary_sheet=summary_sheet_str,
        evaluation_criteria=json.dumps(EVALUATION_CRITERIA, ensure_ascii=False, indent=2)
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
            "reason": f"{label}に関する記述が入力文から確認されました。",
            "evidenceIds": by_target.get(code, [])
        }
    ready = {}
    for code in READINESS_ORDER:
        label = READINESS_LABELS.get(code, code)
        ready[code] = {
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
    # タイトルはモードに応じて表示名を切り替える
    if st.session_state.system_mode == "assessment":
        st.title("📊 サクセッション評価")
    elif st.session_state.system_mode == "training":
        st.title("📚 研修管理システム")
    else:
        st.title("🎓 統合管理システム")
    
    # システム選択
    if st.session_state.system_mode is None:
        st.header("システムを選択してください")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📚 研修管理システム")
            st.write("研修の事前課題作成、まとめシート管理、受講者評価を行います。")
            if st.button("研修管理システムを使用", type="primary", use_container_width=True):
                st.session_state.system_mode = "training"
                st.rerun()
        
        with col2:
            st.subheader("📊 サクセッション評価")
            st.write("サクセッション評価を3ステップで実行します。")
            if st.button("サクセッションを使用", type="primary", use_container_width=True):
                st.session_state.system_mode = "assessment"
                st.rerun()
    
    # 研修管理システム
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
            # ドライラン切替
            st.divider()
            st.session_state.dry_run = st.checkbox(
                "ドライラン（ダミー出力）",
                value=st.session_state.get('dry_run', False),
                help="APIを使わずダミー結果で画面表示と形式を確認します"
            )
            
            st.divider()
            
            menu = st.radio(
                "機能を選択",
                ["評価設定", "講座情報入力", "事前課題作成", "まとめシート", 
                 "受講者評価"]
            )
        
        # APIキーチェック
        if not st.session_state.api_key and menu not in ["講座情報入力"]:
            st.error("🔑 この機能を使用するにはAPIキーの設定が必要です。サイドバーでAPIキーを設定してください。")
            return
        
        # 各機能の実装
        if menu == "講座情報入力":
            st.header("講座情報入力")
            
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.subheader("📝 講座情報")
                url = st.text_input(
                    "講座URL",
                    placeholder="https://school.jma.or.jp/products/detail.php?product_id=100132",
                    help="講座のURLを入力してください"
                )
                
                uploaded_file = st.file_uploader(
                    "講座資料PDF（オプション）",
                    type=['pdf'],
                    help="講座の詳細資料やシラバスなどのPDFファイルをアップロードできます"
                )
                
                if st.button("📥 講座情報を取得", type="primary", use_container_width=True):
                    if url:
                        with st.spinner("講座情報を取得中..."):
                            course_info = scrape_course_info(url)
                            if course_info:
                                st.session_state.course_info = course_info
                                
                                if uploaded_file:
                                    pdf_text = extract_text_from_pdf(uploaded_file)
                                    if pdf_text:
                                        st.session_state.course_info['pdf_content'] = pdf_text[:5000]
                                        st.session_state.course_info['pdf_filename'] = uploaded_file.name
                                        save_pdf_to_session(uploaded_file, 'default')
                                
                                st.success("✅ 講座情報を取得しました")
                                st.rerun()
                    else:
                        st.error("URLを入力してください")
            
            with col2:
                st.subheader("👥 受講者情報")
                participant_name = st.text_input("受講者名", placeholder="山田太郎")
                participant_id = st.text_input("受講者ID", placeholder="EMP001")
                participant_dept = st.text_input("所属部署", placeholder="営業部")
                
                if st.button("➕ 受講者を追加", type="primary", use_container_width=True):
                    if participant_name and participant_id:
                        participant = {
                            "name": participant_name,
                            "id": participant_id,
                            "department": participant_dept,
                            "added_at": datetime.now().isoformat()
                        }
                        st.session_state.participants.append(participant)
                        st.success(f"✅ 受講者「{participant_name}」を追加しました")
                        st.rerun()
                    else:
                        st.error("受講者名とIDは必須です")
            
            # 講座情報の表示
            if st.session_state.course_info:
                st.divider()
                st.subheader("📋 取得した講座情報")
                
                col1, col2 = st.columns([2, 1])
                with col1:
                    st.write(f"**タイトル:** {st.session_state.course_info['title']}")
                    st.write(f"**URL:** {st.session_state.course_info['url']}")
                    if 'pdf_filename' in st.session_state.course_info:
                        st.write(f"**PDF資料:** 📄 {st.session_state.course_info['pdf_filename']}")
                
                with st.expander("詳細を表示"):
                    st.write("**講座概要:**")
                    st.write(st.session_state.course_info['description'])
            
            # 受講者リスト
            if st.session_state.participants:
                st.divider()
                st.subheader("📊 登録済み受講者一覧")
                
                for idx, participant in enumerate(st.session_state.participants):
                    col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
                    with col1:
                        st.write(f"👤 {participant['name']}")
                    with col2:
                        st.write(f"ID: {participant['id']}")
                    with col3:
                        st.write(f"部署: {participant.get('department', '-')}")
                    with col4:
                        st.write(f"登録: {participant['added_at'][:10]}")
                    with col5:
                        if st.button("削除", key=f"del_{idx}", type="secondary"):
                            st.session_state.participants.pop(idx)
                            st.rerun()
        
        elif menu == "事前課題作成":
            st.header("事前課題作成")
            
            if not st.session_state.course_info:
                st.warning("先に講座情報を入力してください")
            elif not st.session_state.participants:
                st.warning("先に受講者を登録してください")
            else:
                participant = st.selectbox(
                    "受講者を選択",
                    options=st.session_state.participants,
                    format_func=lambda x: x['name']
                )
                
                col1, col2, col3 = st.columns([1, 1, 1])
                with col1:
                    if st.button("📄 事前課題を生成", type="primary"):
                        with st.spinner("事前課題を生成中..."):
                            tasks = generate_pre_tasks(st.session_state.course_info, participant['name'])
                            if tasks:
                                st.session_state.pre_tasks[participant['id']] = tasks
                                st.success("✅ 事前課題を生成しました")
                                st.rerun()
                
                with col2:
                    if participant['id'] in st.session_state.pre_tasks:
                        st.info(f"📝 {participant['name']}さんの事前課題は生成済みです")
                
                with col3:
                    if participant['id'] in st.session_state.pre_tasks:
                        if st.button("🤖 ダミーデータ作成", type="secondary"):
                            with st.spinner("ダミーデータを生成中..."):
                                dummy_answers = generate_dummy_answers(
                                    st.session_state.pre_tasks[participant['id']],
                                    participant['name'],
                                    st.session_state.course_info
                                )
                                if dummy_answers:
                                    if 'dummy_answers' not in st.session_state:
                                        st.session_state.dummy_answers = {}
                                    st.session_state.dummy_answers[participant['id']] = dummy_answers
                                    st.success("✅ ダミーデータを生成しました")
                                    st.rerun()
                
                # 事前課題の表示と回答入力
                if participant and participant['id'] in st.session_state.pre_tasks:
                    st.subheader(f"📋 {participant['name']}さんの事前課題")
                    
                    st.info("各管理項目について、①何が問題だと思っているのか、②どうすれば良いと思うのか、を記載してください。")
                    
                    has_dummy = 'dummy_answers' in st.session_state and participant['id'] in st.session_state.dummy_answers
                    if has_dummy:
                        st.success("🤖 ダミーデータが入力欄に反映されています。必要に応じて編集してください。")
                    
                    answers = {}
                    
                    tabs = st.tabs(MANAGEMENT_ITEMS)
                    
                    for idx, item in enumerate(MANAGEMENT_ITEMS):
                        with tabs[idx]:
                            if item in st.session_state.pre_tasks[participant['id']]:
                                task = st.session_state.pre_tasks[participant['id']][item]
                                
                                st.markdown(f"### {item}")
                                
                                dummy_value_problem = ""
                                dummy_value_solution = ""
                                if has_dummy and item in st.session_state.dummy_answers[participant['id']]:
                                    dummy_data = st.session_state.dummy_answers[participant['id']][item]
                                    dummy_value_problem = dummy_data.get('問題認識', '')
                                    dummy_value_solution = dummy_data.get('改善案', '')
                                
                                existing_answers = st.session_state.evaluations.get(participant['id'], {}).get('pre_task_answers', {})
                                existing_problem = existing_answers.get(item, {}).get('問題認識', '')
                                existing_solution = existing_answers.get(item, {}).get('改善案', '')
                                
                                st.markdown("**① 何が問題だと思っているのか:**")
                                if '問題認識' in task:
                                    st.caption(task['問題認識'])
                                problem = st.text_area(
                                    "あなたの回答",
                                    key=f"problem_{participant['id']}_{item}",
                                    height=120,
                                    value=dummy_value_problem if dummy_value_problem else existing_problem,
                                    placeholder="現在直面している問題や課題を具体的に記載してください..."
                                )
                                
                                st.divider()
                                
                                st.markdown("**② どうすれば良いと思うか:**")
                                if '改善案' in task:
                                    st.caption(task['改善案'])
                                solution = st.text_area(
                                    "あなたの回答",
                                    key=f"solution_{participant['id']}_{item}",
                                    height=120,
                                    value=dummy_value_solution if dummy_value_solution else existing_solution,
                                    placeholder="問題を解決するための改善策や対応方法を記載してください..."
                                )
                                
                                answers[item] = {
                                    "問題認識": problem,
                                    "改善案": solution
                                }
                    
                    st.divider()
                    col1, col2, col3 = st.columns([1, 2, 1])
                    with col2:
                        button_cols = st.columns(2)
                        with button_cols[0]:
                            if st.button("💾 回答を保存", type="primary", use_container_width=True):
                                if participant['id'] not in st.session_state.evaluations:
                                    st.session_state.evaluations[participant['id']] = {}
                                st.session_state.evaluations[participant['id']]['pre_task_answers'] = answers
                                
                                if 'dummy_answers' in st.session_state and participant['id'] in st.session_state.dummy_answers:
                                    del st.session_state.dummy_answers[participant['id']]
                                
                                st.success("✅ 回答を保存しました")
        
        elif menu == "まとめシート":
            st.header("まとめシート")
            
            if not st.session_state.participants:
                st.warning("先に受講者を登録してください")
            else:
                participant = st.selectbox(
                    "受講者を選択",
                    options=st.session_state.participants,
                    format_func=lambda x: x['name']
                )
                
                st.subheader(f"📝 {participant['name']}さんのまとめシート")
                
                col1, col2, col3 = st.columns([1, 1, 1])
                with col1:
                    if st.button("🤖 ダミーデータ作成", type="secondary"):
                        with st.spinner("まとめシートのダミーデータを生成中..."):
                            dummy_summary = generate_dummy_summary(
                                participant['name'],
                                st.session_state.course_info
                            )
                            
                            if dummy_summary:
                                if 'dummy_summary' not in st.session_state:
                                    st.session_state.dummy_summary = {}
                                st.session_state.dummy_summary[participant['id']] = dummy_summary
                                st.success("✅ ダミーデータを生成しました")
                                st.rerun()
                
                has_dummy = 'dummy_summary' in st.session_state and \
                           participant['id'] in st.session_state.dummy_summary
                if has_dummy:
                    st.success("🤖 ダミーデータが入力欄に反映されています。必要に応じて編集してください。")
                
                dummy_data = {}
                if has_dummy:
                    dummy_data = st.session_state.dummy_summary[participant['id']]
                
                existing_data = st.session_state.summary_sheets.get(participant['id'], {})
                
                summary_sheet = {}
                
                st.markdown("### 【受講者への期待】")
                expectations_from_instructor = st.text_area(
                    "受講者への期待",
                    key=f"exp_instructor_{participant['id']}",
                    height=100,
                    value=dummy_data.get('expectations_from_instructor', '') if dummy_data else existing_data.get('expectations_from_instructor', ''),
                    placeholder="この研修を通じて習得してほしいことや期待する成長..."
                )
                summary_sheet['expectations_from_instructor'] = expectations_from_instructor
                
                st.markdown("### 【受講に対する事前期待】《受講者記入》")
                expectations_from_participant = st.text_area(
                    "受講者の事前期待",
                    key=f"exp_participant_{participant['id']}",
                    height=100,
                    value=dummy_data.get('expectations_from_participant', '') if dummy_data else existing_data.get('expectations_from_participant', ''),
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
                        
                        dummy_value = ""
                        if dummy_data and 'learning_items' in dummy_data:
                            dummy_value = dummy_data['learning_items'].get(item, '')
                        
                        existing_value = existing_data.get('learning_items', {}).get(item, '')
                        
                        content = st.text_area(
                            f"学んだ内容・気づき",
                            key=f"item_{participant['id']}_{item}",
                            height=150,
                            value=dummy_value if dummy_value else existing_value,
                            placeholder="このテーマで学んだことや新たな気づきを記載してください..."
                        )
                        learning_items[item] = content
                
                summary_sheet['learning_items'] = learning_items
                
                st.divider()
                
                st.markdown("### 【職場で実践すること】")
                
                practice_themes = []
                
                for i in range(2):
                    st.markdown(f"#### テーマ{i+1}")
                    
                    dummy_theme = ""
                    dummy_content = ""
                    if dummy_data and 'practice_themes' in dummy_data and len(dummy_data['practice_themes']) > i:
                        dummy_theme = dummy_data['practice_themes'][i].get('theme', '')
                        dummy_content = dummy_data['practice_themes'][i].get('content', '')
                    
                    existing_theme = ""
                    existing_content = ""
                    if 'practice_themes' in existing_data and len(existing_data['practice_themes']) > i:
                        existing_theme = existing_data['practice_themes'][i].get('theme', '')
                        existing_content = existing_data['practice_themes'][i].get('content', '')
                    
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        theme = st.text_input(
                            f"テーマ名",
                            key=f"theme_{participant['id']}_{i}",
                            value=dummy_theme if dummy_theme else existing_theme,
                            placeholder="実践テーマ"
                        )
                    with col2:
                        content = st.text_area(
                            f"具体的な実践内容",
                            key=f"practice_{participant['id']}_{i}",
                            height=100,
                            value=dummy_content if dummy_content else existing_content,
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
                        st.session_state.summary_sheets[participant['id']] = summary_sheet
                        
                        if 'dummy_summary' in st.session_state and \
                           participant['id'] in st.session_state.dummy_summary:
                            del st.session_state.dummy_summary[participant['id']]
                        
                        st.success("✅ まとめシートを保存しました")
        
        elif menu == "受講者評価":
            st.header("受講者評価")
            
            if not st.session_state.participants:
                st.warning("先に受講者を登録してください")
            else:
                participant = st.selectbox(
                    "受講者を選択",
                    options=st.session_state.participants,
                    format_func=lambda x: x['name']
                )
                
                has_pre_task = participant['id'] in st.session_state.evaluations and \
                              'pre_task_answers' in st.session_state.evaluations[participant['id']]
                has_summary = participant['id'] in st.session_state.summary_sheets
                
                col1, col2 = st.columns(2)
                with col1:
                    if has_pre_task:
                        st.success("✅ 事前課題: 完了")
                    else:
                        st.error("❌ 事前課題: 未完了")
                with col2:
                    if has_summary:
                        st.success("✅ まとめシート: 完了")
                    else:
                        st.error("❌ まとめシート: 未完了")
                
                if st.button("AI評価を実行", disabled=not (has_pre_task and has_summary)):
                    if has_pre_task and has_summary:
                        with st.spinner("評価を生成中..."):
                            evaluation = evaluate_participant(
                                st.session_state.evaluations[participant['id']]['pre_task_answers'],
                                st.session_state.summary_sheets[participant['id']]
                            )
                            
                            if evaluation:
                                if participant['id'] not in st.session_state.evaluations:
                                    st.session_state.evaluations[participant['id']] = {}
                                st.session_state.evaluations[participant['id']]['ai_evaluation'] = evaluation
                                st.success("評価を完了しました")
                    else:
                        st.warning("事前課題とまとめシートの両方が必要です")
                
                if participant['id'] in st.session_state.evaluations and \
                   'ai_evaluation' in st.session_state.evaluations[participant['id']]:
                    st.subheader("評価結果")
                    
                    ai_eval = st.session_state.evaluations[participant['id']]['ai_evaluation']
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("総合スコア", f"{ai_eval.get('total_score', 0)}/40点")
                    with col2:
                        avg_score = ai_eval.get('total_score', 0) / 8
                        st.metric("平均スコア", f"{avg_score:.1f}/5.0")
                    with col3:
                        percentage = (ai_eval.get('total_score', 0) / 40) * 100
                        st.metric("達成率", f"{percentage:.0f}%")
                    
                    st.subheader("詳細評価")
                    
                    for eval_item in ai_eval.get('evaluations', []):
                        with st.expander(f"{eval_item['criteria']}  {eval_item['score']}/5点"):
                            st.write(f"**評価理由:** {eval_item['reason']}")
                    
                    st.subheader("総合フィードバック")
                    st.info(ai_eval.get('overall_feedback', ''))
        
        elif menu == "評価設定":
            st.header("⚙️ 評価設定")
            
            # タブで設定項目を分ける
            tab1, tab2 = st.tabs(["除外キーワード設定", "評価プロンプト設定"])
            
            with tab1:
                st.subheader("🚫 除外キーワード設定")
                st.info("評価時に無視するキーワードを設定できます。これらのキーワードを含む文は評価から除外されます。")
                
                new_keyword = st.text_input(
                    "除外キーワードを追加",
                    placeholder="例: ダミー、テスト、サンプル"
                )
                if st.button("➕ キーワードを追加", type="primary"):
                    if new_keyword and new_keyword not in st.session_state.exclude_keywords:
                        st.session_state.exclude_keywords.append(new_keyword)
                        st.success(f"✅ 「{new_keyword}」を除外キーワードに追加しました")
                        st.rerun()
                
                if st.session_state.exclude_keywords:
                    st.write("**登録済み除外キーワード:**")
                    cols = st.columns(4)
                    for idx, keyword in enumerate(st.session_state.exclude_keywords):
                        with cols[idx % 4]:
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.write(f"• {keyword}")
                            with col2:
                                if st.button("×", key=f"del_kw_{idx}"):
                                    st.session_state.exclude_keywords.pop(idx)
                                    st.rerun()
                else:
                    st.write("除外キーワードは設定されていません")
            
            with tab2:
                st.subheader("📝 評価プロンプトテンプレート")
                st.info("AI評価で使用するプロンプトをカスタマイズできます。変数は {pre_task_answers}, {summary_sheet}, {evaluation_criteria} が使用できます。")
                
                # デフォルトプロンプト
                default_prompt = """以下の受講者の事前課題回答とまとめシートを基に、8つの評価基準それぞれについて5点満点で評価してください。

事前課題回答:
{pre_task_answers}

まとめシート:
{summary_sheet}

評価基準:
{evaluation_criteria}

各基準について1-5点で評価し、評価理由を記載してください。
事前課題とまとめシートの両方を考慮して総合的に評価してください。

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
    "overall_feedback": "総合フィードバック"
}}"""
                
                # プリセットプロンプトの選択
                st.write("**プロンプトテンプレートを選択:**")
                preset_option = st.selectbox(
                    "プリセット",
                    options=["カスタム", "デフォルト", "詳細評価", "簡易評価", "成長重視"],
                    help="プリセットを選択するか、カスタムで独自のプロンプトを作成できます"
                )
                
                # プリセットプロンプトの定義
                preset_prompts = {
                    "デフォルト": default_prompt,
                    "詳細評価": """受講者の事前課題回答とまとめシートを詳細に分析し、以下の観点から評価してください。

【評価対象データ】
◆事前課題回答:
{pre_task_answers}

◆まとめシート:
{summary_sheet}

【評価基準】
{evaluation_criteria}

【評価指示】
1. 各基準について1-5点で採点（5点が最高）
2. 評価理由は具体的な記述を引用しながら150-200字で記載
3. 改善点や強みを明確に指摘
4. 実践への意欲や理解度を重視

JSON形式で出力:
{{
    "evaluations": [
        {{
            "criteria": "基準名",
            "score": 点数,
            "reason": "評価理由（具体的な記述を引用）"
        }}
    ],
    "total_score": 合計点,
    "overall_feedback": "総合フィードバック（強み・改善点・今後への期待を含む）"
}}""",
                    "簡易評価": """事前課題とまとめシートから受講者の理解度を評価してください。

データ:
- 事前課題: {pre_task_answers}
- まとめ: {summary_sheet}
- 基準: {evaluation_criteria}

各基準を1-5点で評価し、簡潔な理由（50-80字）を付けてください。

JSON出力:
{{
    "evaluations": [
        {{"criteria": "基準名", "score": 点数, "reason": "理由"}}
    ],
    "total_score": 合計,
    "overall_feedback": "総評"
}}""",
                    "成長重視": """受講者の成長可能性と実践意欲を重視して評価してください。

【評価材料】
■事前課題での気づき:
{pre_task_answers}

■研修での学び:
{summary_sheet}

【評価の視点】
{evaluation_criteria}

【評価方針】
- 現状の課題認識の深さを重視（配点40%）
- 改善への具体的なアプローチ（配点30%）
- 実践への意欲と計画性（配点30%）
- 各項目1-5点で評価

【求める出力】
JSON形式で以下を出力:
{{
    "evaluations": [
        {{
            "criteria": "基準名",
            "score": 点数,
            "reason": "成長の観点からの評価理由（100-150字）"
        }}
    ],
    "total_score": 合計点,
    "overall_feedback": "今後の成長への期待と具体的アドバイス（200字程度）"
}}"""
                }
                
                # プロンプト編集エリア
                if preset_option != "カスタム":
                    if st.button(f"「{preset_option}」プロンプトを適用", type="primary"):
                        st.session_state.evaluation_prompt_template = preset_prompts[preset_option]
                        st.success(f"✅ {preset_option}プロンプトを適用しました")
                        st.rerun()
                
                st.write("**現在のプロンプト:**")
                
                # テキストエリアでプロンプト編集
                edited_prompt = st.text_area(
                    "評価プロンプト",
                    value=st.session_state.evaluation_prompt_template,
                    height=400,
                    help="プロンプトを編集してAI評価の挙動をカスタマイズできます"
                )
                
                # ボタンを横並びに
                col1, col2, col3 = st.columns([1, 1, 1])
                
                with col1:
                    if st.button("💾 プロンプトを保存", type="primary"):
                        st.session_state.evaluation_prompt_template = edited_prompt
                        st.success("✅ プロンプトを保存しました")
                        st.rerun()
                
                with col2:
                    if st.button("🔄 デフォルトに戻す"):
                        st.session_state.evaluation_prompt_template = default_prompt
                        st.success("✅ デフォルトのプロンプトに戻しました")
                        st.rerun()
                
                with col3:
                    # プロンプトのエクスポート
                    st.download_button(
                        label="📥 プロンプトをダウンロード",
                        data=st.session_state.evaluation_prompt_template,
                        file_name="evaluation_prompt.txt",
                        mime="text/plain"
                    )
                
                # プロンプトのプレビュー
                with st.expander("プロンプトのプレビュー（変数展開例）"):
                    st.write("**実際の評価時には以下のように変数が展開されます:**")
                    
                    sample_preview = st.session_state.evaluation_prompt_template.format(
                        pre_task_answers="[受講者の事前課題回答がここに入ります]",
                        summary_sheet="[受講者のまとめシートがここに入ります]",
                        evaluation_criteria="[8つの評価基準がここに入ります]"
                    )
                    st.code(sample_preview, language="text")
                
                # プロンプト作成のヒント
                with st.expander("💡 プロンプト作成のヒント"):
                    st.markdown("""
                    ### 効果的なプロンプトの書き方
                    
                    1. **明確な指示**: 評価の観点や重視するポイントを明確に記載
                    2. **出力形式の指定**: JSON形式の構造を正確に指定
                    3. **評価基準の活用**: `{evaluation_criteria}`変数を適切に配置
                    4. **文字数の指定**: 評価理由の文字数を指定すると一貫性が保てます
                    5. **重み付け**: 特定の観点を重視する場合は配点比率を明記
                    
                    ### 使用可能な変数
                    - `{pre_task_answers}`: 事前課題の回答内容
                    - `{summary_sheet}`: まとめシートの内容
                    - `{evaluation_criteria}`: 8つの評価基準
                    
                    ### 必須の出力形式
                    ```json
                    {
                        "evaluations": [...],
                        "total_score": 数値,
                        "overall_feedback": "文字列"
                    }
                    ```
                    """)
    
    # アセスメント評価システム
    elif st.session_state.system_mode == "assessment":
        with st.sidebar:
            st.header("📋 メニュー")
            
            if st.button("🏠 システム選択に戻る"):
                st.session_state.system_mode = None
                st.rerun()
            
            st.divider()
            
            # APIキー設定
            with st.expander("🔑 API設定", expanded=not st.session_state.api_key):
                api_key_input = st.text_input(
                    "Claude API Key",
                    value=st.session_state.api_key,
                    type="password",
                    help="Anthropic Claude APIのキーを入力してください"
                )
                if st.button("APIキーを保存", type="primary"):
                    if api_key_input:
                        st.session_state.api_key = api_key_input
                        st.success("✅ APIキーを保存しました")
                        st.rerun()
                    else:
                        st.error("APIキーを入力してください")
            
            if not st.session_state.api_key:
                st.warning("⚠️ APIキーを設定してください")
            else:
                st.success("✅ API設定済み")
        
        st.header("サクセッション評価ツール")
        st.info("課題と実施内容など、評価に必要な情報を1つのテキストボックスにまとめて入力してください。\n入力後に『AI評価を実行する』を押すと3ステップ評価を行います。")

        user_bulk_text = st.text_area(
            "課題・実施内容（まとめて入力）",
            height=260,
            placeholder="例）課題文、取り組み内容、成果、振り返り、今後の計画 などをまとめて記載してください。"
        )

        if st.button("AI評価を実行する", type="primary"):
            if not st.session_state.api_key:
                st.error("Claude APIキーが設定されていません。サイドバーから設定してください。")
            else:
                # 既存パイプラインIFを維持するため、1行のDataFrameに変換
                df = pd.DataFrame({
                    "項目": ["全入力"],
                    "あなたの考え": [user_bulk_text.strip()]
                })
                final_evaluation = run_assessment_evaluation_pipeline(df)
                if final_evaluation:
                    st.header("最終評価結果")

                    # 構造化表示: 獲得度/準備度 → 各中項目で原文エビデンスとコメント
                    scores = final_evaluation.get("scores", {}) or {}
                    evidence_list = final_evaluation.get("evidence", {}).get("list", []) or []

                    # インデックス構築
                    ev_by_id = {}
                    ev_by_target = {code: [] for code in (COMPETENCY_ORDER + READINESS_ORDER)}
                    for ev in evidence_list:
                        ev_id = ev.get("id")
                        if ev_id:
                            ev_by_id[ev_id] = ev
                        tgt = ev.get("target")
                        if tgt in ev_by_target:
                            ev_by_target[tgt].append(ev)

                    def render_item(block_title, code, label, data_block):
                        st.markdown(f"### {label}")
                        # コメント（理由）
                        reason = ""
                        if isinstance(data_block, dict):
                            reason = data_block.get("reason") or data_block.get("Reason") or ""

                        # 関連エビデンスの解決
                        quotes = []
                        ids = []
                        if isinstance(data_block, dict):
                            ids = data_block.get("evidenceIds") or data_block.get("evidence_ids") or []
                            if isinstance(ids, dict):
                                # 万一、{id:...}形式の場合に備える
                                ids = list(ids.values())
                        for eid in ids:
                            ev = ev_by_id.get(eid)
                            if ev and ev.get("quote"):
                                quotes.append(ev.get("quote"))
                        # フォールバック: target一致
                        if not quotes:
                            for ev in ev_by_target.get(code, [])[:3]:
                                if ev.get("quote"):
                                    quotes.append(ev.get("quote"))

                        # 根拠（原文）
                        st.write("根拠（原文）")
                        if quotes:
                            for q in quotes:
                                st.write(q)
                        else:
                            st.caption("該当する原文の根拠は見つかりませんでした。")

                        # コメント（理由）
                        if reason:
                            st.write("コメント")
                            st.write(reason)

                    # 獲得度
                    st.subheader("獲得度")
                    comp = scores.get("competencies", {}) or {}
                    for code in COMPETENCY_ORDER:
                        render_item("competencies", code, COMPETENCY_LABELS.get(code, code), comp.get(code, {}))
                        st.divider()

                    # 準備度
                    st.subheader("準備度")
                    ready = scores.get("readiness", {}) or {}
                    for code in READINESS_ORDER:
                        render_item("readiness", code, READINESS_LABELS.get(code, code), ready.get(code, {}))
                        st.divider()

                    with st.expander("詳細（JSON全体）"):
                        st.json(final_evaluation)

if __name__ == "__main__":
    main()
