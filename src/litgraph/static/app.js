// litgraph: the knowledge graph (canvas, live physics) and the research companion (chat) on one page.
// No libraries: the layout is a small force simulation (charge, springs, collision, a pull to the middle).

const MEMORY_KEY = "litgraph_chat_v1";
const THEME_KEY = "litgraph_theme_v1";
const MAX_MEMORY = 12;
const EXPORTED = window.LITGRAPH_EXPORT || null; // a file from `litgraph export`: graph inside, no server

// The five levels (docs/GRAPH_SCHEMA.md), in order.
const TYPE_ORDER = ["family", "technique", "paper", "claim", "quantity"];
const LEVEL_NUMBER = { family: 1, technique: 2, paper: 3, claim: 4, quantity: 5 };
const RADIUS = { family: 11, technique: 6.5, paper: 5, claim: 6, quantity: 6 };
const CHARGE = { family: -1200, technique: -180, paper: -120, claim: -200, quantity: -200 };
const LINK_DISTANCE = { contains: 75, uses: 70, extends: 70, contrasts: 110, supports: 90, contradicts: 90, about: 95, validates: 90, relates: 100, bridge: 120 };
const LINK_STRENGTH = { contains: 0.7, uses: 0.4, extends: 0.5, contrasts: 0.25, supports: 0.35, contradicts: 0.35, about: 0.3, validates: 0.3, relates: 0.25, bridge: 0.12 };
const ALWAYS_LABELLED = new Set(["family", "quantity"]);
const VALIDATION_LEVELS = ["structural", "thermodynamic", "kinetic", "transport", "mechanistic"];
const CLAIM_STATUSES = ["supported", "contradicted", "contested", "hypothesis", "open"];
const LEVEL_HELP = {
  structural: "Structural: distributions of structure (radial distribution function, site occupancy, coordination).",
  thermodynamic: "Thermodynamic: free-energy differences, equilibrium populations.",
  kinetic: "Kinetic: residence times, transition probabilities, hop rates.",
  transport: "Transport: mean squared displacement, diffusivity, correlation factor.",
  mechanistic: "Mechanistic: migration pathways, cooperative events, environment-dependent transitions.",
};
const CLAIM_HELP = {
  supported: "Supported: at least one paper in the graph gives evidence for it.",
  contradicted: "Contradicted: at least one paper in the graph gives evidence against it.",
  contested: "Contested: papers in the graph point both ways.",
  hypothesis: "Hypothesis: the reviewer's judgement; no direct evidence recorded yet.",
  open: "Open: an unanswered question; nothing in the graph settles it.",
};
const STATUS_TEXT = {
  seed: "From the original review", proposed: "Proposed by the agent, not kept yet",
  chat: "Added from a conversation and kept", search: "Added from a search and kept", manual: "Added by you", extract: "Extracted from notes", review: "From the original review",
};
// How a link reads from the side of the node whose card is open: [heading, edge label shown?]
function linkHeading(node, edge, other) {
  const out = edge.source === node.id;
  switch (edge.type) {
    case "contains": return out ? (other.type === "paper" ? "Papers in this family" : "Techniques in this family") : "Part of";
    case "uses": return out ? "Techniques used" : "Used in";
    case "extends": return out ? "Builds on" : "Extended by";
    case "contrasts": return "Compared with";
    case "supports": return out ? "Gives evidence for" : "Supported by";
    case "contradicts": return out ? "Gives evidence against" : "Contradicted by";
    case "about": return out ? "About" : "Claims about it";
    case "validates": return out ? "Reports evidence for" : "Reported in";
    default: return "Related";
  }
}
function statusText(node) {
  if (node.status === "proposed") return STATUS_TEXT.proposed;
  if (node.status === "seed") return STATUS_TEXT.seed;
  return STATUS_TEXT[node.source] || "Confirmed";
}
// Fields per level, beyond label / summary / aliases: [key, label, kind]. kind: text, textarea, int, select:<name>, multi:<name>
const TYPE_FIELDS = {
  family: [["keeps", "Keeps or learns", "textarea"], ["discards", "Gives up", "textarea"], ["computes", "Still has to run", "textarea"], ["relevance", "Relevance to the question (1-5)", "int"]],
  technique: [["reference", "Reference (a citation, or the id of its defining paper)", "text"]],
  paper: [["year", "Year", "int"], ["venue", "Venue", "text"], ["authors", "Authors", "text"], ["doi", "DOI", "text"], ["url", "URL", "text"],
          ["learns", "What it learns", "textarea"], ["discards", "What it leaves out", "textarea"], ["validated_at", "Evidence reported at", "multi:levels"], ["priority", "Reading priority", "int"]],
  claim: [["claim_status", "Status", "select:claim"], ["scope", "Where it holds", "text"]],
  quantity: [["level", "Validation level", "select:levels"], ["definition", "How it is computed (object, data, computation)", "textarea"], ["symbol", "Symbol", "text"], ["units", "Units", "text"]],
};

const $ = (selector) => document.querySelector(selector);
const el = {
  shell: $(".app-shell"), canvas: $("#graph-canvas"), stage: $("#graph-stage"), search: $("#graph-search"), searchResults: $("#search-results"),
  legend: $("#legend"), hint: $("#graph-hint"),
  card: $("#node-card"), kind: $("#node-kind"), status: $("#node-status"), title: $("#node-title"), meta: $("#node-meta"), summary: $("#node-summary"), links: $("#node-links"),
  explain: $("#explain-node"), expand: $("#expand-node"), edit: $("#edit-node"), confirm: $("#confirm-node"), remove: $("#delete-node"),
  chat: $("#chat-panel"), openChat: $("#open-chat"), closeChat: $("#close-chat"), clearChat: $("#clear-chat"), chatModel: $("#chat-model"),
  contextBar: $("#context-bar"), contextChip: $("#context-chip"), messages: $("#messages"), suggestions: $("#suggestions"),
  form: $("#chat-form"), question: $("#question"), send: $("#send-question"),
  dialog: $("#edit-dialog"), editForm: $("#edit-form"), editTitle: $("#edit-title"), editError: $("#edit-error"), editLinks: $("#edit-links"), linkList: $("#edit-link-list"),
  linkTarget: $("#link-target"), linkType: $("#link-type"), linkLabel: $("#link-label"), linkAdd: $("#link-add"), nodeOptions: $("#node-options"),
};

const state = {
  graph: null, nodeTypes: {}, edgeTypes: {}, nodesById: new Map(), edgesByNode: new Map(),
  sim: null, alpha: 1, alphaTarget: 0, frame: null, homesSet: false, fitPending: true,
  hiddenKinds: new Set(), hoverId: null, selectedId: null, pinnedId: null, transform: { x: 0, y: 0, k: 1 }, size: null, ratio: 1,
  pointer: null, viewTouched: false, colours: null, lastFocus: null, focusSince: 0, labelled: new Set(),
  health: { ai: false, model: "" }, busy: null, chatOpen: true, autoFollow: true, pendingLinks: [], editingId: null, highlight: new Set(),
  topic: null, topics: [],
};

// ---------- theme ----------
const darkQuery = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : { matches: false, addEventListener() {} };
function applyTheme() {
  let saved = null;
  try { saved = localStorage.getItem(THEME_KEY); } catch { /* private mode */ }
  const dark = saved ? saved === "dark" : darkQuery.matches;
  document.documentElement.classList.toggle("dark", dark);
  if (state.graph) { readColours(); draw(); }
}
$("#toggle-theme").addEventListener("click", () => {
  const dark = !document.documentElement.classList.contains("dark");
  try { localStorage.setItem(THEME_KEY, dark ? "dark" : "light"); } catch { /* ignore */ }
  applyTheme();
});
darkQuery.addEventListener?.("change", applyTheme);
applyTheme();

// ---------- the graph ----------
function indexGraph(payload, options = {}) {
  state.graph = payload.graph;
  if (payload.topic) { state.topicInfo = payload.topic; updateTopicBar(); }
  state.nodeTypes = payload.node_types || state.nodeTypes;
  state.edgeTypes = payload.edge_types || state.edgeTypes;
  state.nodesById = new Map(state.graph.nodes.map((node) => [node.id, node]));
  state.edgesByNode = new Map(state.graph.nodes.map((node) => [node.id, []]));
  for (const edge of state.graph.edges) {
    state.edgesByNode.get(edge.source)?.push(edge);
    state.edgesByNode.get(edge.target)?.push(edge);
  }
  buildSimulation(options.keepPositions ? state.sim : null);
  buildLegend();
  fillTypeSelects();
  if (state.selectedId && !state.nodesById.has(state.selectedId)) clearSelection();
  else if (state.selectedId) showNodeCard(state.nodesById.get(state.selectedId));
  startPhysics(options.keepPositions ? 0.3 : 1);
}

function buildSimulation(previous) {
  const old = new Map(previous ? previous.nodes.map((item) => [item.id, item]) : []);
  const sim = { nodes: [], byId: new Map(), links: [], neighbours: new Map() };
  for (const node of state.graph.nodes) {
    const was = old.get(node.id);
    const item = { id: node.id, node, x: was ? was.x : 0, y: was ? was.y : 0, vx: 0, vy: 0, fx: null, fy: null, degree: 0, r: RADIUS[node.type] || 5, fresh: !was && old.size > 0 };
    if (was) { item.hx = was.hx; item.hy = was.hy; }
    sim.nodes.push(item); sim.byId.set(node.id, item); sim.neighbours.set(node.id, new Set());
  }
  for (const edge of state.graph.edges) {
    const source = sim.byId.get(edge.source); const target = sim.byId.get(edge.target);
    if (!source || !target || source === target) continue;
    sim.neighbours.get(edge.source).add(edge.target); sim.neighbours.get(edge.target).add(edge.source);
    sim.links.push({ source, target, edge, distance: LINK_DISTANCE[edge.type] || 100, strength: LINK_STRENGTH[edge.type] || 0.3 });
  }
  for (const item of sim.nodes) {
    item.degree = sim.neighbours.get(item.id).size;
    item.r = Math.min((RADIUS[item.node.type] || 5) + Math.sqrt(item.degree) * 0.9, 26);
  }
  for (const link of sim.links) { const a = link.source.degree + 1; const b = link.target.degree + 1; link.bias = a / (a + b); }
  state.sim = sim;
  state.shown = null;
  if (!previous) seedPositions(); else placeFresh();
  state.alpha = 1;
  state.homesSet = previous ? state.homesSet : false;
}

