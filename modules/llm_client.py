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
        '你是一个专业的医学文献检索专家。'
        '请根据用户提供的中文研究主题，生成规范的英文检索式。'
        '只返回 JSON，不要返回其他内容。'
    )

    user_prompt = f"""请为主题"{theme}"（研究方向：{direction or '未指定'}）生成以下数据库的检索式：

数据库：{', '.join(databases)}

要求：
1. PubMed 检索式使用 MeSH 词 + 自由词组合，格式如：
   ("Knee Osteoarthritis"[MeSH] OR "Knee Osteoarthritis"[Title/Abstract]) AND ("Artificial Intelligence"[Title/Abstract] OR "Deep Learning"[Title/Abstract])
2. IEEE 检索式使用 Index Terms 精确匹配，格式如：
   ("Index Terms":Knee Osteoarthritis OR "Index Terms":Knee Osteoarthritis (KOA)) AND ("Index Terms":Deep Learning OR "Index Terms":Machine Learning)
3. OpenAlex 检索式直接使用关键词，用空格连接，如：
   Knee Osteoarthritis Artificial Intelligence Deep Learning

请返回 JSON 格式：
{{
  "pubmed": {{"query": "...", "filters": "近5年 | Journal Article, Review", "note": "..."}},
  "ieee": {{"query": "...", "filters": "近2年 | Conferences/Journals/Early Access", "note": "..."}},
  "openalex": {{"query": "...", "note": "..."}}
}}"""

    result = call_llm(system_prompt, user_prompt, temperature=0.3, max_tokens=1000)
    if not result:
        return None

    try:
        json_start = result.find('{')
        json_end = result.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_str = result[json_start:json_end]
            return json.loads(json_str)
    except Exception as e:
        print(f'[LLM] JSON parse error: {e}')

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
