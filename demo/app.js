// Fetches the JSON that demo/build.py wrote and draws every section.
// The page only displays: every number here was computed in Python.

// Colors, the same as style.css (Plotly needs plain hex)
const INK = "#1b1e22";
const INK_2 = "#383c42";
const MUTED = "#5b6067";
const FAINT = "#878b91";
const QUIET = "#b3b6ba";
const RULE = "#e4e6e9";
const PAPER = "#fcfcfd";
const PAPER_2 = "#f3f4f6";
const ACCENT = "#0066cc";

// Each cause: its name, color, and the plain words for its action
const CAUSES = {
  SPACE_WEATHER: { label: "Space weather", color: "#5b2fc0", action: "Halt or switch to degraded mode" },
  JAMMING: { label: "Jamming", color: "#b3261e", action: "Halt and report" },
  SPOOFING: { label: "Spoofing", color: "#b0600f", action: "Halt, cross-check, and report" },
  EQUIPMENT_FAULT: { label: "Equipment fault", color: "#0a5640", action: "Service this machine, the others keep going" },
  MULTIPATH: { label: "Multipath", color: "#5f5e68", action: "Keep going, it's a false alarm" },
};
const ORDER = Object.keys(CAUSES);

// Tractor line colors in the deep dive
const TRACTOR_COLORS = { T1: INK, T2: ACCENT, T3: FAINT };

// The 8 stages, grouped like run.py
const STAGES = [
  ["Prepare", [
    ["1", "Load", "telemetry and the five space feeds"],
    ["2", "Mask", "keep working minutes, drop parked time"],
    ["3", "Features", "each minute vs. its own normal and the fleet"],
  ]],
  ["Find", [
    ["4", "Segment", "bad minutes, dips, drifts and steps into episodes"],
    ["5", "Group", "overlapping episodes share one event"],
  ]],
  ["Explain", [
    ["6", "Attribute", "run the five cause tests"],
    ["7", "Decide", "pick a cause, score confidence, write evidence"],
    ["8", "Emit", "write submission.json and validate it"],
  ]],
];

const FONT = { family: "Segoe UI, system-ui, sans-serif", size: 14, color: INK_2 };
const PLOT_CONFIG = {
  responsive: true,
  displaylogo: false,
  displayModeBar: "hover",
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"],
};
const LINKED = ["data-chart", "dev-chart"];

let data = {};
let syncing = false;
const view = { day: null, dataDay: null, picked: null, showMultipath: false, debugRows: false, allLabels: false };

// ---------- Small helpers ----------

// "2026-05-04T01:20:00Z" -> "2026-05-04 01:20:00", so Plotly shows UTC as is
function t(text) {
  return text.replace("T", " ").replace("Z", "");
}

// "2026-05-04T01:20:00Z" -> "01:20"
function hhmm(text) {
  return text.slice(11, 16);
}

function minutesBetween(start, end) {
  return (Date.parse(end) - Date.parse(start)) / 60000;
}

// Short lengths in seconds, longer ones in minutes
function lengthText(start, end) {
  const minutes = minutesBetween(start, end);
  return minutes < 3 ? `${Math.round(minutes * 60)} s` : `${Math.round(minutes)} min`;
}

// "2026-05-06..." -> "May 6"
function dayName(text) {
  return `May ${Number(text.slice(8, 10))}`;
}

