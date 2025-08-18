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
    page_title="研修管理システム",
    page_icon="📚",
    layout="wide"
)

# セッション状態の初期化
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
    st.session_state.api_key = ""
if 'exclude_keywords' not in st.session_state:
    st.session_state.exclude_keywords = []
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
    if st.session_state.api_key:
        return anthropic.Anthropic(api_key=st.session_state.api_key)
    return None

def scrape_course_info(url):
    """講座情報をスクレイピング"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # タイトルと説明を取得
        title = soup.find('h1') or soup.find('title')
        title_text = title.text.strip() if title else "講座情報"
        
        # 説明文を取得
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
        # PDFの内容をバイト列として保存
        pdf_bytes = pdf_file.read()
        pdf_file.seek(0)  # ファイルポインタをリセット
        
        # Base64エンコードして保存（JSON化可能にするため）
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
            model="claude-3-5-haiku-20241022",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.content[0].text
        
        # JSON部分を抽出
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        
        if json_match:
            try:
                dummy_summary = json.loads(json_match.group())
                return dummy_summary
            except json.JSONDecodeError:
                pass
        
        # フォールバック
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
            model="claude-3-5-haiku-20241022",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.content[0].text
        
        # JSON部分を抽出
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        
        if json_match:
            try:
                dummy_answers = json.loads(json_match.group())
                return dummy_answers
            except json.JSONDecodeError:
                pass
        
        # フォールバック
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
    
    # PDFの内容も含める
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
            model="claude-3-5-haiku-20241022",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # レスポンスから課題を抽出
        content = response.content[0].text
        
        # JSON部分を抽出して解析
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        
        if json_match:
            try:
                tasks = json.loads(json_match.group())
                # 生成されたタスクが適切な形式か確認
                for item in MANAGEMENT_ITEMS:
                    if item not in tasks:
                        tasks[item] = {
                            "問題認識": f"{item}において現在どのような問題があると認識していますか？具体的に記載してください。",
                            "改善案": f"その問題を解決するためにどのような改善策が必要だと思いますか？実現可能な方法を記載してください。"
                        }
                return tasks
            except json.JSONDecodeError:
                pass
        
        # フォールバック：デフォルトの課題を生成
        tasks = {}
        for item in MANAGEMENT_ITEMS:
            tasks[item] = {
                "問題認識": f"{item}において現在どのような問題があると認識していますか？具体的に記載してください。",
                "改善案": f"その問題を解決するためにどのような改善策が必要だと思いますか？実現可能な方法を記載してください。"
            }
        return tasks
        
    except Exception as e:
        st.error(f"事前課題の生成に失敗しました: {e}")
        # エラーが発生してもデフォルトの課題を返す
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
    
    # 除外キーワードでフィルタリング
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
    
    # カスタムプロンプトテンプレートを使用
    prompt = st.session_state.evaluation_prompt_template.format(
        pre_task_answers=pre_task_answers_str,
        summary_sheet=summary_sheet_str,
        evaluation_criteria=json.dumps(EVALUATION_CRITERIA, ensure_ascii=False, indent=2)
    )
    
    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
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

# Streamlitアプリ
def main():
    st.title("🎓 研修管理システム")
    
    # サイドバー
    with st.sidebar:
        st.header("📋 メニュー")
        
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
        
        st.divider()
        
        menu = st.radio(
            "機能を選択",
            ["評価設定", "講座情報入力", "事前課題作成", "まとめシート", 
             "受講者評価"]
        )
        
        st.divider()
        
        # デバッグモード
        st.session_state.debug_mode = False
        
        if st.session_state.debug_mode:
            st.caption("デバッグ情報")
            st.caption(f"課題数: {len(st.session_state.pre_tasks)}")
            st.caption(f"受講者数: {len(st.session_state.participants)}")
            st.caption(f"まとめシート: {len(st.session_state.summary_sheets)}")
    
    # APIキーチェック
    if not st.session_state.api_key and menu not in ["講座情報入力", "データ管理"]:
        st.error("🔒 この機能を使用するにはAPIキーの設定が必要です。サイドバーでAPIキーを設定してください。")
        return
    
    # メインコンテンツ
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
            
            # PDFファイルアップロード
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
                            
                            # PDFがアップロードされている場合は処理
                            if uploaded_file:
                                pdf_text = extract_text_from_pdf(uploaded_file)
                                if pdf_text:
                                    st.session_state.course_info['pdf_content'] = pdf_text[:5000]
                                    st.session_state.course_info['pdf_filename'] = uploaded_file.name
                                    # PDFファイル自体も保存
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
            
            with col2:
                if 'pdf_filename' in st.session_state.course_info:
                    if st.button("🗑️ PDF削除"):
                        if 'pdf_content' in st.session_state.course_info:
                            del st.session_state.course_info['pdf_content']
                        if 'pdf_filename' in st.session_state.course_info:
                            del st.session_state.course_info['pdf_filename']
                        st.success("PDFを削除しました")
                        st.rerun()
            
            with st.expander("詳細を表示"):
                st.write("**講座概要:**")
                st.write(st.session_state.course_info['description'])
                
                if 'pdf_content' in st.session_state.course_info:
                    st.write("**PDF内容（抜粋）:**")
                    pdf_preview = st.session_state.course_info['pdf_content'][:1000]
                    st.text(pdf_preview + "..." if len(st.session_state.course_info['pdf_content']) > 1000 else pdf_preview)
        
        # 受講者リスト
        if st.session_state.participants:
            st.divider()
            st.subheader("📊 登録済み受講者一覧")
            
            # テーブル形式で表示
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
                # 既存の課題があるか確認
                if participant['id'] in st.session_state.pre_tasks:
                    st.info(f"📝 {participant['name']}さんの事前課題は生成済みです")
            
            with col3:
                # ダミーデータ作成ボタン
                if participant['id'] in st.session_state.pre_tasks:
                    if st.button("🤖 ダミーデータ作成", type="secondary"):
                        with st.spinner("ダミーデータを生成中..."):
                            dummy_answers = generate_dummy_answers(
                                st.session_state.pre_tasks[participant['id']],
                                participant['name'],
                                st.session_state.course_info
                            )
                            if dummy_answers:
                                # セッション状態にダミーデータを保存
                                if 'dummy_answers' not in st.session_state:
                                    st.session_state.dummy_answers = {}
                                st.session_state.dummy_answers[participant['id']] = dummy_answers
                                st.success("✅ ダミーデータを生成しました")
                                st.rerun()
            
            # 事前課題の表示と回答入力
            if participant and participant['id'] in st.session_state.pre_tasks:
                st.subheader(f"📋 {participant['name']}さんの事前課題")
                
                # 課題の説明
                st.info("各管理項目について、①何が問題だと思っているのか、②どうすれば良いと思うのか、を記載してください。")
                
                # ダミーデータがある場合の通知
                has_dummy = 'dummy_answers' in st.session_state and participant['id'] in st.session_state.dummy_answers
                if has_dummy:
                    st.success("🤖 ダミーデータが入力欄に反映されています。必要に応じて編集してください。")
                
                # 回答を保存する辞書
                answers = {}
                
                # タブで管理項目を整理
                tabs = st.tabs(MANAGEMENT_ITEMS)
                
                for idx, item in enumerate(MANAGEMENT_ITEMS):
                    with tabs[idx]:
                        if item in st.session_state.pre_tasks[participant['id']]:
                            task = st.session_state.pre_tasks[participant['id']][item]
                            
                            st.markdown(f"### {item}")
                            
                            # ダミーデータの取得
                            dummy_value_problem = ""
                            dummy_value_solution = ""
                            if has_dummy and item in st.session_state.dummy_answers[participant['id']]:
                                dummy_data = st.session_state.dummy_answers[participant['id']][item]
                                dummy_value_problem = dummy_data.get('問題認識', '')
                                dummy_value_solution = dummy_data.get('改善案', '')
                            
                            # 既存の回答があるか確認
                            existing_answers = st.session_state.evaluations.get(participant['id'], {}).get('pre_task_answers', {})
                            existing_problem = existing_answers.get(item, {}).get('問題認識', '')
                            existing_solution = existing_answers.get(item, {}).get('改善案', '')
                            
                            # ①何が問題だと思っているのか
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
                            
                            # ②どうすれば良いと思うか
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
                
                # 保存ボタン
                st.divider()
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    button_cols = st.columns(2)
                    with button_cols[0]:
                        if st.button("💾 回答を保存", type="primary", use_container_width=True):
                            if participant['id'] not in st.session_state.evaluations:
                                st.session_state.evaluations[participant['id']] = {}
                            st.session_state.evaluations[participant['id']]['pre_task_answers'] = answers
                            
                            # ダミーデータをクリア（保存後は不要）
                            if 'dummy_answers' in st.session_state and participant['id'] in st.session_state.dummy_answers:
                                del st.session_state.dummy_answers[participant['id']]
                            
                            st.success("✅ 回答を保存しました")
                            
                            # 回答状況を表示
                            filled_count = sum(1 for item in answers.values() if item['問題認識'] or item['改善案']) * 2
                            total_count = len(answers) * 2
                            st.info(f"回答状況: {filled_count}/{total_count} 項目入力済み")
                    
                    with button_cols[1]:
                        if st.button("🔄 回答をクリア", use_container_width=True):
                            # ダミーデータもクリア
                            if 'dummy_answers' in st.session_state and participant['id'] in st.session_state.dummy_answers:
                                del st.session_state.dummy_answers[participant['id']]
                            st.rerun()
            
            elif participant:
                st.info("📝 上の「事前課題を生成」ボタンをクリックして、事前課題を作成してください。")
    
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
            
            # ダミーデータ作成ボタン
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if st.button("🤖 ダミーデータ作成", type="secondary"):
                    with st.spinner("まとめシートのダミーデータを生成中..."):
                        dummy_summary = generate_dummy_summary(
                            participant['name'],
                            st.session_state.course_info
                        )
                        
                        if dummy_summary:
                            # セッション状態にダミーデータを保存
                            if 'dummy_summary' not in st.session_state:
                                st.session_state.dummy_summary = {}
                            st.session_state.dummy_summary[participant['id']] = dummy_summary
                            st.success("✅ ダミーデータを生成しました")
                            st.rerun()
            
            with col2:
                # 既存のまとめシートがあるか確認
                has_existing = participant['id'] in st.session_state.summary_sheets
                if has_existing:
                    st.info("📝 保存済みのまとめシートがあります")
            
            with col3:
                if st.button("🔄 入力をクリア"):
                    # ダミーデータもクリア
                    if 'dummy_summary' in st.session_state and \
                       participant['id'] in st.session_state.dummy_summary:
                        del st.session_state.dummy_summary[participant['id']]
                    st.rerun()
            
            # ダミーデータがある場合の通知
            has_dummy = 'dummy_summary' in st.session_state and \
                       participant['id'] in st.session_state.dummy_summary
            if has_dummy:
                st.success("🤖 ダミーデータが入力欄に反映されています。必要に応じて編集してください。")
            
            # ダミーデータまたは既存データの取得
            dummy_data = {}
            if has_dummy:
                dummy_data = st.session_state.dummy_summary[participant['id']]
            
            existing_data = st.session_state.summary_sheets.get(participant['id'], {})
            
            # まとめシートの入力フォーム
            summary_sheet = {}
            
            # 受講者への期待（講師から）
            st.markdown("### 【受講者への期待】")
            expectations_from_instructor = st.text_area(
                "受講者への期待",
                key=f"exp_instructor_{participant['id']}",
                height=100,
                value=dummy_data.get('expectations_from_instructor', '') if dummy_data else existing_data.get('expectations_from_instructor', ''),
                placeholder="この研修を通じて習得してほしいことや期待する成長..."
            )
            summary_sheet['expectations_from_instructor'] = expectations_from_instructor
            
            # 受講に対する事前期待（受講者記入）
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
            
            # 研修当日記入欄
            st.markdown("### 【研修当日ご記入欄】")
            
            # 学習項目タブ
            tabs = st.tabs(SUMMARY_SHEET_ITEMS)
            learning_items = {}
            
            for idx, item in enumerate(SUMMARY_SHEET_ITEMS):
                with tabs[idx]:
                    st.markdown(f"#### {idx + 1}. {item}")
                    
                    # ダミーデータから値を取得
                    dummy_value = ""
                    if dummy_data and 'learning_items' in dummy_data:
                        dummy_value = dummy_data['learning_items'].get(item, '')
                    
                    # 既存データから値を取得
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
            
            # 職場で実践すること
            st.markdown("### 【職場で実践すること】")
            
            practice_themes = []
            
            for i in range(2):
                st.markdown(f"#### テーマ{i+1}")
                
                # ダミーデータから値を取得
                dummy_theme = ""
                dummy_content = ""
                if dummy_data and 'practice_themes' in dummy_data and len(dummy_data['practice_themes']) > i:
                    dummy_theme = dummy_data['practice_themes'][i].get('theme', '')
                    dummy_content = dummy_data['practice_themes'][i].get('content', '')
                
                # 既存データから値を取得
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
            
            # 保存ボタン
            st.divider()
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("💾 まとめシートを保存", type="primary", use_container_width=True):
                    st.session_state.summary_sheets[participant['id']] = summary_sheet
                    
                    # ダミーデータをクリア（保存後は不要）
                    if 'dummy_summary' in st.session_state and \
                       participant['id'] in st.session_state.dummy_summary:
                        del st.session_state.dummy_summary[participant['id']]
                    
                    st.success("✅ まとめシートを保存しました")
                    
                    # 記入状況を表示
                    filled_items = sum(1 for v in learning_items.values() if v)
                    filled_practice = sum(1 for p in practice_themes if p['theme'] or p['content'])
                    st.info(f"記入状況: 学習項目 {filled_items}/7, 実践テーマ {filled_practice}/2")
    
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
            
            # データの準備状況確認
            has_pre_task = participant['id'] in st.session_state.evaluations and \
                          'pre_task_answers' in st.session_state.evaluations[participant['id']]
            has_summary = participant['id'] in st.session_state.summary_sheets
            
            # データ状況の表示
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
            
            # 評価結果の表示
            if participant['id'] in st.session_state.evaluations and \
               'ai_evaluation' in st.session_state.evaluations[participant['id']]:
                st.subheader("評価結果")
                
                ai_eval = st.session_state.evaluations[participant['id']]['ai_evaluation']
                
                # スコアカード
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("総合スコア", f"{ai_eval.get('total_score', 0)}/40点")
                with col2:
                    avg_score = ai_eval.get('total_score', 0) / 8
                    st.metric("平均スコア", f"{avg_score:.1f}/5.0")
                with col3:
                    percentage = (ai_eval.get('total_score', 0) / 40) * 100
                    st.metric("達成率", f"{percentage:.0f}%")
                
                # 詳細評価
                st.subheader("詳細評価")
                
                for eval_item in ai_eval.get('evaluations', []):
                    with st.expander(f"{eval_item['criteria']}  {eval_item['score']}/5点"):
                        st.write(f"**評価理由:** {eval_item['reason']}")
                
                # 総合フィードバック
                st.subheader("総合フィードバック")
                st.info(ai_eval.get('overall_feedback', ''))
            elif has_pre_task or has_summary:
                st.info("評価を実行するには、事前課題とまとめシートの両方が必要です")
            else:
                st.info("この受講者のデータがまだありません")
    
    elif menu == "評価設定":
        st.header("⚙️ 評価設定")
        
        # 除外キーワード設定
        st.subheader("🚫 除外キーワード設定")
        st.info("評価時に無視するキーワードを設定できます。これらのキーワードを含む文は評価から除外されます。")
        
        # 新しいキーワード追加
        new_keyword = st.text_input(
            "除外キーワードを追加",
            placeholder="例: ダミー、テスト、サンプル"
        )
        if st.button("➕ キーワードを追加", type="primary"):
            if new_keyword and new_keyword not in st.session_state.exclude_keywords:
                st.session_state.exclude_keywords.append(new_keyword)
                st.success(f"✅ 「{new_keyword}」を除外キーワードに追加しました")
                st.rerun()
        
        # 既存のキーワード表示と削除
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
        
        st.divider()
        
        # 評価プロンプトテンプレート設定
        st.subheader("📝 評価プロンプトテンプレート")
        st.info("AI評価で使用するプロンプトをカスタマイズできます。変数は {pre_task_answers}, {summary_sheet}, {evaluation_criteria} が使用できます。")
        
        # デフォルトに戻すボタン
        if st.button("🔄 デフォルトに戻す"):
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
            st.success("✅ デフォルトのプロンプトに戻しました")
            st.rerun()
        
        # プロンプト編集
        edited_prompt = st.text_area(
            "評価プロンプト",
            value=st.session_state.evaluation_prompt_template,
            height=400,
            help="プロンプトを編集してAI評価の挙動をカスタマイズできます"
        )
        
        if st.button("💾 プロンプトを保存", type="primary"):
            st.session_state.evaluation_prompt_template = edited_prompt
            st.success("✅ プロンプトを保存しました")
            st.rerun()
        
        # プレビュー
        with st.expander("プロンプトのプレビュー"):
            st.code(st.session_state.evaluation_prompt_template)
    
    elif menu == "データ管理":
        st.header("データ管理")
        
        # デバッグ情報の表示
        if st.session_state.debug_mode:
            st.subheader("🔧 デバッグ情報")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("登録受講者数", len(st.session_state.participants))
            with col2:
                st.metric("生成済み課題", len(st.session_state.pre_tasks))
            with col3:
                st.metric("まとめシート", len(st.session_state.summary_sheets))
            with col4:
                st.metric("評価済み", len([e for e in st.session_state.evaluations.values() if 'ai_evaluation' in e]))
            
            # セッション状態の詳細表示
            with st.expander("セッション状態の詳細"):
                st.write("**事前課題:**")
                if st.session_state.pre_tasks:
                    for pid, tasks in st.session_state.pre_tasks.items():
                        participant_name = next((p['name'] for p in st.session_state.participants if p['id'] == pid), pid)
                        st.write(f"受講者: {participant_name} (ID: {pid})")
                        st.json(tasks)
                else:
                    st.write("課題なし")
                
                st.write("**まとめシート:**")
                if st.session_state.summary_sheets:
                    for pid, sheet in st.session_state.summary_sheets.items():
                        participant_name = next((p['name'] for p in st.session_state.participants if p['id'] == pid), pid)
                        st.write(f"受講者: {participant_name} (ID: {pid})")
                        st.json(sheet)
                else:
                    st.write("まとめシートなし")
            
            st.divider()
        
        # エクスポート
        st.subheader("データエクスポート")
        
        export_col1, export_col2 = st.columns(2)
        
        with export_col1:
            if st.button("📥 全データをJSON形式でエクスポート", type="primary", use_container_width=True):
                export_data = {
                    "course_info": st.session_state.course_info,
                    "participants": st.session_state.participants,
                    "evaluations": st.session_state.evaluations,
                    "pre_tasks": st.session_state.pre_tasks,
                    "summary_sheets": st.session_state.summary_sheets,
                    "exclude_keywords": st.session_state.exclude_keywords,
                    "evaluation_prompt_template": st.session_state.evaluation_prompt_template,
                    "exported_at": datetime.now().isoformat()
                }
                
                # PDFファイルは別途処理（Base64データが大きいため）
                if st.session_state.pdf_files:
                    export_data["pdf_files_info"] = {
                        k: {"filename": v["filename"], "uploaded_at": v["uploaded_at"]} 
                        for k, v in st.session_state.pdf_files.items()
                    }
                
                json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
                st.download_button(
                    label="📄 JSONファイルをダウンロード",
                    data=json_str,
                    file_name=f"training_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
        
        with export_col2:
            # PDFファイルのダウンロード
            if st.session_state.pdf_files:
                course_id = list(st.session_state.pdf_files.keys())[0] if st.session_state.pdf_files else None
                if course_id:
                    pdf_bytes, pdf_filename = get_pdf_from_session(course_id)
                    if pdf_bytes:
                        st.download_button(
                            label=f"📄 PDF資料をダウンロード ({pdf_filename})",
                            data=pdf_bytes,
                            file_name=pdf_filename,
                            mime="application/pdf",
                            use_container_width=True
                        )
        
        # データクリア
        st.subheader("データクリア")
        
        col1, col2 = st.columns([2, 1])
        with col1:
            st.warning("⚠️ この操作は取り消せません。必要なデータはエクスポートしてください。")
        with col2:
            if st.button("🗑️ 全データをクリア", type="secondary"):
                # APIキーと設定は保持
                api_key = st.session_state.api_key
                exclude_keywords = st.session_state.exclude_keywords
                prompt_template = st.session_state.evaluation_prompt_template
                
                st.session_state.clear()
                
                # APIキーと設定を復元
                st.session_state.api_key = api_key
                st.session_state.exclude_keywords = exclude_keywords
                st.session_state.evaluation_prompt_template = prompt_template
                
                st.success("✅ 全データをクリア しました（API設定は保持）")
                st.rerun()

if __name__ == "__main__":
    main()