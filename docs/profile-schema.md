# Device Profile Schema Reference

This document describes the YAML schema for Media Room Manager device profiles.
Profiles live in `profiles/bundled/` (community library) or
`<config>/media_room_manager/profiles/` (user-local overrides). The schema
version is `1`.

---

## Top-level fields

```yaml
profile_id: vendor/model-slug        # required — unique, lowercase, no spaces
schema_version: 1                     # required — always 1 for now
manufacturer: Acme Corp               # required — human-readable
model: AMP-2000                       # required — human-readable
category: avr                         # required — see Categories
power_handling: discrete_capable      # optional — default: disabled
power_on_delay: 4                     # optional — seconds, default: 0
exclusive_outputs: false              # optional — default: false
```

### `profile_id`

Format: `vendor/model-slug`. Use lowercase, hyphens for spaces, no special
characters. Must be unique across all layers (bundled, community, local).
Examples: `apple/apple-tv-4k`, `marantz/sr8015`, `generic/hdmi-splitter-1x4`.

### `schema_version`

Always `1` for profiles targeting the current integration version.

### `category`

| Value | Meaning |
|---|---|
| `source` | A source device (streamer, disc player, game console, cable box) |
| `avr` | An AV receiver or surround processor |
| `matrix` | An HDMI matrix switch |
| `video_processor` | A dedicated video processor (scaler, frame rate converter) |
| `passive_converter` | A passive signal converter or distributor (no selection mechanism) |
| `display` | A display device (TV, projector) |
| `other` | Anything that doesn't fit the above |

### `power_handling`

| Value | Meaning |
|---|---|
| `discrete_capable` | Device has discrete power-on and power-off commands |
| `toggle` | Device has only a single power toggle command |
| `always_on` | Device is always on; no power commands are issued |
| `disabled` | Power management is disabled for this device |

### `power_on_delay`

Seconds to wait after issuing a power-on command before sending further
commands to this device. Used to allow time for the device to initialize.
Default: `0`.

### `exclusive_outputs`

When `true`, all outputs share one output group but only one output is in
correct use at a time. The integration tracks which output is in use for
contention purposes but **does not command the device to change its active
output** — that is the user's responsibility. Typically applies to video
processors with multiple output connectors where only one is correctly
connected to a downstream device (e.g. Lumagen Radiance Pro).

---

## `output_groups`

An output group is a device-internal grouping of outputs that share one active
input selection. An AVR's main zone and zone 2 are separate output groups; an
HDMI matrix with N outputs has N output groups (one per output).

```yaml
output_groups:
  - id: main                          # required — unique within the profile
    selection_mechanism:              # optional — omit for passive devices
      kind: media_player_source       # required — see Mechanism kinds
      expected_domain: media_player   # optional
      expected_features:             # optional — list of feature flag names
        - turn_on
        - turn_off
        - select_source
        - volume_set
        - volume_mute
      expected_options: []            # optional — for select_entity
      expected_commands: []           # optional — for remote_command
    provides_roles:                   # optional — roles this output group fulfills
      - power
      - volume
      - source_selection
      - metadata_source
    role_operations:                  # optional — for non-media_player groups
      power:
        kind: remote_command
        operations:
          power_on:  { command: "KEY_POWER_ON",  delay: 0.5 }
          power_off: { command: "KEY_POWER_OFF", delay: 0.5 }
```

### Mechanism kinds

| Kind | Bound entity | What it controls |
|---|---|---|
| `media_player_source` | `media_player` | Full media player: source, power, volume, transport |
| `select_entity` | `select` | Switches input by selecting an option |
| `switch_combo` | `switch` (grid) | Turns on the correct switch in a matrix of switches |
| `remote_command` | `remote` | Sends IR/RF commands via `remote.send_command` |
| `service_call` | any | Calls an arbitrary HA service with static parameters |

### Control roles

| Role | Meaning |
|---|---|
| `power` | This output group handles power on/off |
| `volume` | This output group handles volume and mute |
| `source_selection` | This output group handles input switching |
| `metadata_source` | This output group provides playback metadata |
| `transport` | This output group handles play/pause/stop |

When a `media_player_source` group is used, all applicable roles are inferred
automatically. Declare `provides_roles` explicitly only for groups that use
other mechanism kinds.

---

## `inputs_are_exclusive_per_output_group`

```yaml
inputs_are_exclusive_per_output_group: [main, zone_2]
```

Lists which output groups enforce single-input exclusivity — only one input
can be selected on a given output group at a time. For AVRs and most other
devices this is true for all output groups; for a true full-matrix device it
would be omitted.

---

## `interfaces`

Each interface represents a physical port on the device. Input interfaces
declare `routable_to_output_group`; output interfaces declare `output_group`.

```yaml
interfaces:
  - id: hdmi_in_1                     # required — unique within the profile
    direction: input                  # required — input | output
    type: hdmi                        # required — see Interface types
    label: "HDMI 1"                   # required — displayed in the UI
    routable_to_output_group:         # required for inputs
      - main
      - zone_2

  - id: hdmi_main_out
    direction: output
    type: hdmi_audio_return
    label: "HDMI MAIN"
    output_group: main                # required for outputs
```

### Interface types

| Value | Physical connector |
|---|---|
| `hdmi` | Standard HDMI |
| `hdmi_audio_return` | HDMI with ARC/eARC (Audio Return Channel) |
| `optical_audio` | Optical / TOSLINK |
| `coax_audio` | Coaxial digital audio (S/PDIF) |
| `rca_audio` | Analog RCA stereo |
| `xlr_audio` | Balanced XLR analog |
| `component_video` | Component video (3× RCA) |
| `composite_video` | Composite video (single RCA) |

