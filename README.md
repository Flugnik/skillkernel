# SkillKernel v0.1

Modular local platform dispatcher core with pluggable domain skills.

## Architecture

```
IncomingEvent
    │
    ▼
SkillRouter ──── scores all skills ──── DispatchDecision
    │                                        │
    │  matched                               │  unknown / ambiguous
    ▼                                        ▼
BaseSkill.handle()                    return to caller
    │
    ▼
SkillResult (ActionPlan)
    │
    ├── requires_confirmation=True ──► ConfirmManager.store_plan()
    │                                        │
    │                                   user: confirm <plan_id>
    │                                        │
    └── requires_confirmation=False ──► ActionExecutor.execute()
                                             │
                                        ExecutionResult
```

### Key principles

- **No LLM required** — routing is keyword-based; skills are pure Python
- **No Telegram / web / voice** — CLI only at v0.1
- **No business logic in core** — skills are domain plugins
- **No side effects in skills** — skills return `ActionPlan`; executor acts
- **Preview → Confirm → Execute** — mandatory confirmation flow
- **Ambiguous / unknown → no guessing** — dispatcher stops and reports

---

## Project structure

```
skillkernel/
├── main.py                    # Entry point — wires everything, starts CLI
├── pyproject.toml
├── README.md
├── config/
│   └── platform.yaml          # Routing thresholds, TTL, paths
├── core/
│   ├── models.py              # Pydantic models (IncomingEvent, ActionPlan, …)
│   ├── exceptions.py          # Custom exceptions
│   ├── config.py              # Config loader
│   ├── registry.py            # SkillRegistry
│   ├── router.py              # SkillRouter (scoring + decision)
│   ├── dispatcher.py          # Dispatcher (orchestrator)
│   ├── confirm_manager.py     # Pending plan storage
│   ├── executor.py            # ActionExecutor
│   └── event_log.py           # JSONL event logger
├── interfaces/
│   ├── base.py                # BaseAdapter ABC
│   └── cli_adapter.py         # Interactive CLI
├── skills/
│   ├── base.py                # BaseSkill ABC
│   ├── farm_guardian/         # Farm observation skill
│   │   ├── manifest.py
│   │   └── plugin.py
│   └── limiter/               # Feed limit tracking skill
│       ├── manifest.py
│       └── plugin.py
├── executors/
│   ├── registry.py            # ExecutorRegistry
│   └── file_executor.py       # write_markdown + noop
├── memory/
│   ├── runtime/               # pending_plans.json
│   ├── event_log/             # YYYY-MM-DD.jsonl
│   └── domains/               # skill output files
└── tests/
    ├── test_models.py
    ├── test_router.py
    └── test_dispatcher.py
```

---

## Requirements

- Python 3.11+
- `pydantic >= 2.5`
- `pyyaml >= 6.0`

---

## Installation

```bash
# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

# Install dependencies
pip install pydantic pyyaml

# Install dev dependencies (for tests)
pip install pytest
```

---

## Running

```bash
python main.py
```

New runtime entrypoint:

```bash
python -m entrypoints.cli.main
python -m entrypoints.cli.main "привет"
```

The CLI is a thin adapter: it builds `CoreEvent`, calls `runtime.handle()`, and prints the returned `CoreResult`.

Set `SK_DEBUG=1` for verbose debug logging:

```bash
SK_DEBUG=1 python main.py     # Linux / macOS
set SK_DEBUG=1 && python main.py   # Windows cmd
```

---

## CLI usage

```
>> <text>                  Dispatch text as an event
>> confirm <plan_id>       Confirm and execute a pending plan
>> reject  <plan_id>       Reject and discard a pending plan
>> help                    Show command list
>> exit                    Exit
```

### Example session

```
>> Маша сегодня хорошо поела, записать в журнал
────────────────────────────────────────────────────────────
[MATCHED]  skill=farm_guardian

[PREVIEW]
  [FarmGuardian] Запись в журнал:
    Файл: memory/domains/farm_guardian/journal.log
    Текст: Маша сегодня хорошо поела, записать в журнал

  plan_id: 3f2a1b4c-...
  → Preview ready. Confirm with: confirm 3f2a1b4c-...
────────────────────────────────────────────────────────────

>> confirm 3f2a1b4c-...
────────────────────────────────────────────────────────────
[CONFIRMED & EXECUTED]  plan_id=3f2a1b4c-...
  ✓ [0] write_markdown
────────────────────────────────────────────────────────────

>> Списать 5 кг корма
────────────────────────────────────────────────────────────
[MATCHED]  skill=limiter
...

>> Привет, как дела?
────────────────────────────────────────────────────────────
[UNKNOWN]  No skill matched (best score 0.00 < threshold 0.20).
────────────────────────────────────────────────────────────
```

---

## Running tests

```bash
pytest
```

Or with verbose output:

```bash
pytest -v
```

---

## Configuration (`config/platform.yaml`)

| Key | Default | Description |
|-----|---------|-------------|
| `threshold_unknown` | `0.2` | Scores below this → unknown |
| `threshold_ambiguous_gap` | `0.15` | Gap between top-2 scores below this → ambiguous |
| `confirmation_ttl_seconds` | `300` | Pending plan expiry time |
| `log_dir` | `memory/event_log` | Directory for JSONL event logs |
| `pending_store_path` | `memory/runtime/pending_plans.json` | Pending plan storage |

---

## Adding a new skill

1. Create `skills/my_skill/` with `__init__.py`, `manifest.py`, `plugin.py`
2. Implement `class MySkill(BaseSkill)` with `score()` and `handle()`
3. Register in `main.py`:
   ```python
   from skills.my_skill.plugin import MySkill
   skill_registry.register(MySkill())
   ```

No changes to core required.

---

## Adding a new executor

1. Write a function `def execute_my_action(action: Action) -> None`
2. Register in `main.py`:
   ```python
   executor_registry.register("my_action", execute_my_action)
   ```
3. Use `ActionType` enum value `"my_action"` in skill's `ActionPlan`

---

## Event log

All events are logged to `memory/event_log/YYYY-MM-DD.jsonl`.
Each line is a JSON object with a `kind` field:

- `incoming_event`
- `routing_decision`
- `skill_result`
- `execution_result`
- `error`
