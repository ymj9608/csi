#!/usr/bin/env python3
"""Redraw the frozen graph as an unambiguous component/connection atlas.

No evaluator labels, source files, or model responses are read. Repeated endpoint
IDs are references to the component catalog, not newly invented components.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'docs/benchmarks/complex-mock/readable-v2'
WIDTH, HEIGHT = 3000, 2320
PALETTE = ['#126c83', '#7251a2', '#2759a5', '#996117', '#38734e', '#a34b63']


def esc(value):
    return html.escape(str(value), quote=True)


def render_svg(graph):
    nodes, edges, groups = graph['nodes'], graph['edges'], graph['groups']
    if len(nodes) > 28 or len(edges) > 26 or len(groups) > 6:
        raise ValueError('This fixed-size atlas supports 28 components and 26 connections.')
    lookup = {n['id']: n for n in nodes}
    colors = {g['id']: PALETTE[i] for i, g in enumerate(groups)}
    if len(lookup) != len(nodes) or any(n['group'] not in colors for n in nodes):
        raise ValueError('Invalid component IDs or group reference')
    if any(e['from'] not in lookup or e['to'] not in lookup or e['mode'] not in {'sync', 'async'} for e in edges):
        raise ValueError('Invalid connection')
    if any(len(n['id']) > 27 for n in nodes) or any(len(e['label']) > 29 for e in edges):
        raise ValueError('Text exceeds the fixed layout; resize explicitly before rendering.')
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
             '<rect width="3000" height="2320" fill="#f5f8fc"/>',
             '<g font-family="Arial, sans-serif" fill="#14283e">',
             '<rect width="3000" height="125" fill="#142d48"/>',
             '<text x="40" y="53" font-size="38" font-weight="700" fill="white">COMMERCE PLATFORM / COMPONENTS &amp; DIRECTED CONNECTIONS</text>',
             '<text x="40" y="93" font-size="23" fill="#dbe8f4">Synthetic design · 28 components · 26 connections · each endpoint uses its exact component ID</text>',
             '<text x="40" y="167" font-size="28" font-weight="700">01  COMPONENT CATALOG</text>',
             '<text x="1040" y="167" font-size="22" fill="#50647a">Identifier / responsibility / technology / logical group</text>']
    node_records = []
    for i, n in enumerate(nodes):
        x, y = 40 + (i % 4)*740, 190 + (i // 4)*92
        color = colors[n['group']]
        parts.extend([
            f'<g data-node-id="{esc(n["id"])}">',
            f'<rect x="{x}" y="{y}" width="710" height="84" rx="10" fill="white" stroke="#d3deea"/>',
            f'<rect x="{x}" y="{y}" width="6" height="84" rx="3" fill="{color}"/>',
            f'<text x="{x+18}" y="{y+29}" font-size="27" font-weight="700">{esc(n["id"])}</text>',
            f'<text x="{x+18}" y="{y+54}" font-size="22">{esc(n["label"])}</text>',
            f'<text x="{x+18}" y="{y+75}" font-size="18" fill="{color}">{esc(n["kind"])} · {esc(n["technology"])} · group: {esc(n["group"])}</text>',
            '</g>'])
        node_records.append({**n, 'bbox': [x,y,710,84]})
    for i, group in enumerate(groups):
        parts.append(f'<text x="{40+i*495}" y="856" font-size="18" fill="{colors[group["id"]]}">{esc(group["id"])} · {esc(group["label"])}</text>')
    parts.extend([
        '<text x="40" y="883" font-size="28" font-weight="700">02  CONNECTION ATLAS</text>',
        '<text x="520" y="883" font-size="22" fill="#50647a">Source → target. Repeated IDs refer to the same component above.</text>',
        '<path d="M2120 876 H2200" stroke="#2759a5" stroke-width="4"/><text x="2215" y="883" font-size="21">SYNC</text>',
        '<path d="M2375 876 H2455" stroke="#7251a2" stroke-width="4" stroke-dasharray="10 6"/><text x="2470" y="883" font-size="21">ASYNC</text>'])
    edge_records = []
    # Each edge has its own row: no shared shafts, crossings, or label leaders.
    for i, e in enumerate(edges):
        col, row = divmod(i, 13)
        x, y = 40 + col*1480, 920 + row*98
        mode = e['mode']; color = '#2759a5' if mode == 'sync' else '#7251a2'
        dash = '' if mode == 'sync' else ' stroke-dasharray="12 7"'
        parts.extend([
            f'<g data-edge-from="{esc(e["from"])}" data-edge-to="{esc(e["to"])}" data-edge-label="{esc(e["label"])}" data-edge-mode="{mode}">',
            f'<rect x="{x}" y="{y}" width="1440" height="90" rx="10" fill="white" stroke="#d3deea"/>',
            f'<text x="{x+13}" y="{y+18}" font-size="15" fill="#62758a">CONNECTION {i+1:02d}</text>'])
        for endpoint, dx in ((e['from'],18),(e['to'],982)):
            n = lookup[endpoint]
            fill = {'DATABASE':'#e9f5ef','MESSAGE_QUEUE':'#f0eafa','EXTERNAL_SERVICE':'#fff2df'}.get(n['kind'],'#f1f6fc')
            parts.extend([
                f'<rect x="{x+dx}" y="{y+28}" width="438" height="48" rx="7" fill="{fill}" stroke="#bdcbdb"/>',
                f'<text x="{x+dx+219}" y="{y+59}" text-anchor="middle" font-size="24" font-weight="700">{esc(endpoint)}</text>'])
        parts.extend([
            f'<text x="{x+720}" y="{y+30}" text-anchor="middle" font-size="23" fill="{color}">{esc(e["label"])}</text>',
            f'<path d="M{x+474} {y+53} H{x+960}" fill="none" stroke="{color}" stroke-width="4"{dash}/>',
            f'<path d="M{x+948} {y+45} L{x+962} {y+53} L{x+948} {y+61} Z" fill="{color}"/>',
            f'<text x="{x+720}" y="{y+79}" text-anchor="middle" font-size="16" fill="#50647a">{mode.upper()}</text>',
            '</g>'])
        edge_records.append({**e, 'bbox':[x,y,1440,90]})
    parts.extend([
        '<text x="40" y="2245" font-size="22" fill="#50647a">Groups are logical responsibilities, not security trust boundaries. Async relationships may use a shared broker.</text>',
        '<text x="40" y="2285" font-size="22" fill="#50647a">This design is not a complete background-job inventory or a security verdict. Verify implementation and deployment settings in code.</text>',
        '</g></svg>'])
    return '\n'.join(parts)+'\n', {'width':WIDTH,'height':HEIGHT,'nodes':node_records,'edges':edge_records,
        'graphUnchanged':True,'edgeCrossings':0,'layout':'component catalog + isolated directed connection rows',
        'containsSourcePaths':False,'containsEvaluationAnswers':False,
        'visualChanges':['Exact endpoint IDs repeated beside each arrow','One isolated row per directed edge',
                         'Explicit component kind labels from the existing graph','No overlapping edges or edge labels']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render',action='store_true')
    args=parser.parse_args()
    raw=(ROOT/'tests/fixtures/complex_architecture/graph.json').read_bytes()
    svg,meta=render_svg(json.loads(raw))
    PUBLIC.mkdir(parents=True,exist_ok=True)
    path=PUBLIC/'architecture.svg'
    path.write_text(svg)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    meta.update(graphSha256=sha(raw),svgSha256=sha(svg.encode()))
    if args.render:
        png=path.with_suffix('.png')
        js="""const {chromium}=await import(process.argv[1]); const b=await chromium.launch({channel:'chrome',headless:true}); try {const p=await b.newPage({viewport:{width:3000,height:2320},deviceScaleFactor:1}); await p.goto(process.argv[2]); await p.screenshot({path:process.argv[3]});} finally {await b.close();}"""
        subprocess.run(['node','--input-type=module','-e',js,(ROOT/'frontend/node_modules/playwright/index.mjs').as_uri(),path.as_uri(),str(png)],check=True)
        meta.update(pngSha256=sha(png.read_bytes()),pngBytes=png.stat().st_size)
    path.with_suffix('.render.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'path':str(path),'components':len(meta['nodes']),'connections':len(meta['edges'])}))


if __name__=='__main__':
    main()
