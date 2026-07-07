import os

import streamlit.components.v1 as components

_PARENT_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIR = os.path.join(_PARENT_DIR, "frontend")
_clipboard_paste = components.declare_component("clipboard_paste", path=_FRONTEND_DIR)


def clipboard_paste_zone(
    label="여기를 클릭한 뒤 Ctrl+V(⌘+V)로 붙여넣거나, 이미지 파일을 끌어다 놓으세요.",
    key=None,
):
    return _clipboard_paste(label=label, key=key, default=None)
