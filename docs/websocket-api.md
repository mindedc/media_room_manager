# WebSocket API Reference

All commands are registered under the `media_room_manager` domain and follow
Home Assistant's standard WebSocket command pattern.

**Schema version policy:** Breaking changes to any command's request or
response shape increment the `api_version` field in the response. Callers
should validate the `api_version` field before relying on response fields
added in later versions.

---

## Phase 1 commands — Read-only inspection

### `media_room_manager/list_devices`

Returns all configured devices in the system graph.

**Request:**

```json
{ "id": 1, "type": "media_room_manager/list_devices" }
```

**Response:**

```json
{
  "id": 1,
  "type": "result",
  "success": true,
  "result": {
    "devices": [
      {
        "id": "atv",
        "name": "Apple TV",
        "profile_id": "apple/apple-tv-4k",
        "power_handling": "discrete_capable",
        "power_on_delay": 0,
        "exclusive_outputs": false,
        "output_groups": [ ... ],
        "interfaces": [ ... ],
        "virtual_sources": [ ... ],
        "dynamic_virtual_sources": null,
        "aux_entities": [],
        "inputs_are_exclusive_per_output_group": []
      }
    ]
  }
}
```

---

### `media_room_manager/list_zones`

Returns all configured zones.

**Request:**

```json
{ "id": 2, "type": "media_room_manager/list_zones" }
```

**Response:**

```json
{
  "id": 2,
  "type": "result",
  "success": true,
  "result": {
    "zones": [
      {
        "id": "living_room",
        "name": "Living Room",
        "sink_device_ids": ["tv"],
        "sink_mode": "single",
        "volume_authority_device_id": "avr",
        "volume_authority_output_group_id": "main",
        "contention_policy": "deny",
        "default_sink_device_id": null
      }
    ]
  }
}
```

---

### `media_room_manager/list_connections`

Returns all configured connections between device interfaces.

**Request:**

```json
{ "id": 3, "type": "media_room_manager/list_connections" }
```

**Response:**

```json
{
  "id": 3,
  "type": "result",
  "success": true,
  "result": {
    "connections": [
      {
        "id": "atv_to_avr",
        "from_device_id": "atv",
        "from_interface_id": "hdmi_out",
        "to_device_id": "avr",
        "to_interface_id": "hdmi_in_1"
      }
    ]
  }
}
```

---

## Phase 2 commands — Profile registry

### `media_room_manager/list_profiles`

Returns a lightweight summary of every loaded profile (bundled + local).

**Request:**

```json
{ "id": 4, "type": "media_room_manager/list_profiles" }
```

**Response:**

```json
{
  "id": 4,
  "type": "result",
  "success": true,
  "result": {
    "profiles": [
      {
        "profile_id": "apple/apple-tv-4k",
        "manufacturer": "Apple",
        "model": "Apple TV 4K",
        "category": "source",
        "power_handling": "discrete_capable"
      }
    ]
  }
}
```

---

### `media_room_manager/get_profile`

Returns the fully serialized profile for a given `profile_id`.

**Request:**

```json
{ "id": 5, "type": "media_room_manager/get_profile", "profile_id": "marantz/sr8015" }
```

**Response (success):**

```json
{
  "id": 5,
  "type": "result",
  "success": true,
  "result": {
    "profile": {
      "profile_id": "marantz/sr8015",
      "schema_version": 1,
      "manufacturer": "Marantz",
      "model": "SR8015",
      "category": "avr",
      "power_handling": "discrete_capable",
      "power_on_delay": 4,
      "exclusive_outputs": false,
      "output_groups": [ ... ],
      "interfaces": [ ... ],
      "virtual_sources": [ ... ],
      "dynamic_virtual_sources": { ... },
      "aux_entities": [],
      "inputs_are_exclusive_per_output_group": ["main", "zone_2"],
      "discovery": { ... }
    }
  }
}
```

**Response (not found):**

```json
{
  "id": 5,
  "type": "result",
  "success": false,
  "error": { "code": "not_found", "message": "Profile 'bad/id' not found" }
}
```

---

*Further commands will be added in subsequent phases. See `TASKS.md` for the
planned command surface.*
