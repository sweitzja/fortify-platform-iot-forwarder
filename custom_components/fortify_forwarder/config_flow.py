"""Config flow: paste the Fortify API key, pick your location. Nothing else to configure."""
from __future__ import annotations

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_KEY, CONF_LOCATION_ID, CONF_LOCATION_NAME, CONF_URL, DEFAULT_URL, DOMAIN


class InvalidAuth(Exception):
    """The platform rejected the API key."""


async def _fetch_locations(hass, url: str, api_key: str) -> list[dict]:
    session = async_get_clientsession(hass)
    async with session.get(
        f"{url.rstrip('/')}/api/iot/locations",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        if resp.status == 401:
            raise InvalidAuth
        resp.raise_for_status()
        data = await resp.json()
        return data.get("locations", [])


class FortifyForwarderConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Two steps: credentials, then location pick."""

    VERSION = 1

    def __init__(self) -> None:
        self._url = ""
        self._api_key = ""
        self._locations: list[dict] = []

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                locations = await _fetch_locations(
                    self.hass, user_input[CONF_URL], user_input[CONF_API_KEY])
                if not locations:
                    errors["base"] = "no_locations"
                else:
                    self._url = user_input[CONF_URL].rstrip("/")
                    self._api_key = user_input[CONF_API_KEY]
                    self._locations = locations
                    return await self.async_step_location()
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_URL, default=DEFAULT_URL): str,
                vol.Required(CONF_API_KEY): str,
            }),
            errors=errors,
        )

    async def async_step_location(self, user_input=None):
        if user_input is not None:
            loc = next(
                (l for l in self._locations if l["locationId"] == user_input[CONF_LOCATION_ID]),
                None)
            if loc:
                await self.async_set_unique_id(f"{DOMAIN}_{loc['locationId']}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Fortify — {loc['name']}",
                    data={
                        CONF_URL: self._url,
                        CONF_API_KEY: self._api_key,
                        CONF_LOCATION_ID: loc["locationId"],
                        CONF_LOCATION_NAME: loc["name"],
                    },
                )
        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema({
                vol.Required(CONF_LOCATION_ID): vol.In(
                    {l["locationId"]: l["name"] for l in self._locations}),
            }),
        )
