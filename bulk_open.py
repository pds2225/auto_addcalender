"""구글 캘린더 선택 일괄 열기 HTML/JS.

여러 탭을 같은 클릭에서 한꺼번에 열면 구글 캘린더처럼 무거운 페이지가
브라우저를 멈출 수 있다. 첫 탭만 사용자 제스처로 열고, 나머지는 짧은
간격으로 이어서 연다. 팝업이 막히면 중단하고 남은 일정은 다시 누른다.
"""

from __future__ import annotations

import json

OPEN_GAP_MS_DESKTOP = 500
OPEN_GAP_MS_MOBILE = 700

BULK_OPEN_SCRIPT = r"""
var openedIndexes = {};
var opening = false;
var OPEN_GAP_MS = 500;
try {
  if (typeof navigator !== 'undefined' && /iPhone|iPad|iPod|Android/i.test(navigator.userAgent || '')) {
    OPEN_GAP_MS = 700;
  }
} catch (e) {}

function openedOk(win) {
  return !!win;
}

function checkedItems() {
  var selected = [];
  items.forEach(function(item, i) {
    var cb = document.getElementById('chk' + i);
    if (cb && cb.checked) selected.push({ item: item, index: i });
  });
  return selected;
}

function setAll(checked) {
  if (opening) return;
  items.forEach(function(_, i) {
    var cb = document.getElementById('chk' + i);
    if (cb) cb.checked = checked;
  });
  updateButton();
}

function renderList() {
  var list = document.getElementById('bulk-list');
  list.innerHTML = '';
  items.forEach(function(item, i) {
    var row = document.createElement('div');
    row.className = 'item';

    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.id = 'chk' + i;
    cb.checked = !openedIndexes[i];
    cb.addEventListener('change', updateButton);

    var label = document.createElement('label');
    label.htmlFor = 'chk' + i;
    var titleText = openedIndexes[i] ? ('열림 · ' + item.title) : item.title;
    label.appendChild(document.createTextNode(titleText));
    var sub = document.createElement('span');
    sub.className = 'sub';
    sub.textContent = item.when;
    label.appendChild(sub);

    var link = document.createElement('a');
    link.href = item.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = '개별 열기';

    row.appendChild(cb);
    row.appendChild(label);
    row.appendChild(link);
    list.appendChild(row);
  });
}

function pendingItems() {
  return checkedItems().filter(function(entry) {
    return !openedIndexes[entry.index];
  });
}

function remainingCount() {
  var n = 0;
  items.forEach(function(_, i) {
    if (!openedIndexes[i]) n += 1;
  });
  return n;
}

function updateButton() {
  var btn = document.getElementById('bulk-btn');
  var msg = document.getElementById('bulk-msg');
  if (opening) return;
  var n = pendingItems().length;
  var openedCount = Object.keys(openedIndexes).length;
  btn.disabled = n === 0;
  if (remainingCount() === 0) {
    btn.textContent = '모두 열었습니다 (' + openedCount + '개)';
    msg.textContent = '각 구글 캘린더 탭에서 저장을 눌러 주세요.';
  } else if (n === 0) {
    btn.textContent = '선택 일괄 열기 (0개)';
    msg.textContent = '열 일정을 하나 이상 선택해 주세요.';
  } else if (openedCount > 0) {
    btn.textContent = '남은 일정 일괄 열기 (' + n + '개)';
    msg.textContent = openedCount + '개는 열었습니다. 팝업을 허용한 뒤 같은 버튼을 누르면 남은 ' + n + '개가 이어서 열립니다.';
  } else {
    btn.textContent = '선택 일괄 열기 (' + n + '개)';
    msg.textContent = '체크한 일정의 구글 캘린더 탭을 짧은 간격으로 순서대로 엽니다. 각 탭에서 저장을 눌러 주세요.';
  }
}

function markOpened(index) {
  openedIndexes[index] = true;
  var cb = document.getElementById('chk' + index);
  if (cb) cb.checked = false;
}

function openOne(entry, stamp) {
  var name = 'gcal_sel_' + stamp + '_' + entry.index;
  var win = window.open(entry.item.url, name);
  if (!openedOk(win)) return false;
  try {
    win.opener = null;
  } catch (e) {}
  markOpened(entry.index);
  return true;
}

function finishOpening() {
  opening = false;
  renderList();
  updateButton();
}

function openSelectedAll() {
  if (opening) return;
  var selected = pendingItems();
  if (!selected.length) {
    updateButton();
    return;
  }
  opening = true;
  var stamp = Date.now();
  var i = 0;
  var btn = document.getElementById('bulk-btn');
  var msg = document.getElementById('bulk-msg');
  btn.disabled = true;

  function showProgress() {
    btn.textContent = '여는 중 (' + i + '/' + selected.length + ')';
    msg.textContent = '구글 캘린더 탭을 여는 중 (' + i + '/' + selected.length + '). 잠시만 기다려 주세요.';
  }

  function tick() {
    try {
      if (i >= selected.length) {
        finishOpening();
        return;
      }
      if (!openOne(selected[i], stamp)) {
        finishOpening();
        return;
      }
      i += 1;
      showProgress();
      if (i >= selected.length) {
        finishOpening();
        return;
      }
      setTimeout(tick, OPEN_GAP_MS);
    } catch (e) {
      finishOpening();
    }
  }

  tick();
}

renderList();
updateButton();
"""


