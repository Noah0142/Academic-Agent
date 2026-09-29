# -*- coding: utf-8 -*-
"""
学术智能体 — Flask WebUI 入口 (端口 7000)
三区布局：左侧主题工作流 | 右侧上文献管理 | 右侧下综述列表
"""
from flask import Flask, render_template, request, jsonify, send_file
import json, os, sys, io, uuid, yaml, datetime


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
OUTPUTS_DIR = os.path.join(BASE_DIR, 'outputs')
TASK_CARDS_DIR = os.path.join(BASE_DIR, 'task_cards')
LITERATURE_DIR = os.path.join(BASE_DIR, 'literature')
REPORTS_DIR = os.path.join(BASE_DIR, 'reports')

for d in [OUTPUTS_DIR, TASK_CARDS_DIR, LITERATURE_DIR, REPORTS_DIR]:
    os.makedirs(d, exist_ok=True)

app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['JSON_AS_ASCII'] = False

# ---------- 状态存储 ----------
current_task = {}
current_literature = []
current_reports = []


def _save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_json(path, default=None):
    if not os.path.exists(path):
        return default or {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------- 路由 ----------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/search', methods=['POST'])
def api_search():
    """接收用户主题输入，生成任务卡占位"""
    data = request.get_json(force=True) or {}
    theme = data.get('theme', '').strip()
    if not theme:
        return jsonify({'error': '请输入研究主题'}), 400

    task_id = str(uuid.uuid4())[:8]
    task_card = {
        'task_id': task_id,
        'theme': theme,
        'created_at': datetime.datetime.now().isoformat(),
        'status': 'pending_confirm',
        'databases': ['PubMed', 'IEEE Xplore'],
        'time_range': '近5年',
        'doc_types': ['Journal Article', 'Review'],
        'direction': data.get('direction', ''),
        'problem': data.get('problem', ''),
        'innovation': data.get('innovation', ''),
        'outcome': data.get('outcome', ''),
        'data': data.get('data', ''),
    }
    # 保存任务卡
    tc_path = os.path.join(TASK_CARDS_DIR, f'{task_id}.yaml')
    with open(tc_path, 'w', encoding='utf-8') as f:
        yaml.dump(task_card, f, allow_unicode=True, sort_keys=False)

    current_task.update(task_card)
    return jsonify({'task_id': task_id, 'task_card': task_card, 'status': 'ok'})


@app.route('/api/confirm', methods=['POST'])
def api_confirm():
    """用户确认任务卡，触发检索占位"""
    data = request.get_json(force=True) or {}
    task_id = data.get('task_id', '')
    tc_path = os.path.join(TASK_CARDS_DIR, f'{task_id}.yaml')
    if not os.path.exists(tc_path):
        return jsonify({'error': '任务卡不存在'}), 404

    task_card = _load_json(tc_path.replace('.yaml', '.json'), {})
    if not task_card:
        with open(tc_path, 'r', encoding='utf-8') as f:
            task_card = yaml.safe_load(f)

    # 生成检索式占位
    theme = task_card.get('theme', '')
    query_result = generate_queries(theme)

    # 保存检索产物
    q_path = os.path.join(OUTPUTS_DIR, 'queries', f'{task_id}.json')
    os.makedirs(os.path.dirname(q_path), exist_ok=True)
    _save_json(q_path, query_result)

    task_card['status'] = 'query_generated'
    task_card['queries'] = query_result
    current_task.update(task_card)

    return jsonify({'status': 'ok', 'queries': query_result})


@app.route('/api/retrieve', methods=['POST'])
def api_retrieve():
    """执行检索"""
    data = request.get_json(force=True) or {}
    task_id = data.get('task_id', '')
    tc_path = os.path.join(TASK_CARDS_DIR, f'{task_id}.yaml')

    print(f'[RETRIEVE] task_id={task_id}, tc_exists={os.path.exists(tc_path)}')

    if not os.path.exists(tc_path):
        return jsonify({'error': '任务卡不存在'}), 404

    with open(tc_path, 'r', encoding='utf-8') as f:
        task_card = yaml.safe_load(f)

    theme = task_card.get('theme', '')
    print(f'[RETRIEVE] theme={theme}')
    results = {
        'pubmed': [],
        'ieee': [],
        'openalex': [],
    }

    try:
        from modules.pubmed_retriever import search_pubmed
        results['pubmed'] = search_pubmed(theme, task_card)
        print(f'[RETRIEVE] pubmed={len(results["pubmed"])}')
    except Exception as e:
        print(f'[RETRIEVE] pubmed_error: {e}')
        results['pubmed_error'] = str(e)

    try:
        from modules.ieee_retriever import search_ieee
        results['ieee'] = search_ieee(theme, task_card)
        print(f'[RETRIEVE] ieee={len(results["ieee"])}')
    except Exception as e:
        print(f'[RETRIEVE] ieee_error: {e}')
        results['ieee_error'] = str(e)

    try:
        from modules.openalex_retriever import search_openalex
        results['openalex'] = search_openalex(theme, task_card)
        print(f'[RETRIEVE] openalex={len(results["openalex"])}')
    except Exception as e:
        print(f'[RETRIEVE] openalex_error: {e}')
        results['openalex_error'] = str(e)

    all_papers = merge_results(results)
    print(f'[RETRIEVE] merged={len(all_papers)}')
    current_literature.extend(all_papers)

    lit_path = os.path.join(LITERATURE_DIR, f'{task_id}.json')
    _save_json(lit_path, all_papers)

    task_card['status'] = 'retrieved'
    task_card['total_results'] = len(all_papers)
    current_task.update(task_card)

    db_counts = {k: len(v) if isinstance(v, list) else 0 for k, v in results.items()}
    return jsonify({
        'status': 'ok',
        'total': len(all_papers),
        'papers': all_papers[:5],
        'all_papers': all_papers,
        'databases': db_counts
    })


@app.route('/api/literature', methods=['GET'])
def api_literature():
    task_id = request.args.get('task_id', '')
    if task_id:
        lit_path = os.path.join(LITERATURE_DIR, f'{task_id}.json')
        data = _load_json(lit_path, [])
    else:
        data = current_literature
    return jsonify({'papers': data})


@app.route('/api/verify', methods=['POST'])
def api_verify():
    data = request.get_json(force=True) or {}
    papers = data.get('papers', current_literature)
    report = verify_citations(papers)
    return jsonify({'status': 'ok', 'report': report})


@app.route('/api/report', methods=['POST'])
def api_report():
    data = request.get_json(force=True) or {}
    task_id = data.get('task_id', 'latest')
    papers = current_literature
    if not papers and task_id:
        lit_path = os.path.join(LITERATURE_DIR, f'{task_id}.json')
        papers = _load_json(lit_path, [])
    from modules.report_generator import generate_report_content
    content = generate_report_content(current_task, papers)
    return jsonify({'status': 'ok', 'content': content, 'task_id': task_id})


@app.route('/api/report/download', methods=['POST'])
def api_report_download():
    data = request.get_json(force=True) or {}
    task_id = data.get('task_id', 'latest')
    papers = current_literature
    if not papers and task_id:
        lit_path = os.path.join(LITERATURE_DIR, f'{task_id}.json')
        papers = _load_json(lit_path, [])
    from modules.report_generator import generate_report
    import tempfile
    tmp_path = os.path.join(tempfile.gettempdir(), f'report_{task_id}.docx')
    generate_report(task_id, current_task, papers, output_path=tmp_path)
    return send_file(tmp_path, as_attachment=True, download_name=f'report_{task_id}.docx')


@app.route('/api/reports', methods=['GET'])
def api_reports_list():
    """返回所有已保存的综述报告列表。"""
    files = []
    if os.path.exists(REPORTS_DIR):
        for f in sorted(os.listdir(REPORTS_DIR), reverse=True):
            if f.endswith('.docx') or f.endswith('.md'):
                fpath = os.path.join(REPORTS_DIR, f)
                files.append({
                    'name': f,
                    'path': fpath,
                    'size': os.path.getsize(fpath) if os.path.exists(fpath) else 0,
                    'modified': os.path.getmtime(fpath) if os.path.exists(fpath) else 0,
                })
    return jsonify({'reports': files})


@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify({'task': current_task, 'literature_count': len(current_literature)})


@app.route('/api/health', methods=['GET'])
def api_health():
    """健康检查 + 诊断信息"""
    import sys
    return jsonify({
        'status': 'ok',
        'version': '2026-09-28-v3',
        'python': sys.version,
        'task_count': len(current_literature),
        'report_count': len(current_reports),
        'current_task': current_task.get('task_id', ''),
        'current_theme': current_task.get('theme', ''),
    })


@app.route('/api/debug/retrieve', methods=['POST'])
def api_debug_retrieve():
    """调试检索：返回详细诊断信息"""
    data = request.get_json(force=True) or {}
    task_id = data.get('task_id', '')

    if not task_id:
        return jsonify({'error': '缺少 task_id'}), 400

    tc_path = os.path.join(TASK_CARDS_DIR, f'{task_id}.yaml')
    tc_exists = os.path.exists(tc_path)

    debug_info = {
        'task_id': task_id,
        'task_card_exists': tc_exists,
        'task_card_path': tc_path,
    }

    if tc_exists:
        with open(tc_path, 'r', encoding='utf-8') as f:
            task_card = yaml.safe_load(f)
        debug_info['theme'] = task_card.get('theme', '')
        debug_info['databases'] = task_card.get('databases', [])

        # 逐个测试检索器
        from modules.pubmed_retriever import search_pubmed
        try:
            pubmed_results = search_pubmed(task_card.get('theme', ''), task_card)
            debug_info['pubmed'] = {
                'count': len(pubmed_results),
                'sample': pubmed_results[:2] if pubmed_results else [],
                'error': None
            }
        except Exception as e:
            debug_info['pubmed'] = {'count': 0, 'error': str(e)}

        from modules.ieee_retriever import search_ieee
        try:
            ieee_results = search_ieee(task_card.get('theme', ''), task_card)
            debug_info['ieee'] = {
                'count': len(ieee_results),
                'sample': ieee_results[:2] if ieee_results else [],
                'error': None
            }
        except Exception as e:
            debug_info['ieee'] = {'count': 0, 'error': str(e)}

        from modules.openalex_retriever import search_openalex
        try:
            oalex_results = search_openalex(task_card.get('theme', ''), task_card)
            debug_info['openalex'] = {
                'count': len(oalex_results),
                'sample': oalex_results[:2] if oalex_results else [],
                'error': None
            }
        except Exception as e:
            debug_info['openalex'] = {'count': 0, 'error': str(e)}
    else:
        debug_info['error'] = f'Task card not found at {tc_path}'
        # 列出可用的 task cards
        if os.path.exists(TASK_CARDS_DIR):
            debug_info['available_task_ids'] = [f.replace('.yaml', '') for f in os.listdir(TASK_CARDS_DIR) if f.endswith('.yaml')]

    return jsonify(debug_info)


# ---------- 检索式生成占位 ----------

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


def generate_queries(theme):
    theme_lower = theme.lower()
    is_koa = '膝' in theme or 'knee' in theme_lower or 'koa' in theme_lower
    is_ai = '人工智能' in theme or 'ai' in theme_lower or 'deep learning' in theme_lower or 'machine learning' in theme_lower

    if is_koa and is_ai:
        return {
            'pubmed': {
                'query': '("Knee Osteoarthritis"[MeSH] OR "Knee Osteoarthritis"[Title/Abstract]) AND ("Artificial Intelligence"[Title/Abstract] OR "Deep Learning"[Title/Abstract] OR "Machine Learning"[Title/Abstract]) AND ("Medical Imaging"[Title/Abstract] OR "Radiograph*"[Title/Abstract] OR "Magnetic Resonance Imaging"[Title/Abstract])',
                'filters': '近5年 | Journal Article, Review | 英语+中文',
                'note': '复现手动检索的 PubMed 检索式（MeSH + 自由词组合）',
            },
            'ieee': {
                'query': '("Index Terms":Knee Osteoarthritis OR "Index Terms":Knee Osteoarthritis (KOA)) AND ("Index Terms":Deep Learning OR "Index Terms":Machine Learning OR "Index Terms":Convolutional Neural Networks OR "Index Terms":Artificial Intelligence OR "Index Terms":Transfer Learning) AND ("Index Terms":Image Classification OR "Index Terms":Medical Imaging OR "Index Terms":Feature Extraction)',
                'filters': '2025-2026年 | Conferences/Journals/Early Access | 按相关度',
                'note': '复现手动检索的 IEEE Xplore 检索式（Index Terms 精确匹配）',
            }
        }
    else:
        # 将中文主题翻译为英文后生成检索式
        theme_en = _cn_to_en_medical(theme)
        return {
            'pubmed': {'query': f'({theme_en})[Title/Abstract]', 'filters': '近5年', 'note': f'英文检索式（自动翻译）'},
            'ieee': {'query': f'"Index Terms":({theme_en})', 'filters': '近2年', 'note': f'英文检索式（自动翻译）'},
        }


# ---------- 结果合并 ----------

def merge_results(results):
    seen_dois = set()
    merged = []
    for source, papers in results.items():
        if isinstance(papers, list):
            for p in papers:
                doi = p.get('doi', '')
                if doi and doi in seen_dois:
                    continue
                if doi:
                    seen_dois.add(doi)
                p['source'] = source
                p['evidence_level'] = p.get('evidence_level', '未评级')
                merged.append(p)
    return merged


# ---------- 引用核验占位 ----------

def verify_citations(papers):
    report = {
        'total_checked': 0,
        'passed': 0,
        'failed': 0,
        'details': [],
    }
    sample = papers[:10] if len(papers) >= 10 else papers
    report['total_checked'] = len(sample)
    for p in sample:
        doi = p.get('doi', '')
        has_doi = bool(doi)
        has_title = bool(p.get('title', ''))
        has_year = bool(p.get('year', ''))
        ok = has_doi and has_title and has_year
        report['passed'] += (1 if ok else 0)
        report['failed'] += (0 if ok else 1)
        report['details'].append({
            'title': p.get('title', 'N/A')[:80],
            'doi': doi or 'N/A',
            'has_title': has_title,
            'has_doi': has_doi,
            'has_year': has_year,
            'result': 'PASS' if ok else 'FAIL',
        })
    return report


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 7000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    print(f'Academic Agent WebUI starting on port {port}...')
    app.run(host='0.0.0.0', port=port, debug=debug)

