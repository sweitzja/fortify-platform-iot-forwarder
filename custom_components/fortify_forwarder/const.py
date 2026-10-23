"""Constants for the Fortify Platform Forwarder."""

DOMAIN = "fortify_forwarder"

CONF_URL = "url"
CONF_API_KEY = "api_key"
CONF_LOCATION_ID = "location_id"
CONF_LOCATION_NAME = "location_name"

DEFAULT_URL = "https://sze0buuoa1.execute-api.us-east-1.amazonaws.com/sls"

# binary_sensor device classes worth reporting as candidates (contract: max 1000)
CANDIDATE_CLASSES = {
    "motion", "occupancy", "presence", "door", "window", "opening", "garage_door",
}
# whole domains reported as candidates: a light/switch flip is a human hand on a wall,
# so the platform can bind these as activity ("switch" kind — BOTH edges forwarded).
# ORDER MATTERS: a report is capped at INVENTORY_MAX entities and is filled in this order, so a
# room's dimmer (light.*) never loses its slot to a switch.* entity. Entities with an entity
# category (config / diagnostic — a camera's detection toggles, overlays, status LEDs) are never
# candidates: they are settings, not a hand on a wall.
CANDIDATE_DOMAINS = ("binary_sensor", "light", "switch")
INVENTORY_MAX = 1000         # contract cap (1000 since 0.5.2 / platform 2026-10-23); the platform rejects a larger report outright

# Contract cadences (docs/HA-FORWARDER-CONTRACT.md in FortifyPlatform)
INVENTORY_MINUTES = 10       # inventory report = heartbeat; platform holds welfare alerts at 20min stale
FLUSH_SECONDS = 30           # retry cadence for a non-empty queue
EVENT_BATCH_MAX = 500
QUEUE_LIMIT = 10_000         # oldest events drop beyond this (multi-day outage ceiling)
