# -*- coding: utf-8 -*-
"""
fetch_papers.py — 从 OpenAlex 抓取"碳材料超级电容器导电网络"领域文献
============================================================
- 纯标准库实现（urllib），Windows / Linux / GitHub Actions 均可直接运行
- 幂等合并：与已有 data/papers.json 合并，可反复运行（自动更新工作流每周调用）
- 数据源: OpenAlex (https://openalex.org) — 覆盖 WoS/Scopus/Crossref 的开放学术索引，
  以 DOI 为准；另有 scripts/import_wos.py 可直接导入 Web of Science 导出文件
用法:
    python scripts/fetch_papers.py [--limit N]
环境变量:
    OPENALEX_MAILTO  可选，填入邮箱可进入 polite pool 提高限流
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# Windows 控制台默认 GBK，统一 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "data", "papers.json")
API = "https://api.openalex.org/works"
MAILTO = os.environ.get("OPENALEX_MAILTO", "")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vocab import VOCAB, CORE_JOURNALS  # noqa: E402

# ---------------------------------------------------------------------------
# 检索式：每个查询单独请求（OpenAlex 过滤器内逗号 = OR，不适合拼多个搜索串）
# ---------------------------------------------------------------------------
QUERIES = [
    '"3D conductive network" supercapacitor',
    '"conductive network" supercapacitor carbon',
    '"3D graphene" supercapacitor electrode',
    '"3D porous" carbon supercapacitor',
    '"carbon nanotube" supercapacitor network electrode',
    '"carbon aerogel" supercapacitor',
    '"porous carbon" supercapacitor high rate performance',
    'graphene supercapacitor "rate performance" electrode',
    '"biomass-derived carbon" supercapacitor',
    '"carbon fiber" supercapacitor flexible electrode',
    '"hierarchical porous carbon" supercapacitor',
    '"free-standing" carbon electrode supercapacitor',
]

FROM_DATE = "2010-01-01"
PER_PAGE = 200
CLASSIC_PER_QUERY = 40   # 按被引排序取前 N（经典/高被引文献）
RECENT_PER_QUERY = 30    # 按日期排序取最新 N（近三年新文献）
RECENT_YEARS = 3
MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# 性能参数抽取正则（在摘要文本中取最大值）
# 权威期刊清单与受控词表见 vocab.py
# ---------------------------------------------------------------------------
RE_F_PER_G = re.compile(r"(\d{2,4}(?:\.\d+)?)\s*(?:F\s*g\s*[\-−–]\s*1|F/g)", re.I)
RE_WH_PER_KG = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:Wh\s*kg\s*[\-−–]\s*1|Wh/kg|Wh\s*kg[\-−–]1)", re.I)
RE_W_PER_KG = re.compile(r"(\d{2,6}(?:\.\d+)?)\s*W\s*kg\s*[\-−–]\s*1|(\d{2,6}(?:\.\d+)?)\s*W/kg", re.I)
RE_KW_PER_KG = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*kW\s*kg\s*[\-−–]\s*1|(\d{1,3}(?:\.\d+)?)\s*kW/kg", re.I)
RE_RETENTION = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*%\s*(?:of\s+)?(?:its\s+)?(?:initial\s+)?capacitance", re.I)


def log(msg):
    print(msg, flush=True)


def http_get_json(url):
    """带重试的 JSON GET 请求"""
    headers = {"User-Agent": f"carbon-supercap-site/1.0 ({MAILTO or 'anonymous'})"}
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            log(f"  [retry {attempt}/{MAX_RETRIES}] {e}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"request failed: {url} -> {last_err}")


# OpenAlex 的 type 字段对综述标注不可靠（大多为 article），
# 综述识别采用标题启发式（文献计量分析的标准做法）
REVIEW_TITLE_PATTERNS = [
    r"\breview\b", r"\boverview\b", r"\bprogress\b", r"\badvances?\b",
    r"\bperspectives?\b", r"\bchallenges?\b", r"\boutlook\b", r"\ba survey\b",
    r"\bstatus\b", r"\bstate[ \-]of[ \-]the[ \-]art\b", r"\bdevelopments?\b",
    r"\bfrontiers?\b", r"\blandscape\b",
]


def classify_type(work):
    """文献类型分类：优先 OpenAlex type，否则标题启发式"""
    if work.get("type") == "review":
        return "review"
    title = (work.get("title") or "").lower()
    if any(re.search(p, title) for p in REVIEW_TITLE_PATTERNS):
        return "review"
    return "article"


def reconstruct_abstract(inv_index):
    """由 abstract_inverted_index 还原摘要文本"""
    if not inv_index:
        return ""
    positioned = {}
    for word, positions in inv_index.items():
        for p in positions:
            positioned[p] = word
    return " ".join(positioned[p] for p in sorted(positioned))


def extract_metrics(abstract):
    """从摘要提取报道的性能数值（取最大值，单位统一为 F/g, Wh/kg, W/kg）"""
    def max_val(regex, lo, hi):
        best = None
        for m in regex.finditer(abstract):
            val = float(next(g for g in m.groups() if g))
            if lo <= val <= hi and (best is None or val > best):
                best = val
        return best

    metrics = {}
    fg = max_val(RE_F_PER_G, 50, 6000)
    if fg:
        metrics["f_per_g"] = fg
    wh = max_val(RE_WH_PER_KG, 1, 250)
    if wh:
        metrics["wh_per_kg"] = wh
    w = max_val(RE_W_PER_KG, 100, 200000)
    kw = max_val(RE_KW_PER_KG, 0.5, 500)
    w_candidates = [x for x in (w, kw * 1000 if kw else None) if x]
    if w_candidates:
        metrics["w_per_kg"] = max(w_candidates)
    if RE_RETENTION.search(abstract):
        metrics["has_retention"] = True
    return metrics


def tag_paper(text):
    """按受控词表打标签"""
    text_l = text.lower()
    tags = []
    for cn, category, patterns in VOCAB:
        for pat in patterns:
            if re.search(pat, text_l):
                tags.append(cn)
                break
    return tags


def work_to_entry(work):
    loc = work.get("primary_location") or {}
    source = loc.get("source") or {}
    journal = source.get("display_name") or "Unknown"
    jnorm = journal.lower().strip()
    core = any(jnorm == cj or jnorm.startswith(cj) for cj in CORE_JOURNALS)

    abstract = reconstruct_abstract(work.get("abstract_inverted_index"))
    if len(abstract) > 1600:
        abstract = abstract[:1600] + " …"
    text = (work.get("title") or "") + " " + abstract

    authors, institutions = [], []
    for a in work.get("authorships") or []:
        name = (a.get("author") or {}).get("display_name")
        if name and name not in authors and len(authors) < 6:
            authors.append(name)
        for inst in (a.get("institutions") or []):
            iname = inst.get("display_name")
            if iname and iname not in institutions and len(institutions) < 3:
                institutions.append(iname)

    doi = (work.get("doi") or "").replace("https://doi.org/", "")
    concepts = [c.get("display_name") for c in (work.get("concepts") or [])
                if (c.get("score") or 0) >= 0.35][:6]

    return {
        "id": work["id"].split("/")[-1],
        "doi": doi,
        "title": work.get("title") or "(无标题)",
        "journal": journal,
        "core_journal": core,
        "year": work.get("publication_year"),
        "date": work.get("publication_date") or "",
        "cited_by_count": work.get("cited_by_count") or 0,
        "authors": authors,
        "institutions": institutions,
        "type": classify_type(work),
        "oa": bool((work.get("open_access") or {}).get("is_oa")),
        "url": doi and f"https://doi.org/{doi}" or (loc.get("landing_page_url") or ""),
        "abstract": abstract,
        "tags": tag_paper(text),
        "metrics": extract_metrics(abstract),
        "concepts": concepts,
    }


def fetch_query(query, sort, per_page, n_keep, recent_cutoff=None):
    """执行一次查询，返回 (entries, 总数)"""
    params = {
        "filter": f"title_and_abstract.search:{query},type:article|review,from_publication_date:{FROM_DATE}",
        "sort": sort,
        "per-page": str(per_page),
    }
    if MAILTO:
        params["mailto"] = MAILTO
    url = API + "?" + urllib.parse.urlencode(params)
    data = http_get_json(url)
    out = []
    for w in data.get("results", []):
        if recent_cutoff and (w.get("publication_year") or 0) < recent_cutoff:
            continue
        out.append(work_to_entry(w))
        if len(out) >= n_keep:
            break
    return out, data.get("meta", {}).get("count", 0)


def load_existing():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def reclassify():
    """仅重新分类现有数据的综述类型（标题启发式），不重新抓取"""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        papers = json.load(f)
    n_rev = 0
    for p in papers:
        title = (p.get("title") or "").lower()
        if any(re.search(pat, title) for pat in REVIEW_TITLE_PATTERNS) and p["type"] != "review":
            p["type"] = "review"
            n_rev += 1
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=1)
    log(f"重新分类完成：{n_rev} 篇标记为综述，库中共 {len(papers)} 篇")


def main():
    if "--reclassify" in sys.argv:
        reclassify()
        return
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    now_year = datetime.now(timezone.utc).year
    recent_cutoff = now_year - RECENT_YEARS

    existing = load_existing()
    by_id = {p["id"]: p for p in existing}
    log(f"已有文献 {len(existing)} 篇，开始增量抓取…")

    for i, q in enumerate(QUERIES):
        log(f"[{i + 1}/{len(QUERIES)}] 查询: {q}")
        # 经典文献：按被引排序
        entries, n = fetch_query(q, "cited_by_count:desc", PER_PAGE, CLASSIC_PER_QUERY)
        log(f"   高被引: 取 {len(entries)} 篇 (命中 {n})")
        for e in entries:
            by_id[e["id"]] = e
        # 最新文献：按日期排序，仅保留近三年
        entries, n = fetch_query(q, "publication_date:desc", PER_PAGE, RECENT_PER_QUERY,
                                 recent_cutoff=recent_cutoff)
        log(f"   最新:   取 {len(entries)} 篇 (命中 {n})")
        for e in entries:
            by_id[e["id"]] = e
        time.sleep(0.4)
        if limit and (i + 1) * (CLASSIC_PER_QUERY + RECENT_PER_QUERY) >= limit:
            log("达到 --limit 上限，提前结束")
            break

    papers = list(by_id.values())
    # 主排序：核心期刊优先 → 被引降序
    papers.sort(key=lambda p: (not p["core_journal"], -(p["cited_by_count"] or 0), -(p["year"] or 0)))

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=1)

    n_core = sum(1 for p in papers if p["core_journal"])
    n_rev = sum(1 for p in papers if p["type"] == "review")
    n_tags = sum(1 for p in papers if p["tags"])
    log(f"完成：共 {len(papers)} 篇文献（核心期刊 {n_core}，综述 {n_rev}，已打标签 {n_tags}）")
    log(f"数据文件: {DATA_FILE}")


if __name__ == "__main__":
    main()
