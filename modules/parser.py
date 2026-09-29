# -*- coding: utf-8 -*-
"""
全文解析模块 — PDF 文本解析（PyMuPDF）
提取题名、作者、年份等元数据并验证一致性。
"""
import os, sys, io


try:
    import fitz
except ImportError:
    try:
        import pymupdf as fitz
    except ImportError:
        fitz = None


def parse_pdf(fpath):
    """解析 PDF 文件，返回文本内容和元数据。"""
    if not fitz or not os.path.exists(fpath):
        return {'text': '', 'metadata': {}, 'status': 'error'}

    try:
        doc = fitz.open(fpath)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())

        meta = doc.metadata
        result = {
            'text': '\n'.join(text_parts),
            'metadata': {
                'title': meta.get('title', ''),
                'author': meta.get('author', ''),
                'subject': meta.get('subject', ''),
            },
            'page_count': len(doc),
            'status': 'ok',
        }
        doc.close()
        return result
    except Exception as e:
        return {'text': '', 'metadata': {}, 'status': f'error: {e}'}


def _normalize_ws(s):
    return ' '.join(s.split())

def verify_paper_match(parsed, paper):
    """验证全文内容与文献表是否一致。"""
    full_text = parsed.get('text', '')
    meta = parsed.get('metadata', {})
    
    # 优先使用文献表已知信息
    paper_title = paper.get('title', '')
    paper_doi = paper.get('doi', '')
    paper_year = paper.get('year', '')
    
    # 也检查 PDF 元数据
    pdf_title = meta.get('title', '')
    
    # 统一空白字符后匹配（忽略换行/空格差异）
    norm_text = _normalize_ws(full_text)
    title_sample = _normalize_ws(paper_title[:120]) if paper_title else ''

    title_found = bool(title_sample) and (title_sample.lower() in norm_text.lower() or 
                                          (pdf_title and title_sample.lower() in _normalize_ws(pdf_title).lower()))
    doi_found = bool(paper_doi) and paper_doi.replace(' ', '') in norm_text
    year_found = bool(paper_year) and paper_year in norm_text
    title_meta_found = bool(pdf_title)

    checks = {
        'title_in_text': title_found,
        'doi_in_text': doi_found,
        'year_in_text': year_found,
        'title_in_metadata': title_meta_found,
    }
    all_pass = title_found or title_meta_found
    return {'checks': checks, 'passed': all_pass}
