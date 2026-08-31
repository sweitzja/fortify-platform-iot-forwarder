"""Re-sync button — report inventory + refresh the watch-list + flush the queue, now."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_LOCATION_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    fwd = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ResyncButton(fwd, entry)])


class ResyncButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Re-sync with Fortify Platform"
    _attr_icon = "mdi:cloud-sync"

    def __init__(self, fwd, entry: ConfigEntry) -> None:
        self._fwd = fwd
        self._attr_unique_id = f"{entry.entry_id}_resync"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Fortify Forwarder — {entry.data.get(CONF_LOCATION_NAME, 'site')}",
            manufacturer="Fortify Labs",
            model="HA Forwarder",
        )

    async def async_press(self) -> None:
        await self._fwd.async_resync()
