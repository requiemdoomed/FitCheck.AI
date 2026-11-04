// Dashboard: counts, readiness, recent outfits and wardrobe statistics.

import { api } from "../api.js";
import { categoryLabel, label } from "../lib/catalog.js";
import { itemPicture, outfitCardHTML } from "../outfit-view.js";
import { initShell } from "../shell.js";
import { demoWardrobeButton, emptyStateHTML, esc, watchApiStatus } from "../ui.js";

const me = await initShell("dashboard");
if (me) start();

function greeting(name) {
  const h = new Date().getHours();
  const part = h < 5 ? "Up late" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  return `${part}, ${name.split(" ")[0]}`;
}

async function start() {
  watchApiStatus();
  document.querySelector("[data-greeting]").textContent = greeting(me.user.display_name);
  const root = document.querySelector("[data-dashboard]");
  const unit = me.preferences.temperature_unit;

  let summary, stats;
  try {
    [summary, stats] = await Promise.all([api.dashboard.summary(), api.dashboard.statistics()]);
  } catch (err) {
    root.innerHTML = `<div class="notice notice--error" role="alert">${esc(err.message)}</div>`;
    return;
  }

  const c = summary.counts;
  const rated = c.likes + c.dislikes;
  const likeRate = rated ? `${Math.round((100 * c.likes) / rated)}%` : "–";

  const readiness = summary.ready_to_generate ? "" : `
    <div class="notice notice--warn readiness" role="status">
      <div><strong>Almost ready to get dressed.</strong>
      <p>Add ${summary.missing.map((m) => (m === "footwear" ? "a pair of shoes" : `a ${categoryLabel(m).toLowerCase()}`)).join(" and ")}
      so FitCheck.AI can put a full outfit together.</p></div>
      <a class="btn btn--sm" href="wardrobe.html#add">Add clothes</a>
    </div>`;

  const ledger = `
    <dl class="ledger">
      ${cell(c.items, c.items === 1 ? "piece in your wardrobe" : "pieces in your wardrobe")}
      ${cell(c.outfits, c.outfits === 1 ? "outfit suggested" : "outfits suggested")}
      ${cell(c.saved, "saved")}
      ${cell(likeRate, rated ? `liked, of ${rated} rated` : "liked, none rated yet")}
      ${cell(c.avg_score || "–", "average score")}
    </dl>`;

  const recent = summary.recent_outfits.length
    ? `<ul class="outfit-list">${summary.recent_outfits.map((o) => `<li>${outfitCardHTML(o, { unit, level: 3 })}</li>`).join("")}</ul>
       <p style="margin-top:var(--s3)"><a href="history.html">See all outfits</a></p>`
    : `<p class="muted">No outfits yet. <a href="outfit-generator.html">Get your first one</a>.</p>`;

  const used = stats.most_recommended.length
    ? `<ul class="mini-list">${stats.most_recommended.map((i) => `<li>${itemPicture({ ...i, main_color: { hex: i.hex } }, { size: "sm" })}
        <span>${esc(i.name)}</span><span class="count">${i.count}×</span></li>`).join("")}</ul>`
    : `<p class="muted">Suggestions you get will show up here.</p>`;

  const waiting = stats.never_recommended.length
    ? `<ul class="mini-list">${stats.never_recommended.map((i) => `<li><span class="tag-mini">${esc(categoryLabel(i.category))}</span>
        <span>${esc(i.name)}</span><span></span></li>`).join("")}</ul>`
    : `<p class="muted">Every piece has been in at least one outfit.</p>`;

  if (!c.items) {
    root.innerHTML = readiness + ledger + emptyStateHTML({
      title: "Start with what you wear most",
      body: "Your statistics fill in as you add clothes and try outfits.",
      actionLabel: "Add your first piece",
      actionHref: "wardrobe.html#add",
    });
    const es = root.querySelector(".empty-state");
    const row = document.createElement("div");
    row.className = "empty-state__actions";
    row.append(es.querySelector(".btn"), demoWardrobeButton(() => location.reload()));
    es.append(row);
    return;
  }

  root.innerHTML = `${readiness}${ledger}
    <div class="dash-grid">
      <section class="panel panel--wide"><h2 class="panel__title">Recent outfits</h2>${recent}</section>
      <section class="panel"><h2 class="panel__title">Colours on your rail</h2><div class="chart-box"><canvas data-chart="colors" role="img" aria-label="Number of pieces in each colour"></canvas></div></section>
      <section class="panel"><h2 class="panel__title">Outfits per week</h2>${c.outfits
        ? `<div class="chart-box"><canvas data-chart="weekly" role="img" aria-label="Outfits suggested in each of the last 8 weeks"></canvas></div>`
        : `<p class="muted">Fills in once you start getting outfits.</p>`}</section>
      <section class="panel"><h2 class="panel__title">What you dress for</h2>${c.outfits
        ? `<div class="chart-box"><canvas data-chart="occasions" role="img" aria-label="Outfits by occasion"></canvas></div>`
        : `<p class="muted">Shows which occasions you ask for most.</p>`}</section>
      <section class="panel"><h2 class="panel__title">Seasons covered</h2><div class="chart-box"><canvas data-chart="seasons" role="img" aria-label="Pieces suitable for each season"></canvas></div></section>
      <section class="panel"><h2 class="panel__title">Suggested most</h2>${used}</section>
      <section class="panel"><h2 class="panel__title">Waiting for their turn</h2>${waiting}</section>
    </div>`;

  drawCharts(stats);
  // redraw in the new colours when the theme changes
  new MutationObserver(() => drawCharts(stats))
    .observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
}

