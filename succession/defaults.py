PROMPTS_DEFAULTS = {
    "norm": (
        "入力テキストを以下のセクションに分類してください。"
        "各エントリは (1) summary: 120字以内の要約 と (2) text: 原文抜粋（逐語、改変禁止）を必ず含めます。"
        "出力は JSON: {\"items\":[{\"docId\":\"...\",\"section\":\"dept_status|dept_issues|solutions|vision|training_reflection|next1to2y\",\"summary\":\"...\",\"text\":\"...\"}], \"confidence\":\"low|med|high\"} のみ。"
    ),
    "evidence": (
        "提供された ORIGINAL_TEXT（原文）に基づき評価根拠を抽出。"
        "quote は ORIGINAL_TEXT からの逐語抜粋（サブストリング）であり、要約・言い換えは禁止。"
        "各抜粋は30〜200字、targetは SF|VCI|OL|DE|LA|CV|MR|MN、polarityは pos|neg|neutral。"
        "出力は JSON: {\"list\":[{\"id\":\"EV-1\",\"docId\":\"...\",\"polarity\":\"pos\",\"target\":\"DE\",\"quote\":\"...\",\"note\":\"...\"}]} のみ。"
    ),
    "score": (
        "Evidence(list)に基づき、以下の8項目について score(1-5), reason, evidenceIds を必ず返してください。JSONのみ。\n\n"
        "必須の構造:\n{\n  \"competencies\": {\n    \"SF\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [\"EV-1\", ...]},\n"
        "    \"VCI\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]},\n    \"OL\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]},\n"
        "    \"DE\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]},\n    \"LA\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]}\n  },\n"
        "  \"readiness\": {\n    \"CV\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]},\n    \"MR\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]},\n    \"MN\": {\"score\": 1, \"reason\": \"...\", \"evidenceIds\": [...]}\n  }\n}\n\n"
        "注: scoreは1〜5の整数。reasonは100〜180字。evidenceIdsは抽出済みEvidenceのidのみ。"
    ),
}

RUBRICS_DEFAULTS = {
    "SF": "長期視点・整合性・仮説妥当性・全体観の示唆を重視",
    "VCI": "価値仮説・差別化・改善/創造アクションの具体性",
    "OL": "配員・育成・協働・制度活用など運営の具体性",
    "DE": "意思決定プロセス・リスク評価・実行計画の緻密さ",
    "LA": "振り返り・学習循環・適応の速さと広がり",
    "CV": "キャリア像の具体性・期間・整合性",
    "MR": "使命/責任の根拠・動機の一貫性",
    "MN": "体制・利害関係者・ネットワーク活用の実効性",
}

