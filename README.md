# Fortify Platform IoT Forwarder

A Home Assistant custom integration that connects a building's sensors to the
[Fortify Platform](https://network.fortifylife.org). It is **headless and deliberately dumb**:
all configuration — which sensors matter and which room each one belongs to — lives in the
Fortify Platform, not in Home Assistant.

What it does:

- **Inventories** the building's motion/occupancy/door sensors and reports them to the platform
  every 10 minutes (this doubles as the site heartbeat).
- **Forwards** state changes for the sensors that staff have associated to rooms — in realtime,
  with the event's original timestamp.
- **Buffers** to disk whenever the platform is unreachable and replays on reconnect, so an
  internet outage loses nothing and events still land in the correct time blocks.
- Exposes a **Re-sync button** and two status sensors (**Forwarded sensors**, **Queued events**)
  on a device card.

---

## Requirements

- Home Assistant 2024.6 or newer (developed against 2026.4).
- A Fortify Platform **API key with the IoT / Sensors entitlement**:
  Fortify Platform → **Settings → API Keys → Create key** → choose the **IoT / Sensors**
  entitlement → copy the key (`fp_…`) — it is shown only once.

---

## Installation

### Option A — HACS (recommended)

1. In HACS: **⋮ menu → Custom repositories**.
2. Repository: `https://github.com/sweitzja/fortify-platform-iot-forwarder` · Type: **Integration** → **Add**.
3. Find **Fortify Platform Forwarder** in HACS and click **Download**.
4. Restart Home Assistant (**Settings → System → Restart**).

### Option B — manual, via Samba or the File editor

1. On this page click **Code → Download ZIP** and extract it.
2. Copy the folder `custom_components/fortify_forwarder/` into your Home Assistant
   `/config/custom_components/` directory (create `custom_components` if it doesn't exist).
   The result must be `/config/custom_components/fortify_forwarder/manifest.json` etc.
3. Restart Home Assistant.

### Option C — manual, via SSH

```bash
cd /config
mkdir -p custom_components
curl -L https://github.com/sweitzja/fortify-platform-iot-forwarder/archive/refs/heads/main.tar.gz \
  | tar xz --strip-components=2 -C custom_components \
    fortify-platform-iot-forwarder-main/custom_components/fortify_forwarder
```
Then restart Home Assistant. (If `/config` is read-only for your SSH user, prefix the commands
with `sudo`, or use Option B.)

---

## Setup (after the restart)

1. **Settings → Devices & Services → Add Integration** → search **"Fortify"** →
   **Fortify Platform Forwarder**.
2. **Screen 1:** the Platform URL is prefilled; paste your **API key**.
3. **Screen 2:** pick the **location** this Home Assistant lives in (e.g. *Fortify Home*).
4. Done. The integration reports its sensor inventory immediately and every 10 minutes after.

There is nothing else to configure in Home Assistant — ever.

## Associating sensors to rooms (done in the Fortify Platform)

1. Fortify Platform → **Housing** → open the location's board → click a room.
2. In the unit dialog, under **Sensors**, click **Associate a sensor** and pick from the list
   the integration reported (friendly names straight from Home Assistant).
3. The forwarder picks up the change within 10 minutes — or immediately if you press the
   **Re-sync with Fortify Platform** button on the integration's device page.

Only associated sensors are ever forwarded. Unassociating (the ✕ next to a sensor) stops
forwarding; history stays where it was recorded.

## Status & troubleshooting

On the integration's device page (**Settings → Devices & Services → Fortify Platform
Forwarder → 1 device**):

- **Forwarded sensors** — how many entities are room-associated; the entity's attributes list
  them by name.
- **Queued events** — `0` in healthy operation. A climbing number means the platform is
  unreachable and buffering is active; it drains automatically on reconnect (or press Re-sync).
- **Re-sync with Fortify Platform** — forces an immediate inventory report, watch-list refresh,
  and queue flush.

Logs: **Settings → System → Logs**, search `fortify`. For per-event detail, enable debug
logging from the integration card's ⋮ menu.

| Symptom | Likely cause |
|---|---|
| Config flow says *invalid_auth* | Key lacks the IoT / Sensors entitlement, or was revoked |
| Config flow says *no_locations* | The key's service provider has no locations yet |
| *Forwarded sensors* is 0 | No sensors associated to rooms yet — see above |
| *Queued events* climbing | Platform unreachable; buffering (this is the design working) |
| A sensor isn't offered in the platform picker | Its `device_class` isn't motion/occupancy/presence/door/window/opening — set one in HA |

## Privacy & scope

The integration sends: entity IDs, friendly names, areas, and device classes of candidate
binary sensors (the inventory), and on/off state changes with timestamps for room-associated
sensors only. It sends nothing else — no media players, no device trackers, no camera data —
and it never receives control access: the API key can only submit sensor data and read the
location list.

## License

MIT
