import os

import streamlit.components.v1 as components

_PARENT_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIR = os.path.join(_PARENT_DIR, "frontend")
_clipboard_paste = components.declare_component("clipboard_paste", path=_FRONTEND_DIR)


def clipboard_paste_zone(
    label="모바일: 버튼 또는 길게 눌러 붙여넣기 · PC: Ctrl+V / 드래그앤드롭",
    key=None,
):
    return _clipboard_paste(label=label, key=key, default=None)