function seedPositions() {
  const sim = state.sim;
  const hubs = sim.nodes.filter((item) => item.node.type === "family");
  const ring = 160 + hubs.length * 26;
  hubs.forEach((item, index) => { const angle = -Math.PI / 2 + (index / Math.max(hubs.length, 1)) * Math.PI * 2; item.x = Math.cos(angle) * ring; item.y = Math.sin(angle) * ring; });
  const jitter = () => (Math.random() - 0.5) * 60;
  for (const item of sim.nodes) {
    if (hubs.includes(item)) continue;
    const near = [...sim.neighbours.get(item.id)].map((id) => sim.byId.get(id)).filter((other) => hubs.includes(other));
    const mean = (key) => (near.length ? near.reduce((sum, other) => sum + other[key], 0) / near.length : 0);
    item.x = mean("x") * 1.15 + jitter(); item.y = mean("y") * 1.15 + jitter();
  }
}
// New nodes (from a proposal) start next to their neighbours, so they grow out of the graph instead of flying in.
function placeFresh() {
  for (const item of state.sim.nodes) {
    if (!item.fresh) continue;
    const near = [...state.sim.neighbours.get(item.id)].map((id) => state.sim.byId.get(id)).filter((other) => other && !other.fresh);
    const mean = (key) => (near.length ? near.reduce((sum, other) => sum + other[key], 0) / near.length : 0);
    item.x = mean("x") + (Math.random() - 0.5) * 50; item.y = mean("y") + (Math.random() - 0.5) * 50;
    item.hx = undefined; item.hy = undefined;
  }
}

function shownNodes() { if (!state.shown) refreshShown(); return state.shown.nodes; }
function shownLinks() { if (!state.shown) refreshShown(); return state.shown.links; }
// What the level filter lets through. When a level is hidden, two visible nodes that were joined through a hidden
// node get a dashed "bridge" link (families to the techniques their papers use, techniques to the claims about them,
// ...), so the graph stays connected and still says what is derived from what.
const BRIDGE_CAP = 40; // pairs per hidden node: a hub paper with 20 neighbours would otherwise add 190 links
function refreshShown() {
  const hidden = state.hiddenKinds; const sim = state.sim;
  const nodes = sim.nodes.filter((item) => !hidden.has(item.node.type));
  const links = sim.links.filter((link) => !hidden.has(link.source.node.type) && !hidden.has(link.target.node.type));
  const direct = new Set(links.map((link) => `${link.source.id}|${link.target.id}`).concat(links.map((link) => `${link.target.id}|${link.source.id}`)));
  const bridged = new Set();
  for (const item of sim.nodes) {
    if (!hidden.has(item.node.type)) continue;
    const around = [...sim.neighbours.get(item.id)].map((id) => sim.byId.get(id)).filter((other) => other && !hidden.has(other.node.type));
    let made = 0;
    for (let i = 0; i < around.length && made < BRIDGE_CAP; i += 1) for (let j = i + 1; j < around.length && made < BRIDGE_CAP; j += 1) {
      const a = around[i]; const b = around[j]; const key = a.id < b.id ? `${a.id}|${b.id}` : `${b.id}|${a.id}`;
      if (direct.has(`${a.id}|${b.id}`) || bridged.has(key)) continue;
      bridged.add(key); made += 1;
      const da = a.degree + 1; const db = b.degree + 1;
      links.push({ source: a, target: b, edge: { type: "bridge", via: item.node.label, status: "confirmed" }, distance: LINK_DISTANCE.bridge, strength: LINK_STRENGTH.bridge, bias: da / (da + db) });
    }
  }
  const neighbours = new Map(nodes.map((item) => [item.id, new Set()]));
  for (const { source, target } of links) { neighbours.get(source.id)?.add(target.id); neighbours.get(target.id)?.add(source.id); }
  state.shown = { nodes, links, neighbours };
}
function shownNeighbours(id) { if (!state.shown) refreshShown(); return state.shown.neighbours.get(id) || new Set(); }
const isShownNode = (item) => item && !state.hiddenKinds.has(item.node.type);

const VELOCITY_DECAY = 0.4; const HOME_PULL = 0.04; const ALPHA_MIN = 0.001; const ALPHA_DECAY = 1 - Math.pow(ALPHA_MIN, 1 / 300);
function tick() {
  const alpha = state.alpha; const nodes = shownNodes();
  for (let i = 0; i < nodes.length; i += 1) {
    const a = nodes[i]; const chargeA = CHARGE[a.node.type] || -120;
    for (let j = i + 1; j < nodes.length; j += 1) {
      const b = nodes[j];
      let dx = b.x - a.x; let dy = b.y - a.y; let l = dx * dx + dy * dy;
      if (l > 360000) continue;
      if (l < 1) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; l = 1; }
      const pushA = ((CHARGE[b.node.type] || -120) * alpha) / l; const pushB = (chargeA * alpha) / l;
      a.vx += dx * pushA; a.vy += dy * pushA; b.vx -= dx * pushB; b.vy -= dy * pushB;
      const room = a.r + b.r + 10; // never overlap
      if (l < room * room) { const d = Math.sqrt(l); const shift = ((room - d) / d) * 0.3; a.vx -= dx * shift; a.vy -= dy * shift; b.vx += dx * shift; b.vy += dy * shift; }
    }
  }
  for (const link of shownLinks()) {
    const { source, target } = link;
    let dx = target.x + target.vx - source.x - source.vx; let dy = target.y + target.vy - source.y - source.vy;
    let l = Math.sqrt(dx * dx + dy * dy) || 1e-6;
    l = ((l - link.distance) / l) * alpha * link.strength; dx *= l; dy *= l;
    target.vx -= dx * link.bias; target.vy -= dy * link.bias; source.vx += dx * (1 - link.bias); source.vy += dy * (1 - link.bias);
  }
  for (const item of nodes) {
    item.vx -= item.x * 0.012 * alpha; item.vy -= item.y * 0.012 * alpha;
    if (item.hx !== undefined) { item.vx += (item.hx - item.x) * HOME_PULL * alpha; item.vy += (item.hy - item.y) * HOME_PULL * alpha; }
    if (item.fx !== null) { item.x = item.fx; item.y = item.fy; item.vx = 0; item.vy = 0; continue; }
    item.vx *= 1 - VELOCITY_DECAY; item.vy *= 1 - VELOCITY_DECAY; item.x += item.vx; item.y += item.vy;
  }
  state.alpha += (state.alphaTarget - state.alpha) * ALPHA_DECAY;
}
function startPhysics(alpha) {
  if (alpha !== undefined) state.alpha = Math.max(state.alpha, alpha);
  if (state.frame) return;
  const loop = () => {
    tick();
    if (state.fitPending && state.alpha < 0.08) { state.fitPending = false; if (state.selectedId) focusOn(state.selectedId); else fitGraph(); }
    if (!state.homesSet && state.alpha < 0.02) { for (const item of state.sim.nodes) { item.hx = item.x; item.hy = item.y; } state.homesSet = true; }
    if (state.homesSet) for (const item of state.sim.nodes) if (item.hx === undefined && state.alpha < 0.05) { item.hx = item.x; item.hy = item.y; }
    render();
    const settled = state.homesSet ? 0.008 : ALPHA_MIN;
    state.frame = state.alpha > settled || state.alphaTarget > 0 ? requestAnimationFrame(loop) : null;
  };
  state.frame = requestAnimationFrame(loop);
}

// ---------- drawing ----------
function readColours() {
  const style = getComputedStyle(document.documentElement);
  const value = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
  state.colours = { text: value("--text", "#17233a"), link: value("--link", "rgba(70,94,128,.2)"), linkActive: value("--link-active", "#2563eb"),
    halo: value("--halo", "#f7f9fc"), glow: value("--glow", "rgba(37,99,235,.35)"), muted: value("--muted", "#66758c") };
  for (const type of TYPE_ORDER) state.colours[type] = value(`--c-${type}`, "#64748b");
}
const colourOf = (type) => state.colours?.[type] || "#64748b";
const sharpRatio = () => Math.min(window.devicePixelRatio || 1, 2);
function resizeCanvas() {
  const width = el.stage.clientWidth; const height = el.stage.clientHeight; const ratio = sharpRatio();
  if (state.size) { state.transform.x += (width - state.size.width) / 2; state.transform.y += (height - state.size.height) / 2; }
  state.size = { width, height };
  el.canvas.style.width = `${width}px`; el.canvas.style.height = `${height}px`;
  el.canvas.width = Math.round(width * ratio); el.canvas.height = Math.round(height * ratio); state.ratio = ratio;
  draw();
}
function draw() { if (state.drawQueued) return; state.drawQueued = true; requestAnimationFrame(() => { state.drawQueued = false; render(); }); }
const focusId = () => state.hoverId || state.pinnedId || state.selectedId;

