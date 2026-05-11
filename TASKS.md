# TASKS.md

Granular task tracker. Each task is sized to fit one Claude Code session without exhausting context. Work top-to-bottom within the active phase.

When you complete a task, mark it `[x]` and commit the work *and* this update in the same commit. If a task is too big for a session, break it into smaller subtasks here rather than leaving a half-finished commit.

If a task description is unclear or seems to contradict the README, **stop and ask** — don't guess.

---

## Active phase: Phase 7 — Services (state tracker, discovery, repair)

### Phase 0 tasks

- [x] **0.1** Initialize repo structure. Create directories: `custom_components/media_room_manager/`, `frontend/`, `tests/{unit,integration,fixtures}/`, `scripts/`, `docs/`. Add a top-level `.gitignore` (Python + Node patterns), `LICENSE` (TBD by user — leave a placeholder if not specified), and a stub `README.md` at the repo root that points at the design doc location.

- [x] **0.2** Create `custom_components/media_room_manager/manifest.json` with: `domain: "media_room_manager"`, `name: "Media Room Manager"`, valid HACS-compatible fields. Set `version` to `0.0.1`. Include `iot_class`, `dependencies`, `requirements` (empty list initially), `codeowners`. Validate against HA's manifest schema.

- [x] **0.3** Create `custom_components/media_room_manager/__init__.py` with the standard async setup/unload structure for a config-flow-based integration. `async_setup_entry` returns `True` and stores nothing yet. `async_unload_entry` returns `True`. `const.py` defines `DOMAIN = "media_room_manager"` and any other constants.

- [x] **0.4** Create `custom_components/media_room_manager/config_flow.py` with a single-step flow that just creates a config entry with no data. Title: "Media Room Manager". The user clicks "Submit" and the integration installs. No options flow yet.

- [x] **0.5** Set up Python tooling. Add `pyproject.toml` with `ruff`, `mypy`, and `pytest` configurations. Configure `ruff` for line length 100, target Python 3.12, sensible rule selection. Configure `mypy` with `strict = true` for `custom_components/`. Configure `pytest` to discover tests from `tests/`.

- [x] **0.6** Add development dependencies. Create `requirements_test.txt` with `pytest`, `pytest-asyncio`, `pytest-homeassistant-custom-component`, `voluptuous`, `homeassistant`, `ruff`, `mypy`. Document install steps in a brief `docs/development.md`.

- [x] **0.7** Add a single trivial unit test in `tests/unit/test_const.py` that imports `const` and asserts `DOMAIN == "media_room_manager"`. Verify `pytest` runs and passes.

- [x] **0.8** Verify `ruff check`, `ruff format --check`, and `mypy` all pass on the empty integration. Fix any issues from scaffolding.

- [x] **0.9** Set up frontend tooling stub. Create `frontend/package.json`, `frontend/tsconfig.json` (strict mode), `frontend/vite.config.ts`, `frontend/.eslintrc`, and `frontend/src/index.ts` (empty). Verify `npm install` and `npm run typecheck` work, even though there's no real code yet. Don't build a panel yet.

- [ ] **0.10** Verify the integration loads in a dev HA instance. Document the steps in `docs/development.md`. The integration should appear in "Add Integration", install successfully, and show no errors in the HA log. Mark Phase 0 complete.

---

## Phase 1 — Graph model and persistence

### Phase 1 tasks

- [x] **1.1** Create `custom_components/media_room_manager/graph/__init__.py` and `graph/model.py` with frozen dataclasses for the simplest objects first: `InterfaceType` (enum), `InterfaceDirection` (enum), `Interface`. Type hints throughout. Unit tests verifying construction and equality.

- [x] **1.2** Add dataclasses for `OutputGroup`, `Connection`, `VirtualSource`, `Device`. Unit tests for each.

- [x] **1.3** Add dataclasses for `Zone` (with `sink_mode` enum: `single`, `simultaneous`, `selectable_exclusive`), `SourceVisibilitySelection`, `InstanceBinding` (entity registry id + per-instance remaps), and any supporting types. Unit tests.

