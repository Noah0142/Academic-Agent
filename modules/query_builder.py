# -*- coding: utf-8 -*-
"""
检索式生成模块 — 医工交叉维度 -> PubMed MeSH + IEEE Index Terms
"""
def build_pubmed_query(theme, direction=''):
    """构建 PubMed 检索式。"""
    theme_lower = theme.lower()
    is_koa = any(kw in theme_lower for kw in ['膝', 'knee', 'koa', 'osteoarthritis'])
    is_ai = any(kw in theme_lower for kw in ['人工智能', 'ai', 'deep learning', 'machine learning'])

    if is_koa and is_ai:
        return (
            '("Knee Osteoarthritis"[MeSH] OR "Knee Osteoarthritis"[Title/Abstract])'
            ' AND ("Artificial Intelligence"[Title/Abstract] OR "Deep Learning"[Title/Abstract]'
            ' OR "Machine Learning"[Title/Abstract] OR "Convolutional Neural Network*"[Title/Abstract])'
            ' AND ("Medical Imaging"[Title/Abstract] OR "Radiograph*"[Title/Abstract]'
            ' OR "X-ray"[Title/Abstract] OR "Magnetic Resonance Imaging"[Title/Abstract])'
        )
    # 通用回退：自由词检索
    return f'"{theme}"[Title/Abstract]'


def build_ieee_query(theme, direction=''):
    """构建 IEEE Xplore 检索式（Index Terms）。"""
    theme_lower = theme.lower()
    is_koa = any(kw in theme_lower for kw in ['膝', 'knee', 'koa', 'osteoarthritis'])
    is_ai = any(kw in theme_lower for kw in ['人工智能', 'ai', 'deep learning', 'machine learning'])

    if is_koa and is_ai:
        return (
            '("Index Terms":Knee Osteoarthritis OR "Index Terms":Knee Osteoarthritis (KOA))'
            ' AND ("Index Terms":Deep Learning OR "Index Terms":Machine Learning'
            ' OR "Index Terms":Convolutional Neural Networks OR "Index Terms":Artificial Intelligence'
            ' OR "Index Terms":Transfer Learning)'
            ' AND ("Index Terms":Image Classification OR "Index Terms":Medical Imaging'
            ' OR "Index Terms":Feature Extraction)'
        )
    return f'"Index Terms":{theme}'


def build_openalex_query(theme):
    return theme

