from typing import Dict, List
from .constants import COMPETENCY_ORDER, READINESS_ORDER, ALL_CODES, COMPETENCY_LABELS, READINESS_LABELS


def generate_dummy_evidence(original_text: str) -> Dict:
    import re
    sentences = [s.strip() for s in re.split(r"[。\n\r]", original_text or "") if s.strip()]
    if not sentences:
        sentences = [(original_text or "入力がありません")[:80]]
    ev_list: List[Dict] = []
    for i, code in enumerate(ALL_CODES):
        sent = sentences[i % len(sentences)] or "（ダミー）入力文からの抜粋"
        ev_list.append({
            "id": f"EV-{code}-{i+1}",
            "target": code,
            "quote": sent,
        })
    return {"list": ev_list}


def generate_dummy_scores(evidence: Dict) -> Dict:
    ev_list = evidence.get("list", []) if isinstance(evidence, dict) else []
    by_code = {c: [] for c in ALL_CODES}
    for ev in ev_list:
        tgt = ev.get("target")
        if tgt in by_code:
            by_code[tgt].append(ev.get("id"))

    comp = {}
    for code in COMPETENCY_ORDER:
        label = COMPETENCY_LABELS.get(code, code)
        comp[code] = {"score": 4, "reason": f"{label}に関する記述が入力文から確認されました。", "evidenceIds": by_code.get(code, [])}
    ready = {}
    for code in READINESS_ORDER:
        label = READINESS_LABELS.get(code, code)
        ready[code] = {"score": 3, "reason": f"{label}に関する記述が入力文から確認されました。", "evidenceIds": by_code.get(code, [])}
    return {"competencies": comp, "readiness": ready}


def generate_dummy_normalized(original_text: str) -> Dict:
    return {"items": [{"docId": "D-1", "section": "summary", "summary": "入力内容のダミー要約", "text": (original_text or "")[:120]}], "confidence": "low"}


def generate_dummy_assessment(original_text: str) -> Dict:
    evidence = generate_dummy_evidence(original_text)
    scores = generate_dummy_scores(evidence)
    return {
        "normalized": generate_dummy_normalized(original_text),
        "evidence": evidence,
        "scores": scores,
        "meta": {"dummy": True},
    }

