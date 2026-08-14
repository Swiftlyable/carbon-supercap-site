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
import re
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
            "zh_title": p.get("zh_title") or "",
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
        entry["zh_title"] = p.get("zh_title") or ""
        entry["classic"] = bool(p.get("classic"))
        out.append(entry)
    return out


def build_latest(papers):
    """首页「最新文献」板块：按发表日期倒序取前 6 篇"""
    picked = sorted(papers,
                    key=lambda p: (p.get("date") or "", p.get("year") or 0),
                    reverse=True)[:6]
    out = []
    for p in picked:
        entry = {k: p[k] for k in ("id", "doi", "title", "journal", "year",
                                   "cited_by_count", "authors", "type", "tags",
                                   "core_journal", "url")}
        entry["zh_title"] = p.get("zh_title") or ""
        entry["classic"] = bool(p.get("classic"))
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# 知识脉络叶子节点 → 代表论文匹配规则
# 每个叶子节点给出「受控词表标签 + 英文正则（检索标题+摘要）」，
# 命中任一条计 1 分，按 得分 → 权威期刊 → 被引次数 排序取前 3 篇。
# ---------------------------------------------------------------------------
NODE_PAPER_RULES = {
    # 储能机理基础
    "双电层电容 (EDLC)": {"tags": [], "re": [r"\bEDLC\b", r"electric\w*\s+double[\s-]?layer",
                                              r"electrochemical\s+double[\s-]?layer"]},
    "赝电容": {"tags": [], "re": [r"pseudocapacit"]},
    "混合/非对称器件": {"tags": ["非对称器件"], "re": [r"hybrid\s+supercapacitor", r"battery[\s-]type"]},
    # 碳材料体系（按维度）
    "0D 碳材料": {"tags": ["活性炭 AC", "炭黑 CB", "碳点"], "re": []},
    "1D 碳材料": {"tags": ["碳纳米管 CNT", "碳纤维/织物"], "re": []},
    "2D 碳材料": {"tags": ["石墨烯", "氧化石墨烯 GO/rGO"], "re": []},
    "3D 碳材料": {"tags": ["碳气凝胶", "泡沫碳", "多孔碳"], "re": []},
    # 导电网络的维度工程
    "0D 点接触网络": {"tags": ["炭黑 CB"], "re": [r"conductive\s+additive"]},
    "1D 线接触网络": {"tags": ["碳纳米管 CNT", "碳纤维/织物"], "re": [r"percolat"]},
    "2D 面接触网络": {"tags": ["石墨烯", "氧化石墨烯 GO/rGO"],
                       "re": [r"freestanding\s+(?:film|membrane)", r"paper[\s-]like"]},
    "连续电子通道": {"tags": [], "re": [r"\binterconnected\b", r"conductive\s+(?:pathway|network|skeleton)",
                                        r"electron\s+transport"]},
    "分级多孔离子通道": {"tags": ["多孔碳"], "re": [r"hierarchic"]},
    "抑制 2D 堆叠": {"tags": ["石墨烯", "氧化石墨烯 GO/rGO"], "re": [r"restack", r"re[\s-]stack", r"aggregation"]},
    "高负载面电容": {"tags": ["面电容"], "re": [r"mass\s+loading", r"thick\s+electrode"]},
    "柔性与结构稳定": {"tags": ["柔性器件"], "re": [r"compressib", r"mechanical"]},
    # 3D 导电网络构建策略
    "CVD 直接生长": {"tags": ["CVD 生长"], "re": []},
    "模板法": {"tags": ["模板法", "冷冻干燥/冰模板"], "re": []},
    "自组装": {"tags": ["自组装", "水热/溶剂热"], "re": []},
    "静电纺丝": {"tags": ["静电纺丝"], "re": []},
    "3D 打印 (DIW)": {"tags": ["3D 打印"], "re": []},
    "焊接/交联": {"tags": ["焊接/交联"], "re": []},
    "生物质碳化活化": {"tags": ["生物质碳", "化学活化"], "re": [r"carboniz", r"pyrolysi"]},
    # 关键性能指标
    "比电容": {"tags": ["比电容"], "re": []},
    "倍率性能": {"tags": ["倍率性能"], "re": []},
    "循环稳定性": {"tags": ["循环稳定性"], "re": []},
    "能量/功率密度": {"tags": ["能量密度", "功率密度"], "re": []},
    "面电容（高负载）": {"tags": ["面电容"], "re": [r"mass\s+loading", r"high\s+loading"]},
    # 典型应用
    "柔性/可穿戴电子": {"tags": ["柔性器件", "可穿戴"], "re": []},
    "微型超级电容器": {"tags": ["微型超级电容器 MSC"], "re": []},
    "结构储能": {"tags": [], "re": [r"structural\s+(?:supercapacitor|electrode|energy\s+storage|battery|composite)",
                                     r"load[\s-]bearing"]},
    "电网储能/功率补偿": {"tags": [], "re": [r"\bgrid\b", r"regenerative\s+braking",
                                               r"power\s+(?:compensation|buffer|fluctuation)", r"frequency\s+regulation"]},
    # 前沿方向
    "机器学习辅助设计": {"tags": [], "re": [r"machine\s+learning", r"deep\s+learning", r"neural\s+network",
                                              r"random\s+forest", r"data[\s-]driven"]},
    "高熵/多元掺杂碳": {"tags": ["杂原子掺杂"], "re": [r"co[\s-]dop", r"multi[\s-]heteroatom", r"high[\s-]entropy"]},
    "器件构型创新": {"tags": ["纤维状器件"], "re": [r"fiber[\s-]shaped", r"yarn[\s-]shaped",
                                                     r"transparent\s+(?:supercapacitor|electrode)", r"self[\s-]heal", r"stretchab"]},
    "极端环境适用": {"tags": [], "re": [r"low[\s-]temperature", r"high[\s-]temperature",
                                         r"extreme\s+environment", r"subzero"]},
}