- [x] **1.4** Create `graph/schema.py` with `voluptuous` validators for each dataclass. Validators should be reversible: `validator(value).is_valid` and round-trip through dict serialization. Tests covering positive and negative cases for each.

- [x] **1.5** Create `store.py` with a `MRMStore` class wrapping HA's `Store` helper. Persistence key: `media_room_manager.system`. Version 1. Methods: `async_load() -> SystemConfig`, `async_save(config: SystemConfig)`. Migration scaffold (no migrations needed yet, but the structure is in place). Round-trip test: build a non-trivial config, save it, reload, assert equality.

- [x] **1.6** Define a `SystemConfig` aggregate that holds all graph data (lists of devices, connections, zones, source visibility selections, etc.). Includes a `schema_version` field. Add to the validator set.

- [x] **1.7** Wire `MRMStore` into the integration's `async_setup_entry`. On entry setup, load the config (or create an empty one if none exists) and stash it in `hass.data[DOMAIN][entry.entry_id]`. Tests using HA's mock environment.

- [x] **1.8** Create `websocket/__init__.py` and `websocket/inspection.py`. Register read-only commands `media_room_manager/list_devices`, `media_room_manager/list_zones`, `media_room_manager/list_connections`. Each returns the relevant slice of the system config as serializable dicts. Unit tests asserting the commands return correct data.

- [x] **1.9** Document the WebSocket commands added in this phase in `docs/websocket-api.md` with command names, parameters, response shapes, and version notes.

- [x] **1.10** Verify all Phase 1 success criteria. Mark Phase 1 complete.

---

## Phase 2 — Profile registry and bundled profiles

### Phase 2 tasks

- [x] **2.1** Create `profiles/schema.py` defining the full profile YAML schema in `voluptuous`. Cover:
  - Top-level: `profile_id`, `schema_version`, `manufacturer`, `model`, `category`, `power_handling` (one of `discrete_capable`, `toggle`, `always_on`, `disabled`), `power_on_delay` (integer seconds, defaults to 0), `exclusive_outputs` (boolean, optional).
  - `output_groups` list: each with `id`, optional `selection_mechanism` (with `kind`, `expected_domain`, capability expectations like `expected_features`, `expected_options`, `expected_commands`), `provides_roles`, and optional `role_operations` for non-`media_player`-bound groups.
  - `inputs_are_exclusive_per_output_group` list of output_group ids.
  - `aux_entities` list: each with `id`, `expected_domain`, and capability expectations.
  - `interfaces` list: each with `id`, `direction`, `type`, `label`. Outputs declare `output_group`; inputs declare `routable_to_output_group` (list of output_group ids).
  - `virtual_sources` list: each with `id`, `label`, `routable_to_output_group`.
  - `dynamic_virtual_sources` block: `source` (currently only `source_list_minus_known`), `output_group`, optional `exclude` list.
  - `discovery` block (optional): `output_groups` list, each with `output_group`, optional `is_discovery_anchor: true`, `match_threshold`, optional `optional: true`, `signals` list.
  - Document the schema in `docs/profile-schema.md`.

- [x] **2.2** Create `profiles/loader.py`. Function: `load_profile_yaml(path: Path) -> Profile`. Reads YAML, validates against schema, returns a typed `Profile` dataclass (defined in `profiles/types.py`). Tests against minimal valid and invalid examples.

- [x] **2.3** Create `profiles/registry.py`. `ProfileRegistry` loads bundled profiles from `profiles/bundled/` at integration startup. Exposes `get(profile_id) -> Profile | None` and `list_all() -> list[Profile]`. Layered loading order: local > community-fetched > bundled (only bundled implemented in this phase). Tests.

- [x] **2.4** Author starter profile #1: Apple TV 4K (`profiles/bundled/apple/apple-tv-4k.yaml`). Match the README example. `power_handling: discrete_capable`. Includes `dynamic_virtual_sources` with `exclude` list. Discovery block with anchor on `main`. Verify it loads.

