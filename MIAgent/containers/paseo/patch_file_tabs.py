"""Keep file selections as separate tabs in the pinned Paseo web UI."""

import gzip
import json
from pathlib import Path
import sys


VERSION = "0.9.2"
BEFORE = "if(b&&c({serverId:o.serverId,workspaceId:o.workspaceId,tabId:b.tabId,currentTarget:b.target,nextTarget:o.target}))"
AFTER = 'if(b&&"file"!==o.target.kind&&c({serverId:o.serverId,workspaceId:o.workspaceId,tabId:b.tabId,currentTarget:b.target,nextTarget:o.target}))'


def patch_ui(package):
    package = Path(package)
    version = json.loads((package / "package.json").read_text())["version"]
    if version != VERSION:
        raise RuntimeError(f"File-tab adjustment requires Paseo {VERSION}; found {version}")
    ui = package / "dist/server/web-ui"
    index = ui / "index.html"
    html = index.read_text(encoding="utf-8")
    if ".miagent-tabs-v1.js" in html:
        return
    bundles = list((ui / "_expo/static/js/web").glob("index-*.js"))
    if len(bundles) != 1:
        raise RuntimeError("Expected exactly one Paseo entry bundle")
    bundle = bundles[0]
    source = bundle.read_text(encoding="utf-8")
    if source.count(BEFORE) != 1 or bundle.name not in html:
        raise RuntimeError("Paseo file-preview implementation changed; review compatibility")
    # A new asset URL avoids serving an old cached bundle. Keep upstream assets
    # intact, and publish a matching gzip file for the server's compression path.
    target = bundle.with_name(bundle.stem + ".miagent-tabs-v1.js")
    content = source.replace(BEFORE, AFTER).encode("utf-8")
    target.write_bytes(content)
    target.with_suffix(".js.gz").write_bytes(gzip.compress(content, mtime=0))
    index.write_text(html.replace(bundle.name, target.name), encoding="utf-8")


if __name__ == "__main__":
    patch_ui(sys.argv[1])
