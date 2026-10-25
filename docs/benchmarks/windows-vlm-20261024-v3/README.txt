Windows local VLM comparison -- version 3

execution.json is the live progress record. summary.json and comparison.csv
are derived from actual completed trials, retaining failed/interrupted/unrun
conditions. Do not interpret controls/ as model-generated repairs.

This is an exploratory calibration, NOT a confirmatory study or an enterprise
benchmark. There are two authored task families: event fanout and failure-path
relay. Each has a small version and a paired version with 48 unrelated catalog
files added. The paired size variants are NOT independent tasks. There is one
trial per arm/case. No statistical noninferiority or general model ranking is
claimed. Generated patches are tested on eight fixed functional/security
contracts, including direct calls to delivery functions.

Four arms share the same orchestrator, coder, tools, budgets and tests:
  full_code: all fixture code/configuration is supplied initially.
  code_search: entry point, one-hop imports, deployment config, shared import
               and function index; additional source via read/search actions.
  image_search: code_search plus the architecture image.
  text_search: code_search plus exactly the image's facts in structured text.
All arms may read the same deployment facts. Diagrams include explicit code
names and are complete synthetic diagrams; they are easier to map than real
diagrams without implementation names. Omitted/stale diagrams and real large
repositories are NOT evaluated by this pilot.
Every arm also receives the same editable-file allowlist. Catalog distractors
are outside that allowlist and the literal import graph exposes their isolation.
The expanded cases therefore measure added input/index clutter, not discovery
of unknown vulnerable modules across a real enterprise repository.

The same Qwen3-VL 8B Instruct orchestrates all four arms. Ministral 3 8B Instruct
generates patches. The orchestrator chooses read/search/delegate/verify/finish.
The host enforces read-before-write scope, existing function signatures, two
coding attempts, current-candidate verification and the fixed test suite.
The 1,200-second loop budget is checked between turns; it is not a hard
process deadline. Individual model requests have a 300-second timeout.
Each request also has a 20,000-byte text-content guard; image data is excluded
from that byte check. Output budgets are 700 tokens for orchestration and
1,000 for coding. These are harness limits, not the models' native maxima.
New helper functions are permitted. On retry the coder receives its previous
proposal and actual validation/test diagnostics, as in the production executor.
Every proposal is materialized from the same original sources. Test sources
and correct-control patches are not included in initial prompts. Failure
tracebacks may reach the models through the shared verifier tool.

This is a standalone experimental harness, not a production CSI/Lichu backend
end-to-end test. It removes the production engine's image/no-image flow
confound, but does not generalize its fixed Lichu profile to enterprise repair.

On this 16GB Windows machine, only one model may be loaded at a time. It is
retained for up to two minutes inside a trial and explicitly unloaded between
trials. Initial loading, generation, switching, verification and retries are
included in trial wall time. Model downloads/setup and diagram/fixture authoring
are excluded; these inputs are prepared before measurement. This does not
measure the cost of creating real project diagrams. Within-trial prefix reuse
is allowed equally in all arms; OS disk cache is not forcibly
cleared. This remains a developer desktop rather than a dedicated benchmark
machine. Do not treat provider token counts as an accuracy metric or assume
they expose image-only or cached token counts.

Generated Python executes in read-only/no-network WASI Python 3.12.0 under
Wasmtime 50.0.1 with memory, fuel and wall-time bounds. Only fixture and stdlib
directories are mounted; host environment is not inherited. This does not
validate production Docker, native extensions, Java, HTTP or deployment.

Version history is preserved:
  ../windows-vlm-20261024: model installation/compatibility and v1 calibration.
  ../archive/windows-vlm-20261024-v2.zip: shared code index, scope and retention correction.
  This directory: v3 adds production-equivalent coder retry context.
V1/V2 comparisons were stopped after runner-contract issues were identified.
Their incomplete/failed trials are NOT combined with v3 as model evidence.
Snapshots preserve the exact older runner sources. Calibration metadata in
this directory is explicitly reused, with origin paths/hashes in protocol.json;
it is not a second measurement. runner-validation.json records the v3 checks,
all completed before comparison inference started.

Original compatibility.json uses strict ID matching. The separately labeled
POST_HOC perception-label-diagnostic.json accepts only exact full box labels
printed in the image as aliases for IDs. It does not repair response contents,
invent relations or replace original scores. The rule was added after Qwen
Instruct used full labels, while its directed/styled edges were correct.

Reproduction from csi root, using a NEW output directory:
  .venv\Scripts\python.exe -X utf8 scripts/benchmark_windows_vlm.py prepare --out docs/benchmarks/NEW-RUN
  .venv\Scripts\python.exe -X utf8 scripts/benchmark_windows_vlm.py controls --out docs/benchmarks/NEW-RUN
  .venv\Scripts\python.exe -X utf8 scripts/benchmark_windows_vlm.py compatibility --out docs/benchmarks/NEW-RUN
  .venv\Scripts\python.exe -X utf8 scripts/benchmark_windows_vlm.py pilot --out docs/benchmarks/NEW-RUN --case retry-small
  Repeat pilot with fanout-small, retry-expanded, fanout-expanded.
  .venv\Scripts\python.exe -X utf8 scripts/summarize_windows_vlm.py docs/benchmarks/NEW-RUN

Use scripts/requirements-vlm-experiment.txt for optional Python dependencies.
Ollama: .runtime/tools/ollama-v0.40.10/ollama.exe; models: .runtime/ollama-models.
Bind 127.0.0.1:11434 with OLLAMA_MAX_LOADED_MODELS=1, OLLAMA_NUM_PARALLEL=1,
OLLAMA_NO_CLOUD=1. Install hashes, actual model digests and hardware are stored
in setup.json, environment.json and hardware.json. Python WASI goes under
.runtime/tools/python-wasi with its bin/ and usr/ directories preserved.
No .env edits, global PATH changes, cloud inference, or application deployment.
