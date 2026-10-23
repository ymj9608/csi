#!/usr/bin/env python3
"""Render a manually designed, source-derived Lichu snapshot diagram (not an original design document)."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/benchmarks"
EXPECTED_COMMIT = "95345dbd8ba45fe77ea8cd926c84e40e4d16f83a"

COMPONENTS = [
    {"id": "browser", "title": "Vue browser application", "position": (380, 120, 640, 135),
     "paths": ["frontend/src/api/client.ts", "frontend/src/stores/auth.ts", "frontend/src/views/AuthView.vue"],
     "role": "Employee signup / login / license requests"},
    {"id": "api", "title": "FastAPI entry / validation", "position": (45, 350, 415, 150),
     "paths": ["backend/app/main.py", "backend/app/api/routes.py", "backend/app/schemas/dto.py"],
     "role": "JSON requests and responses"},
    {"id": "auth", "title": "Identity / role boundary", "position": (495, 350, 415, 150),
     "paths": ["backend/app/api/deps.py", "backend/app/core/security.py", "backend/app/core/config.py"],
     "role": "Bearer identity + employee / master role"},
    {"id": "lab", "title": "Conditional signup lab module", "position": (945, 350, 410, 150),
     "paths": ["backend/app/core/csi_signup.py"],
     "role": "Called when CSI_LAB_MODE is enabled"},
    {"id": "service", "title": "Application services", "position": (285, 595, 830, 115),
     "paths": ["backend/app/services/hub.py"],
     "role": "Signup, login, profile, request decision, assignment, dashboard"},
    {"id": "repo", "title": "SQLAlchemy repositories", "position": (45, 790, 600, 115),
     "paths": ["backend/app/repositories/hub.py"],
     "role": "Queries / counts / row locks"},
    {"id": "db", "title": "Models / DB session", "position": (695, 790, 660, 115),
     "paths": ["backend/app/models/entities.py", "backend/app/db/session.py"],
     "role": "Users, contact, license, request, assignment, lab profile"},
]


def render_svg(commit):
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1060" viewBox="0 0 1400 1060">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10" fill="#476988"/></marker></defs>',
        '<rect width="1400" height="1060" fill="white"/><g font-family="Arial,sans-serif" fill="#21364b">',
        '<text x="35" y="40" font-size="27" font-weight="700">Lichu web application: manually summarized source snapshot</text>',
        f'<text x="35" y="73" font-size="17">Commit {html.escape(commit)}. Not an original architecture document.</text>',
        '<rect x="25" y="305" width="1350" height="625" rx="14" fill="#fafcff" stroke="#94a7ba" stroke-dasharray="8 6"/>',
        '<text x="43" y="333" font-size="16">Backend application boundary (runtime infrastructure / trust configuration is not shown)</text>',
    ]
    for component in COMPONENTS:
        x, y, width, height = component["position"]
        parts += [f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="#f1f6ff" stroke="#57799a" stroke-width="2"/>',
                  f'<text x="{x+16}" y="{y+28}" font-size="21" font-weight="700">{html.escape(component["title"])}</text>']
        for index, line in enumerate(component["paths"] + [component["role"]]):
            parts.append(f'<text x="{x+16}" y="{y+53+index*22}" font-size="15">{html.escape(line)}</text>')
    for points in [(580, 255, 250, 350), (700,255,700,350), (250,500,500,595), (700,500,700,595),
                   (1115,650,1150,500), (520,710,350,790), (880,710,1010,790), (645,845,695,845)]:
        x1, y1, x2, y2 = points
        parts.append(f'<path d="M{x1},{y1} L{x2},{y2}" stroke="#476988" stroke-width="2" marker-end="url(#arrow)"/>')
    parts += ['<text x="1030" y="560" font-size="15">conditional call</text>',
              '<text x="35" y="970" font-size="18">Scope: source-level web paths only. Tests, migrations, deployment and external services are omitted.</text>',
              '<text x="35" y="1000" font-size="18">No statement about security controls is implied. Inspect selected source and verify missing components.</text>',
              '<text x="35" y="1030" font-size="17">Manually curated path labels assist retrieval; this is not a blind test of an unlabeled production diagram.</text>',
              '</g></svg>']
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT.parent / "Lichu")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()
    commit = subprocess.check_output(["git", "-C", str(args.repository), "rev-parse", "HEAD"], text=True).strip()
    if commit != EXPECTED_COMMIT:
        raise SystemExit("Source snapshot changed; review component mapping before updating EXPECTED_COMMIT.")
    source_hashes = []
    for path in sorted({path for component in COMPONENTS for path in component["paths"]}):
        raw = subprocess.check_output(["git", "-C", str(args.repository), "show", f"{commit}:{path}"])
        source_hashes.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    svg = OUTPUT / "lichu-architecture.svg"
    svg.write_text(render_svg(commit))
    manifest = {
        "schema_version": 1, "kind": "manually_source_derived_diagram", "repository_name": "Lichu", "commit": commit,
        "diagram": "lichu-architecture.png", "diagram_source": "lichu-architecture.svg",
        "svg_sha256": hashlib.sha256(svg.read_bytes()).hexdigest(),
        "components": [{key: value for key, value in component.items() if key != "position"} for component in COMPONENTS],
        "reviewed_source_files": source_hashes,
        "limitations": ["Source-derived path labels favor retrieval compared with unlabeled diagrams.",
                        "Manually summarized source; not the user-attached workflow image and not an original architecture document.",
                        "Omitted migrations, tests, deployment details and external-service configuration.",
                        "Does not encode or establish security findings; analyze actual source to validate."],
    }
    (OUTPUT / "lichu-architecture-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if args.render:
        js = '''
            const {chromium} = await import(process.argv[1]);
            const browser = await chromium.launch({channel: 'chrome', headless: true});
            try {
                const page = await browser.newPage({viewport: {width: 1400, height: 1060}, deviceScaleFactor: 1});
                await page.goto(process.argv[2]);
                await page.screenshot({path: process.argv[3]});
            } finally { await browser.close(); }
        '''
        subprocess.run(["node", "--input-type=module", "-e", js,
                        (ROOT / "frontend/node_modules/playwright/index.mjs").as_uri(),
                        svg.as_uri(), str(OUTPUT / "lichu-architecture.png")], check=True)
    print(json.dumps({"commit": commit, "reviewed_source_files": len(source_hashes), "output": str(OUTPUT)}))


if __name__ == "__main__":
    main()
