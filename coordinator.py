"""DataUpdateCoordinator for GL-iNet API."""
import asyncio
import logging
from datetime import timedelta

import homeassistant.util.dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import DOMAIN, GUEST_CLIENT_TYPES, KNOWN_SERVICES, MODEL_MAP

_LOGGER = logging.getLogger(__name__)

def router_device_info(entry, coordinator):
    """Build device info for the router."""
    sys_info = coordinator.data.get("system", {}) if coordinator.data else {}
    model = sys_info.get("model") or "Router"
    fw = sys_info.get("firmware_version") or sys_info.get("fw_version")
    router_mac = sys_info.get("mac")
    
    lookup_model = model.lower()
    if lookup_model.startswith("gl-"):
        lookup_model = lookup_model[3:]
    friendly_model = MODEL_MAP.get(lookup_model, model)

    info = {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": f"GL-iNet {friendly_model}",
        "manufacturer": "GL-iNet",
        "model": f"{friendly_model} ({model})",
        "configuration_url": coordinator.api.host,
    }
    if router_mac:
        from homeassistant.helpers import device_registry as dr
        info["connections"] = {(dr.CONNECTION_NETWORK_MAC, router_mac)}
    if fw:
        info["sw_version"] = fw
    return info

def get_router_prefix(hass, entry, coordinator):
    """Get the prefix for router entities based on model and instance number."""
    sys_info = coordinator.data.get("system", {}) if coordinator.data else {}
    model = sys_info.get("model", "router").lower()
    if model.startswith("gl-"):
        model = model[3:]
    
    # Count how many entries have this model
    entries = hass.config_entries.async_entries(DOMAIN)
    model_entries = []
    
    for e in entries:
        if e.entry_id in hass.data.get(DOMAIN, {}):
            other_coord = hass.data[DOMAIN][e.entry_id]["coordinator"]
            if other_coord.data:
                other_model = other_coord.data.get("system", {}).get("model", "").lower()
                if other_model.startswith("gl-"):
                    other_model = other_model[3:]
                if other_model == model:
                    model_entries.append(e.entry_id)
    
    model_entries.sort()
    try:
        idx = model_entries.index(entry.entry_id)
    except ValueError:
        idx = 0
    
    if idx == 0:
        return model
    return f"{model}_{idx}"

def _parse_mac_map(entry, key=None) -> dict[str, str]:
    """Parse a mac grouping option into {mac: canonical_id}."""
    if key is None:
        from .const import CONF_MAC_GROUPS
        key = CONF_MAC_GROUPS

    mac_map: dict[str, str] = {}
    import re
    import shlex
    
    groups_raw = entry.options.get(key, entry.data.get(key, ""))
    if isinstance(groups_raw, list):
        lines = groups_raw
    elif isinstance(groups_raw, str):
        lines = groups_raw.splitlines()
    else:
        return mac_map

    mac_regex = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")

    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        try:
            parts = shlex.split(line)
        except ValueError:
            parts = line.split()

        if len(parts) >= 2:
            macs = [p.lower() for p in parts if mac_regex.match(p)]
            name_parts = [p for p in parts if not mac_regex.match(p)]
            
            if macs and name_parts:
                group_name = " ".join(name_parts)
                for m in macs:
                    mac_map[m] = group_name

    return mac_map

class GLiNetDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching GL-iNet data."""

    def __init__(self, hass, api, entry):
        self.entry = entry
        from .const import CONF_SCAN_INTERVAL
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, 30))
        """Initialize the coordinator."""
        self.api = api
        self._last_fw_check = None
        self._cached_fw_res = {}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self):
        """Fetch data from API."""
        
        requests = [
            ("clients", "get_list", {}),
            ("wifi", "get_config", {}),
            ("wifi", "get_mlo_config", {}),
            ("system", "get_info", {}),
            ("system", "get_status", {}),
            ("fan", "get_status", {}),
            ("firewall", "get_port_forward_list", {}),
            ("kmwan", "get_status", {}),
            ("kmwan", "get_config", {}),
            ("cable", "get_status", {}),
            ("led", "get_config", {}),
        ]

        try:
            results = await self.api.batch_call(requests)
            if not results:
                raise UpdateFailed("No data received from API")

            res = {}
            for item in results:
                idx = item.get("id")
                if idx is None:
                    continue
                if "error" in item:
                    _LOGGER.debug(
                        "Batch request %s (%s.%s) returned error: %s",
                        idx,
                        requests[idx][0] if idx < len(requests) else "?",
                        requests[idx][1] if idx < len(requests) else "?",
                        item["error"],
                    )
                    res[idx] = {}
                else:
                    res[idx] = item.get("result") or {}

            clients_list = res.get(0, {}).get("clients", [])
            wifi_res = res.get(1, {})
            mlo_res = res.get(2, {})
            system_info = res.get(3, {})
            system_status = res.get(4, {})
            fan_status = res.get(5, {})
            port_forward = res.get(6, {})
            kmwan_status = res.get(7, {})
            kmwan_config = res.get(8, {})
            cable_status = res.get(9, {})
            led_config = res.get(10, {})

            extra_service_data = {}
            raw_services = system_status.get("service", [])
            if isinstance(system_status, dict):
                raw_services = system_status.get("service", [])
                for svc in raw_services:
                    svc_id = svc.get("name")
                    if svc.get("status") == 1 and svc_id in KNOWN_SERVICES:
                        config = KNOWN_SERVICES[svc_id]
                        if "attributes" in config:
                            endpoints = {attr['endpoint'] for attr in config["attributes"].values()}
                            svc_data = {}
                            for ep in endpoints:
                                try:
                                    svc_data[ep] = await self.api.call_endpoint(ep)
                                except Exception as err:
                                    _LOGGER.debug("Attr fetch failed for %s at %s: %s", svc_id, ep, err)
                                    continue
                            extra_service_data[svc_id] = svc_data
                    

            now = dt_util.utcnow()
            if self._last_fw_check is None or now - self._last_fw_check > timedelta(hours=6):
                try:
                    self._cached_fw_res = await self.api.upgrade_check_firmware_online()
                    self._last_fw_check = now
                except Exception as err:
                    _LOGGER.debug("Error checking firmware: %s", err)
            
            online_clients = [c for c in clients_list if c.get("online")]
            guest_online = sum(1 for c in online_clients if c.get("type") in GUEST_CLIENT_TYPES)


            return {
                "clients": clients_list,
                "online_count": len(online_clients),
                "guest_count": guest_online,
                "lan_count": len(online_clients) - guest_online,
                "wifi": wifi_res,
                "mlo": mlo_res,
                "system": system_info,
                "system_status": system_status,
                "services": raw_services,
                "services_extra": extra_service_data,
                "fan": fan_status,
                "port_forward": port_forward,
                "upgrade_check_firmware_online": self._cached_fw_res,
                "kmwan_status": kmwan_status,
                "kmwan_config": kmwan_config,
                "cable_status": cable_status,
                "led_config": led_config,
            }

        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
