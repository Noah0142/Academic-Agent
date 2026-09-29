# 学术智能体 — AI在膝骨关节炎精准分型中的应用文献检索

基于 Flask 的学术文献检索与综述报告生成系统，支持 PubMed、IEEE Xplore、OpenAlex 多数据库检索。

## 功能特性

- 多数据库文献检索（PubMed / IEEE Xplore / OpenAlex）
- 自动中英文检索式生成
- 文献去重与合并
- 综述报告生成（Markdown 预览 + Word 下载）
- 引用核验
- 三区布局 WebUI

## 技术栈

- **后端**: Flask (Python 3.13)
- **前端**: 原生 HTML/CSS/JavaScript
- **检索**: Biopython (Entrez E-utilities)
- **报告**: python-docx

## 本地运行

```bash
cd 项目代码
python app/webui.py
```

浏览器访问 http://localhost:7000

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PUBMED_EMAIL` | PubMed E-utilities 邮箱 | Noah13610480142@outlook.com |
| `IEEE_API_KEY` | IEEE Xplore API Key | 无（使用样例数据） |

## 项目结构

```
项目代码/
├── app/
│   ├── webui.py           # Flask 主入口
│   ├── templates/
│   │   └── index.html     # 前端页面
│   └── static/
│       └── style.css      # 样式文件
├── modules/
│   ├── pubmed_retriever.py    # PubMed 检索
│   ├── ieee_retriever.py      # IEEE 检索
│   ├── openalex_retriever.py  # OpenAlex 检索
│   ├── report_generator.py    # 报告生成
│   └── ...
├── task_cards/            # 任务卡存储
├── literature/            # 文献数据存储
└── outputs/               # 输出文件
```

## 注意事项

- 项目初始化时会自动创建必要目录
- OpenAlex API 有频率限制（429），已做异常处理
- IEEE Xplore 无 API Key 时返回样例数据
- 综述报告生成后可在右下角预览，支持下载为 .docx

## License

MIT
