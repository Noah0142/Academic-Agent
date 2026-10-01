# -*- coding: utf-8 -*-
"""
IEEE Xplore 检索模块 — IEEE Xplore API / 降级样例
API Key 通过环境变量 IEEE_API_KEY 或 .env 文件设置。
"""
import os, json, sys, io


try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

IEEE_API_KEY = os.environ.get('IEEE_API_KEY', '')


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


def search_ieee(theme, task_card=None):
    """在 IEEE Xplore 中检索文献。"""
    if not IEEE_API_KEY:
        return _sample_results(theme)

    # 优先使用 LLM 生成的检索式
    querytext = None
    if task_card:
        queries = task_card.get('queries', {})
        ieee_query = queries.get('ieee', {})
        if isinstance(ieee_query, dict):
            querytext = ieee_query.get('query')

    # 回退到英文主题
    if not querytext:
        querytext = _cn_to_en_medical(theme)

    url = 'https://ieeexploreapi.ieee.org/api/v1/search/articles'
    params = {
        'apikey': IEEE_API_KEY,
        'querytext': querytext,
        'max_records': 50,
        'start_record': 1,
        'sort_order': 'desc',
        'sort_field': 'relevance',
    }

    try:
        import requests
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f'[IEEE] API error: {e}')
        return _sample_results()

    articles = data.get('articles', [])
    results = []
    for art in articles[:20]:
        results.append({
            'id': f"IEEE_{art.get('article_number', '')}",
            'title': art.get('title', ''),
            'authors': ', '.join([a.get('full_name', '') for a in art.get('authors', {}).get('authors', [])]),
            'year': str(art.get('publication_year', '')),
            'journal': art.get('publication_title', ''),
            'doi': art.get('doi', ''),
            'abstract': art.get('abstract', ''),
            'database': 'IEEE Xplore',
            'evidence_level': '未评级',
            'source_url': art.get('html_url', ''),
        })
    return results


def _sample_results(theme=''):
    """无 API Key 时返回空列表，避免返回与主题无关的硬编码样本。"""
    print(f'[IEEE] No API key configured, returning empty results for theme: {theme}')
    return []
