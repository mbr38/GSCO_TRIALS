// Builds the two §9 diagrams as a .pptx, one slide per diagram,
// matching the §8 house style (GSCO_Section8_Diagrams.pptx) exactly:
// 13.33×7.5 custom layout, Arial, rounded rectangles with thin borders,
// the locked palette, thin 555555 triangle-head connectors.
const Pptx = require("pptxgenjs");
const pptx = new Pptx();
pptx.defineLayout({ name: "GSCO", width: 13.33, height: 7.5 });
pptx.layout = "GSCO";

const RR = pptx.ShapeType.roundRect;
const LINE = pptx.ShapeType.line;

// ---- locked palette (fill / line / text) -------------------------------
const PAL = {
  air:     { fill: "CDD9E6", line: "3F5F86", text: "16263C" },
  ghg:     { fill: "CFE0DF", line: "3F7370", text: "163230" },
  nature:  { fill: "CFE2C8", line: "487A40", text: "1D3418" },
  orch:    { fill: "AEBACD", line: "1F2C47", text: "0F1830" },
  infra:   { fill: "E7E9ED", line: "4B5563", text: "1F2937" },
  iface:   { fill: "E5E7EB", line: "374151", text: "111827" },
};
const CLUSTER = { fill: "F4F5F7", line: "C2C8D0" };
const RED = "C0392B";
const ARROW = "555555";
const LAV = "F3E6F7"; // annotation chip fill, as in §8

// ---- helpers -----------------------------------------------------------
function cluster(s, x, y, w, h, title) {
  s.addShape(RR, { x, y, w, h, fill: { color: CLUSTER.fill },
    line: { color: CLUSTER.line, width: 1.0 }, rectRadius: 0.06 });
  s.addText(title, { x: x, y: y + 0.06, w: w, h: 0.34, align: "center",
    valign: "middle", fontFace: "Arial", fontSize: 13, bold: true, color: "1F2937" });
}

function box(s, x, y, w, h, pal, title, opts = {}) {
  const lw = pal === PAL.orch ? 2.2 : 1.25;
  s.addShape(RR, { x, y, w, h, fill: { color: pal.fill },
    line: { color: pal.line, width: lw }, rectRadius: 0.06 });
  const runs = [{ text: title, options: { bold: true, fontSize: opts.size || 12,
    color: pal.text, breakLine: true } }];
  (opts.subs || []).forEach((sub) =>
    runs.push({ text: sub.t, options: { fontSize: sub.size || 10,
      color: sub.red ? RED : pal.text, italic: !!sub.italic, breakLine: true } }));
  s.addText(runs, { x, y, w, h, align: "center", valign: "middle",
    fontFace: "Arial", lineSpacingMultiple: 0.98, margin: 3 });
}

// double-square composite token, as in §8
function composite(s, x, y, sz, title, subs) {
  s.addShape(RR, { x, y, w: sz, h: sz, fill: { color: PAL.orch.fill },
    line: { color: PAL.orch.line, width: 2.5 }, rectRadius: 0.04 });
  const i = 0.17;
  s.addShape(RR, { x: x + i, y: y + i, w: sz - 2 * i, h: sz - 2 * i,
    fill: { color: PAL.orch.fill }, line: { color: PAL.orch.line, width: 1.0 }, rectRadius: 0.03 });
  const runs = [{ text: title, options: { bold: true, fontSize: 12, color: PAL.orch.text, breakLine: true } }];
  (subs || []).forEach((t) => runs.push({ text: t, options: { fontSize: 9.5, color: PAL.orch.text, breakLine: true } }));
  s.addText(runs, { x, y, w: sz, h: sz, align: "center", valign: "middle", fontFace: "Arial", lineSpacingMultiple: 0.98 });
}

// straight connector with a triangle head. dir: 'down'|'right'|'left'|'up'
function arrow(s, x, y, w, h, dir) {
  const o = { x, y, w: Math.abs(w), h: Math.abs(h),
    line: { color: ARROW, width: 1.5 } };
  if (dir === "left" || dir === "up") o.line.beginArrowType = "triangle";
  else o.line.endArrowType = "triangle";
  if (dir === "left") o.flipH = true;
  if (dir === "up") o.flipV = true;
  s.addShape(LINE, o);
}

// plain segment, no arrowhead (for building elbows)
function seg(s, x, y, w, h) {
  s.addShape(LINE, { x, y, w: Math.abs(w), h: Math.abs(h), line: { color: ARROW, width: 1.5 } });
}