function render() {
  if (!state.sim || !state.colours) return;
  const context = el.canvas.getContext("2d"); const { x, y, k } = state.transform; const ratio = state.ratio;
  context.setTransform(1, 0, 0, 1, 0, 0); context.clearRect(0, 0, el.canvas.width, el.canvas.height);
  context.setTransform(ratio * k, 0, 0, ratio * k, ratio * x, ratio * y);
  const focus = focusId(); const near = focus ? new Set([focus, ...shownNeighbours(focus)]) : null;
  const now = performance.now();
  if (focus !== state.lastFocus) { state.lastFocus = focus; state.focusSince = now; }
  const fade = !near ? 1 : Math.min(1, (now - state.focusSince) / 180);
  if (fade < 1) draw();
  const view = { left: -x / k - 60, top: -y / k - 60, right: (el.canvas.width / ratio - x) / k + 60, bottom: (el.canvas.height / ratio - y) / k + 60 };
  const onScreen = (item) => item.x > view.left && item.x < view.right && item.y > view.top && item.y < view.bottom;

  // links: plain, then the focus node's in colour, then proposed ones dashed
  context.lineWidth = 1 / k; context.strokeStyle = state.colours.link; context.globalAlpha = near ? 0.8 - 0.5 * fade : 0.8;
  context.beginPath();
  for (const { source, target, edge } of shownLinks()) {
    if (edge.status === "proposed" || edge.type === "bridge") continue;
    context.moveTo(source.x, source.y); context.lineTo(target.x, target.y);
  }
  context.stroke();
  context.setLineDash([4 / k, 4 / k]); context.beginPath();
  for (const { source, target, edge } of shownLinks()) {
    if (edge.status !== "proposed") continue;
    context.moveTo(source.x, source.y); context.lineTo(target.x, target.y);
  }
  context.stroke();
  context.setLineDash([2 / k, 5 / k]); context.globalAlpha *= 0.7; context.beginPath();
  for (const { source, target, edge } of shownLinks()) {
    if (edge.type !== "bridge") continue;
    context.moveTo(source.x, source.y); context.lineTo(target.x, target.y);
  }
  context.stroke(); context.setLineDash([]);
  if (near) {
    const centre = state.sim.byId.get(focus);
    context.globalAlpha = fade; context.strokeStyle = state.colours.linkActive; context.lineWidth = 1.5 / k; context.beginPath();
    for (const id of shownNeighbours(focus)) { const other = state.sim.byId.get(id); if (isShownNode(other) && isShownNode(centre)) { context.moveTo(centre.x, centre.y); context.lineTo(other.x, other.y); } }
    context.stroke();
  }
  // nodes, one fill per colour
  const nodes = shownNodes(); const batches = new Map();
  for (const item of nodes) {
    if (!onScreen(item)) continue;
    const key = `${item.node.type}|${near && !near.has(item.id) ? 1 : 0}`;
    if (!batches.has(key)) batches.set(key, []); batches.get(key).push(item);
  }
  for (const [key, items] of batches) {
    const [type, faded] = key.split("|");
    context.globalAlpha = faded === "1" ? 1 - 0.8 * fade : 1; context.fillStyle = colourOf(type); context.beginPath();
    for (const item of items) { context.moveTo(item.x + item.r, item.y); context.arc(item.x, item.y, item.r, 0, Math.PI * 2); }
    context.fill();
  }
  // proposed nodes: a dashed ring; highlighted (just added): a halo
  context.globalAlpha = 1; context.lineWidth = 1.5 / k; context.setLineDash([3 / k, 3 / k]); context.strokeStyle = state.colours.text;
  for (const item of nodes) if (item.node.status === "proposed" && onScreen(item)) { context.beginPath(); context.arc(item.x, item.y, item.r + 3 / k, 0, Math.PI * 2); context.stroke(); }
  context.setLineDash([]);
  for (const id of state.highlight) {
    const item = state.sim.byId.get(id); if (!item || !isShownNode(item)) continue;
    context.fillStyle = state.colours.glow; context.globalAlpha = 0.35; context.beginPath(); context.arc(item.x, item.y, item.r + 10 / k, 0, Math.PI * 2); context.fill();
  }
  const glowing = focus && state.sim.byId.get(focus);
  if (glowing && isShownNode(glowing)) {
    context.fillStyle = state.colours.glow;
    for (const [grow, alpha] of [[9, 0.18], [4.5, 0.32]]) { context.globalAlpha = alpha * fade; context.beginPath(); context.arc(glowing.x, glowing.y, glowing.r + grow / k, 0, Math.PI * 2); context.fill(); }
    context.globalAlpha = 1; context.fillStyle = colourOf(glowing.node.type); context.beginPath(); context.arc(glowing.x, glowing.y, glowing.r, 0, Math.PI * 2); context.fill();
  }
  const selected = state.selectedId && state.sim.byId.get(state.selectedId);
  if (selected && isShownNode(selected)) { context.globalAlpha = 1; context.lineWidth = 2.5 / k; context.strokeStyle = state.colours.text; context.beginPath(); context.arc(selected.x, selected.y, selected.r + 3 / k, 0, Math.PI * 2); context.stroke(); }
  const pinned = state.pinnedId && state.sim.byId.get(state.pinnedId);
  if (pinned && isShownNode(pinned)) {
    context.globalAlpha = 1; context.strokeStyle = state.colours.linkActive; context.lineWidth = 2 / k;
    context.beginPath(); context.arc(pinned.x, pinned.y, pinned.r + 7 / k, 0, Math.PI * 2); context.stroke();
    context.lineWidth = 1 / k; context.beginPath(); context.arc(pinned.x, pinned.y, pinned.r + 10.5 / k, 0, Math.PI * 2); context.stroke();
  }
  drawLabels(context, nodes, near, focus, onScreen);
  context.globalAlpha = 1;
}

function drawLabels(context, nodes, near, focus, onScreen) {
  const { k } = state.transform; const zoomed = Math.max(0, Math.min(1, (k - 0.55) / 0.6)); const scale = 1 / Math.max(k, 0.6);
  const candidates = [];
  for (const item of nodes) {
    const isNear = near?.has(item.id);
    let alpha = ALWAYS_LABELLED.has(item.node.type) ? 1 : item.node.type === "technique" ? Math.max(zoomed, item.degree >= 3 ? 0.9 : 0) : zoomed;
    if (near) alpha = isNear ? 1 : Math.min(alpha, 0.12);
    if (alpha >= 0.05 && onScreen(item)) candidates.push({ item, alpha, isNear });
  }
  const before = state.labelled; const now = new Set();
  const rank = ({ item, isNear }) => (item.id === focus ? 4 : isNear ? 3 : ALWAYS_LABELLED.has(item.node.type) ? 2 : 1) * 1000 + (before.has(item.id) ? 500 : 0) + Math.min(item.degree, 499);
  candidates.sort((a, b) => rank(b) - rank(a));
  context.textAlign = "center"; context.textBaseline = "top"; context.lineJoin = "round";
  const cell = 80 / k; const taken = new Map();
  const cellsOf = (box) => { const keys = []; for (let gx = Math.floor(box.left / cell); gx <= Math.floor(box.right / cell); gx += 1) for (let gy = Math.floor(box.top / cell); gy <= Math.floor(box.bottom / cell); gy += 1) keys.push(`${gx},${gy}`); return keys; };
  const overlaps = (box, keys) => keys.some((key) => (taken.get(key) || []).some((other) => box.left < other.right && box.right > other.left && box.top < other.bottom && box.bottom > other.top));
  let font = "";
  for (const { item, alpha, isNear } of candidates) {
    const big = ALWAYS_LABELLED.has(item.node.type); const weight = big ? 700 : 500; const base = big ? 13 : 11;
    if (item.labelWidth === undefined) {
      const max = item.node.type === "claim" ? 44 : 34;
      item.labelText = item.node.label.length > max ? `${item.node.label.slice(0, max - 2)}…` : item.node.label;
      context.font = `${weight} ${base}px Inter, ui-sans-serif, system-ui, sans-serif`; font = ""; item.labelWidth = context.measureText(item.labelText).width;
    }
    const size = base * scale; const width = item.labelWidth * scale; const height = size * 1.2; const gap = 3 / k;
    const left = item.x - width / 2; const top = item.y + item.r + gap;
    const box = { left: left - 2 / k, right: left + width + 2 / k, top, bottom: top + height }; const keys = cellsOf(box);
    if (overlaps(box, keys) && !isNear && !big) continue;
    now.add(item.id); for (const key of keys) { if (!taken.has(key)) taken.set(key, []); taken.get(key).push(box); }
    const wanted = `${weight} ${size}px Inter, ui-sans-serif, system-ui, sans-serif`; if (wanted !== font) { context.font = wanted; font = wanted; }
    context.globalAlpha = alpha; context.lineWidth = 3 / k; context.strokeStyle = state.colours.halo; context.strokeText(item.labelText, item.x, top);
    context.fillStyle = state.colours.text; context.fillText(item.labelText, item.x, top);
  }
  state.labelled = now;
}

// ---------- views ----------
function visibleArea() { return { width: el.stage.clientWidth, height: el.stage.clientHeight }; }
function viewFor(items, maxScale = 1.5) {
  const { width, height } = visibleArea();
  if (!items.length) return { x: width / 2, y: height / 2, k: 1 };
  const xs = items.map((i) => i.x); const ys = items.map((i) => i.y);
  const minX = Math.min(...xs) - 50; const maxX = Math.max(...xs) + 50; const minY = Math.min(...ys) - 50; const maxY = Math.max(...ys) + 60;
  const cardRoom = el.card.hidden || width < 600 ? 0 : 420;
  const k = Math.min(maxScale, Math.max(0.12, Math.min((width - cardRoom) / (maxX - minX), height / (maxY - minY)) * 0.92));
  return { k, x: (width - cardRoom) / 2 - ((minX + maxX) / 2) * k, y: height / 2 - ((minY + maxY) / 2) * k };
}
function fitGraph() { animateTo(viewFor(shownNodes())); }
function focusOn(nodeId) {
  const item = state.sim.byId.get(nodeId); if (!item) return;
  const { width, height } = visibleArea(); const cardRoom = width < 600 ? 0 : 420;
  const distances = [...shownNeighbours(nodeId)].map((id) => state.sim.byId.get(id)).filter((o) => o && isShownNode(o)).map((o) => Math.hypot(o.x - item.x, o.y - item.y)).sort((a, b) => a - b);
  const reach = distances.length ? distances[Math.floor((distances.length - 1) * 0.8)] + 40 : 140;
  const k = Math.min(2, Math.max(0.8, (Math.min(width - cardRoom, height) / 2 - 30) / reach));
  animateTo({ k, x: (width - cardRoom) / 2 - item.x * k, y: height / 2 - item.y * k });
}
function animateTo(target) {
  state.viewTouched = false; const start = { ...state.transform }; const began = performance.now(); cancelAnimationFrame(state.viewFrame);
  const step = (now) => {
    const t = Math.min(1, (now - began) / 300); const ease = 1 - Math.pow(1 - t, 3);
    for (const key of ["x", "y", "k"]) state.transform[key] = start[key] + (target[key] - start[key]) * ease;
    draw(); if (t < 1) state.viewFrame = requestAnimationFrame(step);
  };
  state.viewFrame = requestAnimationFrame(step);
}

