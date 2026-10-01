# -*- coding: utf-8 -*-
"""
PubMed 检索模块 — 基于 Entrez E-utilities (Biopython)
"""
import os, json, time, sys, io


try:
    from Bio import Entrez
except ImportError:
    Entrez = None


def _cn_to_en_medical(theme):
    """简单的中文医学术语到英文的映射，用于生成英文检索式。"""
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
    # 清理多余空格
    result = ' '.join(result.split())
    return result.strip()


def search_pubmed(theme, task_card=None):
    """在 PubMed 中检索文献，返回结构化结果列表。"""
    if Entrez is None:
        return _sample_results()

    Entrez.email = os.environ.get('PUBMED_EMAIL', 'Noah13610480142@outlook.com')
    time_range = (task_card or {}).get('time_range', '5')
    year_from = _parse_year_range(time_range)

    # 优先使用 LLM 生成的检索式
    query = None
    if task_card:
        queries = task_card.get('queries', {})
        pubmed_query = queries.get('pubmed', {})
        if isinstance(pubmed_query, dict):
            query = pubmed_query.get('query')

    # 回退到本地规则生成的检索式
    if not query:
        theme_en = _cn_to_en_medical(theme)
        query = _build_pubmed_query(theme_en)

    print(f'[PubMed] Using query: {query[:200]}')

    try:
        from datetime import datetime
        now = datetime.now()
        mindate = f'{now.year - year_from}/01/01'
        maxdate = f'{now.year}/{now.month}/{now.day}'
        handle = Entrez.esearch(
            db='pubmed', term=query, retmax=50, sort='relevance',
            datetype='pdat', mindate=mindate, maxdate=maxdate
        )
        record = Entrez.read(handle)
        handle.close()
        id_list = record.get('IdList', [])
    except Exception as e:
        print(f'[PubMed] Search error: {e}')
        return _sample_results()

    if not id_list:
        return []

    results = []
    try:
        handle = Entrez.efetch(db='pubmed', id=id_list[:20], rettype='abstract', retmode='text')
        abstracts = handle.read()
        handle.close()
    except Exception as e:
        print(f'[PubMed] Fetch error: {e}')
        abstracts = ''

    for pmid in id_list[:20]:
        try:
            h = Entrez.efetch(db='pubmed', id=pmid, rettype='medline', retmode='text')
            text = h.read()
            h.close()
        except Exception:
            text = ''

        title = _extract_field(text, 'TI')
        authors = _extract_field(text, 'AU')
        journal = _extract_field(text, 'JT')
        year = _extract_field(text, 'DP')[:4] if _extract_field(text, 'DP') else ''
        doi_raw = _extract_field(text, 'LID', pattern='[doi]')
        if not doi_raw:
            doi_raw = _extract_field(text, 'AID', pattern='[doi]')
        # 提取纯 DOI：[doi] 标记跟在 DOI 值后面
        doi = ''
        if doi_raw:
            for i, part in enumerate(doi_raw.split()):
                if '[doi]' in part and i > 0:
                    doi = doi_raw.split()[i - 1]
                    break
        abstract_text = _extract_field(text, 'AB')

        results.append({
            'id': f'PM{pmid}',
            'pmid': str(pmid),
            'title': title or 'Unknown Title',
            'authors': authors,
            'year': year,
            'journal': journal,
            'doi': doi,
            'abstract': abstract_text or '',
            'database': 'PubMed',
            'evidence_level': '未评级',
            'source_url': f'https://pubmed.ncbi.nlm.nih.gov/{pmid}/',
        })

    return results


def _build_pubmed_query(theme):
    """构建 PubMed 检索式。"""
    if '膝' in theme or 'knee' in theme.lower() or 'koa' in theme.lower():
        return (
            '("Knee Osteoarthritis"[MeSH] OR "Knee Osteoarthritis"[Title/Abstract])'
            ' AND ("Artificial Intelligence"[Title/Abstract] OR "Deep Learning"[Title/Abstract]'
            ' OR "Machine Learning"[Title/Abstract] OR "Convolutional Neural Network*"[Title/Abstract])'
            ' AND ("Medical Imaging"[Title/Abstract] OR "Radiograph*"[Title/Abstract]'
            ' OR "X-ray"[Title/Abstract] OR "Magnetic Resonance Imaging"[Title/Abstract])'
        )
    # 非膝骨关节炎主题：使用更灵活的检索式
    # 将主题拆分为单词，构建宽松的检索式
    words = theme.split()
    if len(words) <= 3:
        # 短查询直接搜索
        return f'"{theme}"[Title/Abstract]'
    else:
        # 长查询拆分为关键词，用 AND 连接
        # 只保留有实际意义的关键词（长度>3的单词）
        keywords = [w for w in words if len(w) > 3]
        if keywords:
            return ' AND '.join([f'"{w}"[Title/Abstract]' for w in keywords])
        return f'"{theme}"[Title/Abstract]'


def _parse_year_range(time_range):
    try:
        return int(''.join(filter(str.isdigit, str(time_range)))) or 5
    except Exception:
        return 5


def _extract_field(text, tag, pattern=None):
    """从 MEDLINE 文本中提取字段。"""
    lines = text.split('\n')
    capture = False
    values = []
    # MEDLINE 字段可能有 'TAG -' (一个空格) 或 'TAG  -' (两个空格) 两种格式
    for line in lines:
        stripped = line
        if stripped.startswith(tag + ' -') or stripped.startswith(tag + '  -'):
            capture = True
            # 统一取分隔符后的内容
            val = stripped.split('-', 1)[1].strip()
            values.append(val)
        elif capture and stripped.startswith('      '):
            values.append(stripped.strip())
        else:
            capture = False

    result = ' '.join(values)
    if pattern and pattern in result:
        return result
    return result


def _sample_results():
    """降级样例数据（接口不可用时使用）。"""
    return [
        {
            'id': 'PM_SAMPLE_001',
            'pmid': '00000000',
            'title': 'Computational Intelligence in Knee Osteoarthritis Detection: A Systematic Review of AI and Machine Learning Approaches',
            'authors': 'Sharma A, Garg VK',
            'year': '2026',
            'journal': 'CIPHER 2026',
            'doi': '10.1109/CIPHER70417.2026.11524036',
            'abstract': 'Computational Intelligence (CI) and AI for early diagnosis of Knee Osteoarthritis (KOA). Systematic review comparing methodologies and performance.',
            'database': 'PubMed',
            'evidence_level': '系统评价',
            'source_url': 'https://doi.org/10.1109/CIPHER70417.2026.11524036',
        },
        {
            'id': 'PM_SAMPLE_002',
            'pmid': '00000001',
            'title': '[Advances in deep learning multimodal fusion for early diagnosis of knee osteoarthritis]',
            'authors': 'Tian J, Ma J, Zhao J, Ma X',
            'year': '2026',
            'journal': 'Sheng Wu Yi Xue Gong Cheng Xue Za Zhi',
            'doi': '10.7507/1001-5515.202601026',
            'abstract': 'Deep learning multimodal fusion for early diagnosis of KOA, covering X-ray, MRI, clinical variables, gait/biomechanics, and molecular biomarkers.',
            'database': 'PubMed',
            'evidence_level': '综述',
            'source_url': 'https://doi.org/10.7507/1001-5515.202601026',
        },
    ]