- [x] **2.5** Author starter profile #2: Sony DVP-NS500V (IR-controlled Blu-ray). `power_handling: toggle`. Uses `remote_command` mechanism in `role_operations`. Aux entity for the IR blaster. Match the README example.

- [x] **2.6** Author starter profile #3: a single-zone AVR — pick a representative model (e.g., Denon AVR-X1700H) and structure it cleanly. `power_handling: discrete_capable`. One output group with `media_player_source` mechanism. Include `discovery` block.

- [x] **2.7** Author starter profile #4: Marantz SR8015. Match the README example exactly. Two output groups (`main` and `zone_2`), `inputs_are_exclusive_per_output_group`, static `tuner` virtual source, `dynamic_virtual_sources` for HEOS on `main`. Discovery block with anchor on `main` and optional sibling for `zone_2`.

- [x] **2.8** Author starter profile #5: Anthem MRX 740. Two output groups with parallel HDMI outputs both belonging to `main`. Discovery block. Match the README example.

- [x] **2.9** Author starter profile #6: Monoprice Blackbird 8x8 matrix. Each output is its own output group of size 1 with `select_entity` mechanism. Aux entity for the power switch. Match the README example.

- [x] **2.10** Author starter profile #7: HDFury Diva. Two output groups (`tx0`, `tx1`) with audio extraction outputs in TX0's group. Power switch aux entity. Discovery block.

- [x] **2.11** Author starter profile #8: Lumagen Radiance Pro. Single output group, `exclusive_outputs: true`, `inputs_are_exclusive_per_output_group: [main]`. Match the README example.

- [x] **2.12** Author starter profile #9: a generic HDMI 1×4 splitter / distribution amp. One output group with no `selection_mechanism` (passive transit). `power_handling: disabled`.

- [x] **2.13** Author starter profile #10: generic HDMI audio extractor. Passive converter category. One output group with no `selection_mechanism`, four outputs (HDMI passthrough, HDMI audio extraction, optical, RCA). `power_handling: disabled`. Match the README example.

- [x] **2.14** Add WebSocket commands `media_room_manager/list_profiles` and `media_room_manager/get_profile`. Each returns serialized profile data. Tests.

- [x] **2.15** Verify all 10 starter profiles load without warnings. Add an integration test that loads each and asserts structural correctness (expected number of interfaces, output groups, etc.). Mark Phase 2 complete.

---

## Phase 3 — Adapter registry

### Phase 3 tasks

- [x] **3.1** Define the adapter interface in `adapters/base.py`. Abstract base class (or Protocol) with async methods: `async_select_input(...)`, `async_set_volume(...)`, `async_send_transport(...)`, `async_power_on(...)`, `async_power_off(...)`, etc. Document each method's contract.

- [x] **3.2** Implement `MediaPlayerSourceAdapter` in `adapters/media_player_source.py`. Operations call `media_player.select_source`, `media_player.turn_on`, `media_player.turn_off`, `media_player.volume_set`, etc., on the bound entity. Tests using HA's mock service registry assert the right service calls.

- [x] **3.3** Implement `SelectEntityAdapter` in `adapters/select_entity.py`. Calls `select.select_option` on the bound entity. Tests.

- [x] **3.4** Implement `SwitchComboAdapter` in `adapters/switch_combo.py`. For matrices exposed as a grid of switch entities, turns on the correct switch and ensures others in the row are off. Tests.

- [x] **3.5** Implement `RemoteCommandAdapter` in `adapters/remote_command.py`. Calls `remote.send_command` with the configured command name. Supports command sequences with delays. Tests including sequence/delay behavior.

- [x] **3.6** Implement `ServiceCallAdapter` in `adapters/service_call.py`. Calls an arbitrary HA service with statically-enumerated parameters. Implements the `$value` sentinel substitution: any field whose value is exactly `"$value"` is replaced with the operation's input value at call time. Tests covering positive cases and rejection of any other templating attempts (e.g., `"prefix-$value"` is **not** substituted; only the literal string `"$value"` is).

- [x] **3.7** Create `adapters/registry.py` with an `AdapterRegistry` that maps mechanism kind strings to adapter instances. Used by the orchestrator. Tests.