function el(id) {
  return document.getElementById(id);
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

function tractors() {
  return Object.keys(data.minutes).sort();
}

// Fetch every data file. A missing one comes back as null.
async function loadData() {
  const names = ["meta", "minutes", "space_feeds", "labels", "matches", "thresholds", "episodes", "deep_dives"];
  const files = await Promise.all(
    names.map(async (name) => {
      const response = await fetch(`data/${name}.json`, { cache: "no-store" });
      return response.ok ? response.json() : null;
    })
  );
  data = Object.fromEntries(names.map((name, i) => [name, files[i]]));
}

// ---------- Stacked chart layout ----------

// Stack rows top to bottom by weight. Each row gets its own y axis on one shared x axis.
function stackRows(rows, gap) {
  const total = rows.reduce((sum, row) => sum + row.weight, 0);
  const free = 1 - gap * (rows.length - 1);
  let top = 1;
  return rows.map((row, i) => {
    const height = (row.weight / total) * free;
    const placed = {
      ...row,
      axis: i === 0 ? "y" : `y${i + 1}`,
      key: i === 0 ? "yaxis" : `yaxis${i + 1}`,
      domain: [top - height, top],
    };
    top -= height + gap;
    return placed;
  });
}

function baseLayout(height, range) {
  return {
    font: FONT,
    height,
    margin: { l: 64, r: 44, t: 28, b: 36 },
    paper_bgcolor: PAPER,
    plot_bgcolor: PAPER,
    showlegend: false,
    barmode: "overlay",
    hovermode: "closest",
    hoverlabel: { bgcolor: INK, bordercolor: INK, font: { color: PAPER, size: 13 } },
    xaxis: {
      type: "date",
      range,
      anchor: "free",
      position: 0,
      showgrid: false,
      linecolor: RULE,
      tickfont: { size: 12, color: MUTED },
      showspikes: true,
      spikemode: "across",
      spikesnap: "cursor",
      spikethickness: 1,
      spikecolor: FAINT,
      spikedash: "solid",
    },
    shapes: [],
    annotations: [],
  };
}

function yAxis(row, extra) {
  return {
    domain: row.domain,
    zeroline: false,
    showgrid: false,
    fixedrange: true,
    // Ticks on the right, so the row titles on the left have room
    side: "right",
    tickfont: { size: 11, color: FAINT },
    ...extra,
  };
}

// A bold row title on the left edge, with an optional small line under it
function rowTitle(row, text, small) {
  const under = small ? `<br><span style="font-size:11px;color:${MUTED}">${small}</span>` : "";
  return {
    xref: "paper", yref: `${row.axis} domain`, x: -0.005, y: 0.5, xanchor: "right", align: "right",
    text: `<b>${text}</b>${under}`, showarrow: false, font: { size: 15, color: INK },
  };
}

// A dashed cutoff line across one row
function cutoffLine(row, value) {
  return {
    type: "line", xref: "paper", x0: 0, x1: 1, yref: row.axis, y0: value, y1: value,
    line: { color: FAINT, width: 1, dash: "dash" },
  };
}

// Light bands where no tractor is working, inside the given window
function parkedShapes(yref) {
  const lists = tractors().map((tractor) => data.minutes[tractor]);
  const times = lists[0].minute;
  const shapes = [];
  let start = null;
  for (let i = 0; i <= times.length; i++) {
    const parked = i < times.length && lists.every((list) => !list.working[i]);
    if (parked && start === null) start = times[i];
    if (!parked && start !== null) {
      shapes.push({
        type: "rect", xref: "x", yref: yref || "paper", x0: t(start), x1: t(times[i - 1]), y0: 0, y1: 1,
        fillcolor: PAPER_2, line: { width: 0 }, layer: "below",
      });
      start = null;
    }
  }
  return shapes;
}

// Day names along the top of a chart
function dayAnnotations(days) {
  return days.map(([day, text, bold]) => ({
    xref: "x", yref: "paper", x: `${day} 12:00:00`, y: 1, yanchor: "bottom", showarrow: false,
    text: bold ? `<b>${text}</b>` : text, font: { size: 13, color: bold ? ACCENT : MUTED },
  }));
}

// A thin vertical line at each midnight
function midnightLines(days) {
  return days.map((day) => ({
    type: "line", xref: "x", yref: "paper", x0: `${day} 00:00:00`, x1: `${day} 00:00:00`, y0: 0, y1: 1,
    line: { color: RULE, width: 1 },
  }));
}

// Markers at the minutes where a yes/no signal is true, at height y on one row
function flagTrace(tractor, key, row, y, color, label) {
  const m = data.minutes[tractor];
  const x = m.minute.filter((_, j) => m[key][j]).map(t);
  return {
    type: "scatter", mode: "markers", x, y: x.map(() => y), yaxis: row.axis,
    marker: { symbol: "square", size: 4, color },
    hovertemplate: `${tractor} ${label} %{x|%H:%M}<extra></extra>`,
  };
}

// ---------- Section 1 ----------

function drawCauses() {
  el("causes").innerHTML = ORDER.map((cause) => `
    <div class="cause-row">
      <span class="name" style="color:${CAUSES[cause].color}"><span class="dot" style="background:${CAUSES[cause].color}"></span>${CAUSES[cause].label}</span>
      <span class="action">${CAUSES[cause].action}</span>
      <span class="code">${data.meta.actions[cause]}</span>
    </div>`).join("");
}

// ---------- Shared lanes ----------

// Every tractor gets its own thin track inside a lane, T1 on top
function trackY(tractor) {
  const list = tractors();
  return list.length - list.indexOf(tractor) - 0.5;
}

// The y axis for a lane, with the tractor names as its ticks
function trackAxis(row) {
  const list = tractors();
  return yAxis(row, {
    range: [0, list.length], tickvals: list.map(trackY), ticktext: list,
    tickfont: { size: 10, color: FAINT },
  });
}

// A small lane name on the left edge
function laneTitle(row) {
  return {
    xref: "paper", yref: `${row.axis} domain`, x: -0.005, y: 0.5, xanchor: "right",
    text: row.id, showarrow: false, font: { size: 12, color: MUTED },
  };
}

// The light band behind a lane
function laneTrack(row) {
  return {
    type: "rect", xref: "paper", yref: `${row.axis} domain`, x0: 0, x1: 1, y0: 0, y1: 1,
    fillcolor: PAPER_2, line: { width: 0 }, layer: "below",
  };
}

// The weakest-signal row: one line per tractor and each tractor's cutoff
function signalRow(row, layout, traces) {
  const thresholds = data.thresholds ? data.thresholds.tractors : {};
  layout[row.key] = yAxis(row, { range: [0, 48], tickvals: [0, 20, 40] });
  layout.annotations.push(rowTitle(row, "Signal"));
  // T1 is drawn last, so it sits on top where the lines agree
  for (const tractor of tractors().slice().reverse()) {
    const m = data.minutes[tractor];
    traces.push({
      type: "scatter", mode: "lines", x: m.minute.map(t), y: m.signal_weakest_db, yaxis: row.axis,
      line: { color: TRACTOR_COLORS[tractor], width: 1.1 },
      hovertemplate: `${tractor} %{x|%b %d %H:%M}<br>weakest satellite %{y} dB-Hz<extra></extra>`,
    });
    const cut = (thresholds[tractor] || {}).bad_below_signal_weakest_db;
    if (cut) layout.shapes.push(cutoffLine(row, cut));
  }
}

function tractorLegend() {
  return tractors().map((tractor) =>
    `<span><span class="swatch line" style="background:${TRACTOR_COLORS[tractor]}"></span>${tractor}</span>`);
}

// ---------- Section 2 ----------

// The x range for one day, or null for every day
function dayRange(day) {
  if (!day) return null;
  const next = new Date(Date.parse(`${day}T00:00:00Z`) + 24 * 3600 * 1000).toISOString().slice(0, 10);
  return [`${day} 00:00:00`, `${next} 00:00:00`];
}

// The buttons that show every day or one day
function drawDataDays() {
  const days = dayList();
  el("data-days").innerHTML = [null, ...days].map((day) => `
    <button type="button" class="pill" data-day="${day || ""}" aria-pressed="${day === view.dataDay}">${day ? dayName(day) : `All ${days.length} days`}</button>`).join("");
  el("data-days").querySelectorAll("button").forEach((button) =>
    button.addEventListener("click", () => {
      view.dataDay = button.dataset.day || null;
      drawDataChart();
    })
  );
}

function drawDataChart() {
  drawDataDays();
  const cutoffs = data.meta.cutoffs;
  const feeds = data.space_feeds;
  const fleet = [
    { id: "Signal", weight: 3, kind: "signal" },
    { id: "Labels", weight: 1.1, kind: "labels" },
    { id: "Link lost", weight: 0.9, kind: "flag", flag: "base_link_lost", color: INK, label: "correction link lost" },
    { id: "Off row", weight: 0.9, kind: "flag", flag: "off_row", color: CAUSES.SPOOFING.color, label: "off the row" },
  ];
  const debug = view.debugRows
    ? [
        { id: "Sats", weight: 1.3, kind: "minutes", key: "num_sats_min", title: "fewest satellites" },
        { id: "Fix", weight: 1.3, kind: "minutes", key: "fix_rank_worst", title: "fix (4 = RTK fixed)", shape: "hv" },
        { id: "Bad", weight: 1.3, kind: "bad" },
      ]
    : [];
  const feedRows = [
    { id: "Kp", weight: 1.4, kind: "kp", small: "storm level" },
    { id: "Dst", weight: 1.4, kind: "dst", small: "field drop" },
    { id: "S4", weight: 1.4, kind: "s4", small: "flicker" },
    { id: "Reports", weight: 0.7, kind: "reports" },
  ];
  const rows = stackRows([...fleet, ...debug, ...feedRows], 0.02);
  const layout = baseLayout(view.debugRows ? 880 : 680, dayRange(view.dataDay));
  if (!view.dataDay) {
    layout.xaxis.autorange = true;
    delete layout.xaxis.range;
  }
  const traces = [];

  for (const row of rows) {
    if (row.kind === "signal") {
      signalRow(row, layout, traces);
      continue;
    }
    if (row.kind === "labels" || row.kind === "flag") {
      layout[row.key] = trackAxis(row);
      layout.annotations.push(laneTitle(row));
      layout.shapes.push(laneTrack(row));
      if (row.kind === "labels") {
        traces.push(...laneTraces(data.labels, row,
          () => ({ opacity: 1, pattern: "", dot: 8 }),
          (label) => hoverLines(label, [`Label ${label.id}`])));
      } else {
        for (const tractor of tractors()) {
          traces.push(flagTrace(tractor, row.flag, row, trackY(tractor), row.color, row.label));
        }
      }
      continue;
    }
    layout.annotations.push(rowTitle(row, row.id, row.small));

    if (row.kind === "minutes") {
      layout[row.key] = yAxis(row, { title: { text: row.title, font: { size: 11, color: FAINT } } });
      for (const tractor of tractors()) {
        const m = data.minutes[tractor];
        traces.push({
          type: "scatter", mode: "lines", x: m.minute.map(t), y: m[row.key], yaxis: row.axis,
          line: { color: TRACTOR_COLORS[tractor], width: 1.2, shape: row.shape || "linear" },
          hovertemplate: `${tractor} %{x|%H:%M}<br>${row.title}: %{y}<extra></extra>`,
        });
      }
    } else if (row.kind === "bad") {
      layout[row.key] = yAxis(row, { type: "category", categoryarray: tractors().slice().reverse() });
      for (const tractor of tractors()) {
        const m = data.minutes[tractor];
        const x = m.minute.filter((_, j) => m.bad[j]).map(t);
        traces.push({
          type: "scatter", mode: "markers", x, y: x.map(() => tractor), yaxis: row.axis,
          marker: { symbol: "square", size: 4, color: INK },
          hovertemplate: `${tractor} stage 4 calls this minute bad %{x|%H:%M}<extra></extra>`,
        });
      }
    } else if (row.kind === "kp") {
      // Kp comes every 3 hours, so each bar covers its 3 hours
      const kp = feeds.storm_kp;
      layout[row.key] = yAxis(row, { range: [0, 9], tickvals: [0, 5, 9] });
      traces.push({
        type: "bar", x: kp.ts.map(t), y: kp.storm_kp, yaxis: row.axis, width: 3 * 3600 * 1000 * 0.85, offset: 0,
        marker: { color: kp.storm_kp.map((v) => (v >= cutoffs.STORM_KP ? CAUSES.SPACE_WEATHER.color : QUIET)) },
        hovertemplate: `storm level (Kp) %{y}<br>%{x|%b %d %H:%M}<extra></extra>`,
      });
      layout.shapes.push(cutoffLine(row, cutoffs.STORM_KP));
    } else if (row.kind === "dst") {
      const dst = feeds.storm_field_drop;
      layout[row.key] = yAxis(row, { tickvals: [0, -200, -400] });
      traces.push({
        type: "scatter", mode: "lines", x: dst.ts.map(t), y: dst.storm_field_drop_nt, yaxis: row.axis,
        line: { color: CAUSES.SPACE_WEATHER.color, width: 1.8 },
        hovertemplate: `magnetic field drop (Dst) %{y} nT<br>%{x|%b %d %H:%M}<extra></extra>`,
      });
      layout.shapes.push(cutoffLine(row, cutoffs.STORM_FIELD_DROP_NT));
    } else if (row.kind === "s4") {
      const s4 = feeds.signal_flicker_s4;
      layout[row.key] = yAxis(row, { range: [0, 0.85], tickvals: [0, 0.3, 0.8] });
      traces.push({
        type: "scatter", mode: "lines", x: s4.ts.map(t), y: s4.signal_flicker_s4, yaxis: row.axis,
        line: { color: CAUSES.SPACE_WEATHER.color, width: 1.8 },
        hovertemplate: `signal flicker (S4) %{y}<br>%{x|%b %d %H:%M}<extra></extra>`,
      });
      layout.shapes.push(cutoffLine(row, cutoffs.HIGH_FLICKER_S4));
    } else if (row.kind === "reports") {
      // Advisories as gray squares, interference reports as red triangles
      layout[row.key] = yAxis(row, { range: [0, 1], showticklabels: false });
      const adv = feeds.advisories;
      traces.push({
        type: "scatter", mode: "markers", x: adv.issued.map(t), y: adv.issued.map(() => 0.5), yaxis: row.axis,
        marker: { symbol: "square", size: 12, color: QUIET },
        text: adv.text.map((text, j) => `${adv.advisory_id[j]}: ${escapeHtml(text)}`),
        hovertemplate: `%{x|%b %d %H:%M}<br>%{text}<extra></extra>`,
      });
      const rfi = feeds.interference_reports;
      traces.push({
        type: "scatter", mode: "markers", x: rfi.received.map(t), y: rfi.received.map(() => 0.5), yaxis: row.axis,
        marker: { symbol: "triangle-up", size: 14, color: CAUSES.JAMMING.color },
        text: rfi.text.map((text, j) => `${rfi.report_id[j]} (confidence ${rfi.confidence[j]}): ${escapeHtml(text)}`),
        hovertemplate: `%{x|%b %d %H:%M}<br>%{text}<extra></extra>`,
      });
    }
  }

  // Parked time, the scored evaluation window, midnights and day names
  const [evalStart, evalEnd] = data.meta.windows.eval;
  layout.shapes.push(...parkedShapes());
  layout.shapes.push({
    type: "rect", xref: "x", yref: "paper", x0: t(evalStart), x1: t(evalEnd), y0: 0, y1: 1,
    fillcolor: ACCENT, opacity: 0.05, line: { width: 0 }, layer: "below",
  });
  layout.shapes.push(...midnightLines(["2026-05-05", "2026-05-06"]));
  layout.annotations.push(...dayAnnotations([
    ["2026-05-04", "May 4, development"], ["2026-05-05", "May 5, development"],
    ["2026-05-06", "May 6, evaluation (scored)", true],
  ]));

  Plotly.react("data-chart", traces, layout, PLOT_CONFIG);

  el("data-legend").innerHTML = [
    ...tractorLegend(),
    `<span class="legend-title">Training labels</span>`,
    ...ORDER.map((c) => `<span><span class="swatch" style="background:${CAUSES[c].color}"></span>${CAUSES[c].label}</span>`),
    `<span><svg width="12" height="10" viewBox="0 0 12 10" aria-hidden="true"><path d="M0 10L6 0l6 10Z" fill="${CAUSES.JAMMING.color}"></path></svg>interference report</span>`,
    `<span><span class="swatch" style="background:${QUIET}"></span>space weather advisory</span>`,
    `<span><span class="swatch cutoff"></span>cutoff</span>`,
  ].join("");
}

// ---------- Section 3 ----------

function drawRules() {
  el("stages").innerHTML = STAGES.map(([group, stages], i) => `
    <div class="stage-group">
      <div>
        <h3>${group}</h3>
        <ol>${stages.map(([n, name, what]) => `<li><span class="mono">${n}</span><span><strong>${name}</strong> <span class="what">${what}</span></span></li>`).join("")}</ol>
      </div>
      ${i < STAGES.length - 1 ? `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="${QUIET}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"></path></svg>` : ""}
    </div>`).join("");

  el("tests").innerHTML = `<table class="tbl">
    <thead><tr><th>Cause</th><th>Passes when</th></tr></thead>
    <tbody>${ORDER.map((c) => `<tr><td style="white-space:nowrap;width:200px;font-weight:700;color:${CAUSES[c].color}">${CAUSES[c].label}</td><td>${escapeHtml(data.meta.tests[c])}</td></tr>`).join("")}</tbody>
  </table>`;

  if (!data.thresholds) {
    el("thresholds").innerHTML = `<p class="error">No thresholds.json yet: run python run.py</p>`;
    return;
  }
  el("thresholds").innerHTML = `<table class="tbl">
    <thead><tr><th>Tractor</th><th class="num">Working minutes</th><th class="num">Normal signal</th><th class="num">Normal weakest satellite</th><th class="num">Bad below</th></tr></thead>
    <tbody>${Object.entries(data.thresholds.tractors).map(([tractor, v]) => `<tr>
      <td style="font-weight:700">${tractor}</td><td class="num">${v.working_minutes.toLocaleString("en-US")}</td>
      <td class="num">${v.normal_signal_mean_db.toFixed(1)} dB-Hz</td><td class="num">${v.normal_signal_weakest_db.toFixed(1)} dB-Hz</td>
      <td class="num" style="font-weight:700">${v.bad_below_signal_weakest_db.toFixed(1)} dB-Hz</td></tr>`).join("")}</tbody>
  </table>`;
}

// ---------- Section 4 ----------

// Hover text for a label or detection
function hoverLines(item, extra) {
  return [
    `<b>${CAUSES[item.class].label}</b> ${item.tractors.join(", ")}`,
    `${hhmm(item.start)} to ${hhmm(item.end)} (${lengthText(item.start, item.end)})`,
    ...extra,
  ].join("<br>");
}

// Bars on one lane, one per item per tractor and one trace per cause; short ones also get a dot so they show
function laneTraces(items, row, styleFor, hoverFor) {
  const traces = [];
  for (const cause of ORDER) {
    const mine = items
      .filter((item) => item.class === cause)
      .flatMap((item) => item.tractors.map((tractor) => ({ item, y: trackY(tractor), style: styleFor(item) })));
    if (!mine.length) continue;
    traces.push({
      type: "bar", orientation: "h", yaxis: row.axis,
      y: mine.map((m) => m.y), base: mine.map((m) => t(m.item.start)),
      x: mine.map((m) => Date.parse(m.item.end) - Date.parse(m.item.start)),
      width: 0.7,
      marker: {
        color: CAUSES[cause].color, opacity: mine.map((m) => m.style.opacity),
        pattern: { shape: mine.map((m) => m.style.pattern), fgcolor: PAPER, solidity: 0.4 },
        line: { width: 0 },
      },
      hovertext: mine.map((m) => hoverFor(m.item)), hoverinfo: "text",
    });
    const short = mine.filter((m) => minutesBetween(m.item.start, m.item.end) < 15);
    if (short.length) {
      traces.push({
        type: "scatter", mode: "markers", yaxis: row.axis,
        x: short.map((m) => t(m.item.start)), y: short.map((m) => m.y),
        marker: { color: CAUSES[cause].color, size: short.map((m) => m.style.dot), symbol: "diamond", opacity: short.map((m) => m.style.opacity) },
        hovertext: short.map((m) => hoverFor(m.item)), hoverinfo: "text",
      });
    }
  }
  return traces;
}

function drawDevChart() {
  if (!data.matches) {
    el("dev-chart").innerHTML = `<p class="error">No development predictions yet: run python run.py --window dev</p>`;
    return;
  }
  const labelInfo = Object.fromEntries(data.matches.labels.map((l) => [l.label_id, l]));
  const rows = stackRows([
    { id: "Signal", weight: 2.6, kind: "signal" },
    { id: "Labels", weight: 1.1, kind: "labels" },
    { id: "My calls", weight: 1.1, kind: "mine" },
    { id: "Short dips", weight: 1, kind: "free" },
  ], 0.025);
  const [devStart, devEnd] = data.meta.windows.dev;
  const layout = baseLayout(460, [t(devStart), t(devEnd)]);
  const traces = [];

  for (const row of rows) {
    if (row.kind === "signal") {
      signalRow(row, layout, traces);
      continue;
    }
    layout[row.key] = trackAxis(row);
    layout.annotations.push(laneTitle(row));
    layout.shapes.push(laneTrack(row));

    if (row.kind === "labels") {
      traces.push(...laneTraces(data.labels, row,
        (label) => (labelInfo[label.id]?.status === "hit" ? { opacity: 1, pattern: "", dot: 8 } : { opacity: 1, pattern: "/", dot: 8 }),
        (label) => hoverLines(label, [`Label ${label.id}: <b>${(labelInfo[label.id] || {}).status || "?"}</b>`])));
    } else {
      const free = row.kind === "free";
      const detections = data.matches.detections.filter((d) => (d.status === "exempt") === free);
      traces.push(...laneTraces(detections, row,
        (d) => ({ opacity: free ? 0.45 : 1, pattern: d.status === "false_alarm" ? "x" : "", dot: free ? 4 : 8 }),
        (d) => {
          const info = d.label_id ? labelInfo[d.label_id] : null;
          const extra = [d.status === "exempt" ? "short multipath (not scored)" : `<b>${d.status.replace("_", " ")}</b>${d.label_id ? ` (${d.label_id})` : ""}`];
          if (info && info.time_iou !== undefined) extra.push(`time IoU ${info.time_iou.toFixed(2)}, onset ${info.onset_min >= 0 ? "+" : ""}${info.onset_min.toFixed(0)} min`);
          extra.push(`confidence ${d.confidence.toFixed(2)}`);
          return hoverLines(d, extra);
        }));
    }
  }

  layout.shapes.push(...parkedShapes());
  layout.shapes.push(...midnightLines(["2026-05-05"]));
  layout.annotations.push(...dayAnnotations([["2026-05-04", "May 4"], ["2026-05-05", "May 5"]]));
  Plotly.react("dev-chart", traces, layout, PLOT_CONFIG);

  el("dev-legend").innerHTML = [
    ...tractorLegend(),
    ...ORDER.map((c) => `<span><span class="swatch" style="background:${CAUSES[c].color}"></span>${CAUSES[c].label}</span>`),
  ].join("");
}

function drawScorecard() {
  const m = data.matches;
  if (!m) return;
  el("figures").innerHTML = `<strong>${m.total.toFixed(1)} / 40</strong>
    <p>Development score. Average score across the five causes ${m.macro_f1.toFixed(2)} (25 pts), onset credit ${m.mean_onset.toFixed(2)} (15 pts),
    actions agree ${m.actions_agreed} / ${m.labels.length}, ${m.free_multipath} short multipath reports not scored.</p>`;

  el("cause-score").innerHTML = `<table class="tbl">
    <thead><tr><th>Cause</th><th class="num">Labels</th><th class="num">Hits</th><th class="num">False alarms</th><th class="num">Misses</th><th class="num">Cause score</th></tr></thead>
    <tbody>${ORDER.map((cause) => {
      const c = m.counts[cause];
      return `<tr><td style="font-weight:700;color:${CAUSES[cause].color}">${CAUSES[cause].label}</td>
        <td class="num">${c.hits + c.missed}</td><td class="num">${c.hits}</td><td class="num">${c.false}</td>
        <td class="num">${c.missed}</td><td class="num">${c.f1.toFixed(2)}</td></tr>`;
    }).join("")}</tbody>
  </table>`;

  const labelsById = Object.fromEntries(data.labels.map((l) => [l.id, l]));
  const resultNames = { hit: "Hit", missed: "Missed", wrong_cause: "Wrong cause" };
  el("label-table").innerHTML = `<table class="tbl">
    <thead><tr><th>Label</th><th>Cause</th><th>Tractors</th><th>Start</th><th>Result</th><th class="num">Time IoU</th><th class="num">Onset</th></tr></thead>
    <tbody>${m.labels.slice(0, view.allLabels ? m.labels.length : 3).map((entry) => {
      const label = labelsById[entry.label_id];
      const onset = entry.onset_min === undefined ? "" : entry.onset_min === 0 ? "on time" : `${entry.onset_min > 0 ? "+" : "−"}${Math.abs(entry.onset_min).toFixed(0)} min`;
      return `<tr><td class="mono">${entry.label_id}</td>
        <td style="color:${CAUSES[label.class].color};font-weight:600;white-space:nowrap">${CAUSES[label.class].label}</td>
        <td>${label.tractors.join(", ")}</td><td class="mono" style="white-space:nowrap">${dayName(label.start)} ${hhmm(label.start)}</td>
        <td class="result ${entry.status}">${resultNames[entry.status]}</td>
        <td class="num mono">${entry.time_iou === undefined ? "" : entry.time_iou.toFixed(2)}</td><td class="num mono">${onset}</td></tr>`;
    }).join("")}</tbody>
  </table>`;

  // Three labels to start with, and a button for the rest
  const more = el("labels-more");
  more.hidden = m.labels.length <= 3;
  more.textContent = view.allLabels ? "Show fewer labels" : `Show all ${m.labels.length} labels`;
  more.setAttribute("aria-expanded", view.allLabels);
}

// ---------- Section 5 ----------

// The days that have data, as "2026-05-04"
function dayList() {
  return [...new Set(data.minutes[tractors()[0]].minute.map((text) => text.slice(0, 10)))];
}

// The episodes on the chosen day, oldest first, with multipath hidden unless asked
function dayEpisodes() {
  return (data.episodes || [])
    .filter((e) => e.start.slice(0, 10) === view.day)
    .filter((e) => view.showMultipath || e.class !== "MULTIPATH")
    .sort((a, b) => a.start.localeCompare(b.start));
}

// Minutes since midnight on the chosen day, as a share of the day
function dayShare(text) {
  const minutes = (Date.parse(text) - Date.parse(`${view.day}T00:00:00Z`)) / 60000;
  return Math.max(0, Math.min(1, minutes / 1440));
}

function drawEval() {
  const days = dayList();
  if (!view.day) view.day = data.meta.windows.eval[0].slice(0, 10);
  const evalDay = data.meta.windows.eval[0].slice(0, 10);

  el("days").innerHTML = days.map((day) => `
    <button type="button" class="pill" data-day="${day}" aria-pressed="${day === view.day}">${dayName(day)}<small>${day >= evalDay ? "evaluation" : "development"}</small></button>`).join("");
  el("days").querySelectorAll("button").forEach((button) =>
    button.addEventListener("click", () => {
      view.day = button.dataset.day;
      view.picked = null;
      drawEval();
    })
  );

  const allOnDay = (data.episodes || []).filter((e) => e.start.slice(0, 10) === view.day);
  const multipathCount = allOnDay.filter((e) => e.class === "MULTIPATH").length;
  el("multipath-label").textContent = `Show multipath (${multipathCount})`;

  const episodes = dayEpisodes();
  episodes.forEach((e, i) => (e.index = i));
  if (view.picked === null || view.picked >= episodes.length) {
    // Start on the highest-confidence call that day
    view.picked = episodes.reduce((best, e, i) => (e.confidence > (episodes[best] || {}).confidence ? i : best), 0);
  }

  drawField(episodes);
  drawEpisodeList(episodes);
  drawDetail(episodes[view.picked]);
}

// One strip per tractor: parked time, the real weakest-signal line, and a block per episode
function drawField(episodes) {
  const rows = tractors().map((tractor) => {
    const m = data.minutes[tractor];

    // Minutes on this day, as x 0-1440 and y 0-72 (45 dB-Hz at the top)
    let path = "";
    let pen = false;
    const parked = [];
    let parkStart = null;
    m.minute.forEach((minute, j) => {
      if (minute.slice(0, 10) !== view.day) return;
      const x = dayShare(minute) * 1440;
      if (!m.working[j]) {
        if (parkStart === null) parkStart = x;
        pen = false;
        return;
      }
      if (parkStart !== null) {
        parked.push([parkStart, x]);
        parkStart = null;
      }
      const value = m.signal_weakest_db[j];
      if (value === null) {
        pen = false;
        return;
      }
      const y = 68 - (Math.min(value, 45) / 45) * 64;
      path += `${pen ? "L" : "M"}${x.toFixed(0)} ${y.toFixed(1)}`;
      pen = true;
    });
    if (parkStart !== null) parked.push([parkStart, 1440]);

    const blocks = episodes.filter((e) => e.tractors.includes(tractor)).map((e) => {
      const left = dayShare(e.start) * 100;
      const width = Math.max((dayShare(e.end) - dayShare(e.start)) * 100, 0.1);
      const color = CAUSES[e.class].color;
      return `<button type="button" class="block${e.index === view.picked ? " picked" : ""}" data-index="${e.index}"
        aria-label="${CAUSES[e.class].label} on ${tractor}, ${hhmm(e.start)} to ${hhmm(e.end)}"
        style="left:${left}%;width:${width}%;border-top-color:${color};background:${color}22"></button>`;
    }).join("");

    return `<div class="field-row"><span class="id">${tractor}</span>
      <div class="strip">
        ${parked.map(([a, b]) => `<span class="parked" style="left:${(a / 14.4).toFixed(2)}%;width:${((b - a) / 14.4).toFixed(2)}%">${b - a > 120 ? "parked" : ""}</span>`).join("")}
        ${blocks}
        <svg viewBox="0 0 1440 72" preserveAspectRatio="none" width="100%" height="72" aria-hidden="true">
          <path d="${path}" fill="none" stroke="${INK}" stroke-width="1.6" stroke-linejoin="round" vector-effect="non-scaling-stroke"></path>
        </svg>
      </div></div>`;
  });
  rows.push(`<div class="hours"><span style="width:28px;flex:none"></span><div><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00 UTC</span></div></div>`);
  el("field").innerHTML = rows.join("");
  el("field").querySelectorAll(".block").forEach((block) =>
    block.addEventListener("click", () => {
      view.picked = Number(block.dataset.index);
      drawEval();
    })
  );
}

function drawEpisodeList(episodes) {
  const count = `${episodes.length} ${episodes.length === 1 ? "episode" : "episodes"} on ${dayName(view.day)}`;
  el("ep-list").innerHTML = `<div class="count">${count}</div>` + episodes.map((e) => `
    <button type="button" data-index="${e.index}" aria-pressed="${e.index === view.picked}">
      <span class="dot" style="width:10px;height:10px;background:${CAUSES[e.class].color}"></span>
      <span class="when">${hhmm(e.start)}–${hhmm(e.end)}</span>
      <span class="what">${CAUSES[e.class].label} <span>${e.tractors.join(" ")}</span></span>
      <span class="conf">${e.confidence.toFixed(2)}</span>
    </button>`).join("");
  el("ep-list").querySelectorAll("button").forEach((button) =>
    button.addEventListener("click", () => {
      view.picked = Number(button.dataset.index);
      drawEval();
    })
  );
}

// Icons for each kind of evidence line
const SIGN_ICONS = {
  seen: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#0a5640" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="Seen, supports the call"><path d="M4 10.5l4 4 8-9"></path></svg>`,
  nothing_against: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#0a5640" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="Nothing against the call"><path d="M4 10.5l4 4 8-9"></path></svg>`,
  against: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#b3261e" stroke-width="2.4" stroke-linecap="round" role="img" aria-label="Against the call"><path d="M5 5l10 10M15 5L5 15"></path></svg>`,
  not_seen: `<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="#878b91" stroke-width="2.4" stroke-linecap="round" role="img" aria-label="Not seen"><path d="M5 10h10"></path></svg>`,
};
const SIGN_WORDS = { seen: "Seen", nothing_against: "Nothing against", against: "Against", not_seen: "Not seen" };

function drawDetail(e) {
  if (!e) {
    el("detail").innerHTML = `<p class="meta">No episodes on ${dayName(view.day)}${view.showMultipath ? "" : " (multipath hidden)"}.</p>`;
    return;
  }
  const cause = CAUSES[e.class];
  let tag = "";
  if (e.status === "hit") tag = `<span class="tag">Matches ${e.label_id}</span>`;
  else if (e.status === "exempt") tag = `<span class="tag grey">Short dip, not scored</span>`;
  else if (e.status === "false_alarm") tag = `<span class="tag bad">False alarm${e.label_id ? ` (${e.label_id})` : ""}</span>`;
  else if (e.status === "eval") tag = `<span class="tag grey">Evaluation day, no label to check against</span>`;

  el("detail").innerHTML = `
    <div>
      <p class="meta">${dayName(e.start)}, ${e.tractors.join(", ")}, ${hhmm(e.start)} to ${hhmm(e.end)} UTC (${lengthText(e.start, e.end)})</p>
      <div class="head">
        <h3 style="color:${cause.color}">${cause.label}</h3>
        <span><span class="big">${e.confidence.toFixed(2)}</span> <small>confidence</small></span>
      </div>
      ${tag}
    </div>
    <p class="why">${escapeHtml(e.meaning.charAt(0).toUpperCase() + e.meaning.slice(1))}.</p>
    <div class="action-row">
      <span class="label-small">Action</span>
      <strong>${cause.action}</strong>
      <span class="mono" style="font-size:13px;color:${MUTED}">${e.action}</span>
    </div>
    <div>
      <div class="label-small" style="margin-bottom:4px">Evidence</div>
      <ul class="signs">${e.signs.map((s) => `<li>${SIGN_ICONS[s.state]}<span><strong>${SIGN_WORDS[s.state]}: ${escapeHtml(s.label)}</strong> <span class="detail-text">(${escapeHtml(s.detail)})</span></span></li>`).join("")}</ul>
      ${e.notes.length ? `<ul class="notes">${e.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>` : ""}
    </div>
    <div>
      <div class="formula">confidence = ${e.formula}</div>
      <p class="formula-key">${formulaKey()}</p>
    </div>`;
}

// What each part of the confidence sum means, from the pipeline's own settings
function formulaKey() {
  const c = data.meta.confidence;
  if (!c) return "";
  return `Starts at ${c.start.toFixed(2)}, plus up to ${c.signs.toFixed(2)} for the share of signs seen, plus ${c.bonus.toFixed(2)} per bonus sign, ` +
    `minus ${c.penalty.toFixed(2)} per sign against. It never goes above ${c.cap.toFixed(2)}.`;
}

// ---------- Section 6 ----------

function drawDeepDive(name) {
  const dive = data.deep_dives && data.deep_dives[name];
  if (!dive) {
    el(`dive-${name}`).innerHTML = `<p class="error">No deep-dive data: run python -m demo.build</p>`;
    return;
  }
  const [start, end] = dive.window;
  const calls = (data.episodes || []).filter(
    (e) => e.class !== "MULTIPATH" && e.start < end && e.end > start
  );
  const rows = stackRows([
    { id: "Signal", weight: 3, kind: "signal" },
    { id: "Off row", weight: 1.6, kind: "xte" },
    ...calls.map((call) => ({ id: "", weight: 0.5, kind: "call", call })),
  ], 0.03);
  const layout = baseLayout(380 + calls.length * 34, [t(start), t(end)]);
  layout.margin.l = 72;
  const traces = [];

  for (const row of rows) {
    if (row.kind === "signal") {
      layout[row.key] = yAxis(row, { range: [-4, 48], tickvals: [0, 20, 40] });
      layout.annotations.push(rowTitle(row, "Signal"));
      for (const [tractor, values] of Object.entries(dive.tractors)) {
        traces.push({
          type: "scatter", mode: "lines", x: values.ts.map(t), y: values.signal_weakest_db, yaxis: row.axis,
          line: { color: TRACTOR_COLORS[tractor], width: tractor === "T1" ? 2 : 1.6 },
          hovertemplate: `${tractor} %{x|%H:%M:%S}<br>weakest satellite %{y} dB-Hz<extra></extra>`,
        });
        // Correction link lost, as ticks under the lines
        const lost = values.ts.filter((_, j) => values.base_link_lost[j]).map(t);
        const lane = { T1: 3, T2: 1, T3: -1 }[tractor];
        traces.push({
          type: "scatter", mode: "markers", x: lost, y: lost.map(() => lane), yaxis: row.axis,
          marker: { symbol: "square", size: 3, color: TRACTOR_COLORS[tractor] },
          hovertemplate: `${tractor} correction link lost %{x|%H:%M:%S}<extra></extra>`,
        });
      }
    } else if (row.kind === "xte") {
      layout[row.key] = yAxis(row, { type: "log", range: [-2, Math.log10(30)], dtick: 1 });
      layout.annotations.push(rowTitle(row, "Off row"));
      for (const [tractor, values] of Object.entries(dive.tractors)) {
        traces.push({
          type: "scatter", mode: "lines", x: values.ts.map(t), y: values.cross_track_error_m, yaxis: row.axis,
          line: { color: TRACTOR_COLORS[tractor], width: 1.4 },
          hovertemplate: `${tractor} %{x|%H:%M:%S}<br>off the row %{y} m<extra></extra>`,
        });
      }
      const cut = Math.log10(data.meta.cutoffs.BAD_CROSS_TRACK_ERROR_M);
      layout.shapes.push({ ...cutoffLine(row, 0), y0: cut, y1: cut });
    } else {
      // One bar per call in the window, labeled with its cause and confidence
      const call = row.call;
      const color = CAUSES[call.class].color;
      layout[row.key] = yAxis(row, { range: [0, 1], showticklabels: false });
      traces.push({
        type: "bar", orientation: "h", yaxis: row.axis, y: [0.5], base: [t(call.start)],
        x: [Date.parse(call.end) - Date.parse(call.start)], width: 0.9, marker: { color },
        hovertext: [hoverLines(call, [`confidence ${call.confidence.toFixed(2)}`])], hoverinfo: "text",
      });
      layout.annotations.push({
        xref: "x", yref: row.axis, x: t(call.start > start ? call.start : start), y: 0.5, xanchor: "left",
        text: `<b>${CAUSES[call.class].label} on ${call.tractors.join(", ")}, ${call.confidence.toFixed(2)}</b>`,
        showarrow: false, font: { size: 12, color: PAPER }, bgcolor: color, borderpad: 2,
      });
    }
  }
  Plotly.react(`dive-${name}`, traces, layout, PLOT_CONFIG);

  el(`dive-${name}-calls`).innerHTML = calls.map((call) => `
    <div class="call-card" style="--cause:${CAUSES[call.class].color}">
      <strong>${CAUSES[call.class].label} on ${call.tractors.join(", ")}</strong>
      <span class="when"> ${hhmm(call.start)}–${hhmm(call.end)}</span>
      <div class="formula">confidence = ${call.formula}</div>
      <ul class="notes">${call.signs.map((s) => `<li>${SIGN_WORDS[s.state]}: ${escapeHtml(s.label)}</li>`).join("")}${call.notes.map((n) => `<li>${escapeHtml(n)}</li>`).join("")}</ul>
    </div>`).join("");
}

// ---------- Linked zoom ----------

// Zooming one timeline zooms the other to match
function linkZoom() {
  for (const id of LINKED) {
    const chart = el(id);
    if (!chart.on || chart.dataset.linked) continue;
    chart.dataset.linked = "yes";
    chart.on("plotly_relayout", (event) => {
      if (syncing) return;
      let range = null;
      if (event["xaxis.range[0]"] !== undefined) range = [event["xaxis.range[0]"], event["xaxis.range[1]"]];
      else if (event["xaxis.range"]) range = event["xaxis.range"];
      else if (event["xaxis.autorange"]) return resetZoom();
      if (!range) return;
      syncing = true;
      Promise.all(LINKED.filter((other) => other !== id && el(other).layout).map((other) => Plotly.relayout(other, { "xaxis.range": range })))
        .finally(() => (syncing = false));
    });
  }
}

// Double-click puts each timeline back to its own full window
function resetZoom() {
  syncing = true;
  view.dataDay = null;
  drawDataDays();
  const [devStart, devEnd] = data.meta.windows.dev;
  Promise.all([
    el("data-chart").layout && Plotly.relayout("data-chart", { "xaxis.autorange": true }),
    el("dev-chart").layout && Plotly.relayout("dev-chart", { "xaxis.range": [t(devStart), t(devEnd)] }),
  ]).finally(() => (syncing = false));
}

// ---------- Nav ----------

function highlightNav() {
  const links = [...document.querySelectorAll(".rail .num")];
  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        links.forEach((link) => {
          const on = link.hash === `#${entry.target.id}`;
          link.classList.toggle("active", on);
          link.setAttribute("aria-current", on ? "true" : "false");
        });
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
  el("load-error").hidden = true;
  try {
    await loadData();
    drawCauses();
    drawDataChart();
    drawRules();
    drawDevChart();
    drawScorecard();
    drawEval();
    drawDeepDive("clear");
    linkZoom();
    // The build time on this computer's clock
    const built = new Date(data.meta.built).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    status.textContent = `Built ${built}`;
  } catch (error) {
    console.error(error);
    status.innerHTML = `<span class="error">Couldn't load</span>`;
    el("load-error").hidden = false;
  }
}

// Reload: the server rebuilds the JSON from the latest run.py outputs, then the page redraws
async function reload() {
  const button = el("reload");
  button.disabled = true;
  el("status").textContent = "Rebuilding…";
  try {
    const response = await fetch("rebuild", { method: "POST" });
    if (!response.ok) throw new Error(`rebuild failed (${response.status})`);
    await drawAll();
  } catch (error) {
    el("status").innerHTML = `<span class="error">${escapeHtml(error.message)}</span>`;
  } finally {
    button.disabled = false;
  }
}

el("reload").addEventListener("click", reload);
el("debug-rows").addEventListener("change", (event) => {
  view.debugRows = event.target.checked;
  drawDataChart();
});
el("labels-more").addEventListener("click", () => {
  view.allLabels = !view.allLabels;
  drawScorecard();
});
el("show-multipath").addEventListener("change", (event) => {
  view.showMultipath = event.target.checked;
  view.picked = null;
  drawEval();
});
highlightNav();
drawAll();
