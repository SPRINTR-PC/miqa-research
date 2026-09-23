"""The ETL sandbox script contract (#160): the fixed file layout and exit codes shared by every
per-language platform shim. A Python shim implements it here; an eventual R shim (#166) must
match it exactly, since the orchestrator (#162) and sandbox runners (#161/#165) are written
against this contract, not against either language's shim internals.

Layout, all paths relative to the sandbox root:

- `manifest.json` -- run metadata written by the orchestrator before the container starts:
  `{"datatype": "<a name from the ETL Datatype registry, #159>", "config": {<Script config>}}`.
- `input/`  -- read-only staged source files for this Job.
- `script.py` (or the language's own equivalent) -- the pinned Script Version's source, baked
  into the sandbox by the runner.
- `output/result.jsonl` -- written only once the whole script run succeeds: a header line
  `{"datatype": "<name>"}` followed by one JSON row per line, each validated against that
  Datatype's schema (participant-referenced, per #159). Never partially written: on any failure
  no result file exists, so a downstream loader can never consume a partial batch.
- `output/log.txt` -- the script run's captured stdout+stderr, written regardless of outcome.

Exit codes (every non-zero code fails the Job all-or-nothing, matching #159's loader):

- 0 `EXIT_SUCCESS` -- the script ran to completion and every row validated.
- 1 `EXIT_SCRIPT_ERROR` -- the script's own code raised.
- 2 `EXIT_CONTRACT_VIOLATION` -- a bad manifest, a script with no `main`, or a yielded row that
  fails the Datatype's schema.
- 3 `EXIT_TIMEOUT_OR_KILLED` -- the outer `SandboxBackend` (#141/#146) killed the container; a
  shim can never produce this code itself, since a killed process cannot run its own exit path.
"""

MANIFEST_FILENAME = "manifest.json"
INPUT_DIRNAME = "input"
SCRIPT_FILENAME = "script.py"
OUTPUT_DIRNAME = "output"
RESULT_FILENAME = "result.jsonl"
LOG_FILENAME = "log.txt"

EXIT_SUCCESS = 0
EXIT_SCRIPT_ERROR = 1
EXIT_CONTRACT_VIOLATION = 2
EXIT_TIMEOUT_OR_KILLED = 3
