#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import mimetypes
import re
import shutil
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


STATIC_DIR = Path(__file__).resolve().parent / "static"
SKIP_TREE_NAMES = {
    ".DS_Store",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "runtime",
}
TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".css",
    ".csv",
    ".ini",
    ".js",
    ".json",
    ".jsonl",
    ".log",
    ".py",
    ".sh",
    ".slurm",
    ".toml",
    ".ts",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
IMAGE_SUFFIXES = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
NIIVUE_BROKEN_OVERLAY_LOADER = """  if (je(A.uri)) {
    const e = new UA(A.data, A.uri, t.defaultOverlayColormap, 0.5);
    g.addVolume(e);
"""
NIIVUE_FIXED_OVERLAY_LOADER = """  if (je(A.uri)) {
    const e = await UA.loadFromUrl({
      url: A.data || A.uri,
      name: A.uri,
      colormap: t.defaultOverlayColormap,
      opacity: 0.5
    });
    g.addVolume(e);
"""
NIIVUE_DEBUG_HANDLER = """    case "debugRequest":
      xa(B, A);
      break;
    default:
"""
NIIVUE_REVIEW_HANDLERS = """    case "debugRequest":
      xa(B, A);
      break;
    case "miagentWindow":
      {
        const C = t.value[B.index ?? 0], s = C?.volumes?.[0];
        if (s) {
          if (B.min == null || B.max == null) {
            s.cal_min = s.robust_min;
            s.cal_max = s.robust_max;
          } else {
            s.cal_min = B.min;
            s.cal_max = B.max;
          }
          C.updateGLVolume();
        }
      }
      break;
    case "miagentOpacity":
      {
        const C = t.value[B.index ?? 0], v = B.volume ?? 1;
        if (C?.volumes?.[v]) {
          const s = Number(B.opacity), o = Number.isFinite(s) ? Math.max(0, Math.min(1, s)) : 0.5;
          C.setOpacity(v, o);
        }
      }
      break;
    case "miagentLabelColormap":
      {
        const C = t.value[B.index ?? 0], s = C?.volumes?.[B.volume ?? 1];
        if (s) {
          s.setColormapLabel(B.colormap);
          C.updateGLVolume();
        }
      }
      break;
    default:
"""
FILE_ORDER = {
    "challenge.md": 0,
    "state.md": 1,
    "trajectory.md": 2,
    "dashboard.md": 3,
    "literature.md": 4,
    "candidates.md": 5,
    "baseline.md": 6,
    "experiment.md": 7,
    "result_viewer.html": 8,
    "jobs": 9,
}


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class WebUIHandler(BaseHTTPRequestHandler):
    challenge_dir: Path
    files_dir: Path
    data_dir: Path | None
    niivue_root: Path | None
    runtime_dir: Path
    start_at_root: bool = False
    inference_dir: Path | None = None

    def resolve_file(self, rel: str) -> tuple[Path | None, Path, str]:
        if self.inference_dir is not None:
            namespace, separator, remainder = unquote(rel).lstrip("/").partition("/")
            roots = {"challenge": self.files_dir, "inference_tmp": self.inference_dir}
            if namespace in roots:
                root = roots[namespace]
                return safe_join(root, remainder if separator else ""), root, namespace + "/"
        return safe_join(self.files_dir, rel), self.files_dir, ""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        if route == "/":
            self.serve_file(STATIC_DIR / "index.html")
            return
        if route.startswith("/static/"):
            target = safe_join(STATIC_DIR, route.removeprefix("/static/"))
            if target is None:
                self.send_error(404, "Static asset not found")
                return
            self.serve_file(target)
            return
        if route.startswith("/niivue/"):
            if self.niivue_root is None:
                self.send_error(503, "NiiVue assets are unavailable")
                return
            target = safe_join(self.niivue_root, route.removeprefix("/niivue/"))
            if target is None or not target.is_file():
                self.send_error(404, "NiiVue asset not found")
                return
            if route == "/niivue/niivue/index.js":
                self.send_text(patched_niivue_script(target), "text/javascript; charset=utf-8")
                return
            self.serve_file(target)
            return
        if route == "/api/tree":
            tree = build_browser_tree(self.files_dir, self.inference_dir)
            tree["start_at_root"] = self.start_at_root
            self.send_json(tree)
            return
        if route == "/api/runtime":
            self.send_json(runtime_snapshot(self.challenge_dir, self.runtime_dir))
            return
        if route == "/api/raw":
            query = parse_qs(parsed.query)
            rel = query.get("path", [""])[0]
            target, _, _ = self.resolve_file(rel)
            if target is None or not target.exists():
                self.send_error(404, "File not found")
                return
            self.send_text(read_text(target), "text/plain; charset=utf-8")
            return
        if route == "/md":
            query = parse_qs(parsed.query)
            rel = query.get("path", [""])[0]
            target, root, prefix = self.resolve_file(rel)
            if target is None or not target.exists() or target.suffix.lower() != ".md":
                self.send_error(404, "Markdown file not found")
                return
            self.send_text(render_markdown_page(target, root, prefix), "text/html; charset=utf-8")
            return
        if route == "/nii":
            if self.niivue_root is None:
                self.send_error(503, "NiiVue assets are unavailable")
                return
            self.send_text(render_niivue_page(), "text/html; charset=utf-8")
            return
        if route == "/view":
            query = parse_qs(parsed.query)
            rel = query.get("path", [""])[0]
            target, root, _ = self.resolve_file(rel)
            if target is None or not target.exists() or not target.is_file():
                self.send_error(404, "File not found")
                return
            self.send_text(render_text_page(target, root), "text/html; charset=utf-8")
            return
        if route.startswith("/files/"):
            rel = route.removeprefix("/files/")
            target, _, _ = self.resolve_file(rel)
            if target is None or not target.exists() or not target.is_file():
                self.send_error(404, "File not found")
                return
            self.serve_file(target)
            return
        if route.startswith("/data-files/"):
            if self.data_dir is None:
                self.send_error(503, "Data directory is unavailable")
                return
            rel = route.removeprefix("/data-files/")
            target = safe_join(self.data_dir, rel)
            if target is None or not target.exists() or not target.is_file():
                self.send_error(404, "Data file not found")
                return
            self.serve_file(target)
            return
        if route == "/asset":
            query = parse_qs(parsed.query)
            rel = query.get("path", [""])[0]
            target, _, _ = self.resolve_file(rel)
            if target is None or not target.exists() or not target.is_file():
                self.send_error(404, "Asset not found")
                return
            self.serve_file(target)
            return
        self.send_error(404, "Not found")

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404, "File not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with path.open("rb") as source:
            shutil.copyfileobj(source, self.wfile, length=1024 * 1024)

    def send_json(self, data: object) -> None:
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_text(self, text: str, content_type: str) -> None:
        payload = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def safe_join(root: Path, rel: str) -> Path | None:
    rel = unquote(rel).lstrip("/")
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def build_file_tree(root: Path) -> dict[str, object]:
    root = root.resolve()
    file_count = 0

    def visit(directory: Path) -> list[dict[str, object]]:
        nonlocal file_count
        nodes: list[dict[str, object]] = []
        try:
            children = sorted(directory.iterdir(), key=tree_sort_key)
        except OSError:
            return nodes
        for child in children:
            if child.name in SKIP_TREE_NAMES or child.name.startswith(".") or child.is_symlink():
                continue
            rel = rel_path(child, root)
            if child.is_dir():
                nodes.append(
                    {
                        "name": child.name,
                        "path": rel,
                        "type": "directory",
                        "experiment": bool(re.match(r"^exp\d+", child.name, re.IGNORECASE)),
                        "children": visit(child),
                    }
                )
                continue
            if not child.is_file():
                continue
            file_count += 1
            try:
                size = child.stat().st_size
            except OSError:
                size = 0
            nodes.append(
                {
                    "name": child.name,
                    "path": rel,
                    "type": "file",
                    "kind": file_kind(child),
                    "size": size,
                }
            )
        return nodes

    tree = visit(root)
    return {
        "name": root.name,
        "root": str(root),
        "file_count": file_count,
        "tree": tree,
    }


