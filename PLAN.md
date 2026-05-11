# PLAN.md

Strategic phase plan for building Media Room Manager. Each phase has a definable end state. Phases are roughly sequential but small overlap is fine when one phase's output is needed to test another. The granular work is in `TASKS.md`.

The full design is in `README.md`. Read it before starting any phase.

---

## Phase 0 — Repository scaffold

**Goal.** A loadable HA custom integration that does nothing yet, but is structurally correct and passes its own tooling.

**End state:**

- Repo structure matches the layout in `CLAUDE.md`.
- `manifest.json` is valid; HA recognizes the integration.
- A trivial config flow installs the integration with no actual configuration.
- `pytest`, `ruff`, `mypy` all pass on an essentially empty codebase.
- HACS-installable (validate via HACS schema requirements).
- Frontend dev tooling stub exists but produces no panel yet.

**Success criterion:** install in a dev HA instance, see "Media Room Manager" in the integrations list, install it, see it appear in installed integrations with no errors. No panel yet.

---

## Phase 1 — Graph model and persistence

**Goal.** The data model exists, can be persisted, and can be inspected.

**End state:**

- Dataclasses (or equivalent) for: `Device`, `Interface`, `OutputGroup`, `Connection`, `Zone`, `VirtualSource`, `SourceVisibilitySelection`, instance bindings (entity registry IDs and per-instance remaps).
- `voluptuous` validators for each.
- `Store`-backed persistence at `<config>/.storage/media_room_manager.system` with `version=1` and migration scaffolding.
- A small set of WebSocket commands for read-only inspection: `list_devices`, `list_zones`, `list_connections`. (Mutations come later.)
- Unit tests for: dataclass construction, schema validation (positive and negative cases), Store round-trip.

**Success criterion:** can write a test that constructs an in-memory graph, persists it, reloads it, and gets equivalent objects back.

---

## Phase 2 — Profile registry and bundled profiles

**Goal.** Profiles can be loaded, validated, and queried. A small starter library exists.

**End state:**

- Profile YAML schema (`voluptuous`) covering everything in the README's profile examples:
  - Top-level: `profile_id`, `schema_version`, `manufacturer`, `model`, `category`, `power_handling`, `power_on_delay`, `exclusive_outputs`.
  - `output_groups` list: `id`, `selection_mechanism` (with `kind`, `expected_domain`, `expected_features`, `expected_options`, `expected_commands` as applicable), `provides_roles`, optional `role_operations` for non-`media_player`-bound groups.
  - `inputs_are_exclusive_per_output_group` list.
  - `aux_entities` list: `id`, `expected_domain`, `expected_features`, `expected_commands`, `expected_options` as applicable.
  - `interfaces` list: `id`, `direction`, `type`, `label`, `output_group` (for outputs) or `routable_to_output_group` (for inputs).
  - `virtual_sources` list: `id`, `label`, `routable_to_output_group`.
  - `dynamic_virtual_sources` block: `source`, `output_group`, optional `exclude`.
  - `discovery` block (optional): `output_groups` list, each with `output_group`, optional `is_discovery_anchor`, `match_threshold`, optional `optional`, `signals` list.
- Profile loader that reads bundled profiles from the package's `profiles/bundled/` directory.
- Profile registry that resolves profile-by-id lookups. Layered loading order: local > community-fetched > bundled (only bundled implemented in this phase).
- Ten hand-written starter profiles seeding the library:
  - Apple TV 4K (simple source, dynamic virtual sources).
  - A generic IR-controlled Blu-ray (e.g., Sony DVP-NS500V — `remote_command` mechanism, `power_handling: toggle`).
  - A single-zone AVR (e.g., Denon AVR-X1700H — `media_player_source` mechanism, one output group).
  - Marantz SR8015 (multi-zone AVR, two output groups, static and dynamic virtual sources, full discovery block).
  - Anthem MRX 740 (multi-zone AVR with parallel HDMI outputs in the same output group).
  - Monoprice Blackbird 8x8 matrix (true matrix, one output group per output, `select_entity` mechanism, `switch` aux entity).
  - HDFury Diva (two output groups with audio extraction outputs grouped).
  - Lumagen Radiance Pro (single output group, `exclusive_outputs: true`).
  - Generic HDMI 1×4 splitter / distribution amp (one output group, no selection_mechanism).
  - Generic HDMI audio extractor (passive converter, one output group, no selection_mechanism, `power_handling: disabled`).