// ---------- pointer ----------
function graphPoint(event) { const rect = el.canvas.getBoundingClientRect(); return { x: (event.clientX - rect.left - state.transform.x) / state.transform.k, y: (event.clientY - rect.top - state.transform.y) / state.transform.k }; }
function nodeAt(point) {
  let best = null; let bestDistance = Infinity; const slack = 5 / state.transform.k;
  for (const item of shownNodes()) { const d = Math.hypot(item.x - point.x, item.y - point.y); if (d <= item.r + slack && d < bestDistance) { best = item; bestDistance = d; } }
  return best;
}
el.canvas.addEventListener("pointerdown", (event) => {
  el.canvas.setPointerCapture(event.pointerId);
  const item = nodeAt(graphPoint(event));
  state.pointer = item ? { kind: "node", item, startX: event.clientX, startY: event.clientY, moved: false }
    : { kind: "pan", startX: event.clientX, startY: event.clientY, originX: state.transform.x, originY: state.transform.y, moved: false };
});
el.canvas.addEventListener("pointermove", (event) => {
  const pointer = state.pointer;
  if (!pointer) {
    const item = nodeAt(graphPoint(event)); const id = item ? item.id : null;
    if (id !== state.hoverId) { state.hoverId = id; el.canvas.style.cursor = id ? "pointer" : ""; el.canvas.title = item ? item.node.label : ""; draw(); }
    return;
  }
  const dx = event.clientX - pointer.startX; const dy = event.clientY - pointer.startY;
  if (Math.abs(dx) + Math.abs(dy) > 3) pointer.moved = true;
  if (pointer.kind === "pan") { state.viewTouched = true; state.transform.x = pointer.originX + dx; state.transform.y = pointer.originY + dy; draw(); }
  else if (pointer.moved) { if (!pointer.dragging) { pointer.dragging = true; state.alphaTarget = 0.2; startPhysics(0.2); } const p = graphPoint(event); pointer.item.fx = p.x; pointer.item.fy = p.y; }
});
function endPointer(event) {
  const pointer = state.pointer; state.pointer = null;
  if (el.canvas.hasPointerCapture(event.pointerId)) el.canvas.releasePointerCapture(event.pointerId);
  if (!pointer) return;
  if (pointer.kind === "node") {
    if (pointer.dragging) { pointer.item.hx = pointer.item.fx; pointer.item.hy = pointer.item.fy; pointer.item.fx = null; pointer.item.fy = null; state.alphaTarget = 0; startPhysics(0.3); }
    if (!pointer.moved && event.type === "pointerup") selectNode(pointer.item.id, { fit: true });
  } else if (!pointer.moved && event.type === "pointerup") clearSelection();
}
el.canvas.addEventListener("pointerup", endPointer); el.canvas.addEventListener("pointercancel", endPointer);
el.canvas.addEventListener("pointerleave", () => { if (!state.pointer && state.hoverId) { state.hoverId = null; draw(); } });
el.canvas.addEventListener("wheel", (event) => {
  event.preventDefault(); state.viewTouched = true; cancelAnimationFrame(state.viewFrame);
  const rect = el.canvas.getBoundingClientRect(); const px = event.clientX - rect.left; const py = event.clientY - rect.top;
  const delta = event.deltaY * (event.deltaMode === 1 ? 33 : event.deltaMode === 2 ? 400 : 1);
  const next = Math.min(4, Math.max(0.1, state.transform.k * Math.exp(-delta * (event.ctrlKey ? 0.01 : 0.0018))));
  const old = state.transform.k;
  state.transform.x = px - ((px - state.transform.x) / old) * next; state.transform.y = py - ((py - state.transform.y) / old) * next; state.transform.k = next; draw();
}, { passive: false });
new ResizeObserver(() => { if (state.graph) resizeCanvas(); }).observe(el.stage);

// ---------- legend, search ----------
// The level filter: any subset of the five levels. Hidden levels leave dashed bridges between what they connected.
function buildLegend() {
  el.legend.replaceChildren();
  const counts = new Map();
  for (const node of state.graph.nodes) counts.set(node.type, (counts.get(node.type) || 0) + 1);
  const title = document.createElement("span"); title.className = "legend-title"; title.textContent = "Levels"; el.legend.appendChild(title);
  for (const type of TYPE_ORDER) {
    const button = document.createElement("button"); button.type = "button"; button.setAttribute("aria-pressed", String(!state.hiddenKinds.has(type)));
    button.title = `${state.hiddenKinds.has(type) ? "Show" : "Hide"} level ${LEVEL_NUMBER[type]}: ${state.nodeTypes[type] || type}`;
    const dot = document.createElement("i"); dot.style.background = `var(--c-${type})`;
    button.append(dot, `${LEVEL_NUMBER[type]} ${state.nodeTypes[type] || type} `); const count = document.createElement("small"); count.textContent = counts.get(type) || 0; button.appendChild(count);
    button.addEventListener("click", () => {
      if (state.hiddenKinds.has(type)) state.hiddenKinds.delete(type); else state.hiddenKinds.add(type);
      state.shown = null; buildLegend(); startPhysics(0.5); if (!state.viewTouched) setTimeout(fitGraph, 400);
    });
    el.legend.appendChild(button);
  }
  const allShown = state.hiddenKinds.size === 0;
  const toggle = document.createElement("button"); toggle.type = "button"; toggle.className = "legend-reset"; toggle.textContent = allShown ? "None" : "All";
  toggle.title = allShown ? "Hide every level, then pick the ones to show" : "Show every level";
  toggle.addEventListener("click", () => {
    if (allShown) for (const type of TYPE_ORDER) state.hiddenKinds.add(type); else state.hiddenKinds.clear();
    state.shown = null; buildLegend(); startPhysics(0.4); if (!state.viewTouched) setTimeout(fitGraph, 400);
  });
  el.legend.appendChild(toggle);
}
function showSearchResults(query) {
  const needle = query.trim().toLowerCase();
  if (!needle) { el.searchResults.hidden = true; el.searchResults.replaceChildren(); return; }
  const score = (node) => {
    const names = [node.label.toLowerCase(), ...(node.aliases || []).map((a) => a.toLowerCase())];
    if (names.some((n) => n === needle)) return 0; if (names.some((n) => n.startsWith(needle))) return 1; if (names.some((n) => n.includes(needle))) return 2;
    if ((node.authors || "").toLowerCase().includes(needle) || (node.summary || "").toLowerCase().includes(needle)) return 3; return 9;
  };
  const matches = state.graph.nodes.map((node) => ({ node, score: score(node) })).filter((m) => m.score < 9).sort((a, b) => a.score - b.score || a.node.label.localeCompare(b.node.label)).slice(0, 10);
  el.searchResults.replaceChildren();
  for (const { node } of matches) {
    const button = document.createElement("button"); button.className = "search-result"; button.type = "button";
    const dot = document.createElement("i"); dot.className = "dot"; dot.style.background = `var(--c-${node.type})`;
    const label = document.createElement("span"); label.textContent = node.label; const kind = document.createElement("small"); kind.textContent = `${state.nodeTypes[node.type] || node.type}${node.year ? ` · ${node.year}` : ""}${node.claim_status ? ` · ${node.claim_status}` : ""}`;
    button.append(dot, label, kind); button.addEventListener("click", () => { el.search.value = ""; el.searchResults.hidden = true; selectNode(node.id, { fit: true }); });
    el.searchResults.appendChild(button);
  }
  if (!matches.length) { const empty = document.createElement("div"); empty.className = "search-result"; empty.textContent = "Nothing matches"; el.searchResults.appendChild(empty); }
  el.searchResults.hidden = false;
}
el.search.addEventListener("input", () => state.graph && showSearchResults(el.search.value));
el.search.addEventListener("keydown", (event) => { if (event.key === "Escape") { el.search.value = ""; showSearchResults(""); el.search.blur(); } });
document.addEventListener("click", (event) => { if (!event.target.closest(".search-box") && !event.target.closest(".search-results")) el.searchResults.hidden = true; });
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); el.search.focus(); }
  if (event.key === "Escape" && !el.card.hidden && !el.dialog.open) clearSelection();
});
$("#reset-view").addEventListener("click", () => { state.hiddenKinds.clear(); state.shown = null; buildLegend(); setPinned(null); clearSelection(); fitGraph(); });

