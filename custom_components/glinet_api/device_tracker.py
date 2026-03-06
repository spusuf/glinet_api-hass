"""Device Tracker platform for GL-iNet API."""
import logging
from homeassistant.components.device_tracker import SourceType
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.restore_state import RestoreEntity
from .const import DOMAIN, CONF_TRACKED_CLASSES, CONF_MAC_GROUPS, CLIENT_TYPE_MAP, DEFAULT_TRACKED, CONF_TRUSTED_MODE
from .coordinator import GLiNetDataUpdateCoordinator, _parse_mac_map, router_device_info

import re
_LOGGER = logging.getLogger(__name__)

TRACKER_DOMAIN = "device_tracker"

MAC_REGEX = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")




async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the GL-iNet device trackers."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    if coordinator.data is None:
        _LOGGER.error("Coordinator data is None; cannot set up entities yet")
        return
    tracked_canonical_macs: set[str] = set()
    mac_map = _parse_mac_map(entry)

    def update_entities():
        new_entities = []
        clients = coordinator.data.get("clients", [])
        tracked_classes = entry.options.get(
            CONF_TRACKED_CLASSES,
            entry.data.get(CONF_TRACKED_CLASSES, DEFAULT_TRACKED)
        )

        for client in clients:
            raw_mac = client.get("mac", "").lower()
            if not raw_mac:
                continue

            canonical_mac = mac_map.get(raw_mac, raw_mac)
            dclass = str(client.get("class", "")).lower()

            if canonical_mac in tracked_canonical_macs:
                continue


            if client.get("online") and dclass in tracked_classes:
                equivalent_macs: set[str] = set()
                if MAC_REGEX.match(canonical_mac):
                    equivalent_macs.add(canonical_mac)
                
                for m, target in mac_map.items():
                    if target == canonical_mac:
                        equivalent_macs.add(m)

                tracked_canonical_macs.add(canonical_mac)
                new_entities.append(
                    GLiNetDeviceTracker(coordinator, entry, canonical_mac, equivalent_macs)
                )
            else:
                _LOGGER.debug(
                    "Skipping %s: online=%s class='%s' tracked_classes=%s",
                    raw_mac, client.get("online"), dclass, tracked_classes,
                )

        return new_entities

    async_add_entities(update_entities())

    def on_coordinator_update():
        new_entities = update_entities()
        if new_entities:
            async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(on_coordinator_update))


class GLiNetDeviceTracker(CoordinatorEntity, RestoreEntity):
    """
    Device tracker for GL-iNet clients.

    Uses CoordinatorEntity + RestoreEntity instead of ScannerEntity so that
    we have full control over device_info and grouping. Each instance gets
    its own isolated HA Device card nested under the router.
    """

    def __init__(self, coordinator, entry, canonical_mac: str, macs: set[str]):
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self._entry = entry
        self._canonical_mac = canonical_mac
        self._macs = macs

        self._attr_unique_id = f"{entry.entry_id}_tracker_{canonical_mac}"
        self._attr_icon = "mdi:cellphone"

    # --- State ---

    @property
    def state(self) -> str:
        """Return 'home' if any grouped MAC is connected, else 'not_home'."""
        for client in self.coordinator.data.get("clients", []):
            if client.get("mac", "").lower() in self._macs and client.get("online"):
                return "home"
        return "not_home"

    @property
    def state_attributes(self) -> dict:
        """Expose connection details as attributes."""
        trusted = self._entry.options.get(CONF_TRUSTED_MODE, True)
        
        clean_macs = [m for m in self._macs if MAC_REGEX.match(m)]

        active = None
        for client in self.coordinator.data.get("clients", []):
            if client.get("mac", "").lower() in self._macs and client.get("online"):
                active = client
                break

        if not active:
            return {"mac_group": clean_macs} if trusted else {}

        attrs = {
            "interface": CLIENT_TYPE_MAP.get(active.get("type"), f"Unknown ({active.get('type')})"),
            "source_type": SourceType.ROUTER,
        }
        if trusted:
            attrs.update({
                "alias": active.get("alias"),
                "ip": active.get("ip"),
                "active_mac": active.get("mac"),
                "mac_group": clean_macs,
            })
        return attrs

    @property
    def name(self) -> str:
        """Return the name of the device (prefers friendly group name, then alias)."""
        if not MAC_REGEX.match(self._canonical_mac):
            return self._canonical_mac

        for client in self.coordinator.data.get("clients", []):
            if client.get("mac", "").lower() in self._macs:
                label = client.get("alias") or client.get("name")
                if label:
                    return label
        return f"Device {self._canonical_mac}"

    # --- Device Registry ---

    @property
    def device_info(self) -> dict:
        """Each client gets its own device card, nested under the router."""
        device_name = None
        device_class = None
        
        if not MAC_REGEX.match(self._canonical_mac):
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
                    elif raw_class.lower() == "smartappliances":
                        device_class = "Appliances"
                if device_name and device_class:
                    break

        info: dict = {
            "identifiers": {(DOMAIN, f"glinet_client_{self._canonical_mac}")},
            "name": device_name or f"Device {self._canonical_mac}",
            "connections": {(dr.CONNECTION_NETWORK_MAC, m) for m in self._macs if MAC_REGEX.match(m)},
            "via_device": (DOMAIN, self._entry.entry_id),
        }
        if device_class:
            info["model"] = device_class
        return info