- [x] **3.8** Verify all five adapters work correctly in isolation against HA's mock environment. Mark Phase 3 complete.

---

## Phase 4 — Path resolver

### Phase 4 tasks

- [x] **4.1** Create `resolver/graph_view.py`. Helper that takes a `SystemConfig` and produces a queryable view: "for this output interface, what input interface does it connect to?", "for this device's output group, what input interfaces are routable to it?", etc. Tests.

- [x] **4.2** Implement `resolver/path.py` BFS for simple linear paths through a single carrier (audio or video). Given (source_interface, sink_interface, carrier), returns the list of (device, input_interface, output_interface, output_group) tuples or a structured "no path" result. Tests with simple two-device and three-device chains.

- [x] **4.3** Add transit-device transparency: any input on a transit device can reach any output of compatible carrier within the same output group. Tests with a matrix in the middle of a path.

- [x] **4.4** Add `hdmi_audio_return` reverse-audio handling: when computing audio paths, treat `hdmi_audio_return` interfaces as having a hidden complementary direction. Tests with a TV-feeding-AVR-via-ARC example.

- [x] **4.5** Add output-group constraint checking: an input is only routable to a given output group if listed in `routable_to_output_group`. Tests with a Marantz-like profile where Phono is routable to main only.

- [x] **4.6** Handle multi-sink zones: `simultaneous` (resolve to each sink, deduplicate shared transit devices) and `selectable_exclusive` (resolve to one sink per request). Tests covering both modes.

- [x] **4.7** Handle virtual sources: when the source is a virtual source, the "path" is the source's containing device + virtual source selection. The audio path terminates at the volume authority (which may be a different device entirely if the virtual source is upstream of an AVR). Tests.

- [x] **4.8** Add `exclusive_outputs` tracking. The resolver records which output of an `exclusive_outputs` device is being used in the resolved path. This is captured in the resolver's output for the orchestrator's contention tracking — the resolver does not refuse to compute paths through `exclusive_outputs` devices and does not command output switching.

- [x] **4.9** Add input-side and output-side contention detection. Path resolver checks against currently-active paths and reports contention as part of its result. Includes input-side from `inputs_are_exclusive_per_output_group`, output-side from per-output `output_selection`, and output-side from `exclusive_outputs` devices. Tests with two zones competing for an AVR's input and two zones competing for a Lumagen's outputs.

- [x] **4.10** Implement WebSocket command `media_room_manager/resolve_path` that takes (zone_id, source_id, sink_id?) and returns the structured resolver output. This powers the Looking Glass. Tests.

- [x] **4.11** Build comprehensive integration tests using a fixture system that defines small example configurations (Marantz + Apple TV, a sports-bar setup with matrix, a media room with TV+projector, an HDFury Diva with audio extraction to a stereo amp, a Lumagen feeding two displays) and asserts resolver output for various source-zone combinations. Mark Phase 4 complete.

---

## Phase 5 — Role resolver and orchestrator

### Phase 5 tasks

- [x] **5.1** Create `resolver/roles.py`. Given a resolved path, identifies which device/output_group holds each control role: `volume` from the zone's pinned volume authority; `transport` and `metadata_source` from the active source's device. Tests.

- [x] **5.2** Create `orchestrator/__init__.py` and `orchestrator/orchestrator.py`. Skeleton class with `async_activate_zone(zone_id, source_id, sink_id?)` and `async_deactivate_zone(zone_id)`. Wire it to the path resolver, role resolver, and adapter registry.

- [x] **5.3** Implement power-on sequencing respecting `power_handling`. For `discrete_capable`, issue power_on commands. For `toggle`, use observed state (or commanded-state fallback from the state tracker) to decide whether to issue the toggle. For `always_on` and `disabled`, issue no commands. Respect `power_on_delay`. Tests with mock devices for each `power_handling` value.

- [x] **5.4** Implement input-selection sequencing. From sink toward source, set each transit device's input via the relevant output group's selection mechanism. Shared transit devices configured once. For `exclusive_outputs` devices, the orchestrator does **not** command output switching — it commands input selection and trusts the user has externally configured the active output. Tests.