function chip(s, x, y, w, runs) {
  s.addShape(RR, { x, y, w, h: 0.3, fill: { color: LAV },
    line: { color: "C9B6D6", width: 0.75 }, rectRadius: 0.04 });
  s.addText(runs, { x, y, w, h: 0.3, align: "center", valign: "middle",
    fontFace: "Arial", fontSize: 8.5, color: "5B3A6B" });
}

// =======================================================================
// SLIDE 1 — §9.1 Application workflow and page structure
// =======================================================================
{
  const s = pptx.addSlide();
  s.addText("GSCO tool — workflow and page structure", { x: 0.5, y: 0.12, w: 12.3, h: 0.3,
    fontFace: "Arial", fontSize: 11, italic: true, color: "6B7280", align: "left" });

  // ENTRY band (top)
  cluster(s, 0.5, 0.55, 12.33, 1.45, "ENTRY  —  landing → scope → hub");
  box(s, 0.9, 1.05, 3.1, 0.8, PAL.iface, "Landing & user-type",
    { subs: [{ t: "P-01 · Policy Maker / MNC", red: false }] });
  box(s, 4.85, 1.05, 3.1, 0.8, PAL.iface, "Scope Setup",
    { subs: [{ t: "P-02 · node / region / none", red: false }] });
  box(s, 9.0, 1.05, 3.4, 0.8, PAL.orch, "Workflow Hub",
    { subs: [{ t: "P-03 · router (branch point)", red: false }] });
  arrow(s, 4.0, 1.45, 0.85, 0, "right");
  arrow(s, 7.95, 1.45, 1.05, 0, "right");

  // branch down to the two workflows
  arrow(s, 3.5, 2.0, 0, 0.55, "down");   // hub -> inspect (elbow drawn via vertical from band)
  arrow(s, 9.6, 2.0, 0, 0.55, "down");   // hub -> prioritisation

  // INSPECT cluster (left)
  cluster(s, 0.5, 2.6, 6.0, 2.55, "INSPECT WORKFLOW  —  screening · monitoring · reporting");
  box(s, 0.85, 3.15, 2.5, 0.85, PAL.iface, "Inspect — Setup",
    { subs: [{ t: "P-04 · centre · radius · indicators", red: false }] });
  box(s, 3.75, 3.15, 2.4, 0.85, PAL.orch, "Screening Results",
    { subs: [{ t: "P-05 · traffic-light + drill-down", red: false }] });
  arrow(s, 3.35, 3.575, 0.4, 0, "right");
  box(s, 3.75, 4.25, 2.4, 0.75, PAL.nature, "Trend View",
    { subs: [{ t: "P-06 · per-indicator, on demand", red: false }] });
  arrow(s, 4.95, 4.0, 0, 0.25, "down");
  s.addText("drill-down", { x: 5.1, y: 4.02, w: 1.0, h: 0.2, fontFace: "Arial", fontSize: 8, italic: true, color: "6B7280" });

  // PRIORITISATION cluster (right)
  cluster(s, 6.83, 2.6, 6.0, 2.55, "PRIORITISATION WORKFLOW  —  batch");
  box(s, 7.2, 3.15, 2.5, 0.85, PAL.iface, "Prioritisation — Setup",
    { subs: [{ t: "P-07 · ≤ 20 nodes · one radius", red: false }] });
  box(s, 10.1, 3.15, 2.4, 0.85, PAL.orch, "Prioritisation — Results",
    { subs: [{ t: "P-08 · ranked table · risk matrix", red: false }] });
  arrow(s, 9.7, 3.575, 0.4, 0, "right");

  // PERSISTENT MODULES band (bottom)
  cluster(s, 0.5, 5.5, 12.33, 1.6, "PERSISTENT MODULES  —  save & reuse");
  box(s, 0.95, 6.05, 3.5, 0.85, PAL.infra, "Saved Analyses",
    { subs: [{ t: "P-10 · re-open without recompute", red: false }] });
  box(s, 4.9, 6.05, 3.5, 0.85, PAL.infra, "Reports",
    { subs: [{ t: "P-11 · template · preview · export", red: false }] });
  box(s, 8.85, 6.05, 3.5, 0.85, PAL.infra, "Indicator Library",
    { subs: [{ t: "P-09 · reference catalogue", red: false }] });

  // result views -> save (P-05 straight to Reports; P-08 elbows back to Reports)
  arrow(s, 4.95, 5.15, 0, 0.9, "down");   // P-05 -> Reports
  s.addText("save as report →", { x: 5.05, y: 5.22, w: 1.6, h: 0.2, fontFace: "Arial", fontSize: 8, italic: true, color: "6B7280" });
  seg(s, 11.3, 4.0, 0, 1.3);              // P-08 down
  seg(s, 6.65, 5.3, 4.65, 0);             // left along the gutter
  arrow(s, 6.65, 5.3, 0, 0.75, "down");   // into Reports
}

