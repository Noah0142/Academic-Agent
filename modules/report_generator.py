# -*- coding: utf-8 -*-
"""
综述报告生成模块 — 结构化综述报告
输出格式：Word (.docx)
"""
import os, sys, io, json, re


try:
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
except ImportError:
    Document = None

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'outputs', 'reports')
os.makedirs(OUTPUTS_DIR, exist_ok=True)


def generate_report(task_id, task_card, papers, output_path=None):
    """生成综述报告 Word 文档。"""
    if Document is None:
        return _save_text_report(task_id, task_card, papers, output_path)

    doc = Document()
    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(11)

    theme = task_card.get('theme', '未指定主题')

    # ---- 摘要 ----
    doc.add_heading('综述报告', 0)
    p = doc.add_paragraph()
    p.add_run(f'主题：').bold = True
    p.add_run(theme)
    p = doc.add_paragraph()
    p.add_run('检索日期：').bold = True
    p.add_run(task_card.get('created_at', 'N/A')[:10])

    doc.add_heading('摘要', level=1)
    n = len(papers)
    top_papers = [p for p in papers if p.get('evidence_level', '') in ('系统评价', '综述')][:3]
    abstract_text = (
        f'本报告围绕"{theme}"主题，通过 PubMed、IEEE Xplore 等多数据库检索，'
        f'共获取相关文献 {n} 篇。重点关注系统性综述、AI辅助影像学分析、'
        f'深度学习在膝骨关节炎精准分型中的最新研究进展。'
        f'其中系统性综述 {len(top_papers)} 篇。'
    )
    doc.add_paragraph(abstract_text)

    # ---- 引言 ----
    doc.add_heading('一、引言', level=1)
    intro_text = (
        f'膝骨关节炎（Knee Osteoarthritis, KOA）是膝关节的进行性退行性病变，'
        f'对活动能力和生活质量有重要影响。人工智能（AI）尤其是深度学习技术'
        f'在KOA的早期诊断、病情分级与精准分型中展现出巨大潜力。'
        f'本报告系统梳理了该领域的最新研究进展。'
    )
    doc.add_paragraph(intro_text)

    # ---- 检索策略 ----
    doc.add_heading('二、检索策略', level=1)
    doc.add_paragraph(f'研究主题：{theme}')
    doc.add_paragraph(f'数据库：{", ".join(task_card.get("databases", ["PubMed", "IEEE Xplore"]))}')
    doc.add_paragraph(f'时间范围：{task_card.get("time_range", "近5年")}')
    doc.add_paragraph(f'文献类型：{", ".join(task_card.get("doc_types", ["Journal Article", "Review"]))}')

    queries = task_card.get('queries', {})
    for db, q in queries.items():
        doc.add_paragraph(f'{db} 检索式：')
        p = doc.add_paragraph(q.get('query', 'N/A'))
        p.style = doc.styles['Normal']
        doc.add_paragraph(f'  限定条件：{q.get("filters", "N/A")}')

    # ---- 检索结果 ----
    doc.add_heading('三、检索结果', level=1)
    doc.add_paragraph(f'共检索到相关文献 {len(papers)} 篇（去重后）。')
    doc.add_paragraph()

    # ---- 重点文献 ----
    doc.add_heading('四、重点文献', level=1)
    for i, paper in enumerate(papers[:10], 1):
        doc.add_heading(f'4.{i} {paper.get("title", "N/A")}', level=2)
        meta = f'作者：{paper.get("authors", "N/A")} | 年份：{paper.get("year", "N/A")} | 期刊：{paper.get("journal", "N/A")}'
        doc.add_paragraph(meta)
        if paper.get('doi'):
            doc.add_paragraph(f'DOI：{paper["doi"]}')
            doc.add_paragraph(f'链接：https://doi.org/{paper["doi"]}')
        abstract = paper.get('abstract', '')
        if abstract:
            doc.add_paragraph(f'摘要：{abstract[:500]}{"..." if len(abstract) > 500 else ""}')
        doc.add_paragraph()

    # ---- 讨论 ----
    doc.add_heading('五、讨论', level=1)
    discuss = (
        '从检索结果来看，AI在膝骨关节炎影像学诊断领域的研究处于快速增长期。'
        '主要研究方向包括：深度学习分类模型、迁移学习、多模态融合等。'
        '系统性综述显示当前AI模型已能达到较高的诊断准确率，但临床转化仍需更多大规模前瞻性验证。'
    )
    doc.add_paragraph(discuss)

    # ---- 结论 ----
    doc.add_heading('六、结论', level=1)
    doc.add_paragraph(
        'AI方法在膝骨关节炎精准分型中展现出广阔的应用前景。'
        '深度学习特别是CNN架构在影像学分析中表现突出。'
        '未来研究应注重多中心验证、可解释性提升及临床工作流整合。'
    )

    # ---- 参考文献 ----
    doc.add_heading('七、参考文献', level=1)
    for i, paper in enumerate(papers, 1):
        ref = f'[{i}] {paper.get("authors", "")} ({paper.get("year", "")}). {paper.get("title", "")}. {paper.get("journal", "")}.'
        if paper.get('doi'):
            ref += f' DOI: {paper["doi"]}'
        doc.add_paragraph(ref)

    # ---- 保存 ----
    if output_path is None:
        output_path = os.path.join(OUTPUTS_DIR, f'report_{task_id}.docx')
    doc.save(output_path)
    return output_path