// ---------- the node card ----------
function selectNode(nodeId, options = {}) {
  const node = state.nodesById.get(nodeId); if (!node) return;
  if (options.toggle && state.selectedId === nodeId && !el.card.hidden) { setPinned(state.pinnedId === nodeId ? null : nodeId); return; }
  if (state.hiddenKinds.delete(node.type)) { state.shown = null; buildLegend(); }
  state.selectedId = nodeId; showNodeCard(node); updateContext(); updateSuggestions(node);
  if (options.fit && !state.pinnedId) focusOn(nodeId);
  draw();
}
function clearSelection() { state.selectedId = null; el.card.hidden = true; updateContext(); updateSuggestions(null); draw(); }
// Pin a node: the view and the highlighted neighbourhood stay on it while other nodes are looked at.
function setPinned(nodeId) {
  state.pinnedId = nodeId;
  const pin = $("#pin-node"); const node = nodeId && state.nodesById.get(nodeId);
  if (pin) { pin.textContent = state.selectedId && state.selectedId === nodeId ? "Unpin" : "Pin"; pin.classList.toggle("active", Boolean(nodeId) && state.selectedId === nodeId); }
  const chip = $("#pinned-chip");
  if (chip) { chip.hidden = !node; if (node) chip.querySelector("b").textContent = shortLabel(node); }
  if (node) focusOn(nodeId);
  draw();
}
function chip(node, extra = "", options = {}) {
  const button = document.createElement("button"); button.type = "button"; button.className = "chip";
  button.title = node.type === "paper" ? node.label : node.summary || node.label;
  const dot = document.createElement("i"); dot.className = "dot"; dot.style.background = `var(--c-${node.type})`;
  const text = document.createElement("span"); text.textContent = options.cite && node.type === "paper" ? citeName(node) : node.label; button.append(dot, text);
  if (extra) { const small = document.createElement("small"); small.textContent = extra; button.appendChild(small); }
  button.addEventListener("click", () => selectNode(node.id, { fit: true }));
  return button;
}
function fieldRow(label, value) {
  const row = document.createElement("div"); row.className = "field-row";
  const name = document.createElement("b"); name.textContent = label; row.appendChild(name);
  if (Array.isArray(value)) { const wrap = document.createElement("span"); for (const item of value) { const tag = document.createElement("i"); tag.className = "tag"; tag.textContent = item; wrap.appendChild(tag); } row.appendChild(wrap); }
  else if (value instanceof Node) row.appendChild(value);
  else { const text = document.createElement("span"); text.textContent = value; row.appendChild(text); }
  return row;
}
function showNodeCard(node) {
  el.kind.textContent = `Level ${LEVEL_NUMBER[node.type] || ""} · ${state.nodeTypes[node.type] || node.type}`; el.kind.style.color = `var(--c-${node.type})`;
  el.status.hidden = false; el.status.replaceChildren();
  if (node.status === "proposed") { const origin = document.createElement("span"); origin.textContent = "Proposed by the agent, not kept yet"; origin.className = "proposed"; el.status.appendChild(origin); }
  if (node.type === "claim" && node.claim_status) { const b = document.createElement("span"); b.textContent = node.claim_status; b.title = CLAIM_HELP[node.claim_status] || ""; b.className = "badge"; el.status.appendChild(b); }
  if (node.type === "quantity" && node.level) { const b = document.createElement("span"); b.textContent = `${node.level} level`; b.title = LEVEL_HELP[node.level] || ""; b.className = "badge"; el.status.appendChild(b); }
  el.status.hidden = !el.status.childElementCount;
  el.title.textContent = node.label;
  el.meta.replaceChildren();
  if (node.type === "paper") {
    const who = [node.authors, node.year ? `(${node.year})` : ""].filter(Boolean).join(" ");
    el.meta.append([who, node.venue].filter(Boolean).join(" · "));
    const link = node.doi ? `https://doi.org/${node.doi.replace(/^https?:\/\/doi\.org\//, "")}` : node.url;
    if (link) { el.meta.append(" · "); const a = document.createElement("a"); a.href = link; a.target = "_blank"; a.rel = "noopener"; a.textContent = node.doi ? "DOI ↗" : "Open ↗"; el.meta.appendChild(a); }
    if (node.priority) el.meta.append(` · reading priority ${node.priority}`);
  } else if (node.type === "family" && node.relevance) el.meta.append(`Relevance to the research question: ${node.relevance} of 5 (the reviewer's judgement)`);
  else if (node.type === "technique" && node.reference) {
    const ref = state.nodesById.get(node.reference); el.meta.append("Reference: ");
    if (ref) { const a = document.createElement("a"); a.href = "#"; a.textContent = citeName(ref); a.title = ref.label; a.addEventListener("click", (e) => { e.preventDefault(); selectNode(ref.id, { fit: true }); }); el.meta.appendChild(a); } else el.meta.append(node.reference);
  }
  el.meta.hidden = !el.meta.textContent;
  el.summary.textContent = node.summary || ""; el.summary.hidden = !node.summary;
  el.links.replaceChildren();
  // the structured fields of the level, in plain words
  const levelTags = (levels) => { const wrap = document.createElement("span"); for (const level of levels) { const t = document.createElement("i"); t.className = "tag"; t.textContent = level; t.title = LEVEL_HELP[level] || ""; wrap.appendChild(t); } return wrap; };
  if (node.type === "paper") {
    if (node.learns) el.links.appendChild(fieldRow("What it learns", node.learns));
    if (node.discards) el.links.appendChild(fieldRow("What it leaves out", node.discards));
    const row = fieldRow("Evidence reported at", node.validated_at?.length ? levelTags(node.validated_at) : "not recorded"); row.title = "The validation levels the paper itself reports results for; hover a level for what it covers."; el.links.appendChild(row);
  } else if (node.type === "family") {
    if (node.keeps) el.links.appendChild(fieldRow("Keeps or learns", node.keeps));
    if (node.discards) el.links.appendChild(fieldRow("Gives up", node.discards));
    if (node.computes) el.links.appendChild(fieldRow("Still has to run", node.computes));
  } else if (node.type === "claim") {
    if (node.scope) el.links.appendChild(fieldRow("Where it holds", node.scope));
  } else if (node.type === "quantity") {
    if (node.definition) el.links.appendChild(fieldRow("How it is computed", node.definition));
    if (node.symbol || node.units) el.links.appendChild(fieldRow("Symbol", [node.symbol, node.units].filter(Boolean).join(", ")));
  }
  // links, grouped by what they mean from this node's side
  const groups = new Map();
  for (const edge of state.edgesByNode.get(node.id) || []) {
    const other = state.nodesById.get(edge.source === node.id ? edge.target : edge.source); if (!other) continue;
    const heading = linkHeading(node, edge, other);
    if (!groups.has(heading)) groups.set(heading, []); groups.get(heading).push({ edge, other });
  }
  const order = ["Part of", "Techniques in this family", "Papers in this family", "Techniques used", "Used in", "Reports evidence for", "Reported in", "About", "Claims about it", "Supported by", "Contradicted by", "Gives evidence for", "Gives evidence against", "Builds on", "Extended by", "Compared with", "Related"];
  for (const heading of order) {
    const items = groups.get(heading); if (!items) continue;
    const group = document.createElement("div"); group.className = "group"; const title = document.createElement("b"); title.textContent = heading; group.appendChild(title);
    for (const { edge, other } of items) {
      const c = chip(other, "", { cite: true });
      if (edge.label && ["contrasts", "relates", "extends"].includes(edge.type)) { const why = document.createElement("small"); why.textContent = `— ${edge.label}`; c.appendChild(why); }
      if (edge.note) c.title = `${c.title}\n${edge.note}`;
      group.appendChild(c);
    }
    el.links.appendChild(group);
  }
  el.confirm.hidden = node.status !== "proposed";
  const pin = $("#pin-node"); pin.textContent = state.pinnedId === node.id ? "Unpin" : "Pin"; pin.classList.toggle("active", state.pinnedId === node.id);
  const offline = Boolean(EXPORTED);
  el.explain.hidden = offline; el.expand.hidden = offline; el.edit.hidden = offline; el.remove.hidden = offline; el.confirm.hidden = offline || node.status !== "proposed";
  el.card.hidden = false;
}
$("#close-node-card").addEventListener("click", clearSelection);
$("#pin-node").addEventListener("click", () => { if (state.selectedId) setPinned(state.pinnedId === state.selectedId ? null : state.selectedId); });
$("#pinned-chip").addEventListener("click", () => setPinned(null));
el.explain.addEventListener("click", () => { const node = state.nodesById.get(state.selectedId); if (node) askAbout(node, `Explain ${shortLabel(node)} [${node.id}] using the graph: what it is, what it learns or assumes and discards, which claims and quantities it bears on, and what is uncertain. Then say whether the graph's record of it should be improved.`); });
el.expand.addEventListener("click", () => { const node = state.nodesById.get(state.selectedId); if (node) askAbout(node, `Search the literature for work closely related to ${shortLabel(node)} [${node.id}] (papers that extend it, apply it to ion transport in solids, or compare against it). Pick at most four that matter for the research question, say why each matters, and add them to the graph: each with its family, the techniques it uses, learns / discards / validated_at, and any claim it supports or contradicts.`); });
el.confirm.addEventListener("click", async () => { const id = state.selectedId; if (id) { await api("/api/graph/status", { ids: [id], status: "confirmed" }); } });
el.remove.addEventListener("click", async () => {
  const node = state.nodesById.get(state.selectedId); if (!node) return;
  if (!window.confirm(`Delete "${node.label}" and its links?`)) return;
  await api(`/api/graph/nodes/${encodeURIComponent(node.id)}`, null, "DELETE");
});

