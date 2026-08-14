/* ============================================================
   assistant.js — AI 文献助手（文献库页）
   ------------------------------------------------------------
   检索（RAG）：在浏览器本地对文献库（标题/摘要/标签）加权打分，
              取最相关 5 篇作为上下文 —— 文献数据不出你的浏览器。
   生成（LLM）：硅基流动 SiliconFlow（OpenAI 兼容接口），
              默认免费模型 Qwen2.5-7B / GLM-4-9B。
   安全（BYOK）：API Key 仅保存在浏览器 localStorage，
              提问时由浏览器直连 api.siliconflow.cn（HTTPS），
              不经任何中间服务器、不提交代码仓库；
              模型输出一律先 HTML 转义再渲染，杜绝注入。
   ============================================================ */
"use strict";

const AI_KEY = "scnet-ai-key";
const AI_MODEL = "scnet-ai-model";
const AI_API = "https://api.siliconflow.cn/v1/chat/completions";
const AI_DEFAULT_MODEL = "Qwen/Qwen3-8B";
const AI_MODELS = [
  ["Qwen/Qwen3-8B", "通义千问 Qwen3-8B（免费，推荐）"],
  ["Qwen/Qwen2.5-7B-Instruct", "通义千问 Qwen2.5-7B（免费）"],
  ["__custom__", "自定义模型（手动输入 ID）"],
];
// 已被平台下线/更名的旧模型 ID：保存了这些值就自动回退默认
const AI_DEPRECATED = new Set(["THUDM/glm-4-9b-chat", "deepseek-ai/DeepSeek-V3"]);

const AI_SYSTEM = [
  "你是「碳网图谱 CarbonNet」网站的 AI 文献助手，该站专注碳材料超级电容器三维导电网络研究。",
  "用户会提供若干条【参考文献】。回答规则：",
  "1. 优先基于文献内容回答，引用处标注 [编号]（如 [1]；同时适用多个编号时合并为 [1,3]）；",
  "2. 文献未覆盖的部分可基于通用知识补充，但须在相关语句后标注（通用知识）；",
  "3. 禁止编造文献、数据或引用不存在的编号；",
  "4. 使用提问者的语言回答；",
  "5. 简洁专业，可用小标题、列表，总长度不超过 600 字；",
  "6. 禁止重复输出相同的字、词或句子，禁止无意义地重复字符；",
  "7. 若参考文献与问题相关性弱，直接说明并给出简短建议，不要强行展开。",
].join("\n");

/* ---------- 本地检索（RAG） ---------- */

const EN_STOP = new Set([
  "of", "the", "and", "in", "on", "to", "by", "for", "with", "via",
  "using", "based", "from", "their", "its", "are", "was", "were", "been",
  "into", "that", "this", "these", "those",
]);

function zhGrams(run) {
  if (run.length <= 4) return [run];
  const out = [];
  for (let i = 0; i + 2 <= run.length; i++) out.push(run.slice(i, i + 2));
  return out;
}

function wordTokens(s) {
  const lower = s.toLowerCase();
  const set = new Set();
  // 英文/数字词元（过滤纯功能词）
  (lower.match(/[a-z0-9][a-z0-9-]{1,}/g) || []).forEach((t) => {
    if (!EN_STOP.has(t)) set.add(t);
  });
  // 中文：短串整体匹配，长串拆为 2-gram（对子串命中也有一定召回）
  (lower.match(/[一-鿿]+/g) || []).forEach((run) => {
    zhGrams(run).forEach((g) => set.add(g));
  });
  return set;
}

function tokenize(q) {
  const full = q.trim().toLowerCase();
  return { full, tokens: [...wordTokens(full)] };
}

let _idf = null;

// 文献库词元文档频率（IDF）：只在首次提问时构建一次
// 目的：让「machine learning」这类稀有词压过 design/performance 等泛词
function idfFor(papers) {
  if (_idf) return _idf;
  const df = {};
  for (const p of papers) {
    const seen = new Set();
    for (const f of [p.title, p.zh_title, p.abstract, p.zh_abstract, (p.tags || []).join(" ")]) {
      if (!f) continue;
      wordTokens(f).forEach((t) => {
        if (!seen.has(t)) { seen.add(t); df[t] = (df[t] || 0) + 1; }
      });
    }
  }
  const N = papers.length;
  _idf = {};
  for (const t in df) _idf[t] = Math.min(8, Math.log(1 + N / (1 + df[t])));
  return _idf;
}

