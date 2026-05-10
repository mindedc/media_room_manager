# CLAUDE.md

This file is loaded at the start of every Claude Code session in this repository. Read it before doing anything else.

## What this project is

Media Room Manager is a Home Assistant custom integration that adds AV signal-routing and orchestration on top of existing HA integrations. The full design is in `README.md`. Read it before any non-trivial change.

The everyday user does not write code, automations, or YAML to operate the integration. Profile authors write YAML for the community library, but only declaratively — there is no Python escape hatch and no embedded templating. If you find yourself reaching for either, stop and reconsider.

## Required reading at session start

In order, every session:

1. `README.md` — full design.
2. `CLAUDE.md` — this file.
3. `PLAN.md` — phase plan.
4. `TASKS.md` — current task tracker. Find the first unchecked task in the active phase. If a task is mid-progress (partial commits exist), continue it. Do not start a new task while another is mid-flight.

If your assigned task isn't clearly defined in TASKS.md, stop and ask before guessing.

## Project structure

```
custom_components/media_room_manager/      # Backend Python package
├── __init__.py                            # Integration setup/teardown
├── manifest.json                          # HA integration manifest
├── const.py                               # Domain constants, defaults
├── config_flow.py                         # Minimal config flow (install only)
├── store.py                               # Store-backed persistence
├── graph/                                 # Graph model (Layer 1)
├── profiles/                              # Profile registry (Layer 2)
│   ├── registry.py
│   ├── schema.py                          # voluptuous schema for profiles
│   └── bundled/                           # Bundled YAML profiles
├── adapters/                              # Adapter registry (Layer 3)
├── resolver/                              # Path + role resolvers (Layers 4-5)
├── orchestrator/                          # Orchestrator (Layer 6)
├── services/                              # State tracker, discovery, repair
├── entities/                              # MediaPlayer, BinarySensor, Select, Switch
├── websocket/                             # WebSocket command surface
└── panel/                                 # Bundled panel JS (built artifact)

frontend/                                  # Panel source (TypeScript + Lit)
├── src/
├── package.json
└── vite.config.ts

tests/                                     # pytest test suite
├── unit/
├── integration/
└── fixtures/

scripts/                                   # Dev tooling
docs/                                      # Additional reference docs (profile schema, etc.)
```

When the structure doesn't yet exist for a layer you're building, create it as outlined above. Don't reorganize without explicit approval.

## Coding standards

**Python:**

- Python 3.12+. Type hints on every function signature, including return types.
- `from __future__ import annotations` at top of every module.
- Use `voluptuous` for all schema validation (HA's standard).
- Async everywhere HA expects it (entity callbacks, service handlers, store operations).
- Use `homeassistant.helpers.storage.Store` for persistence — never `open()` files in the config dir directly.
- Bind to entities via `entity_registry` IDs (UUIDs), never via `entity_id` strings.
- Logging via `_LOGGER = logging.getLogger(__name__)` per module. No `print()`.
- Docstrings on every public class and function. Triple-quoted, summary line, blank line, details if needed.
- Dataclasses (`@dataclass(frozen=True)` where appropriate) for graph model objects.

**TypeScript (panel):**

- TypeScript strict mode. No `any` without an explanatory comment.
- Lit components. No React.
- Communicate with backend via Home Assistant's WebSocket API only.
- Never use `localStorage`, `sessionStorage`, or any browser storage from within the panel — panel state is either in HA storage (via WebSocket) or in component state.

## Boundaries — do not cross without explicit approval

- **No new Python adapter mechanisms** beyond the documented five (`media_player_source`, `select_entity`, `switch_combo`, `remote_command`, `service_call`). If a device needs something different, raise it; don't invent.
- **No templating in profile YAML.** No Jinja2, no `{name}` substitution. The only runtime substitution sentinel is `$value`. If you find yourself wanting more, stop.
- **No custom HA events for automation triggers.** All automation surfaces are entity state changes. If the data model doesn't expose what's needed, expose it as an entity attribute, not as an event.
- **No changes to the WebSocket command schema** without updating its documentation in the same commit. The API is a stable contract.
- **No changes to the profile schema** without updating `docs/profile-schema.md` and the example profiles in the same commit.
- **No `# type: ignore` or `# noqa`** without an explanatory comment on the same line.

## Testing expectations

- `pytest` is the test runner. Tests live in `tests/`.
- Every public function in `graph/`, `profiles/`, `resolver/`, `adapters/`, `orchestrator/` has unit tests covering the happy path and at least the obvious failure modes.
- Integration tests for end-to-end flows: profile loaded → graph built → path resolved → commands generated.
- Use HA's `pytest-homeassistant-custom-component` for tests that need a HA test harness.
- Run tests before declaring a task complete. If they fail, fix or revert.
- Do not commit code that fails its own tests.

## Required commands (run yourself; don't hand broken work to the user)

After any code change, before declaring done:

```
pytest                              # all tests pass
ruff check custom_components tests  # lint clean
ruff format --check custom_components tests  # formatted
mypy custom_components              # type-check clean
```

If any of these fail, fix or roll back before ending the session.

For the panel:

```
cd frontend && npm run build        # builds clean
cd frontend && npm run typecheck    # type-checks clean
cd frontend && npm run lint         # lint clean
```

## Commit discipline

- Commit after each completed task in TASKS.md. One task = one commit (unless the task explicitly calls for multiple).
- Commit messages: `<phase>: <task summary>`. E.g., `phase-2: implement profile loader for bundled profiles`.
- Mark the task as complete in TASKS.md *in the same commit* as the work.
- Never leave the working tree in a half-finished state across sessions. If a task can't be completed in one session, leave a `WIP:` commit with notes about where to resume — but prefer breaking the task down further in TASKS.md instead.

## When to stop and ask

Stop and ask the user (do not guess) when:

- The README and CLAUDE.md don't cover the case you're hitting.
- A task description is ambiguous or seems to contradict the README.
- You've made multiple attempts at the same problem and tests still fail.
- A change you're about to make would alter a documented schema (WebSocket commands, profile YAML, storage layout).
- You believe the design is wrong for the case at hand. Surface it; don't quietly work around.

Better to spend a turn confirming than to commit a confidently-wrong implementation.

## Drift prevention

Before ending each session:

1. Run all the required commands above.
2. Re-read the README section relevant to the work just done.
3. Compare your implementation to the README's description. If they diverge, either fix the implementation or — if the implementation revealed something the README got wrong — flag it explicitly in your end-of-session summary so the user can decide.
4. Never quietly "fix the README" to match wrong code.

## Session output format

End each session with a brief summary:

```
## Session summary

Task: <task ID from TASKS.md>
Status: complete | in-progress | blocked

Changes:
- file: short description
- file: short description

Tests: <pass/fail counts>

Notes: <anything the next session should know — drift, surprises, decisions made under ambiguity>
```

Keep it terse. The next session will read the commits and TASKS.md; the summary is for the user.