- [x] **5.5** Implement virtual-source selection. If the active source is a virtual source, after path setup, select it on its containing device. Tests.

- [x] **5.6** Implement transport activation. After path setup, issue a transport command (typically `play`) at the source if it provides the transport role. Tests.

- [x] **5.7** Implement deactivation sequencing. On zone deactivation, mark devices in the path as no-longer-needed-by-this-zone. Devices still in use by other zones stay on. Devices no longer needed are powered off (respecting `power_handling`). Tests with shared devices and multi-zone scenarios.

- [x] **5.8** Implement retry policy and failure surfacing. Each step has a configurable retry count. Hard failures result in `state: unavailable` plus `error_detail` on the zone media_player. Tests injecting failures.

- [x] **5.9** Implement contention enforcement for `deny` and `preempt` policies. When activation requires a contended resource, apply the zone's policy. For `preempt`, tear down conflicting paths first. **The `share` policy is v1.x and is not implemented in this phase** — profiles or zone configurations specifying `share` should be validated against and rejected with a clear error message in v1.0. Tests for both `deny` and `preempt` covering input-side, output-side, and `exclusive_outputs` contention.

- [x] **5.10** End-to-end integration test: load a multi-device profile set, define a graph and a zone, activate the zone, assert correct service calls were made in the correct order. Mark Phase 5 complete.

---

## Phase 6 — Entities and devices

### Phase 6 tasks

- [x] **6.1** Create `entities/__init__.py` and `entities/zone_media_player.py`. Implement the per-zone `MediaPlayerEntity` subclass. Stub state and supported_features for now; expand in subsequent tasks.

- [x] **6.2** Implement `supported_features` static computation. At zone configuration time, compute the union of features across all devices that could hold a role in any path through this zone. Cache and expose as the entity's `supported_features`. Tests.

- [x] **6.3** Implement source list computation from source visibility config. The entity's `source_list` is the visible-sources list for the zone. `select_source` triggers orchestrator activation. Tests.

- [x] **6.4** Implement transport command pass-through. `media_play`, `media_pause`, `media_stop`, etc., on the zone entity route to the active source's `transport` role-holder via the orchestrator. Tests with mock active sources.

- [x] **6.5** Implement volume command pass-through. `volume_set`, `volume_up`, `volume_down`, `volume_mute` on the zone entity route to the volume authority (pinned per zone). Tests.

- [x] **6.6** Implement metadata pass-through. The zone entity subscribes to the `metadata_source` role-holder's state changes and surfaces `media_title`, `media_artist`, `media_image_url`, etc., as its own attributes. When the active source changes, the subscription moves. Tests.

- [x] **6.7** Implement state computation: `off`, `idle`, `playing`, `paused`, `unavailable` based on orchestrator and underlying state. `error_detail` attribute on errors. Tests.

- [x] **6.8** Implement helper entities for `selectable_exclusive` zones: `select.<zone>_display` and per-sink `switch.<zone>_<sink>`. Bidirectional sync — toggling a switch updates the select; changing the select updates switches; both trigger orchestrator. Tests.

- [x] **6.9** Implement `binary_sensor.<device>_in_use` for shared physical devices. Only created for devices reachable from more than one zone. Updates as orchestrator state changes. Tests.

- [x] **6.10** Register HA Device Registry entries for each Media Room Manager zone and each orchestrated physical device. Associate appropriate entities under each device entry. Tests with HA's device registry mocks.

- [x] **6.11** Integration test: configure a multi-zone system, verify all expected entities are registered under the correct device entries, simulate state changes, and assert entity behavior. Mark Phase 6 complete.

---

## Phase 7 — Services (state tracker, discovery, repair)

### Phase 7 tasks

- [ ] **7.1** Create `services/state_tracker.py`. Subscribes to state changes on every entity referenced by the active graph. Maintains in-memory observed/commanded/unknown state per device interface. Exposes a query API for the orchestrator. Tests.

- [ ] **7.2** Wire state tracker re-evaluation on external changes. If an underlying entity changes state outside an orchestrator-issued command, the affected zone's state recomputes. Tests with simulated external changes.

