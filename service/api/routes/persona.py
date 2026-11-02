"""人格路由逻辑：读写与重要的事同步。"""
from __future__ import annotations

import os
import re


def get_persona(store) -> dict:
    return store.get_persona()


def set_persona(store, lock, body: dict, important_file: str) -> dict:
    """设置页保存。两半都能写；没传的字段保持原值。"""
    constitution = body.get("constitution")
    self_model = body.get("self_model")
    self_image = body.get("self_image")
    identity = body.get("identity")
    if constitution is None and self_model is None and self_image is None and identity is None:
        raise ValueError("constitution/self_model/self_image/identity all empty")
    with lock:
        data = store.set_persona(
            constitution=None if constitution is None else str(constitution),
            self_model=None if self_model is None else str(self_model),
            self_image=None if self_image is None else str(self_image),
            identity=None if identity is None else str(identity),
        )
    if constitution is not None:
        match = re.search(r"<!-- important:begin -->(.*?)<!-- important:end -->", str(constitution), re.S)
        if match:
            items = [
                line[2:].strip()
                for line in match.group(1).splitlines()
                if line.strip().startswith("- ")
            ]
            try:
                folder = os.path.dirname(important_file)
                if folder:
                    os.makedirs(folder, exist_ok=True)
                with open(important_file, "w", encoding="utf-8") as handle:
                    handle.write("# 非常重要的事\n\n" + "\n".join(f"- {x}" for x in items) + ("\n" if items else ""))
            except OSError:
                pass
    return data
