"""Switch platform for GL-iNet API."""
import logging
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import EntityCategory
from .const import (
    DOMAIN, KNOWN_SERVICES, CONF_TRACKED_CLASSES, CONF_MONITOR_CLASSES, 
    CONF_MAC_GROUPS, CONF_GUEST_GROUPS, DEFAULT_TRACKED, DEFAULT_MONITORED, GUEST_CLIENT_TYPES,
    CONF_TRUSTED_MODE
)
from .coordinator import router_device_info, _parse_mac_map, get_router_prefix
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

_IFACE_LABEL = {
    "wifi2g":   "2.4 GHz",
    "guest2g":  "2.4 GHz Guest",
    "wifi5g":   "5 GHz",
    "guest5g":  "5 GHz Guest",
    "wifi6g":   "6 GHz",
    "guest6g":  "6 GHz Guest",
    "mld0":     "MLO",
    "mld1":     "MLO Guest",
}

def _iface_label(iface_name: str, is_guest: bool = False) -> str:
    """Return a human-readable label for a WiFi interface name."""
    if iface_name in _IFACE_LABEL:
        return _IFACE_LABEL[iface_name]
    name = iface_name.lower()
    guest_suffix = " Guest" if is_guest else ""
    if "6g" in name: return f"6 GHz{guest_suffix}"
    if "5g" in name: return f"5 GHz{guest_suffix}"
    if "2g" in name: return f"2.4 GHz{guest_suffix}"
    if "mlo" in name or name.startswith("mld"): return f"MLO{guest_suffix}"
    return iface_name




async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the GL-iNet switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    if coordinator.data is None:
        _LOGGER.error("Coordinator data is None; cannot set up entities yet")
        return
    
    prefix = get_router_prefix(hass, entry, coordinator)
    entities = []

    wifi_config = coordinator.data.get("wifi", {})
    if wifi_config and "res" in wifi_config:
        for radio in wifi_config["res"]:
            radio_id = radio.get("device")
            for iface in radio.get("ifaces", []):
                entities.append(GLiNetWifiSwitch(coordinator, entry, radio_id, iface))

    mlo_config = coordinator.data.get("mlo", {})
    if mlo_config and "res" in mlo_config:
        for iface in mlo_config["res"].get("ifaces", []):
            entities.append(GLiNetMLOSwitch(coordinator, entry, iface))
    
    entities.append(GLiNetLEDSwitch(coordinator, entry))

    entities.extend([
        GLiNetServiceSwitch(coordinator, entry, svc["name"])
        for svc in coordinator.data.get("services", [])
        if svc["name"] in KNOWN_SERVICES
    ])

    trusted = entry.options.get(CONF_TRUSTED_MODE, entry.data.get(CONF_TRUSTED_MODE, True))
    port_forwards = coordinator.data.get("port_forward", [])
    if isinstance(port_forwards, dict):
        port_forwards = port_forwards.get("res", [])
        
    # for rule in port_forwards:
    #     entities.append(GLiNetPortForwardSwitch(coordinator, entry, rule))

    # --- Client Blocking Switches (Commented out until fix found) ---
    # tracked_block_switches = set()
    # mac_map = _parse_mac_map(entry)
    # guest_map = _parse_mac_map(entry, CONF_GUEST_GROUPS)
    
    # def _build_client_switches():
    #     new_switches = []
    #     clients = coordinator.data.get("clients", [])
        
    #     tracked_presence = entry.options.get(CONF_TRACKED_CLASSES, entry.data.get(CONF_TRACKED_CLASSES, DEFAULT_TRACKED))
    #     monitor_classes = entry.options.get(CONF_MONITOR_CLASSES, entry.data.get(CONF_MONITOR_CLASSES, DEFAULT_MONITORED))
    #     all_classes = set(tracked_presence) | set(monitor_classes)

    #     for client in clients:
    #         raw_mac = client.get("mac", "").lower()
    #         if not raw_mac or not client.get("online"):
    #             continue
            
    #         dclass = str(client.get("class", "")).lower()
    #         is_guest_wifi = client.get("type") in GUEST_CLIENT_TYPES
    #         is_in_group = raw_mac in mac_map or raw_mac in guest_map
            
    #         if not (dclass in all_classes or is_guest_wifi or is_in_group):
    #             continue
            
    #         canonical_mac = mac_map.get(raw_mac, guest_map.get(raw_mac, raw_mac))
    #         if canonical_mac in tracked_block_switches:
    #             continue
            
    #         equivalent_macs = {canonical_mac}
    #         combined_mac_list = list(mac_map.items()) + list(guest_map.items())
    #         for m, t in combined_mac_list:
    #             if t == canonical_mac:
    #                 equivalent_macs.add(m)
            
    #         tracked_block_switches.add(canonical_mac)
    #         new_switches.append(GLiNetClientBlockSwitch(coordinator, entry, canonical_mac, equivalent_macs))
    #     return new_switches

    # entities.extend(_build_client_switches())
    for entity in entities:
        entity._attr_has_entity_name = True
        obj_id = slugify(entity.name)
        entity.entity_id = f"switch.{prefix}_{obj_id}"

    async_add_entities(entities)



class GLiNetLEDSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for LED."""
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._entry = entry
        self._attr_name = "Lights"
        self._attr_unique_id = f"{entry.entry_id}_led"
        self._attr_entity_category = EntityCategory.CONFIG


    @property
    def is_on(self):
        """Return true if switch is on."""
        return self._coordinator.data.get("led_config", {}).get("led_enable", False)

    @property
    def icon(self):
        """Return the icon based on state."""
        return "mdi:led-on" if self.is_on else "mdi:led-off"

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._coordinator.api.led_set_config(True)
        await self._coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._coordinator.api.led_set_config(False)
        await self._coordinator.async_request_refresh()

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)


class GLiNetWifiSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for standard WiFi interfaces."""
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry, radio_id, iface):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._entry = entry
        self._radio_id = radio_id
        self._iface_name = iface.get("name")
        self._is_guest = iface.get("guest", False)
        label = _iface_label(self._iface_name, self._is_guest)
        self._attr_name = f"WiFi {label}"
        self._attr_unique_id = f"{entry.entry_id}_{self._radio_id}_{self._iface_name}"
        self._attr_icon = "mdi:wifi" if self._is_guest else "mdi:wifi-lock"
        self._attr_entity_category = EntityCategory.CONFIG

    def _get_wifi_data(self):
        res = self._coordinator.data.get("wifi", {}).get("res", [])
        for radio in res:
            if radio.get("device") == self._radio_id:
                ifaces = radio.get("ifaces", [])
                for iface in ifaces:
                    if iface.get("name") == self._iface_name:
                        return radio, iface
        return {}, {}

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        radio, iface = self._get_wifi_data()
        raw_channel = radio.get("channel", "Unknown")
        if raw_channel == 0:
            channel = "auto"
        else:
            channel = raw_channel

        mode = radio.get("hwmode", "Unknown")
        clean_mode = "Unknown"
        model_label = "Unknown"

        if mode and mode.startswith("11"):
            clean_mode = mode[2:]


        if "bn" in clean_mode:
            mode_label = "Wi-Fi 8"
        elif "be" in clean_mode:
            mode_label = "Wi-Fi 7"
        elif "ax" in clean_mode:
            mode_label = "Wi-Fi 6"
        elif "ac" in clean_mode:
            mode_label = "Wi-Fi 5"
        elif "n" in clean_mode:
            mode_label = "Wi-Fi 4"
        elif "g" in clean_mode:
            mode_label = "Wi-Fi 3"
        elif "a" in clean_mode:
            mode_label = "Wi-Fi 2G"
        elif "b" in clean_mode:
            mode_label = "Wi-Fi 2"
        else:
            mode_label = f"Legacy ({clean_mode.upper()})"

        trusted = self._entry.options.get(CONF_TRUSTED_MODE, True)
        attrs = {
            "Channel": channel,
            "Interface Name": self._iface_name,
            "Bandwidth (MHz)": radio.get("htmode", "Unknown"),
            "AP Mode": mode_label,
            "All Modes": clean_mode,
            "Hidden": iface.get("hidden", False),
            "Guest": self._is_guest,
        }
        if trusted:
            attrs["SSID"] = iface.get("ssid", "Unknown")
            attrs["Password"] = iface.get("key", "Unknown")
        return attrs

    @property
    def is_on(self):
        """Return true if switch is on."""
        _, iface = self._get_wifi_data()
        return iface.get("enabled", False)

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._coordinator.api.set_wifi_iface(self._radio_id, self._iface_name, True)
        await self._coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._coordinator.api.set_wifi_iface(self._radio_id, self._iface_name, False)
        await self._coordinator.async_request_refresh()

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)


class GLiNetMLOSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for MLO interfaces."""
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry, iface):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._entry = entry
        self._iface_name = iface.get("name")
        self._is_guest = iface.get("guest", False)
        label = _iface_label(self._iface_name, self._is_guest)
        self._attr_name = f"WiFi {label}"
        self._attr_unique_id = f"{entry.entry_id}_mlo_{self._iface_name}"
        self._attr_icon = "mdi:wifi-plus"
        self._attr_entity_category = EntityCategory.CONFIG

    def _get_mlo_data(self):
        """Helper to find this specific MLO interface data."""
        mlo_res = self._coordinator.data.get("mlo", {}).get("res", {})
        for iface in mlo_res.get("ifaces", []):
            if iface.get("name") == self._iface_name:
                return iface
        return {}

    @property
    def extra_state_attributes(self):
        """Return technical MLO details as attributes."""
        iface = self._get_mlo_data()
        if not iface:
            return {"Interface": self._iface_name, "Status": "Unavailable"}

        bands = iface.get("mlo_band", [])
        combined_bands = ", ".join(bands).upper() if bands else "None"

        trusted = self._entry.options.get(CONF_TRUSTED_MODE, True)
        attrs = {
            "Bands": combined_bands,
            "Interface Name": self._iface_name,
            "Guest": self._is_guest,
            "Hidden": iface.get("hidden", False), 
        }
        if trusted:
            attrs["SSID"] = iface.get("ssid", "Unknown")
            attrs["Password"] = iface.get("key", "Unknown")
        return attrs

    @property
    def is_on(self):
        """Return true if switch is on."""
        iface = self._get_mlo_data()
        return iface.get("mlo_enable", False)

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._coordinator.api.set_mlo_status(self._iface_name, True)
        await self._coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._coordinator.api.set_mlo_status(self._iface_name, False)
        await self._coordinator.async_request_refresh()

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)


class GLiNetServiceSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, svc_id):
        super().__init__(coordinator)
        self._coordinator = coordinator
        self._entry = entry
        self.svc_id = svc_id
        self._config = KNOWN_SERVICES[svc_id]
        self._attr_name = self._config.get("name", svc_id.title())
        self._attr_unique_id = f"{entry.entry_id}_{svc_id}_switch"
        self._attr_icon = self._config.get("icon", "mdi:toggle-switch")
        self._optimistic_on: bool | None = None

    def _real_state(self) -> bool:
        """Return the current state from coordinator data."""
        for s in self.coordinator.data.get("services", []):
            if s["name"] == self.svc_id:
                return s["status"] == 1
        return False

    @property
    def is_on(self) -> bool:
        if self._optimistic_on is not None:
            return self._optimistic_on
        return self._real_state()

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state once coordinator agrees with what we intended."""
        if self._optimistic_on is not None:
            real = self._real_state()
            if real == self._optimistic_on:
                self._optimistic_on = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs):
        action = self._config["actions"]["on"]
        await self.coordinator.api.call_endpoint(action["endpoint"], action["payload"])
        self._optimistic_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        action = self._config["actions"]["off"]
        await self.coordinator.api.call_endpoint(action["endpoint"], action["payload"])
        self._optimistic_on = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        """Pluck extra attributes from the services_extra cache."""
        attrs = {}
        extras = self.coordinator.data.get("services_extra", {}).get(self.svc_id, {})
        trusted = self._entry.options.get(CONF_TRUSTED_MODE, True)
        
        for attr_key, cfg in self._config.get("attributes", {}).items():
            endpoint_data = extras.get(cfg["endpoint"], {})
            val = endpoint_data.get(cfg["attribute"])
            if val is not None:
                is_sensitive = any(k in attr_key.lower() for k in ["ip", "password", "ssid", "port"])
                if trusted or not is_sensitive:
                    attrs[attr_key.replace("_", " ").title()] = val
        return attrs

    @property
    def device_info(self):
        return router_device_info(self._entry, self._coordinator)


class GLiNetPortForwardSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for Port Forward rules."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, rule):
        """Initialize the switch."""
        super().__init__(coordinator)
        self._entry = entry
        self._rule_id = rule.get("id")
        
        rule_name = rule.get("name")
        if rule_name and rule_name.strip() != "":
            name = f"Port {rule.get('src_dport')} ({rule_name.strip()})"
        else:
            name = f"Port {rule.get('src_dport')}"
        
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_port_forward_{self._rule_id}"
        self._attr_icon = "mdi:router-network"
        self._attr_entity_category = EntityCategory.CONFIG
        
        self._optimistic_on: bool | None = None

    def _get_rule_data(self):
        """Find the current rule data in coordinator."""
        pfs = self.coordinator.data.get("port_forward", [])
        if isinstance(pfs, dict):
            pfs = pfs.get("res", [])
        for r in pfs:
            if r.get("id") == self._rule_id:
                return r
        return {}

    @property
    def is_on(self) -> bool:
        if self._optimistic_on is not None:
            return self._optimistic_on
        return self._get_rule_data().get("enabled", False)

    def _handle_coordinator_update(self) -> None:
        if self._optimistic_on is not None:
            real = self._get_rule_data().get("enabled")
            if real == self._optimistic_on:
                self._optimistic_on = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs):
        rule = self._get_rule_data().copy()
        if not rule:
            return
        rule["enabled"] = True
        await self.coordinator.api.firewall_set_port_forward(rule)
        self._optimistic_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        rule = self._get_rule_data().copy()
        if not rule:
            return
        rule["enabled"] = False
        await self.coordinator.api.firewall_set_port_forward(rule)
        self._optimistic_on = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @property
    def extra_state_attributes(self):
        rule = self._get_rule_data()
        trusted = self._entry.options.get(CONF_TRUSTED_MODE, True)
        attrs = {
            "External Port": rule.get("src_dport"),
            "Internal Port": rule.get("dest_port"),
            "Protocol": rule.get("proto"),
            "Zones": f"{rule.get('src', '')} -> {rule.get('dest', '')}",
        }
        if trusted:
            attrs["Internal IP"] = rule.get("dest_ip")
        return attrs

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)


class GLiNetClientBlockSwitch(CoordinatorEntity, SwitchEntity):
    """Switch to block/unblock a client's internet access."""
    _attr_has_entity_name = True
    
    def __init__(self, coordinator, entry, canonical_mac, macs):
        super().__init__(coordinator)
        self._entry = entry
        self._canonical_mac = canonical_mac
        self._macs = macs
        self._attr_name = "Block Internet"
        self._attr_unique_id = f"{entry.entry_id}_block_{canonical_mac}"
        self._attr_icon = "mdi:web-off"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        """Return True if the client is currently BLOCKED."""
        for client in self.coordinator.data.get("clients", []):
            if client.get("mac", "").lower() in self._macs:
                if client.get("blocked"):
                    return True
        return False

    async def async_turn_on(self, **kwargs):
        """Block the client."""
        import asyncio
        tasks = [self.coordinator.api.set_client_block(m, True) for m in self._macs if ":" in m]
        if tasks:
            await asyncio.gather(*tasks)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Unblock the client."""
        import asyncio
        tasks = [self.coordinator.api.set_client_block(m, False) for m in self._macs if ":" in m]
        if tasks:
            await asyncio.gather(*tasks)
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self) -> dict:
        """Link this switch to the same identity as the tracker."""
        device_name = None
        device_class = None
        import re
        mac_regex = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")
        if not mac_regex.match(self._canonical_mac):
            device_name = self._canonical_mac

        for client in self.coordinator.data.get("clients", []):
            if client.get("mac", "").lower() in self._macs:
                if not device_name:
                    device_name = client.get("alias") or client.get("name")
                raw_class = client.get("class", "")
                if raw_class:
                    device_class = raw_class.capitalize()
                    if raw_class.lower() == "nas":
                        device_class = "NAS"
                if device_name and device_class:
                    break

        from homeassistant.helpers import device_registry as dr
        info = {
            "identifiers": {(DOMAIN, f"glinet_client_{self._canonical_mac}")},
            "name": device_name or f"Device {self._canonical_mac}",
            "connections": {(dr.CONNECTION_NETWORK_MAC, m) for m in self._macs if mac_regex.match(m)},
            "via_device": (DOMAIN, self._entry.entry_id),
        }
        if device_class:
            info["model"] = device_class
        return info
