import streamlit as st

_HTML = """
<div id="zone" tabindex="0"></div>
<div id="status"></div>
"""

_CSS = """
#zone {
  min-height: 96px;
  padding: 16px;
  border: 2px dashed #9aa0a6;
  border-radius: 10px;
  background: #f8f9fa;
  color: #5f6368;
  text-align: center;
  line-height: 1.5;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s ease, background 0.15s ease;
}
#zone:focus,
#zone.active {
  border-color: #4285f4;
  background: #eef4ff;
  color: #1a73e8;
}
#status {
  margin-top: 8px;
  font-size: 12px;
  color: #188038;
  text-align: center;
  min-height: 16px;
}
"""

_JS = """
export default function(component) {
  const { setStateValue, parentElement, data } = component;
  const zone = parentElement.querySelector("#zone");
  const status = parentElement.querySelector("#status");
  const defaultLabel =
    "이 영역을 클릭한 뒤 Ctrl+V (Mac: ⌘+V)로 이미지를 붙여넣으세요.";

  zone.textContent = data.label || defaultLabel;

  zone.onclick = () => zone.focus();
  zone.onfocus = () => zone.classList.add("active");
  zone.onblur = () => zone.classList.remove("active");

  zone.onpaste = (event) => {
    const items = event.clipboardData && event.clipboardData.items;
    if (!items) {
      status.textContent = "클립보드 접근이 지원되지 않는 환경입니다.";
      return;
    }

    for (const item of items) {
      if (!item.type.startsWith("image/")) {
        continue;
      }
      const file = item.getAsFile();
      if (!file) {
        continue;
      }
      const reader = new FileReader();
      reader.onload = () => {
        setStateValue("image_data", reader.result);
        status.textContent = "이미지가 붙여넣어졌습니다.";
      };
      reader.onerror = () => {
        status.textContent = "이미지를 읽지 못했습니다.";
      };
      reader.readAsDataURL(file);
      event.preventDefault();
      return;
    }

    status.textContent =
      "클립보드에 이미지가 없습니다. 이미지를 복사한 뒤 다시 붙여넣어 주세요.";
  };
}
"""

_clipboard_paste = st.components.v2.component(
    "clipboard_paste",
    html=_HTML,
    css=_CSS,
    js=_JS,
)


def clipboard_paste_zone(
    label="이 영역을 클릭한 뒤 Ctrl+V (Mac: ⌘+V)로 이미지를 붙여넣으세요.",
    key=None,
):
    result = _clipboard_paste(
        data={"label": label},
        default={"image_data": None},
        key=key,
        on_image_data_change=lambda: None,
        height=130,
    )
    return result.image_data if result else None