function cell(value, text) {
  return `<div class="ledger__cell"><dd class="ledger__value">${esc(value)}</dd><dt class="ledger__label">${esc(text)}</dt></div>`;
}

const charts = [];

function drawCharts(stats) {
  const Chart = window.Chart;
  if (!Chart) {
    document.querySelectorAll("[data-chart]").forEach((c) =>
      c.replaceWith(Object.assign(document.createElement("p"), { className: "muted", textContent: "Charts couldn't load." })));
    return;
  }
  charts.splice(0).forEach((ch) => ch.destroy());

  const css = getComputedStyle(document.documentElement);
  const ink = css.getPropertyValue("--ink").trim();
  const soft = css.getPropertyValue("--ink-soft").trim();
  const line = css.getPropertyValue("--line").trim();
  const magenta = css.getPropertyValue("--magenta").trim();
  const cobalt = css.getPropertyValue("--cobalt").trim();
  const sun = css.getPropertyValue("--sun").trim();
  const mint = css.getPropertyValue("--mint").trim();
  const tangerine = css.getPropertyValue("--tangerine").trim();
  const sky = css.getPropertyValue("--sky").trim();
  Chart.defaults.font.family = css.getPropertyValue("--font");
  Chart.defaults.font.weight = 600;
  Chart.defaults.color = soft;
  Chart.defaults.borderColor = line;

  const base = {
    responsive: true,
    maintainAspectRatio: false,
    animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 500 },
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { display: false } },
      y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: line } },
    },
  };

  const make = (key, config) => {
    const el = document.querySelector(`[data-chart="${key}"]`);
    if (el) charts.push(new Chart(el, config));
  };

  make("colors", {
    type: "bar",
    data: {
      labels: stats.colors.map((c) => label(c.name)),
      datasets: [{ data: stats.colors.map((c) => c.count), backgroundColor: stats.colors.map((c) => c.hex),
                   borderColor: ink, borderWidth: 2, borderRadius: 6 }],
    },
    options: base,
  });

  make("weekly", {
    type: "bar",
    data: {
      labels: stats.weekly.map((w) => new Date(w.week_start + "T00:00:00").toLocaleDateString([], { day: "numeric", month: "short" })),
      datasets: [{ data: stats.weekly.map((w) => w.outfits), backgroundColor: magenta, borderColor: ink,
                   borderWidth: 2, borderRadius: 6 }],
    },
    options: { ...base, plugins: { legend: { display: false }, tooltip: { callbacks: {
      afterLabel: (ctx) => {
        const s = stats.weekly[ctx.dataIndex].avg_score;
        return s ? `average score ${s}` : "";
      } } } } },
  });

  make("occasions", {
    type: "bar",
    data: {
      labels: stats.occasions.map((o) => label(o.occasion)),
      datasets: [{ data: stats.occasions.map((o) => o.count),
                   backgroundColor: stats.occasions.map((_, i) => [sun, mint, sky, magenta, tangerine, cobalt][i % 6]),
                   borderColor: ink, borderWidth: 2, borderRadius: 6 }],
    },
    options: { ...base, indexAxis: "y", scales: { x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: line } }, y: { grid: { display: false } } } },
  });

  const seasons = ["spring", "summer", "autumn", "winter"];
  make("seasons", {
    type: "bar",
    data: {
      labels: seasons.map(label),
      datasets: [{ data: seasons.map((s) => stats.seasons[s] || 0),
                   backgroundColor: [mint, sun, tangerine, sky], borderColor: ink, borderWidth: 2, borderRadius: 6 }],
    },
    options: base,
  });
}
