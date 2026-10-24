Privacy MVP paired experiment
Branch: experiment/privacy-mvp-vision
Read protocol.json for frozen inputs, budgets, schedule and the predeclared integration gate.
comparison.csv: per-condition measured times and best verification score.
diagnostics.json: source/test audit, first-plan structural accuracy and matched-success timings.
runs/: original model requests/responses, unchanged candidate sources and WASI verifier logs.
controls/: known-correct and intentionally wrong candidates, not supplied to models.
calibration/: separate direct-coder task; excluded from paired success rates.
Images are authored source-derived component diagrams. Route/trust facts exist in code-only input; scenario titles are image-only context (see diagnostics design limitations).
This measures known-vulnerability remediation, not detection recall or a real production deployment.
A best partial score is diagnostic only and never a publishable patch.
