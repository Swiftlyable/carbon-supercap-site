# -*- coding: utf-8 -*-
"""
import_wos.py — Web of Science / JCR 数据导入与校准
====================================================
用法:
    python scripts/import_wos.py --citations savedrecs1.txt [savedrecs2.txt ...]
        # 解析 WoS「制表符分隔文件 (Win) → 完整记录」导出，按 DOI 提取被引次数
    python scripts/import_wos.py --jcr jcr.xlsx [或 jcr.csv]
        # 解析 Journal Citation Reports 导出表（期刊名/ISSN/JIF/分区）
    python scripts/import_wos.py --apply
        # 仅把 data/wos_overlay.json 应用到 data/papers.json（工作流每周调用）

数据流:
    导入命令 → data/wos_overlay.json（持久覆盖层，随仓库提交）
             → 应用：papers.json 的 cited_by_count / core_journal / jcr_quartile / jif
每周自动更新会重新抓取 OpenAlex 数据，随后工作流自动 --apply 恢复 WoS 校准值，
因此 WoS 数据不会被冲掉。原始 savedrecs 导出文件放在 wos_export/（已 gitignore，
WoS 许可不允许公开再分发）。

分区口径: 一本期刊在 JCR 多个学科各有分区时取最佳（Q 编号最小）分区。
core_journal: 期刊在 JCR 表中有分区 → Q1 才为 True（站内标签即「WoS/JCR Q1」）；
期刊不在 JCR 表中（如未被 SCIE 收录）→ 保留原值（vocab.py 硬编码清单兜底）。
"""

import csv
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
PAPERS_FILE = os.path.join(DATA_DIR, "papers.json")
CLASSICS_FILE = os.path.join(DATA_DIR, "classics.json")
OVERLAY_FILE = os.path.join(DATA_DIR, "wos_overlay.json")

# 期刊名归一化：小写去除非字母数字（"Journal of Materials Chemistry A"
# 与 "JOURNAL OF MATERIALS CHEMISTRY A" 归一后相同）
JOURNAL_ALIASES = {
    "procnatlacadsciusa": "proceedingsofthenationalacademyofsciencesoftheunitedstatesofamerica",
    "pnas": "proceedingsofthenationalacademyofsciencesoftheunitedstatesofamerica",
    "jamchemsoc": "journaloftheamericanchemicalsociety",
    "angewcheminted": "angewandtechemieinternationaledition",
}


def log(msg):
    print(msg, flush=True)


def norm_journal(s):
    n = re.sub(r"[^a-z0-9]+", "", (s or "").lower())
    return JOURNAL_ALIASES.get(n, n)


# ---------------------------------------------------------------------------
# WoS savedrecs 解析（字段标记式：PT/AU/TI/DI/TC/...）
# ---------------------------------------------------------------------------

def parse_wos_fields(text):
    """解析 WoS 字段标记格式（每行以两字符字段名 + 空格开头，续行为前导空格）"""
    records, cur = [], None
    for raw in text.splitlines():
        if not raw:
            continue
        # 字段标记行：两位大写字母/数字开头，后面跟空格或行就到此结束
        # （ER/EF 等标记行只有两位字符、无尾随空格，须单独兼容）
        if len(raw) >= 2 and raw[:2].isalnum() and raw[:2].isupper() \
                and (len(raw) == 2 or raw[2] == " "):
            tag, val = raw[:2], raw[3:].strip()
            if tag == "ER":  # 记录结束
                if cur:
                    records.append(cur)
                cur = None
            elif tag in ("FN", "VR", "EF"):  # 文件头/尾标记，忽略
                continue
            elif tag == "PT":  # 新记录开始，先保存上一条
                if cur:
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


def extract_citations_from_savedrecs(text):
    """savedrecs → {doi_lower: 被引次数}（优先 TC，缺失时用 Z9）"""
    out = {}
    for r in parse_wos_fields(text):
        doi = (r.get("DI") or "").strip().lower()
        if not doi:
            continue
        for tag in ("TC", "Z9"):
            v = (r.get(tag) or "").strip()
            if v.isdigit():
                out[doi] = int(v)
                break
    return out


# WoS 有时导出「Excel」格式（实为 HTML 表格），兜底解析
def extract_citations_from_html(text):
    """HTML 表格 savedrecs → {doi_lower: 被引次数}"""
    out = {}
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I)
    header, di_idx, tc_idx = None, None, None
    for row in rows:
        cells = [re.sub(r"<[^>]+>", "", c).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]
        if not cells:
            continue
        if header is None:
            header = [c.upper() for c in cells]
            if "DI" in header:
                di_idx = header.index("DI")
            tc_idx = header.index("TC") if "TC" in header else (
                header.index("Z9") if "Z9" in header else None)
            continue
        if di_idx is not None and di_idx < len(cells):
            doi = cells[di_idx].strip().lower()
            if doi and tc_idx is not None and tc_idx < len(cells) and cells[tc_idx].strip().isdigit():
                out[doi] = int(cells[tc_idx].strip())
    return out


