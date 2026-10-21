// Interactive accuracy-vs-latency chart with Pareto frontiers, for <div class="pareto-chart" data-src="...">.
// Data: docs/assets/engines.json, written by bench/naga/plot.py from the bench results (the same points
// as hero.png). The overall frontier is always drawn; a kind's own frontier appears while the pointer
// (or keyboard focus) is on one of its points or on its legend entry. Plain SVG, no library.
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var W = 720, H = 400, M = { l: 70, r: 16, t: 12, b: 48 };
  var XMIN = 20, XMAX = 30000;   // plot.py XMIN, XMAX

  function el(name, attrs, parent) {
    var e = document.createElementNS(NS, name);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }

  // Fastest first; keep each engine more accurate than every faster one (plot.py's frontier()).
  function frontier(points) {
    var sorted = points.slice().sort(function (a, b) { return a.ms - b.ms || b.acc - a.acc; });
    var out = [], best = -Infinity;
    sorted.forEach(function (p) { if (p.acc > best) { out.push(p); best = p.acc; } });
    return out;
  }

  function marker(kind, x, y, r, parent) {
    if (kind.shape === "s") return el("rect", { x: x - r, y: y - r, width: 2 * r, height: 2 * r, rx: 1.5 }, parent);
    if (kind.shape === "^") return el("path", { d: "M" + x + "," + (y - r * 1.25) + "L" + (x + r * 1.15) + "," + (y + r * 0.85) +
                                                "L" + (x - r * 1.15) + "," + (y + r * 0.85) + "Z" }, parent);
    return el("circle", { cx: x, cy: y, r: r }, parent);
  }

  function draw(root, data) {
    var kinds = data.kinds, kindIndex = {};
    kinds.forEach(function (k, i) { kindIndex[k.name] = i; });
    var all = [];
    data.panels.forEach(function (p) { p.points.forEach(function (q) { all.push(q.acc); }); all.push(p.baseline); });
    var YMIN = Math.floor((Math.min.apply(null, all) - 4) / 10) * 10, YMAX = 100;

    // Legend first, in one row above the panels: hovering a kind shows its frontier in every panel.
    var legend = document.createElement("div");
    legend.className = "pareto-legend";
    kinds.forEach(function (k, i) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "pareto-key k" + i;
      var s = el("svg", { width: 14, height: 14, viewBox: "0 0 14 14", "aria-hidden": "true" });
      marker(k, 7, 7, 5, s).setAttribute("class", "pareto-dot k" + i);
      b.appendChild(s);
      b.appendChild(document.createTextNode(" " + k.name));
      ["mouseenter", "focus"].forEach(function (ev) { b.addEventListener(ev, function () { highlight(i, null); }); });
      ["mouseleave", "blur"].forEach(function (ev) { b.addEventListener(ev, function () { highlight(null, null); }); });
      legend.appendChild(b);
    });
    var key = document.createElement("span");
    key.className = "pareto-key-frontier";
    key.textContent = "— Pareto frontier: nothing is both faster and more accurate";
    legend.appendChild(key);
    root.appendChild(legend);

    var grid = document.createElement("div");
    grid.className = "pareto-panels";
    root.appendChild(grid);
    var tip = document.createElement("div");
    tip.className = "pareto-tip";
    tip.hidden = true;
    root.appendChild(tip);
    var panelsDrawn = [];

    data.panels.forEach(function (panel) {
      var fig = document.createElement("div");
      fig.className = "pareto-panel";
      var cap = document.createElement("div");
      cap.className = "pareto-caption";
      cap.textContent = panel.title;
      fig.appendChild(cap);
      var svg = el("svg", { viewBox: "0 0 " + W + " " + H, role: "img",
                            "aria-label": panel.title + ": top-1 accuracy against median latency per engine" });
      fig.appendChild(svg);
      grid.appendChild(fig);
      var x = function (ms) { return M.l + (Math.log10(ms) - Math.log10(XMIN)) / (Math.log10(XMAX) - Math.log10(XMIN)) * (W - M.l - M.r); };
      var y = function (acc) { return H - M.b - (acc - YMIN) / (YMAX - YMIN) * (H - M.t - M.b); };

      var axes = el("g", { "class": "pareto-axes" }, svg);
      for (var v = YMIN; v <= YMAX; v += 10) {
        el("line", { x1: M.l, x2: W - M.r, y1: y(v), y2: y(v), "class": "pareto-grid" }, axes);
        el("text", { x: M.l - 6, y: y(v) + 4, "text-anchor": "end" }, axes).textContent = v + "%";
      }
      [100, 1000, 10000].forEach(function (t) {
        el("line", { x1: x(t), x2: x(t), y1: M.t, y2: H - M.b, "class": "pareto-grid" }, axes);
        el("text", { x: x(t), y: H - M.b + 16, "text-anchor": "middle" }, axes).textContent = t >= 1000 ? t / 1000 + " s" : t + " ms";
      });
      el("text", { x: (M.l + W - M.r) / 2, y: H - 8, "text-anchor": "middle", "class": "pareto-title" }, axes).textContent =
        "median latency per decision (log scale)";
      el("text", { x: 14, y: (M.t + H - M.b) / 2, "text-anchor": "middle", "class": "pareto-title",
                   transform: "rotate(-90 14 " + (M.t + H - M.b) / 2 + ")" }, axes).textContent = "top-1 accuracy";
      el("line", { x1: M.l, x2: W - M.r, y1: y(panel.baseline), y2: y(panel.baseline), "class": "pareto-baseline" }, axes);
      el("text", { x: W - M.r - 4, y: y(panel.baseline) - 5, "text-anchor": "end", "class": "pareto-note" }, axes).textContent = "keyword search alone";

      function stepPath(pts) {
        if (!pts.length) return "";
        var d = "M" + x(pts[0].ms) + "," + y(pts[0].acc);
        for (var i = 1; i < pts.length; i++) d += "H" + x(pts[i].ms) + "V" + y(pts[i].acc);
        return d + "H" + (W - M.r);
      }
      el("path", { d: stepPath(frontier(panel.points)), "class": "pareto-front" }, svg);
      var kindFronts = kinds.map(function (k, i) {
        return el("path", { d: stepPath(frontier(panel.points.filter(function (p) { return p.kind === k.name; }))),
                            "class": "pareto-front-kind k" + i }, svg);
      });

      var marks = panel.points.map(function (p) {
        var i = kindIndex[p.kind], g = el("g", { "class": "pareto-point k" + i, tabindex: 0,
          "aria-label": p.label + ", " + p.kind + ": " + p.acc + "% in " + p.ms + " ms" }, svg);
        el("circle", { cx: x(p.ms), cy: y(p.acc), r: 14, "class": "pareto-hit" }, g);   // a target bigger than the mark
        marker(kinds[i], x(p.ms), y(p.acc), 6, g).setAttribute("class", "pareto-dot k" + i);
        el("text", { x: x(p.ms) + (p.dx === undefined ? 9 : p.dx), y: y(p.acc) - (p.dy === undefined ? 7 : p.dy), "class": "pareto-label" }, g).textContent = p.label;
        function on() {
          highlight(i, p);
          var box = root.getBoundingClientRect(), r = g.getBoundingClientRect();
          tip.replaceChildren();
          var b = document.createElement("strong"); b.textContent = p.label; tip.appendChild(b);
          tip.appendChild(document.createElement("br"));
          tip.appendChild(document.createTextNode(p.kind));
          tip.appendChild(document.createElement("br"));
          tip.appendChild(document.createTextNode(p.acc + "% right, " + (p.ms >= 1000 ? (p.ms / 1000).toFixed(1) + " s" : Math.round(p.ms) + " ms")));
          tip.hidden = false;
          tip.style.left = Math.min(r.right - box.left + 8, box.width - 220) + "px";
          tip.style.top = (r.top - box.top - 8) + "px";
        }
        function off() { highlight(null, null); tip.hidden = true; }
        g.addEventListener("mouseenter", on); g.addEventListener("focus", on);
        g.addEventListener("mouseleave", off); g.addEventListener("blur", off);
        return { g: g, p: p, kind: i };
      });
      panelsDrawn.push({ marks: marks, kindFronts: kindFronts });
    });

    function highlight(kind, point) {
      root.classList.toggle("pareto-focus", kind !== null);
      panelsDrawn.forEach(function (pd) {
        pd.kindFronts.forEach(function (f, i) { f.classList.toggle("on", i === kind); });
        pd.marks.forEach(function (m) {
          m.g.classList.toggle("dim", kind !== null && m.kind !== kind);
          m.g.classList.toggle("on", point !== null && m.p.engine === point.engine);
        });
      });
    }

    // The same numbers as a table, for readers who cannot use the chart.
    var det = document.createElement("details");
    var sum = document.createElement("summary");
    sum.textContent = "Show the numbers as a table";
    det.appendChild(sum);
    data.panels.forEach(function (panel) {
      var t = document.createElement("table"), cap = document.createElement("caption");
      cap.textContent = panel.title;
      t.appendChild(cap);
      var head = t.insertRow();
      ["Engine", "Kind", "Top-1 accuracy", "Median latency", "On the frontier"].forEach(function (h) {
        var th = document.createElement("th"); th.textContent = h; head.appendChild(th);
      });
      var front = frontier(panel.points).map(function (p) { return p.engine; });
      panel.points.slice().sort(function (a, b) { return b.acc - a.acc; }).forEach(function (p) {
        var r = t.insertRow();
        [p.label, p.kind, p.acc + "%", Math.round(p.ms) + " ms", front.indexOf(p.engine) >= 0 ? "yes" : ""].forEach(function (c) {
          r.insertCell().textContent = c;
        });
      });
      det.appendChild(t);
    });
    root.appendChild(det);
  }

  function init() {
    document.querySelectorAll(".pareto-chart:not([data-drawn])").forEach(function (root) {
      root.setAttribute("data-drawn", "1");
      fetch(root.getAttribute("data-src")).then(function (r) { return r.json(); })
        .then(function (data) { draw(root, data); })
        .catch(function () { root.textContent = "The interactive chart could not load; the image above shows the same data."; });
    });
  }
  // Material's instant navigation swaps pages without a reload: document$ fires on each page.
  if (window.document$) window.document$.subscribe(init); else document.addEventListener("DOMContentLoaded", init);
})();
