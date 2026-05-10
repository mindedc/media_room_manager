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

- Dataclasses (or equivalent) for: `Device`, `Interface`, `Connection`, `Zone`, `OutputGroup`, `VirtualSource`, `SourceVisibilitySelection`, instance bindings.
- `voluptuous` validators for each.
- `Store`-backed persistence at `<config>/.storage/media_room_manager.system` with `version=1` and migration scaffolding.
- A small set of WebSocket commands for read-only inspection: `list_devices`, `list_zones`, `list_connections`. (Mutations come later.)
- Unit tests for: dataclass construction, schema validation (positive and negative cases), Store round-trip.

**Success criterion:** can write a test that constructs an in-memory graph, persists it, reloads it, and gets equivalent objects back.

---

## Phase 2 — Profile registry and bundled profiles

**Goal.** Profiles can be loaded, validated, and queried. A small starter library exists.

**End state:**

- Profile YAML schema (`voluptuous`) covering everything in the README's profile examples: `output_groups` (with `selection_mechanism`, capability expectations, `provides_roles`), `interfaces` (with type, label, `output_group` or `routable_to_output_group`), `aux_entities`, `virtual_sources`, `dynamic_virtual_sources`, `inputs_are_exclusive_per_output_group`, `exclusive_outputs`, `discovery`, `power_metadata`.
- Profile loader that reads bundled profiles from the package's `profiles/bundled/` directory.
- Profile registry that resolves profile-by-id lookups.
- ~10 hand-written profiles for common devices to seed the library:
  - One simple source (e.g., Apple TV).
  - One IR-controlled source (e.g., a generic Blu-ray).
  - One single-zone AVR.
  - One multi-zone AVR (Marantz SR8015).
  - One AVR with parallel HDMI outputs (Anthem MRX 740).
  - One true matrix using `select_entity` (Monoprice Blackbird).
  - One HDFury-style device (Diva or Vertex).
  - One Lumagen-class processor with `exclusive_outputs`.
  - One passive HDMI splitter / distribution amp.
  - One passive converter (HDMI audio extractor).
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
- The `$value` sentinel substitution mechanism in `service_call` parameter data.
- Unit tests for each adapter using HA's mock service registry — verify the right service call is emitted with the right parameters for each operation.

**Success criterion:** a test for each adapter constructs a profile snippet using that mechanism, runs the adapter through each operation it supports, and asserts the expected `hass.services.async_call` invocations.

---

## Phase 4 — Path resolver

**Goal.** Given a graph and a (source, zone) pair, the resolver returns a structured path or a clear failure.

**End state:**

- BFS-based path finding through the connection graph for video and audio independently.
- Handles transit devices (any input → any output of compatible carrier within the same output group).
- Handles `hdmi_audio_return` interfaces' implicit reverse audio.
- Handles virtual sources (the "path" is just the device + virtual source selection).
- Handles `simultaneous` and `selectable_exclusive` zones (multiple sinks).
- Returns structured output: ordered (device, output_group, input_interface, output_interface) tuples, or a structured failure with reason.
- A `resolve_path(zone_id, source_id, sink_id=None)` WebSocket command that runs the resolver and returns its output. This is the data backing the Looking Glass.
- Extensive unit tests covering: simple linear paths, multi-hop paths through matrices and AVRs, audio paths diverging from video paths, no-path failures, type-incompatible paths, virtual source activation.

**Success criterion:** for each starter profile combination, a test fixture defines a small example system (a few devices, connections, and zones) and asserts the resolver produces correct paths.

---

## Phase 5 — Role resolver and orchestrator

**Goal.** Resolved paths can be turned into actual command sequences against HA, and zone activation works end-to-end.

**End state:**

- Role resolver: given an active path, identifies which device holds each control role. Volume is pinned (lookup); transport and metadata_source are dynamic.
- Orchestrator: takes resolved paths, executes power-on in dependency order with delays, executes input selections from sink toward source, activates virtual sources, signals transport at the source.
- Per-step retries with configurable counts.
- Failure surfaces on the zone media_player as `state: unavailable` with `error_detail` attribute.
- Contention detection (input-side from `inputs_are_exclusive_per_output_group`, output-side from `output_selection` per output and `exclusive_outputs`). Zone-level contention policy: `deny`, `preempt`, `share`. v1 implements `deny` and `preempt`; `share` can be deferred to v1.x.
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
- **Discovery service** scans HA's installed integrations, device registry, and entities. Implements constellation matching against profiles' `discovery` blocks. Returns ranked profile suggestions for any candidate entity.
- A `discover_profiles_for_entity` WebSocket command that returns ranked suggestions for a given entity.
- An "Add Device" WebSocket command flow that surfaces auto-discovery suggestions.
- Discovery service also re-evaluates dynamic virtual sources for already-bound entities when their `source_list` changes.
- **Repair service** observes events and emits HA repairs for: disappeared dynamic source that was enabled, source-list expectations broken, path no longer resolves, bound entity removed.
- Tests for each service.

**Success criterion:** an integration test bootstraps a fake HA environment with a couple of fake integrations and entities, runs discovery, and asserts the expected profile suggestions are returned with appropriate confidence.

---

## Phase 8 — WebSocket command surface (mutations) and ad-hoc profile flow

**Goal.** The full set of WebSocket commands needed by the panel exists and is documented.

**End state:**

- Mutation commands: `add_device`, `update_device`, `remove_device`, `add_connection`, `remove_connection`, `upsert_zone`, `remove_zone`, `update_source_visibility`, `bind_entity`, `update_remap`.
- Subscription commands for live state: `subscribe_state` (graph state), `subscribe_diagnostics` (orchestrator activity).
- Ad-hoc profile creation flow: a multi-step WebSocket flow that walks through declaring interfaces, output groups, mechanisms, and capturing discovery hints from the bound entity.
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
- **Devices tab**: device cards, modal for full editor, "Add Device" flow with auto-discovery, ad-hoc device wizard.
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
  - **Looking Glass**: header with Zone/Source/Display dropdowns; two side-by-side cards (Video, Audio) showing resolved paths; stacks vertically on narrow viewports; surfaces resolution failures with clear messages; passive note for `exclusive_outputs` devices.
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

## Out of scope for v1

These are explicitly v1.x or later and not part of this plan:

- Topology visualization tab (read-mostly graph view).
- Advanced contention policies (`share`, queueing).
- Sophisticated power policies (load shedding, scheduled, dependency timeouts).
- CEC-aware orchestration.
- Fallback path resolution.
- Community profile repository (federation, fetching). v1 ships with bundled profiles only; submit-from-UI flow lands content in a GitHub PR.
- Standardized profile-declaration interface for third-party HA integration developers (a Python package).
- Scenes (preset zone activations).
- Cross-system migration tools (Control4 project import, etc.).

If a session reveals one of these is necessary for v1 correctness, raise it; otherwise it stays deferred.

---

## Notes on phasing

Phases are sequential in dependency, but small overlaps are fine where one phase's output is needed to test another. For example, Phase 3 (adapters) can begin while Phase 2 (profile registry) is still adding starter profiles, since adapters don't depend on the full library. Phase 6 (entities) requires Phase 5 (orchestrator) to be functional but can stub orchestrator results in tests if needed.

The frontend (Phases 9-10) requires a working WebSocket command surface (Phase 8). Don't start the frontend until the backend can answer its queries.

Each phase's "success criterion" is the gate before moving to the next. Don't move on if the criterion isn't met.
