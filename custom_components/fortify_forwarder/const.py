"""Constants for the Fortify Platform Forwarder."""

DOMAIN = "fortify_forwarder"

CONF_URL = "url"
CONF_API_KEY = "api_key"
CONF_LOCATION_ID = "location_id"
CONF_LOCATION_NAME = "location_name"

DEFAULT_URL = "https://sze0buuoa1.execute-api.us-east-1.amazonaws.com/sls"

# binary_sensor device classes worth reporting as candidates (contract: max 500)
CANDIDATE_CLASSES = {
    "motion", "occupancy", "presence", "door", "window", "opening", "garage_door",
}
# whole domains reported as candidates: a light/switch flip is a human hand on a wall,
# so the platform can bind these as activity ("switch" kind — BOTH edges forwarded)
CANDIDATE_DOMAINS = {"light", "switch"}

# Contract cadences (docs/HA-FORWARDER-CONTRACT.md in FortifyPlatform)
INVENTORY_MINUTES = 10       # inventory report = heartbeat; platform holds welfare alerts at 20min stale
FLUSH_SECONDS = 30           # retry cadence for a non-empty queue
EVENT_BATCH_MAX = 500
QUEUE_LIMIT = 10_000         # oldest events drop beyond this (multi-day outage ceiling)