def build_browser_tree(root: Path, inference: Path | None) -> dict[str, object]:
    if inference is None:
        return build_file_tree(root)

    def prefix_paths(nodes: list[dict[str, object]], namespace: str) -> None:
        for node in nodes:
            node["path"] = namespace + "/" + str(node["path"])
            if node["type"] == "directory":
                prefix_paths(node["children"], namespace)

    groups = []
    count = 0
    for namespace, directory in (("challenge", root), ("inference_tmp", inference)):
        tree = build_file_tree(directory)
        prefix_paths(tree["tree"], namespace)
        count += tree["file_count"]
        groups.append({"name": namespace, "path": namespace, "type": "directory", "children": tree["tree"]})
    return {"name": "MIAgent", "root": "challenge/ and inference_tmp/", "file_count": count,
            "tree": groups, "multiple_roots": True}


def tree_sort_key(path: Path) -> tuple[int, int, str]:
    explicit_order = FILE_ORDER.get(path.name.lower())
    if explicit_order is not None:
        return (0, explicit_order, path.name.lower())
    if path.is_dir():
        return (1, 0, path.name.lower())
    return (2, 0, path.name.lower())


def file_kind(path: Path) -> str:
    if path.name.lower().endswith((".nii", ".nii.gz")):
        return "nifti"
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "markdown"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if suffix in TEXT_SUFFIXES or not suffix:
        return "text"
    return "binary"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def patched_niivue_script(path: Path) -> str:
    """Repair the browser overlay loader shipped by NiiVue VS Code 2.5.7."""
    source = read_text(path)
    source = source.replace(
        NIIVUE_BROKEN_OVERLAY_LOADER,
        NIIVUE_FIXED_OVERLAY_LOADER,
        1,
    )
    source = source.replace(NIIVUE_DEBUG_HANDLER, NIIVUE_REVIEW_HANDLERS, 1)
    source = source.replace('/* @__PURE__ */ T(Ir, { ...g }),', '', 1)
    source = source.replace('hideUI: EA(3),', 'hideUI: EA(0),', 1)
    return source.replace(
        'g.isLoaded = !0, g.body = null,',
        'g.isLoaded = !0, window.miagentNiivue.configure(g), g.body = null,',
        1,
    )


