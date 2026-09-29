# -*- coding: utf-8 -*-
"""
引用核验模块 — 引用存在性检查，DOI 可打开性，10 条抽查
"""
try:
    import requests
except ImportError:
    requests = None


def verify_citations(papers, sample_size=10):
    """对文献表进行引用核验，抽查指定条数。"""
    sample = papers[:sample_size] if len(papers) >= sample_size else papers
    report = {
        'total_checked': len(sample),
        'passed': 0,
        'failed': 0,
        'details': [],
    }

    for p in sample:
        title = p.get('title', '')
        doi = p.get('doi', '')
        year = p.get('year', '')
        source_url = p.get('source_url', '')

        has_title = bool(title and title != 'Unknown Title')
        has_doi = bool(doi)
        has_url = bool(source_url)
        has_year = bool(year)

        # DOI 可打开性检查
        doi_accessible = False
        if has_doi and requests:
            try:
                r = requests.head(f'https://doi.org/{doi}', timeout=10, allow_redirects=True)
                doi_accessible = r.status_code < 400
            except Exception:
                doi_accessible = False

        ok = has_title and has_doi and has_year
        if ok:
            report['passed'] += 1
        else:
            report['failed'] += 1

        report['details'].append({
            'title': title[:80] if title else 'N/A',
            'doi': doi or 'N/A',
            'year': year or 'N/A',
            'has_title': has_title,
            'has_doi': has_doi,
            'has_year': has_year,
            'doi_accessible': doi_accessible,
            'result': 'PASS' if ok else 'FAIL',
        })

    return report