def bulk_open_iframe_height(count: int) -> int:
    list_height = min(count, 6) * 52
    return 180 + list_height


def build_bulk_open_page(items: list[dict]) -> str:
    count = len(items)
    list_height = min(count, 6) * 52
    items_json = json.dumps(items, ensure_ascii=False).replace("<", "\\u003c")
    head = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    padding: 2px 0;
  }}
  .toolbar {{
    display: flex;
    gap: 12px;
    margin-bottom: 8px;
  }}
  .toolbar button {{
    width: auto;
    background: none;
    color: #1a73e8;
    border: none;
    padding: 0;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }}
  #bulk-btn {{
    width: 100%;
    background: #1a73e8;
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 12px 14px;
    font-size: 15px;
    font-weight: 700;
    cursor: pointer;
  }}
  #bulk-btn:disabled {{
    background: #9aa0a6;
    cursor: not-allowed;
  }}
  #bulk-list {{
    margin-top: 10px;
    max-height: {list_height}px;
    overflow-y: auto;
  }}
  .item {{
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 8px 2px;
    border-bottom: 1px solid #eee;
  }}
  .item input[type=checkbox] {{
    width: 18px;
    height: 18px;
    margin-top: 3px;
    flex-shrink: 0;
    accent-color: #1a73e8;
    cursor: pointer;
  }}
  .item label {{
    flex: 1;
    font-size: 14px;
    line-height: 1.45;
    cursor: pointer;
  }}
  .item label .sub {{
    display: block;
    font-size: 12px;
    color: #5f6368;
  }}
  .item a {{
    flex-shrink: 0;
    margin-top: 2px;
    font-size: 12px;
    color: #1a73e8;
    text-decoration: none;
    white-space: nowrap;
  }}
  #bulk-msg {{
    margin-top: 8px;
    font-size: 12px;
    color: #5f6368;
    line-height: 1.5;
  }}
</style>
</head>
<body>
<div class="toolbar">
  <button type="button" onclick="setAll(true)">전체 선택</button>
  <button type="button" onclick="setAll(false)">전체 해제</button>
</div>
<button id="bulk-btn" type="button" onclick="openSelectedAll()">선택 일괄 열기 ({count}개)</button>
<div id="bulk-list"></div>
<p id="bulk-msg">체크한 일정의 구글 캘린더 탭을 짧은 간격으로 순서대로 엽니다. 각 탭에서 저장을 눌러 주세요.</p>
<script>
var items = {items_json};
"""
    return head + BULK_OPEN_SCRIPT + "\n</script>\n</body>\n</html>\n"