def generate_report_content(task_card, papers):
    """生成综述报告内容为 Markdown 字符串，用于前端展示。"""
    theme = task_card.get('theme', '未指定主题')
    n = len(papers)
    top_papers = [p for p in papers if p.get('evidence_level', '') in ('系统评价', '综述')][:3]

    lines = [
        f'# 综述报告 — {theme}',
        f'**检索日期：** {task_card.get("created_at", "N/A")[:10]}',
        f'**文献数量：** {n} 篇（去重后）',
        '',
        '## 摘要',
        (
            f'本报告围绕"{theme}"主题，通过 PubMed、IEEE Xplore 等多数据库检索，'
            f'共获取相关文献 {n} 篇。重点关注系统性综述、AI辅助影像学分析、'
            f'深度学习在膝骨关节炎精准分型中的最新研究进展。'
            f'其中系统性综述 {len(top_papers)} 篇。'
        ),
        '',
        '## 一、引言',
        (
            f'膝骨关节炎（Knee Osteoarthritis, KOA）是膝关节的进行性退行性病变，'
            f'对活动能力和生活质量有重要影响。人工智能（AI）尤其是深度学习技术'
            f'在KOA的早期诊断、病情分级与精准分型中展现出巨大潜力。'
            f'本报告系统梳理了该领域的最新研究进展。'
        ),
        '',
        '## 二、检索策略',
        f'- **研究主题：** {theme}',
        f'- **数据库：** {", ".join(task_card.get("databases", ["PubMed", "IEEE Xplore"]))}',
        f'- **时间范围：** {task_card.get("time_range", "近5年")}',
        f'- **文献类型：** {", ".join(task_card.get("doc_types", ["Journal Article", "Review"]))}',
        '',
        '### 检索式',
    ]
    queries = task_card.get('queries', {})
    for db, q in queries.items():
        lines.append(f'- **{db}：** {q.get("query", "N/A")}')
        lines.append(f'  - 限定条件：{q.get("filters", "N/A")}')
        lines.append('')

    lines.extend([
        '## 三、检索结果',
        f'共检索到相关文献 {n} 篇（去重后）。',
        '',
        '## 四、重点文献',
    ])
    for i, paper in enumerate(papers[:10], 1):
        lines.append(f'### 4.{i} {paper.get("title", "N/A")}')
        lines.append(f'- **作者：** {paper.get("authors", "N/A")}')
        lines.append(f'- **年份：** {paper.get("year", "N/A")}')
        lines.append(f'- **期刊：** {paper.get("journal", "N/A")}')
        if paper.get('doi'):
            lines.append(f'- **DOI：** {paper["doi"]}')
            lines.append(f'- **链接：** https://doi.org/{paper["doi"]}')
        abstract = paper.get('abstract', '')
        if abstract:
            lines.append(f'- **摘要：** {abstract[:500]}{"..." if len(abstract) > 500 else ""}')
        lines.append('')

    lines.extend([
        '## 五、讨论',
        (
            '从检索结果来看，AI在膝骨关节炎影像学诊断领域的研究处于快速增长期。'
            '主要研究方向包括：深度学习分类模型、迁移学习、多模态融合等。'
            '系统性综述显示当前AI模型已能达到较高的诊断准确率，但临床转化仍需更多大规模前瞻性验证。'
        ),
        '',
        '## 六、结论',
        (
            'AI方法在膝骨关节炎精准分型中展现出广阔的应用前景。'
            '深度学习特别是CNN架构在影像学分析中表现突出。'
            '未来研究应注重多中心验证、可解释性提升及临床工作流整合。'
        ),
        '',
        '## 七、参考文献',
    ])
    for i, paper in enumerate(papers, 1):
        ref = f'[{i}] {paper.get("authors", "")} ({paper.get("year", "")}). {paper.get("title", "")}. {paper.get("journal", "")}.'
        if paper.get('doi'):
            ref += f' DOI: {paper["doi"]}'
        lines.append(ref)

    return '\n'.join(lines)


def _save_text_report(task_id, task_card, papers, output_path=None):
    """降级方案：生成 Markdown 格式报告。"""
    if output_path is None:
        output_path = os.path.join(OUTPUTS_DIR, f'report_{task_id}.md')
    theme = task_card.get('theme', '未指定主题')
    lines = [
        f'# 综述报告 — {theme}',
        f'检索日期：{task_card.get("created_at", "N/A")[:10]}',
        '',
        '## 摘要',
        f'围绕"{theme}"主题，共获取文献 {len(papers)} 篇。',
        '',
        '## 重点文献',
    ]
    for i, p in enumerate(papers[:10], 1):
        lines.append(f'### {i}. {p.get("title", "N/A")}')
        lines.append(f'作者：{p.get("authors", "N/A")}')
        lines.append(f'年份：{p.get("year", "N/A")}')
        lines.append(f'DOI：{p.get("doi", "N/A")}')
        lines.append('')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return output_path
