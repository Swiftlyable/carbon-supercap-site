/* ============================================================
   site.js — 全站共享：主题、导航、数据加载、ECharts 主题桥接
   ============================================================ */
"use strict";

/* ---------- 主题 ---------- */
const THEME_KEY = "scnet-theme";

function currentTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "light" || saved === "dark") return saved;
  return "dark"; // 默认深色（科研图表风格）
}

function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem(THEME_KEY, t);
  const btn = document.getElementById("theme-toggle");
  if (btn) btn.textContent = t === "dark" ? "☀" : "☾";
  window.dispatchEvent(new CustomEvent("themechange", { detail: { theme: t } }));
}

function initTheme() {
  applyTheme(currentTheme());
  const btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.addEventListener("click", () => {
      applyTheme(currentTheme() === "dark" ? "light" : "dark");
    });
  }
}

/* ---------- 页头/页脚注入（全站一致，便于维护） ---------- */
const NAV_ITEMS = [
  ["home", "首页", "index.html"],
  ["mindmap", "知识脉络", "mindmap.html"],
  ["papers", "文献库", "papers.html"],
  ["graph", "关系图", "graph.html"],
  ["stats", "数据面板", "stats.html"],
  ["about", "关于", "about.html"],
];

function renderChrome() {
  // 所有页面均位于站点根目录，相对链接直接写文件名即可
  // （无论部署在域名根还是 /repo/ 子路径下都成立）
  const header = document.createElement("header");
  header.className = "site-header";
  header.innerHTML =
    `<div class="header-inner">` +
    `<a class="brand" href="index.html"><span class="brand-dot"></span><span class="brand-text">碳网图谱 CarbonNet</span></a>` +
    `<nav class="nav">` +
    NAV_ITEMS.map(([k, label, href]) =>
      `<a data-nav="${k}" href="${href}">${label}</a>`).join("") +
    `</nav>` +
    `<button id="theme-toggle" class="theme-btn" title="切换明暗主题" aria-label="切换明暗主题"></button>` +
    `</div>`;
  document.body.prepend(header);

  const footer = document.createElement("footer");
  footer.className = "site-footer";
  footer.innerHTML =
    `<div class="container">` +
    `<span>碳网图谱 CarbonNet — 碳材料超级电容器三维导电网络文献知识站</span>` +
    `<span>数据源：<a href="https://openalex.org" target="_blank" rel="noopener">OpenAlex</a> · 支持 <a href="https://www.webofscience.com" target="_blank" rel="noopener">Web of Science</a> 导出文件导入</span>` +
    `<span>自动更新：GitHub Actions 每周一运行</span>` +
    `</div>`;
  document.body.append(footer);
}

/* ---------- 导航高亮 ---------- */
function initNav() {
  const page = document.body.dataset.page;
  document.querySelectorAll(".nav a").forEach((a) => {
    if (a.dataset.nav === page) a.classList.add("active");
  });
}

/* ---------- 数据加载（所有页面位于站点根目录） ---------- */
async function loadJSON(name) {
  // data/*.json 由工作流定期更新；禁用浏览器缓存，避免刷新后仍显示旧数据
  const resp = await fetch(`data/${name}.json`, { cache: "no-store" });
  if (!resp.ok) throw new Error(`加载 ${name}.json 失败: ${resp.status}`);
  return resp.json();
}

/* ---------- 格式化 ---------- */
// ECharts tooltip 等以 innerHTML 渲染的位置，注入前必须转义不可信文本
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function fmtInt(n) {
  return (n ?? 0).toLocaleString("en-US");
}
function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
}
function shortAuthors(authors) {
  if (!authors || !authors.length) return "—";
  const s = authors.slice(0, 3).join(", ");
  return authors.length > 3 ? `${s} 等` : s;
}

/* ---------- ECharts 主题桥接：从 CSS 令牌读取双模式颜色 ---------- */
function readToken(name) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name).trim();
}

