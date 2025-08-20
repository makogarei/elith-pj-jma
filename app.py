import streamlit as st
import pandas as pd
import openai
import json

# --- 1. プロンプト定義 ---
# すべてのプロンプトを単一の辞書に集約
PROMPTS = {
    "pr_norm_ja": {
        "step": "normalize",
        "name": "Normalize JA",
        "content": "入力テキストを以下のセクションに分類し、各エントリを120字以内で要約してください。出力は JSON: {\"items\":[{\" :[{\"docId\":\"...\",\"section\":\"dept_status|dept_issues|solutions|vision|training_reflection|next1to2y\",\"summary\":\"...\",\"text\":\"...\"}], \"confidence\":\"low|med|high\"} のみ。"
    },
    "pr_evi_ja": {
        "step": "evidence",
        "name": "Evidence JA",
        "content": "正規化されたテキストから評価根拠を抽出。各抜粋は原文30〜200字、targetは SF|VCI|OL|DE|LA|CV|MR|MN、polarityは pos|neg|neutral。出力は JSON: {\"list\":[{\"id\":\"EV-1\",\"docId\":\"...\",\"polarity\":\"pos\",\"target\":\"DE\",\"quote\":\"...\",\"note\":\"...\"}]} のみ。"
    },
    "pr_score_ja": {
        "step": "score",
        "name": "Score JA",
        "content": "Evidenceに基づき各項目を1-5で採点。理由は100〜180字で、必ず evidenceIds を含める。獲得度は四捨五入で算出: solution=0.40*VCI+0.30*DE+0.30*LA、achievement=0.50*DE+0.30*OL+0.20*LA、management=0.40*OL+0.40*SF+0.20*MR。JSONのみで返答。"
    },
    "pr_score_SF_ja": {
        "step": "score_SF",
        "name": "SF Detail JA",
        "content": "あなたは経営者評価の専門家です。戦略構想力(Strategic Foresight)について3要件で詳細評価してください。\n\n【評価要件】\n要件1: 業界動向・技術革新を定期的に分析し、5〜10年後の事業機会を経営会議で提示している\n要件2: 複数事業の収益構造・リスクを数値で把握し、ポートフォリオ最適化の意思決定を行っている\n要件3: 社会課題や規制変化を先取りし、自社の強みと結びつけた新たな事業構想を策定している\n\n【スコア基準】\n5: 要件を高いレベルで満たし具体的成果あり／4: 要件を満たし一定成果／3: 基本的に満たす／2: 部分的／1: ほとんど満たさない\n\n【出力形式】JSONのみ:\n{\n  \"overall\": {\"score\": 1-5, \"reason\": \"総合評価理由120-180字\", \"evidenceIds\": [\"EV-X\"]},\n  \"criteria\": {\n    \"criterion1\": {\"score\": 1-5, \"reason\": \"要件1評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion2\": {\"score\": 1-5, \"reason\": \"要件2評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion3\": {\"score\": 1-5, \"reason\": \"要件3評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]}\n  }\n}"
    },
    "pr_score_VCI_ja": {
        "step": "score_VCI",
        "name": "VCI Detail JA",
        "content": "あなたは経営者評価の専門家です。価値創出・イノベーション力(VCI)について3要件で詳細評価してください。\n\n【評価要件】\n要件1: 現場訪問や対話を通じ潜在ニーズを抽出し、新サービスに反映している\n要件2: 前例に囚われず社内外リソースを組合せ新しいビジネスモデルを提案している\n要件3: デジタルやプロセス改革を主導し、顧客体験と業務効率を同時に向上している\n\n【スコア基準】\n5: 要件を高いレベルで満たし具体的成果あり／4: 要件を満たし一定成果／3: 基本的に満たす／2: 部分的／1: ほとんど満たさない\n\n【出力形式】JSONのみ:\n{\n  \"overall\": {\"score\": 1-5, \"reason\": \"総合評価理由120-180字\", \"evidenceIds\": [\"EV-X\"]},\n  \"criteria\": {\n    \"criterion1\": {\"score\": 1-5, \"reason\": \"要件1評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion2\": {\"score\": 1-5, \"reason\": \"要件2評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion3\": {\"score\": 1-5, \"reason\": \"要件3評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]}\n  }\n}"
    },
    "pr_score_OL_ja": {
        "step": "score_OL",
        "name": "OL Detail JA",
        "content": "あなたは経営者評価の専門家です。人的資源・組織運営力(OL)について3要件で詳細評価してください。\n\n【評価要件】\n要件1: 明確で共感を呼ぶビジョンを示し、各層へ継続的に浸透させている\n要件2: 多様な人材を適材適所に配置し、能力を最大化する環境を整えている\n要件3: 部門横断チームで全社連携と相互理解を促進している\n\n【スコア基準】\n5: 要件を高いレベルで満たし具体的成果あり／4: 要件を満たし一定成果／3: 基本的に満たす／2: 部分的／1: ほとんど満たさない\n\n【出力形式】JSONのみ:\n{\n  \"overall\": {\"score\": 1-5, \"reason\": \"総合評価理由120-180字\", \"evidenceIds\": [\"EV-X\"]},\n  \"criteria\": {\n    \"criterion1\": {\"score\": 1-5, \"reason\": \"要件1評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion2\": {\"score\": 1-5, \"reason\": \"要件2評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion3\": {\"score\": 1-5, \"reason\": \"要件3評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]}\n  }\n}"
    },
    "pr_score_DE_ja": {
        "step": "score_DE",
        "name": "DE Detail JA",
        "content": "あなたは経営者評価の専門家です。意思決定・実行力(DE)について3要件で詳細評価してください。\n\n【評価要件】\n要件1: 不確実でも期限を設け入手可能な情報で決断している\n要件2: 反対意見にもぶれず長期利益に資する決断を貫いている\n要件3: 進捗を定量測定し迅速に軌道修正・資源再配分を行っている\n\n【スコア基準】\n5: 要件を高いレベルで満たし具体的成果あり／4: 要件を満たし一定成果／3: 基本的に満たす／2: 部分的／1: ほとんど満たさない\n\n【出力形式】JSONのみ:\n{\n  \"overall\": {\"score\": 1-5, \"reason\": \"総合評価理由120-180字\", \"evidenceIds\": [\"EV-X\"]},\n  \"criteria\": {\n    \"criterion1\": {\"score\": 1-5, \"reason\": \"要件1評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion2\": {\"score\": 1-5, \"reason\": \"要件2評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion3\": {\"score\": 1-5, \"reason\": \"要件3評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]}\n  }\n}"
    },
    "pr_score_LA_ja": {
        "step": "score_LA",
        "name": "LA Detail JA",
        "content": "あなたは経営者評価の専門家です。学習・適応力(LA)について3要件で詳細評価してください。\n\n【評価要件】\n要件1: 最新理論や技術トレンドを学び自社経営へ応用している\n要件2: 失敗から学びを抽出し組織で共有、次の戦略へ反映している\n要件3: 外部対話・協業で新視点を取り入れ変革に活かしている\n\n【スコア基準】\n5: 要件を高いレベルで満たし具体的成果あり／4: 要件を満たし一定成果／3: 基本的に満たす／2: 部分的／1: ほとんど満たさない\n\n【出力形式】JSONのみ:\n{\n  \"overall\": {\"score\": 1-5, \"reason\": \"総合評価理由120-180字\", \"evidenceIds\": [\"EV-X\"]},\n  \"criteria\": {\n    \"criterion1\": {\"score\": 1-5, \"reason\": \"要件1評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion2\": {\"score\": 1-5, \"reason\": \"要件2評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion3\": {\"score\": 1-5, \"reason\": \"要件3評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]}\n  }\n}"
    },
    "pr_score_CV_ja": {
        "step": "score_CV",
        "name": "CV Detail JA",
        "content": "あなたは経営者評価の専門家です。キャリアビジョン(CV)について3要件で詳細評価してください。\n\n【評価要件】\n要件1: 目指す経営者像を具体的に言語化し一貫して説明できる\n要件2: 1-3/3-5/5-10年の役割と準備行動を具体化している\n要件3: 自己分析に基づき強み・課題を認識し能力開発を実践している\n\n【スコア基準】\n5: 要件を高いレベルで満たし具体的成果あり／4: 要件を満たし一定成果／3: 基本的に満たす／2: 部分的／1: ほとんど満たさない\n\n【出力形式】JSONのみ:\n{\n  \"overall\": {\"score\": 1-5, \"reason\": \"総合評価理由120-180字\", \"evidenceIds\": [\"EV-X\"]},\n  \"criteria\": {\n    \"criterion1\": {\"score\": 1-5, \"reason\": \"要件1評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion2\": {\"score\": 1-5, \"reason\": \"要件2評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion3\": {\"score\": 1-5, \"reason\": \"要件3評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]}\n  }\n}"
    },
    "pr_score_MR_ja": {
        "step": "score_MR",
        "name": "MR Detail JA",
        "content": "あなたは経営者評価の専門家です。使命感・責任感(MR)について3要件で詳細評価してください。\n\n【評価要件】\n要件1: 企業活動の社会的意義を深く理解し自らの考えを持っている\n要件2: 多様なステークホルダーの期待を把握し責任を自覚している\n要件3: 困難でも会社の未来を守る決断を下す意思を示している\n\n【スコア基準】\n5: 要件を高いレベルで満たし具体的成果あり／4: 要件を満たし一定成果／3: 基本的に満たす／2: 部分的／1: ほとんど満たさない\n\n【出力形式】JSONのみ:\n{\n  \"overall\": {\"score\": 1-5, \"reason\": \"総合評価理由120-180字\", \"evidenceIds\": [\"EV-X\"]},\n  \"criteria\": {\n    \"criterion1\": {\"score\": 1-5, \"reason\": \"要件1評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion2\": {\"score\": 1-5, \"reason\": \"要件2評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion3\": {\"score\": 1-5, \"reason\": \"要件3評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]}\n  }\n}"
    },
    "pr_score_MN_ja": {
        "step": "score_MN",
        "name": "MN Detail JA",
        "content": "あなたは経営者評価の専門家です。体制・ネットワーク構築(MN)について3要件で詳細評価してください。\n\n【評価要件】\n要件1: 社内外と良好な信頼関係を築き協力して業務を進めている\n要件2: 研究機関等と関係を築き外部環境を捉える体制を持つ\n要件3: 事業・業務承継のリスクを認識し適切な承継対策を想定している\n\n【スコア基準】\n5: 要件を高いレベルで満たし具体的成果あり／4: 要件を満たし一定成果／3: 基本的に満たす／2: 部分的／1: ほとんど満たさない\n\n【出力形式】JSONのみ:\n{\n  \"overall\": {\"score\": 1-5, \"reason\": \"総合評価理由120-180字\", \"evidenceIds\": [\"EV-X\"]},\n  \"criteria\": {\n    \"criterion1\": {\"score\": 1-5, \"reason\": \"要件1評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion2\": {\"score\": 1-5, \"reason\": \"要件2評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]},\n    \"criterion3\": {\"score\": 1-5, \"reason\": \"要件3評価理由100-150字\", \"evidenceIds\": [\"EV-X\"]}\n  }\n}"
    }
}