function scorePaper(p, q, idf) {
  // 字段权重：标题 > 标签 > 摘要 > 期刊
  const fields = [
    [p.title, 3], [p.zh_title, 3], [(p.tags || []).join(" "), 2],
    [p.abstract, 1], [p.zh_abstract, 1], [p.journal, 0.5],
  ];
  const lower = (f) => (f ? f.toLowerCase() : "");
  let s = 0;
  // 完整查询串命中（高权重）
  if (q.full.length >= 4) {
    for (const [f, w] of fields) if (lower(f).includes(q.full)) s += w * 1.5;
  }
  // 词元命中 × IDF（短词元再降权，避免噪音）
  for (const tok of q.tokens) {
    const idfW = idf[tok] || 0;
    if (!idfW) continue;
    for (const [f, w] of fields) {
      if (lower(f).includes(tok)) s += idfW * w * (tok.length >= 4 ? 1 : 0.6);
    }
  }
  // 命中后加少量被引权重，让高影响力文献优先
  if (s > 0) s += 0.4 * Math.log10((p.cited_by_count || 0) + 1);
  return s;
}

async function getPapers() {
  if (window.__papers && window.__papers.length) return window.__papers;
  // 等待页面主体脚本加载完成（最多 15 秒），避免重复下载 papers.json
  for (let i = 0; i < 150; i++) {
    if (window.__papers && window.__papers.length) return window.__papers;
    await new Promise((r) => setTimeout(r, 100));
  }
  try {
    window.__papers = await loadJSON("papers");
    return window.__papers;
  } catch {
    return [];
  }
}

function retrieve(query, papers) {
  const q = tokenize(query);
  const idf = idfFor(papers);
  const scored = papers.map((p) => [scorePaper(p, q, idf), p]);
  scored.sort((a, b) => b[0] - a[0]);
  const hits = scored.filter(([s]) => s > 0);
  const matched = hits.length;
  let top = hits.slice(0, 5).map(([, p]) => p);
  if (!top.length) {
    // 未命中：附领域高被引文献兜底，并在提示中说明
    top = papers.slice()
      .sort((a, b) => (b.cited_by_count || 0) - (a.cited_by_count || 0))
      .slice(0, 3);
  }
  return { top, matched };
}

function refSnippet(p) {
  const t = stripHtml(p.zh_abstract || p.abstract || "").trim();
  if (!t) return "（无摘要）";
  return t.length > 300 ? t.slice(0, 300) + "…" : t;
}

function buildPrompt(query, top) {
  const refs = top.map((p, i) => {
    const zh = stripHtml(p.zh_title), en = stripHtml(p.title);
    const title = zh ? `${zh}（${en}）` : en;
    return `[${i + 1}] ${title}\n    ${p.journal || "未知期刊"} · ${p.year || "未知年份"} · ` +
      `被引 ${p.cited_by_count || 0} · DOI: ${p.doi || "无"}\n    摘要：${refSnippet(p)}`;
  }).join("\n\n");
  return { user: `【参考文献】\n${refs}\n\n【问题】${query}` };
}

/* 数据源标题可能含 <sub>/<i> 等 HTML 标记，展示/拼接前先剥离（配合 textContent 双保险） */
function stripHtml(s) {
  return String(s ?? "").replace(/<[^>]*>/g, "");
}

/* ---------- 安全渲染：先转义，再极简 Markdown（加粗/标题/列表/引用标号） ---------- */

