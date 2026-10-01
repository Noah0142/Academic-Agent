# -*- coding: utf-8 -*-
"""
LLM 客户端模块 — 调用大语言模型生成检索式和报告
支持 GLM-4-Flash / DeepSeek / OpenAI 兼容 API
"""
import os, json, requests
from dotenv import load_dotenv

load_dotenv()

# GLM-4-Flash 默认配置
DEFAULT_API_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
DEFAULT_MODEL = 'glm-4-flash'


def get_llm_config():
    """从环境变量读取 LLM 配置。"""
    return {
        'api_url': os.environ.get('LLM_API_URL', DEFAULT_API_URL),
        'api_key': os.environ.get('LLM_API_KEY', ''),
        'model': os.environ.get('LLM_MODEL', DEFAULT_MODEL),
    }


def call_llm(system_prompt, user_prompt, temperature=0.3, max_tokens=2000):
    """调用 LLM 并返回文本内容。"""
    config = get_llm_config()
    if not config['api_key']:
        return None

    headers = {
        'Authorization': f"Bearer {config['api_key']}",
        'Content-Type': 'application/json',
    }
    payload = {
        'model': config['model'],
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': temperature,
        'max_tokens': max_tokens,
    }

    try:
        resp = requests.post(
            config['api_url'],
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
        return content.strip() if content else None
    except Exception as e:
        print(f'[LLM] Error: {e}')
        return None


def generate_queries_with_llm(theme, direction='', databases=None):
    """使用 LLM 生成英文检索式。"""
    if databases is None:
        databases = ['PubMed', 'IEEE Xplore']

    system_prompt = (
        '你是一个专业的医学文献检索专家，精通 PubMed MeSH 词表、IEEE Xplore Index Terms 检索语法。'
        '请根据中文研究主题，生成符合各数据库规范的英文检索式。'
        '只返回 JSON，不要返回其他内容。'
    )

    user_prompt = f"""请为主题"{theme}"（研究方向：{direction or '未指定'}）生成以下数据库的检索式：

【PubMed 检索式要求】
1. 必须使用 MeSH 主题词 + 自由词组合
2. 格式规范：
   - MeSH 词：("Knee Osteoarthritis"[MeSH])
   - 自由词：("Knee Osteoarthritis"[Title/Abstract])
   - 组合：("Knee Osteoarthritis"[MeSH] OR "Knee Osteoarthritis"[Title/Abstract])
   - 不同概念用 AND 连接
   - 同义词/缩略语用 OR 连接
   - 截词符：Radiograph*
3. 示例完整检索式：
   ("Knee Osteoarthritis"[MeSH] OR "Knee Osteoarthritis"[Title/Abstract]) AND ("Artificial Intelligence"[Title/Abstract] OR "Deep Learning"[Title/Abstract] OR "Machine Learning"[Title/Abstract]) AND ("Medical Imaging"[Title/Abstract] OR "Radiograph*"[Title/Abstract] OR "Magnetic Resonance Imaging"[Title/Abstract])

【IEEE Xplore 检索式要求】
1. 使用 "Index Terms":Term 精确匹配
2. 缩略语放在括号内：Knee Osteoarthritis (KOA)
3. 不同概念用 AND 连接
4. 示例：
   ("Index Terms":Knee Osteoarthritis OR "Index Terms":Knee Osteoarthritis (KOA)) AND ("Index Terms":Deep Learning OR "Index Terms":Machine Learning OR "Index Terms":Convolutional Neural Networks) AND ("Index Terms":Image Classification OR "Index Terms":Medical Imaging)

【OpenAlex 检索式要求】
1. 直接使用英文关键词，空格连接
2. 示例：Knee Osteoarthritis Artificial Intelligence Deep Learning

重要提示：
- 每个数据库的 query 字段必须是完整的、可执行的检索式字符串
- 不要使用 + 号拼接字符串，不要换行，整个检索式放在一个字符串中
- JSON 中的双引号不需要转义，直接写英文双引号即可

请返回 JSON 格式（query 字段必须是符合上述规范的完整检索式字符串，不要包含任何换行符）：
{{
  "pubmed": {{"query": "完整的 PubMed 检索式", "filters": "近5年 | Journal Article, Review", "note": "MeSH + 自由词组合"}},
  "ieee": {{"query": "完整的 IEEE 检索式", "filters": "近2年 | Conferences/Journals/Early Access", "note": "Index Terms 精确匹配"}},
  "openalex": {{"query": "OpenAlex 关键词", "note": "空格分隔关键词"}}
}}"""

    result = call_llm(system_prompt, user_prompt, temperature=0.3, max_tokens=1500)
    if not result:
        return None

    try:
        # 去除代码块标记
        cleaned = result.strip()
        if cleaned.startswith('```json'):
            cleaned = cleaned[7:]
        elif cleaned.startswith('```'):
            cleaned = cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # 尝试直接解析完整 JSON
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                # 确保返回的字典包含所需的键
                result_dict = {}
                for db in ['pubmed', 'ieee', 'openalex']:
                    if db in parsed:
                        result_dict[db] = parsed[db]
                if result_dict:
                    return result_dict
        except json.JSONDecodeError:
            pass

        # 如果直接解析失败，用正则提取各个数据库的检索式
        import re

        result_dict = {}

        # 提取 pubmed
        pubmed_query = re.search(r'"pubmed"\s*:\s*\{[^}]*"query"\s*:\s*"(.+?)"(?=\s*[,}])', cleaned, re.DOTALL)
        pubmed_filters = re.search(r'"pubmed"\s*:\s*\{[^}]*"filters"\s*:\s*"([^"]*)"', cleaned, re.DOTALL)
        pubmed_note = re.search(r'"pubmed"\s*:\s*\{[^}]*"note"\s*:\s*"([^"]*)"', cleaned, re.DOTALL)

        if pubmed_query:
            query = pubmed_query.group(1)
            # 修复引号：将 'Term'[Field] 替换回 "Term"[Field]，并去除多余转义
            query = re.sub(r"'([^']+)'(\[\w+\])", r'"\1"\2', query)
            query = query.replace('\\"', '"').replace('\\\\', '\\')
            result_dict['pubmed'] = {
                'query': query,
                'filters': pubmed_filters.group(1) if pubmed_filters else '近5年 | Journal Article, Review',
                'note': pubmed_note.group(1) if pubmed_note else '',
            }

        # 提取 ieee
        ieee_query = re.search(r'"ieee"\s*:\s*\{[^}]*"query"\s*:\s*"(.+?)"(?=\s*[,}])', cleaned, re.DOTALL)
        ieee_filters = re.search(r'"ieee"\s*:\s*\{[^}]*"filters"\s*:\s*"([^"]*)"', cleaned, re.DOTALL)
        ieee_note = re.search(r'"ieee"\s*:\s*\{[^}]*"note"\s*:\s*"([^"]*)"', cleaned, re.DOTALL)

        if ieee_query:
            query = ieee_query.group(1)
            query = re.sub(r"'([^']+)'(\[\w+\])", r'"\1"\2', query)
            query = query.replace('\\"', '"').replace('\\\\', '\\')
            result_dict['ieee'] = {
                'query': query,
                'filters': ieee_filters.group(1) if ieee_filters else '近2年 | Conferences/Journals/Early Access',
                'note': ieee_note.group(1) if ieee_note else '',
            }

        # 提取 openalex
        oalex_query = re.search(r'"openalex"\s*:\s*\{[^}]*"query"\s*:\s*"([^"]*)"', cleaned, re.DOTALL)
        oalex_note = re.search(r'"openalex"\s*:\s*\{[^}]*"note"\s*:\s*"([^"]*)"', cleaned, re.DOTALL)

        if oalex_query:
            result_dict['openalex'] = {
                'query': oalex_query.group(1),
                'note': oalex_note.group(1) if oalex_note else '',
            }

        if result_dict:
            return result_dict

    except Exception as e:
        print(f'[LLM] Parse error: {e}')

    return None


def generate_report_with_llm(task_card, papers):
    """使用 LLM 生成综述报告内容。"""
    theme = task_card.get('theme', '未指定主题')
    n = len(papers)

    # 构建文献摘要
    paper_summaries = []
    for i, p in enumerate(papers[:15], 1):
        summary = f"[{i}] {p.get('title', 'N/A')}\n"
        summary += f"    作者：{p.get('authors', 'N/A')} | 年份：{p.get('year', 'N/A')} | 期刊：{p.get('journal', 'N/A')}\n"
        if p.get('doi'):
            summary += f"    DOI：{p['doi']}\n"
        abstract = p.get('abstract', '')
        if abstract:
            summary += f"    摘要：{abstract[:300]}{'...' if len(abstract) > 300 else ''}\n"
        paper_summaries.append(summary)

    papers_text = '\n'.join(paper_summaries)

    system_prompt = (
        '你是一个专业的医学研究综述写作专家。'
        '请根据提供的检索结果，撰写一篇结构化的学术综述报告。'
        '使用 Markdown 格式输出。'
    )

    user_prompt = f"""请为主题"{theme}"撰写一篇综述报告。

检索到的文献（共 {n} 篇）：
{papers_text}

要求：
1. 结构包含：摘要、引言、检索策略、检索结果、重点文献分析（前10篇）、讨论、结论、参考文献
2. 语言风格：学术性、客观、准确
3. 重点分析 AI 在医学影像诊断中的应用进展
4. 参考文献格式：[序号] 作者 (年份). 标题. 期刊. DOI
5. 讨论部分要指出当前研究的局限性和未来方向
6. 直接输出 Markdown 格式的报告内容，不要包含其他说明文字"""

    result = call_llm(system_prompt, user_prompt, temperature=0.5, max_tokens=4000)
    return result
