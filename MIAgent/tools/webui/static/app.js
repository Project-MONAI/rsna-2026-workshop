let DATA = null;
let selectedPath = "";
let filterValue = "";
const expandedPaths = new Set(["baselines"]);

const treeElement = document.getElementById("file-tree");
const previewBody = document.getElementById("preview-body");
const breadcrumbs = document.getElementById("breadcrumbs");
const openFile = document.getElementById("open-file");
const fileFilter = document.getElementById("file-filter");
const runtimeMonitor = document.getElementById("runtime-monitor");
const workspace = document.querySelector(".workspace");
const divider = document.getElementById("explorer-divider");
let explorerWidth = 360;
try { explorerWidth = Number(localStorage.getItem("miagent-explorer-width")) || 360; } catch (_) {}
function resizeExplorer(width) {
  const maximum = Math.max(160, Math.min(640, workspace.clientWidth - 286));
  explorerWidth = Math.round(Math.max(160, Math.min(maximum, width)));
  workspace.style.setProperty("--explorer-width", `${explorerWidth}px`);
  divider.setAttribute("aria-valuemax", String(maximum));
  divider.setAttribute("aria-valuenow", String(explorerWidth));
}
function saveExplorerWidth() {
  try { localStorage.setItem("miagent-explorer-width", String(explorerWidth)); } catch (_) {}
}
divider.addEventListener("pointerdown", (event) => {
  if (event.button !== 0) return;
  event.preventDefault();
  divider.setPointerCapture(event.pointerId);
  document.body.classList.add("resizing-explorer");
});
divider.addEventListener("pointermove", (event) => {
  if (divider.hasPointerCapture(event.pointerId)) resizeExplorer(event.clientX - workspace.getBoundingClientRect().left);
});
for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) {
  divider.addEventListener(name, () => {
    document.body.classList.remove("resizing-explorer");
    saveExplorerWidth();
  });
}
divider.addEventListener("keydown", (event) => {
  const widths = { ArrowLeft: explorerWidth - 20, ArrowRight: explorerWidth + 20, Home: 160, End: 640 };
  if (!(event.key in widths)) return;
  event.preventDefault();
  resizeExplorer(widths[event.key]);
  saveExplorerWidth();
});
window.addEventListener("resize", () => {
  if (window.innerWidth > 760) resizeExplorer(explorerWidth);
});
if (window.innerWidth > 760) resizeExplorer(explorerWidth);

for (const [id, service] of [["mlflow-link", "mlflow"], ["tensorboard-link", "tensorboard"]]) {
  const hostname = window.location.hostname;
  if (hostname.startsWith("reports.")) {
    const port = window.location.port ? `:${window.location.port}` : "";
    document.getElementById(id).href = `${window.location.protocol}//${service}.${hostname.slice(8)}${port}/`;
  } else {
    const archive = window.location.pathname.startsWith("/solutions/");
    document.getElementById(id).href = `${archive ? "/solutions" : ""}/${service}/`;
  }
  document.getElementById(id).target = "_blank";
  document.getElementById(id).rel = "noopener";
}

document.getElementById("refresh-button").addEventListener("click", load);
document.getElementById("collapse-button").addEventListener("click", () => {
  expandedPaths.clear();
  renderTree();
});
fileFilter.addEventListener("input", () => {
  filterValue = fileFilter.value.trim().toLowerCase();
  renderTree();
});
window.addEventListener("hashchange", selectFromHash);

load();
loadRuntime();
window.setInterval(loadRuntime, 15000);

async function load() {
  treeElement.innerHTML = '<p class="tree-message">Loading files...</p>';
  try {
    const response = await fetch("api/tree", { cache: "no-store" });
    if (!response.ok) throw new Error(`File request failed (${response.status})`);
    DATA = await response.json();
    document.getElementById("challenge-title").textContent = DATA.name || "MIAgent";
    document.getElementById("challenge-root").textContent = DATA.root || "";
    document.getElementById("file-count").textContent = `${DATA.file_count || 0}`;
    renderTree();
    if (!selectFromHash() && !DATA.start_at_root) {
      selectDefaultFile();
    }
  } catch (error) {
    treeElement.innerHTML = "";
    const message = document.createElement("p");
    message.className = "tree-message error";
    message.textContent = error.message || "Could not load challenge files.";
    treeElement.append(message);
  }
}

