# -*- coding: utf-8 -*-
"""
全文下载模块 — 多策略下载策略
策略优先级：
1. Entrez EFetch (medline/text/abstract) — 获取摘要和结构化信息
2. 直接 DOI PDF 链接 — 通过出版商直接下载
3. PMC HTML 全文 — 从 PMC 页面提取正文
4. OpenAlex 摘要 — 开放学术数据
5. 降级为"仅摘要级证据"

注：PMC PDF 常因 reCAPTCHA 限制无法直接下载，降级为 HTML 全文提取。
"""
import os, sys, re, json, time
try:
    import requests
    from Bio import Entrez
except ImportError:
    requests = None
    Entrez = None

FULLTEXT_DIR = None


def set_fulltext_dir(base_dir):
    global FULLTEXT_DIR
    FULLTEXT_DIR = os.path.join(base_dir, 'outputs', 'fulltext')
    os.makedirs(FULLTEXT_DIR, exist_ok=True)


def download_fulltext(paper, base_dir=None):
    """根据 DOI 下载全文，返回本地路径和状态。"""
    if FULLTEXT_DIR is None:
        set_fulltext_dir(base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    elif base_dir:
        set_fulltext_dir(base_dir)

    doi = paper.get('doi', '')
    pmid = paper.get('pmid', '')
    pid = paper.get('id', str(int(time.time())))
    fname = f'{pid}.txt'
    fpath = os.path.join(FULLTEXT_DIR, fname)

    if not doi and not pmid:
        return {'path': '', 'status': 'no_doi', 'note': '无 DOI 且无 PMID，无法自动下载'}

    # 策略1: 通过 Entrez efetch 获取摘要（始终可用）
    if pmid and pmid not in ('00000000', '00000001', ''):
        abstract_text = _fetch_pubmed_abstract(pmid)
        if abstract_text:
            _save_text(fpath, abstract_text, paper)
            return {'path': fpath, 'status': 'abstract_downloaded', 'note': '已通过 Entrez 获取摘要全文'}

    # 策略2: 通过 DOI 获取出版商页面摘要
    if doi and requests:
        pub_abstract = _fetch_via_doi(doi)
        if pub_abstract:
            _save_text(fpath, pub_abstract, paper)
            return {'path': fpath, 'status': 'abstract_downloaded', 'note': '已通过 DOI 获取摘要'}

    # 策略3: 尝试 PMC HTML 全文
    pmc_id = _get_pmc_id(pmid)
    if pmc_id:
        pmc_text = _fetch_pmc_html(pmc_id)
        if pmc_text:
            _save_text(fpath, pmc_text, paper)
            return {'path': fpath, 'status': 'pmc_downloaded', 'note': f'已从 PMC {pmc_id} 获取全文'}

    return {
        'path': fpath,
        'status': 'abstract_only',
        'note': '仅摘要级证据（全文需授权访问）',
    }


def _fetch_pubmed_abstract(pmid):
    """通过 Entrez efetch 获取摘要。"""
    if Entrez is None:
        return None
    try:
        handle = Entrez.efetch(db='pubmed', id=pmid, rettype='abstract', retmode='text')
        text = handle.read()
        handle.close()
        if text and len(text.strip()) > 50:
            return text.strip()
    except Exception:
        pass
    return None


def _fetch_via_doi(doi):
    """通过 DOI 获取出版商摘要。"""
    if not requests:
        return None
    try:
        doi_url = f'https://doi.org/{doi}'
        r = requests.get(doi_url, timeout=15, allow_redirects=True,
                         headers={'User-Agent': 'AcademicAgent/1.0; mailto:academic@example.com'})
        if r.status_code == 200:
            # 简单提取正文
            text = re.sub(r'<[^>]+>', ' ', r.text)
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) > 200:
                return text[:8000]
    except Exception:
        pass
    return None


def _get_pmc_id(pmid):
    """通过 PMID 获取 PMC ID。"""
    if not pmid or pmid in ('00000000', '00000001', ''):
        return None
    if Entrez is None:
        return None
    try:
        handle = Entrez.efetch(db='pubmed', id=pmid, rettype='medline', retmode='text')
        text = handle.read()
        handle.close()
        m = re.search(r'PMC(\d+)', text)
        return f'PMC{m.group(1)}' if m else None
    except Exception:
        return None


def _fetch_pmc_html(pmc_id):
    """从 PMC 获取 HTML 全文。"""
    if not requests:
        return None
    try:
        url = f'https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/'
        r = requests.get(url, timeout=15,
                         headers={'User-Agent': 'AcademicAgent/1.0; mailto:academic@example.com'})
        if r.status_code == 200 and len(r.text) > 1000:
            # 提取正文
            body = re.search(r'id="body"[^>]*>(.*?)</div>\s*<div[^>]+id="ref-list"', r.text, re.DOTALL)
            if body:
                text = re.sub(r'<[^>]+>', ' ', body.group(1))
            else:
                # 回退：提取所有段落
                paras = re.findall(r'<p[^>]*>(.*?)</p>', r.text, re.DOTALL)
                text = ' '.join(re.sub(r'<[^>]+>', ' ', p) for p in paras)
            text = re.sub(r'\s+', ' ', text).strip()
            return text if len(text) > 200 else None
    except Exception:
        pass
    return None


def _save_text(fpath, text, paper):
    title = paper.get('title', 'Unknown')
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(f'TITLE: {title}\n')
        f.write(f'DOI: {paper.get("doi", "N/A")}\n')
        f.write(f'PMID: {paper.get("pmid", "N/A")}\n')
        f.write(f'SOURCE: {paper.get("database", "Unknown")}\n')
        f.write('=' * 60 + '\n\n')
        f.write(text)
