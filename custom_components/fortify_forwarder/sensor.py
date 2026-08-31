"""Status sensors: which entities are being forwarded, and how many events are queued."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_LOCATION_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    fwd = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ForwardedSensors(fwd, entry), QueuedEvents(fwd, entry)])


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, fwd, entry: ConfigEntry) -> None:
        self._fwd = fwd
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Fortify Forwarder — {entry.data.get(CONF_LOCATION_NAME, 'site')}",
            manufacturer="Fortify Labs",
            model="HA Forwarder",
            sw_version=getattr(fwd, "version", None),
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(
            self.hass, self._fwd.signal, self._refresh))

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()


class ForwardedSensors(_Base):
    """State = how many entities the platform has room-associated; attributes list them."""

    _attr_name = "Forwarded sensors"
    _attr_icon = "mdi:motion-sensor"
    _attr_native_unit_of_measurement = "sensors"

    def __init__(self, fwd, entry: ConfigEntry) -> None:
        super().__init__(fwd, entry)
        self._attr_unique_id = f"{entry.entry_id}_forwarded"

    @property
    def native_value(self) -> int:
        return len(self._fwd.watched)

    @property
    def extra_state_attributes(self) -> dict:
        rows = []
        for entity_id, kind in sorted(self._fwd.watched.items()):
            st = self.hass.states.get(entity_id)
            name = st.attributes.get("friendly_name") if st else None
            rows.append(f"{name or entity_id} ({kind})")
        return {"sensors": rows, "location": self._entry.data.get(CONF_LOCATION_NAME, "")}


class QueuedEvents(_Base):
    """0 in healthy operation; climbing = the platform is unreachable and buffering is active."""

    _attr_name = "Queued events"
    _attr_icon = "mdi:tray-full"
    _attr_native_unit_of_measurement = "events"

    def __init__(self, fwd, entry: ConfigEntry) -> None:
        super().__init__(fwd, entry)
        self._attr_unique_id = f"{entry.entry_id}_queued"

    @property
    def native_value(self) -> int:
        return len(self._fwd.queue)
