# -*- coding: utf-8 -*-
"""
任务卡生成模块 — PICO-D + 医工交叉三维度拆解 -> YAML 任务卡
"""
import sys, io, uuid, datetime, os

import yaml

TASK_CARDS_DIR = None


def set_task_cards_dir(base_dir):
    global TASK_CARDS_DIR
    TASK_CARDS_DIR = base_dir
    import os
    os.makedirs(TASK_CARDS_DIR, exist_ok=True)


def generate_task_card(theme, problem='', innovation='', outcome='', data='', direction='',
                       databases=None, time_range='近5年', doc_types=None,
                       language='英语+中文', sub_questions=None, audience='', word_count=3000):
    """生成结构化任务卡。"""
    if databases is None:
        databases = ['PubMed', 'IEEE Xplore']
    if doc_types is None:
        doc_types = ['Journal Article', 'Review']
    if sub_questions is None:
        sub_questions = []

    task_id = str(uuid.uuid4())[:8]
    task_card = {
        'task_id': task_id,
        'theme': theme,
        'created_at': datetime.datetime.now().isoformat(),
        'status': 'pending_confirm',
        'pico_d': {
            'P_Problem': problem,
            'I_Innovation': innovation,
            'O_Outcome': outcome,
            'D_Data': data,
            'D_Direction': direction,
        },
        'databases': databases,
        'time_range': time_range,
        'doc_types': doc_types,
        'language': language,
        'sub_questions': sub_questions,
        'audience': audience,
        'word_count': word_count,
        'data_sources': _select_data_sources(theme, direction),
    }
    return task_card


def save_task_card(task_card):
    """保存任务卡为 YAML 文件。"""
    if TASK_CARDS_DIR is None:
        _auto_init_task_cards_dir()
    if TASK_CARDS_DIR is None:
        raise RuntimeError('TASK_CARDS_DIR not set')
    path = f"{TASK_CARDS_DIR}/{task_card['task_id']}.yaml"
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(task_card, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return path


def _auto_init_task_cards_dir():
    global TASK_CARDS_DIR
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        base = os.path.dirname(here)
        TASK_CARDS_DIR = os.path.join(base, 'task_cards')
        os.makedirs(TASK_CARDS_DIR, exist_ok=True)
    except Exception:
        pass


def _select_data_sources(theme, direction):
    """根据主题和方向推荐数据源。"""
    theme_lower = theme.lower()
    is_medical = any(kw in theme_lower for kw in ['膝', 'knee', 'medical', 'clinical'])
    is_ai = any(kw in theme_lower for kw in ['人工智能', 'ai', 'deep learning'])

    sources = ['PubMed']
    if is_ai:
        sources.append('IEEE Xplore')
    if is_medical:
        sources.append('Embase')
    sources.extend(['OpenAlex', 'Semantic Scholar'])
    return sources
