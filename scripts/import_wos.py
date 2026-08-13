# -*- coding: utf-8 -*-
"""
import_wos.py — 导入 Web of Science 导出文件（savedrecs.txt）
============================================================
用法:
    python scripts/import_wos.py 路径/to/savedrecs.txt [更多文件...]

说明:
- 支持 WoS「制表符分隔文件 (Win, UTF-8) → 全记录」格式（字段标记式：PT/AU/TI/...）
- 按 DOI 与现有 data/papers.json 去重合并；无 DOI 的按标题小写去重
- 导入记录标记 source="WoS"，weekly 自动更新不会被覆盖（增量合并逻辑保留）
- 导入后请运行 python scripts/build_data.py 重新生成统计与关系图
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vocab import VOCAB, CORE_JOURNALS  # noqa: E402
from fetch_papers import extract_metrics, tag_paper  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPERS_FILE = os.path.join(BASE_DIR, "data", "papers.json")

# WoS 文献类型 → 本站类型
DT_MAP = {"Article": "article", "Review": "review", "Article; Proceedings Paper": "article"}


def parse_wos_fields(text):
    """解析 WoS 字段标记格式（每行以两字符字段名 + 空格开头，续行为前导空格）"""
    records, cur = [], None
    for raw in text.splitlines():
        if not raw:
            continue
        if len(raw) >= 3 and raw[2] == " " and raw[:2].isalpha() and raw[0:2].isupper():
            tag, val = raw[:2], raw[3:].strip()
            if tag == "ER":  # 记录结束
                if cur:
                    records.append(cur)
                cur = None
            elif tag == "PT" and cur is not None:  # 意外新记录开始，先保存
                records.append(cur)
                cur = {tag: val}
            else:
                if cur is None:
                    cur = {}
                cur[tag] = (cur.get(tag, "") + " " + val).strip()
        elif cur is not None:
            # 续行
            last = next(reversed(cur)) if cur else None
            if last:
                cur[last] = cur[last] + " " + raw.strip()
    if cur:
        records.append(cur)
    return records


def parse_authors(au_field):
    """AU: 'Lastname, Firstname; Lastname2, Firstname2' → ['Firstname Lastname', ...]"""
    out = []
    for part in (au_field or "").split(";"):
        part = part.strip()
        if not part:
            continue
        if "," in part:
            last, _, first = part.partition(",")
            out.append(f"{first.strip()} {last.strip()}".strip())
        else:
            out.append(part)
    return out


def wos_to_entry(r):
    doi = (r.get("DI") or "").strip()
    title = (r.get("TI") or "无标题").strip()
    journal = (r.get("SO") or "Unknown").strip()
    year = int(r["PY"]) if r.get("PY", "").strip().isdigit() else None
    abstract = (r.get("AB") or "")[:1600]
    text = title + " " + abstract
    jnorm = journal.lower().strip()

    entry = {
        "id": f"wos-{abs(hash(doi or title.lower()))}",
        "doi": doi,
        "title": title,
        "journal": journal,
        "core_journal": any(jnorm == cj or jnorm.startswith(cj) for cj in CORE_JOURNALS),
        "year": year,
        "date": (r.get("PY") or "") + "-01-01",
        "cited_by_count": int(r["TC"]) if r.get("TC", "").strip().isdigit() else 0,
        "authors": parse_authors(r.get("AU"))[:6],
        "institutions": [],
        "type": DT_MAP.get((r.get("DT") or "").strip(), "article"),
        "oa": False,
        "url": doi and f"https://doi.org/{doi}" or "",
        "abstract": abstract,
        "tags": tag_paper(text),
        "metrics": extract_metrics(abstract),
        "concepts": [],
        "source": "WoS",
        "wos_id": (r.get("UT") or "").strip(),  # WoS 入藏号
    }
    return entry


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/import_wos.py savedrecs1.txt [savedrecs2.txt ...]")
        sys.exit(1)

    existing = []
    if os.path.exists(PAPERS_FILE):
        with open(PAPERS_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
    papers = {p["id"]: p for p in existing}
    by_doi = {p["doi"].lower(): p for p in existing if p.get("doi")}
    by_title = {p["title"].lower(): p for p in existing if p.get("title")}

    total, added, merged = 0, 0, 0
    for path in sys.argv[1:]:
        print(f"解析 {path} …")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            records = parse_wos_fields(f.read())
        print(f"  找到 {len(records)} 条记录")
        for r in records:
            total += 1
            entry = wos_to_entry(r)
            key = entry["doi"].lower() if entry["doi"] else ""
            target = by_doi.get(key) or (by_title.get(entry["title"].lower()) if not key else None)
            if target:
                # 合并：保留 OpenAlex 摘要/概念，补充 WoS 来源标记与被引取大值
                target["source"] = "WoS"
                target["wos_id"] = entry.get("wos_id") or target.get("wos_id", "")
                target["cited_by_count"] = max(target.get("cited_by_count") or 0,
                                               entry["cited_by_count"])
                merged += 1
            else:
                papers[entry["id"]] = entry
                by_doi[key] = entry
                by_title[entry["title"].lower()] = entry
                added += 1

    papers = sorted(papers.values(),
                    key=lambda p: (not p["core_journal"], -(p["cited_by_count"] or 0)))
    with open(PAPERS_FILE, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=1)

    print(f"完成：解析 {total} 条 → 新增 {added} 篇，合并更新 {merged} 篇，库中共 {len(papers)} 篇")
    print("下一步：python scripts/build_data.py")


if __name__ == "__main__":
    main()