// ---------- editing ----------
function fillTypeSelects() {
  const typeSelect = $("#edit-type"); typeSelect.replaceChildren();
  for (const type of TYPE_ORDER) { if (!state.nodeTypes[type]) continue; const option = document.createElement("option"); option.value = type; option.textContent = `${LEVEL_NUMBER[type]} · ${state.nodeTypes[type]}`; typeSelect.appendChild(option); }
  el.linkType.replaceChildren();
  for (const [type, name] of Object.entries(state.edgeTypes)) { const option = document.createElement("option"); option.value = type; option.textContent = name; el.linkType.appendChild(option); }
  el.nodeOptions.replaceChildren();
  for (const node of state.graph.nodes) { const option = document.createElement("option"); option.value = node.label; el.nodeOptions.appendChild(option); }
}
// The fields of the chosen level, built when the dialog opens and when the type changes.
function renderTypeFields(node) {
  const type = $("#edit-type").value; const box = $("#edit-type-fields"); box.replaceChildren();
  for (const [key, label, kind] of TYPE_FIELDS[type] || []) {
    const wrap = document.createElement("label"); if (kind === "textarea" || kind.startsWith("multi")) wrap.className = "wide";
    wrap.append(label);
    const value = node && node.type === type ? node[key] : undefined;
    let input;
    if (kind === "textarea") { input = document.createElement("textarea"); input.rows = 2; input.value = value || ""; }
    else if (kind.startsWith("select")) {
      input = document.createElement("select"); const options = kind.endsWith("claim") ? CLAIM_STATUSES : VALIDATION_LEVELS;
      for (const option of ["", ...options]) { const o = document.createElement("option"); o.value = option; o.textContent = option || "—"; input.appendChild(o); }
      input.value = value || "";
    } else if (kind.startsWith("multi")) {
      input = document.createElement("div"); input.className = "checks";
      for (const option of VALIDATION_LEVELS) { const l = document.createElement("label"); l.title = LEVEL_HELP[option]; const c = document.createElement("input"); c.type = "checkbox"; c.value = option; c.checked = (value || []).includes(option); l.append(c, option); input.appendChild(l); }
    } else { input = document.createElement("input"); if (kind === "int") { input.type = "number"; input.min = 0; } input.value = value ?? ""; }
    input.dataset.field = key; input.dataset.kind = kind; wrap.appendChild(input); box.appendChild(wrap);
  }
}
function readTypeFields() {
  const out = {};
  for (const input of $("#edit-type-fields").querySelectorAll("[data-field]")) {
    const key = input.dataset.field; const kind = input.dataset.kind;
    if (kind.startsWith("multi")) out[key] = [...input.querySelectorAll("input:checked")].map((c) => c.value);
    else if (kind === "int") out[key] = input.value ? Number(input.value) : undefined;
    else out[key] = input.value.trim();
  }
  return out;
}
function openEditor(node) {
  state.editingId = node ? node.id : null; state.pendingLinks = [];
  el.editTitle.textContent = node ? "Edit node" : "Add a node"; el.editError.hidden = true;
  $("#edit-label").value = node?.label || ""; $("#edit-type").value = node?.type || "paper"; $("#edit-summary").value = node?.summary || "";
  $("#edit-aliases").value = (node?.aliases || []).join(", ");
  renderTypeFields(node); renderEditLinks(); el.dialog.showModal();
}
$("#edit-type").addEventListener("change", () => renderTypeFields(state.editingId ? state.nodesById.get(state.editingId) : null));
// Fill in with AI: send what is filled so far, get the rest back (the model may search for a paper's metadata),
// and put it into the form for review; nothing is saved until Save.
$("#edit-fill").addEventListener("click", async () => {
  const button = $("#edit-fill"); if (button.disabled) return;
  const draft = { id: state.editingId || undefined, type: $("#edit-type").value, label: $("#edit-label").value.trim(), summary: $("#edit-summary").value.trim(),
    aliases: $("#edit-aliases").value.split(",").map((a) => a.trim()).filter(Boolean), ...readTypeFields() };
  if (!draft.label) { el.editError.textContent = "Give at least a label (a title, a name, or a sentence) for the AI to start from."; el.editError.hidden = false; return; }
  el.editError.hidden = true; button.disabled = true; button.textContent = "Filling in…";
  try {
    const response = await fetch(withTopic("/api/complete"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ node: draft, links: state.pendingLinks.map((p) => ({ target: p.target, type: p.type, label: p.label })) }) });
    const reply = await response.json();
    if (!reply.ok) throw new Error(reply.message || "The AI could not fill this in.");
    const node = reply.node || {};
    if (node.label && !draft.label) $("#edit-label").value = node.label;
    if (node.summary) $("#edit-summary").value = node.summary;
    if (node.aliases?.length) $("#edit-aliases").value = [...new Set([...draft.aliases, ...node.aliases])].join(", ");
    if (node.type && TYPE_FIELDS[node.type]) $("#edit-type").value = node.type;
    renderTypeFields({ ...node, type: $("#edit-type").value });
    for (const edge of reply.edges || []) {
      const target = state.nodesById.get(edge.target); if (!target) continue;
      if (!state.pendingLinks.some((p) => p.target === edge.target && p.type === edge.type)) state.pendingLinks.push({ target: edge.target, targetLabel: target.label, type: edge.type, label: edge.label || "", incoming: Boolean(edge.incoming) });
    }
    renderEditLinks();
    if (reply.note) { el.editError.textContent = reply.note; el.editError.hidden = false; }
  } catch (error) { el.editError.textContent = error.message; el.editError.hidden = false; }
  finally { button.disabled = false; button.textContent = "Fill in with AI"; }
});
function renderEditLinks() {
  el.linkList.replaceChildren();
  const existing = state.editingId ? state.edgesByNode.get(state.editingId) || [] : [];
  for (const edge of existing) {
    const outgoing = edge.source === state.editingId; const other = state.nodesById.get(outgoing ? edge.target : edge.source); if (!other) continue;
    const li = document.createElement("li"); const text = document.createElement("span"); text.textContent = `${outgoing ? "→" : "←"} ${edge.label || state.edgeTypes[edge.type] || edge.type}: ${other.label}`;
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "×"; remove.title = "Remove this link";
    remove.addEventListener("click", async () => { await api("/api/graph/edges", { source: edge.source, target: edge.target, type: edge.type }, "DELETE"); renderEditLinks(); });
    li.append(text, remove); el.linkList.appendChild(li);
  }
  for (const pending of state.pendingLinks) {
    const li = document.createElement("li"); const text = document.createElement("span"); text.textContent = `${pending.incoming ? "←" : "→"} ${pending.label || state.edgeTypes[pending.type]}: ${pending.targetLabel} (new)`;
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "×"; remove.addEventListener("click", () => { state.pendingLinks = state.pendingLinks.filter((p) => p !== pending); renderEditLinks(); });
    li.append(text, remove); el.linkList.appendChild(li);
  }
}
el.linkAdd.addEventListener("click", () => {
  const label = el.linkTarget.value.trim(); const target = state.graph.nodes.find((n) => n.label.toLowerCase() === label.toLowerCase());
  if (!target) { el.editError.textContent = `No node called "${label}". Pick one from the list.`; el.editError.hidden = false; return; }
  const type = el.linkType.value; const incoming = $("#link-direction").value === "in";
  el.editError.hidden = true; state.pendingLinks.push({ target: target.id, targetLabel: target.label, type, label: el.linkLabel.value.trim(), incoming });
  el.linkTarget.value = ""; el.linkLabel.value = ""; renderEditLinks();
});
$("#add-node").addEventListener("click", () => openEditor(null));
el.edit.addEventListener("click", () => { const node = state.nodesById.get(state.selectedId); if (node) openEditor(node); });
el.editForm.addEventListener("submit", async (event) => {
  if (event.submitter?.value !== "save") return;
  event.preventDefault();
  const aliases = $("#edit-aliases").value.split(",").map((a) => a.trim()).filter(Boolean);
  const payload = { id: state.editingId || undefined, label: $("#edit-label").value.trim(), type: $("#edit-type").value, summary: $("#edit-summary").value.trim(),
    aliases, status: "confirmed", ...readTypeFields() };
  const reply = await api("/api/graph/nodes", payload, "POST", { silent: true });
  if (!reply?.ok) { el.editError.textContent = reply?.message || "Could not save."; el.editError.hidden = false; return; }
  for (const pending of state.pendingLinks) await api("/api/graph/edges", pending.incoming ? { source: pending.target, target: reply.node.id, type: pending.type, label: pending.label } : { source: reply.node.id, target: pending.target, type: pending.type, label: pending.label }, "POST", { silent: true });
  await reloadGraph({ keepPositions: true });
  el.dialog.close("saved"); selectNode(reply.node.id, { fit: !state.editingId });
});

// ---------- server ----------
async function api(path, body, method = "POST", options = {}) {
  try {
    const response = await fetch(withTopic(path), { method, headers: body ? { "Content-Type": "application/json" } : {}, body: body ? JSON.stringify(body) : undefined });
    const reply = await response.json();
    if (reply.graph) indexGraph(reply, { keepPositions: true });
    if (!reply.ok && !options.silent) addNotice(reply.message || "The server refused that.", true);
    return reply;
  } catch (error) { if (!options.silent) addNotice(error.message, true); return null; }
}
async function reloadGraph(options = {}) {
  const response = await fetch(withTopic("/api/graph")); if (response.ok) indexGraph(await response.json(), options);
}