// =======================================================================
// SLIDE 2 — §9.7 Parent-platform interface round-trip
// =======================================================================
{
  const s = pptx.addSlide();
  s.addText("Parent-platform integration — node-keyed screening round-trip", { x: 0.5, y: 0.12, w: 12.3, h: 0.3,
    fontFace: "Arial", fontSize: 11, italic: true, color: "6B7280", align: "left" });

  // GSCO map node (left)
  box(s, 0.55, 2.55, 2.7, 1.5, PAL.iface, "GSCO platform map",
    { size: 12, subs: [
      { t: "app.cambridge-gsco.co.uk", red: true, size: 9.5 },
      { t: "supply-chain node (click)", red: false, size: 9.5 } ] });

  // Inspect Setup (no-login entry)
  box(s, 4.0, 2.55, 2.6, 1.5, PAL.iface, "Inspect — Setup",
    { size: 12, subs: [
      { t: "no-login entry; lat/lon pre-filled", red: false, size: 9 },
      { t: "user sets radius · indicators · mode", red: false, size: 9 } ] });

  // ScreeningRun engine
  box(s, 7.35, 2.7, 2.4, 1.2, PAL.orch, "ScreeningRun",
    { size: 12, subs: [
      { t: "engine/orchestrator.py", red: true, size: 9 },
      { t: "air → ghg → nature", red: false, size: 9 } ] });

  // Result token (double-square composite) far right
  composite(s, 10.6, 2.45, 1.85, "Screening result",
    ["headline scores", "+ coverage flag", "+ detail + provenance"]);

  // forward arrows
  arrow(s, 3.25, 3.3, 0.75, 0, "right");
  arrow(s, 6.6, 3.3, 0.75, 0, "right");
  arrow(s, 9.75, 3.3, 0.85, 0, "right");

  // request-contract chip (GSCO -> tool)
  chip(s, 2.95, 1.95, 4.55, [
    { text: "GSCO → tool:  ", options: { bold: true } },
    { text: "node_id · latitude · longitude · name", options: {} } ]);
  arrow(s, 5.2, 2.25, 0, 0.3, "down");

  // response-contract chip (tool -> GSCO), on the return path
  // return path: result (bottom) -> left along bottom -> up into map node
  arrow(s, 11.5, 4.3, 0, 1.0, "down");          // result down
  arrow(s, 1.9, 5.3, 9.6, 0, "left");           // along the bottom, head pointing left toward map
  arrow(s, 1.9, 4.05, 0, 1.25, "up");           // up into the map node

  chip(s, 4.3, 5.02, 5.0, [
    { text: "tool → GSCO (on save):  ", options: { bold: true } },
    { text: "result keyed by node_id · replace-on-rerun", options: {} } ]);

  // partial-coverage mandatory-flag callout
  box(s, 9.65, 5.55, 3.2, 1.1, PAL.ghg, "Partial-coverage flag",
    { size: 11, subs: [
      { t: 'coverage = "full" | "partial"', red: true, size: 9 },
      { t: "partial result must be flagged on the map", red: false, size: 9, italic: true } ] });
  arrow(s, 11.5, 5.3, 0, 0.25, "down");

  // theming note
  s.addText([
    { text: "UI theming:  ", options: { bold: true } },
    { text: "Streamlit restyled to the parent platform's tokens (ui/theme/) — designed & implemented; the map↔tool wiring is specified, not yet live.", options: {} } ],
    { x: 0.55, y: 6.85, w: 8.9, h: 0.45, fontFace: "Arial", fontSize: 9, italic: true, color: "6B7280", valign: "top" });
}

pptx.writeFile({ fileName: "GSCO_Section9_Diagrams.pptx" }).then((f) => console.log("wrote", f));