def read_json_file(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def runtime_snapshot(challenge_dir: Path, runtime_dir: Path) -> dict[str, object]:
    """Read-only summary for the report header; it never controls a job."""
    challenges: list[dict[str, object]] = []
    try:
        challenge_paths = sorted(path for path in challenge_dir.iterdir() if path.is_dir() and not path.name.startswith("."))
    except OSError:
        challenge_paths = []
    for path in challenge_paths:
        job_states: dict[str, int] = {}
        for job_path in path.glob("baselines/*/runs/*/job.json"):
            state = str(read_json_file(job_path).get("state", "unknown"))
            job_states[state] = job_states.get(state, 0) + 1
        heartbeat = read_json_file(runtime_dir / "heartbeats" / path.name / "state.json")
        if heartbeat or job_states:
            challenges.append(
                {
                    "challenge": path.name,
                    "heartbeat_status": str(heartbeat.get("status", "not_started")),
                    "last_pulse_utc": heartbeat.get("last_pulse_utc"),
                    "jobs": job_states,
                }
            )
    gpu_state = read_json_file(runtime_dir / "locks" / "gpu0.state.json")
    return {
        "challenges": challenges,
        "gpu": {
            "state": "running" if gpu_state else "idle",
            "challenge": gpu_state.get("challenge"),
            "baseline": gpu_state.get("baseline"),
            "experiment": gpu_state.get("experiment"),
        },
    }


def render_markdown_page(path: Path, root: Path, prefix: str = "") -> str:
    rel = rel_path(path, root)
    body = render_markdown(read_text(path), path.parent, root, prefix)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(rel)}</title>
  <style>
    body {{
      margin: 0;
      background: #f6f7f9;
      color: #20252b;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }}
    main {{
      width: min(1100px, calc(100% - 40px));
      margin: 28px auto 48px;
      background: #fff;
      border: 1px solid #dce1e8;
      border-radius: 8px;
      padding: 24px;
      box-shadow: 0 1px 2px rgba(18, 28, 45, 0.04);
    }}
    .path {{
      margin: 0 0 18px;
      color: #687381;
      font-size: 13px;
      overflow-wrap: anywhere;
    }}
    h1, h2, h3, h4 {{ line-height: 1.2; }}
    h1 {{ margin-top: 0; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 14px 0 22px;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      vertical-align: top;
      border: 1px solid #dce1e8;
      padding: 8px 10px;
    }}
    th {{ background: #f8fafc; }}
    pre {{
      overflow-x: auto;
      background: #101828;
      color: #f8fafc;
      padding: 14px;
      border-radius: 8px;
    }}
    code {{
      background: #f1f5f9;
      border-radius: 4px;
      padding: 1px 4px;
    }}
    pre code {{ background: transparent; padding: 0; }}
    img {{ max-width: 100%; height: auto; }}
    a {{ color: #2457d6; }}
  </style>
</head>
<body>
  <main>
    <p class="path">{html.escape(rel)}</p>
    {body}
  </main>
</body>
</html>"""


def render_niivue_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NiiVue</title>
  <link rel="stylesheet" href="niivue/vscode-styles.css">
  <link rel="stylesheet" href="niivue/niivue/index.css">
  <style>
    html, body, #app { color-scheme: light; }
    body > #app { color: #111827; background: #f8fafc; }
    body > #app button, body > #app [role="button"], body > #app select {
      color: #111827 !important; background: #fff !important;
      border-color: #94a3b8 !important;
    }
    body > #app button:hover, body > #app [role="button"]:hover {
      color: #0f172a !important; background: #e2e8f0 !important;
    }
    body > #app a { color: #1d4ed8 !important; }
    #miagent-review {
      position: fixed; right: 10px; bottom: 10px; z-index: 1000;
      padding: 8px 10px; border-radius: 7px; color: white;
      background: rgba(17, 24, 39, .88); font: 13px system-ui, sans-serif;
    }
    #miagent-review label { margin-right: 6px; }
    #miagent-review select { color: #111827; background: white; padding: 3px; }
    #miagent-review .modes { margin-top: 7px; display: flex; gap: 5px; }
    #miagent-review button { padding: 3px 7px; color: white; background: #374151; border: 1px solid #6b7280; border-radius: 4px; }
    #miagent-review button.active { background: #2563eb; }
    #miagent-review .legend { margin-top: 6px; font-size: 12px; }
    #miagent-review { display: none !important; }
    #miagent-contrast-toolbar {
      position: fixed; right: 54px; bottom: 10px; z-index: 1000;
      display: flex; align-items: center; gap: 6px; padding: 4px 8px;
      max-width: calc(100% - 74px); box-sizing: border-box;
      height: 32px; border: 1px solid #94a3b8; border-radius: 4px;
      background: #fff; color: #111827; font: 13px system-ui, sans-serif;
    }
    #miagent-contrast-toolbar select { min-width: 0; max-width: 180px; color: #111827; background: #fff; }
    #miagent-render-toggle {
      position: fixed; right: 10px; bottom: 10px; z-index: 1000;
      width: 36px; height: 32px; padding: 0; border-radius: 4px;
      border: 1px solid #94a3b8; background: #fff; color: #111827;
      font: 600 13px system-ui, sans-serif; cursor: pointer;
    }
    #miagent-render-toggle[aria-pressed="true"] { background: #bbf7d0; border-color: #15803d; }
  </style>
</head>
<body>
  <div id="app"></div>
  <button id="miagent-render-toggle" type="button" title="Show 3D volume" aria-label="Show 3D volume" aria-pressed="false">3D</button>
  <div id="miagent-contrast-toolbar" role="toolbar" aria-label="CT contrast presets">
    <label for="miagent-window">CT contrast</label>
    <select id="miagent-window">
      <option value="auto">Automatic</option>
      <option value="cardiac">Cardiac [-200, 800] HU</option>
      <option value="abdomen">Abdomen [-150, 250] HU</option>
      <option value="soft">Soft tissue [-160, 240] HU</option>
      <option value="lung">Lung [-1350, 150] HU</option>
      <option value="bone">Bone [-500, 1500] HU</option>
    </select>
  </div>
  <aside id="miagent-review" hidden>
    <div class="modes" id="miagent-modes"></div>
    <div class="legend" id="miagent-legend" hidden>Difference: green correct · pink FP · red FN · yellow wrong class</div>
  </aside>
  <script>
    // The bundled NiiVue web app handles `images=` itself, but only exposes its
    // overlay loader through window messages. Bridge same-origin `overlays=`
    // URLs into that loader so reports can link to an image + segmentation.
    (() => {
      const params = new URLSearchParams(window.location.search);
      const overlayUrls = (params.get("overlays") || "")
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
      if (!overlayUrls.length) return;

      const palettes = {
        heart: {
          R: [0, 230, 55, 30, 240, 245, 150, 20], G: [0, 60, 180, 140, 155, 215, 80, 205],
          B: [0, 60, 75, 230, 35, 40, 200, 210], A: [0, 210, 210, 210, 210, 210, 210, 210],
          I: [0, 1, 2, 3, 4, 5, 6, 7], labels: ["background", "LV", "RV", "LA", "RA", "myocardium", "aorta", "pulmonary artery"]
        },
        errors: {
          R: [0, 0, 255, 255, 255], G: [0, 255, 64, 0, 255], B: [0, 0, 160, 0, 0],
          A: [0, 230, 230, 230, 230], I: [0, 1, 2, 3, 4],
          labels: ["background", "correct foreground", "false positive", "false negative", "wrong class"]
        }
      };
      let overlayRequestsSent = false;
      let paletteApplied = false;
      let pollTimer = null;

      async function loadOverlays() {
        if (overlayRequestsSent) return;
        overlayRequestsSent = true;
        for (const url of overlayUrls) {
          const response = await fetch(url, { cache: "no-store" });
          if (!response.ok) throw new Error(`Could not load NiiVue overlay (${response.status}): ${url}`);
          const data = await response.arrayBuffer();
          window.postMessage({ type: "overlay", body: { data, uri: url, index: 0 } }, "*");
        }
      }

      window.addEventListener("message", (event) => {
        if (event.data?.type !== "debugAnswer") return;
        const volumeCount = Number(event.data.body);
        if (volumeCount > 0 && !overlayRequestsSent) {
          loadOverlays().catch((error) => console.error(error));
        }
        if (overlayRequestsSent && volumeCount >= 1 + overlayUrls.length && !paletteApplied) {
          paletteApplied = true;
          if (pollTimer !== null) window.clearInterval(pollTimer);
          const palette = palettes[params.get("palette") || ""];
          if (palette) window.postMessage({ type: "miagentLabelColormap", body: { index: 0, volume: 1, colormap: palette } }, "*");
        }
      });
      document.addEventListener("AppReady", () => {
        const askForVolumeCount = () => window.postMessage(
          { type: "debugRequest", body: "getNVolumes" },
          "*",
        );
        pollTimer = window.setInterval(askForVolumeCount, 100);
        askForVolumeCount();
      }, { once: true });

      const review = document.getElementById("miagent-review");
      const huOffset = Number(params.get("huOffset") || 0);
      const windows = { cardiac: [-200, 800], abdomen: [-150, 250], soft: [-160, 240], lung: [-1350, 150], bone: [-500, 1500] };
      document.getElementById("miagent-window").addEventListener("change", (event) => {
        const range = windows[event.target.value];
        const body = range ? { index: 0, min: range[0] + huOffset, max: range[1] + huOffset } : { index: 0, min: null, max: null };
        window.postMessage({ type: "miagentWindow", body }, "*");
      });
      const variants = [["prediction", "Prediction", "heart"], ["truth", "Ground truth", "heart"], ["difference", "Difference", "errors"]];
      const mode = params.get("mode") || "prediction";
      const modes = document.getElementById("miagent-modes");
      for (const [key, label, palette] of variants) {
        const overlay = params.get(key);
        if (!overlay) continue;
        const button = document.createElement("button");
        button.textContent = label;
        button.classList.toggle("active", key === mode);
        button.addEventListener("click", () => {
          const target = new URL(window.location.href);
          target.searchParams.set("overlays", overlay);
          target.searchParams.set("palette", palette);
          target.searchParams.set("mode", key);
          window.location.href = target.href;
        });
        modes.append(button);
      }
      document.getElementById("miagent-legend").hidden = mode !== "difference";
      review.hidden = params.get("embedded") === "1";
    })();
  </script>
  <script src="static/niivue-controls.js?v=compact-slices-3"></script>
  <script type="module" src="niivue/niivue/index.js?v=compact-slices-3"></script>
</body>
</html>"""


def render_text_page(path: Path, root: Path) -> str:
    rel = rel_path(path, root)
    text = read_text(path)
    if path.suffix.lower() in {".json", ".jsonl"}:
        try:
            if path.suffix.lower() == ".json":
                text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(rel)}</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{
      margin: 0;
      background: #ffffff;
      color: #24292f;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    header {{
      position: sticky;
      top: 0;
      padding: 10px 16px;
      border-bottom: 1px solid #d0d7de;
      background: #f6f8fa;
      color: #57606a;
      font: 12px/1.4 Inter, ui-sans-serif, system-ui, sans-serif;
      overflow-wrap: anywhere;
    }}
    pre {{
      margin: 0;
      padding: 16px;
      font: 13px/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      tab-size: 2;
    }}
  </style>
</head>
<body>
  <header>{html.escape(rel)}</header>
  <pre>{html.escape(text)}</pre>
</body>
</html>"""


def render_markdown(text: str, base_dir: Path, root: Path, prefix: str = "") -> str:
    lines = text.splitlines()
    out: list[str] = []
    paragraph: list[str] = []
    in_code = False
    code_lines: list[str] = []
    heading_ids: dict[str, int] = {}
    i = 0

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{inline_markdown(' '.join(paragraph), base_dir, root, prefix)}</p>")
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not in_code and stripped.startswith("<!--"):
            flush_paragraph()
            while i < len(lines) and "-->" not in lines[i]:
                i += 1
            i += 1
            continue
        if stripped.startswith("```"):
            if in_code:
                out.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph()
                in_code = True
            i += 1
            continue
        if in_code:
            code_lines.append(line)
            i += 1
            continue
        if not stripped:
            flush_paragraph()
            i += 1
            continue
        table = collect_table(lines, i)
        if table:
            flush_paragraph()
            out.append(render_table(table, base_dir, root, prefix))
            i += len(table)
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            base_id = markdown_heading_id(heading.group(2))
            occurrence = heading_ids.get(base_id, 0)
            heading_ids[base_id] = occurrence + 1
            heading_id = base_id if occurrence == 0 else f"{base_id}-{occurrence}"
            out.append(
                f'<h{level} id="{html.escape(heading_id)}">'
                f"{inline_markdown(heading.group(2), base_dir, root, prefix)}</h{level}>"
            )
            i += 1
            continue
        bullet = collect_bullets(lines, i)
        if bullet:
            flush_paragraph()
            out.append("<ul>" + "".join(f"<li>{inline_markdown(item, base_dir, root, prefix)}</li>" for item in bullet) + "</ul>")
            i += len(bullet)
            continue
        paragraph.append(stripped)
        i += 1
    flush_paragraph()
    if in_code:
        out.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(out)


def collect_table(lines: list[str], start: int) -> list[str]:
    if start + 1 >= len(lines):
        return []
    if not is_table_line(lines[start]) or not is_separator_line(lines[start + 1]):
        return []
    rows = [lines[start], lines[start + 1]]
    i = start + 2
    while i < len(lines) and is_table_line(lines[i]):
        rows.append(lines[i])
        i += 1
    return rows


def render_table(lines: list[str], base_dir: Path, root: Path, prefix: str = "") -> str:
    headers = split_row(lines[0])
    body_rows = [split_row(line) for line in lines[2:]]
    header_html = "".join(f"<th>{inline_markdown(cell, base_dir, root, prefix)}</th>" for cell in headers)
    rows_html = []
    for row in body_rows:
        cells = []
        for idx in range(len(headers)):
            value = row[idx] if idx < len(row) else ""
            cells.append(f"<td>{inline_markdown(value, base_dir, root, prefix)}</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    return "<table><thead><tr>" + header_html + "</tr></thead><tbody>" + "".join(rows_html) + "</tbody></table>"


def collect_bullets(lines: list[str], start: int) -> list[str]:
    items = []
    i = start
    while i < len(lines):
        match = re.match(r"^\s*[-*]\s+(.+)$", lines[i])
        if not match:
            break
        items.append(match.group(1).strip())
        i += 1
    return items


def inline_markdown(value: str, base_dir: Path, root: Path, prefix: str = "") -> str:
    escaped = html.escape(value)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)

    def image_replace(match: re.Match[str]) -> str:
        alt = match.group(1)
        href = html.unescape(match.group(2))
        return f'<img src="{html.escape(resolve_href(href, base_dir, root, "asset", prefix))}" alt="{alt}">'

    def link_replace(match: re.Match[str]) -> str:
        label = match.group(1)
        href = html.unescape(match.group(2))
        return f'<a href="{html.escape(resolve_href(href, base_dir, root, prefix=prefix))}">{label}</a>'

    escaped = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", image_replace, escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_replace, escaped)
    return escaped


def markdown_heading_id(value: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    text = re.sub(r"[`*~]", "", text).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s", "-", text) or "section"


def resolve_href(href: str, base_dir: Path, root: Path, kind: str = "", prefix: str = "") -> str:
    href = href.strip()
    if re.match(r"^(https?://|#)", href):
        return href
    path_part, separator, anchor = href.partition("#")
    fragment = f"#{anchor}" if separator else ""
    target = Path(unquote(path_part))
    if target.is_absolute():
        try:
            rel = str(target.resolve().relative_to(root.resolve()))
        except ValueError:
            return href
    else:
        rel = rel_path((base_dir / target).resolve(), root)
    if kind == "asset" or not rel.endswith(".md"):
        return "files/" + quote_path(prefix + rel) + fragment
    return "md?path=" + quote(prefix + rel) + fragment


def is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def is_separator_line(line: str) -> bool:
    if not is_table_line(line):
        return False
    cells = split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def quote_path(rel: str) -> str:
    return "/".join(quote(part) for part in rel.split("/"))


def rel_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def choose_port(host: str, requested: int) -> int:
    if requested == 0:
        return 0
    for port in range(requested, requested + 50):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only MIAgent challenge file browser.")
    parser.add_argument("--challenge", default="challenge/challenge_template", help="Challenge folder.")
    parser.add_argument("--root", help="File-browser root. Defaults to the challenge folder.")
    parser.add_argument("--inference-root", help="Optional second browser root for standalone inference outputs.")
    parser.add_argument("--start-at-root", action="store_true",
                        help="Open the browser root without automatically selecting a file.")
    parser.add_argument(
        "--data-root",
        default="/data",
        help="Read-only mounted dataset root exposed through /data-files/. Set empty to disable.",
    )
    parser.add_argument(
        "--niivue-extensions",
        default="/usr/local/share/code-server/extensions",
        help="Directory containing the installed NiiVue extension.",
    )
    parser.add_argument("--runtime", default="/runtime", help="Read-only runtime state directory.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port. Use 0 for any free port.")
    args = parser.parse_args()

    challenge_dir = Path(args.challenge).expanduser()
    if not challenge_dir.is_absolute():
        challenge_dir = (Path.cwd() / challenge_dir).resolve()
    if not challenge_dir.exists():
        raise SystemExit(f"Challenge folder does not exist: {challenge_dir}")
    files_dir = Path(args.root).expanduser() if args.root else challenge_dir
    if not files_dir.is_absolute():
        files_dir = (Path.cwd() / files_dir).resolve()
    if not files_dir.exists():
        raise SystemExit(f"File-browser root does not exist: {files_dir}")
    inference_dir = Path(args.inference_root).expanduser().resolve() if args.inference_root else None
    if inference_dir is not None and inference_dir.exists() and not inference_dir.is_dir():
        raise SystemExit(f"Inference root is not a directory: {inference_dir}")
    data_dir = Path(args.data_root).expanduser().resolve() if args.data_root else None
    if data_dir is not None and not data_dir.is_dir():
        data_dir = None
    extension_dir = Path(args.niivue_extensions).expanduser()
    niivue_candidates = sorted(extension_dir.glob("korbinianeckstein.niivue-*"))
    niivue_root = niivue_candidates[-1].resolve() if niivue_candidates else None
    runtime_dir = Path(args.runtime).expanduser().resolve()

    port = choose_port(args.host, args.port)
    if args.port and port != args.port:
        print(f"Port {args.port} is busy; using port {port or 'auto'} instead.")

    handler = type(
        "ConfiguredWebUIHandler",
        (WebUIHandler,),
        {
            "challenge_dir": challenge_dir,
            "start_at_root": args.start_at_root,
            "files_dir": files_dir,
            "inference_dir": inference_dir,
            "data_dir": data_dir,
            "niivue_root": niivue_root,
            "runtime_dir": runtime_dir,
        },
    )
    server = ReusableThreadingHTTPServer((args.host, port), handler)
    host, actual_port = server.server_address
    print(f"MIAgent files: http://{host}:{actual_port}/")
    print(f"Files: {files_dir}")
    print(f"Data files: {data_dir or 'unavailable'}")
    print(f"Challenge tracking: {challenge_dir}")
    print(f"NiiVue: {niivue_root or 'unavailable'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
