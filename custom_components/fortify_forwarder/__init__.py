"""Fortify Platform Forwarder — headless sensor forwarding with durable buffering.

The platform owns ALL configuration (which sensors matter, which room each belongs to);
this integration inventories candidates, pulls its watch-list, forwards watched-entity
events in realtime from the local bus, and disk-queues them (with original timestamps)
whenever the platform is unreachable. Contract: FortifyPlatform docs/HA-FORWARDER-CONTRACT.md.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .const import (
    CANDIDATE_CLASSES, CANDIDATE_DOMAINS, CONF_API_KEY, CONF_LOCATION_ID, CONF_URL, DOMAIN,
    EVENT_BATCH_MAX, FLUSH_SECONDS, INVENTORY_MINUTES, QUEUE_LIMIT,
)

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1
PLATFORMS = ["button", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    fwd = FortifyForwarder(hass, entry)
    await fwd.async_start()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = fwd
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    fwd: FortifyForwarder | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if fwd:
        await fwd.async_stop()
    return ok


class FortifyForwarder:
    """Inventory loop + event listener + durable outbound queue."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.url: str = entry.data[CONF_URL].rstrip("/")
        self.api_key: str = entry.data[CONF_API_KEY]
        self.location_id: str = entry.data[CONF_LOCATION_ID]
        self.session = async_get_clientsession(hass)
        self.watched: dict[str, str] = {}          # entity_id -> kind (motion|door)
        self.queue: list[dict] = []                # pending events, oldest first
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.queue.{entry.entry_id}")
        self._unsubs: list = []
        self._flushing = asyncio.Lock()
        self.signal = f"{DOMAIN}_{entry.entry_id}_update"  # dispatcher topic for status entities

    # ── lifecycle ────────────────────────────────────────────────────────────────────────
    async def async_start(self) -> None:
        stored = await self._store.async_load()
        if isinstance(stored, list):
            self.queue = stored[-QUEUE_LIMIT:]
            if self.queue:
                _LOGGER.info("Restored %d queued events from disk", len(self.queue))
        if self.hass.is_running:
            await self._report_inventory()  # also fetches the initial watch-list
            await self._push_snapshot()
        else:
            # During boot, slower integrations (Caseta, ZHA) haven't created their entities
            # yet — a startup inventory would under-report. Wait for HA to finish starting.
            async def _on_started(_event):
                await self._report_inventory()
                await self._push_snapshot()
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started)
        self._unsubs.append(self.hass.bus.async_listen("state_changed", self._on_state_changed))
        self._unsubs.append(async_track_time_interval(
            self.hass, self._report_inventory, timedelta(minutes=INVENTORY_MINUTES)))
        self._unsubs.append(async_track_time_interval(
            self.hass, self._flush_tick, timedelta(seconds=FLUSH_SECONDS)))

    async def async_stop(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()
        await self._store.async_save(self.queue)

    # ── platform calls ───────────────────────────────────────────────────────────────────
    async def _post(self, path: str, payload: dict) -> dict:
        async with self.session.post(
            f"{self.url}{path}", json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            if resp.status == 401:
                raise PermissionError("API key rejected")
            resp.raise_for_status()
            return await resp.json()

    # ── inventory (and heartbeat, and watch-list refresh) ────────────────────────────────
    def _candidates(self) -> list[dict]:
        ent_reg = er.async_get(self.hass)
        dev_reg = dr.async_get(self.hass)
        area_reg = ar.async_get(self.hass)
        out: list[dict] = []
        candidates = list(self.hass.states.async_all("binary_sensor"))
        for domain in CANDIDATE_DOMAINS:
            candidates.extend(self.hass.states.async_all(domain))
        for state in candidates:
            domain = state.entity_id.split(".")[0]
            dc = state.attributes.get("device_class")
            if domain == "binary_sensor":
                if dc not in CANDIDATE_CLASSES:
                    continue
            else:
                dc = dc or domain  # lights/switches usually have no device_class
            area_name = ""
            ent = ent_reg.async_get(state.entity_id)
            if ent:
                area_id = ent.area_id
                if not area_id and ent.device_id:
                    dev = dev_reg.async_get(ent.device_id)
                    area_id = dev.area_id if dev else None
                if area_id:
                    area = area_reg.async_get_area(area_id)
                    area_name = area.name if area else ""
            out.append({
                "entityId": state.entity_id,
                "name": state.attributes.get("friendly_name") or state.entity_id,
                "area": area_name,
                "deviceClass": dc,
            })
        return out[:500]

    def _reassert_active_occupancy(self) -> None:
        """Latched occupancy sensors (Lutron Caseta) hold 'on' for an entire occupancy
        instead of pulsing — without this, a 3-hour session stamps only its entry block.
        Every inventory cycle (10 min < the 15-min block size, so every block gets at
        least one stamp), re-assert 'on' for occupancy/motion kinds that are still on.
        Deliberately NOT switches (a light left on in an empty room is not presence)
        and NOT doors (their state is positional, not presence)."""
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        n = 0
        for entity_id, kind in self.watched.items():
            if kind != "motion":
                continue
            st = self.hass.states.get(entity_id)
            if st is not None and st.state == "on":
                self.queue.append({"entityId": entity_id, "state": "on", "ts": now_iso})
                n += 1
        if n:
            _LOGGER.debug("Re-asserted %d active occupancy sensors", n)

    async def _report_inventory(self, _now=None) -> None:
        try:
            resp = await self._post("/api/iot/inventory", {
                "locationId": self.location_id,
                "entities": self._candidates(),
            })
            self.watched = {
                w["entityId"]: w.get("kind", "motion")
                for w in resp.get("watchList", [])
            }
            async_dispatcher_send(self.hass, self.signal)
            _LOGGER.debug("Inventory reported; watching %d entities", len(self.watched))
            # sustained-occupancy re-assertion rides the same 10-minute cycle
            self._reassert_active_occupancy()
            # connectivity proven — drain anything the queue is holding
            await self._flush()
        except Exception as e:  # noqa: BLE001 — network failures are routine; queue covers us
            _LOGGER.warning("Inventory report failed (will retry): %s", e)

    # ── events ───────────────────────────────────────────────────────────────────────────
    @callback
    def _on_state_changed(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        kind = self.watched.get(entity_id)
        if not kind:
            return
        new = event.data.get("new_state")
        old = event.data.get("old_state")
        if new is None or new.state in ("unavailable", "unknown"):
            return
        if old is not None and old.state == new.state:
            return
        if kind == "switch":
            if new.state not in ("on", "off"):
                return  # lights/switches: BOTH edges are activity (off = someone just left)
        elif kind != "door" and new.state != "on":
            return  # motion/occupancy: forward the on-edge only; doors send both edges
        ts = (new.last_changed or new.last_updated).isoformat()
        self.queue.append({"entityId": entity_id, "state": new.state, "ts": ts})
        if len(self.queue) > QUEUE_LIMIT:
            del self.queue[: len(self.queue) - QUEUE_LIMIT]
        async_dispatcher_send(self.hass, self.signal)
        self.hass.async_create_task(self._flush())

    async def _flush_tick(self, _now=None) -> None:
        if self.queue:
            await self._flush()

    async def _flush(self) -> None:
        if self._flushing.locked():
            return
        async with self._flushing:
            while self.queue:
                batch = self.queue[:EVENT_BATCH_MAX]
                try:
                    resp = await self._post("/api/iot/events", {
                        "locationId": self.location_id, "events": batch,
                    })
                    del self.queue[: len(batch)]
                    if resp.get("unbound"):
                        # bindings changed under us — refresh the watch-list soon
                        _LOGGER.debug("%s events unbound; watch-list stale", resp["unbound"])
                except Exception as e:  # noqa: BLE001
                    _LOGGER.warning("Event flush failed, %d queued (will retry): %s",
                                    len(self.queue), e)
                    break
            await self._store.async_save(self.queue)
            async_dispatcher_send(self.hass, self.signal)

    async def async_resync(self) -> None:
        """The re-sync button: inventory + watch-list + queue flush + state snapshot."""
        _LOGGER.info("Manual re-sync requested")
        await self._report_inventory()
        await self._push_snapshot()

    def _snapshot_events(self) -> list[dict]:
        """Current state of every watched entity, stamped with when it ACTUALLY changed —
        so a restart back-fills truth (light on since 17:42) instead of fabricating
        boot-time activity. The platform's 72h staleness gate and monotonic lastAt
        guard handle the rest."""
        out: list[dict] = []
        for entity_id, _kind in self.watched.items():
            st = self.hass.states.get(entity_id)
            if st is None or st.state in ("unknown", "unavailable"):
                continue
            if st.state not in ("on", "off", "open", "closed"):
                continue
            out.append({
                "entityId": entity_id, "state": st.state,
                "ts": (st.last_changed or st.last_updated).isoformat(),
            })
        return out

    async def _push_snapshot(self) -> None:
        events = self._snapshot_events()
        if not events:
            return
        _LOGGER.info("Pushing state snapshot for %d watched entities", len(events))
        self.queue.extend(events)
        if len(self.queue) > QUEUE_LIMIT:
            del self.queue[: len(self.queue) - QUEUE_LIMIT]
        await self._flush()
