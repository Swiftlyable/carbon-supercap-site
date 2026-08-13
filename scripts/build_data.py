# -*- coding: utf-8 -*-
"""
build_data.py — 由 papers.json 生成站点所需的派生数据
============================================================
- data/stats.json  聚合统计 + 性能参数分布（供数据面板页面使用）
- data/graph.json  三维导电网络知识关系图（标签节点 + 论文节点 + 边）
- data/featured.json  首页精选文献
纯标准库实现，可反复运行。
"""

import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
PAPERS_FILE = os.path.join(DATA_DIR, "papers.json")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vocab import VOCAB  # noqa: E402

MAX_GRAPH_PAPERS = 110     # 关系图中论文节点上限
MIN_TAG_LINK = 5           # 标签共现边的最小共同论文数
NOW_YEAR = datetime.now(timezone.utc).year


def load_papers():
    with open(PAPERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def build_stats(papers):
    by_year = Counter(p["year"] for p in papers if p.get("year"))
    journals = Counter(p["journal"] for p in papers)
    concepts = Counter(c for p in papers for c in (p.get("concepts") or []))
    authors = Counter(a for p in papers for a in (p.get("authors") or []))
    institutions = Counter(i for p in papers for i in (p.get("institutions") or []))
    tags = Counter(t for p in papers for t in (p.get("tags") or []))

    # 标签按类别分组
    tag_meta = {cn: category for cn, category, _ in VOCAB}

    metrics = {"f_per_g": [], "wh_per_kg": [], "w_per_kg": [], "retention": []}
    for p in papers:
        m = p.get("metrics") or {}
        for k in metrics:
            if k in m:
                metrics[k].append(m[k])

    cited = [p["cited_by_count"] for p in papers if p.get("cited_by_count")]
    core_journals = Counter(p["journal"] for p in papers if p.get("core_journal"))

    # 材料 × 策略 共现矩阵（热力图）
    rows = [cn for cn, cat, _ in VOCAB if cat == "material"]
    cols = [cn for cn, cat, _ in VOCAB if cat == "strategy"]
    co = Counter()
    for p in papers:
        pt = set(p.get("tags") or [])
        for r in rows:
            if r in pt:
                for c in cols:
                    if c in pt:
                        co[(r, c)] += 1
    heatmap = [[ri, ci, co[(r, c)]] for ri, r in enumerate(rows)
               for ci, c in enumerate(cols) if co[(r, c)] > 0]

    by_year_type = defaultdict(lambda: {"article": 0, "review": 0})
    for p in papers:
        if p.get("year"):
            by_year_type[p["year"]][p["type"]] += 1

    return {
        "last_updated": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "totals": {
            "papers": len(papers),
            "reviews": sum(1 for p in papers if p["type"] == "review"),
            "oa": sum(1 for p in papers if p.get("oa")),
            "core_journal": sum(1 for p in papers if p.get("core_journal")),
            "tagged": sum(1 for p in papers if p.get("tags")),
            "classics": sum(1 for p in papers if p.get("classic")),
            "cited_total": sum(cited),
            "cited_max": max(cited) if cited else 0,
            "cited_avg": round(sum(cited) / len(cited), 1) if cited else 0,
            "year_min": min(by_year) if by_year else NOW_YEAR,
            "year_max": max(by_year) if by_year else NOW_YEAR,
            "n_authors": len(authors),
            "n_institutions": len(institutions),
            "core_journals_n": len(core_journals),
        },
        "by_year": [{"year": y, "count": by_year[y]} for y in sorted(by_year)],
        "by_year_type": [{"year": y, "article": by_year_type[y]["article"],
                          "review": by_year_type[y]["review"]} for y in sorted(by_year_type)],
        "journals": [{"name": j, "count": n, "core": j in core_journals}
                     for j, n in journals.most_common(15)],
        "concepts": [{"name": c, "count": n} for c, n in concepts.most_common(20)],
        "authors_top": [{"name": a, "count": n} for a, n in authors.most_common(12)],
        "institutions_top": [{"name": i, "count": n} for i, n in institutions.most_common(12)],
        "tags": [{"name": t, "category": tag_meta.get(t, "other"), "count": n}
                 for t, n in tags.most_common()],
        "metrics": metrics,
        "heatmap": {"rows": rows, "cols": cols, "data": heatmap},
    }


def paper_score(p):
    """精选文献评分：被引对数 + 近因加权"""
    c = p.get("cited_by_count") or 0
    y = p.get("year") or NOW_YEAR - 10
    cite_score = min(math.log10(c + 1), 3.0) / 3.0
    recent = max(0.0, 1.0 - (NOW_YEAR - y) / 12.0)
    return 0.55 * cite_score + 0.45 * recent


def build_graph(papers):
    tag_count = Counter(t for p in papers for t in (p.get("tags") or []))
    if not tag_count:
        return {"nodes": [], "links": []}

    nodes, links = [], []
    node_ids = set()

    def add_node(nid, node):
        if nid not in node_ids:
            node_ids.add(nid)
            nodes.append(node)

    # 标签节点（大小 = 相关论文数开方）
    for tag, n in tag_count.items():
        add_node(f"t:{tag}", {
            "id": f"t:{tag}", "name": tag, "type": "tag",
            "value": n,
            "symbolSize": 14 + 10 * math.sqrt(n / max(tag_count.values())),
        })

    # 论文节点（精选评分前 MAX_GRAPH_PAPERS 篇）
    picked = sorted(papers, key=paper_score, reverse=True)[:MAX_GRAPH_PAPERS]
    for p in picked:
        add_node(f"p:{p['id']}", {
            "id": f"p:{p['id']}", "name": (p["title"] or "")[:45],
            "type": "paper", "value": p.get("cited_by_count") or 0,
            "year": p.get("year"), "doi": p.get("doi"), "journal": p.get("journal"),
            "core_journal": p.get("core_journal"),
            "symbolSize": 6 + 8 * paper_score(p),
        })
        for t in p.get("tags") or []:
            links.append({"source": f"p:{p['id']}", "target": f"t:{t}", "weight": 1})

    # 标签共现边（两个标签共同出现在同一篇论文 ≥ MIN_TAG_LINK 次）
    co = Counter()
    for p in papers:
        pt = set(p.get("tags") or [])
        for i, t1 in enumerate(pt):
            for t2 in list(pt)[i + 1:]:
                co[tuple(sorted((t1, t2)))] += 1
    for (t1, t2), n in co.items():
        if n >= MIN_TAG_LINK:
            links.append({"source": f"t:{t1}", "target": f"t:{t2}", "weight": n})

    return {"nodes": nodes, "links": links,
            "paper_nodes": len(picked), "tag_nodes": len(tag_count)}


def build_featured(papers):
    picked = sorted(papers, key=paper_score, reverse=True)[:9]
    out = []
    for p in picked:
        entry = {k: p[k] for k in ("id", "doi", "title", "journal", "year",
                                   "cited_by_count", "authors", "type", "tags",
                                   "core_journal", "url")}
        entry["classic"] = bool(p.get("classic"))
        out.append(entry)
    return out


def main():
    papers = load_papers()
    print(f"载入 {len(papers)} 篇文献")

    stats = build_stats(papers)
    with open(os.path.join(DATA_DIR, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)

    graph = build_graph(papers)
    with open(os.path.join(DATA_DIR, "graph.json"), "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=1)

    featured = build_featured(papers)
    with open(os.path.join(DATA_DIR, "featured.json"), "w", encoding="utf-8") as f:
        json.dump(featured, f, ensure_ascii=False, indent=1)

    print(f"stats.json:  {len(stats['by_year'])} 个年份, {len(stats['journals'])} 本期刊")
    print(f"graph.json:  {len(graph['nodes'])} 节点 ({graph['paper_nodes']} 论文 + {graph['tag_nodes']} 标签), "
          f"{len(graph['links'])} 条边")
    print(f"featured.json: {len(featured)} 篇精选")
    print("完成")


if __name__ == "__main__":
    main()