async function loadRuntime() {
  try {
    const response = await fetch("api/runtime", { cache: "no-store" });
    if (!response.ok) throw new Error(`Runtime request failed (${response.status})`);
    const snapshot = await response.json();
    const gpu = snapshot.gpu || {};
    const challenge = (snapshot.challenges || []).find((item) => item.challenge === "cq500_ich")
      || (snapshot.challenges || [])[0];
    if (!challenge) {
      runtimeMonitor.textContent = `GPU: ${gpu.state || "unknown"} · no heartbeat configured`;
      return;
    }
    const jobs = challenge.jobs || {};
    const queued = jobs.queued || 0;
    const running = jobs.running || 0;
    const pulse = challenge.last_pulse_utc ? ` · last pulse ${challenge.last_pulse_utc}` : "";
    runtimeMonitor.textContent = `${challenge.challenge}: heartbeat ${challenge.heartbeat_status} · ${queued} queued · ${running} running · GPU ${gpu.state || "unknown"}${pulse}`;
    runtimeMonitor.title = "Read-only runtime monitor; it refreshes every 15 seconds.";
  } catch (_error) {
    runtimeMonitor.textContent = "Runtime: unavailable";
  }
}

function renderTree() {
  if (!DATA) return;
  treeElement.innerHTML = "";
  const tree = document.createElement("ul");
  tree.className = "tree-root";
  const visible = DATA.tree.filter((node) => nodeMatches(node, filterValue));
  visible.forEach((node) => tree.append(renderNode(node, 0)));
  treeElement.append(tree);
  if (!visible.length) {
    const message = document.createElement("p");
    message.className = "tree-message";
    message.textContent = "No matching files.";
    treeElement.append(message);
  }
  requestAnimationFrame(() => {
    treeElement.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest" });
  });
}

function renderNode(node, depth) {
  const item = document.createElement("li");
  item.className = node.type === "directory" ? "tree-directory" : "tree-file";

  const row = document.createElement("button");
  row.type = "button";
  row.className = "tree-row";
  row.style.setProperty("--depth", depth);
  row.title = node.path;

  if (node.type === "directory") {
    const forcedOpen = Boolean(filterValue);
    const isOpen = forcedOpen || expandedPaths.has(node.path);
    row.setAttribute("aria-expanded", String(isOpen));
    row.append(disclosure(isOpen), typeBadge(node.experiment ? "EXP" : "DIR"), fileName(node.name));
    if (node.experiment) row.classList.add("experiment-row");
    row.addEventListener("click", () => {
      if (expandedPaths.has(node.path)) expandedPaths.delete(node.path);
      else expandedPaths.add(node.path);
      renderTree();
    });
    item.append(row);
    if (isOpen) {
      const children = document.createElement("ul");
      const visibleChildren = node.children.filter((child) => nodeMatches(child, filterValue));
      visibleChildren.forEach((child) => children.append(renderNode(child, depth + 1)));
      item.append(children);
    }
    return item;
  }

  row.append(disclosure(false, true), typeBadge(fileBadge(node)), fileName(node.name));
  if (selectedPath === node.path) {
    row.classList.add("is-selected");
    row.setAttribute("aria-current", "page");
  }
  row.addEventListener("click", () => selectFile(node));
  item.append(row);
  return item;
}

function disclosure(open, placeholder = false) {
  const marker = document.createElement("span");
  marker.className = placeholder ? "disclosure placeholder" : "disclosure";
  marker.textContent = placeholder ? "" : open ? "▾" : "▸";
  return marker;
}

function typeBadge(value) {
  const badge = document.createElement("span");
  badge.className = `file-badge badge-${value.toLowerCase()}`;
  badge.textContent = value;
  return badge;
}

function fileName(value) {
  const name = document.createElement("span");
  name.className = "file-name";
  name.textContent = value;
  return name;
}