// ---------- chat ----------
function setChatOpen(open) {
  state.chatOpen = open; el.shell.classList.toggle("chat-is-open", open); el.chat.hidden = !open; el.openChat.hidden = open;
  requestAnimationFrame(() => { if (state.graph) { resizeCanvas(); if (state.pinnedId) focusOn(state.pinnedId); else if (!state.viewTouched) fitGraph(); } });
}
el.openChat.addEventListener("click", () => setChatOpen(true)); el.closeChat.addEventListener("click", () => setChatOpen(false));
const memoryKey = () => `${MEMORY_KEY}:${state.topic || ""}`;
function readMemory() { try { const parsed = JSON.parse(sessionStorage.getItem(memoryKey()) || "[]"); return Array.isArray(parsed) ? parsed.slice(-MAX_MEMORY) : []; } catch { return []; } }
function writeMemory(items) { try { sessionStorage.setItem(memoryKey(), JSON.stringify(items.slice(-MAX_MEMORY))); } catch { /* ignore */ } }
const withTopic = (path) => (state.topic ? `${path}${path.includes("?") ? "&" : "?"}topic=${encodeURIComponent(state.topic)}` : path);
// A short name for a node in prompts and chips: its shortest alias, else the label cut at 60 characters.
function shortLabel(node) {
  const alias = (node.aliases || []).filter((a) => a.length >= 3).sort((x, y) => x.length - y.length)[0];
  if (alias && alias.length < node.label.length) return alias;
  return node.label.length > 60 ? `${node.label.slice(0, 58)}…` : node.label;
}
function updateContext() {
  const node = state.nodesById.get(state.selectedId);
  el.contextBar.hidden = !node; el.question.placeholder = node ? `Ask about ${shortLabel(node)}…` : "Ask about the field, or ask to search and add…";
  if (node) el.contextChip.querySelector("b").textContent = shortLabel(node);
}
el.contextChip.addEventListener("click", clearSelection);
function updateSuggestions(node) {
  const list = node
    ? [`What does ${shortLabel(node)} learn, assume and discard, and what is it validated against?`, `Which claims in the graph bear on ${shortLabel(node)}, and how strong is the evidence?`, `Find recent papers that build on ${shortLabel(node)} and add the relevant ones, with their techniques and validation levels.`]
    : ["Which families are validated at the kinetic or mechanistic level, and which stop at structure or MSD?", "Which open claims could be settled by papers already published? Search and add them.", "Where are the gaps in this graph? Suggest what to add."];
  el.suggestions.replaceChildren();
  for (const text of list) { const button = document.createElement("button"); button.type = "button"; button.textContent = text; button.addEventListener("click", () => submitQuestion(text)); el.suggestions.appendChild(button); }
}
function scrollMessages(force = false) { if (force || state.autoFollow) el.messages.scrollTop = el.messages.scrollHeight; }
el.messages.addEventListener("scroll", () => { state.autoFollow = el.messages.scrollHeight - el.messages.scrollTop - el.messages.clientHeight < 72; });
function addUserMessage(text) {
  const article = document.createElement("article"); article.className = "message user"; const bubble = document.createElement("div"); const p = document.createElement("p"); p.textContent = text;
  bubble.appendChild(p); article.appendChild(bubble); el.messages.appendChild(article); state.autoFollow = true; scrollMessages(true);
}
function addAssistantMessage() {
  const article = document.createElement("article"); article.className = "message assistant";
  const avatar = document.createElement("div"); avatar.className = "assistant-avatar"; avatar.textContent = "L";
  const content = document.createElement("div"); const body = document.createElement("div"); body.className = "message-body";
  const thinking = document.createElement("span"); thinking.className = "thinking"; thinking.innerHTML = "<i></i><i></i><i></i>"; body.appendChild(thinking);
  content.appendChild(body); article.append(avatar, content); el.messages.appendChild(article); scrollMessages(true);
  return { article, body, content };
}
function addNotice(text, isError = false) {
  const assistant = addAssistantMessage(); assistant.body.textContent = text; if (isError) assistant.article.classList.add("error"); scrollMessages();
}
function addStatus(text) { const line = document.createElement("div"); line.className = "status-line"; line.textContent = text; el.messages.appendChild(line); scrollMessages(); return line; }
function addProposal(proposal) {
  const card = document.createElement("div"); card.className = "proposal"; card.dataset.id = proposal.id;
  const title = document.createElement("b");
  const parts = [proposal.added_nodes.length ? `${proposal.added_nodes.length} new node${proposal.added_nodes.length > 1 ? "s" : ""}` : "", proposal.updated_nodes.length ? `${proposal.updated_nodes.length} updated` : "", proposal.added_edges.length ? `${proposal.added_edges.length} new link${proposal.added_edges.length > 1 ? "s" : ""}` : ""].filter(Boolean);
  title.textContent = (proposal.status === "confirmed" ? "Added to the graph: " : "Proposed for the graph: ") + (parts.join(", ") || "no change");
  const reason = document.createElement("p"); reason.textContent = proposal.reason || "";
  const items = document.createElement("div"); items.className = "items";
  for (const node of proposal.nodes || []) if (node) items.appendChild(chip(node, proposal.updated_nodes.includes(node.id) ? "updated" : "new"));
  const actions = document.createElement("div"); actions.className = "actions";
  if (proposal.status === "proposed" && !EXPORTED) {
    const accept = document.createElement("button"); accept.type = "button"; accept.className = "act primary"; accept.textContent = "Keep";
    const discard = document.createElement("button"); discard.type = "button"; discard.className = "act"; discard.textContent = "Discard";
    const decide = async (action) => {
      const reply = await api(`/api/proposals/${proposal.id}/${action}`, {}, "POST", { silent: true });
      if (!reply?.ok) { addNotice(reply?.message || "Could not do that.", true); return; }
      actions.replaceChildren(Object.assign(document.createElement("span"), { textContent: action === "accept" ? "Kept ✓" : "Discarded" }));
      state.highlight.clear(); draw();
    };
    accept.addEventListener("click", () => decide("accept")); discard.addEventListener("click", () => decide("discard")); actions.append(accept, discard);
  }
  if (proposal.errors?.length) { const note = document.createElement("span"); note.textContent = `Skipped: ${proposal.errors.join("; ")}`; actions.appendChild(note); }
  card.append(title, reason, items, actions); el.messages.appendChild(card); scrollMessages();
  for (const id of proposal.added_nodes) state.highlight.add(id);
}

// How a node is cited in prose, as in a paper: Author et al. (year) for a paper, the name for a technique or
// quantity, "family B" for a family, a short form for a claim.
function citeName(node) {
  if (node.type === "paper") {
    const raw = String(node.authors || "").replace(/\s+and\s+/g, " & ");
    let who;
    if (/et al/i.test(raw)) who = `${raw.split(/[,&]| et al/i)[0].trim()} et al.`;
    else {
      const names = raw.split(/\s*[,&]\s*/).filter(Boolean).map((name) => name.trim().split(/\s+/).pop());
      who = names.length <= 1 ? names[0] || node.label.split(":")[0] : names.length === 2 ? `${names[0]} & ${names[1]}` : `${names[0]} et al.`;
    }
    return node.year ? `${who} (${node.year})` : who;
  }
  if (node.type === "family") { const m = node.label.match(/^([A-Z])\./); return m ? `family ${m[1]}` : node.label; }
  if (node.type === "claim") { const words = node.label.split(/\s+/); return words.length > 8 ? `${words.slice(0, 8).join(" ")}…` : node.label; }
  return node.label.replace(/\s*\([^)]*\)\s*$/, "");
}
// A reference chip: the citation, or only a link mark when the words before it already name the node.
function referenceChip(node, before) {
  const name = citeName(node);
  const low = before.toLowerCase();
  // a claim is usually paraphrased ("the claim that ..."), so the word "claim" just before it counts as naming it
  const already = low.includes(name.toLowerCase()) || low.includes(node.label.toLowerCase().slice(0, 24)) || (node.type === "claim" && /claim/.test(low.slice(-60)));
  const b = document.createElement("button"); b.type = "button"; b.className = `node-ref${already ? " bare" : ""}`; b.title = node.label;
  const dot = document.createElement("i"); dot.className = "dot"; dot.style.background = `var(--c-${node.type})`;
  b.append(dot, already ? "" : name);
  b.addEventListener("click", () => selectNode(node.id, { fit: true }));
  return b;
}