- Schema migration scaffolding for profile schema versions.
- WebSocket commands: `list_profiles`, `get_profile`.
- Unit tests for: schema validation against each example, profile-id resolution, malformed profile rejection.

**Success criterion:** all 10 starter profiles load without warnings; the WebSocket commands return them; a test exists for each profile that asserts its structural correctness.

---

## Phase 3 — Adapter registry

**Goal.** All five v1 mechanisms have working adapter implementations.

**End state:**

- A common adapter interface (abstract base class or protocol) defining methods like `async_select_input`, `async_set_volume`, `async_power_on`, etc.
- Implementations for: `media_player_source`, `select_entity`, `switch_combo`, `remote_command`, `service_call`.
- The `$value` sentinel substitution mechanism in `service_call` parameter data. Only the literal string `"$value"` is substituted; no other templating.
- Unit tests for each adapter using HA's mock service registry — verify the right service call is emitted with the right parameters for each operation.

**Success criterion:** a test for each adapter constructs a profile snippet using that mechanism, runs the adapter through each operation it supports, and asserts the expected `hass.services.async_call` invocations.

---

## Phase 4 — Path resolver

**Goal.** Given a graph and a (source, zone) pair, the resolver returns a structured path or a clear failure.

**End state:**

- BFS-based path finding through the connection graph for video and audio independently.
- Handles transit devices (any input on a transit device can reach any output of compatible carrier within the same output group).
- Respects `routable_to_output_group` constraints — inputs only feed listed output groups.
- Handles `hdmi_audio_return` interfaces' implicit reverse-direction audio.
- Handles virtual sources (the "path" is just the device + virtual source selection).
- Handles `simultaneous` and `selectable_exclusive` zones (multiple sinks).
- Tracks `exclusive_outputs: true` devices for contention purposes (the resolver records which output of these devices is being used, even though the orchestrator doesn't command output switching).
- Returns structured output: ordered (device, output_group, input_interface, output_interface) tuples, or a structured failure with reason.
- A `resolve_path(zone_id, source_id, sink_id=None)` WebSocket command that runs the resolver and returns its output. This is the data backing the Looking Glass.
- Extensive unit tests covering: simple linear paths, multi-hop paths through matrices and AVRs, audio paths diverging from video paths, no-path failures, type-incompatible paths, virtual source activation.

**Success criterion:** for each starter profile combination, a test fixture defines a small example system (a few devices, connections, and zones) and asserts the resolver produces correct paths.

---

## Phase 5 — Role resolver and orchestrator

**Goal.** Resolved paths can be turned into actual command sequences against HA, and zone activation works end-to-end.

**End state:**

- Role resolver: given an active path, identifies which device holds each control role. Volume is pinned (lookup); transport and metadata_source are dynamic.
- Orchestrator: takes resolved paths, executes power-on in dependency order with delays based on `power_handling` and `power_on_delay`, executes input selections from sink toward source, activates virtual sources, signals transport at the source.
- Per-step retries with configurable counts.
- Failure surfaces on the zone media_player as `state: unavailable` with `error_detail` attribute.
- Contention detection covering input-side (from `inputs_are_exclusive_per_output_group`), output-side (from per-output `output_selection`), and `exclusive_outputs` devices. Zone-level contention policy: v1 implements `deny` (default) and `preempt` only. The `share` policy is v1.x and is **not** implemented in this phase.
- For `exclusive_outputs` devices, the orchestrator does not issue output-switching commands — the device's active output is externally managed by the user. The orchestrator tracks the resolved output for contention purposes only.
- For `power_handling: toggle` devices, the orchestrator uses observed state (or commanded-state fallback) to decide whether to issue the toggle command for a power-on or power-off request.
- For `power_handling: always_on` and `power_handling: disabled` devices, no power commands are issued.
- Unit and integration tests using HA's mock environment.

**Success criterion:** an end-to-end test loads a profile, builds a graph, picks a zone and source, runs orchestration, and asserts the expected service calls were made on the underlying mock entities.

---

## Phase 6 — Entities and devices

**Goal.** The integration registers HA Devices and entities. A user installing the integration and configuring a graph (via WebSocket commands in tests) sees `media_player`, `binary_sensor`, `select`, and `switch` entities appear.

**End state:**

- Per-zone `media_player` entity with: source list from visibility config, transport pass-through to active source's role-holder, volume control routed to volume authority, metadata pass-through from `metadata_source` role-holder.
- Static `supported_features` computation at zone configuration time (union of features across all reachable role-holders).
- Per-zone `select` and per-sink `switch` entities for `selectable_exclusive` zones, kept in sync.
- Per-physical-device `binary_sensor.<device>_in_use`, only created for devices reachable from more than one zone.
- HA Device Registry entries for each MRM zone and each orchestrated physical device, with appropriate entities under each.
- Reactive entity state updates as orchestrator state changes.
- Unit and integration tests for entity behavior.

**Success criterion:** an integration test loads a config, confirms entities are registered, simulates state changes, and asserts entities reflect them correctly.

---

## Phase 7 — Services (state tracker, discovery, repair)

**Goal.** The supporting services run alongside the core pipeline and add discovery, repair, and external-state-change tracking.

**End state:**

- **State tracker** subscribes to all underlying entities referenced by the active graph. Tracks observed/commanded/unknown per interface. Re-evaluates zone state on external changes (someone hits the AVR remote).
- **Discovery service** implements the two-stage discovery model:
  - **Stage 1 (anchor matching):** iterate `ent_reg.entities.values()` for enabled entities, score each against each profile's anchor output group signals (the output group flagged `is_discovery_anchor: true`), apply that output group's `match_threshold`, surface entities scoring above as anchor candidates.
  - **Stage 2 (sibling matching):** for each anchor candidate, look up its `device_id`, retrieve sibling entities via `async_entries_for_device(ent_reg, device_id, include_disabled_entities=True)`. For each non-anchor output group in the profile's discovery block, score the sibling entities against that output group's signals and apply that group's `match_threshold`. Bind the best match. If no sibling meets the threshold and the entry is marked `optional`, leave the output group unbound.
  - Implements all eight signal kinds: `device_registry`, `platform`, `supported_features`, `source_list_signature`, `sound_mode_list_signature`, `device_class`, `friendly_name`, `attribute_constellation`. The `source_list_signature`, `sound_mode_list_signature`, and `attribute_constellation` kinds support `includes_any`, `includes` (all), and `matches` (exact) operators where appropriate.
  - Discovery reads from HA's entity registry (`platform`, `device_id`, registered `capabilities`) and device registry (`manufacturer`, `model`) where available, falling back to entity state attributes (`source_list`, `sound_mode_list`, `device_class`, `friendly_name`) for fields not in the registry.
  - Disabled entities surfaced in sibling matching: when a disabled entity is bound to an output group, the suggestion notes the disabled state.
- A `discover_profiles_for_entity` WebSocket command (kept for backward compatibility / per-entity inspection) and a `discover_profiles` command that runs the full two-stage discovery and returns ranked multi-binding suggestions.
- An "Add Device" WebSocket command flow that surfaces auto-discovery suggestions. Suggestions are ranked by score; the user always confirms. User assignment is the always-available fallback when a sibling can't be confidently matched.
- Discovery service also re-evaluates dynamic virtual sources for already-bound entities when their `source_list` changes.
- **Repair service** observes events and emits HA repairs for: disappeared dynamic source that was enabled, source-list expectations broken, path no longer resolves, bound entity removed.
- Tests for each service. Discovery tests include: multi-binding suggestions with all output groups matched, suggestions with optional output groups unmatched, disabled entities found in sibling matching, ambiguous matches surfaced as multiple candidates.

**Success criterion:** an integration test bootstraps a fake HA environment with a couple of fake integrations and entities, runs discovery, and asserts the expected profile suggestions are returned with appropriate confidence and bindings.

---

## Phase 8 — WebSocket command surface (mutations) and ad-hoc profile flow

**Goal.** The full set of WebSocket commands needed by the panel exists and is documented.

**End state:**

- Mutation commands: `add_device`, `update_device`, `remove_device`, `add_connection`, `remove_connection`, `upsert_zone`, `remove_zone`, `update_source_visibility`, `bind_entity`, `update_remap`.
- Subscription commands for live state: `subscribe_state` (graph state), `subscribe_diagnostics` (orchestrator activity).
- Ad-hoc profile creation flow: a multi-step WebSocket flow that walks through declaring interfaces, output groups, mechanisms, and capturing discovery hints from the bound entity. The wizard captures `platform`, `device_registry` manufacturer/model, and any distinguishing attributes from the entity at binding time so the locally-saved profile can be auto-discovered on this user's system thereafter.
- All commands documented in `docs/websocket-api.md` with versioning information.
- Tests for each command (positive and negative cases).

**Success criterion:** a test exercises every WebSocket command and asserts state changes match expectations.

---

## Phase 9 — Frontend panel (skeleton)

**Goal.** A bundled panel registers and is reachable from the HA sidebar. Devices and Zones tabs work end-to-end against the WebSocket API.

**End state:**

- Frontend project (`frontend/`) using Lit + Vite. TypeScript strict mode.
- Build pipeline produces a single bundled JS file at `custom_components/media_room_manager/panel/<bundle>.js` and `panel_custom` configuration registers it.
- Panel structure: tabbed dashboard with placeholders for all six tabs.
- **Devices tab**: device cards, modal for full editor, "Add Device" flow with auto-discovery, ad-hoc device wizard. Multi-binding suggestions render as a single device with pre-filled bindings; user can override individual bindings before confirming.
- **Zones tab**: zone cards, modal for full zone editor, dual-list source visibility selector, sink mode selector, volume authority pinning.
- WebSocket client wrapper (typed) for all the commands needed.
- Cards-with-modals interaction pattern. Mobile-responsive.
- No graph canvas yet.

**Success criterion:** a user can install the integration, open the panel, add devices via auto-discovery and ad-hoc paths, define connections inline, create zones, and see the resulting `media_player` entities appear in HA.

---

## Phase 10 — Frontend panel (remaining tabs)

**Goal.** Connections, Profile library, Diagnostics (with Looking Glass), and Settings tabs work.

**End state:**

- **Connections tab**: connections overview table with auditing/bulk-edit affordances.
- **Profile library tab**: searchable, filterable, install/override/edit/submit flows.
- **Diagnostics tab**:
  - Live state cards: active zones, in-progress orchestration, observed-vs-commanded mismatches.
  - **Looking Glass**: header with Zone/Source/Display dropdowns; two side-by-side cards (Video, Audio) showing resolved paths; stacks vertically on narrow viewports; surfaces resolution failures with clear messages; passive note for `exclusive_outputs` devices reminding the user that output state is externally managed.
- **Settings tab**: integration-wide options (community profile fetching opt-in, log verbosity, defaults).

**Success criterion:** every tab is functional, the Looking Glass renders correctly for each starter-profile-based example system, errors are surfaced clearly.

---

## Phase 11 — Polish, packaging, and release prep

**Goal.** v1.0 ready for public release.

**End state:**

- HACS metadata (`hacs.json`) complete and validated.
- README at repo root is the public-facing intro (may be slimmer than the design README — link to the full design doc).
- Installation instructions, screenshots, getting-started guide.
- Documentation site or `docs/` folder with: profile schema reference, WebSocket API reference, contribution guide, troubleshooting.
- All operational expectations clearly stated.
- Profile contribution flow tested end-to-end.
- CI: tests run on PRs, lint and type-check enforced.
- Versioning strategy in place (semver, schema version compatibility).

**Success criterion:** an outside user can install via HACS, follow the getting-started guide, and successfully configure a small AV system without help.

---

## Out of scope for v1.0

These are explicitly v1.x, v2.0, or later and not part of this plan:

- `share` contention policy (v1.x).
- Community profile repository with federation / fetching beyond bundled profiles (v1.x; submit-from-UI flow opens GitHub PRs).
- `media_player.join` exposure for streaming-source multi-room (v1.x).
- Topology visualization tab (v2.0).
- Sophisticated power policies — load shedding, scheduled, dependency timeouts (v2.0).
- Advanced contention policies — queueing, priority (v2.0).
- Fallback path resolution when primary path fails (v2.0).
- CEC-aware orchestration (v2.0).
- Standardized profile-declaration interface for third-party HA integration developers (beyond v2.0).
- Scenes — preset zone activations (beyond v2.0).
- Cross-system migration tools — Control4 project import, etc. (beyond v2.0).

If a session reveals one of these is necessary for v1.0 correctness, raise it; otherwise it stays deferred.

---

## Notes on phasing

Phases are sequential in dependency, but small overlaps are fine where one phase's output is needed to test another. For example, Phase 3 (adapters) can begin while Phase 2 (profile registry) is still adding starter profiles, since adapters don't depend on the full library. Phase 6 (entities) requires Phase 5 (orchestrator) to be functional but can stub orchestrator results in tests if needed.

The frontend (Phases 9-10) requires a working WebSocket command surface (Phase 8). Don't start the frontend until the backend can answer its queries.

Each phase's "success criterion" is the gate before moving to the next. Don't move on if the criterion isn't met.