function renderMarkdown(text) {
  let s = escapeHtml(text);
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // 引用标号 [1] / [1,3] → 可点击按钮（编号来自正则白名单，天然安全）
  s = s.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (_, ids) =>
    ids.split(",").map((x) => {
      const n = Number(x.trim());
      return `<button class="cite-ref" data-ref="${n}" type="button" ` +
        `aria-label="跳转到参考文献 ${n}">[${n}]</button>`;
    }).join(""));
  const lines = s.split("\n");
  let html = "", inUl = false, inOl = false, para = [];
  const closePara = () => { if (para.length) { html += `<p>${para.join("<br>")}</p>`; para = []; } };
  const closeLists = () => {
    if (inUl) { html += "</ul>"; inUl = false; }
    if (inOl) { html += "</ol>"; inOl = false; }
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { closePara(); closeLists(); continue; }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      closePara(); closeLists();
      html += h[1].length <= 2 ? `<h4>${h[2]}</h4>` : `<h5>${h[2]}</h5>`;
      continue;
    }
    const ul = line.match(/^[-*•]\s+(.*)$/);
    if (ul) {
      closePara();
      if (!inUl) { html += "<ul>"; inUl = true; }
      html += `<li>${ul[1]}</li>`;
      continue;
    }
    const ol = line.match(/^\d+[.)]\s+(.*)$/);
    if (ol) {
      closePara();
      if (!inOl) { html += "<ol>"; inOl = true; }
      html += `<li>${ol[1]}</li>`;
      continue;
    }
    closeLists();
    para.push(line);
  }
  closePara(); closeLists();
  return html || escapeHtml(text);
}

/* ---------- 界面 ---------- */

function chat() { return document.getElementById("ai-chat"); }

function appendMsg(role) {
  const el = document.createElement("div");
  el.className = `ai-msg ai-msg-${role}`;
  chat().appendChild(el);
  chat().scrollTop = chat().scrollHeight;
  return el;
}

function buildRefs(top, matched) {
  const wrap = document.createElement("div");
  wrap.className = "ai-refs";
  const head = document.createElement("div");
  head.className = "ai-ref-heading";
  head.textContent = matched > 0
    ? `📚 检索到最相关的 ${top.length} 篇文献（点击文中 [编号] 可定位）`
    : "📚 未直接命中相关文献，附领域高被引文献供参考";
  wrap.appendChild(head);
  top.forEach((p, i) => {
    const item = document.createElement("div");
    item.className = "ai-ref";
    item.dataset.refCard = i + 1;
    const idx = document.createElement("span");
    idx.className = "ai-ref-idx";
    idx.textContent = i + 1;
    item.appendChild(idx);
    const body = document.createElement("div");
    const a = document.createElement("a");
    a.href = p.url || "#";
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = stripHtml(p.zh_title || p.title);
    a.style.cssText = "color:var(--ink);font-weight:500";
    body.appendChild(a);
    if (p.zh_title) {
      const en = document.createElement("div");
      en.textContent = stripHtml(p.title);
      en.style.cssText = "font-size:12px;color:var(--muted)";
      en.title = "英文原标题";
      body.appendChild(en);
    }
    const meta = document.createElement("div");
    meta.textContent = `${p.journal || ""} · ${p.year || ""} · 被引 ${fmtInt(p.cited_by_count)}`;
    meta.style.cssText = "font-size:12px;color:var(--muted);margin-top:2px;font-variant-numeric:tabular-nums";
    body.appendChild(meta);
    item.appendChild(body);
    wrap.appendChild(item);
  });
  return wrap;
}

function setSendEnabled(on) {
  const b = document.getElementById("ai-send");
  const i = document.getElementById("ai-input");
  if (b) b.disabled = !on;
  if (i) i.disabled = !on;
}

function maskKey(k) {
  if (!k) return "未配置";
  if (k.length <= 12) return "已配置";
  return `${k.slice(0, 6)}…${k.slice(-4)}`;
}

// 已保存的模型可能被平台下线（见 AI_DEPRECATED），自动回退到默认模型；
// 列表外的自定义 ID 视为有效，原样使用
function currentModel() {
  const saved = localStorage.getItem(AI_MODEL);
  if (saved && !AI_DEPRECATED.has(saved)) return saved;
  return AI_DEFAULT_MODEL;
}

function refreshStatus() {
  const key = localStorage.getItem(AI_KEY);
  const model = currentModel();
  const st = document.getElementById("ai-status");
  if (st) {
    st.textContent = key
      ? `密钥 ${maskKey(key)} · ${model}`
      : "未配置密钥（免费模型，需自行注册硅基流动）";
  }
}

