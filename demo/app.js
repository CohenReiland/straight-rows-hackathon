// Fetches the JSON that demo/build.py wrote and draws every section.
// The page only displays: every number here was computed in Python.

const CAUSE_COLORS = {
  SPACE_WEATHER: "#7c3aed",
  JAMMING: "#dc2626",
  SPOOFING: "#ea8c00",
  EQUIPMENT_FAULT: "#2563eb",
  MULTIPATH: "#059669",
};

const CAUSE_NAMES = {
  SPACE_WEATHER: "Space weather",
  JAMMING: "Jamming",
  SPOOFING: "Spoofing",
  EQUIPMENT_FAULT: "Equipment fault",
  MULTIPATH: "Multipath",
};

const TRACTOR_COLORS = { T1: "#111827", T2: "#0891b2", T3: "#db2777" };

const STATUS_NAMES = {
  hit: "hit",
  missed: "missed",
  wrong_cause: "wrong cause",
  false_alarm: "false alarm",
  exempt: "short multipath (not scored)",
};

const CHART_IDS = ["data-chart", "dev-chart"];
const FONT = { family: "Segoe UI, system-ui, sans-serif", size: 16, color: "#111827" };
const PLOT_CONFIG = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
};

let data = {};
let syncing = false;

// "2026-05-04T01:20:00Z" -> "2026-05-04 01:20:00", so Plotly shows UTC as is
function t(text) {
  return text.replace("T", " ").replace("Z", "");
}

// "2026-05-04T01:20:00Z" -> "05-04 01:20"
function clock(text) {
  return text.slice(5, 16).replace("T", " ");
}

function minutesBetween(start, end) {
  return (Date.parse(end) - Date.parse(start)) / 60000;
}

// Short lengths in seconds, longer ones in minutes
function lengthText(start, end) {
  const minutes = minutesBetween(start, end);
  return minutes < 3 ? `${Math.round(minutes * 60)} s` : `${Math.round(minutes)} min`;
}