// Markdown, with [node:id] references turned into citation chips that select the node.
function appendInline(parent, text) {
  const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\(https?:\/\/[^)\s]+\)|\[[a-z]+:[a-z0-9][a-z0-9-]*\]|\*[^*\n]+\*)/g;
  let cursor = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > cursor) parent.appendChild(document.createTextNode(text.slice(cursor, match.index)));
    const token = match[0];
    if (token.startsWith("`")) { const code = document.createElement("code"); code.textContent = token.slice(1, -1); parent.appendChild(code); }
    else if (token.startsWith("**")) { const strong = document.createElement("strong"); appendInline(strong, token.slice(2, -2)); parent.appendChild(strong); }
    else if (token.startsWith("[")) {
      const link = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/); const ref = token.slice(1, -1);
      if (link) { const a = document.createElement("a"); a.href = link[2]; a.target = "_blank"; a.rel = "noopener noreferrer"; appendInline(a, link[1]); parent.appendChild(a); }
      else if (state.nodesById.has(ref)) parent.appendChild(referenceChip(state.nodesById.get(ref), text.slice(Math.max(0, match.index - 80), match.index)));
      else parent.appendChild(document.createTextNode(token));
    } else { const em = document.createElement("em"); appendInline(em, token.slice(1, -1)); parent.appendChild(em); }
    cursor = match.index + token.length;
  }
  if (cursor < text.length) parent.appendChild(document.createTextNode(text.slice(cursor)));
}
const blockStart = (line) => /^\s*(?:```|#{1,4}\s+|>\s?|[-*+]\s+|\d+[.)]\s+|\|)/.test(line);
function renderMarkdown(container, markdown) {
  const lines = String(markdown || "").replaceAll("\r\n", "\n").split("\n"); const fragment = document.createDocumentFragment(); let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }
    const fence = line.match(/^\s*```/);
    if (fence) { index += 1; const code = []; while (index < lines.length && !/^\s*```/.test(lines[index])) { code.push(lines[index]); index += 1; } index += 1; const pre = document.createElement("pre"); const c = document.createElement("code"); c.textContent = code.join("\n"); pre.appendChild(c); fragment.appendChild(pre); continue; }
    const heading = line.match(/^\s*(#{1,4})\s+(.+)$/);
    if (heading) { const h = document.createElement(`h${Math.min(heading[1].length + 1, 5)}`); appendInline(h, heading[2].trim()); fragment.appendChild(h); index += 1; continue; }
    if (/^\s*\|/.test(line)) {
      const rows = []; while (index < lines.length && /^\s*\|/.test(lines[index])) { rows.push(lines[index]); index += 1; }
      const table = document.createElement("table");
      rows.filter((row) => !/^\s*\|[\s:|-]+\|\s*$/.test(row)).forEach((row, at) => { const tr = document.createElement("tr"); row.replace(/^\s*\||\|\s*$/g, "").split("|").forEach((cell) => { const td = document.createElement(at === 0 ? "th" : "td"); appendInline(td, cell.trim()); tr.appendChild(td); }); table.appendChild(tr); });
      fragment.appendChild(table); continue;
    }
    const unordered = /^\s*[-*+]\s+/.test(line); const ordered = /^\s*\d+[.)]\s+/.test(line);
    if (unordered || ordered) {
      const list = document.createElement(unordered ? "ul" : "ol"); const pattern = unordered ? /^\s*[-*+]\s+(.+)$/ : /^\s*\d+[.)]\s+(.+)$/;
      while (index < lines.length) { const m = lines[index].match(pattern); if (!m) break; const li = document.createElement("li"); appendInline(li, m[1].trim()); list.appendChild(li); index += 1; }
      fragment.appendChild(list); continue;
    }
    if (/^\s*>/.test(line)) { const quote = document.createElement("blockquote"); const q = []; while (index < lines.length && /^\s*>/.test(lines[index])) { q.push(lines[index].replace(/^\s*>\s?/, "")); index += 1; } appendInline(quote, q.join(" ")); fragment.appendChild(quote); continue; }
    const paragraph = [line.trim()]; index += 1;
    while (index < lines.length && lines[index].trim() && !blockStart(lines[index])) { paragraph.push(lines[index].trim()); index += 1; }
    const p = document.createElement("p"); appendInline(p, paragraph.join(" ")); fragment.appendChild(p);
  }
  container.replaceChildren(fragment);
}

async function streamAnswer(query, assistant, contextIds, mode = "chat") {
  const response = await fetch(withTopic("/api/answer/stream"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, history: mode === "build" ? [] : readMemory(), context_ids: contextIds, mode }) });
  if (!response.ok) { let message = "The research companion is not available."; try { message = (await response.json()).message || message; } catch { /* keep */ } throw new Error(message); }
  const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ""; let answer = ""; let changed = false;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n"); buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line);
      if (event.type === "error") throw new Error(event.message || "The companion could not answer.");
      if (event.type === "delta") { answer += event.text || ""; renderMarkdown(assistant.body, answer); scrollMessages(); }
      if (event.type === "status") { assistant.article.insertAdjacentElement("afterend", Object.assign(document.createElement("div"), { className: "status-line", textContent: event.text })); scrollMessages(); }
      if (event.type === "proposal") { changed = true; await reloadGraph({ keepPositions: true }); addProposal(event.proposal); el.messages.appendChild(assistant.article); }
      if (event.type === "done") { answer = event.answer || answer; renderMarkdown(assistant.body, answer); }
    }
    if (done) break;
  }
  if (changed) { startPhysics(0.5); setTimeout(() => { state.highlight.clear(); draw(); }, 12000); }
  return answer;
}
async function submitQuestion(text, contextIds, options = {}) {
  text = text.trim(); if (!text || state.busy) return;
  const mode = options.mode || "chat";
  if (EXPORTED) { addNotice("This is an exported file: run `litgraph serve` for the research companion."); return; }
  if (!state.health.ai) { addNotice("No API key on the server: put ANTHROPIC_API_KEY in the workspace's .env and restart `litgraph serve`.", true); return; }
  const ids = contextIds || (state.selectedId ? [state.selectedId] : []);
  el.question.value = ""; resizeQuestion(); el.send.disabled = true; el.suggestions.hidden = true; state.busy = true;
  addUserMessage(mode === "build" ? `Build a review of: ${text}` : text); const assistant = addAssistantMessage();
  if (mode === "build") addStatus("Building the review from scratch: searching, then adding families, techniques, papers, claims and quantities. This takes a few minutes.");
  try {
    const answer = await streamAnswer(text, assistant, ids, mode);
    const memory = readMemory(); memory.push({ role: "user", content: text }, { role: "assistant", content: answer }); writeMemory(memory);
  } catch (error) { assistant.article.classList.add("error"); assistant.body.textContent = error.message; }
  finally { state.busy = false; el.send.disabled = false; el.suggestions.hidden = false; el.question.focus(); scrollMessages(); }
}
function askAbout(node, text) { setChatOpen(true); submitQuestion(text, [node.id]); }
function resizeQuestion() { el.question.style.height = "auto"; el.question.style.height = `${Math.min(el.question.scrollHeight, 140)}px`; }
el.form.addEventListener("submit", (event) => { event.preventDefault(); submitQuestion(el.question.value); });
el.question.addEventListener("input", resizeQuestion);
el.question.addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); el.form.requestSubmit(); } });
el.clearChat.addEventListener("click", () => { writeMemory([]); showWelcome(); });
function showWelcome() {
  el.messages.replaceChildren();
  const assistant = addAssistantMessage(); assistant.body.textContent = "";
  const p = document.createElement("p"); p.textContent = "Click a node and ask about it, or ask anything about the field. I can search the literature and add what we find to the graph; additions stay marked as proposed until you keep them.";
  const small = document.createElement("small"); small.textContent = state.health.ai ? `Model: ${state.health.model}` : "No API key yet: the graph works, the chat does not.";
  assistant.body.append(p, small); updateSuggestions(state.nodesById.get(state.selectedId) || null);
}
function restoreConversation() {
  const memory = readMemory(); if (!memory.length) { showWelcome(); return; }
  el.messages.replaceChildren();
  for (const turn of memory) { if (turn.role === "user") addUserMessage(turn.content); else { const a = addAssistantMessage(); renderMarkdown(a.body, turn.content); } }
  updateSuggestions(null); scrollMessages(true);
}

// ---------- topics: one graph and one review document per topic ----------
async function loadTopics() {
  try { const r = await fetch("/api/topics"); if (r.ok) state.topics = (await r.json()).topics || []; } catch { state.topics = []; }
  const select = $("#topic-select"); select.replaceChildren();
  for (const topic of state.topics) { const o = document.createElement("option"); o.value = topic.slug; o.textContent = topic.title; select.appendChild(o); }
  if (state.topic) select.value = state.topic;
  select.hidden = !state.topics.length;
}
function updateTopicBar() {
  const info = state.topicInfo || state.topics.find((t) => t.slug === state.topic) || {};
  document.title = `${info.title || state.health.title || "litgraph"} · litgraph`;
  $("#keep-all").hidden = !(info.proposed > 0) || Boolean(EXPORTED);
  $("#keep-all").textContent = `Keep all (${info.proposed || 0})`;
  $("#write-review").hidden = Boolean(EXPORTED) || !state.graph?.nodes?.length;
  $("#open-review").hidden = !info.has_review;
  $("#graph-title").textContent = info.description || "";
}
async function switchTopic(slug, options = {}) {
  state.topic = slug; state.selectedId = null; state.pinnedId = null; el.card.hidden = true; state.hiddenKinds.clear(); state.shown = null;
  const url = new URL(window.location); url.searchParams.set("topic", slug); history.replaceState(null, "", url);
  $("#topic-select").value = slug;
  state.viewTouched = false; state.fitPending = true;
  await reloadGraph();
  updateContext(); restoreConversation(); updateTopicBar();
  if (options.build) submitQuestion(options.build, [], { mode: "build" });
}
$("#topic-select").addEventListener("change", (event) => switchTopic(event.target.value));
$("#new-topic").addEventListener("click", () => { $("#topic-name").value = ""; $("#topic-error").hidden = true; $("#topic-dialog").showModal(); $("#topic-name").focus(); });
$("#topic-form").addEventListener("submit", async (event) => {
  if (event.submitter?.value !== "open") return;
  event.preventDefault();
  const title = $("#topic-name").value.trim(); if (!title) return;
  const button = $("#topic-open"); button.disabled = true;
  try {
    const r = await fetch("/api/topics", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title }) });
    const reply = await r.json(); if (!reply.ok) throw new Error(reply.message || "Could not open the topic.");
    await loadTopics(); $("#topic-dialog").close();
    if (reply.created) { setChatOpen(true); await switchTopic(reply.topic.slug, { build: title }); }
    else { await switchTopic(reply.topic.slug); addNotice(`Opened the existing topic "${reply.topic.title}".`); }
  } catch (error) { $("#topic-error").textContent = error.message; $("#topic-error").hidden = false; }
  finally { button.disabled = false; }
});
$("#keep-all").addEventListener("click", async () => { const reply = await api("/api/graph/keep_all", {}); if (reply?.ok) { addNotice(`Kept ${reply.changed} proposed node${reply.changed === 1 ? "" : "s"}.`); state.highlight.clear(); draw(); } });
async function showReview(markdown) {
  renderMarkdown($("#review-body"), markdown);
  $("#review-download").href = `/api/topics/${encodeURIComponent(state.topic)}/review?download=1`;
  $("#review-dialog").showModal();
}
$("#open-review").addEventListener("click", async () => {
  const r = await fetch(`/api/topics/${encodeURIComponent(state.topic)}/review`); const reply = await r.json();
  if (reply.ok) showReview(reply.markdown); else addNotice(reply.message || "No review yet.", true);
});
$("#write-review").addEventListener("click", async () => {
  const button = $("#write-review"); if (button.disabled) return;
  if (!window.confirm("Write the review document from the current graph? This replaces the saved review of this topic and takes a minute or two.")) return;
  button.disabled = true; button.textContent = "Writing…"; const line = addStatus("Writing the review document from the graph…");
  try {
    const r = await fetch(`/api/topics/${encodeURIComponent(state.topic)}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const reply = await r.json(); if (!reply.ok) throw new Error(reply.message || "Could not write the review.");
    line.textContent = "Review saved as review.md in the topic folder."; state.topicInfo = reply.topic; updateTopicBar(); showReview(reply.markdown);
  } catch (error) { line.remove(); addNotice(error.message, true); }
  finally { button.disabled = false; button.textContent = "Write review"; }
});
$("#review-close").addEventListener("click", () => $("#review-dialog").close());

// ---------- start ----------
async function initialize() {
  try {
    let payload = EXPORTED;
    if (!payload) {
      const healthResponse = await fetch("/api/health");
      if (healthResponse.ok) state.health = await healthResponse.json();
      await loadTopics();
      const wanted = new URLSearchParams(window.location.search).get("topic");
      state.topic = state.topics.some((t) => t.slug === wanted) ? wanted : state.topics[0]?.slug || null;
      if (!state.topic) { // an empty workspace: offer to start the first topic
        $("#topic-dialog").showModal(); $("#topic-name").focus();
        readColours(); resizeCanvas(); el.chatModel.textContent = state.health.model || "Claude"; return;
      }
      $("#topic-select").value = state.topic;
      const graphResponse = await fetch(withTopic("/api/graph"));
      if (!graphResponse.ok) throw new Error("The graph could not be loaded.");
      payload = await graphResponse.json();
    } else { $("#add-node").hidden = true; $("#new-topic").hidden = true; }
    el.chatModel.textContent = state.health.model ? state.health.model : "Claude";
    readColours(); resizeCanvas(); indexGraph(payload);
    state.transform = { x: el.stage.clientWidth / 2, y: el.stage.clientHeight / 2, k: 0.5 };
    restoreConversation(); updateTopicBar();
    const focus = new URLSearchParams(window.location.search).get("focus");
    if (focus && state.nodesById.has(focus)) selectNode(focus, { fit: true });
    if (EXPORTED) { setChatOpen(false); el.openChat.hidden = true; }
  } catch (error) { const message = document.createElement("div"); message.className = "graph-load-error"; message.textContent = error.message; el.stage.appendChild(message); }
}
initialize();
