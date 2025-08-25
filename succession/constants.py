from typing import List, Dict

# Codes for items
COMPETENCY_ORDER: List[str] = ["SF", "VCI", "OL", "DE", "LA"]
READINESS_ORDER: List[str] = ["CV", "MR", "MN"]

COMPETENCY_LABELS: Dict[str, str] = {
    "SF": "戦略構想力",
    "VCI": "価値創出・イノベーション力",
    "OL": "人的資源・組織運営力",
    "DE": "意思決定・実行力",
    "LA": "学習・適応力",
}

READINESS_LABELS: Dict[str, str] = {
    "CV": "キャリアビジョン",
    "MR": "使命感・責任感",
    "MN": "体制・ネットワーク",
}

ALL_CODES: List[str] = COMPETENCY_ORDER + READINESS_ORDER

