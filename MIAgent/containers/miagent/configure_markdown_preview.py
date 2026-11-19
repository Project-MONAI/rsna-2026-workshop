#!/usr/bin/env python3
"""Set Markdown preview defaults while preserving other user settings."""

import json
import os
from pathlib import Path

settings = Path(os.environ["HOME"]) / ".local/share/code-server/User/settings.json"
settings.parent.mkdir(parents=True, exist_ok=True)
config = json.loads(settings.read_text()) if settings.exists() else {}
associations = config.setdefault("workbench.editorAssociations", {})
associations.update({"*.md": "vscode.markdown.preview.editor",
                     "*.markdown": "vscode.markdown.preview.editor"})
settings.write_text(json.dumps(config, indent=2) + "\n")