function openSettings(force) {
  const box = document.getElementById("ai-settings");
  if (!box) return;
  if (force || box.classList.contains("hidden")) {
    box.classList.remove("hidden");
    if (force && !localStorage.getItem(AI_KEY)) {
      const inp = document.getElementById("ai-key");
      if (inp) setTimeout(() => inp.focus(), 50);
    }
  } else {
    box.classList.add("hidden");
  }
}

function saveSettings() {
  const key = document.getElementById("ai-key").value.trim();
  let model = document.getElementById("ai-model").value;
  if (model === "__custom__") {
    model = document.getElementById("ai-custom-model").value.trim();
  }
  const prev = localStorage.getItem(AI_KEY) || "";
  if (key) localStorage.setItem(AI_KEY, key);
  if (model) localStorage.setItem(AI_MODEL, model);
  document.getElementById("ai-settings").classList.add("hidden");
  refreshStatus();
  if (key && key !== prev) {
    const el = appendMsg("ai");
    el.textContent = "✅ 密钥已保存。现在可以提问啦——点击上方快捷问题或直接输入。";
  }
}

function clearSettings() {
  const had = !!localStorage.getItem(AI_KEY);
  localStorage.removeItem(AI_KEY);
  document.getElementById("ai-key").value = "";
  refreshStatus();
  if (had) {
    const el = appendMsg("ai");
    el.textContent = "密钥已从浏览器本地清除。";
  }
}

// 检测模型输出异常：
// 1) 压缩空白后，任意连续 40 字符窗口内仅出现 ≤2 种字符（zzz / 等等等 循环）
// 2) 字母沙拉：同一孤立字母以空格分隔重复 ≥3 次（如 "e e e e"）
function looksDegenerate(s) {
  if (s.length < 30) return false;
  const c = s.replace(/\s+/g, "");
  for (let i = 4; i + 40 <= c.length; i += 8) {
    if (new Set(c.slice(i, i + 40)).size <= 2) return true;
  }
  if (/(?:^|\s)([a-z])(?:\s+\1){2,}(?=\s|$)/i.test(s)) return true;
  return false;
}

let busy = false;

