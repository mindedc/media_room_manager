# Media Room Manager

**An AV signal-routing and orchestration layer for Home Assistant.**

Status: design phase, approaching implementation. This document is the architectural plan and reference for building the system.

---

## Table of contents

1. [Motivation](#motivation)
2. [What this is, and what it isn't](#what-this-is-and-what-it-isnt)
3. [Core concepts](#core-concepts)
4. [Architecture](#architecture)
5. [The configuration panel](#the-configuration-panel)
6. [The Looking Glass](#the-looking-glass)
7. [Profiles and the device library](#profiles-and-the-device-library)
8. [Interface types and connections](#interface-types-and-connections)
9. [Output groups](#output-groups)
10. [Virtual sources: static and dynamic](#virtual-sources-static-and-dynamic)
11. [Control mechanisms](#control-mechanisms)
12. [Profile content: what's declared, what's inferred](#profile-content-whats-declared-whats-inferred)
13. [Entity binding and capability matching](#entity-binding-and-capability-matching)
14. [Auto-discovery and repairs](#auto-discovery-and-repairs)
15. [Control roles and the virtual media_player](#control-roles-and-the-virtual-media_player)
16. [Zone sink modes](#zone-sink-modes)
17. [Source visibility](#source-visibility)
18. [Entities, devices, and automation triggers](#entities-devices-and-automation-triggers)
19. [State tracking](#state-tracking)
20. [Power management](#power-management)
21. [Path resolution and orchestration](#path-resolution-and-orchestration)
22. [Storage and data layout](#storage-and-data-layout)
23. [Operational expectations](#operational-expectations)
24. [Example profile YAML](#example-profile-yaml)
25. [Roadmap](#roadmap)
26. [Open questions](#open-questions)

---

## Motivation

Home Assistant has excellent device-level integrations for AV gear — receivers, TVs, projectors, streamers, HDMI matrices — but it has no concept of how those devices are *interconnected*. Every integration treats its device as a black box exposing a flat `media_player` entity with a `source_list` that the user must manually map to physical reality. There is no model of signal flow, no automatic input switching across multiple devices in a chain, no path resolution, and no way to express "to play Apple TV in the living room, the system must power on the AVR, the video processor, and the TV, set the AVR to HDMI 2, set the processor to HDMI 1, and set the TV to HDMI 1."

Dedicated AV control systems have solved this for decades by modeling the system as a graph of devices with typed interfaces, where connections between those interfaces define signal paths. When a user picks a source for a room, the controller traverses the graph, computes the path, and orchestrates every device in that path automatically.

Media Room Manager brings that capability to Home Assistant — without replacing or fighting the existing ecosystem. It sits *above* existing integrations and orchestrates them.

A core tenet of the project is that the everyday user does not write code, write automations, or curate YAML to make their AV system work. Configuration happens entirely through the integration's panel; orchestration happens entirely through declarative profiles and built-in mechanisms. Profile authoring is YAML for community contributors, but it remains purely declarative — there is no escape hatch into custom Python and no embedded templating language.

## What this is, and what it isn't

**It is:**

- An orchestration layer that models AV systems as graphs of devices and signal connections.
- A virtual `media_player` provider — each defined zone appears as a standard HA media_player entity, fully usable from voice assistants, dashboards, automations, and the Google/Alexa integrations.
- A device profile system describing the physical interfaces of devices, the output groups within those devices, the bindings to underlying HA entities, and the control mechanisms needed to operate them.
- A panel-driven configuration system. The integration ships its own custom Home Assistant panel that handles essentially all configuration. Config flow is used only for the initial integration install.
- A path resolver and command sequencer that translates "play source X in zone Y" into the right ordered sequence of HA service calls against existing integrations.
- A control-pass-through layer: the virtual media_player routes each kind of control to the right underlying device for the currently active path, and surfaces metadata from the active source.
- A discovery and reconciliation system that suggests appropriate profiles based on the user's installed integrations and entities, and surfaces issues through HA's standard repairs framework when the user's environment drifts away from a configured state.

**It is not:**

- A replacement for any existing media_player, remote, or switch integration. It calls them.
- A protocol implementation for AV devices. It does not talk RS-232 to a Marantz or IP to a JVC projector — the existing integrations do, and Media Room Manager orchestrates them.
- A Home Assistant add-on. The orchestration logic is pure Python operating on HA entities; it belongs in-process as an integration. The configuration panel ships as part of the same integration package — there is no separate service to install.
- A YAML-configured integration from the user's perspective. The user's system configuration is built and persisted entirely through the panel. The only YAML in the project is the community profile library, which only contributors edit.
- An integration with code-level escape hatches. There is no "drop a Python file in" mechanism for individual devices, and no embedded templating language for profile values. Devices that cannot be controlled through the integration's declarative mechanisms need their control surface improved at the underlying Home Assistant integration layer first.
- A graphical node-based canvas like Node-RED. The panel uses a structured layout — cards, lists, modals — not a free-form graph editor. A topology visualization view is on the future roadmap but is not the primary configuration surface.
- A signal-flow validator. The integration assumes the user's AV system already works correctly outside Home Assistant; Media Room Manager orchestrates power and inputs but does not verify that signals actually arrive where the graph says they should.

## Core concepts

A note on terminology: this project uses **zone** strictly to mean a Media Room Manager user-facing zone (a defined listening or viewing area in the user's home). The internal sub-domains within a multi-zone AVR or similar device are called **output groups** to avoid overloading "zone." This separation matters: AVR manufacturers call their internal sub-domains "Zone 2" and "Zone 3," but those are device-internal control concepts, not the user's room-level concept. Profiles speak of output groups; the user thinks in zones.

**Device.** A physical unit of AV equipment — a Sony BDP-S5500, a Marantz SR8015, a JVC NX9 projector, a Monoprice Blackbird 8x8 matrix. A device is an instance of a profile, linked to one or more underlying HA entities.

**Interface.** A typed input or output port on a device. Has a direction, a type, and a label. Represents something the user could plug a real cable into.

**Output group.** A device-internal grouping of outputs that share one active input selection. An AVR's "main" zone and "zone 2" are output groups — each has its own input selection, its own outputs, and its own control surface. An HDFury Diva's TX0 and TX1 are output groups — each TX output, with its associated audio extraction outputs, shares one active input. A simple device with no internal grouping has one output group implicitly. A true matrix (where every output independently selects its source) has many output groups, one per output.

**Connection.** A directed edge from an output interface on one device to an input interface on another. Represents a physical cable. Connections are type-checked.

**Transit device.** A device that signal passes through on its way from a source to a sink. Media Room Manager assumes every input on a transit device can route to every output of compatible carrier type within the relevant output group on that device.

**Zone.** A defined listening or viewing area in the user's home. A zone has one or more sink devices and a *sink mode* describing how those sinks behave together. Each zone surfaces in HA as a virtual `media_player` entity. Zones are the user-facing primitives.

**Source.** A device or virtual source designated as a content origin. The path resolver computes routes from physical sources through the connection graph; virtual sources are activated directly on their containing device.

**Virtual source.** A content source that lives inside a device but has no physical input — an AVR's tuner, a streamer's installed apps, a TV's internal apps. May be **static** (declared in the profile, intrinsic to the device model) or **dynamic** (discovered at runtime from the bound entity's `source_list`).

**Profile.** A reusable YAML description of a device model: its physical interfaces, output groups, virtual sources, the bindings to underlying HA entities' capabilities, the discovery signals that help auto-suggest the profile, and any control mechanisms needed.

**Adapter.** Code in the integration that translates an abstract orchestrator operation into a concrete Home Assistant service call. Each adapter implements one of the supported mechanisms; profiles declare which mechanism applies on each output group.

**Control role.** A capability a device can fulfill in an active path: `transport`, `volume`, `metadata_source`, `power`, `source_selection`. When a path is active, the orchestrator assigns each role to the appropriate device in that path.

**Volume authority.** The single device pinned at zone configuration time to handle volume and mute for a given zone. Does not float dynamically with the active source.

## Architecture

Media Room Manager consists of two parts shipped together as a single HACS-installable component:

- A **Python backend** running in the Home Assistant process.
- A **TypeScript frontend panel** registered with Home Assistant via `panel_custom`, accessed from the HA sidebar.

The backend and panel communicate exclusively through Home Assistant's WebSocket API, using commands the integration registers under its domain. The panel never accesses backend state by any other route, and the backend has no panel-specific code paths. This is the pattern used by other panel-shipping integrations such as KNX (which ships [`knx-frontend`](https://github.com/XKNX/knx-frontend) as its UI), Dynalite, LCN, Insteon, and Alarmo.

Inside the backend, the architecture has three categories of components: a layered core orchestration pipeline, several services that interact with that core but aren't part of its dependency stack, and outward-facing interfaces.

### Core orchestration pipeline

These six components form a true dependency stack. Each reads from or builds on the components beneath it.

**1. Graph model.** Pure data. Devices, interfaces, output groups, virtual sources (static and dynamic), connections, zones, source visibility selections, instance bindings, per-instance remaps. Persisted via Home Assistant's `Store` helper. Validated via `voluptuous`.

**2. Profile registry.** Loads bundled profiles shipped with the integration package, optional community profiles fetched from the upstream repository, and user-supplied local profiles from the HA config directory. Profiles are matched to devices by manufacturer + model.

**3. Adapter registry.** A fixed set of mechanism implementations: `media_player_source`, `select_entity`, `switch_combo`, `remote_command`, `service_call`. Each adapter takes an abstract operation and a mechanism declaration from the relevant output group's profile, and emits the appropriate HA service call. Holds no state — pure command translation.

**4. Path resolver.** Reads from the graph model and profile registry. Given (source, zone), computes the ordered list of devices and per-device operations needed to route signal end-to-end. Walks audio and video subgraphs independently. Treats transit devices as transparent within their output group constraints.

**5. Role resolver.** Reads from the graph model and the path resolver's output. For an active path, identifies which device holds each control role. Volume is pinned per zone; transport and metadata_source are determined by the active source.

**6. Orchestrator.** Consumes resolver outputs and uses the adapter registry to issue commands. Issues operations in dependency order, applies configurable inter-step delays, retries on transient failure, surfaces hard failures. Updates the entities subsystem reactively.

### Services

These are subsystems with their own lifecycles that interact with the core but aren't part of its dependency stack.

**State tracker.** Subscribes to state changes on every entity referenced by the active graph. Maintains in-memory `observed` / `commanded` / `unknown` state per device interface. The orchestrator consults it; the virtual media_player entities surface state from it.

**Discovery service.** Runs on demand when the user opens the panel's "Add Device" flow. Scans Home Assistant's integrations, device registry, and entities, scoring candidates against profiles' declared discovery signals via constellation matching. Returns ranked profile suggestions. Also re-evaluates dynamic virtual sources for already-bound entities when those entities' state changes.

**Repair service.** Observes state changes and binding events. Emits issues to Home Assistant's repairs framework when the user's environment drifts from a configured state.

### Outward interfaces

**Entities and HA Device Registry entries.** The integration registers entries in Home Assistant's Device Registry for each Media Room Manager zone and for each orchestrated physical device. Entities live under those device entries.

**WebSocket command surface.** A set of commands registered under the integration's domain. The panel calls these to query and mutate state. Includes a `resolve_path` command for the Looking Glass — pure analysis, returns a structured path resolution for any (zone, source, optional sink) triple without commanding any devices.

### Frontend panel

The panel is a single-page application bundled with the integration's Python package. On integration setup the backend registers it with Home Assistant's panel system, after which it appears in the user's sidebar. The panel runs inside the HA frontend, not as an iframe.

The build pipeline (likely Lit + Vite) produces a minified JS bundle shipped in the Python package.

## The configuration panel

The panel is the primary configuration surface. Config flow does only the initial install acknowledgment; everything else happens here.

### Layout

A tabbed dashboard:

**Devices.** The primary working surface. Each device appears as a card showing its name, profile, bound HA entities, and a summary of its interfaces with their current connections. A modal opens from each card for the full device editor. The "Add Device" flow leads with auto-discovery suggestions before falling back to library search and the ad-hoc wizard.

**Connections.** Connections are edited inline on device cards in the Devices tab — each output interface shows its downstream connection or a "Connect…" affordance; each input shows its upstream source. Selecting a target opens a small modal that filters choices by interface type compatibility. A separate **Connections** overview tab shows all connections as a table.

**Zones.** Zone cards summarize sink devices, sink mode, volume authority, and source count. The zone editor handles sink mode selection, volume authority pinning, source visibility (dual-list selector with three categories — physical, static virtual, dynamic virtual), and per-zone display name overrides for visible sources.

**Profile library.** Searchable browser for the bundled, community, and locally-defined profiles.

**Diagnostics.** Live system state plus the Looking Glass for configuration validation. See [The Looking Glass](#the-looking-glass).

**Settings.** Integration-wide options: opt-in for community profile fetching, log verbosity, default policies for new zones.

### Interaction patterns

The general pattern across all tabs is **cards-with-modals**. Type compatibility is enforced visually. When a profile expects specific values from a bound entity (source-list values, command names, select options) and the user's actual entity has different values, the panel walks the user through a one-time remap.

A free-form node-and-edge canvas is not part of v1.

## The Looking Glass

The Looking Glass is a configuration-validation tool on the Diagnostics tab. It lets the user inspect the resolved video and audio paths for any (zone, source) combination without activating the system. It answers "if I activated this combination, what would happen?" — pure analysis, no commands issued, no devices required to be on.

This is distinct from the live diagnostic cards on the same tab, which show what *is* happening: currently active zones, in-progress orchestration, observed-vs-commanded mismatches. Looking Glass shows intent; live diagnostics show reality.

### Layout

A parent card with a full-width header spanning two path cards beneath it:

**Header.** Three dropdowns:

- **Zone** — picks from the user's defined zones.
- **Source** — populated based on the selected zone's source visibility list (the same set the zone's media_player exposes in its `source_list`). Disabled until a zone is selected.
- **Display** — appears only when the selected zone has more than one sink. For `selectable_exclusive` zones, lists each sink. For `simultaneous` zones, lists each sink plus an "All (simultaneous)" option which is the default. The audio card is unaffected by Display selection.

Changing any selection re-runs path resolution and updates the cards immediately.

**Path cards.** Two cards laid side by side: **Video Path** and **Audio Path**. On narrow viewports (mobile, etc.) the two cards stack vertically so each is read top-to-bottom.

Each card shows the source at top, transit devices in the middle (one per row), and the endpoint at the bottom. Each transit row shows the device, the input interface receiving signal, and the output interface sending it onward. Connections between rows are implicit by adjacency.

For `simultaneous` zones with the "All" option selected, the video card branches at the relevant transit point (typically a distribution amp or matrix), with each branch flowing down to its respective sink.

The audio path always terminates at the zone's volume authority. Equipment downstream of the volume authority — passive amps, speakers, smart-plug-controlled vintage gear — is intentionally not shown because it's outside the integration's scope and not relevant to the user's mental model of "where is volume controlled?"

### What's not shown

Power state is not displayed on devices. The Looking Glass shows configuration logic, and any reasonable user understands that devices need to be on to function. Cluttering the visualization with power badges adds noise without helping.

### Failure modes

If a path can't be resolved — no compatible interface chain, contention with another active path, broken connection — the Looking Glass shows clear diagnostic information at the affected point: "No video path: Apple TV's HDMI output has no connection." or "Path conflicts with active path on Theater zone using TX1 output." The user sees exactly where the chain breaks and why.

For devices with `exclusive_outputs` (Lumagen-class processors, HDFury switchable models), the path display includes a passive note: "Lumagen — output: HDMI A (mutually exclusive — verify external configuration)." This reminds the user that the active output state is their responsibility to manage externally; the Looking Glass shows the path that would work assuming the device is correctly configured.

## Profiles and the device library

Profiles are the durable, shareable artifacts of this project — and the only YAML the user might ever look at, and only if they're contributing to the library.

**Sourcing.** Seed the profile library by parsing existing control-system driver archives. Manufacturer spec sheets are explicitly not relied on.

**Licensing.** Topology data is factual specification information and is extracted freely. Specific control payloads (IR hex codes, vendor IP command strings) are handled separately. Where they exist in open databases, they may be referenced; where they're proprietary, they are not redistributed.

**Ad-hoc profiles.** First-class. The panel includes a "device not in library" wizard. The resulting profile is saved locally and behaves identically to library profiles. A submit-from-UI flow opens a pre-filled PR for upstreaming.

**Profile versioning and overrides.** Profiles carry a semantic version. User systems pin to a version per device; updates are opt-in. Local user profiles take precedence over fetched community profiles, which take precedence over bundled profiles.

**Converter library.** Passive media converters ship as ordinary YAML profiles using the same schema with `category: passive_converter` and no output group selection mechanisms.

**No templating.** Profile values are static. Where a value depends on runtime data (a service-call parameter that takes the operation's input value), a fixed sentinel like `$value` marks the slot. There is no Jinja2, no expression evaluation, no `{name}` substitution. Every value is verifiable at profile load time.

## Interface types and connections

Interfaces are the typed ports on devices. Each has:

- A **direction**: `output` or `input`.
- A **type**: one of the eight types listed below.
- A **label**: typically the manufacturer's name for it.

The type implies the carriers (audio, video) — there is no separate `carries` field on interfaces.

### Interface type taxonomy

| Type | Carries | Notes |
|---|---|---|
| `hdmi` | audio, video | Standard HDMI. |
| `hdmi_audio_return` | audio, video | HDMI link with ARC/eARC. ARC and eARC are not distinguished. |
| `optical_audio` | audio | TOSLINK, S/PDIF over fiber. |
| `coax_audio` | audio | S/PDIF over coax. |
| `rca_audio` | audio | Unbalanced analog audio. |
| `xlr_audio` | audio | Balanced analog audio. |
| `component_video` | video | YPbPr. |
| `composite_video` | video | RCA composite. |

Control channels (`ir_emitter`, `ip_control`, `rs232`) are not represented as interfaces.

### Bidirectional interfaces (audio return)

`hdmi_audio_return` interfaces carry video forward (in the declared direction) and audio in the reverse direction. The user defines the interface with a single direction and wires a single connection. The path resolver internally treats the interface as having a hidden complementary direction for audio carriers. This is the only special-cased bidirectionality in v1.

### Type compatibility for connections

Connections are type-checked. Cross-type connections are not permitted. Where users have devices that perform passive signal conversion, they instantiate a passive converter device from the bundled library.

## Output groups

An output group is a device-internal grouping of outputs that share one active input selection. The model accommodates the full range of device behaviors with a single uniform vocabulary:

- **A simple source device** (Apple TV, Blu-ray) has one output group containing its single output. Selecting an "input" doesn't apply because there are no inputs to switch among.
- **A single-zone AVR** has one output group containing all its physical outputs (HDMI main, optical out, etc.). All outputs share whichever input is currently active.
- **A multi-zone AVR** (Marantz SR8015, Anthem MRX 740) has multiple output groups (`main`, `zone_2`), each with its own active input selection. The `main` output group typically contains the HDMI main output and any parallel HDMI outputs. The `zone_2` output group contains the zone 2 HDMI output and any zone 2 pre-outs.
- **A device like the HDFury Diva** has multiple output groups (`tx0`, `tx1`), each containing a primary HDMI output plus any audio extraction outputs (HDMI extraction, optical, RCA breakouts). All outputs in the `tx0` group share the same active input.
- **A true matrix** (Monoprice Blackbird) has every output in its own output group of size 1. Each output independently selects its source.
- **A passive transit device** (HDMI splitter, distribution amp) has one output group containing all outputs but declares no selection mechanism — every output is always carrying the active signal.

### Profile structure for output groups

Each output group declares:

- An **id** used to reference it from interface declarations.
- A **selection_mechanism** describing how to switch the active input on this group, including the mechanism kind (`media_player_source`, `select_entity`, etc.) and the capability expectations for the entity that will be bound to it.

Output interfaces declare their **output_group** by id. Input interfaces declare which output groups they're routable to via **routable_to_output_group**.

For multi-output-group devices where the active input must be exclusive within each group (single-input-active behavior), the profile declares **inputs_are_exclusive_per_output_group** with the list of group ids that have this constraint. The contention model uses this for input-side conflict detection.

For devices whose outputs are mutually exclusive (Lumagen-class, HDFury switchable models — only one output is in correct use at a time even though signal may be present on others), the profile declares **exclusive_outputs: true** at the device level. The integration tracks which output is in use for contention purposes but does not command the device to change it — that's the user's responsibility to manage externally.

Auxiliary entities not tied to an output group (a separate power switch on a matrix, a discrete remote on a non-media_player device) are declared in **aux_entities** with their own capability expectations.

### Contention

Two flavors of contention exist:

**Input-side contention.** A path needs to switch the active input on an output group, but another zone is currently using a different input on the same group. Detected for output groups listed in `inputs_are_exclusive_per_output_group`.

**Output-side contention.** A path needs an output that's already routed to a different source. Detected for matrix-style devices (with `output_selection` per output) and for devices with `exclusive_outputs: true`.

Both flavors apply the requesting Media Room Manager zone's contention policy: `deny` (default) or `preempt` (tear down conflicting paths). A `share` policy is planned for v1.x for cases where outputs are already broadcasting compatibly.

## Virtual sources: static and dynamic

Many devices have content sources that don't correspond to a physical input. These are modeled as **virtual sources** on the device, separately from physical interfaces. The path resolver activates virtual sources directly on the containing device rather than walking the connection graph.

### Static virtual sources

Sources intrinsic to the device model, well-known at profile-authoring time — an AVR's built-in tuner, a CD player's transport, a DVR's cable input. These are enumerated in the profile.

### Dynamic virtual sources

Sources the device exposes through its underlying entity at runtime, discovered by reading the bound entity's `source_list` and subtracting the values already mapped to physical interfaces and static virtual sources. The remainder is dynamic content — typically apps on a streamer or smart TV.

For a Roku or Apple TV, this surfaces installed apps. When a new app is installed, the entity reports the updated source_list, the discovery service picks it up, and it appears in the candidate pool. When an app is uninstalled, the discovery service detects the disappearance; if the app was previously enabled in any zone's visible source list, the repair service triggers a repair.

For multi-output-group devices, dynamic sources hang off the specific output group whose entity exposes them.

## Control mechanisms

The integration ships a fixed set of adapter mechanisms. The mechanism set extends only by adding new adapters to the integration itself.

The intended boundary: if a device has *any* working Home Assistant integration that exposes services or entities, one of the mechanisms below handles it. Devices without HA integration support need that solved at the integration layer first.

**`media_player_source`** — The bound entity is a `media_player` and the input corresponds to a value in its `source_list`. **Preferred for AVRs, TVs, streamers, and any device with a clean media_player surface.** Implicit default for `media_player`-bound output groups.

**`select_entity`** — The bound entity is a `select` entity, with one option per available input. **Preferred for HDMI matrices and video processors when the underlying integration exposes one `select` per output.**

**`switch_combo`** — For matrices exposed as a grid of switch entities (one per output × input pair).

**`remote_command`** — The bound entity is a `remote`. Selecting an input or invoking an operation sends a configured command name. Covers IR-controlled gear and discrete-code IP devices.

**`service_call`** — Arbitrary HA service call with statically-enumerated parameters. The catch-all that composes with any HA integration exposing services. Used when none of the above mechanisms apply.

For runtime-determined parameter values (volume level being set, etc.), profiles use the `$value` sentinel — a fixed marker the orchestrator substitutes at execution time. No expression evaluation; just a designated slot.

## Profile content: what's declared, what's inferred

A profile is a complete control recipe. The user, when instantiating a profile, provides only the runtime bindings — typically one entity per output group and one entity per auxiliary entity declared.

How much a profile declares depends on how well the device is modeled in Home Assistant.

### Output-group-driven structure

Profile content centers on output groups:

- The profile declares each output group with its selection mechanism and capability expectations.
- Outputs declare which output group they belong to.
- Inputs declare which output groups they're routable to. The default value passed when selecting an input is the input's `label`; if the user's entity has different `source_list` values, the per-instance remap UI handles it.
- Control roles are declared per output group (which roles each group provides).
- For devices whose primary entities are `media_player` types, capability declarations point at standard `media_player.*` services based on the bound entity's `supported_features`. Most operation-level service-call mappings are implicit.
- For devices not controlled via `media_player` entities (IR-only Blu-ray players, HDMI matrices with `select` entities, REST-controlled gear), the profile declares the mechanism, operation-to-service-call mappings, and any per-input-or-per-output specifics explicitly.

### What the user provides

For any profile, the user provides:

1. **Entity bindings.** One entity per output group, plus one per auxiliary entity. The panel filters candidates by the declared expectations.
2. **Per-instance label remaps**, only when the bound entity's source-list / command names / select options differ from the profile's defaults.

The user does not pick mechanisms, write service calls, specify parameters, or edit profiles.

## Entity binding and capability matching

The integration binds device profiles to underlying HA entities through Home Assistant's **entity registry**, not through entity_id strings. The integration stores entity registry IDs (UUIDs); the user can rename entities later in HA without breaking Media Room Manager.

Each output group and auxiliary entity declares its expected capabilities. The panel filters candidate entities by these expectations. When no entity matches, the user gets a clear message naming exactly what's missing. When an entity is the right kind but its source-list / commands / options don't match, the panel offers a remap UI; the remap is stored on the device instance, not in the profile.

Profiles assert canonical defaults; instances remap when reality differs.

## Auto-discovery and repairs

### Auto-discovery

When the user opens the panel's "Add Device" flow, the discovery service scans Home Assistant's entity registry and device registry and suggests appropriate profiles. Suggestions are confidence-ranked and the user always confirms — there is no automatic instantiation.

The `discovery` block is optional at the top level of a profile. Profiles without a `discovery` block aren't auto-suggested; users find them through library search and the ad-hoc wizard.

Discovery operates in two stages: an **anchor match** against any entity in HA to identify the device and profile, followed by **sibling matching** that walks the HA device registry for additional entities to bind to the profile's remaining output groups.

#### Stage 1: anchor matching

The discovery service iterates the HA entity registry, scoring each entity against each profile's anchor signals. The output group flagged with `is_discovery_anchor: true` is the anchor; its signals and its own `match_threshold` are used for this stage. Signals are weighted; the service sums matched weights and applies the threshold. Entities scoring above the threshold are anchor candidates.

#### Stage 2: sibling matching

For each anchor candidate, the discovery service looks up its HA device registry `device_id` and retrieves sibling entities under the same device (including disabled entities, via `async_entries_for_device(ent_reg, device_id, include_disabled_entities=True)`). For each other output group entry in the discovery block, the service scores the sibling entities against that entry's signals and applies that entry's own `match_threshold`. The best-matching sibling is bound — or, when no sibling meets the threshold and the entry is marked `optional`, the output group is left unbound.

Disabled-by-default zone entities (such as the zone 2 entity for some AVR integrations) are still considered as sibling candidates. When discovery binds a disabled entity to an output group, the suggestion notes the disabled state so the user can enable it in their integration's settings before confirming.

When no sibling matches a required output group, the suggestion is still presented but flagged: "Zone 2 entity not found — please bind manually." User assignment is the always-available fallback.

Anchor matching benefits from a higher `match_threshold` than sibling matching: anchoring identifies the device from scratch across all entities in HA, while sibling matching chooses among a small set of entities already constrained to one device. Per-output-group thresholds let profiles tune each stage appropriately.

#### Schema

```yaml
discovery:
  output_groups:
    - output_group: main
      is_discovery_anchor: true
      match_threshold: 60
      signals:
        - kind: device_registry
          manufacturer: "Apple"
          model_patterns: ["Apple TV*"]
          weight: 100
        - kind: platform
          domain: apple_tv
          weight: 100
        - kind: supported_features
          values: [450487, 449463]
          weight: 20
        - kind: source_list_signature
          includes_any: ["TV", "Computers", "Music"]
          weight: 10
        - kind: friendly_name
          friendly_name_patterns: ["Apple TV"]
          weight: 10
        - kind: device_class
          matches: ["tv"]
          weight: 10
        - kind: sound_mode_list_signature
          matches: ["STEREO", "DOLBY_PLII_IIx_MOVIE", "DOLBY_PLII_IIx_MUSIC",
                    "DOLBY_PLII_IIx_GAME", "DOLBY_PL", "DTS_NEO_6_CINEMA",
                    "DTS_NEO_6_MUSIC", "MCH_STEREO"]
          weight: 50
        - kind: attribute_constellation
          includes: ["source_list", "media_content_id", "media_duration",
                     "media_position", "media_position_updated_at", "media_title",
                     "media_artist", "app_id", "app_name", "entity_picture",
                     "friendly_name", "supported_features"]
          weight: 50

    - output_group: zone_2
      match_threshold: 60
      optional: true
      signals:
        - kind: supported_features
          values: [135052]
          weight: 50
        - kind: source_list_signature
          includes: ["FOLLOW_ZONE_1"]
          weight: 50
        - kind: attribute_constellation
          includes: ["source_list", "supported_features"]
          weight: 30
```

Exactly one output group entry must be flagged `is_discovery_anchor: true`. For single-output-group profiles (Apple TV, Blu-ray players, etc.), the one output group entry carries the anchor flag and the `output_groups` list has just one item.

#### Signal kinds

- **`device_registry`** — manufacturer and model match against the device registry entry the entity belongs to. Read from HA's device registry, not from entity state. Strong; definitive when populated.
- **`platform`** — entity registry entry's `platform` field matches the listed `domain`. Read from HA's entity registry, not from entity state. Strong for integrations that uniquely cover one device class (e.g., `kodi`, `apple_tv`); medium for integrations covering many models (e.g., `denonavr`).
- **`supported_features`** — entity's `supported_features` bitmask is in the listed `values`. Multiple values accommodate drift across HA versions. Weak corroboration on its own; strong when combined with `device_registry`.
- **`source_list_signature`** — entity's `source_list` matches with `includes_any` (at least one listed value present), `includes` (all listed values present), or `matches` (exact set match). Medium corroboration.
- **`sound_mode_list_signature`** — entity's `sound_mode_list` matches with the same operators as `source_list_signature`. Medium corroboration. Strongly distinguishing for AVRs and surround processors since most other media_players don't have this attribute.
- **`device_class`** — entity's `device_class` is in the listed values. Weak corroboration; stable across user customization.
- **`friendly_name`** — entity's `friendly_name` matches one of `friendly_name_patterns`. Weak signal — friendly names are user-controllable. Useful when integrations populate sensible defaults that users commonly leave alone (a Denon AVR's default friendly name often matches the model number); not useful when friendly names are user-supplied from configuration (Kodi instance names).
- **`attribute_constellation`** — entity's set of available attribute keys (presence, not values) contains all keys in `includes`. Medium corroboration. Particularly useful for distinguishing entity types within the same integration — for example, an AVR's main zone has a `sound_mode_list` attribute while zone 2 doesn't, making the constellation a clean discriminator even though both entities share the same platform.

The discovery service adds matched signals' weights and applies each output group's `match_threshold`. When two profiles match similarly well, both are surfaced and the user picks. Confidence score is shown in the UI.

For multi-output-group devices, when a user picks an auto-suggested AVR, the panel pre-fills bindings for each output group whose sibling match was confident.

#### Implementation notes

- Discovery scoring reads from HA's entity registry (`platform`, `device_id`, registered `capabilities`) and device registry (`manufacturer`, `model`) where possible, falling back to entity state attributes (`source_list`, `sound_mode_list`, `device_class`, `friendly_name`) for fields not in the registry. The `device_registry` and `platform` signals are registry-backed and stable; the rest read from state.

- The integration uses `async_entries_for_device(ent_reg, device_id, include_disabled_entities=True)` for sibling retrieval so disabled entities remain visible to discovery.

- Discovery returns a ranked list of suggestions whose anchor scored above their respective `match_threshold`. The Add Device UI presents all candidates ordered by score; the user picks. Discovery never silently auto-instantiates.

- Multi-binding suggestions render as a single device with pre-filled bindings for each matched output group. The user can override any individual binding before confirming. When an additional output group could not be matched, the suggestion shows that slot as unbound with a "Bind manually" affordance.

- Profile-side discovery hints captured during the ad-hoc device wizard are baked into locally-saved profiles so they benefit from auto-discovery on the same user's system thereafter.

### Repairs

Home Assistant has a standard repairs framework for issues an integration detects that need user attention. Media Room Manager surfaces these cases as repairs:

**Disappeared dynamic source.** A previously-enabled dynamic source is no longer reported by the bound entity. The user dismisses to acknowledge or investigates if unexpected.

**Source-list expectations broken.** A bound entity's `source_list` no longer matches the profile's expectations or the user's previous remap. The repair walks the user through a fresh remap.

**Path no longer resolves.** A previously-routable source is now unreachable. The repair surfaces what changed.

**Bound entity removed.** The user removed the underlying integration or the entity. The repair offers rebinding or device removal.

Newly discovered dynamic sources are **not** repairs — they're surfaced as a passive panel indication on affected zones.

## Control roles and the virtual media_player

Roles in v1:

- **`transport`** — play, pause, stop, next_track, previous_track, seek. Held by the active source device. Dynamic.
- **`volume`** — set volume, volume up/down, mute. Pinned at zone configuration time to one specific device.
- **`metadata_source`** — supplies media_title, media_artist, media_album_name, media_image_url, media_duration, media_position. Held by the active source. Dynamic.
- **`power`** — handled at the orchestrator level rather than delegated.
- **`source_selection`** — handled at the zone level.

For each output group, the profile declares which control roles that group provides. Most multi-zone AVRs declare all of `power`, `volume`, `source_selection`, and `metadata_source` per output group, since each zone of the AVR has its own control surface.

### Volume authority is pinned, not floating

Letting volume float to whichever device happens to be in the path produces unpredictable behavior. Media Room Manager constrains the `volume` role to a single device per zone, designated explicitly at zone setup. Source devices are not asked to adjust their volume during orchestration.

For zones whose sink is an AVR's secondary output group (e.g., zone 2 RCA pre-outs feeding a passive amp), the volume authority is the AVR (specifically that output group's bound entity), and the path terminates at that output.

### Static supported_features

The virtual media_player declares its supported features statically at zone configuration time. The feature set is the union of features any device that could hold a role in any path through this zone supports. Stable through source switches.

When the active source doesn't support a feature the zone advertises, the corresponding command no-ops gracefully.

### Metadata pass-through

The virtual media_player subscribes to state changes on the entity holding the `metadata_source` role. When the active source changes, the subscription moves to the new source's entity.

## Zone sink modes

A zone has one or more sink devices and a sink mode:

**`single`** — exactly one sink.

**`simultaneous`** — multiple sinks, all active together. Use cases: sports-bar setups, commercial signage, kitchens with primary + secondary displays.

**`selectable_exclusive`** — multiple sinks that are mutually exclusive. Use case: a media room with both a TV and a projector. The integration creates helper `select` and per-sink `switch` entities for the choice.

A zone with sink mode `selectable_exclusive` may have a configured *default sink* used when the zone is activated without an explicit choice.

## Source visibility

After devices are configured, the integration assembles a candidate source pool for each zone by walking the graph and discovery state. The pool contains three categories: physical sources, static virtual sources, and dynamic virtual sources.

The user is presented one screen per zone — a dual-list selector with "available sources" on the left and "visible in source_list" on the right. Items in the right list become the zone media_player's `source_list`. Items can be renamed inline.

The default for a freshly-configured system is **everything hidden**. The user explicitly opts apps and devices into visibility.

When the same logical content exists on multiple devices (Netflix on both an Apple TV and a Shield), each appears as a distinct item. The user enables whichever they prefer, or both with different display names.

When the active source is a virtual source, the orchestrator routes the path to the source's containing device and selects the virtual source on it.

## Entities, devices, and automation triggers

The integration registers entries in Home Assistant's Device Registry for each Media Room Manager zone and for each orchestrated physical device.

### Per zone

- **`media_player.<zone>`** — the primary entity. State changes are the main automation trigger surface.
- **`select.<zone>_display`** (only for `selectable_exclusive` zones) — chooses the active sink.
- **`switch.<zone>_<sink>`** (only for `selectable_exclusive` zones) — toggles per-sink. Toggling one on turns the others off.

### Per orchestrated physical device

- **`binary_sensor.<device>_in_use`** — `on` when the device is part of any currently-active path. **Only created for devices reachable from more than one zone.** For a device used by exactly one zone, the zone media_player's state already conveys the same information.

### Error reporting

Path resolution failures and orchestration errors surface on the zone media_player as `state: unavailable` with `attributes.error_detail` carrying a description.

### No custom events

All automation triggers happen via standard Home Assistant state-change triggers on these entities. Exposing state through entities makes every trigger surface available to ordinary users building automations through the UI; custom integration events are a power-user surface accessible only by typing event names as strings.

### Example automations

- *"Turn on basement amp smart plug when Primary Bedroom zone is active"* → trigger on `media_player.primary_bedroom` state changing to a non-`off` value.
- *"Lower projector screen when theater zone selects projector"* → trigger on `select.theater_display` becoming `Projector`.
- *"Turn on AVR cooling fan when AVR is in use by any zone"* → trigger on `binary_sensor.living_room_avr_in_use` becoming `on`.
- *"Notify me on AV system errors"* → trigger on any `media_player.*_zone` becoming `unavailable`.

## State tracking

The state tracker subscribes to state changes on every entity referenced by the active graph. Three classes of state are tracked:

**Observed.** The underlying entity reports the value reliably. Used directly.
**Commanded.** The integration last issued a command but the device doesn't report back. Fallback.
**Unknown.** No reporting, no recent command, or device offline.

External state changes — someone hits the AVR remote and changes the source — flow through this same mechanism. The zone's reported source updates within seconds.

## Power management

Power behavior is declared in the profile via two fields: `power_handling` and `power_on_delay`.

### `power_handling`

Declares how the integration manages this device's power. One of:

- **`discrete_capable`** — the device supports separate power-on and power-off commands (typical for IP-controlled devices and modern IR codes with discrete on/off codes). The integration powers the device on when needed and off when no longer needed by any zone.

- **`toggle`** — the device only supports a single power-toggle command (common for older IR-controlled devices). The integration uses observed state to decide whether to send the toggle, falling back to commanded state when observed state isn't reliable.

- **`always_on`** — the integration never powers this device off. Useful for devices with long boot cycles or that are shared across many frequently-used zones. The device is assumed to be on; no power commands are issued.

- **`disabled`** — the integration does not manage this device's power at all. The user manages it externally (smart plug automation, manual control, etc.). No power commands are issued in either direction.

### `power_on_delay`

Number of seconds to wait after issuing power-on before sending further commands to the device. Some devices ignore input-selection or transport commands during their boot cycle. Defaults to `0` if omitted.

Ignored when `power_handling` is `always_on` or `disabled`.

### Examples

A networked AVR with discrete on/off and a moderate boot time:

```yaml
power_handling: discrete_capable
power_on_delay: 4
```

An older IR-controlled DVD player:

```yaml
power_handling: toggle
power_on_delay: 6
```

A media streamer the user wants to keep always on:

```yaml
power_handling: always_on
```

A passive converter or a device with no controllable power:

```yaml
power_handling: disabled
```

### Per-instance overrides

The user can override `power_handling` for their specific device instance through the panel. The most common case is changing a `discrete_capable` profile to `always_on` for a device they don't want auto-powered.

The integration does not auto-flatten or override per-device settings on activation. Volume, brightness, picture mode, and similar settings on source devices are left as the user configured them.

## Path resolution and orchestration

The path resolver walks the connection graph from a source to each sink in a zone. Audio and video paths are resolved independently. Transit devices are treated as transparent within the constraints of their output groups.

For physical sources, the resolver:

1. Builds a subgraph for each carrier kind (audio, video) needed.
2. Performs a shortest-path search from the source to each sink. BFS is sufficient for v1.
3. For `hdmi_audio_return` interfaces, includes the implicit reverse-direction audio edge.
4. Returns the ordered list of (device, output group, input interface, output interface) tuples for each path.
5. Deduplicates shared transit devices for multi-sink zones.
6. Checks for input-side and output-side contention against any currently-active paths.

For virtual sources, the "path" is the device itself plus virtual-source selection on it.

The orchestrator translates the resolved plan into commands:

1. Power on every device in any active path that isn't already on, in dependency order.
2. From each sink toward the source, set each transit device's input via the relevant output group's selection mechanism. Shared transit devices are configured once.
3. If the active source is a virtual source, select it on its containing device.
4. Resolve roles for the active path.
5. Issue a transport command at the source when applicable.
6. Update the virtual media_player's state and metadata subscription.

**Failure handling.** Hard failure surfaces on the zone media_player via `state: unavailable` and `attributes.error_detail`.

**Contention.** Per-zone policy: `deny` (default) or `preempt`. Configurable per zone. The `share` policy is planned for v1.x for cases where outputs are already broadcasting compatibly.

## Storage and data layout

**The user's system configuration.** Devices, connections, zones, source visibility selections, instance bindings (entity registry IDs), per-instance remaps. Persisted via `Store` at `<config>/.storage/media_room_manager.system`. Backed up automatically by HA snapshots.

**Profiles.** Three layers, with precedence local > community-fetched > bundled.
- Bundled profiles ship with the integration package (read-only).
- Community-fetched profiles cache to `<config>/media_room_manager/profiles_cache/`.
- User local profiles live in `<config>/media_room_manager/profiles/`.

**Runtime/volatile state.** Active paths, observed device states, role assignments, dynamic virtual source candidate pools. In-memory only. The user's *visibility selections* over dynamic sources are persisted; the underlying source availability is rediscovered.

The WebSocket API stays stable across versions to support both the panel and any third-party scripting.

## Operational expectations

Media Room Manager orchestrates an AV system. It does not validate signal flow, fix wiring problems, or diagnose hardware faults. Three boundaries are worth being explicit about:

**The AV system must work outside Home Assistant first.** Users must verify that their AV system works correctly when operated manually before configuring Media Room Manager. The integration issues commands it believes correct based on the graph and reports success based on commanded state; the user diagnoses any gap between commanded and actual signal flow.

**Each device must be controllable through Home Assistant first.** Media Room Manager orchestrates devices that Home Assistant already controls. If a device has no working HA integration — or its HA integration doesn't expose the services Media Room Manager needs — that's the layer that needs to grow first. The integration intentionally does not provide a Python escape hatch for individual devices.

**Equipment downstream of designated zone sinks is user-managed.** A zone whose sink is an AVR's zone 2 output terminates there. The passive amp it feeds, the speakers, smart plugs powering vintage gear, motorized projector screens, room lighting, and similar are user-managed via standard Home Assistant automations triggered off Media Room Manager's entity state changes.

## Example profile YAML

The community profile library is the only place YAML is user-visible. The schema below is illustrative; the formal schema will be documented in the profile repo.

### A simple source (Apple TV)

One output group, one output, dynamic virtual sources for installed apps.

```yaml
profile_id: apple/apple-tv-4k
schema_version: 1
manufacturer: Apple
model: Apple TV 4K
category: source
power_handling: discrete_capable

output_groups:
  - id: main
    selection_mechanism:
      kind: media_player_source
      expected_domain: media_player
      expected_features:
        - turn_on
        - turn_off
        - select_source
        - play_media
        - media_play
        - media_pause
        - media_stop
        - media_next_track
        - media_previous_track
    provides_roles: [transport, metadata_source, source_selection]

interfaces:
  - id: hdmi_out
    direction: output
    type: hdmi
    label: "HDMI OUT"
    output_group: main
  - id: toslink_out
    direction: output
    type: optical_audio
    label: "Toslink OUT"
    output_group: main

dynamic_virtual_sources:
  source: source_list_minus_known
  output_group: main
  exclude:
    - "Settings"
    - "Search"
    - "App Store"
    - "Photos"

discovery:
  output_groups:
    - output_group: main
      is_discovery_anchor: true
      match_threshold: 60
      signals:
        - kind: platform
          domain: apple_tv
          weight: 100
        - kind: supported_features
          values: [450487]
          weight: 20
        - kind: source_list_signature
          includes_any: ["TV", "Computers", "Music", "App Store", "Arcade",
                         "Movies", "Photos", "Podcasts", "Search", "Settings"]
          weight: 50
        - kind: attribute_constellation
          includes: ["source_list", "media_content_id", "media_duration",
                     "media_position", "media_position_updated_at", "media_title",
                     "media_artist", "app_id", "app_name", "entity_picture",
                     "friendly_name", "supported_features"]
          weight: 50
```

### A multi-zone AVR (Marantz SR8015)

Two output groups, each with its own media_player binding. Inputs declare which groups they route to.

```yaml
profile_id: marantz/sr8015
schema_version: 1
manufacturer: Marantz
model: SR8015
category: avr
power_handling: discrete_capable
power_on_delay: 4

output_groups:
  - id: main
    selection_mechanism:
      kind: media_player_source
      expected_domain: media_player
      expected_features:
        - turn_on
        - turn_off
        - select_source
        - volume_set
        - volume_mute
    provides_roles: [power, volume, source_selection, metadata_source]

  - id: zone_2
    selection_mechanism:
      kind: media_player_source
      expected_domain: media_player
      expected_features:
        - turn_on
        - turn_off
        - select_source
        - volume_set
        - volume_mute
    provides_roles: [power, volume, source_selection, metadata_source]

inputs_are_exclusive_per_output_group: [main, zone_2]

interfaces:
  - id: hdmi_1
    direction: input
    type: hdmi
    label: "CBL/SAT"
    routable_to_output_group: [main, zone_2]

  - id: hdmi_2
    direction: input
    type: hdmi
    label: "DVD"
    routable_to_output_group: [main, zone_2]

  - id: hdmi_3
    direction: input
    type: hdmi
    label: "Blu-ray"
    routable_to_output_group: [main, zone_2]

  - id: hdmi_4
    direction: input
    type: hdmi
    label: "Game"
    routable_to_output_group: [main, zone_2]

  - id: hdmi_5
    direction: input
    type: hdmi
    label: "Media Player"
    routable_to_output_group: [main, zone_2]

  - id: hdmi_6
    direction: input
    type: hdmi
    label: "CD"
    routable_to_output_group: [main, zone_2]

  - id: hdmi_7
    direction: input
    type: hdmi
    label: "AUX1"
    routable_to_output_group: [main, zone_2]

  - id: hdmi_8
    direction: input
    type: hdmi
    label: "AUX2"
    routable_to_output_group: [main, zone_2]

  - id: optical_in_1
    direction: input
    type: optical_audio
    label: "OPTICAL 1"
    routable_to_output_group: [main, zone_2]

  - id: optical_in_2
    direction: input
    type: optical_audio
    label: "OPTICAL 2"
    routable_to_output_group: [main, zone_2]

  - id: coax_in_1
    direction: input
    type: coax_audio
    label: "COAX 1"
    routable_to_output_group: [main, zone_2]

  - id: coax_in_2
    direction: input
    type: coax_audio
    label: "COAX 2"
    routable_to_output_group: [main, zone_2]

  - id: phono_in
    direction: input
    type: rca_audio
    label: "Phono"
    routable_to_output_group: [main]

  - id: hdmi_main_out_1
    direction: output
    type: hdmi_audio_return
    label: "HDMI MONITOR OUT 1"
    output_group: main

  - id: hdmi_main_out_2
    direction: output
    type: hdmi_audio_return
    label: "HDMI MONITOR OUT 2"
    output_group: main

  - id: zone_2_hdmi_out
    direction: output
    type: hdmi
    label: "ZONE 2 HDMI OUT"
    output_group: zone_2

  - id: zone_2_rca_out
    direction: output
    type: rca_audio
    label: "ZONE 2 PRE-OUT"
    output_group: zone_2

virtual_sources:
  - id: tuner
    label: "Tuner"
    routable_to_output_group: [main, zone_2]

dynamic_virtual_sources:
  source: source_list_minus_known
  output_group: main
  exclude:
    - "Internet Radio"

discovery:
  output_groups:
    - output_group: main
      is_discovery_anchor: true
      match_threshold: 60
      signals:
        - kind: device_registry
          manufacturer: "Marantz"
          model_patterns: ["SR8015", "*SR8015*"]
          weight: 100
        - kind: platform
          domain: denonavr
          weight: 40
        - kind: source_list_signature
          includes_any: ["CBL/SAT", "Blu-ray", "Phono", "Media Player"]
          weight: 30
        - kind: sound_mode_list_signature
          includes_any: ["STEREO", "DOLBY DIGITAL", "DTS SURROUND", "MULTI CH STEREO"]
          weight: 50
        - kind: attribute_constellation
          includes: ["source_list", "sound_mode_list", "supported_features"]
          weight: 50

    - output_group: zone_2
      match_threshold: 50
      optional: true
      signals:
        - kind: platform
          domain: denonavr
          weight: 40
        - kind: attribute_constellation
          includes: ["source_list", "supported_features"]
          weight: 30
```

### A multi-zone AVR with parallel HDMI outputs (Anthem MRX 740)

Three HDMI outputs: main, parallel (mirroring main), and zone 2. Plus zone 2 RCA pre-outs.

```yaml
profile_id: anthem/mrx-740
schema_version: 1
manufacturer: Anthem
model: MRX 740
category: avr
power_handling: discrete_capable
power_on_delay: 5

output_groups:
  - id: main
    selection_mechanism:
      kind: media_player_source
      expected_domain: media_player
      expected_features: [turn_on, turn_off, select_source, volume_set, volume_mute]
    provides_roles: [power, volume, source_selection, metadata_source]
  - id: zone_2
    selection_mechanism:
      kind: media_player_source
      expected_domain: media_player
      expected_features: [turn_on, turn_off, select_source, volume_set, volume_mute]
    provides_roles: [power, volume, source_selection, metadata_source]

inputs_are_exclusive_per_output_group: [main, zone_2]

interfaces:
  # ...inputs as appropriate, routable_to_output_group: [main, zone_2] for those routable to both...

  - id: hdmi_main_out
    direction: output
    type: hdmi_audio_return
    label: "HDMI MAIN"
    output_group: main

  - id: hdmi_parallel_out
    direction: output
    type: hdmi_audio_return
    label: "HDMI PARALLEL"
    output_group: main   # same signal as main; both belong to main

  - id: hdmi_zone_2_out
    direction: output
    type: hdmi
    label: "HDMI ZONE 2"
    output_group: zone_2

  - id: zone_2_rca_pre_out
    direction: output
    type: rca_audio
    label: "ZONE 2 PRE-OUT"
    output_group: zone_2

discovery:
  output_groups:
    - output_group: main
      is_discovery_anchor: true
      match_threshold: 60
      signals:
        - kind: device_registry
          manufacturer: "Anthem"
          model_patterns: ["MRX 740"]
          weight: 100
        - kind: attribute_constellation
          includes: ["source_list", "sound_mode_list", "supported_features"]
          weight: 50

    - output_group: zone_2
      match_threshold: 50
      optional: true
      signals:
        - kind: attribute_constellation
          includes: ["source_list", "supported_features"]
          weight: 30
```

The main and parallel HDMI outputs both belong to `main` — both carry whatever's on the main zone simultaneously. A user can put both in a `simultaneous` Media Room Manager zone (driving two TVs from the AVR's parallel outputs) or in different zones if they happen to have separate displays driven by each.

### An IR-controlled DVD player (Sony DVP-NS500V)

Single output group, no input selection needed (no inputs to switch among). Mechanism declarations are explicit because the device isn't controlled via `media_player`. The Sony uses a single POWER toggle command rather than discrete on/off codes.

```yaml
profile_id: sony/dvp-ns500v
schema_version: 1
manufacturer: Sony
model: DVP-NS500V
category: source
power_handling: toggle
power_on_delay: 4

output_groups:
  - id: main
    # No selection_mechanism — this is a source device with one
    # output group and no inputs to switch among.
    aux_entity: ir_blaster
    provides_roles: [power, transport]
    role_operations:
      power:
        kind: remote_command
        operations:
          power_on:  { command: "POWER" }
          power_off: { command: "POWER" }
      transport:
        kind: remote_command
        operations:
          play:     { command: "PLAY" }
          pause:    { command: "PAUSE" }
          stop:     { command: "STOP" }
          next:     { command: "NEXT" }
          previous: { command: "PREV" }

aux_entities:
  - id: ir_blaster
    expected_domain: remote
    expected_commands: ["POWER", "PLAY", "PAUSE", "STOP", "NEXT", "PREV"]

interfaces:
  - id: composite_video_out
    direction: output
    type: composite_video
    label: "VIDEO OUT"
    output_group: main

  - id: rca_audio_out
    direction: output
    type: rca_audio
    label: "AUDIO OUT"
    output_group: main

  - id: coax_audio_out
    direction: output
    type: coax_audio
    label: "COAX DIGITAL OUT"
    output_group: main
```

### An HDMI matrix exposed as one `select` per output (Monoprice Blackbird 8x8)

True matrix: each output is independently switchable, so each is its own output group of size 1.

```yaml
profile_id: monoprice/blackbird-8x8
schema_version: 1
manufacturer: Monoprice
model: Blackbird 8x8 (24179)
category: matrix
power_handling: discrete_capable

output_groups:
  - id: out_1
    selection_mechanism:
      kind: select_entity
      expected_domain: select
      expected_options: ["Input 1", "Input 2", "Input 3", "Input 4", "Input 5", "Input 6", "Input 7", "Input 8"]
  - id: out_2
    selection_mechanism:
      kind: select_entity
      expected_domain: select
      expected_options: ["Input 1", "Input 2", "Input 3", "Input 4", "Input 5", "Input 6", "Input 7", "Input 8"]
  # ... out_3 through out_8

aux_entities:
  - id: power
    expected_domain: switch

interfaces:
  - id: in_1
    direction: input
    type: hdmi
    label: "Input 1"
    routable_to_output_group: [out_1, out_2, out_3, out_4, out_5, out_6, out_7, out_8]
  # ... in_2 through in_8

  - id: out_1
    direction: output
    type: hdmi
    label: "Output 1"
    output_group: out_1
  # ... out_2 through out_8
```

### A HDFury Diva (output groups with audio extraction)

Two output groups (TX0, TX1). The TX0 group includes the TX0 HDMI output plus the audio extraction outputs (HDMI extraction, optical, RCA). All TX0 outputs share the same active input.

```yaml
profile_id: hdfury/diva
schema_version: 1
manufacturer: HDFury
model: Diva
category: matrix
power_handling: discrete_capable

output_groups:
  - id: tx0
    selection_mechanism:
      kind: select_entity
      expected_domain: select
      expected_options: ["Input 1", "Input 2", "Input 3", "Input 4"]
  - id: tx1
    selection_mechanism:
      kind: select_entity
      expected_domain: select
      expected_options: ["Input 1", "Input 2", "Input 3", "Input 4"]

inputs_are_exclusive_per_output_group: [tx0, tx1]

aux_entities:
  - id: power
    expected_domain: switch

interfaces:
  - id: hdmi_in_1
    direction: input
    type: hdmi
    label: "Input 1"
    routable_to_output_group: [tx0, tx1]
  - id: hdmi_in_2
    direction: input
    type: hdmi
    label: "Input 2"
    routable_to_output_group: [tx0, tx1]
  - id: hdmi_in_3
    direction: input
    type: hdmi
    label: "Input 3"
    routable_to_output_group: [tx0, tx1]
  - id: hdmi_in_4
    direction: input
    type: hdmi
    label: "Input 4"
    routable_to_output_group: [tx0, tx1]


  - id: tx0_hdmi
    direction: output
    type: hdmi_audio_return
    label: "TX0"
    output_group: tx0

  - id: aud0_hdmi
    direction: output
    type: hdmi
    label: "AUD0 (Audio Extraction)"
    output_group: tx0

  - id: analog_audio_out
    direction: output
    type: rca_audio
    label: "Analog Out"
    output_group: tx0

  - id: optical_out
    direction: output
    type: optical_audio
    label: "Optical Out"
    output_group: tx0

  - id: tx1_hdmi
    direction: output
    type: hdmi
    label: "TX1"
    output_group: tx1
```

The audio extraction outputs all belong to TX0's group, so audio routed through any of them is sourced from whatever input is active on TX0. No separate construct is needed.

### A Lumagen video processor

Multiple inputs, multiple outputs that are mutually exclusive (only one is the correct active output at a time, but the integration doesn't command which — that's external).

```yaml
profile_id: lumagen/radiance-pro
schema_version: 1
manufacturer: Lumagen
model: Radiance Pro
category: video_processor
power_handling: discrete_capable
power_on_delay: 6

output_groups:
  - id: main
    selection_mechanism:
      kind: media_player_source
      expected_domain: media_player
      expected_features: [select_source]
    provides_roles: [source_selection]

inputs_are_exclusive_per_output_group: [main]
exclusive_outputs: true

interfaces:
  - id: hdmi_in_1
    direction: input
    type: hdmi
    label: "Input 1"
    routable_to_output_group: [main]
  - id: hdmi_in_2
    direction: input
    type: hdmi
    label: "Input 2"
    routable_to_output_group: [main]
  # ...

  - id: hdmi_out_a
    direction: output
    type: hdmi
    label: "Output A"
    output_group: main
  - id: hdmi_out_b
    direction: output
    type: hdmi
    label: "Output B"
    output_group: main
```

The `exclusive_outputs: true` flag declares that even though both outputs are in the same group, only one is in correct use at a time. The integration tracks this for contention but does not command the device to change which is active — that's the user's responsibility, typically via an automation triggered off Media Room Manager's zone activation events.

### A passive converter (HDMI audio extractor)

```yaml
profile_id: generic/hdmi-audio-extractor
schema_version: 1
manufacturer: Generic
model: HDMI Audio Extractor
category: passive_converter
power_handling: disabled

output_groups:
  - id: main
    # No selection_mechanism — passive transit, no commands.

interfaces:
  - id: hdmi_in
    direction: input
    type: hdmi
    label: "HDMI IN"
    routable_to_output_group: [main]

  - id: hdmi_passthrough_out
    direction: output
    type: hdmi
    label: "HDMI OUT"
    output_group: main

  - id: audio_breakout_optical
    direction: output
    type: optical_audio
    label: "OPTICAL AUDIO OUT"
    output_group: main

  - id: audio_breakout_rca
    direction: output
    type: rca_audio
    label: "RCA AUDIO OUT"
    output_group: main
```

User-built configuration — devices, connections, zones, source visibility, bindings, remaps — never appears as YAML in the user's HA config.

## Roadmap

### v0.1 — Internal alpha

- Backend graph model and `Store`-backed persistence.
- Bundled profile library skeleton with ~10 hand-written profiles.
- `media_player_source` and `remote_command` adapters.
- Path resolver for simple linear paths.
- `media_player` entity per zone with `select_source` and basic transport pass-through.
- WebSocket command surface covering the minimum needed for the panel.
- Panel skeleton: Devices and Zones tabs, basic CRUD.

### v1.0 — First public release

- Bulk import of profiles from existing driver archives (topology data only).
- Full set of v1 mechanisms.
- Path resolver handles transit devices, output groups, virtual sources (static and dynamic), `hdmi_audio_return` reverse audio, multi-output-group devices, `simultaneous` and `selectable_exclusive` sink modes, exclusive_outputs constraints.
- Helper `select` and `switch` entities for `selectable_exclusive` zones.
- Control role resolution.
- Static `supported_features` computation at zone configuration time.
- Source visibility via dual-list selector (three categories).
- Entity registry-id binding. Capability filtering. Per-instance label remap UI.
- Discovery service with constellation matching against profile `discovery` blocks.
- Repair service for invalid bindings, broken expectations, source-list drift, paths no longer resolving.
- State tracker with observed/commanded/unknown model.
- Basic power sequencing.
- Per-shared-device `binary_sensor.<device>_in_use` entities.
- Bundled converter profile library.
- Panel: Devices, Connections, Zones, Profile library, Diagnostics (with Looking Glass), Settings tabs. Ad-hoc device wizard.
- HACS-installable single package containing backend + bundled panel JS.
- Contention policies: `deny` (default) and `preempt`. The `share` policy is deferred to v1.x.

### v1.x

- Community profile repository with PR-based contribution and submit-from-UI flow.
- Improved error messages and richer diagnostics.
- Expansion of mechanism set as devices in the wild reveal patterns the v1 set doesn't cover.
- `media_player.join` exposure on virtual zones for streaming-source multi-room scenarios.
- `share` contention policy for outputs already broadcasting compatibly.

### v2.0

- Topology visualization tab — read-mostly graph view of the system.
- Sophisticated power policies (load shedding, scheduled, dependency timeouts).
- Advanced contention policies (queueing, priority).
- Fallback path resolution when primary path fails.
- CEC-aware orchestration where the underlying HDMI-CEC integration provides observable state.

### Beyond

- Standardized profile-declaration interface published as a Python package, allowing third-party HA integration developers to declare their entities as natively Media-Room-Manager-aware in a structured (still declarative) way.
- Scenes — preset combinations of zone activations.
- Cross-system migration tools.

## Open questions

These are decisions deliberately left open for now, to be resolved during implementation:

**Identification of identical interfaces.** When a device has multiple identical-looking outputs (a matrix's 8 outputs), graph correctness depends on stable interface IDs that survive profile updates.

**Discovery weight calibration.** The numeric weights on discovery signals are calibration choices that need tuning against real behavior once the library has meaningful coverage.

**Conflict between commanded and observed state.** When the orchestrator commands an AVR to input HDMI 2 but the AVR's reported state remains HDMI 3 after a timeout, the integration must decide whether to retry, fail, or trust the observed state.

**Power tracking for toggle-style commands.** Some IR-controlled devices have a single POWER toggle command rather than discrete on/off codes. The integration must use observed state or other heuristics to decide whether to send the toggle.

**Filter syntax for dynamic-source exclude lists.** Whether profiles should support glob, regex, or just literal-value matching for the `exclude` list on `dynamic_virtual_sources`.

**Ad-hoc profile lifecycle.** If a community profile for the same device is later added to the library, the user should be offered a migration. The detection mechanism needs design.

**WebSocket API stability and versioning.** Decisions about versioning and back-compatibility windows need to be made before v1 ships.

**Frontend framework choice.** Lit aligns most cleanly with HA's native frontend stack and is what KNX uses. Decision to be made when implementation starts, with a slight lean toward Lit.

**Graph rendering library for the future topology view.** Cytoscape.js and React Flow are the leading candidates. Decision deferred to v2 planning.

---

*This document is a planning artifact and a reference for implementation. Details will change as the system is built.*
