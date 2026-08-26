"""선택 일괄 열기가 브라우저를 멈추지 않는지 검증한다."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import bulk_open

APP_PY = Path(__file__).resolve().parent / "app.py"
HARNESS_JS = r"""
const fs = require('fs');
const script = fs.readFileSync(process.argv[2], 'utf8');
const scenario = process.argv[3];

class FakeEl {
  constructor(tag) {
    this.tagName = tag;
    this.children = [];
    this.style = {};
    this.className = '';
    this.type = '';
    this.href = '';
    this.target = '';
    this.rel = '';
    this.htmlFor = '';
    this.textContent = '';
    this.checked = false;
    this.disabled = false;
    this._id = '';
    this._innerHTML = '';
    this.listeners = {};
  }
  set id(value) {
    this._id = value;
    if (typeof document !== 'undefined' && document._byId) {
      document._byId[value] = this;
    }
  }
  get id() {
    return this._id;
  }
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  addEventListener(type, fn) {
    this.listeners[type] = fn;
  }
  click() {
    document._clicks.push(this);
  }
  remove() {}
  set innerHTML(value) {
    this._innerHTML = value;
    if (value === '') this.children = [];
  }
  get innerHTML() {
    return this._innerHTML;
  }
}

const timers = [];
let now = 0;
global.setTimeout = function(fn, ms) {
  timers.push({ fn, at: now + (ms || 0) });
  return timers.length;
};

function flushTimers() {
  while (timers.length) {
    timers.sort((a, b) => a.at - b.at);
    const t = timers.shift();
    now = t.at;
    t.fn();
  }
}

