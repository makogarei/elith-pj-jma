from __future__ import annotations
from typing import Dict, Any
import streamlit as st
from .defaults import PROMPTS_DEFAULTS, RUBRICS_DEFAULTS


def ensure_session() -> None:
    if 'succession' not in st.session_state:
        st.session_state.succession = {}
    s = st.session_state.succession
    s.setdefault('prompts', {})
    s.setdefault('prompts_version', 'v1')
    s.setdefault('rubrics', {})
    s.setdefault('flags', {'dry_run': False})

    # Init defaults if empty
    if not s['prompts']:
        s['prompts'] = {
            'norm': PROMPTS_DEFAULTS['norm'],
            'evidence': PROMPTS_DEFAULTS['evidence'],
            'score': PROMPTS_DEFAULTS['score'],
        }
    if not s['rubrics']:
        s['rubrics'] = dict(RUBRICS_DEFAULTS)


def get_prompts() -> Dict[str, str]:
    ensure_session()
    return st.session_state.succession['prompts']


def get_prompt(key: str) -> str:
    return get_prompts().get(key, '')


def set_prompt(key: str, value: str) -> None:
    ensure_session()
    st.session_state.succession['prompts'][key] = value


def get_rubrics() -> Dict[str, str]:
    ensure_session()
    return st.session_state.succession['rubrics']


def set_rubric(code: str, text: str) -> None:
    ensure_session()
    st.session_state.succession['rubrics'][code] = text


def get_flags() -> Dict[str, Any]:
    ensure_session()
    return st.session_state.succession['flags']


def set_flag(name: str, value: Any) -> None:
    ensure_session()
    st.session_state.succession['flags'][name] = value


def build_rubrics_text() -> str:
    rubrics = get_rubrics()
    lines = []
    for code, txt in rubrics.items():
        lines.append(f"{code}: {txt}")
    return "\n".join(lines)


def build_config() -> Dict[str, Any]:
    return {
        'prompts': get_prompts(),
        'rubrics_text': build_rubrics_text(),
        'flags': get_flags(),
    }

