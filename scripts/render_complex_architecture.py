#!/usr/bin/env python3
"""Render an explicitly synthetic graph, without source paths or security answers.

The JSON input is a drawing contract: groups[{id,label}],
nodes[{id,label,kind,group,technology}], edges[{from,to,label,mode}].
Only these display fields are read. No source code or evaluation labels are used.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import html
import json
import math
from pathlib import Path
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[1]
WIDTH = 3000
GRID = 20
GROUP_WIDTH = 940
GROUP_HEIGHT = 900
GROUP_GAP_X = 40
GROUP_GAP_Y = 100
NODE_WIDTH = 380
NODE_HEIGHT = 160
COLORS = {"sync": "#32678b", "async": "#8255ae"}


def esc(value):
    return html.escape(str(value), quote=True)


def display_lines(value: str, width: int):
    return textwrap.wrap(value, width, break_long_words=False, break_on_hyphens=False) or [""]


def render_svg(graph: dict, exclude_ids=()):
    """Return SVG and rendering metadata for a graph of at most six nodes/group."""
    excluded = set(exclude_ids)
    groups = graph["groups"]
    if not groups or len({g["id"] for g in groups}) != len(groups):
        raise ValueError("Group IDs must be nonempty and unique")
    group_ids = {g["id"] for g in groups}
    raw_nodes = graph["nodes"]
    if len({n["id"] for n in raw_nodes}) != len(raw_nodes):
        raise ValueError("Node IDs must be unique")
    if not excluded.issubset({n["id"] for n in raw_nodes}):
        raise ValueError("Excluded node ID does not exist")
    if any(n["group"] not in group_ids for n in raw_nodes):
        raise ValueError("Every node must reference a declared group")
    raw_ids = {n["id"] for n in raw_nodes}
    for edge in graph["edges"]:
        if edge["from"] not in raw_ids or edge["to"] not in raw_ids:
            raise ValueError("Edge references an unknown node")
        if edge.get("mode", "sync") not in COLORS:
            raise ValueError("Edge mode must be sync or async")
    nodes = [n for n in raw_nodes if n["id"] not in excluded]
    edges = [e for e in graph["edges"] if e["from"] not in excluded and e["to"] not in excluded]
    group_rows = math.ceil(len(groups) / 3)
    height = 240 + group_rows * GROUP_HEIGHT + (group_rows - 1) * GROUP_GAP_Y + 180
    if height > 8192 or WIDTH * height > 16_000_000:
        raise ValueError("Drawing exceeds the vision worker image-size limit")
    positions = {}
    group_positions = {}
    for index, group in enumerate(groups):
        group_x = 40 + (index % 3) * (GROUP_WIDTH + GROUP_GAP_X)
        group_y = 240 + (index // 3) * (GROUP_HEIGHT + GROUP_GAP_Y)
        group_positions[group["id"]] = (group_x, group_y)
        # Preserve slots in partial-image variants so changing the included nodes
        # does not accidentally redesign all remaining edges and components.
        members = [n for n in raw_nodes if n["group"] == group["id"]]
        if len(members) > 6:
            raise ValueError("This overview supports at most six nodes per group")
        for slot, node in enumerate(members):
            if node["id"] in excluded:
                continue
            x = group_x + 40 + (slot % 2) * 480
            y = group_y + 140 + (slot // 2) * 240
            positions[node["id"]] = (x, y, NODE_WIDTH, NODE_HEIGHT)

    # Orthogonal paths avoid every component rectangle. Reusing a route has a
    # cost, but crossing is allowed when a dense graph cannot avoid it.
    max_x, max_y = WIDTH // GRID - 1, (height - 120) // GRID
    blocked = set()
    header_boxes = [(x + 20, y + 10, GROUP_WIDTH - 40, 90) for x, y in group_positions.values()]
    for x, y, w, h in [*positions.values(), *header_boxes]:
        for gx in range(x // GRID, (x + w) // GRID + 1):
            for gy in range(y // GRID, (y + h) // GRID + 1):
                blocked.add((gx, gy))
    used = {}

    def ports(box):
        x, y, w, h = box
        return [((x // GRID - 1, (y + h // 2) // GRID), (x, y + h // 2)),
                (((x + w) // GRID + 1, (y + h // 2) // GRID), (x + w, y + h // 2)),
                (((x + w // 2) // GRID, y // GRID - 1), (x + (w // 2 // GRID) * GRID, y)),
                (((x + w // 2) // GRID, (y + h) // GRID + 1), (x + (w // 2 // GRID) * GRID, y + h))]

    def route(source, target):
        starts, ends = ports(positions[source]), ports(positions[target])
        targets = {p: actual for p, actual in ends}
        queue, costs, previous = [], {}, {}
        for point, actual in starts:
            state = (*point, -1)
            costs[state] = 0
            previous[state] = (None, actual)
            heuristic = min(abs(point[0] - p[0]) + abs(point[1] - p[1]) for p in targets)
            heapq.heappush(queue, (heuristic, 0, state))
        finish = None
        while queue:
            _, cost, state = heapq.heappop(queue)
            if costs.get(state) != cost:
                continue
            x, y, direction = state
            if (x, y) in targets:
                finish = state
                break
            for turn, (dx, dy) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1))):
                step = x + dx, y + dy
                if not (1 <= step[0] <= max_x and 10 <= step[1] <= max_y) or step in blocked:
                    continue
                turn_cost = 0 if direction in (-1, turn) else 1.8
                next_cost = cost + 1 + turn_cost + min(used.get(step, 0), 4) * 0.7
                following = (*step, turn)
                if next_cost >= costs.get(following, math.inf):
                    continue
                costs[following] = next_cost
                previous[following] = (state, None)
                estimate = min(abs(step[0] - p[0]) + abs(step[1] - p[1]) for p in targets)
                heapq.heappush(queue, (next_cost + estimate, next_cost, following))
        if finish is None:
            raise ValueError(f"Cannot route {source} to {target}")
        coordinates = [targets[finish[:2]]]
        cursor = finish
        while cursor is not None:
            point = cursor[:2]
            used[point] = used.get(point, 0) + 1
            coordinates.append((point[0] * GRID, point[1] * GRID))
            cursor, actual = previous[cursor]
            if actual is not None:
                coordinates.append(actual)
        coordinates.reverse()
        compact = [coordinates[0]]
        for i in range(1, len(coordinates) - 1):
            a, b, c = coordinates[i - 1:i + 2]
            if (a[0] == b[0] == c[0]) or (a[1] == b[1] == c[1]):
                continue
            compact.append(b)
        compact.append(coordinates[-1])
        return compact

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}">',
             '<defs>']
    for mode, color in COLORS.items():
        parts.append(f'<marker id="arrow-{mode}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10" fill="{color}"/></marker>')
    parts.extend(['</defs>', f'<rect width="{WIDTH}" height="{height}" fill="#fbfcff"/>',
                  '<g font-family="Arial, sans-serif" fill="#20354c">',
                  f'<text x="50" y="68" font-size="44" font-weight="700">{esc(graph.get("title", "Synthetic enterprise service architecture"))}</text>',
                  '<text x="50" y="113" font-size="25">Synthetic benchmark system · components and configured routes · no deployment or security guarantees</text>',
                  '<path d="M55,160 L145,160" stroke="#32678b" stroke-width="4" marker-end="url(#arrow-sync)"/>',
                  '<text x="165" y="169" font-size="24">Synchronous call / persistence</text>',
                  '<path d="M650,160 L740,160" stroke="#8255ae" stroke-width="4" stroke-dasharray="12 8" marker-end="url(#arrow-async)"/>',
                  '<text x="760" y="169" font-size="24">Asynchronous event / job</text>',
                  '<text x="1310" y="169" font-size="24">Dashed panel = logical responsibility boundary</text>',
                  f'<text x="2450" y="169" font-size="24">{len(nodes)} components · {len(edges)} routes</text>'])
    for group in groups:
        x, y = group_positions[group["id"]]
        parts.extend([f'<rect x="{x}" y="{y}" width="{GROUP_WIDTH}" height="{GROUP_HEIGHT}" rx="24" fill="#f1f5fa" stroke="#8b9fb4" stroke-width="2" stroke-dasharray="12 8"/>',
                      f'<text x="{x + 28}" y="{y + 47}" font-size="32" font-weight="700">{esc(group["label"])}</text>',
                      f'<text x="{x + 28}" y="{y + 83}" font-size="22" fill="#526b81">{esc(group["id"])} boundary</text>'])

    label_rectangles = []
    edge_labels = []
    routes = []
    label_warnings = []
    for index, edge in enumerate(edges):
        points = route(edge["from"], edge["to"])
        mode = edge.get("mode", "sync")
        path = "M" + " L".join(f"{x},{y}" for x, y in points)
        dashed = ' stroke-dasharray="12 8"' if mode == "async" else ""
        parts.append(f'<path d="{path}" fill="none" stroke="{COLORS[mode]}" stroke-width="3"{dashed} stroke-linejoin="round" marker-end="url(#arrow-{mode})"/>')
        label = edge.get("label", "")
        routes.append({"from": edge["from"], "to": edge["to"], "mode": mode, "label": label})
        if not label:
            continue
        lines = display_lines(label, 26)
        label_w = max(len(line) for line in lines) * 11 + 18
        label_h = len(lines) * 23 + 8
        segments = sorted(zip(points, points[1:]), key=lambda p: abs(p[1][0] - p[0][0]) + abs(p[1][1] - p[0][1]), reverse=True)
        placement = None
        leader = None
        for a, b in segments:
            for fraction in (0.5, 0.3, 0.7):
                cx, cy = a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction
                # Short node-to-node links have too little horizontal room for
                # text. Move their label into the adjacent row gutter and draw
                # a thin leader back to the route instead of hiding text behind
                # either component.
                offsets = [(0, 0), (0, -80), (0, 80), (0, -100), (0, 100),
                           (-80, -80), (80, -80), (-80, 80), (80, 80),
                           (-120, 0), (120, 0), (0, -140), (0, 140)]
                offsets += [(dx, dy) for dx in (-160, 160, -240, 240) for dy in (-80, 80, -100, 100, -160, 160)]
                for dx, dy in offsets:
                    rect = (cx - label_w / 2 + dx, cy - label_h - 5 + dy, label_w, label_h)
                    def intersects(box):
                        return rect[0] < box[0] + box[2] + 4 and rect[0] + rect[2] > box[0] - 4 and rect[1] < box[1] + box[3] + 4 and rect[1] + rect[3] > box[1] - 4
                    if rect[0] < 10 or rect[0] + label_w > WIDTH - 10 or any(intersects(box) for box in list(positions.values()) + header_boxes + label_rectangles):
                        continue
                    placement = rect
                    if dx or dy:
                        leader = (cx, cy, cx + dx, cy - 5 + dy)
                    break
                if placement:
                    break
            if placement:
                break
        if placement is None:
            # Route label remains visible even in a dense graph; metadata records
            # every edge, and omission of a label is never silent.
            a, b = segments[0]
            placement = ((a[0] + b[0] - label_w) / 2, (a[1] + b[1]) / 2 - label_h - 5, label_w, label_h)
            label_warnings.append({"edge": index, "from": edge["from"], "to": edge["to"], "reason": "No collision-free label position found"})
        label_rectangles.append(placement)
        x, y, w, h = placement
        if leader:
            lx, ly, ex, ey = leader
            edge_labels.append(f'<path d="M{lx:.1f},{ly:.1f} L{ex:.1f},{ey:.1f}" fill="none" stroke="{COLORS[mode]}" stroke-width="1.4"/>')
        edge_labels.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="5" fill="white" fill-opacity="0.95"/>')
        for row, line in enumerate(lines):
            edge_labels.append(f'<text x="{x + 9:.1f}" y="{y + 23 + row * 23:.1f}" font-size="21" fill="{COLORS[mode]}">{esc(line)}</text>')

    parts.extend(edge_labels)
    for node in nodes:
        x, y, w, h = positions[node["id"]]
        kind = str(node.get("kind", "service")).lower()
        fill, stroke = ("#e8f5ec", "#3c7b59") if kind in {"database", "db", "store"} else (("#f1eafa", "#8053a4") if kind in {"queue", "broker", "message_queue"} else (("#fff0de", "#a4752b") if kind in {"external", "external_service"} else ("#ffffff", "#417294")))
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="15" fill="{fill}" stroke="{stroke}" stroke-width="3"/>')
        identifier_size = min(27, int(330 / max(len(node["id"]), 1) / 0.55))
        parts.append(f'<text x="{x + 17}" y="{y + 35}" font-size="{identifier_size}" font-weight="700">{esc(node["id"])}</text>')
        label = display_lines(str(node.get("label", "")), 30)
        if len(label) > 2:
            raise ValueError(f"Node role exceeds two display lines: {node['id']}")
        for row, line in enumerate(label):
            parts.append(f'<text x="{x + 17}" y="{y + 68 + 27 * row}" font-size="24">{esc(line)}</text>')
        technology = str(node.get("technology", kind))
        if len(technology) > 34:
            raise ValueError(f"Technology label is too long: {node['id']}")
        parts.append(f'<text x="{x + 17}" y="{y + 139}" font-size="22" fill="#526678">{esc(technology)}</text>')
    parts.extend([f'<text x="50" y="{height - 84}" font-size="24">Component identifiers map to deployment services. This view does not enumerate internal files, functions, or every background task.</text>',
                  f'<text x="50" y="{height - 44}" font-size="24">Arrows describe intended data movement; verify source code and runtime settings before drawing security conclusions.</text>',
                  '</g></svg>'])
    return "\n".join(parts) + "\n", {"width": WIDTH, "height": height, "nodes": len(nodes), "edges": len(edges), "excludedIds": sorted(excluded), "routes": routes, "labelPlacementWarnings": label_warnings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=ROOT / "tests/fixtures/complex_architecture/graph.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/benchmarks/complex-mock/architecture.svg")
    parser.add_argument("--exclude-id", action="append", default=[])
    parser.add_argument("--render", action="store_true", help="Render PNG using the installed Playwright/Chrome")
    args = parser.parse_args()
    raw = args.graph.read_bytes()
    svg, metadata = render_svg(json.loads(raw), args.exclude_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    metadata.update({"graphSha256": hashlib.sha256(raw).hexdigest(), "svgSha256": hashlib.sha256(svg.encode()).hexdigest(),
                     "provenance": "Generated synthetic component graph, not a production architecture.",
                     "containsSourcePaths": False, "containsEvaluationAnswers": False})
    if args.render:
        png = args.output.with_suffix(".png")
        js = '''const {chromium}=await import(process.argv[1]); const browser=await chromium.launch({channel:'chrome',headless:true}); try { const page=await browser.newPage({viewport:{width:Number(process.argv[4]),height:Number(process.argv[5])},deviceScaleFactor:1}); await page.goto(process.argv[2]); await page.screenshot({path:process.argv[3]}); } finally {await browser.close();}'''
        subprocess.run(["node", "--input-type=module", "-e", js, (ROOT / "frontend/node_modules/playwright/index.mjs").as_uri(),
                        args.output.resolve().as_uri(), str(png.resolve()), str(metadata["width"]), str(metadata["height"])], check=True)
        metadata["pngSha256"] = hashlib.sha256(png.read_bytes()).hexdigest()
        metadata["pngBytes"] = png.stat().st_size
    args.output.with_suffix(".render.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in metadata.items() if key != "routes"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