ACQUISITION_FORMULAS = {
    "solution": {"VCI": 0.40, "DE": 0.30, "LA": 0.30},
    "achievement": {"DE": 0.50, "OL": 0.30, "LA": 0.20},
    "management": {"OL": 0.40, "SF": 0.40, "MR": 0.20}
}

# --- 2. データ定義 ---
initial_data = {
    "項目": [
        "部署の現状と課題", "解決策の提案", "今後のビジョン",
        "研修の振り返り", "今後1-2年の取り組み",
    ],
    "あなたの考え": ["", "", "", "", ""]
}
input_df = pd.DataFrame(initial_data)

# --- 3. ビジネスロジック定義 (AIパイプライン) ---

def _call_llm(client, system_prompt, user_content):
    """LLM呼び出しの共通ラッパー"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

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

def run_evaluation_pipeline(user_input_df):
    """3ステップの評価パイプラインを実行するオーケストレーター"""
    full_text = ""
    for _, row in user_input_df.iterrows():
        if row['あなたの考え'] and row['あなたの考え'].strip():
            full_text += f"## {row['項目']}\n\n{row['あなたの考え']}\n\n"

    if not full_text:
        st.warning("入力がありません。")
        return None

    try:
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        final_result = {}

        with st.status("評価パイプラインを実行中...", expand=True) as status:
            status.update(label="ステップ1/3: テキストを正規化しています...", state="running")
            normalized_data = _call_llm(
                client,
                PROMPTS["pr_norm_ja"]["content"],
                f"入力データ(JSON):\n{json.dumps({'input': {'text': full_text}})}"
            )
            final_result["normalized"] = normalized_data

            status.update(label="ステップ2/3: 評価エビデンスを抽出しています...", state="running")
            evidence_data = _call_llm(
                client,
                PROMPTS["pr_evi_ja"]["content"],
                f"正規化入力:\n{json.dumps(normalized_data)}"
            )
            final_result["evidence"] = evidence_data

            status.update(label="ステップ3/3: 最終スコアを算出しています...", state="running")
            user_content = f"正規化入力:\n{json.dumps(normalized_data)}\n---\nエビデンス:\n{json.dumps(evidence_data)}"
            scores = _call_llm(
                client,
                PROMPTS["pr_score_ja"]["content"],
                user_content
            )
            
            acquisition_scores = _calculate_acquisition_scores(scores)
            scores["acquisition"] = acquisition_scores
            final_result["scores"] = scores
            
            status.update(label="評価パイプライン完了！", state="complete")

        return final_result

    except openai.APIConnectionError as e:
        st.error(f"APIサーバーへの接続に失敗しました: {e}")
    except openai.RateLimitError as e:
        st.error(f"APIのレート制限に達しました: {e}")
    except openai.APIStatusError as e:
        st.error(f"APIステータスエラー: {e.status_code} {e.response}")
    except Exception as e:
        st.error(f"予期せぬエラーが発生しました: {e}")
    
    return None

# --- 4. Streamlit UI構築 ---
st.set_page_config(layout="wide")
st.title("AIによる昇進アセスメント評価ツール")
st.info("以下の表にあなたの考えを入力し、「AI評価を実行する」ボタンを押してください。3ステップのAI評価が実行されます。")

st.header("評価シート")
edited_df = st.data_editor(
    input_df, height=300,
    column_config={
        "項目": st.column_config.TextColumn(disabled=True),
        "あなたの考え": st.column_config.TextColumn(width="large")
    }, hide_index=True)

if st.button("AI評価を実行する", type="primary"):
    if "OPENAI_API_KEY" not in st.secrets or not st.secrets["OPENAI_API_KEY"]:
        st.error("OpenAIのAPIキーが設定されていません。.streamlit/secrets.tomlファイルを確認してください。")
    else:
        final_evaluation = run_evaluation_pipeline(edited_df)
        if final_evaluation:
            st.header("最終評価結果")
            st.json(final_evaluation)