- [ ] **7.3** Create `services/discovery.py`. Implement the eight signal scoring functions:
  - `device_registry` — read `dev_reg.async_get(entity.device_id)` and match `manufacturer` and `model_patterns`.
  - `platform` — read `entity_registry_entry.platform` and match `domain`.
  - `supported_features` — read entity state `supported_features` and match against `values` list.
  - `source_list_signature` — read entity state `source_list` and match with `includes_any`, `includes`, or `matches` operators.
  - `sound_mode_list_signature` — read entity state `sound_mode_list` and match with same operators.
  - `device_class` — read entity state `device_class` (or registry `original_device_class`) and match against `matches` list.
  - `friendly_name` — read entity state `friendly_name` and match against `friendly_name_patterns` (substring match).
  - `attribute_constellation` — read entity state attribute keys (presence, not values) and verify all keys in `includes` are present.
  - Each scoring function returns the matched weight (or 0 if no match). Tests per signal kind.

- [ ] **7.4** Implement two-stage discovery in `services/discovery.py`:
  - **Stage 1 (anchor matching):** for each profile with a `discovery` block, find the output group entry flagged `is_discovery_anchor: true`. Iterate `ent_reg.entities.values()` for enabled entities. For each entity, score against the anchor signals, sum weights, compare against the anchor output group's `match_threshold`. Entities above threshold are anchor candidates.
  - **Stage 2 (sibling matching):** for each anchor candidate, retrieve siblings via `async_entries_for_device(ent_reg, entity.device_id, include_disabled_entities=True)`. For each other output group in the profile's discovery block, score each sibling against that output group's signals, apply that group's `match_threshold`. Assign the best-matching sibling. If no sibling meets the threshold and the entry is marked `optional: true`, leave the output group unbound; otherwise flag the unmatched required output group in the suggestion.
  - Return a ranked list of `DiscoverySuggestion` objects, each containing the matched profile, the anchor binding, and a dict of `output_group_id → entity_id | None` for sibling bindings.
  - Tests covering: high-confidence single-output-group match (Apple TV), high-confidence multi-output-group match with both sibling bindings (Marantz), optional sibling unbound (zone 2 entity disabled), multiple profiles surfaced when ambiguous, sub-threshold candidates filtered out.

- [ ] **7.5** Add WebSocket command `media_room_manager/discover_profiles` that runs full two-stage discovery and returns the ranked suggestions. Add `media_room_manager/discover_profiles_for_entity` for inspecting matches against a specific entity (useful for debugging and the ad-hoc wizard). Tests.

- [ ] **7.6** Implement dynamic-virtual-source rediscovery. When a bound entity's `source_list` changes, the discovery service recomputes the dynamic virtual sources for the relevant device's output groups, subtracting known physical interfaces, static virtual sources, and `exclude` list entries. The remainder is the dynamic source candidate pool. Tests.

- [ ] **7.7** Surface disabled-entity bindings in suggestions. When the discovery service binds a disabled entity to an output group via sibling matching, the suggestion includes a flag and human-readable note indicating the disabled state. The panel will display this so the user can enable the entity in their integration before confirming. Tests.

- [ ] **7.8** Create `services/repair.py`. Observes events and emits HA repairs. Cases: disappeared dynamic source previously enabled, source-list expectations broken, path no longer resolves, bound entity removed. Implement each as a separate repair handler with resolution flow. Tests for each case.

- [ ] **7.9** Newly discovered dynamic sources are **not** repairs. Surface them as a passive panel indication via the WebSocket subscription. Tests.

- [ ] **7.10** Integration test: bootstrap a fake HA environment with mock integrations and entities, run discovery, assert correct suggestions are returned with correct bindings. Test the disappearance case to assert the correct repair fires with correct resolution options. Mark Phase 7 complete.

---

## Phase 8 — WebSocket mutations and ad-hoc profile flow

### Phase 8 tasks

