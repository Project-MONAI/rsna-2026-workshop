#!/usr/bin/env python3
"""Submit three short concurrent chats without altering the running model."""

import json
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

barrier = threading.Barrier(3)


def request(index):
    expected = f"SESSION_OK_{index}"
    body = {
        "model": os.environ.get("MIAgent_LLM_MODEL", "Qwen/Qwen3.8-27B-FP8"),
        "messages": [{"role": "user", "content": f"Reply with exactly {expected}"}],
        "temperature": 0, "max_tokens": 32,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    url = os.environ.get("MIAgent_LLM_API_BASE_URL", "http://llm:8000/v1") + "/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    barrier.wait()
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=120) as response:
        result = json.load(response)
    content = result["choices"][0]["message"]["content"]
    assert expected in content, f"Session {index} did not return its marker"
    return {"session": index, "ok": True, "seconds": round(time.monotonic() - started, 3)}


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=3) as executor:
        print(json.dumps(list(executor.map(request, (1, 2, 3)))))