function el(id) {
  return document.getElementById(id);
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

// Fetch every data file. A missing one comes back as null.
async function loadData() {
  const names = ["meta", "minutes", "space_feeds", "labels", "detections", "matches", "thresholds"];
  const files = await Promise.all(
    names.map(async (name) => {
      const response = await fetch(`data/${name}.json`, { cache: "no-store" });
      return response.ok ? response.json() : null;
    })
  );
  data = Object.fromEntries(names.map((name, i) => [name, files[i]]));
}

function tractors() {
  return Object.keys(data.minutes).sort();
}

function causeLegend(id) {
  el(id).innerHTML = Object.keys(CAUSE_COLORS)
    .map(
      (cause) =>
        `<span class="chip"><span class="swatch" style="background:${CAUSE_COLORS[cause]}"></span>${CAUSE_NAMES[cause]}</span>`
    )
    .join("");
}

// ---------- Shared shapes ----------

// Gray bands where no tractor is working
function parkedShapes() {
  const lists = tractors().map((tractor) => data.minutes[tractor]);
  const times = lists[0].minute;
  const shapes = [];
  let start = null;
  for (let i = 0; i <= times.length; i++) {
    const parked = i < times.length && lists.every((list) => !list.working[i]);
    if (parked && start === null) start = times[i];
    if (!parked && start !== null) {
      shapes.push({
        type: "rect", xref: "x", yref: "paper", x0: t(start), x1: t(times[i - 1]), y0: 0, y1: 1,
        fillcolor: "#9ca3af", opacity: 0.18, line: { width: 0 }, layer: "below",
      });
      start = null;
    }
  }
  return shapes;
}

// A dashed line where the dev window ends and eval starts
function windowDivider() {
  const evalStart = t(data.meta.windows.eval[0]);
  return {
    shape: {
      type: "line", xref: "x", yref: "paper", x0: evalStart, x1: evalStart, y0: 0, y1: 1,
      line: { color: "#111827", width: 2, dash: "dash" },
    },
    annotation: {
      xref: "x", yref: "paper", x: evalStart, y: 1, yanchor: "bottom", showarrow: false,
      text: "dev ◀ ▶ eval", font: { size: 15 },
    },
  };
}

// ---------- Section 2 ----------

// One marker row per tractor, only at the minutes where a yes/no signal is true
function flagTraces(key, axis, label) {
  return tractors().map((tractor) => {
    const m = data.minutes[tractor];
    const x = m.minute.filter((_, j) => m[key][j]).map(t);
    return {
      type: "scatter", mode: "markers", x, y: x.map(() => tractor), yaxis: axis,
      marker: { symbol: "square", size: 6, color: TRACTOR_COLORS[tractor] },
      name: tractor, legendgroup: tractor, showlegend: false,
      hovertemplate: `${tractor} ${label} %{x}<extra></extra>`,
    };
  });
}

function drawDataChart() {
  const cutoffs = data.meta.cutoffs;
  const rows = [
    { title: "Weakest satellite signal (dB-Hz)", key: "signal_weakest_db" },
    { title: "Satellites in view (fewest)", key: "num_sats_min" },
    { title: "Fix (4 = RTK fixed, 0 = none)", key: "fix_rank_worst", shape: "hv" },
    // Log scale, so the 0.5 m cutoff is visible next to 20 m drifts
    { title: "Distance off the row (m, worst, log)", key: "cross_track_error_max_m", log: true, cutoff: [cutoffs.BAD_CROSS_TRACK_ERROR_M, "bad above"] },
    { title: "Correction link lost", flag: "base_link_lost" },
    { title: "Minutes stage 4 calls bad", flag: "bad" },
    { title: "Storm strength (Kp)", feed: "storm_kp", cutoff: [cutoffs.STORM_KP, "storm"] },
    { title: "Magnetic field drop (Dst, nT)", feed: "storm_field_drop", value: "storm_field_drop_nt", cutoff: [cutoffs.STORM_FIELD_DROP_NT, "storm"] },
    { title: "Signal flicker (S4)", feed: "signal_flicker_s4", cutoff: [cutoffs.HIGH_FLICKER_S4, "high"] },
  ];
  const gap = 0.022;
  const height = 1 / rows.length;
  const layout = {
    font: FONT, height: 1180, margin: { l: 70, r: 20, t: 40, b: 40 },
    showlegend: true, legend: { orientation: "h", y: 1.04, x: 1, xanchor: "right" },
    hovermode: "closest", plot_bgcolor: "#ffffff",
    // Time labels along the bottom of the whole stack
    xaxis: {
      type: "date", anchor: "free", position: 0,
      showspikes: true, spikemode: "across", spikesnap: "cursor", spikethickness: 1,
    },
    shapes: [], annotations: [],
  };
  const traces = [];
  const axisFor = {};

  rows.forEach((row, i) => {
    const axis = i === 0 ? "y" : `y${i + 1}`;
    const axisKey = i === 0 ? "yaxis" : `yaxis${i + 1}`;
    axisFor[row.flag || row.key || row.feed] = axis;
    const top = 1 - i * height;
    // Each row leaves a gap above it for its title
    const rowTop = top - gap;
    layout[axisKey] = { domain: [top - height + 0.006, rowTop], automargin: true, zeroline: false };
    // 1 cm to 30 m, so near-zero parked values don't squash the scale
    if (row.log) Object.assign(layout[axisKey], { type: "log", range: [-2, Math.log10(30)], dtick: 1 });
    layout.annotations.push({
      xref: "paper", yref: "paper", x: 0, y: rowTop, xanchor: "left", yanchor: "bottom",
      text: `<b>${row.title}</b>`, showarrow: false, font: { size: 14 },
    });

    if (row.flag) {
      layout[axisKey].type = "category";
      layout[axisKey].categoryarray = tractors().slice().reverse();
      traces.push(...flagTraces(row.flag, axis, row.title.toLowerCase()));
    } else if (row.key) {
      for (const tractor of tractors()) {
        const m = data.minutes[tractor];
        traces.push({
          type: "scatter", mode: "lines", x: m.minute.map(t), y: m[row.key], yaxis: axis,
          line: { color: TRACTOR_COLORS[tractor], width: 1.4, shape: row.shape || "linear" },
          name: tractor, legendgroup: tractor, showlegend: i === 0,
          hovertemplate: `${tractor} %{x}<br>${row.title}: %{y}<extra></extra>`,
        });
      }
    } else {
      const feed = data.space_feeds[row.feed];
      const values = feed[row.value || row.feed];
      const trace = {
        x: feed.ts.map(t), y: values, yaxis: axis, name: row.title, showlegend: false,
        hovertemplate: `%{x}<br>${row.title}: %{y}<extra></extra>`,
      };
      if (row.feed === "storm_kp") {
        // Kp comes every 3 hours, so each bar covers its 3 hours
        Object.assign(trace, {
          type: "bar", width: 3 * 3600 * 1000, offset: 0,
          marker: { color: values.map((kp) => (kp >= cutoffs.STORM_KP ? "#dc2626" : "#6b7280")) },
        });
      } else {
        Object.assign(trace, { type: "scatter", mode: "lines", line: { color: "#374151", width: 2 } });
      }
      traces.push(trace);
    }

    // A dotted red line at the config cutoff for this row
    if (row.cutoff) {
      const [value, label] = row.cutoff;
      // Plotly places shapes on a log axis by the log of the value
      const y = row.log ? Math.log10(value) : value;
      layout.shapes.push({
        type: "line", xref: "paper", x0: 0, x1: 1, yref: axis, y0: y, y1: y,
        line: { color: "#dc2626", width: 1.5, dash: "dot" },
      });
      layout.annotations.push({
        xref: "paper", x: 1, xanchor: "right", yref: axis, y, yanchor: "bottom",
        text: `${label} ${value}`, showarrow: false, font: { size: 12, color: "#dc2626" },
      });
    }
  });

  // Constellation advisories: an amber line at each issued time, on the satellites row
  const advisories = data.space_feeds.advisories;
  const satsAxis = axisFor.num_sats_min;
  advisories.issued.forEach((issued, j) => {
    layout.shapes.push({
      type: "line", xref: "x", yref: `${satsAxis} domain`, x0: t(issued), x1: t(issued), y0: 0, y1: 1,
      line: { color: "#d97706", width: 2.5 },
    });
    const what = advisories.svn[j] ? `${advisories.svn[j]} advisory` : `${advisories.type[j].toLowerCase().replace("_", " ")} advisory`;
    layout.annotations.push({
      xref: "x", yref: `${satsAxis} domain`, x: t(issued), y: 1, xanchor: "left", yanchor: "top",
      text: what, showarrow: false, font: { size: 12, color: "#92400e" },
      hovertext: escapeHtml(advisories.text[j]),
    });
  });

  // Interference reports: a dotted line at each received time
  const reports = data.space_feeds.interference_reports;
  const linkAxis = axisFor.base_link_lost;
  reports.received.forEach((received, j) => {
    layout.shapes.push({
      type: "line", xref: "x", yref: "paper", x0: t(received), x1: t(received), y0: 0, y1: 1,
      line: { color: "#b91c1c", width: 1.5, dash: "dot" },
    });
    // Reports can be close together, so their labels alternate height
    layout.annotations.push({
      xref: "x", yref: `${linkAxis} domain`, x: t(received), y: j % 2 ? 0.3 : 0.7, xanchor: "left",
      showarrow: false, bgcolor: "#ffffff",
      text: `interference ${reports.confidence[j]}`, font: { size: 12, color: "#b91c1c" },
      hovertext: escapeHtml(reports.text[j]),
    });
  });

  // Training labels as colored bands across every row
  for (const label of data.labels) {
    layout.shapes.push({
      type: "rect", xref: "x", yref: "paper", x0: t(label.start), x1: t(label.end), y0: 0, y1: 1,
      fillcolor: CAUSE_COLORS[label.class], opacity: 0.16, line: { width: 0 }, layer: "below",
    });
  }

  layout.shapes.push(...parkedShapes());
  const divider = windowDivider();
  layout.shapes.push(divider.shape);
  layout.annotations.push(divider.annotation);

  Plotly.react("data-chart", traces, layout, PLOT_CONFIG);
}

// ---------- Section 4: lanes ----------

// Bars for labels or detections, one trace per cause so the legend works
function laneTraces(items, laneFor, styleFor, hoverFor) {
  const traces = [];
  for (const cause of Object.keys(CAUSE_COLORS)) {
    const bars = [];
    for (const item of items.filter((i) => i.class === cause)) {
      for (const tractor of item.tractors) bars.push({ item, lane: laneFor(tractor, item) });
    }
    if (!bars.length) continue;
    const styles = bars.map((bar) => styleFor(bar.item));
    traces.push({
      type: "bar", orientation: "h", name: CAUSE_NAMES[cause], legendgroup: cause,
      showlegend: false,
      y: bars.map((bar) => bar.lane),
      base: bars.map((bar) => t(bar.item.start)),
      x: bars.map((bar) => Date.parse(bar.item.end) - Date.parse(bar.item.start)),
      marker: {
        color: CAUSE_COLORS[cause],
        opacity: styles.map((s) => s.opacity),
        pattern: { shape: styles.map((s) => s.pattern), fgcolor: "#111827", solidity: 0.3 },
        line: { color: styles.map((s) => s.outline), width: 2 },
      },
      hovertext: bars.map((bar) => hoverFor(bar.item)),
      hoverinfo: "text",
      width: 0.7,
    });

    // Short items are too thin to see on a 2-day axis, so add a dot
    const short = bars.filter((bar) => minutesBetween(bar.item.start, bar.item.end) < 15);
    if (short.length) {
      traces.push({
        type: "scatter", mode: "markers", legendgroup: cause, showlegend: false,
        y: short.map((bar) => bar.lane),
        x: short.map((bar) => t(bar.item.start)),
        marker: {
          color: CAUSE_COLORS[cause], size: short.map((bar) => styleFor(bar.item).dot || 11),
          symbol: "diamond", opacity: short.map((bar) => styleFor(bar.item).opacity),
        },
        hovertext: short.map((bar) => hoverFor(bar.item)),
        hoverinfo: "text",
      });
    }
  }
  return traces;
}

function laneLayout(lanes, window) {
  const [start, end] = data.meta.windows[window];
  return {
    font: FONT, barmode: "overlay", height: 120 + lanes.length * 44,
    margin: { l: 150, r: 20, t: 30, b: 40 }, hovermode: "closest",
    showlegend: false,
    xaxis: { type: "date", range: [t(start), t(end)], showspikes: true, spikemode: "across", spikethickness: 1 },
    yaxis: { type: "category", categoryarray: lanes.slice().reverse(), automargin: true },
    shapes: parkedShapes(),
  };
}

function hoverLines(item, extra) {
  return [
    `<b>${CAUSE_NAMES[item.class]}</b> ${item.tractors.join(", ")}`,
    `${clock(item.start)} to ${clock(item.end)} (${lengthText(item.start, item.end)})`,
    ...extra,
  ].join("<br>");
}

function drawDevChart() {
  if (!data.matches) {
    el("dev-chart").innerHTML = `<p class="error">No dev predictions yet: run python run.py --window dev</p>`;
    return;
  }
  const labelInfo = Object.fromEntries(data.matches.labels.map((l) => [l.label_id, l]));
  const lanes = tractors().flatMap((tractor) => [`${tractor} labels`, `${tractor} mine`, `${tractor} short (free)`]);

  const labelTraces = laneTraces(
    data.labels,
    (tractor) => `${tractor} labels`,
    (label) => {
      const ok = labelInfo[label.id]?.status === "hit";
      return { opacity: 0.85, pattern: ok ? "" : "/", outline: ok ? "#ffffff" : "#991b1b" };
    },
    (label) => {
      const info = labelInfo[label.id] || {};
      return hoverLines(label, [
        `Label ${label.id}: <b>${STATUS_NAMES[info.status] || "?"}</b>`,
        `Action ${label.recommended_action}`,
      ]);
    }
  );

  // Short multipath reports that aren't scored go in their own thin lane
  const detectionTraces = laneTraces(
    data.matches.detections,
    (tractor, d) => (d.status === "exempt" ? `${tractor} short (free)` : `${tractor} mine`),
    (d) => ({
      opacity: d.status === "exempt" ? 0.45 : 0.95,
      pattern: d.status === "false_alarm" ? "x" : "",
      outline: d.status === "false_alarm" ? "#991b1b" : "#ffffff",
      dot: d.status === "exempt" ? 6 : 11,
    }),
    (d) => {
      const info = d.label_id ? labelInfo[d.label_id] : null;
      const extra = [`<b>${STATUS_NAMES[d.status]}</b>${d.label_id ? ` (${d.label_id})` : ""}`];
      if (info && info.time_iou !== undefined) {
        extra.push(`time IoU ${info.time_iou.toFixed(2)}, onset ${info.onset_min >= 0 ? "+" : ""}${info.onset_min.toFixed(0)} min`);
      }
      extra.push(`${d.action}, confidence ${d.confidence.toFixed(2)}`);
      return hoverLines(d, extra);
    }
  );

  Plotly.react("dev-chart", [...labelTraces, ...detectionTraces], laneLayout(lanes, "dev"), PLOT_CONFIG);
}

// ---------- Section 4 tables ----------

function drawScorecard() {
  const m = data.matches;
  if (!m) {
    el("scorecard").innerHTML = "";
    el("label-table").innerHTML = "";
    el("confusion").innerHTML = "";
    return;
  }
  const rows = Object.entries(m.counts)
    .map(
      ([cause, c]) => `<tr>
        <td><span class="swatch" style="background:${CAUSE_COLORS[cause]}"></span> ${CAUSE_NAMES[cause]}</td>
        <td class="num">${c.hits}</td><td class="num">${c.false}</td><td class="num">${c.missed}</td>
        <td class="num">${c.f1.toFixed(2)}</td></tr>`
    )
    .join("");
  el("scorecard").innerHTML = `
    <div class="big-numbers">
      <div><strong>${m.total.toFixed(1)} / 40</strong>dev score</div>
      <div><strong>${m.macro_f1.toFixed(2)}</strong>macro-F1 (25 pts)</div>
      <div><strong>${m.mean_onset.toFixed(2)}</strong>onset (15 pts)</div>
      <div><strong>${m.actions_agreed} / ${m.labels.length}</strong>actions agreed</div>
      <div><strong>${m.free_multipath}</strong>short multipath (not scored)</div>
    </div>
    <table><tr><th>Cause</th><th>Hits</th><th>False alarms</th><th>Missed</th><th>F1</th></tr>${rows}</table>`;

  const labelsById = Object.fromEntries(data.labels.map((l) => [l.id, l]));
  el("label-table").innerHTML = `<table>
    <tr><th>Label</th><th>Cause</th><th>Tractors</th><th>Result</th><th>Onset error</th><th>Time IoU</th><th>Credit</th></tr>
    ${m.labels
      .map((entry) => {
        const label = labelsById[entry.label_id];
        const onset = entry.onset_min === undefined ? "" : `${entry.onset_min >= 0 ? "+" : ""}${entry.onset_min.toFixed(0)} min`;
        const iou = entry.time_iou === undefined ? "" : entry.time_iou.toFixed(2);
        return `<tr><td class="mono">${entry.label_id}</td><td>${CAUSE_NAMES[label.class]}</td>
          <td>${label.tractors.join(", ")}</td>
          <td><span class="tag ${entry.status}">${STATUS_NAMES[entry.status]}</span></td>
          <td class="num">${onset}</td><td class="num">${iou}</td><td class="num">${entry.credit.toFixed(2)}</td></tr>`;
      })
      .join("")}</table>`;

  // Label cause down the side, what I said across the top
  const causes = Object.keys(CAUSE_COLORS);
  const grid = Object.fromEntries(causes.map((c) => [c, Object.fromEntries([...causes, "missed"].map((d) => [d, 0]))]));
  for (const entry of m.labels) {
    const said = entry.detection ? entry.detection.class : "missed";
    grid[labelsById[entry.label_id].class][said] += 1;
  }
  const falseAlarms = m.detections.filter((d) => d.status === "false_alarm" && !d.label_id);
  el("confusion").innerHTML = `<table>
    <tr><th>Label ↓ / mine →</th>${causes.map((c) => `<th>${CAUSE_NAMES[c]}</th>`).join("")}<th>Missed</th></tr>
    ${causes
      .map(
        (c) => `<tr><th>${CAUSE_NAMES[c]}</th>${[...causes, "missed"]
          .map((d) => `<td class="num">${grid[c][d] || ""}</td>`)
          .join("")}</tr>`
      )
      .join("")}
    <tr><th>No label (false alarm)</th>${causes
      .map((c) => `<td class="num">${falseAlarms.filter((d) => d.class === c).length || ""}</td>`)
      .join("")}<td></td></tr>
    </table>`;
}

// ---------- Linked zoom ----------

// Zooming one chart's time axis zooms the others to match
function linkZoom() {
  for (const id of CHART_IDS) {
    const chart = el(id);
    if (!chart.on || chart.dataset.linked) continue;
    chart.dataset.linked = "yes";
    chart.on("plotly_relayout", (event) => {
      if (syncing) return;
      let update = null;
      if (event["xaxis.range[0]"] !== undefined) {
        update = { "xaxis.range": [event["xaxis.range[0]"], event["xaxis.range[1]"]] };
      } else if (event["xaxis.range"]) {
        update = { "xaxis.range": event["xaxis.range"] };
      } else if (event["xaxis.autorange"]) {
        resetZoom(id);
        return;
      }
      if (!update) return;
      syncing = true;
      Promise.all(
        CHART_IDS.filter((other) => other !== id && el(other).layout).map((other) => Plotly.relayout(other, update))
      ).finally(() => (syncing = false));
    });
  }
}

// Double-click puts each chart back to its own full window
function resetZoom(source) {
  syncing = true;
  const ranges = { "dev-chart": data.meta.windows.dev };
  Promise.all(
    CHART_IDS.filter((id) => el(id).layout).map((id) =>
      ranges[id]
        ? Plotly.relayout(id, { "xaxis.range": ranges[id].map(t) })
        : Plotly.relayout(id, { "xaxis.autorange": true })
    )
  ).finally(() => (syncing = false));
}

// ---------- Nav ----------

function highlightNav() {
  const links = [...document.querySelectorAll(".sidebar a")];
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        links.forEach((link) => link.classList.toggle("active", link.hash === `#${entry.target.id}`));
      }
    },
    { rootMargin: "-40% 0px -55% 0px" }
  );
  document.querySelectorAll("main section").forEach((section) => observer.observe(section));
}

// ---------- Main ----------

async function drawAll() {
  const status = el("status");
  status.textContent = "Loading…";
  try {
    await loadData();
    causeLegend("data-legend");
    causeLegend("dev-legend");
    drawDataChart();
    drawDevChart();
    drawScorecard();
    linkZoom();
    status.textContent = `Data built ${data.meta.built.slice(11, 19)} UTC`;
  } catch (error) {
    console.error(error);
    status.innerHTML = `<span class="error">Couldn't load: ${escapeHtml(error.message)}</span>`;
  }
}

// Reload: the server rebuilds the JSON from the latest run.py outputs, then the page redraws
async function reload() {
  const button = el("reload");
  button.disabled = true;
  el("status").textContent = "Rebuilding…";
  try {
    const response = await fetch("rebuild", { method: "POST" });
    if (!response.ok) throw new Error(`rebuild failed (${response.status}), see the terminal`);
    await drawAll();
  } catch (error) {
    el("status").innerHTML = `<span class="error">${escapeHtml(error.message)}</span>`;
  } finally {
    button.disabled = false;
  }
}

el("reload").addEventListener("click", reload);
highlightNav();
drawAll();
