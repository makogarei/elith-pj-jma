from __future__ import annotations
from typing import Any, Dict, Callable, Optional
import json
import time


def _call_claude(client, system_prompt: str, user_content: str) -> Dict | None:
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{"role": "user", "content": f"System: {system_prompt}\n\nUser: {user_content}\n\nPlease respond with valid JSON only."}],
        )
        content = response.content[0].text
        import re
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            return json.loads(json_match.group())
        else:
            return json.loads(content)
    except Exception:
        return None


def run_pipeline(
    raw_text: str,
    cfg: Dict[str, Any],
    api_key: str | None,
    reporter: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
) -> Dict:
    from .dummy import generate_dummy_assessment
    import anthropic

    if not raw_text or not raw_text.strip():
        return None

    # Dry-run or no key → dummy
    if cfg.get('flags', {}).get('dry_run') or not api_key:
        if reporter:
            reporter("dry_run", "start", {})
            reporter("dry_run", "success", {})
        return generate_dummy_assessment(raw_text)

    client = anthropic.Anthropic(api_key=api_key)

    # Step 1: normalize
    if reporter:
        reporter("normalize", "start", {})
    t0 = time.monotonic()
    norm = _call_claude(
        client,
        cfg['prompts']['norm'],
        f"入力データ(JSON):\n{json.dumps({'input': {'text': raw_text}})}",
    )
    if not norm:
        if reporter:
            reporter("normalize", "failure", {"elapsed_sec": round(time.monotonic()-t0, 2)})
        return generate_dummy_assessment(raw_text)
    if reporter:
        reporter("normalize", "success", {"elapsed_sec": round(time.monotonic()-t0, 2)})

    # Step 2: evidence (include ORIGINAL_TEXT)
    if reporter:
        reporter("evidence", "start", {})
    t1 = time.monotonic()
    evid = _call_claude(
        client,
        cfg['prompts']['evidence'],
        f"正規化入力:\n{json.dumps(norm)}\n---\nORIGINAL_TEXT:\n{raw_text}",
    )
    if not evid:
        if reporter:
            reporter("evidence", "failure", {"elapsed_sec": round(time.monotonic()-t1, 2)})
        return generate_dummy_assessment(raw_text)
    if reporter:
        reporter("evidence", "success", {"elapsed_sec": round(time.monotonic()-t1, 2)})

    # Step 3: score with rubrics
    if reporter:
        reporter("score", "start", {})
    t2 = time.monotonic()
    score_user_content = f"正規化入力:\n{json.dumps(norm)}\n---\nエビデンス:\n{json.dumps(evid)}\n---\nRUBRICS:\n{cfg.get('rubrics_text','')}"
    scores = _call_claude(
        client,
        cfg['prompts']['score'],
        score_user_content,
    )
    if not scores:
        if reporter:
            reporter("score", "failure", {"elapsed_sec": round(time.monotonic()-t2, 2)})
        return generate_dummy_assessment(raw_text)
    if reporter:
        reporter("score", "success", {"elapsed_sec": round(time.monotonic()-t2, 2)})

    return {"normalized": norm, "evidence": evid, "scores": scores}