function chartTheme() {
  const dark = currentTheme() === "dark";
  return {
    dark,
    page: readToken("--page"),
    surface: readToken("--surface-1"),
    ink: readToken("--ink"),
    ink2: readToken("--ink-2"),
    muted: readToken("--muted"),
    grid: readToken("--grid"),
    baseline: readToken("--baseline"),
    border: readToken("--border-strong"),
    series: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => readToken(`--s${i}`)),
    seq: [700, 600, 500, 400, 350, 300, 250, 100].map((i) => readToken(`--seq-${i}`)),
    seqLightToDark: [100, 250, 300, 350, 400, 500, 600, 700].map((i) => readToken(`--seq-${i}`)),
    good: readToken("--good"),
    warning: readToken("--warning"),
    serious: readToken("--serious"),
    critical: readToken("--critical"),
  };
}

/* 图表的公共基础配置 */
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function baseChartOptions() {
  const t = chartTheme();
  return {
    backgroundColor: "transparent",
    textStyle: { color: t.ink2, fontFamily: "inherit" },
    animation: !REDUCED_MOTION,
    animationDuration: 400,
    tooltip: {
      backgroundColor: t.surface,
      borderColor: t.border,
      borderWidth: 1,
      textStyle: { color: t.ink, fontSize: 13 },
      confine: true,
    },
  };
}

/* ---------- 入场动效（尊重 prefers-reduced-motion） ---------- */
function initEntrance() {
  if (REDUCED_MOTION || !("IntersectionObserver" in window)) return;
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (en.isIntersecting) {
        en.target.classList.remove("io-hide");
        en.target.classList.add("io-in");
        observer.unobserve(en.target);
      }
    });
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });

  const animate = (els, baseDelay) => {
    els.forEach((el, i) => {
      if (el.getBoundingClientRect().top < window.innerHeight * 0.92) {
        el.classList.add("fade-up");                       // 首屏内：错峰淡入
        el.style.animationDelay = `${baseDelay + Math.min(i, 8) * 60}ms`;
      } else {
        el.classList.add("io-hide");                       // 首屏外：滚动进入时淡入
        el.style.transitionDelay = `${Math.min(i, 4) * 50}ms`;
        observer.observe(el);
      }
    });
  };

  // 排除 hero 画布：其自身有固定透明度，且无需入场动画
  animate(Array.from(document.querySelectorAll(".hero > *:not(#hero-canvas)")), 0);
  animate(Array.from(document.querySelectorAll("main .section")), 120);
}

/* ---------- 流体背景层（全站氛围光晕，样式见 style.css 流体动效层） ---------- */
function initFluidBackground() {
  const bg = document.createElement("div");
  bg.className = "fluid-bg";
  bg.setAttribute("aria-hidden", "true");
  bg.innerHTML = "<i></i><i></i><i></i>";
  document.body.prepend(bg);
}

/* ---------- 卡片悬浮跟随（聚光 + 微倾斜，样式见 style.css） ---------- */
function initCardTilt() {
  // 仅鼠标类指针设备启用；触屏无 hover，reduce-motion 用户跳过
  if (REDUCED_MOTION || !window.matchMedia("(pointer: fine)").matches) return;
  const CARDS = "a.card, .paper-card, .classic-card, .kpi";
  document.addEventListener("pointermove", (e) => {
    const card = e.target.closest(CARDS);
    if (!card) return;
    const r = card.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width;
    const y = (e.clientY - r.top) / r.height;
    card.style.setProperty("--mx", (x * 100).toFixed(1) + "%");
    card.style.setProperty("--my", (y * 100).toFixed(1) + "%");
    card.style.setProperty("--rx", ((0.5 - y) * 4).toFixed(2) + "deg");
    card.style.setProperty("--ry", ((x - 0.5) * 4).toFixed(2) + "deg");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  renderChrome();
  initTheme();
  initNav();
  initEntrance();
  initFluidBackground();
  initCardTilt();
});