- [ ] **8.1** Implement mutation commands `add_device`, `update_device`, `remove_device`. Each takes the relevant payload, validates against the schema, applies the change to the system config, persists, and broadcasts a state update. Tests covering positive cases and validation errors.

- [ ] **8.2** Implement `add_connection` and `remove_connection`. Type compatibility check. Tests.

- [ ] **8.3** Implement `upsert_zone` and `remove_zone`. Includes sink mode, sink list, volume authority binding. Tests.

- [ ] **8.4** Implement `update_source_visibility` for a zone. Tests.

- [ ] **8.5** Implement `bind_entity` to bind an entity registry id to an output group's selection mechanism slot or an aux_entity slot on a device instance. Tests.

- [ ] **8.6** Implement `update_remap` for per-instance label remaps (source list values, command names, select options). Tests.

- [ ] **8.7** Implement `subscribe_state` for the panel's live state subscription. Pushes graph state changes and orchestrator events. Tests.

- [ ] **8.8** Implement `subscribe_diagnostics` for the panel's diagnostics tab live data. Tests.

- [ ] **8.9** Design and implement the ad-hoc profile creation flow as a multi-step WebSocket interaction. The user walks through declaring interfaces, output groups (and their mechanisms), and capturing discovery hints from the bound entity. The wizard captures `platform`, manufacturer/model from device registry, and distinguishing attributes at binding time so the locally-saved profile can be auto-discovered later. Resulting profile is saved to `<config>/media_room_manager/profiles/`. Tests.

- [ ] **8.10** Document all WebSocket commands added in this phase in `docs/websocket-api.md`. Include versioning notes. Mark Phase 8 complete.

---

## Phase 9 — Frontend panel skeleton

### Phase 9 tasks

- [ ] **9.1** Set up the Vite build to output a single bundled JS file at `custom_components/media_room_manager/panel/panel.js`. Configure `panel_custom` registration in `__init__.py` so the panel appears in the sidebar after install. Tests verifying panel registration in HA.

- [ ] **9.2** Create the WebSocket client wrapper in `frontend/src/api/`. Typed methods for every command the panel needs. Subscriptions for state and diagnostics streams.

- [ ] **9.3** Build the tabbed dashboard shell with Lit components. Tabs: Devices, Connections, Zones, Profile library, Diagnostics, Settings. Empty placeholders for each.

- [ ] **9.4** Implement the Devices tab: device cards, list view, "Add Device" button.

- [ ] **9.5** Implement the "Add Device" flow:
  - Discovery suggestions first. Multi-output-group suggestions render as a single device with pre-filled bindings for each output group. Unbound output groups (where sibling matching failed) appear with a "Bind manually" affordance. Disabled-entity bindings are flagged with a note about enabling the entity in the underlying integration.
  - Library search second.
  - Ad-hoc wizard third.
  - Each path produces a device added to the graph.

- [ ] **9.6** Implement the device editor modal: bind entities to output group mechanisms and aux entities, capability filtering, per-instance label remap UI.

- [ ] **9.7** Implement inline connection editing on device cards. Each output shows current connection or a "Connect…" affordance. Each input shows upstream source. Type-filtered pickers.

- [ ] **9.8** Implement the Zones tab: zone cards, "Add Zone" button.

- [ ] **9.9** Implement the zone editor: sink mode selection (with helper entity creation for `selectable_exclusive`), sink picker, volume authority pinning.

- [ ] **9.10** Implement the dual-list source visibility selector: candidate pool on the left (three categories — physical, static virtual, dynamic virtual), visible list on the right, search and reorder, per-zone display name overrides.

- [ ] **9.11** Mobile-responsive testing. Cards-with-modals interaction pattern works on narrow viewports.

- [ ] **9.12** End-to-end manual test: install in dev HA, configure a small AV system entirely through the panel, verify the resulting media_player entities. Mark Phase 9 complete.

---

## Phase 10 — Frontend remaining tabs

### Phase 10 tasks

- [ ] **10.1** Implement the Connections overview tab: table view of all connections, sortable, filterable, with bulk operations (delete selected, etc.).

- [ ] **10.2** Implement the Profile library tab: searchable browser, filter by manufacturer/category/installed-state, install/override/edit flows.

