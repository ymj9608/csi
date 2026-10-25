"""Build source-native architecture diagrams for the synthetic VLM tasks.

This is a new documentation revision, not a replacement for frozen V3 inputs.
Run from CSI: .venv/Scripts/python scripts/build_windows_vlm_architecture.py
"""
import hashlib
import html
import json
import shutil
import subprocess
from pathlib import Path

from vlm_experiment_data import make_case

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/benchmarks/windows-vlm-architecture-v4"
WIDTH, HEIGHT = 1800, 1180


class Diagram:
    def __init__(self, family):
        self.parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">
<defs>
  <marker id="normal" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="#2563eb"/></marker>
  <marker id="failure" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="#b45309"/></marker>
  <marker id="storage" markerWidth="10" markerHeight="10" refX="8" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="#64748b"/></marker>
</defs>
<rect width="1800" height="1180" fill="#f8fafc"/>
<g font-family="Segoe UI, Arial, sans-serif" fill="#0f172a">''']
        self.text(48, 49, "MEMBER EVENT DELIVERY", 15, "#2563eb", 700)
        self.text(48, 96, "Failure recovery architecture" if family == "retry" else "Multi-recipient delivery architecture", 34, weight=700)
        self.text(48, 128, "Component and data-flow view  /  synthetic Python service  /  documentation revision 4", 17, "#64748b")
        self.rect(40, 160, 1260, 820, "#eff6ff", "#bfdbfe", 20)
        self.text(64, 195, "INTERNAL TRUST BOUNDARY", 17, "#1d4ed8", 700)
        self.text(64, 222, "Application modules, internal recipient and in-memory state", 15, "#64748b")
        self.rect(1340, 160, 420, 820, "#fff7ed", "#fed7aa", 20)
        self.text(1364, 195, "EXTERNAL RECIPIENTS", 17, "#9a3412", 700)
        self.text(1364, 222, "Trust classification: deployment.json", 15, "#9a3412")
        self.rect(850, 174, 420, 51, "white", "#cbd5e1", 10)
        self.text(870, 205, "Transport abstraction: broker.py / publish()", 16, "#475569")
        self.text(1320, 1040, "LOGICAL VIEW · NO DEPLOYMENT CLAIM", 14, "#64748b", 600)

    def text(self, x, y, value, size=17, color="#0f172a", weight=400):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}">{html.escape(value)}</text>')

    def rect(self, x, y, w, h, fill, stroke, radius=12):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')

    def node(self, x, y, title, source, detail, width=280, kind="module"):
        palette = {"module": ("#ffffff", "#93c5fd", "#2563eb"),
                   "external": ("#ffffff", "#fdba74", "#c2410c"),
                   "store": ("#f0fdfa", "#5eead4", "#0f766e")}
        fill, stroke, accent = palette[kind]
        self.rect(x, y, width, 120, fill, stroke)
        self.parts.append(f'<rect x="{x+1}" y="{y+16}" width="5" height="88" rx="2" fill="{accent}"/>')
        self.text(x+20, y+32, title, 21, weight=600)
        self.text(x+20, y+61, source, 17, accent, 600)
        self.text(x+20, y+91, detail, 15, "#64748b")

    def edge(self, points, label="", label_at=None, kind="normal"):
        colors = {"normal": "#2563eb", "failure": "#b45309", "storage": "#64748b"}
        dash = ' stroke-dasharray="10 7"' if kind == "failure" else ""
        path = "M" + " L".join(f"{x} {y}" for x, y in points)
        self.parts.append(f'<path d="{path}" fill="none" stroke="{colors[kind]}" stroke-width="2.5"{dash} marker-end="url(#{kind})"/>')
        if label:
            x, y = label_at
            self.text(x, y, label, 15, colors[kind], 600)

    def finish(self):
        self.edge([(55, 1030), (115, 1030)])
        self.text(130, 1036, "Normal / unconditional flow", 16)
        self.edge([(420, 1030), (480, 1030)], kind="failure")
        self.text(495, 1036, "Failure-only flow", 16)
        self.edge([(720, 1030), (780, 1030)], kind="storage")
        self.text(795, 1036, "In-memory state write", 16)
        self.text(48, 1090, "Each delivery route uses broker.publish(); broker.py records messages in state.MESSAGES (no actual network or queue).", 17, "#475569")
        self.text(48, 1120, "Boxes represent code modules or simulated recipients, not independently deployed services. Inspect source for payload handling.", 17, "#475569")
        self.text(48, 1150, "Small and expanded variants share this topology; the 48 unrelated catalog files are omitted. Not used in the completed V3 results.", 17, "#475569")
        return "\n".join(self.parts + ["</g></svg>\n"])


def build(family):
    d = Diagram(family)
    # Routing is drawn explicitly; no vulnerability label or repair is included.
    d.edge([(360, 510), (470, 510)], "event", (385, 494))
    d.edge([(230, 570), (230, 800)], "store", (245, 637), "storage")
    if family == "retry":
        d.edge([(360, 475), (405, 475), (405, 300), (470, 300)], "send", (416, 283))
        d.edge([(750, 300), (950, 300)], "r1 · normal", (790, 282))
        d.edge([(750, 510), (1420, 510)], "r2 · every signup", (1020, 492))
        d.edge([(360, 550), (405, 550), (405, 740), (470, 740)], "on send failure", (414, 648), "failure")
        d.edge([(750, 740), (880, 740)], "forward", (778, 722), "failure")
        d.edge([(1160, 740), (1420, 740)], "r3 · failure", (1220, 722), "failure")
        d.edge([(610, 800), (610, 920), (880, 920)], "retain for replay", (662, 903), "storage")
        d.node(470, 240, "Notification handler", "notification.py", "send(event, fail)")
        d.node(470, 450, "Analytics emitter", "analytics.py", "emit(event)")
        d.node(470, 680, "Recovery handler", "recovery.py", "retain(event)")
        d.node(880, 680, "Support relay", "relay.py", "emit(event)")
        d.node(880, 850, "Replay archive", "state.ARCHIVE", "In-memory event copies", kind="store")
    else:
        d.edge([(750, 475), (830, 475), (830, 300), (950, 300)], "r1 · normal only", (790, 282))
        d.edge([(750, 510), (1420, 510)], "r2 · normal + failure", (1020, 492))
        d.edge([(750, 550), (830, 550), (830, 740), (1420, 740)], "r3 · failure only", (1030, 722), "failure")
        d.edge([(360, 550), (405, 550), (405, 860), (480, 860)], "archive on failure", (430, 778), "storage")
        d.node(470, 450, "Event dispatcher", "dispatcher.py", "publish_event(event, fail)")
        d.node(480, 800, "Replay archive", "state.ARCHIVE", "In-memory event copies", kind="store")
        d.rect(880, 800, 350, 145, "white", "#bfdbfe")
        d.text(900, 834, "Route selection", 19, weight=600)
        d.text(900, 868, "Normal: r1 + r2", 18, "#2563eb")
        d.text(900, 902, "Failure: r2 + r3", 18, "#b45309")
        d.text(900, 929, "Same event enters the dispatcher", 15, "#64748b")
    d.node(100, 450, "Signup application", "app.py", "signup(phone, fail)", width=260)
    d.node(100, 800, "Member records", "state.MEMBERS", "In-memory event copies", width=260, kind="store")
    d.node(950, 240, "SMS recipient", "r1 / INTERNAL", "Simulated internal delivery")
    d.node(1420, 450, "Metrics recipient", "r2 / EXTERNAL", "Simulated analytics destination", kind="external")
    d.node(1420, 680, "Support recipient", "r3 / EXTERNAL", "Simulated failure destination", kind="external")
    return d.finish()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {"revision": 4, "used_in_v3_experiment": False,
                "scope": "Synthetic source-derived component diagrams; not production infrastructure.",
                "generator": "scripts/build_windows_vlm_architecture.py", "diagrams": {}}
    for family in ("retry", "fanout"):
        folder = OUTPUT / family
        folder.mkdir(exist_ok=True)
        svg = folder / "architecture.svg"
        svg.write_text(build(family), encoding="utf-8")
        case = make_case(family)
        manifest["diagrams"][family] = {
            "source_sha256": {p: hashlib.sha256(v.encode()).hexdigest() for p, v in case["sources"].items()},
            "svg_sha256": hashlib.sha256(svg.read_bytes()).hexdigest(),
            "expanded_variant": "Same topology; 48 isolated catalog files omitted."}
    js = '''
        const {chromium} = await import(process.argv[1]);
        const browser = await chromium.launch({channel: 'chrome', headless: true});
        try {
            const page = await browser.newPage({viewport: {width: 1800, height: 1180}, deviceScaleFactor: 1});
            for (const target of JSON.parse(process.argv[2])) {
                await page.goto(target.url);
                await page.evaluate(() => document.fonts.ready);
                const overflow = await page.locator('text').evaluateAll(nodes => nodes.filter(n => {
                    const b = n.getBBox(); return b.x < 0 || b.y < 0 || b.x+b.width > 1800 || b.y+b.height > 1180;
                }).map(n => n.textContent));
                if (overflow.length) throw new Error(JSON.stringify(overflow));
                await page.screenshot({path: target.png});
            }
        } finally { await browser.close(); }
    '''
    targets = [{"url": (OUTPUT / family / "architecture.svg").as_uri(),
                "png": str(OUTPUT / family / "architecture.png")} for family in ("retry", "fanout")]
    node = shutil.which("node") or str(ROOT / ".runtime/tools/node-v22.15.0-win-x64/node.exe")
    subprocess.run([node, "--input-type=module", "-e", js,
                    (ROOT / "frontend/node_modules/playwright/index.mjs").as_uri(),
                    json.dumps(targets)], check=True)
    for family in ("retry", "fanout"):
        manifest["diagrams"][family]["png_sha256"] = hashlib.sha256((OUTPUT / family / "architecture.png").read_bytes()).hexdigest()
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "diagrams": 2, "size": [WIDTH, HEIGHT]}))


if __name__ == "__main__":
    main()
