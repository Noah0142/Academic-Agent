# -*- coding: utf-8 -*-
"""
OpenAlex 检索模块 — 开放学术图谱数据源
"""
import os, json, sys, io


OPENALEX_BASE = 'https://api.openalex.org/works'


def _cn_to_en_medical(theme):
    """简单的中文医学术语到英文的映射。"""
    mapping = {
        '膝骨关节炎': 'Knee Osteoarthritis',
        '膝关节': 'Knee Joint',
        '膝': 'Knee',
        '肺结节': 'Lung Nodule',
        '肺': 'Lung',
        '糖尿病': 'Diabetes Mellitus',
        '糖尿病视网膜病变': 'Diabetic Retinopathy',
        '视网膜病变': 'Retinopathy',
        '肿瘤': 'Tumor',
        '癌症': 'Cancer',
        '肺癌': 'Lung Cancer',
        '乳腺癌': 'Breast Cancer',
        '心脏病': 'Heart Disease',
        '心血管': 'Cardiovascular',
        '脑卒中': 'Stroke',
        '中风': 'Stroke',
        '阿尔茨海默': 'Alzheimer',
        '痴呆': 'Dementia',
        '帕金森': 'Parkinson',
        '骨折': 'Fracture',
        '骨密度': 'Bone Density',
        '骨质疏松': 'Osteoporosis',
        '精准分型': 'Precision Classification',
        '精准诊断': 'Precision Diagnosis',
        '精准治疗': 'Precision Treatment',
        '影像学': 'Medical Imaging',
        '医学影像': 'Medical Imaging',
        '深度学习': 'Deep Learning',
        '机器学习': 'Machine Learning',
        '人工智能': 'Artificial Intelligence',
        '卷积神经网络': 'Convolutional Neural Network',
        'CNN': 'CNN',
        '迁移学习': 'Transfer Learning',
        '分类': 'Classification',
        '分割': 'Segmentation',
        '检测': 'Detection',
        '应用': 'Application',
        '诊断': 'Diagnosis',
        '治疗': 'Treatment',
        '预后': 'Prognosis',
        '分析': 'Analysis',
        '研究': 'Study',
        '基于': 'Based on',
        '在': 'in',
        '中': 'in',
        '的': ' ',
    }
    result = theme
    for cn, en in sorted(mapping.items(), key=lambda x: -len(x[0])):
        if cn in result:
            result = result.replace(cn, f' {en} ')
    result = ' '.join(result.split())
    return result.strip()


def search_openalex(theme, task_card=None):
    """从 OpenAlex 检索文献。"""
    try:
        import requests
    except ImportError:
        return []

    # 优先使用 LLM 生成的检索式
    search_query = None
    if task_card:
        queries = task_card.get('queries', {})
        oalex_query = queries.get('openalex', {})
        if isinstance(oalex_query, dict):
            search_query = oalex_query.get('query')

    # 回退到英文主题
    if not search_query:
        search_query = _cn_to_en_medical(theme)

    params = {
        'search': search_query,
        'per_page': 20,
        'mailto': os.environ.get('PUBMED_EMAIL', 'Noah13610480142@outlook.com'),
    }
    try:
        resp = requests.get(OPENALEX_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f'[OpenAlex] error: {e}')
        return []

    results = []
    for work in data.get('results', [])[:20]:
        authorships = work.get('authorships', [])
        author_names = [a.get('author', {}).get('display_name', '') for a in authorships]
        year = work.get('publication_year', '')
        doi = work.get('doi', '') or ''
        pmid = work.get('ids', {}).get('pmid', '') or ''

        results.append({
            'id': f"OA_{work.get('id', '').split('/')[-1]}",
            'pmid': pmid,
            'title': work.get('title', ''),
            'authors': ', '.join(author_names),
            'year': str(year),
            'journal': ((work.get('primary_location') or {}).get('source') or {}).get('display_name', ''),
            'doi': doi.replace('https://doi.org/', '') if doi else '',
            'abstract': work.get('abstract', '') or '',
            'database': 'OpenAlex',
            'evidence_level': '未评级',
            'source_url': work.get('doi', ''),
            'cited_by_count': work.get('cited_by_count', 0),
        })
    return results