- [ ] **10.3** Implement the locally-defined profile editor (for ad-hoc profiles and local overrides). Ties to the ad-hoc profile creation flow.

- [ ] **10.4** Implement the submit-from-UI flow: opens a pre-filled GitHub PR (or equivalent submission target) with the local profile YAML.

- [ ] **10.5** Implement live diagnostic cards on the Diagnostics tab: active zones, active paths, observed-vs-commanded mismatches, recent orchestration events. Subscribes to `subscribe_diagnostics`.

- [ ] **10.6** Implement the Looking Glass parent card: header with Zone, Source, Display dropdowns. Display dropdown appears conditionally based on the selected zone's sink mode. For `selectable_exclusive` zones, lists each sink. For `simultaneous` zones, lists each sink plus an "All (simultaneous)" default. The audio card is unaffected by Display selection.

- [ ] **10.7** Implement the Looking Glass video and audio path cards. Side-by-side on wide viewports, stacked vertically on narrow. Source at top, transit devices in middle rows, endpoint at bottom. Branching support for `simultaneous` zones with "All" selected. Power state is not shown. Audio path always terminates at the volume authority.

- [ ] **10.8** Wire the Looking Glass to the `resolve_path` WebSocket command. Re-runs on selection change. Surfaces resolution failures clearly. Includes the passive note for `exclusive_outputs` devices reminding the user that output state is externally managed.

- [ ] **10.9** Implement the Settings tab: community profile fetching opt-in, log verbosity, default policies for new zones.

- [ ] **10.10** Cross-viewport polish pass. Verify all tabs work cleanly on desktop and mobile. Mark Phase 10 complete.

---

## Phase 11 — Polish, packaging, and release prep

### Phase 11 tasks

- [ ] **11.1** Add `hacs.json` with valid HACS metadata. Verify against HACS validation rules.

- [ ] **11.2** Polish the public-facing README at the repo root. Briefer than the design doc; covers installation, basic usage, screenshots, and links to the full design doc.

- [ ] **11.3** Write `docs/getting-started.md`: installation, adding the first device, creating the first zone, validating with the Looking Glass.

- [ ] **11.4** Write `docs/profile-schema.md`: full schema reference for community profile contributors. Includes all eight discovery signal kinds, the `power_handling` value set, and the `output_groups`-centric structure.

- [ ] **11.5** Write `docs/websocket-api.md`: reference for the WebSocket command surface (consolidate from earlier phases' incremental documentation).

- [ ] **11.6** Write `docs/contributing.md`: how to contribute profiles, code, etc.

- [ ] **11.7** Write `docs/troubleshooting.md`: common issues, how to use the Looking Glass and Diagnostics tab to diagnose them.

- [ ] **11.8** Add CI: GitHub Actions running `pytest`, `ruff`, `mypy`, frontend `npm run typecheck` and `npm run build` on every PR. Tests must pass for merge.

- [ ] **11.9** Versioning sweep. Confirm `manifest.json` version, profile `schema_version`, storage `version` are all sensible and documented.

- [ ] **11.10** Create a release checklist and tag v1.0.0. Mark Phase 11 (and v1.0) complete.

---

## How to use this file

1. Start each session by reading `README.md`, `CLAUDE.md`, `PLAN.md`, and this file in that order.
2. Identify the active phase (the heading marked "Active phase").
3. Find the first unchecked `[ ]` task in that phase.
4. Read the task description carefully. If anything is unclear or seems to contradict the README, **stop and ask the user** — don't guess.
5. Do the work. Run all the required commands listed in `CLAUDE.md` ("Required commands"). Fix or revert if anything fails.
6. Mark the task `[x]` in this file. Commit the work *and* this update in the same commit.
7. End the session with the summary format described in `CLAUDE.md`.

When all tasks in the active phase are checked, update the "Active phase" heading at the top of this file to point to the next phase.

Tasks should be small enough to fit in one session. If a task feels too big, break it down here into sub-tasks (e.g., "5.3a", "5.3b") and do them separately.