function fileBadge(node) {
  if (node.kind === "markdown") return "MD";
  if (node.kind === "nifti") return "NII";
  if (node.kind === "html") return node.name === "result_viewer.html" ? "VIEW" : "HTML";
  if (node.kind === "image") return "IMG";
  if (node.kind === "pdf") return "PDF";
  const suffix = node.name.includes(".") ? node.name.split(".").pop().toUpperCase() : "TXT";
  return suffix.slice(0, 5);
}

function nodeMatches(node, query) {
  if (!query) return true;
  if (node.name.toLowerCase().includes(query) || node.path.toLowerCase().includes(query)) return true;
  return node.type === "directory" && node.children.some((child) => nodeMatches(child, query));
}

function selectFromHash() {
  if (!DATA) return false;
  const path = decodeURIComponent(window.location.hash.replace(/^#/, ""));
  if (!path) return false;
  const node = findFile(DATA.tree, path)
    || (DATA.multiple_roots && findFile(DATA.tree, `challenge/${path}`));
  if (!node) return false;
  expandAncestors(path);
  selectFile(node, false);
  return true;
}

function selectDefaultFile() {
  const preferred = ["challenge.md", "state.md", "dashboard.md"];
  for (const path of preferred) {
    const node = findFile(DATA.tree, path)
      || (DATA.multiple_roots && findFile(DATA.tree, `challenge/${path}`));
    if (node) {
      selectFile(node);
      return;
    }
  }
  const first = firstPreviewable(DATA.tree);
  if (first) selectFile(first);
}

function selectFile(node, updateHash = true) {
  selectedPath = node.path;
  expandAncestors(node.path);
  renderTree();
  renderBreadcrumbs(node.path);
  const url = previewUrl(node);
  openFile.href = node.kind === "nifti" ? previewUrl(node) : rawUrl(node);
  openFile.hidden = false;

  previewBody.innerHTML = "";
  if (node.kind === "binary") {
    const state = document.createElement("div");
    state.className = "empty-state";
    const title = document.createElement("strong");
    title.textContent = "Preview unavailable";
    const note = document.createElement("span");
    note.textContent = "Open the file in a new tab to inspect it.";
    state.append(title, note);
    previewBody.append(state);
  } else {
    const frame = document.createElement("iframe");
    frame.className = "file-frame";
    frame.title = node.path;
    frame.src = url;
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-forms allow-popups");
    previewBody.append(frame);
  }

  if (updateHash) {
    history.replaceState(null, "", `#${encodeURIComponent(node.path)}`);
  }
}

function previewUrl(node) {
  if (node.kind === "markdown") return `md?path=${encodeURIComponent(node.path)}`;
  if (node.kind === "nifti") return `nii?images=${encodeURIComponent(rawUrl(node))}`;
  if (node.kind === "text") return `view?path=${encodeURIComponent(node.path)}`;
  return rawUrl(node);
}

function rawUrl(node) {
  return `files/${encodePath(node.path)}`;
}

function encodePath(path) {
  return path.split("/").map(encodeURIComponent).join("/");
}

function renderBreadcrumbs(path) {
  breadcrumbs.innerHTML = "";
  path.split("/").forEach((part, index, parts) => {
    const crumb = document.createElement("span");
    crumb.textContent = part;
    if (index === parts.length - 1) crumb.className = "current";
    breadcrumbs.append(crumb);
    if (index < parts.length - 1) {
      const separator = document.createElement("span");
      separator.className = "breadcrumb-separator";
      separator.textContent = "/";
      breadcrumbs.append(separator);
    }
  });
}

function expandAncestors(path) {
  const parts = path.split("/");
  parts.pop();
  let current = "";
  parts.forEach((part) => {
    current = current ? `${current}/${part}` : part;
    expandedPaths.add(current);
  });
}

function findFile(nodes, path) {
  for (const node of nodes) {
    if (node.type === "file" && node.path === path) return node;
    if (node.type === "directory") {
      const found = findFile(node.children, path);
      if (found) return found;
    }
  }
  return null;
}

function firstPreviewable(nodes) {
  for (const node of nodes) {
    if (node.type === "file" && node.kind !== "binary") return node;
    if (node.type === "directory") {
      const found = firstPreviewable(node.children);
      if (found) return found;
    }
  }
  return null;
}
