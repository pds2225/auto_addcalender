import os

import streamlit.components.v1 as components

_PARENT_DIR = os.path.dirname(os.path.abspath(__file__))
_FRONTEND_DIR = os.path.join(_PARENT_DIR, "frontend")
_clipboard_paste = components.declare_component("clipboard_paste", path=_FRONTEND_DIR)


def clipboard_paste_zone(
    label="이 영역을 클릭한 뒤 Ctrl+V (Mac: ⌘+V)로 이미지를 붙여넣으세요.",
    key=None,
):
    return _clipboard_paste(label=label, key=key, default=None)
