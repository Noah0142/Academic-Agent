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
        # 疾病
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
        '渐冻症': 'Amyotrophic Lateral Sclerosis',
        'ALS': 'ALS',
        '高血压': 'Hypertension',
        '冠心病': 'Coronary Heart Disease',
        '肝炎': 'Hepatitis',
        '肝硬化': 'Liver Cirrhosis',
        '肾病': 'Kidney Disease',
        '尿毒症': 'Uremia',
        '哮喘': 'Asthma',
        '肺炎': 'Pneumonia',
        '肺结核': 'Tuberculosis',
        '艾滋病': 'AIDS',
        'HIV': 'HIV',
        '疟疾': 'Malaria',
        '白血病': 'Leukemia',
        '淋巴瘤': 'Lymphoma',
        '黑色素瘤': 'Melanoma',
        '结肠癌': 'Colon Cancer',
        '胃癌': 'Gastric Cancer',
        '肝癌': 'Liver Cancer',
        '胰腺癌': 'Pancreatic Cancer',
        '前列腺癌': 'Prostate Cancer',
        '宫颈癌': 'Cervical Cancer',
        '卵巢癌': 'Ovarian Cancer',
        '甲状腺癌': 'Thyroid Cancer',
        '脑瘤': 'Brain Tumor',
        '脊髓损伤': 'Spinal Cord Injury',
        '多发性硬化': 'Multiple Sclerosis',
        '类风湿关节炎': 'Rheumatoid Arthritis',
        '红斑狼疮': 'Lupus',
        '银屑病': 'Psoriasis',
        '湿疹': 'Eczema',
        '抑郁症': 'Depression',
        '焦虑症': 'Anxiety',
        '精神分裂症': 'Schizophrenia',
        '双相情感障碍': 'Bipolar Disorder',
        '癫痫': 'Epilepsy',
        '偏头痛': 'Migraine',
        '自闭症': 'Autism',
        '骨质疏松症': 'Osteoporosis',
        '痛风': 'Gout',
        '胰腺炎': 'Pancreatitis',
        '胆结石': 'Gallstone',
        '阑尾炎': 'Appendicitis',
        '疝气': 'Hernia',
        '痔疮': 'Hemorrhoids',
        '近视': 'Myopia',
        '远视': 'Hyperopia',
        '白内障': 'Cataract',
        '青光眼': 'Glaucoma',
        '中耳炎': 'Otitis Media',
        '鼻窦炎': 'Sinusitis',
        '咽喉炎': 'Pharyngitis',
        '支气管炎': 'Bronchitis',
        '肺气肿': 'Emphysema',
        '肺纤维化': 'Pulmonary Fibrosis',
        '肺动脉高压': 'Pulmonary Hypertension',
        '心肌梗死': 'Myocardial Infarction',
        '心力衰竭': 'Heart Failure',
        '心律失常': 'Arrhythmia',
        '心房颤动': 'Atrial Fibrillation',
        '深静脉血栓': 'Deep Vein Thrombosis',
        '动脉粥样硬化': 'Atherosclerosis',
        '糖尿病足': 'Diabetic Foot',
        '肾病综合征': 'Nephrotic Syndrome',
        '尿路感染': 'Urinary Tract Infection',
        '前列腺增生': 'Benign Prostatic Hyperplasia',
        '子宫内膜异位症': 'Endometriosis',
        '多囊卵巢综合征': 'PCOS',
        '妊娠糖尿病': 'Gestational Diabetes',
        '产后抑郁': 'Postpartum Depression',
        '婴幼儿湿疹': 'Infant Eczema',
        '手足口病': 'Hand Foot Mouth Disease',
        '水痘': 'Chickenpox',
        '麻疹': 'Measles',
        '腮腺炎': 'Mumps',
        '百日咳': 'Pertussis',
        '破伤风': 'Tetanus',
        '狂犬病': 'Rabies',
        '登革热': 'Dengue Fever',
        '寨卡病毒': 'Zika Virus',
        '埃博拉': 'Ebola',
        '非典': 'SARS',
        '新冠': 'COVID-19',
        '冠状病毒': 'Coronavirus',
        '流感': 'Influenza',
        '普通感冒': 'Common Cold',
        # 症状
        '发热': 'Fever',
        '咳嗽': 'Cough',
        '头痛': 'Headache',
        '胸痛': 'Chest Pain',
        '腹痛': 'Abdominal Pain',
        '恶心': 'Nausea',
        '呕吐': 'Vomiting',
        '腹泻': 'Diarrhea',
        '便秘': 'Constipation',
        '疲劳': 'Fatigue',
        '乏力': 'Fatigue',
        '失眠': 'Insomnia',
        '食欲不振': 'Loss of Appetite',
        '体重下降': 'Weight Loss',
        '水肿': 'Edema',
        '皮疹': 'Rash',
        '瘙痒': 'Pruritus',
        '关节痛': 'Arthralgia',
        '肌肉痛': 'Myalgia',
        '呼吸困难': 'Dyspnea',
        '胸闷': 'Chest Tightness',
        '心悸': 'Palpitation',
        '眩晕': 'Dizziness',
        '耳鸣': 'Tinnitus',
        '视力模糊': 'Blurred Vision',
        '听力下降': 'Hearing Loss',
        '鼻塞': 'Nasal Congestion',
        '流鼻涕': 'Runny Nose',
        '咽痛': 'Sore Throat',
        '声音嘶哑': 'Hoarseness',
        '咯血': 'Hemoptysis',
        '便血': 'Hematochezia',
        '血尿': 'Hematuria',
        '黄疸': 'Jaundice',
        '抽搐': 'Convulsion',
        '昏迷': 'Coma',
        '麻木': 'Numbness',
        '刺痛': 'Tingling',
        '无力': 'Weakness',
        '步态不稳': 'Gait Instability',
        '言语不清': 'Dysarthria',
        '吞咽困难': 'Dysphagia',
        # 医学概念
        '精准分型': 'Precision Classification',
        '精准诊断': 'Precision Diagnosis',
        '精准治疗': 'Precision Treatment',
        '精准预后': 'Precision Prognosis',
        '影像学': 'Medical Imaging',
        '医学影像': 'Medical Imaging',
        '医学图像': 'Medical Image',
        '深度学习': 'Deep Learning',
        '机器学习': 'Machine Learning',
        '人工智能': 'Artificial Intelligence',
        '卷积神经网络': 'Convolutional Neural Network',
        'CNN': 'CNN',
        '迁移学习': 'Transfer Learning',
        '分类': 'Classification',
        '分割': 'Segmentation',
        '检测': 'Detection',
        '识别': 'Recognition',
        '诊断': 'Diagnosis',
        '治疗': 'Treatment',
        '预后': 'Prognosis',
        '分析': 'Analysis',
        '研究': 'Study',
        '基于': 'Based on',
        '在': 'in',
        '中': 'in',
        '的': ' ',
        '分子基础': 'Molecular Basis',
        '分子机制': 'Molecular Mechanism',
        '发病机制': 'Pathogenesis',
        '病理': 'Pathology',
        '病理学': 'Pathology',
        '生理': 'Physiology',
        '解剖': 'Anatomy',
        '组织学': 'Histology',
        '细胞学': 'Cytology',
        '遗传学': 'Genetics',
        '基因组学': 'Genomics',
        '蛋白质组学': 'Proteomics',
        '代谢组学': 'Metabolomics',
        '转录组学': 'Transcriptomics',
        '生物信息学': 'Bioinformatics',
        '统计学': 'Statistics',
        '流行病学': 'Epidemiology',
        '临床试验': 'Clinical Trial',
        '随机对照试验': 'Randomized Controlled Trial',
        '荟萃分析': 'Meta Analysis',
        '系统综述': 'Systematic Review',
        '回顾性研究': 'Retrospective Study',
        '前瞻性研究': 'Prospective Study',
        '病例对照研究': 'Case Control Study',
        '队列研究': 'Cohort Study',
        '横断面研究': 'Cross-sectional Study',
        '敏感性': 'Sensitivity',
        '特异性': 'Specificity',
        '准确率': 'Accuracy',
        '精确度': 'Precision',
        '召回率': 'Recall',
        'F1分数': 'F1 Score',
        'AUC': 'AUC',
        'ROC曲线': 'ROC Curve',
        '一致性': 'Consistency',
        '可靠性': 'Reliability',
        '有效性': 'Validity',
        '预后因素': 'Prognostic Factor',
        '危险因素': 'Risk Factor',
        '保护因素': 'Protective Factor',
        '生物标志物': 'Biomarker',
        '药物靶点': 'Drug Target',
        '基因突变': 'Gene Mutation',
        '基因表达': 'Gene Expression',
        '蛋白质表达': 'Protein Expression',
        '信号通路': 'Signaling Pathway',
        '免疫组化': 'Immunohistochemistry',
        ' Western Blot': 'Western Blot',
        'PCR': 'PCR',
        '测序': 'Sequencing',
        '下一代测序': 'Next Generation Sequencing',
        '全基因组测序': 'Whole Genome Sequencing',
        '外显子测序': 'Exome Sequencing',
        '转录组测序': 'RNA Sequencing',
        '单细胞测序': 'Single-cell Sequencing',
        '类器官': 'Organoid',
        '干细胞': 'Stem Cell',
        '免疫细胞': 'Immune Cell',
        'T细胞': 'T Cell',
        'B细胞': 'B Cell',
        '自然杀伤细胞': 'NK Cell',
        '巨噬细胞': 'Macrophage',
        '树突状细胞': 'Dendritic Cell',
        '细胞因子': 'Cytokine',
        '趋化因子': 'Chemokine',
        '生长因子': 'Growth Factor',
        '受体': 'Receptor',
        '配体': 'Ligand',
        '酶': 'Enzyme',
        '底物': 'Substrate',
        '产物': 'Product',
        '代谢物': 'Metabolite',
        '底物': 'Substrate',
        '辅酶': 'Coenzyme',
        '辅因子': 'Cofactor',
        '抑制剂': 'Inhibitor',
        '激动剂': 'Agonist',
        '拮抗剂': 'Antagonist',
        '抗体': 'Antibody',
        '抗原': 'Antigen',
        '疫苗': 'Vaccine',
        '药物': 'Drug',
        '药物代谢': 'Drug Metabolism',
        '药代动力学': 'Pharmacokinetics',
        '药效学': 'Pharmacodynamics',
        '副作用': 'Side Effect',
        '不良反应': 'Adverse Reaction',
        '耐药性': 'Drug Resistance',
        '敏感性': 'Sensitivity',
        '耐受性': 'Tolerance',
        '剂量': 'Dose',
        '给药途径': 'Route of Administration',
        '口服': 'Oral',
        '静脉注射': 'Intravenous',
        '肌肉注射': 'Intramuscular',
        '皮下注射': 'Subcutaneous',
        '吸入': 'Inhalation',
        '局部用药': 'Topical',
        '手术': 'Surgery',
        '化疗': 'Chemotherapy',
        '放疗': 'Radiotherapy',
        '免疫治疗': 'Immunotherapy',
        '靶向治疗': 'Targeted Therapy',
        '内分泌治疗': 'Endocrine Therapy',
        '激素治疗': 'Hormone Therapy',
        '镇痛': 'Analgesia',
        '麻醉': 'Anesthesia',
        '复苏': 'Resuscitation',
        '重症监护': 'Intensive Care',
        '康复': 'Rehabilitation',
        '物理治疗': 'Physical Therapy',
        '心理治疗': 'Psychotherapy',
        '营养支持': 'Nutritional Support',
        '输血': 'Blood Transfusion',
        '器官移植': 'Organ Transplantation',
        '骨髓移植': 'Bone Marrow Transplantation',
        '人工关节': 'Artificial Joint',
        '心脏支架': 'Cardiac Stent',
        '起搏器': 'Pacemaker',
        '假体': 'Prosthesis',
        '植入物': 'Implant',
        '影像检查': 'Imaging Examination',
        'CT': 'CT',
        'MRI': 'MRI',
        '超声': 'Ultrasound',
        'X光': 'X-ray',
        'PET': 'PET',
        'SPECT': 'SPECT',
        '内镜': 'Endoscopy',
        '胃镜': 'Gastroscopy',
        '肠镜': 'Colonoscopy',
        '支气管镜': 'Bronchoscopy',
        '膀胱镜': 'Cystoscopy',
        '腹腔镜': 'Laparoscopy',
        '关节镜': 'Arthroscopy',
        '病理检查': 'Pathological Examination',
        '活检': 'Biopsy',
        '穿刺': 'Puncture',
        '穿刺活检': 'Needle Biopsy',
        '手术活检': 'Surgical Biopsy',
        '细胞学检查': 'Cytological Examination',
        '血液检查': 'Blood Test',
        '尿液检查': 'Urine Test',
        '粪便检查': 'Stool Test',
        '生化检查': 'Biochemical Test',
        '免疫学检查': 'Immunological Test',
        '微生物学检查': 'Microbiological Test',
        '基因检测': 'Genetic Testing',
        '产前筛查': 'Prenatal Screening',
        '新生儿筛查': 'Newborn Screening',
        '肿瘤标志物': 'Tumor Marker',
        '心电图': 'ECG',
        '脑电图': 'EEG',
        '肌电图': 'EMG',
        '诱发电位': 'Evoked Potential',
        '肺功能检查': 'Pulmonary Function Test',
        '听力测试': 'Hearing Test',
        '视力测试': 'Vision Test',
        '平衡功能测试': 'Balance Test',
        '认知功能测试': 'Cognitive Test',
        '智力测试': 'Intelligence Test',
        '心理测试': 'Psychological Test',
        '人格测试': 'Personality Test',
        '生活质量评估': 'Quality of Life Assessment',
        '功能评估': 'Functional Assessment',
        '运动功能': 'Motor Function',
        '感觉功能': 'Sensory Function',
        '认知功能': 'Cognitive Function',
        '语言功能': 'Language Function',
        '吞咽功能': 'Swallowing Function',
        '呼吸功能': 'Respiratory Function',
        '心脏功能': 'Cardiac Function',
        '肝功能': 'Liver Function',
        '肾功能': 'Renal Function',
        '内分泌功能': 'Endocrine Function',
        '免疫功能': 'Immune Function',
        '血液系统': 'Hematological System',
        '消化系统': 'Digestive System',
        '呼吸系统': 'Respiratory System',
        '循环系统': 'Circulatory System',
        '泌尿系统': 'Urinary System',
        '生殖系统': 'Reproductive System',
        '神经系统': 'Nervous System',
        '内分泌系统': 'Endocrine System',
        '运动系统': 'Musculoskeletal System',
        '感觉器官': 'Sensory Organs',
        '皮肤': 'Skin',
        '肌肉': 'Muscle',
        '骨骼': 'Bone',
        '关节': 'Joint',
        '韧带': 'Ligament',
        '肌腱': 'Tendon',
        '软骨': 'Cartilage',
        '筋膜': 'Fascia',
        '血液': 'Blood',
        '血浆': 'Plasma',
        '血清': 'Serum',
        '红细胞': 'Red Blood Cell',
        '白细胞': 'White Blood Cell',
        '血小板': 'Platelet',
        '血红蛋白': 'Hemoglobin',
        '血糖': 'Blood Glucose',
        '血脂': 'Blood Lipid',
        '胆固醇': 'Cholesterol',
        '甘油三酯': 'Triglyceride',
        '尿酸': 'Uric Acid',
        '肌酐': 'Creatinine',
        '尿素氮': 'Blood Urea Nitrogen',
        '转氨酶': 'Transaminase',
        '胆红素': 'Bilirubin',
        '蛋白质': 'Protein',
        '白蛋白': 'Albumin',
        '球蛋白': 'Globulin',
        '纤维蛋白原': 'Fibrinogen',
        '凝血酶原': 'Prothrombin',
        '电解质': 'Electrolyte',
        '钠': 'Sodium',
        '钾': 'Potassium',
        '氯': 'Chloride',
        '钙': 'Calcium',
        '磷': 'Phosphorus',
        '镁': 'Magnesium',
        '铁': 'Iron',
        '维生素': 'Vitamin',
        '矿物质': 'Mineral',
        '微量元素': 'Trace Element',
        '激素': 'Hormone',
        '胰岛素': 'Insulin',
        '甲状腺素': 'Thyroxine',
        '肾上腺素': 'Adrenaline',
        '皮质醇': 'Cortisol',
        '生长激素': 'Growth Hormone',
        '性激素': 'Sex Hormone',
        '雌激素': 'Estrogen',
        '孕激素': 'Progesterone',
        '雄激素': 'Androgen',
        '睾酮': 'Testosterone',
        '催产素': 'Oxytocin',
        '抗利尿激素': 'ADH',
        '甲状旁腺激素': 'Parathyroid Hormone',
        '降钙素': 'Calcitonin',
        '促红细胞生成素': 'Erythropoietin',
        '细胞': 'Cell',
        '细胞器': 'Organelle',
        '细胞核': 'Nucleus',
        '线粒体': 'Mitochondria',
        '内质网': 'Endoplasmic Reticulum',
        '高尔基体': 'Golgi Apparatus',
        '溶酶体': 'Lysosome',
        '过氧化物酶体': 'Peroxisome',
        '细胞膜': 'Cell Membrane',
        '细胞壁': 'Cell Wall',
        '细胞质': 'Cytoplasm',
        '细胞骨架': 'Cytoskeleton',
        '染色体': 'Chromosome',
        'DNA': 'DNA',
        'RNA': 'RNA',
        'mRNA': 'mRNA',
        'tRNA': 'tRNA',
        'rRNA': 'rRNA',
        '基因': 'Gene',
        '基因组': 'Genome',
        '等位基因': 'Allele',
        '突变': 'Mutation',
        '多态性': 'Polymorphism',
        '单核苷酸多态性': 'SNP',
        '拷贝数变异': 'Copy Number Variation',
        '表观遗传': 'Epigenetics',
        '甲基化': 'Methylation',
        '乙酰化': 'Acetylation',
        '磷酸化': 'Phosphorylation',
        '泛素化': 'Ubiquitination',
        '糖基化': 'Glycosylation',
        '脂质化': 'Lipidation',
        '蛋白水解': 'Proteolysis',
        '翻译后修饰': 'Post-translational Modification',
        '转录': 'Transcription',
        '翻译': 'Translation',
        '复制': 'Replication',
        '重组': 'Recombination',
        '修复': 'Repair',
        '凋亡': 'Apoptosis',
        '坏死': 'Necrosis',
        '自噬': 'Autophagy',
        '增殖': 'Proliferation',
        '分化': 'Differentiation',
        '凋亡': 'Apoptosis',
        '侵袭': 'Invasion',
        '转移': 'Metastasis',
        '血管生成': 'Angiogenesis',
        '炎症': 'Inflammation',
        '免疫': 'Immunity',
        '自身免疫': 'Autoimmunity',
        '过敏': 'Allergy',
        '超敏反应': 'Hypersensitivity',
        '感染': 'Infection',
        '炎症因子': 'Inflammatory Cytokine',
        '趋化因子': 'Chemokine',
        '生长因子': 'Growth Factor',
        '细胞因子': 'Cytokine',
        '干扰素': 'Interferon',
        '白细胞介素': 'Interleukin',
        '肿瘤坏死因子': 'Tumor Necrosis Factor',
        '补体系统': 'Complement System',
        '抗体': 'Antibody',
        '抗原': 'Antigen',
        '疫苗': 'Vaccine',
        '佐剂': 'Adjuvant',
        '免疫原性': 'Immunogenicity',
        '耐受性': 'Tolerance',
        '免疫监视': 'Immune Surveillance',
        '免疫编辑': 'Immune Editing',
        '免疫逃逸': 'Immune Escape',
        '检查点抑制剂': 'Checkpoint Inhibitor',
        'CAR-T': 'CAR-T',
        '嵌合抗原受体': 'Chimeric Antigen Receptor',
        '肿瘤微环境': 'Tumor Microenvironment',
        '细胞外基质': 'Extracellular Matrix',
        '基底膜': 'Basement Membrane',
        '上皮间质转化': 'Epithelial Mesenchymal Transition',
        '上皮-间质转化': 'EMT',
        '干细胞': 'Stem Cell',
        '祖细胞': 'Progenitor Cell',
        '诱导多能干细胞': 'iPSC',
        '胚胎干细胞': 'Embryonic Stem Cell',
        '成体干细胞': 'Adult Stem Cell',
        '间充质干细胞': 'Mesenchymal Stem Cell',
        '肿瘤干细胞': 'Cancer Stem Cell',
        '类器官': 'Organoid',
        '器官芯片': 'Organ-on-a-Chip',
        '3D打印': '3D Printing',
        '生物打印': 'Bioprinting',
        '组织工程': 'Tissue Engineering',
        '再生医学': 'Regenerative Medicine',
        '基因治疗': 'Gene Therapy',
        '细胞治疗': 'Cell Therapy',
        '免疫治疗': 'Immunotherapy',
        '靶向治疗': 'Targeted Therapy',
        '精准医学': 'Precision Medicine',
        '个体化医疗': 'Personalized Medicine',
        '转化医学': 'Translational Medicine',
        '伴随诊断': 'Companion Diagnostics',
        '药物基因组学': 'Pharmacogenomics',
        '药物基因组学': 'Pharmacogenomics',
        '真实世界研究': 'Real World Study',
        '真实世界证据': 'Real World Evidence',
        '卫生经济学': 'Health Economics',
        '药物经济学': 'Pharmacoeconomics',
        '质量调整生命年': 'QALY',
        '伤残调整生命年': 'DALY',
        '卫生技术评估': 'Health Technology Assessment',
        '临床指南': 'Clinical Guideline',
        '临床路径': 'Clinical Pathway',
        '单病种管理': 'Single Disease Management',
        '多学科诊疗': 'Multidisciplinary Treatment',
        'MDT': 'MDT',
        '远程医疗': 'Telemedicine',
        '数字健康': 'Digital Health',
        '可穿戴设备': 'Wearable Device',
        '移动医疗': 'Mobile Health',
        '人工智能辅助诊断': 'AI-assisted Diagnosis',
        '计算机辅助诊断': 'Computer-aided Diagnosis',
        '影像组学': 'Radiomics',
        '放射组学': 'Radiomics',
        '组学': 'Omics',
        '多组学': 'Multi-omics',
        '整合组学': 'Integrative Omics',
        '系统生物学': 'Systems Biology',
        '合成生物学': 'Synthetic Biology',
        '计算生物学': 'Computational Biology',
        '生物医学工程': 'Biomedical Engineering',
        '医学人工智能': 'Medical AI',
        '医疗机器人': 'Medical Robot',
        '手术机器人': 'Surgical Robot',
        '康复机器人': 'Rehabilitation Robot',
        '辅助机器人': 'Assistive Robot',
        '纳米医学': 'Nanomedicine',
        '纳米药物': 'Nanodrug',
        '纳米载体': 'Nanocarrier',
        '靶向递送': 'Targeted Delivery',
        '控释系统': 'Controlled Release System',
        '缓释系统': 'Sustained Release System',
        '透皮给药': 'Transdermal Delivery',
        '黏膜给药': 'Mucosal Delivery',
        '血脑屏障': 'Blood Brain Barrier',
        '首过效应': 'First Pass Effect',
        '生物利用度': 'Bioavailability',
        '半衰期': 'Half-life',
        '代谢': 'Metabolism',
        '排泄': 'Excretion',
        '分布': 'Distribution',
        '吸收': 'Absorption',
        '药代动力学': 'Pharmacokinetics',
        '药效学': 'Pharmacodynamics',
        '毒性': 'Toxicity',
        '致癌性': 'Carcinogenicity',
        '致畸性': 'Teratogenicity',
        '致突变性': 'Mutagenicity',
        '生殖毒性': 'Reproductive Toxicity',
        '急性毒性': 'Acute Toxicity',
        '慢性毒性': 'Chronic Toxicity',
        '亚慢性毒性': 'Subchronic Toxicity',
        '安全范围': 'Safety Margin',
        '治疗指数': 'Therapeutic Index',
        '有效剂量': 'Effective Dose',
        '半数致死量': 'LD50',
        '半数有效量': 'ED50',
        '最大耐受剂量': 'Maximum Tolerated Dose',
        '无观察到有害作用水平': 'NOAEL',
        '基准剂量': 'Benchmark Dose',
        '暴露评估': 'Exposure Assessment',
        '风险评估': 'Risk Assessment',
        '风险管控': 'Risk Management',
        '风险沟通': 'Risk Communication',
        '利益风险平衡': 'Benefit Risk Balance',
        '获益': 'Benefit',
        '风险': 'Risk',
        '安全性': 'Safety',
        '有效性': 'Efficacy',
        '耐受性': 'Tolerability',
        '依从性': 'Compliance',
        '顺从性': 'Adherence',
        '生活质量': 'Quality of Life',
        '患者报告结局': 'Patient Reported Outcome',
        '终点': 'Endpoint',
        '替代终点': 'Surrogate Endpoint',
        '临床终点': 'Clinical Endpoint',
        '复合终点': 'Composite Endpoint',
        '主要终点': 'Primary Endpoint',
        '次要终点': 'Secondary Endpoint',
        '探索性终点': 'Exploratory Endpoint',
        '安全性终点': 'Safety Endpoint',
        '有效性终点': 'Efficacy Endpoint',
        '生物标志物': 'Biomarker',
        '药效学生物标志物': 'Pharmacodynamic Biomarker',
        '药代学生物标志物': 'Pharmacokinetic Biomarker',
        '预测性生物标志物': 'Predictive Biomarker',
        '预后性生物标志物': 'Prognostic Biomarker',
        '诊断性生物标志物': 'Diagnostic Biomarker',
        '监测性生物标志物': 'Monitoring Biomarker',
        '药物基因组学生物标志物': 'Pharmacogenomic Biomarker',
        '影像学生物标志物': 'Imaging Biomarker',
        '液体活检': 'Liquid Biopsy',
        '循环肿瘤细胞': 'Circulating Tumor Cell',
        '外泌体': 'Exosome',
        '循环肿瘤DNA': 'Circulating Tumor DNA',
        '循环RNA': 'Circulating RNA',
        '微小RNA': 'MicroRNA',
        '长链非编码RNA': 'lncRNA',
        '环状RNA': 'CircRNA',
        '信使RNA': 'mRNA',
        '转移RNA': 'tRNA',
        '核糖体RNA': 'rRNA',
        '小核RNA': 'snRNA',
        '核仁小RNA': 'snoRNA',
        'PIWI相互作用RNA': 'piRNA',
        'CRISPR': 'CRISPR',
        'Cas9': 'Cas9',
        '基因编辑': 'Gene Editing',
        '基因敲除': 'Gene Knockout',
        '基因敲入': 'Gene Knockin',
        '条件敲除': 'Conditional Knockout',
        '诱导敲除': 'Inducible Knockout',
        '组织特异性敲除': 'Tissue-specific Knockout',
        '基因沉默': 'Gene Silencing',
        'RNA干扰': 'RNA Interference',
        ' siRNA': 'siRNA',
        'miRNA': 'miRNA',
        'shRNA': 'shRNA',
        '反义寡核苷酸': 'Antisense Oligonucleotide',
        '反义RNA': 'Antisense RNA',
        '适配体': 'Aptamer',
        '肽': 'Peptide',
        '多肽': 'Polypeptide',
        '蛋白质': 'Protein',
        '酶': 'Enzyme',
        '受体': 'Receptor',
        '配体': 'Ligand',
        '底物': 'Substrate',
        '抑制剂': 'Inhibitor',
        '激动剂': 'Agonist',
        '拮抗剂': 'Antagonist',
        '激活剂': 'Activator',
        '辅因子': 'Cofactor',
        '辅酶': 'Coenzyme',
        '辅基': 'Prosthetic Group',
        '变构调节剂': 'Allosteric Modulator',
        '变构效应': 'Allosteric Effect',
        '协同效应': 'Cooperative Effect',
        '放大效应': 'Amplification Effect',
        '反馈调节': 'Feedback Regulation',
        '负反馈': 'Negative Feedback',
        '正反馈': 'Positive Feedback',
        '前馈': 'Feedforward',
        '级联反应': 'Cascade Reaction',
        '信号转导': 'Signal Transduction',
        '信号通路': 'Signaling Pathway',
        '代谢通路': 'Metabolic Pathway',
        '生化通路': 'Biochemical Pathway',
        '分子通路': 'Molecular Pathway',
        '细胞通路': 'Cellular Pathway',
        '基因调控网络': 'Gene Regulatory Network',
        '蛋白质相互作用网络': 'Protein Interaction Network',
        '代谢网络': 'Metabolic Network',
        '疾病网络': 'Disease Network',
        '药物靶点网络': 'Drug Target Network',
        '系统药理学': 'Systems Pharmacology',
        '网络药理学': 'Network Pharmacology',
        '生物信息学分析': 'Bioinformatics Analysis',
        '数据分析': 'Data Analysis',
        '大数据': 'Big Data',
        '人工智能': 'Artificial Intelligence',
        '机器学习': 'Machine Learning',
        '深度学习': 'Deep Learning',
        '神经网络': 'Neural Network',
        '卷积神经网络': 'Convolutional Neural Network',
        '循环神经网络': 'Recurrent Neural Network',
        '长短期记忆网络': 'LSTM',
        'Transformer': 'Transformer',
        '注意力机制': 'Attention Mechanism',
        '自注意力': 'Self-Attention',
        '图神经网络': 'Graph Neural Network',
        '生成对抗网络': 'Generative Adversarial Network',
        '变分自编码器': 'Variational Autoencoder',
        '自编码器': 'Autoencoder',
        '迁移学习': 'Transfer Learning',
        '联邦学习': 'Federated Learning',
        '强化学习': 'Reinforcement Learning',
        '半监督学习': 'Semi-supervised Learning',
        '无监督学习': 'Unsupervised Learning',
        '监督学习': 'Supervised Learning',
        '在线学习': 'Online Learning',
        '元学习': 'Meta Learning',
        '多任务学习': 'Multi-task Learning',
        '多模态学习': 'Multimodal Learning',
        'few-shot学习': 'Few-shot Learning',
        'zero-shot学习': 'Zero-shot Learning',
        'one-shot学习': 'One-shot Learning',
        '数据增强': 'Data Augmentation',
        '正则化': 'Regularization',
        'dropout': 'Dropout',
        '批归一化': 'Batch Normalization',
        '层归一化': 'Layer Normalization',
        '残差连接': 'Residual Connection',
        '跳跃连接': 'Skip Connection',
        '注意力': 'Attention',
        '多头注意力': 'Multi-head Attention',
        '位置编码': 'Positional Encoding',
        '嵌入': 'Embedding',
        '词嵌入': 'Word Embedding',
        '句嵌入': 'Sentence Embedding',
        '文档嵌入': 'Document Embedding',
        '图像嵌入': 'Image Embedding',
        '特征提取': 'Feature Extraction',
        '特征选择': 'Feature Selection',
        '特征工程': 'Feature Engineering',
        '降维': 'Dimensionality Reduction',
        '主成分分析': 'PCA',
        't-SNE': 't-SNE',
        'UMAP': 'UMAP',
        '聚类': 'Clustering',
        '分类': 'Classification',
        '回归': 'Regression',
        '预测': 'Prediction',
        '诊断': 'Diagnosis',
        '预后': 'Prognosis',
        '治疗': 'Treatment',
        '检测': 'Detection',
        '识别': 'Recognition',
        '分割': 'Segmentation',
        '配准': 'Registration',
        '重建': 'Reconstruction',
        '生成': 'Generation',
        '合成': 'Synthesis',
        '变换': 'Transformation',
        '映射': 'Mapping',
        '对齐': 'Alignment',
        '匹配': 'Matching',
        '检索': 'Retrieval',
        '推荐': 'Recommendation',
        '排序': 'Ranking',
        '过滤': 'Filtering',
        '去重': 'Deduplication',
        '融合': 'Fusion',
        '集成': 'Ensemble',
        '投票': 'Voting',
        '堆叠': 'Stacking',
        '袋装': 'Bagging',
        '提升': 'Boosting',
        '随机森林': 'Random Forest',
        '梯度提升树': 'Gradient Boosting Tree',
        'XGBoost': 'XGBoost',
        'LightGBM': 'LightGBM',
        'CatBoost': 'CatBoost',
        '支持向量机': 'SVM',
        '逻辑回归': 'Logistic Regression',
        '线性回归': 'Linear Regression',
        '决策树': 'Decision Tree',
        '朴素贝叶斯': 'Naive Bayes',
        'K近邻': 'KNN',
        'K-means': 'K-means',
        '层次聚类': 'Hierarchical Clustering',
        '密度聚类': 'Density-based Clustering',
        '谱聚类': 'Spectral Clustering',
        '高斯混合模型': 'Gaussian Mixture Model',
        '隐马尔可夫模型': 'Hidden Markov Model',
        '条件随机场': 'Conditional Random Field',
        '隐语义模型': 'Latent Semantic Model',
        '矩阵分解': 'Matrix Factorization',
        '奇异值分解': 'SVD',
        '非负矩阵分解': 'NMF',
        '主成分分析': 'PCA',
        '线性判别分析': 'LDA',
        '二次判别分析': 'QDA',
        '感知机': 'Perceptron',
        '多层感知机': 'MLP',
        '人工神经网络': 'Artificial Neural Network',
        '前馈神经网络': 'Feedforward Neural Network',
        '反馈神经网络': 'Feedback Neural Network',
        '自组织映射': 'Self-Organizing Map',
        '玻尔兹曼机': 'Boltzmann Machine',
        '受限玻尔兹曼机': 'Restricted Boltzmann Machine',
        '深度信念网络': 'Deep Belief Network',
        '堆叠自编码器': 'Stacked Autoencoder',
        '稀疏自编码器': 'Sparse Autoencoder',
        '降噪自编码器': 'Denoising Autoencoder',
        '变分自编码器': 'Variational Autoencoder',
        '生成对抗网络': 'GAN',
        '条件生成对抗网络': 'Conditional GAN',
        '循环一致性对抗网络': 'CycleGAN',
        '风格迁移': 'Style Transfer',
        '图像超分辨率': 'Image Super-resolution',
        '图像修复': 'Image Inpainting',
        '图像生成': 'Image Generation',
        '文本生成': 'Text Generation',
        '语音识别': 'Speech Recognition',
        '语音合成': 'Speech Synthesis',
        '自然语言处理': 'NLP',
        '自然语言理解': 'NLU',
        '自然语言生成': 'NLG',
        '词性标注': 'Part-of-speech Tagging',
        '命名实体识别': 'Named Entity Recognition',
        '依存句法分析': 'Dependency Parsing',
        '语义分析': 'Semantic Analysis',
        '情感分析': 'Sentiment Analysis',
        '主题模型': 'Topic Model',
        '问答系统': 'Question Answering System',
        '机器翻译': 'Machine Translation',
        '文本摘要': 'Text Summarization',
        '文本分类': 'Text Classification',
        '文本聚类': 'Text Clustering',
        '信息检索': 'Information Retrieval',
        '信息抽取': 'Information Extraction',
        '知识图谱': 'Knowledge Graph',
        '本体': 'Ontology',
        '语义网': 'Semantic Web',
        '关联数据': 'Linked Data',
        '数据挖掘': 'Data Mining',
        '知识发现': 'Knowledge Discovery',
        '模式识别': 'Pattern Recognition',
        '计算机视觉': 'Computer Vision',
        '图像处理': 'Image Processing',
        '视频分析': 'Video Analysis',
        '目标检测': 'Object Detection',
        '目标跟踪': 'Object Tracking',
        '人脸识别': 'Face Recognition',
        '行为识别': 'Action Recognition',
        '场景理解': 'Scene Understanding',
        '语义分割': 'Semantic Segmentation',
        '实例分割': 'Instance Segmentation',
        '全景分割': 'Panoptic Segmentation',
        '边缘检测': 'Edge Detection',
        '角点检测': 'Corner Detection',
        '特征点检测': 'Feature Point Detection',
        '特征匹配': 'Feature Matching',
        '图像配准': 'Image Registration',
        '图像融合': 'Image Fusion',
        '图像增强': 'Image Enhancement',
        '图像去噪': 'Image Denoising',
        '图像压缩': 'Image Compression',
        '图像检索': 'Image Retrieval',
        '视频检索': 'Video Retrieval',
        '音频检索': 'Audio Retrieval',
        '多模态检索': 'Multimodal Retrieval',
        '跨模态检索': 'Cross-modal Retrieval',
        '医学图像分析': 'Medical Image Analysis',
        '医学图像处理': 'Medical Image Processing',
        '计算机辅助诊断': 'Computer Aided Diagnosis',
        '影像组学': 'Radiomics',
        '放射组学': 'Radiomics',
        '影像基因组学': 'Radiogenomics',
        '深度学习': 'Deep Learning',
        '机器学习': 'Machine Learning',
        '人工智能': 'Artificial Intelligence',
        '应用': 'Application',
        '分析': 'Analysis',
        '研究': 'Study',
        '模型': 'Model',
        '算法': 'Algorithm',
        '方法': 'Method',
        '技术': 'Technology',
        '系统': 'System',
        '平台': 'Platform',
        '框架': 'Framework',
        '工具': 'Tool',
        '数据库': 'Database',
        '数据集': 'Dataset',
        '数据': 'Data',
        '信息': 'Information',
        '知识': 'Knowledge',
        '智能': 'Intelligence',
        '计算': 'Computing',
        '计算智能': 'Computational Intelligence',
        '模糊逻辑': 'Fuzzy Logic',
        '神经网络': 'Neural Network',
        '进化计算': 'Evolutionary Computation',
        '遗传算法': 'Genetic Algorithm',
        '粒子群优化': 'Particle Swarm Optimization',
        '蚁群算法': 'Ant Colony Algorithm',
        '模拟退火': 'Simulated Annealing',
        '禁忌搜索': 'Tabu Search',
        '启发式算法': 'Heuristic Algorithm',
        '元启发式算法': 'Meta-heuristic Algorithm',
        '超启发式算法': 'Hyper-heuristic Algorithm',
        '协同进化': 'Coevolution',
        '差分进化': 'Differential Evolution',
        '免疫算法': 'Immune Algorithm',
        'DNA计算': 'DNA Computing',
        '量子计算': 'Quantum Computing',
        '量子机器学习': 'Quantum Machine Learning',
        '量子神经网络': 'Quantum Neural Network',
        '边缘计算': 'Edge Computing',
        '云计算': 'Cloud Computing',
        '雾计算': 'Fog Computing',
        '网格计算': 'Grid Computing',
        '分布式计算': 'Distributed Computing',
        '并行计算': 'Parallel Computing',
        '高性能计算': 'High Performance Computing',
        '超级计算': 'Supercomputing',
        '物联网': 'Internet of Things',
        '工业互联网': 'Industrial Internet',
        '车联网': 'Internet of Vehicles',
        '医疗物联网': 'Medical Internet of Things',
        '智慧医疗': 'Smart Healthcare',
        '精准医疗': 'Precision Medicine',
        '个性化医疗': 'Personalized Medicine',
        '转化医学': 'Translational Medicine',
        '数字医学': 'Digital Medicine',
        '数字病理': 'Digital Pathology',
        '数字影像': 'Digital Imaging',
        '电子病历': 'Electronic Medical Record',
        '电子健康档案': 'Electronic Health Record',
        '医院信息系统': 'Hospital Information System',
        '临床决策支持系统': 'Clinical Decision Support System',
        '医学专家系统': 'Medical Expert System',
        '医学知识图谱': 'Medical Knowledge Graph',
        '医学本体': 'Medical Ontology',
        '医学语义网': 'Medical Semantic Web',
        '医学数据挖掘': 'Medical Data Mining',
        '医学知识发现': 'Medical Knowledge Discovery',
        '医学信息学': 'Medical Informatics',
        '生物医学信息学': 'Biomedical Informatics',
        '临床信息学': 'Clinical Informatics',
        '公共卫生信息学': 'Public Health Informatics',
        '护理信息学': 'Nursing Informatics',
        '口腔医学信息学': 'Dental Informatics',
        '药学信息学': 'Pharmaceutical Informatics',
        '营养学信息学': 'Nutritional Informatics',
        '运动医学信息学': 'Sports Medicine Informatics',
        '法医信息学': 'Forensic Informatics',
        '兽医信息学': 'Veterinary Informatics',
        '全球健康信息学': 'Global Health Informatics',
        '灾害医学信息学': 'Disaster Medicine Informatics',
        '航空航天医学信息学': 'Aerospace Medicine Informatics',
        '军事医学信息学': 'Military Medicine Informatics',
        '太空医学信息学': 'Space Medicine Informatics',
        '潜水医学信息学': 'Diving Medicine Informatics',
        '高原医学信息学': 'High Altitude Medicine Informatics',
        '热带医学信息学': 'Tropical Medicine Informatics',
        '旅行医学信息学': 'Travel Medicine Informatics',
        '职业医学信息学': 'Occupational Medicine Informatics',
        '环境医学信息学': 'Environmental Medicine Informatics',
        '社会医学信息学': 'Social Medicine Informatics',
        '行为医学信息学': 'Behavioral Medicine Informatics',
        '心理医学信息学': 'Psychiatric Informatics',
        '康复医学信息学': 'Rehabilitation Medicine Informatics',
        '老年医学信息学': 'Geriatric Medicine Informatics',
        '儿科医学信息学': 'Pediatric Medicine Informatics',
        '妇产科医学信息学': 'Obstetrics and Gynecology Informatics',
        '眼科医学信息学': 'Ophthalmology Informatics',
        '耳鼻喉科医学信息学': 'ENT Informatics',
        '皮肤科医学信息学': 'Dermatology Informatics',
        '精神科医学信息学': 'Psychiatry Informatics',
        '神经科医学信息学': 'Neurology Informatics',
        '心血管内科信息学': 'Cardiology Informatics',
        '呼吸内科信息学': 'Respiratory Medicine Informatics',
        '消化内科信息学': 'Gastroenterology Informatics',
        '肾内科信息学': 'Nephrology Informatics',
        '血液内科信息学': 'Hematology Informatics',
        '内分泌科信息学': 'Endocrinology Informatics',
        '风湿免疫科信息学': 'Rheumatology and Immunology Informatics',
        '感染科信息学': 'Infectious Disease Informatics',
        '肿瘤科信息学': 'Oncology Informatics',
        '疼痛科信息学': 'Pain Medicine Informatics',
        '急诊科信息学': 'Emergency Medicine Informatics',
        '重症医学科信息学': 'Critical Care Medicine Informatics',
        '麻醉科信息学': 'Anesthesiology Informatics',
        '外科信息学': 'Surgery Informatics',
        '骨科信息学': 'Orthopedics Informatics',
        '泌尿外科信息学': 'Urology Informatics',
        '神经外科信息学': 'Neurosurgery Informatics',
        '胸外科信息学': 'Thoracic Surgery Informatics',
        '心脏外科信息学': 'Cardiac Surgery Informatics',
        '血管外科信息学': 'Vascular Surgery Informatics',
        '整形外科信息学': 'Plastic Surgery Informatics',
        '烧伤科信息学': 'Burn Medicine Informatics',
        '移植外科信息学': 'Transplant Surgery Informatics',
        '微创外科信息学': 'Minimally Invasive Surgery Informatics',
        '机器人外科信息学': 'Robotic Surgery Informatics',
        '介入放射学信息学': 'Interventional Radiology Informatics',
        '核医学信息学': 'Nuclear Medicine Informatics',
        '放射治疗科信息学': 'Radiotherapy Informatics',
        '放疗科信息学': 'Radiation Oncology Informatics',
        '化疗科信息学': 'Chemotherapy Informatics',
        '姑息治疗科信息学': 'Palliative Care Informatics',
        '临终关怀信息学': 'Hospice Informatics',
        '康复科信息学': 'Rehabilitation Medicine Informatics',
        '物理医学与康复科信息学': 'Physical Medicine and Rehabilitation Informatics',
        '言语治疗科信息学': 'Speech Therapy Informatics',
        '作业治疗科信息学': 'Occupational Therapy Informatics',
        '临床营养科信息学': 'Clinical Nutrition Informatics',
        '临床心理科信息学': 'Clinical Psychology Informatics',
        '临床药学信息学': 'Clinical Pharmacy Informatics',
        '临床检验科信息学': 'Clinical Laboratory Informatics',
        '临床病理科信息学': 'Clinical Pathology Informatics',
        '临床影像科信息学': 'Clinical Radiology Informatics',
        '临床麻醉科信息学': 'Clinical Anesthesiology Informatics',
        '临床手术室信息学': 'Clinical Operating Room Informatics',
        '临床重症监护室信息学': 'Clinical ICU Informatics',
        '临床急诊科信息学': 'Clinical Emergency Medicine Informatics',
        '临床门诊信息学': 'Clinical Outpatient Informatics',
        '临床住院部信息学': 'Clinical Inpatient Informatics',
        '临床护理信息学': 'Clinical Nursing Informatics',
        '临床医技信息学': 'Clinical Medical Technology Informatics',
        '临床科研信息学': 'Clinical Research Informatics',
        '临床教学信息学': 'Clinical Education Informatics',
        '临床培训信息学': 'Clinical Training Informatics',
        '临床质量管理信息学': 'Clinical Quality Management Informatics',
        '临床安全管理信息学': 'Clinical Safety Management Informatics',
        '临床感染控制信息学': 'Clinical Infection Control Informatics',
        '临床药物管理信息学': 'Clinical Medication Management Informatics',
        '临床设备管理信息学': 'Clinical Equipment Management Informatics',
        '临床耗材管理信息学': 'Clinical Consumables Management Informatics',
        '临床人力资源信息学': 'Clinical Human Resources Informatics',
        '临床财务管理信息学': 'Clinical Financial Management Informatics',
        '临床物流管理信息学': 'Clinical Logistics Management Informatics',
        '临床后勤管理信息学': 'Clinical Logistics Support Informatics',
        '临床信息管理信息学': 'Clinical Information Management Informatics',
        '临床数据管理信息学': 'Clinical Data Management Informatics',
        '临床知识管理信息学': 'Clinical Knowledge Management Informatics',
        '临床文档管理信息学': 'Clinical Document Management Informatics',
        '临床流程管理信息学': 'Clinical Process Management Informatics',
        '临床绩效管理信息学': 'Clinical Performance Management Informatics',
        '临床成本管理信息学': 'Clinical Cost Management Informatics',
        '临床效益管理信息学': 'Clinical Benefit Management Informatics',
        '临床风险管理信息学': 'Clinical Risk Management Informatics',
        '临床合规管理信息学': 'Clinical Compliance Management Informatics',
        '临床审计信息学': 'Clinical Audit Informatics',
        '临床认证信息学': 'Clinical Certification Informatics',
        '临床评审信息学': 'Clinical Evaluation Informatics',
        '临床考核信息学': 'Clinical Assessment Informatics',
        '临床监测信息学': 'Clinical Monitoring Informatics',
        '临床评估信息学': 'Clinical Evaluation Informatics',
        '临床调查信息学': 'Clinical Investigation Informatics',
        '临床实验信息学': 'Clinical Experiment Informatics',
        '临床测试信息学': 'Clinical Testing Informatics',
        '临床验证信息学': 'Clinical Validation Informatics',
        '临床确认信息学': 'Clinical Confirmation Informatics',
        '临床核准信息学': 'Clinical Approval Informatics',
        '临床注册信息学': 'Clinical Registration Informatics',
        '临床备案信息学': 'Clinical Record Informatics',
        '临床公示信息学': 'Clinical Publicity Informatics',
        '临床公告信息学': 'Clinical Announcement Informatics',
        '临床通报信息学': 'Clinical Notification Informatics',
        '临床报告信息学': 'Clinical Report Informatics',
        '临床反馈信息学': 'Clinical Feedback Informatics',
        '临床沟通信息学': 'Clinical Communication Informatics',
        '临床协调信息学': 'Clinical Coordination Informatics',
        '临床协作信息学': 'Clinical Collaboration Informatics',
        '临床会诊信息学': 'Clinical Consultation Informatics',
        '临床转诊信息学': 'Clinical Referral Informatics',
        '临床随访信息学': 'Clinical Follow-up Informatics',
        '临床复诊信息学': 'Clinical Review Informatics',
        '临床回访信息学': 'Clinical Return Visit Informatics',
        '临床追踪信息学': 'Clinical Tracking Informatics',
        '临床监测信息学': 'Clinical Monitoring Informatics',
        '临床观察信息学': 'Clinical Observation Informatics',
        '临床记录信息学': 'Clinical Documentation Informatics',
        '临床档案信息学': 'Clinical Archive Informatics',
        '临床病历信息学': 'Clinical Medical Record Informatics',
        '临床健康档案信息学': 'Clinical Health Record Informatics',
        '临床个人健康档案信息学': 'Clinical Personal Health Record Informatics',
        '临床家庭健康档案信息学': 'Clinical Family Health Record Informatics',
        '临床社区健康档案信息学': 'Clinical Community Health Record Informatics',
        '临床公共卫生档案信息学': 'Clinical Public Health Record Informatics',
        '临床人群健康档案信息学': 'Clinical Population Health Record Informatics',
        '临床全球健康档案信息学': 'Clinical Global Health Record Informatics',
        '临床行星健康档案信息学': 'Clinical Planetary Health Record Informatics',
        '临床一体化健康档案信息学': 'Clinical Integrated Health Record Informatics',
        '临床互联健康档案信息学': 'Clinical Connected Health Record Informatics',
        '临床智慧健康档案信息学': 'Clinical Smart Health Record Informatics',
        '临床数字健康档案信息学': 'Clinical Digital Health Record Informatics',
        '临床移动健康档案信息学': 'Clinical Mobile Health Record Informatics',
        '临床可穿戴健康档案信息学': 'Clinical Wearable Health Record Informatics',
        '临床远程健康档案信息学': 'Clinical Remote Health Record Informatics',
        '临床居家健康档案信息学': 'Clinical Home Health Record Informatics',
        '临床社区健康档案信息学': 'Clinical Community Health Record Informatics',
        '临床机构健康档案信息学': 'Clinical Institutional Health Record Informatics',
        '临床区域健康档案信息学': 'Clinical Regional Health Record Informatics',
        '临床国家健康档案信息学': 'Clinical National Health Record Informatics',
        '临床国际健康档案信息学': 'Clinical International Health Record Informatics',
        '临床比较健康档案信息学': 'Clinical Comparative Health Record Informatics',
        '临床转化健康档案信息学': 'Clinical Translational Health Record Informatics',
        '临床精准健康档案信息学': 'Clinical Precision Health Record Informatics',
        '临床个性化健康档案信息学': 'Clinical Personalized Health Record Informatics',
        '临床预测性健康档案信息学': 'Clinical Predictive Health Record Informatics',
        '临床预防性健康档案信息学': 'Clinical Preventive Health Record Informatics',
        '临床参与性健康档案信息学': 'Clinical Participatory Health Record Informatics',
        '临床精准医学档案信息学': 'Clinical Precision Medicine Record Informatics',
        '临床个性化医学档案信息学': 'Clinical Personalized Medicine Record Informatics',
        '临床预测性医学档案信息学': 'Clinical Predictive Medicine Record Informatics',
        '临床预防性医学档案信息学': 'Clinical Preventive Medicine Record Informatics',
        '临床参与性医学档案信息学': 'Clinical Participatory Medicine Record Informatics',
        '临床转化医学档案信息学': 'Clinical Translational Medicine Record Informatics',
        '临床整合医学档案信息学': 'Clinical Integrated Medicine Record Informatics',
        '临床替代医学档案信息学': 'Clinical Alternative Medicine Record Informatics',
        '临床补充医学档案信息学': 'Clinical Complementary Medicine Record Informatics',
        '临床整合医学档案信息学': 'Clinical Integrative Medicine Record Informatics',
        '临床功能医学档案信息学': 'Clinical Functional Medicine Record Informatics',
        '临床抗衰老医学档案信息学': 'Clinical Anti-aging Medicine Record Informatics',
        '临床再生医学档案信息学': 'Clinical Regenerative Medicine Record Informatics',
        '临床干细胞医学档案信息学': 'Clinical Stem Cell Medicine Record Informatics',
        '临床基因医学档案信息学': 'Clinical Gene Medicine Record Informatics',
        '临床蛋白质医学档案信息学': 'Clinical Protein Medicine Record Informatics',
        '临床代谢医学档案信息学': 'Clinical Metabolic Medicine Record Informatics',
        '临床免疫医学档案信息学': 'Clinical Immune Medicine Record Informatics',
        '临床微生物医学档案信息学': 'Clinical Microbiome Medicine Record Informatics',
        '临床表观遗传医学档案信息学': 'Clinical Epigenetic Medicine Record Informatics',
        '临床RNA医学档案信息学': 'Clinical RNA Medicine Record Informatics',
        '临床药物基因组学档案信息学': 'Clinical Pharmacogenomics Record Informatics',
        '临床蛋白质组学档案信息学': 'Clinical Proteomics Record Informatics',
        '临床代谢组学档案信息学': 'Clinical Metabolomics Record Informatics',
        '临床转录组学档案信息学': 'Clinical Transcriptomics Record Informatics',
        '临床微生物组学档案信息学': 'Clinical Microbiomics Record Informatics',
        '临床表观基因组学档案信息学': 'Clinical Epigenomics Record Informatics',
        '临床营养基因组学档案信息学': 'Clinical Nutrigenomics Record Informatics',
        '临床毒理基因组学档案信息学': 'Clinical Toxicogenomics Record Informatics',
        '临床化学基因组学档案信息学': 'Clinical Chemogenomics Record Informatics',
        '临床药物蛋白质组学档案信息学': 'Clinical Pharmacoproteomics Record Informatics',
        '临床药物代谢组学档案信息学': 'Clinical Pharmacometabolomics Record Informatics',
        '临床药物基因组学档案信息学': 'Clinical Pharmacogenomics Record Informatics',
        '临床药物表观基因组学档案信息学': 'Clinical Pharmacoepigenomics Record Informatics',
        '临床药物微生物组学档案信息学': 'Clinical Pharmacomicrobiomics Record Informatics',
        '临床药物转录组学档案信息学': 'Clinical Pharmacotranscriptomics Record Informatics',
        '临床药物蛋白质组学档案信息学': 'Clinical Pharmacoproteomics Record Informatics',
        '临床药物代谢组学档案信息学': 'Clinical Pharmacometabolomics Record Informatics',
        '临床药物基因组学档案信息学': 'Clinical Pharmacogenomics Record Informatics',
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