def build_mindmap_papers(papers):
    """按 taxonomy.json 的叶子节点匹配代表论文（每节点最多 3 篇）"""
    with open(os.path.join(DATA_DIR, "taxonomy.json"), "r", encoding="utf-8") as f:
        taxonomy = json.load(f)

    def collect_leaves(node, leaves):
        children = node.get("children") or []
        if children:
            for c in children:
                collect_leaves(c, leaves)
        else:
            leaves.append(node["name"])

    leaves = []
    collect_leaves(taxonomy, leaves)

    matched = {name: [] for name in leaves}
    for p in papers:
        hay = f'{p.get("title") or ""} {p.get("abstract") or ""}'.lower()
        ptags = set(p.get("tags") or [])
        for name in leaves:
            rule = NODE_PAPER_RULES.get(name)
            if not rule:
                continue
            score = sum(1 for t in rule["tags"] if t in ptags)
            score += sum(1 for rx in rule["re"] if re.search(rx, hay))
            if score > 0:
                matched[name].append((score, p))

    def quality(score, p):
        """质量优先：权威期刊加分 + 被引对数主排序，匹配得分仅在近同量级内倾斜"""
        cited = p.get("cited_by_count") or 0
        return math.log10(cited + 1) + (0.8 if p.get("core_journal") else 0) + 0.15 * score

    out = {}
    empty = []
    for name, items in matched.items():
        items.sort(key=lambda sp: quality(sp[0], sp[1]), reverse=True)
        out[name] = [
            {k: p.get(k) for k in ("title", "zh_title", "journal", "year",
                                   "cited_by_count", "core_journal", "doi", "url")}
            for _, p in items[:3]
        ]
        if not out[name]:
            empty.append(name)

    if empty:
        print(f"⚠ 以下叶子节点未匹配到论文：{', '.join(empty)}")
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

    latest = build_latest(papers)
    with open(os.path.join(DATA_DIR, "latest.json"), "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=1)

    mindmap = build_mindmap_papers(papers)
    with open(os.path.join(DATA_DIR, "mindmap_papers.json"), "w", encoding="utf-8") as f:
        json.dump({"last_updated": stats["last_updated"], "papers": mindmap},
                  f, ensure_ascii=False, indent=1)

    print(f"stats.json:  {len(stats['by_year'])} 个年份, {len(stats['journals'])} 本期刊")
    print(f"graph.json:  {len(graph['nodes'])} 节点 ({graph['paper_nodes']} 论文 + {graph['tag_nodes']} 标签), "
          f"{len(graph['links'])} 条边")
    print(f"featured.json: {len(featured)} 篇精选")
    print(f"latest.json: {len(latest)} 篇最新")
    n_papers = sum(len(v) for v in mindmap.values())
    print(f"mindmap_papers.json: {len(mindmap)} 个叶子节点, 共 {n_papers} 篇代表论文")
    print("完成")


if __name__ == "__main__":
    main()