# ---------------------------------------------------------------------------
# JCR 导出解析（xlsx / csv）
# ---------------------------------------------------------------------------

XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _col_index(ref):
    """'AA7' → 26（列号从 0 计）；无单元格坐标时返回 None"""
    m = re.match(r"[A-Z]+", ref or "")
    if not m:
        return None
    n = 0
    for ch in m.group(0):
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def _parse_sheet(xml_bytes, shared):
    root = ET.fromstring(xml_bytes)
    rows = []
    for row in root.iter(f"{{{XLSX_NS}}}row"):
        cells = {}
        for c in row.iter(f"{{{XLSX_NS}}}c"):
            ci = _col_index(c.get("r") or "")
            if ci is None:
                continue
            t = c.get("t")
            v = c.find(f"{{{XLSX_NS}}}v")
            if t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(f"{{{XLSX_NS}}}t"))
            elif t == "s" and v is not None:
                idx = int(v.text)
                val = shared[idx] if 0 <= idx < len(shared) else ""
            else:
                val = v.text if v is not None else ""
            cells[ci] = val or ""
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
    return rows


def read_xlsx(path):
    """读 xlsx → [{表头: 值}, ...]（自动定位含期刊名的表）"""
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.iter(f"{{{XLSX_NS}}}si"):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{XLSX_NS}}}t")))
        sheets = sorted(n for n in z.namelist()
                        if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        candidates = []
        for name in sheets:
            rows = _parse_sheet(z.read(name), shared)
            if rows:
                candidates.append(rows)
    if not candidates:
        raise RuntimeError("xlsx 中没有工作表数据")

    best_rows, best_score = candidates[0], -1
    for rows in candidates:
        score = 0
        for row in rows[:5]:
            joined = " ".join(str(c) for c in row).lower()
            if "journal" in joined or "期刊" in joined:
                score += 1
        if score > best_score:
            best_rows, best_score = rows, score

    header = [str(c).strip() for c in best_rows[0]]
    return [{header[i]: c for i, c in enumerate(row) if i < len(header)}
            for row in best_rows[1:]]


def read_jcr_table(path):
    """读 JCR 导出（xlsx/csv）→ 行字典列表"""
    if path.lower().endswith(".csv"):
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            rows = list(csv.DictReader(f))
        if rows:
            return rows
        raise RuntimeError("csv 为空或表头无法识别")
    return read_xlsx(path)


def _find_col(header, keys):
    """按子串找列名（精确匹配优先，忽略大小写）"""
    hl = {h.strip().lower(): h for h in header if h.strip()}
    for key in keys:
        if key in hl:
            return hl[key]
    for key in keys:
        for h in hl:
            if key in h:
                return hl[h]
    return None


def parse_jcr(path):
    """JCR 表 → {归一化期刊名: {name, issn, quartile, jif}}（多学科取最佳分区）"""
    rows = read_jcr_table(path)
    header = list(rows[0].keys()) if rows else []
    if not header:
        raise RuntimeError("JCR 表为空")

    col_name = _find_col(header, ["journal name", "期刊名称", "journal title"])
    col_issn = _find_col(header, ["issn", "eissn"])
    col_q = _find_col(header, ["jif quartile", "quartile", "分区"])
    col_jif = _find_col(header, ["journal impact factor", "jif", "影响因子"])
    if not col_name:
        raise RuntimeError(f"未找到期刊名列（现有列：{', '.join(header[:12])}）")
    log(f"识别列: 期刊={col_name}, ISSN={col_issn}, 分区={col_q}, JIF={col_jif}")

    journals = {}
    for row in rows:
        name = str(row.get(col_name) or "").strip()
        if not name:
            continue
        key = norm_journal(name)
        jif, quartile = None, None
        if col_jif:
            v = str(row.get(col_jif) or "").strip()
            m = re.search(r"\d+(?:\.\d+)?", v.replace(",", ""))
            if m and float(m.group()) > 0:
                jif = float(m.group())
        if col_q:
            m = re.search(r"Q([1-4])", str(row.get(col_q) or ""), re.I)
            if m:
                quartile = f"Q{m.group(1)}"
        cur = journals.get(key)
        if cur is None:
            journals[key] = {
                "name": name, "issn": str(row.get(col_issn) or "").strip() or None,
                "quartile": quartile, "jif": jif,
            }
        else:
            if jif and not cur["jif"]:
                cur["jif"] = jif
            # 取最佳分区（Q1 最好）
            if quartile and (not cur["quartile"] or int(quartile[1]) < int(cur["quartile"][1])):
                cur["quartile"] = quartile
    return journals


# ---------------------------------------------------------------------------
# 覆盖层与应用
# ---------------------------------------------------------------------------

def load_overlay():
    if os.path.exists(OVERLAY_FILE):
        with open(OVERLAY_FILE, "r", encoding="utf-8") as f:
            ov = json.load(f)
        return {
            "citations": {str(k).lower(): v for k, v in (ov.get("citations") or {}).items()},
            "journals": ov.get("journals") or {},
        }
    return {"citations": {}, "journals": {}}


def save_overlay(ov):
    with open(OVERLAY_FILE, "w", encoding="utf-8") as f:
        json.dump(ov, f, ensure_ascii=False, indent=1)


def apply_overlay():
    """把 wos_overlay.json 应用到 papers.json（幂等，可反复运行）"""
    papers = []
    with open(PAPERS_FILE, "r", encoding="utf-8") as f:
        papers = json.load(f)
    ov = load_overlay()
    cites = ov["citations"]
    jtbl = ov["journals"]

    n_cite = n_jif = n_core_change = n_match = 0
    for p in papers:
        doi = (p.get("doi") or "").strip().lower()
        if doi and doi in cites:
            n_match += 1
            if p.get("cited_by_count") != cites[doi]:
                p["cited_by_count"] = cites[doi]
                n_cite += 1
        j = jtbl.get(norm_journal(p.get("journal") or ""))
        if j:
            if j.get("jif") is not None:
                p["jif"] = j["jif"]
                n_jif += 1
            if j.get("quartile"):
                p["jcr_quartile"] = j["quartile"]
                new_core = j["quartile"] == "Q1"
                if p.get("core_journal") != new_core:
                    p["core_journal"] = new_core
                    n_core_change += 1
            # 期刊在 JCR 表中但无分区（如 ESCI）→ 保持原 core_journal

    papers.sort(key=lambda p: (not p.get("core_journal"),
                               -(p.get("cited_by_count") or 0), -(p.get("year") or 0)))
    with open(PAPERS_FILE, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=1)

    # classics.json 同步校准（按 id 回填被引/分区）
    n_cls = 0
    if os.path.exists(CLASSICS_FILE):
        with open(CLASSICS_FILE, "r", encoding="utf-8") as f:
            classics = json.load(f)
        by_id = {p["id"]: p for p in papers}
        for c in classics:
            p = by_id.get(c.get("id"))
            if not p:
                continue
            changed = False
            for k in ("cited_by_count", "core_journal", "jcr_quartile", "jif"):
                if p.get(k) is not None and c.get(k) != p[k]:
                    c[k] = p[k]
                    changed = True
            if changed:
                n_cls += 1
        with open(CLASSICS_FILE, "w", encoding="utf-8") as f:
            json.dump(classics, f, ensure_ascii=False, indent=1)

    log(f"覆盖层应用完成：被引更新 {n_cite} 篇（DOI 命中 {n_match}），"
        f"JIF 写入 {n_jif} 篇，Q1 判定变更 {n_core_change} 篇，经典文献同步 {n_cls} 条")
    return n_match


def import_citations(paths):
    ov = load_overlay()
    cites = ov["citations"]
    total = 0
    for path in paths:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        if re.search(r"<html", text, re.I):
            got = extract_citations_from_html(text)
        else:
            got = extract_citations_from_savedrecs(text)
        log(f"  {path}: 解析到 {len(got)} 条 DOI+被引")
        for doi, tc in got.items():
            cites[doi] = max(cites.get(doi, 0), tc)
        total += len(got)
    ov["citations"] = cites
    save_overlay(ov)
    log(f"覆盖层 citations 共 {len(cites)} 条（本次处理 {total} 条）")
    return total


def import_jcr(path):
    journals = parse_jcr(path)
    ov = load_overlay()
    merged = {**ov["journals"], **journals}
    ov["journals"] = merged
    save_overlay(ov)
    q1 = sum(1 for j in merged.values() if j.get("quartile") == "Q1")
    withjif = sum(1 for j in merged.values() if j.get("jif"))
    log(f"JCR 期刊 {len(journals)} 本 → 覆盖层 journals 共 {len(merged)} 本"
        f"（Q1 {q1}，有 JIF {withjif}）")
    return len(journals)


def main():
    args = sys.argv[1:]
    if "--apply" in args:
        apply_overlay()
        return
    if "--citations" in args:
        i = args.index("--citations")
        paths = args[i + 1:]
        paths = [a for a in paths if not a.startswith("--")]
        if not paths:
            print("用法: python scripts/import_wos.py --citations savedrecs1.txt [savedrecs2.txt ...]")
            sys.exit(1)
        import_citations(paths)
    elif "--jcr" in args:
        i = args.index("--jcr")
        if i + 1 >= len(args):
            print("用法: python scripts/import_wos.py --jcr jcr.xlsx")
            sys.exit(1)
        import_jcr(args[i + 1])
    else:
        print(__doc__)
        sys.exit(0)
    apply_overlay()


if __name__ == "__main__":
    main()
