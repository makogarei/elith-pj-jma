from __future__ import annotations
import json
import streamlit as st
import pandas as pd
from typing import Any, Dict

from .constants import COMPETENCY_ORDER, READINESS_ORDER, COMPETENCY_LABELS, READINESS_LABELS
from . import config as scfg
from . import pipeline as spipe


def render_prompts_panel():
    scfg.ensure_session()
    prompts = scfg.get_prompts()
    rubrics = scfg.get_rubrics()

    tabs = st.tabs(["正規化", "エビデンス", "スコア（共通）", "スコア（項目別ヒント）", "プレビュー"])
    with tabs[0]:
        norm_val = st.text_area("正規化プロンプト", value=prompts.get('norm',''), height=160)
        if st.button("保存（正規化）"):
            scfg.set_prompt('norm', norm_val)
            st.success("保存しました")
    with tabs[1]:
        ev_val = st.text_area("エビデンス抽出プロンプト", value=prompts.get('evidence',''), height=220)
        if st.button("保存（エビデンス）"):
            scfg.set_prompt('evidence', ev_val)
            st.success("保存しました")
    with tabs[2]:
        sc_val = st.text_area("スコアリング共通プロンプト", value=prompts.get('score',''), height=260)
        if st.button("保存（スコア）"):
            scfg.set_prompt('score', sc_val)
            st.success("保存しました")
    with tabs[3]:
        for code, label in {**COMPETENCY_LABELS, **READINESS_LABELS}.items():
            txt = st.text_area(f"{label}（{code}）", value=rubrics.get(code, ''), height=90, key=f"rub_{code}")
            scfg.set_rubric(code, txt)
        st.info("入力は即時反映されます")
    with tabs[4]:
        cfg = scfg.build_config()
        st.code(json.dumps({"prompts": cfg['prompts'], "rubrics": cfg['rubrics_text']}, ensure_ascii=False, indent=2), language="json")


def render_assessment_ui():
    scfg.ensure_session()

    # Sidebar: back, API, dry-run
    with st.sidebar:
        st.header("📋 メニュー")
        if st.button("🏠 システム選択に戻る"):
            st.session_state.system_mode = None
            st.rerun()
        st.divider()

        with st.expander("🔑 API設定", expanded=not st.session_state.api_key):
            api_key_input = st.text_input("Claude API Key", value=st.session_state.api_key, type="password")
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
        dry = st.checkbox("ドライラン（ダミー出力）", value=scfg.get_flags().get('dry_run', False))
        scfg.set_flag('dry_run', dry)

    # Main body with tabs like 集合研修: 評価 / プロンプト設定
    st.header("サクセッション評価ツール")
    tabs = st.tabs(["評価", "プロンプト設定"])

    with tabs[0]:
        st.info("課題と実施内容など、評価に必要な情報を1つのテキストボックスにまとめて入力してください。\n入力後に『AI評価を実行する』を押すと3ステップ評価を行います。")

        user_bulk_text = st.text_area(
            "課題・実施内容（まとめて入力）",
            height=260,
            placeholder="例）課題文、取り組み内容、成果、振り返り、今後の計画 などをまとめて記載してください。",
        )

        if st.button("AI評価を実行する", type="primary"):
            raw_text = user_bulk_text.strip()
            if not raw_text:
                st.warning("入力がありません。テキストを入力してください。")
                return
            final_evaluation = spipe.run_pipeline(raw_text, scfg.build_config(), st.session_state.api_key)
            if not final_evaluation:
                st.warning("結果を生成できませんでした。APIキーやドライラン設定を確認して再実行してください。")
                return

            st.header("最終評価結果")

            scores = final_evaluation.get("scores", {}) or {}
            evidence_list = final_evaluation.get("evidence", {}).get("list", []) or []

            ev_by_id = {}
            ev_by_target = {code: [] for code in (COMPETENCY_ORDER + READINESS_ORDER)}
            for ev in evidence_list:
                ev_id = ev.get("id")
                if ev_id:
                    ev_by_id[ev_id] = ev
                tgt = ev.get("target")
                if tgt in ev_by_target:
                    ev_by_target[tgt].append(ev)

            def render_item(code: str, label: str, data_block: Dict[str, Any]):
                # score
                score_val = None
                if isinstance(data_block, dict):
                    score_val = data_block.get("score") or data_block.get("Score")
                title = f"### {label}"
                if isinstance(score_val, (int, float)):
                    title = f"### {label} — {int(score_val)}/5"
                st.markdown(title)

                # evidence
                ids = []
                if isinstance(data_block, dict):
                    ids = data_block.get("evidenceIds") or []
                quotes = []
                for eid in ids:
                    ev = ev_by_id.get(eid)
                    if ev and ev.get("quote"):
                        quotes.append(ev.get("quote"))
                if not quotes:
                    for ev in ev_by_target.get(code, [])[:3]:
                        if ev.get("quote"):
                            quotes.append(ev.get("quote"))
                st.write("根拠（原文）")
                if quotes:
                    for q in quotes:
                        st.write(q)
                else:
                    st.caption("該当する原文の根拠は見つかりませんでした。")

                # reason
                reason = ""
                if isinstance(data_block, dict):
                    reason = data_block.get("reason") or ""
                if reason:
                    st.write("コメント")
                    st.write(reason)

            # 獲得度
            st.subheader("獲得度")
            comp = scores.get("competencies", {}) or {}
            for code in COMPETENCY_ORDER:
                render_item(code, COMPETENCY_LABELS.get(code, code), comp.get(code, {}))
                st.divider()

            # 準備度
            st.subheader("準備度")
            ready = scores.get("readiness", {}) or {}
            for code in READINESS_ORDER:
                render_item(code, READINESS_LABELS.get(code, code), ready.get(code, {}))
                st.divider()

            with st.expander("詳細（JSON全体）"):
                st.json(final_evaluation)

    with tabs[1]:
        render_prompts_panel()