---

## `virtual_sources`

Static virtual sources are content origins that live inside the device but
have no physical input — a tuner, a built-in streaming service, etc.

```yaml
virtual_sources:
  - id: tuner
    label: "Tuner"
    routable_to_output_group: [main, zone_2]
```

---

## `dynamic_virtual_sources`

Tells the integration to discover additional virtual sources at runtime by
reading the bound entity's `source_list` and subtracting known physical
interfaces, static virtual sources, and the `exclude` list.

```yaml
dynamic_virtual_sources:
  source: source_list_minus_known     # only value currently supported
  output_group: main
  exclude:
    - "Internet Radio"
    - "AirPlay"
```

---

## `aux_entities`

Auxiliary HA entities bound to the device that are not tied to an output
group's selection mechanism — typically a power switch, an IR blaster remote,
or a sensor.

```yaml
aux_entities:
  - id: power
    expected_domain: switch           # required

  - id: ir_blaster
    expected_domain: remote
    expected_commands:
      - KEY_POWER_ON
      - KEY_POWER_OFF
```

---

## `discovery`

The discovery block tells the integration how to automatically suggest this
profile when scanning the user's HA entity registry. It is optional but
strongly recommended for any profile that corresponds to an integration with
known entity shapes.

Discovery runs in two stages:

1. **Stage 1 — Anchor matching.** The integration scores every enabled entity
   against the output group entry flagged `is_discovery_anchor: true`. Entities
   that meet the `match_threshold` become anchor candidates.

2. **Stage 2 — Sibling matching.** For each anchor candidate, sibling entities
   under the same HA device (including disabled entities) are scored against the
   remaining output group entries. Optional entries that don't meet threshold are
   left unbound.

```yaml
discovery:
  output_groups:
    - output_group: main
      is_discovery_anchor: true       # exactly one entry must be the anchor
      match_threshold: 60             # 0–100, default 60
      signals:
        - kind: device_registry
          manufacturer: "Marantz"
          model_patterns: ["SR8015", "*SR8015*"]
          weight: 100
        - kind: platform
          domain: denonavr
          weight: 40
        - kind: source_list_signature
          includes_any: ["CBL/SAT", "Blu-ray"]
          weight: 30
        - kind: attribute_constellation
          includes: ["source_list", "sound_mode_list", "supported_features"]
          weight: 50

    - output_group: zone_2
      optional: true                  # omit if sibling not found
      match_threshold: 50
      signals:
        - kind: platform
          domain: denonavr
          weight: 40
```

### Discovery signal kinds

#### `device_registry`

Matches the device's manufacturer and model from the HA device registry.

```yaml
kind: device_registry
manufacturer: "Marantz"              # exact substring match
model_patterns: ["SR8015", "*SR8015*"]  # glob patterns
weight: 100
```

#### `platform`

Matches the entity's integration platform (the `platform` field in the entity
registry entry).

```yaml
kind: platform
domain: denonavr
weight: 40
```

#### `supported_features`

Matches against the entity state's `supported_features` bitmask. Values are
integers (feature flag constants).

```yaml
kind: supported_features
values: [1, 4, 8192]                 # all must be set
weight: 30
```

#### `source_list_signature`

Matches against the entity state's `source_list` attribute.

```yaml
kind: source_list_signature
includes_any: ["CBL/SAT", "Blu-ray"]   # at least one must appear
# includes: [...]                       # all must appear
# matches: [...]                        # exact set match
weight: 30
```

#### `sound_mode_list_signature`

Matches against the entity state's `sound_mode_list` attribute. Same operators
as `source_list_signature`.

```yaml
kind: sound_mode_list_signature
includes_any: ["STEREO", "DOLBY DIGITAL"]
weight: 50
```

#### `device_class`

Matches the entity's device class.

```yaml
kind: device_class
matches: ["receiver"]
weight: 20
```

#### `friendly_name`

Substring-matches the entity's friendly name.

```yaml
kind: friendly_name
friendly_name_patterns: ["Marantz", "SR8015"]
weight: 10
```

#### `attribute_constellation`

Checks that the listed attribute keys are all present on the entity state
(presence only, not values).

```yaml
kind: attribute_constellation
includes: ["source_list", "sound_mode_list", "supported_features"]
weight: 50
```

---

## Complete examples

See the bundled profiles in `profiles/bundled/` for complete real-world
examples:

| Profile | Highlights |
|---|---|
| `apple/apple-tv-4k` | Source, discrete power, dynamic virtual sources, discovery |
| `sony/dvp-ns500v` | Source, toggle power, remote_command role_operations, IR blaster aux |
| `denon/avr-x1700h` | Single-zone AVR, media_player_source, dynamic sources, discovery |
| `marantz/sr8015` | Two-zone AVR, static + dynamic virtual sources, full discovery |
| `anthem/mrx-740` | Two-zone AVR, parallel HDMI outputs on main, discovery |
| `monoprice/blackbird-8x8` | 8×8 matrix, select_entity per output, power switch aux |
| `hdfury/diva` | 2-output matrix, audio extraction outputs on TX0 |
| `lumagen/radiance-pro` | Video processor, exclusive_outputs, 8 inputs / 2 outputs |
| `generic/hdmi-splitter-1x4` | Passive splitter, disabled power, no selection mechanism |
| `generic/hdmi-audio-extractor` | Passive converter, 4 outputs (HDMI, HDMI audio, optical, RCA) |
