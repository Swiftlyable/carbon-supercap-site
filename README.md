# 碳网图谱 CarbonNet

碳材料超级电容器**三维导电网络**方向的文献知识站：领域思维导图、知识关系图、文献库与性能数据面板，**每周自动更新**。

- 🌐 站点页面：首页 / 思维导图 / 文献库 / 关系图 / 数据面板 / 关于
- 📚 数据源：[OpenAlex](https://openalex.org)（开放学术索引，与 WoS 同源 DOI/引用数据），支持导入 Web of Science 导出文件
- ⚙️ 零依赖：Python 仅用标准库，前端仅依赖本地 vendored ECharts

## 快速开始

```bash
# 本地预览
python -m http.server 8000
# 浏览器打开 http://localhost:8000

# 抓取/更新文献数据（默认：核心 + 补充检索式 + 经典文献清单）
python scripts/fetch_papers.py
python scripts/build_data.py
# 也可单独运行某一部分：
python scripts/fetch_papers.py --extra-only      # 仅补充检索式
python scripts/fetch_papers.py --classics-only   # 仅经典文献匹配
python scripts/fetch_papers.py --reclassify      # 仅重新分类综述

# 导入 Web of Science 导出文件（可选）
python scripts/import_wos.py 路径/savedrecs.txt
python scripts/build_data.py
```

## 部署到 GitHub Pages

1. 在 GitHub 新建仓库并推送本目录：

   ```bash
   git init && git add . && git commit -m "init"
   git branch -M main
   git remote add origin git@github.com:<你的用户名>/carbon-supercap-site.git
   git push -u origin main
   ```

2. 仓库 **Settings → Pages → Build and deployment → Source** 选择 **GitHub Actions**。

3. 完成后站点位于 `https://<你的用户名>.github.io/carbon-supercap-site/`，
   每次 push 自动部署。

## 自动更新

`.github/workflows/update-papers.yml` 每周一 02:30 UTC（北京 10:30）自动运行：

```
fetch_papers.py（OpenAlex 增量抓取）→ build_data.py（统计/关系图）→ 提交 data/ → Pages 自动重部署
```

也可在 Actions 页手动触发（Run workflow）。可选：在仓库 Settings → Secrets 里添加
`OPENALEX_MAILTO`（你的邮箱），进入 OpenAlex polite pool 获得更高限流。

## 数据文件

| 文件 | 内容 | 生成方式 |
|---|---|---|
| `data/papers.json` | 文献元数据（含标签、性能数值、经典文献标记） | `fetch_papers.py` / `import_wos.py` |
| `data/classics.json` | 领域经典文献（专家清单 + 中文点评） | `fetch_papers.py --classics-only` |
| `data/taxonomy.json` | 领域思维导图（专家整理，手写） | 手动维护 |
| `data/stats.json` | 聚合统计、性能分布、共现矩阵 | `build_data.py` |
| `data/graph.json` | 知识关系图节点与边 | `build_data.py` |
| `data/featured.json` | 首页精选文献 | `build_data.py` |

## 免责声明

摘要性能数值由正则自动抽取，引用前请核对原文；期刊 Q1 标记依据 JCR 分区整理，可能随时间变动。
