#!/usr/bin/env python3
"""Download the exact local Qwen revision into the persistent HF cache."""

import json
import os
import time

from huggingface_hub import snapshot_download

started = time.monotonic()
model = os.environ["MIAgent_LLM_MODEL"]
revision = os.environ["MIAgent_LLM_REVISION"]
path = snapshot_download(model, revision=revision, token=False)
print(json.dumps({"model": model, "revision": revision, "path": path,
                  "download_seconds": round(time.monotonic() - started, 3)}), flush=True)
