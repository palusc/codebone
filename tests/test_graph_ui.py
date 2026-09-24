"""The graph page: it must never interpret analysed data as HTML, must survive odd keys, and must scale."""
import json
import re
import shutil
import subprocess

import pytest

from src.graph_ui import build_live_graph_html

NODE = shutil.which("node")


def script(port=8053):
    return re.search(r"<script>(.*)</script>", build_live_graph_html(port), re.S).group(1)


def test_page_never_builds_html_from_data():
    assert "innerHTML" not in script()
    assert "onclick=\"focusNode(" not in build_live_graph_html(8053)


HARNESS = r"""
const el = () => new Proxy(function(){}, {
  get: (t, k) => k === 'classList' ? {add(){}, remove(){}, toggle(){}} : k === 'style' ? {} :
       k === 'getContext' ? () => new Proxy({}, {get: () => () => ({width: 10}), set: () => true}) :
       (k === 'addEventListener' ? () => {} : k === 'querySelectorAll' ? () => [] : el()),
  set: () => true, apply: () => el() });
global.document = {getElementById: () => el(), querySelectorAll: () => [], addEventListener(){}, createElement: () => el(), visibilityState: 'hidden'};
global.window = {innerWidth: 1300, innerHeight: 850, addEventListener(){}, devicePixelRatio: 1};
global.requestAnimationFrame = () => {}; global.setTimeout = () => 0; global.fetch = () => new Promise(() => {});
const src = require('fs').readFileSync(0, 'utf8').replace(/loadAll\(\)\.then[^\n]*\n?$/, '');
eval(src + `;
  const N = __N__;
  const files = {}, paths = [];
  for (let i = 0; i < N; i++) { const p = 'pkg' + (i % 40) + '/m' + i + '.py'; paths.push(p);
    files[p] = {path: p, domains: ['toString', '__proto__', 'constructor'][i % 3] ? [['toString', 'constructor', 'D' + (i % 7)][i % 3]] : [],
                tables: ['T' + (i % 150)], routes: [], events: [], summary: '</script><img src=x onerror=alert(1)>'}; }
  const gEdges = []; for (let i = 0; i + 6 < N; i++) gEdges.push({from: paths[i], to: paths[i + 6], type: 'table', entity: 'T'});
  const t = Date.now();
  buildGraph({nodes: paths, files, edges: gEdges}, true);
  console.log(JSON.stringify({nodes: nodes.length, ms: Date.now() - t}));
`);
"""


@pytest.mark.skipif(NODE is None, reason="node not installed")
@pytest.mark.parametrize("n,limit_ms", [(60, 1500), (2000, 4000)])
def test_build_graph_survives_prototype_named_domains_and_scales(n, limit_ms):
    out = subprocess.run([NODE, "-e", HARNESS.replace("__N__", str(n))], input=script(), capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["nodes"] >= n and res["ms"] < limit_ms