global.navigator = { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120' };

global.document = {
  _byId: {},
  _clicks: [],
  body: null,
  getElementById(id) {
    return this._byId[id] || null;
  },
  createElement(tag) {
    return new FakeEl(tag);
  },
  createTextNode(text) {
    const el = new FakeEl('#text');
    el.textContent = text;
    return el;
  },
};

const body = new FakeEl('body');
document.body = body;
const list = new FakeEl('div');
list.id = 'bulk-list';
const btn = new FakeEl('button');
btn.id = 'bulk-btn';
const msg = new FakeEl('p');
msg.id = 'bulk-msg';

const openLog = [];
let openCalls = 0;
let blockFrom = null;
if (scenario === 'block-all') blockFrom = 1;
if (scenario === 'block-after-2') blockFrom = 3;

global.window = {
  open(url, name) {
    openCalls += 1;
    if (blockFrom !== null && openCalls >= blockFrom) {
      openLog.push({ url, name, t: now, blocked: true });
      return null;
    }
    const win = { closed: true, opener: { keep: true } };
    openLog.push({ url, name, t: now, blocked: false, win });
    return win;
  },
};

global.Date.now = () => 1700000000000;

eval(script);

function run(name) {
  if (name === 'double-click') {
    openSelectedAll();
    openSelectedAll();
    flushTimers();
    return;
  }
  if (name === 'skip-opened') {
    openedIndexes[0] = true;
    document.getElementById('chk0').checked = false;
    openSelectedAll();
    flushTimers();
    return;
  }
  openSelectedAll();
  flushTimers();
}

run(scenario);

const gaps = [];
for (let i = 1; i < openLog.length; i++) {
  gaps.push(openLog[i].t - openLog[i - 1].t);
}

process.stdout.write(JSON.stringify({
  scenario,
  openCount: openLog.length,
  clickCount: document._clicks.length,
  gaps,
  openerNulledCount: openLog.filter((row) => row.win && row.win.opener === null).length,
  openedKeys: Object.keys(openedIndexes).sort(),
  opening,
  btnText: btn.textContent,
  urls: openLog.map((row) => row.url),
  names: openLog.map((row) => row.name),
}));
"""


def _script_with_items(count: int = 5) -> str:
    items = [
        {"url": f"https://calendar.example/{i}", "title": f"일정 {i}", "when": "08/26(수) 09:00"}
        for i in range(count)
    ]
    items_json = json.dumps(items, ensure_ascii=False)
    return f"var items = {items_json};\n" + bulk_open.BULK_OPEN_SCRIPT


def _run_js(scenario: str, count: int = 5) -> dict:
    script = _script_with_items(count)
    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "bulk.js"
        harness_path = Path(tmp) / "harness.js"
        script_path.write_text(script, encoding="utf-8")
        harness_path.write_text(HARNESS_JS, encoding="utf-8")
        result = subprocess.run(
            ["node", str(harness_path), str(script_path), scenario],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    if result.returncode != 0:
        raise AssertionError(
            f"node failed ({result.returncode})\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return json.loads(result.stdout)


class BulkOpenPageTests(unittest.TestCase):
    def test_page_contains_staggered_open_guards(self):
        html = bulk_open.build_bulk_open_page(
            [
                {"url": "https://calendar.example/a", "title": "A", "when": "08/26 09:00"},
                {"url": "https://calendar.example/b", "title": "B", "when": "08/26 10:00"},
            ]
        )
        self.assertIn("setTimeout(tick, OPEN_GAP_MS)", html)
        self.assertIn("win.opener = null", html)
        self.assertIn("if (opening) return", html)
        self.assertNotIn("a.click()", html)
        self.assertNotIn("win.closed", html)
        self.assertNotIn("한 번에 엽니다", html)
        self.assertIn("<", html)
        self.assertNotIn("</script>", bulk_open.BULK_OPEN_SCRIPT)

    def test_script_escapes_html_in_titles(self):
        html = bulk_open.build_bulk_open_page(
            [{"url": "https://calendar.example/a", "title": "<img src=x>", "when": "08/26"}]
        )
        self.assertNotIn("<img src=x>", html)
        self.assertIn("\\u003cimg src=x>", html)

    def test_app_py_no_longer_opens_tabs_in_a_tight_loop(self):
        source = APP_PY.read_text(encoding="utf-8")
        self.assertNotIn("selected.forEach(function(entry)", source)
        self.assertIn("build_bulk_open_page", source)


class BulkOpenRuntimeTests(unittest.TestCase):
    def test_closed_windows_are_not_retried_or_clicked(self):
        data = _run_js("open-all", 5)
        self.assertEqual(data["openCount"], 5)
        self.assertEqual(data["clickCount"], 0)
        self.assertEqual(data["openedKeys"], ["0", "1", "2", "3", "4"])
        self.assertFalse(data["opening"])
        self.assertEqual(data["gaps"], [bulk_open.OPEN_GAP_MS_DESKTOP] * 4)
        self.assertEqual(data["openerNulledCount"], 5)

    def test_stops_when_popup_is_blocked(self):
        data = _run_js("block-all", 5)
        self.assertEqual(data["openCount"], 1)
        self.assertEqual(data["clickCount"], 0)
        self.assertEqual(data["openedKeys"], [])
        self.assertFalse(data["opening"])

    def test_keeps_already_opened_tabs_and_continues_the_rest(self):
        data = _run_js("block-after-2", 5)
        self.assertEqual(data["openCount"], 3)
        self.assertEqual(data["openedKeys"], ["0", "1"])
        self.assertEqual(data["clickCount"], 0)

    def test_double_click_does_not_start_a_second_burst(self):
        data = _run_js("double-click", 4)
        self.assertEqual(data["openCount"], 4)
        self.assertEqual(data["clickCount"], 0)

    def test_skips_already_opened_index(self):
        data = _run_js("skip-opened", 3)
        self.assertEqual(data["openCount"], 2)
        self.assertEqual(data["urls"], ["https://calendar.example/1", "https://calendar.example/2"])
        self.assertEqual(data["openedKeys"], ["0", "1", "2"])


if __name__ == "__main__":
    unittest.main()