async function send(query) {
  const q = (query || "").trim();
  if (!q || busy) return;
  const key = localStorage.getItem(AI_KEY);
  if (!key) { openSettings(true); return; }

  busy = true;
  setSendEnabled(false);
  appendMsg("user").textContent = q;

  const aiEl = appendMsg("ai");
  const think = document.createElement("div");
  think.className = "ai-thinking";
  think.textContent = "正在检索文献并生成回答…";
  aiEl.appendChild(think);

  // 本地检索 + 先渲染参考文献卡片（流式回答中的 [n] 才有跳转目标）
  const papers = (await getPapers()) || [];
  const { top, matched } = retrieve(q, papers);
  aiEl.appendChild(buildRefs(top, matched));

  const body = document.createElement("div");
  body.className = "ai-body";
  aiEl.appendChild(body);

  const model = currentModel();
  let degenerate = false;
  const ctrl = new AbortController();
  try {
    const resp = await fetch(AI_API, {
      method: "POST",
      cache: "no-store",
      signal: ctrl.signal,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${key}`,
      },
      body: JSON.stringify({
        model,
        messages: [
          { role: "system", content: AI_SYSTEM },
          { role: "user", content: buildPrompt(q, top).user },
        ],
        stream: true,
        // 注意：不要给硅基流动免费 Qwen 传 penalty 参数——
        // 免费档在 penalty 采样下会产出 "e e e" 字母沙拉（已知故障）
        temperature: 0.7,
        max_tokens: 800,
      }),
    });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const j = await resp.json();
        detail = j.message || (j.error && j.error.message) || detail;
      } catch { /* 保留默认 */ }
      if (/disabled|not[\s-]?found|not exist|invalid model/i.test(detail)) {
        throw new Error("该模型已被平台下线（Model disabled），请点「⚙ 设置」更换模型。");
      }
      if (resp.status === 401) throw new Error("API Key 无效或已过期，请点击「⚙ 设置」检查密钥。");
      if (resp.status === 429) throw new Error("请求过于频繁，已触发硅基流动限速（免费额度），请稍等片刻再试。");
      throw new Error(`接口返回错误（${detail}）`);
    }
    think.textContent = "生成中…";
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "", text = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 1);
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (data === "[DONE]") continue;
        let j;
        try { j = JSON.parse(data); } catch { continue; }
        const d = j.choices && j.choices[0] && j.choices[0].delta && j.choices[0].delta.content;
        if (d) {
          text += d;
          body.innerHTML = renderMarkdown(text);
          chat().scrollTop = chat().scrollHeight;
        }
      }
      // 输出陷入重复循环：立即中止，避免刷屏
      if (looksDegenerate(text)) {
        degenerate = true;
        ctrl.abort();
      }
    }
    think.textContent = "";
    if (!text) {
      body.innerHTML = renderMarkdown(
        "模型未返回内容。免费模型可能因并发过高临时不可用，请稍后重试，或在「⚙ 设置」中更换模型。");
    }
  } catch (e) {
    think.textContent = "";
    body.innerHTML = renderMarkdown(
      degenerate
        ? "⚠ 模型输出出现异常重复，已自动停止。请重试一次，或点「⚙ 设置」把模型换成 智谱 GLM-4-9B（免费，更稳定）。"
        : e instanceof TypeError
          ? "无法连接硅基流动接口（网络错误或浏览器跨域限制）。请确认网络正常后重试。"
          : `⚠ 请求失败：${(e && e.message) || "未知错误"}`);
  } finally {
    busy = false;
    setSendEnabled(true);
    const inp = document.getElementById("ai-input");
    if (inp) { inp.value = ""; inp.focus(); }
  }
}

/* ---------- 初始化 ---------- */

document.addEventListener("DOMContentLoaded", () => {
  const panel = document.getElementById("ai-panel");
  if (!panel) return;

  // 模型下拉（选项带免费/付费说明）
  const sel = document.getElementById("ai-model");
  const customInput = document.getElementById("ai-custom-model");
  const savedModel = localStorage.getItem(AI_MODEL);
  if (sel) {
    AI_MODELS.forEach(([id, label]) => {
      const o = document.createElement("option");
      o.value = id;
      o.textContent = label;
      if (id === currentModel()) o.selected = true;
      sel.appendChild(o);
    });
    // 自定义模型：回显 ID 并显示输入框
    const isCustom = savedModel && !AI_MODELS.some(([id]) => id === savedModel)
      && !AI_DEPRECATED.has(savedModel);
    if (isCustom && customInput) {
      customInput.value = savedModel;
      sel.value = "__custom__";
      customInput.classList.remove("hidden");
    }
    sel.addEventListener("change", () => {
      if (customInput) customInput.classList.toggle("hidden", sel.value !== "__custom__");
    });
  }

  const savedKey = localStorage.getItem(AI_KEY);
  if (savedKey) document.getElementById("ai-key").value = savedKey;
  refreshStatus();

  document.getElementById("ai-settings-btn").addEventListener("click", () => openSettings(false));
  document.getElementById("ai-save").addEventListener("click", saveSettings);
  document.getElementById("ai-clear").addEventListener("click", clearSettings);
  document.getElementById("ai-send").addEventListener("click", () =>
    send(document.getElementById("ai-input").value));
  document.getElementById("ai-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(e.target.value); }
  });
  document.querySelectorAll(".ai-quick button").forEach((b) => {
    b.addEventListener("click", () => {
      const inp = document.getElementById("ai-input");
      inp.value = b.dataset.q;
      send(b.dataset.q);
    });
  });

  // 文中引用编号点击 → 滚动到对应文献卡片并闪烁
  chat().addEventListener("click", (e) => {
    const btn = e.target.closest(".cite-ref");
    if (!btn) return;
    const card = chat().querySelector(`[data-ref-card="${btn.dataset.ref}"]`);
    if (!card) return;
    card.scrollIntoView({ behavior: REDUCED_MOTION ? "auto" : "smooth", block: "center" });
    card.classList.remove("flash");
    void card.offsetWidth; // 重启动画
    card.classList.add("flash");
    setTimeout(() => card.classList.remove("flash"), 1400);
  });

  // 文献数徽章（复用页面主体已加载的数据）
  getPapers().then((ps) => {
    const c = document.getElementById("ai-count");
    if (c && ps.length) c.textContent = `基于 ${fmtInt(ps.length)} 篇文献检索`;
  });
});
