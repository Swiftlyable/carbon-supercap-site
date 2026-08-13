# -*- coding: utf-8 -*-
"""
translate_papers.py — 论文标题/摘要中文化（英文 → 中文）
============================================================
- 调用 Google 翻译 gtx 公开端点（无需密钥），纯标准库实现
- 幂等：只翻译缺失 zh_title / zh_abstract 的条目，每 25 条增量保存，
  中断后重跑自动续传
- 翻译失败（限流/断网）自动重试 3 次，仍失败则跳过（保留英文原题），
  下次运行继续补译
- 设计目标：GitHub Actions 每周更新流水线中运行（美国机房可达 Google），
  新文献入库后自动获得中文标题/摘要
用法:
    python scripts/translate_papers.py [--limit N]
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "data", "papers.json")

ENDPOINT = ("https://translate.googleapis.com/translate_a/single"
            "?client=gtx&sl=en&tl=zh-CN&dt=t&q={q}")
MAX_RETRIES = 3
SLEEP_BETWEEN = 0.3          # 每次请求间隔（秒）
SAVE_EVERY = 25              # 每翻译 N 条保存一次（断点续传）
MIN_ABSTRACT_LEN = 40        # 摘要过短（无实质内容）不翻译
TAG_RE = re.compile(r"<[^>]+>")


def log(msg):
    print(msg, flush=True)


def translate(text):
    """翻译一段英文 → 中文；失败返回 None"""
    clean = TAG_RE.sub("", text).strip()  # 标题可能混入 <i>/<sub> 标签
    if not clean:
        return None
    url = ENDPOINT.format(q=urllib.parse.quote(clean[:4000]))
    headers = {"User-Agent": "Mozilla/5.0 (carbon-supercap-site translator)"}
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            parts = [seg[0] for seg in data[0] if seg and seg[0]]
            zh = "".join(parts).strip()
            if zh:
                return zh
            last_err = RuntimeError("empty translation")
        except Exception as e:
            last_err = e
            time.sleep(2 * attempt)
    log(f"    [翻译失败] {clean[:50]}... -> {last_err}")
    return None


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        papers = json.load(f)

    # 待翻译队列：标题 + 摘要（仅当有足够长的英文摘要且尚无中文）
    todo = []
    for p in papers:
        if not p.get("zh_title"):
            todo.append((p, "title"))
        abstract = (p.get("abstract") or "").strip()
        if abstract and len(abstract) >= MIN_ABSTRACT_LEN and not p.get("zh_abstract"):
            todo.append((p, "abstract"))

    log(f"共 {len(papers)} 篇文献，待翻译 {len(todo)} 项（标题+摘要）")
    if limit:
        todo = todo[:limit]
        log(f"--limit {limit}：本次只处理前 {len(todo)} 项")

    done, failed = 0, 0
    for i, (p, kind) in enumerate(todo):
        src = p["title"] if kind == "title" else p["abstract"]
        zh = translate(src)
        if zh:
            p[f"zh_{kind}"] = zh
            done += 1
        else:
            failed += 1
        if (i + 1) % SAVE_EVERY == 0:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(papers, f, ensure_ascii=False, indent=1)
            log(f"  已保存进度 {i + 1}/{len(todo)}（成功 {done}，失败 {failed}）")
        time.sleep(SLEEP_BETWEEN)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=1)

    n_title = sum(1 for p in papers if p.get("zh_title"))
    n_abs = sum(1 for p in papers if p.get("zh_abstract"))
    log(f"完成：本次成功 {done}，失败 {failed}；库中已有中文标题 {n_title}、中文摘要 {n_abs}")


if __name__ == "__main__":
    main()
