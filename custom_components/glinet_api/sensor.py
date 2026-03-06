"""Platform for sensor integration."""
import logging
from datetime import timedelta
import homeassistant.util.dt as dt_util
from homeassistant.const import PERCENTAGE, UnitOfInformation, UnitOfDataRate
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import device_registry as dr
from .const import (
    DOMAIN, MODEL_MAP, CONF_TRACKED_CLASSES, CONF_MONITOR_CLASSES, 
    CONF_MAC_GROUPS, CONF_GUEST_GROUPS, MAX_FAN_SPEED, KNOWN_SERVICES, 
    CLIENT_TYPE_MAP, DEFAULT_MONITORED, DEFAULT_TRACKED, GUEST_CLIENT_TYPES,
    CONF_TRUSTED_MODE
)

_LOGGER = logging.getLogger(__name__)


from .coordinator import (
    GLiNetDataUpdateCoordinator, 
    _parse_mac_map, 
    router_device_info,
    get_router_prefix
)
from homeassistant.util import slugify


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Configures sensors based on GL-iNet data."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    if coordinator.data is None:
        _LOGGER.error("Coordinator data is None; cannot set up entities yet")
        return

    prefix = get_router_prefix(hass, entry, coordinator)
    mac_map = _parse_mac_map(entry)
    guest_map = _parse_mac_map(entry, CONF_GUEST_GROUPS)
    tracked_monitor_macs: set[str] = set()

    sensors = [
        GLiNetStatusSensor(coordinator, entry),
        GLiNetLANSensor(coordinator, entry),
        GLiNetGuestSensor(coordinator, entry),
        GLiNetPeopleHomeSensor(coordinator, entry, mac_map),
        GLiNetGuestCountSensor(coordinator, entry, guest_map),
        GLiNetCPUSensor(coordinator, entry),
        GLiNetMemorySensor(coordinator, entry),
        GLiNetStorageSensor(coordinator, entry),
        GLiNetUptimeSensor(coordinator, entry),
        GLiNetFanSensor(coordinator, entry),
        GLiNetTemperatureSensor(coordinator, entry),
        GLiNetFirmwareUpdateSensor(coordinator, entry),
        GLiNetWANStatusSensor(coordinator, entry),
    ]

    if mac_map:
        groups = set(mac_map.values())
        for group_name in groups:
            sensors.append(GLiNetMACGroupSensor(coordinator, entry, group_name, mac_map))

    sensors.extend([
        GLiNetServiceStatusSensor(coordinator, entry, svc["name"])
        for svc in coordinator.data.get("services", [])
        if svc["name"] not in KNOWN_SERVICES
    ])
    for sensor in sensors:
        sensor._attr_has_entity_name = True
        if not isinstance(sensor, GLiNetMACGroupSensor):
            obj_id = slugify(sensor.name)
            sensor.entity_id = f"sensor.{prefix}_{obj_id}"

    async_add_entities(sensors)

    def _build_client_sensors():
        new_entities = []
        
        tracked_presence = entry.options.get(CONF_TRACKED_CLASSES, entry.data.get(CONF_TRACKED_CLASSES, DEFAULT_TRACKED))
        monitor_classes = entry.options.get(CONF_MONITOR_CLASSES, entry.data.get(CONF_MONITOR_CLASSES, DEFAULT_MONITORED))
        
        all_classes = set(tracked_presence) | set(monitor_classes)

        clients = coordinator.data.get("clients", []) if coordinator.data else []
        for client in clients:
            raw_mac = client.get("mac", "").lower()
            if not raw_mac:
                continue
            
            dclass = str(client.get("class", "")).lower()
            if dclass not in all_classes:
                is_guest_wifi = client.get("type") in GUEST_CLIENT_TYPES
                is_in_group = raw_mac in mac_map or raw_mac in guest_map
                if not (is_guest_wifi or is_in_group):
                    continue

            if not client.get("online"):
                continue

            canonical_mac = mac_map.get(raw_mac, guest_map.get(raw_mac, raw_mac))
            equivalent_macs: set[str] = {canonical_mac}
            combined_mac_list = list(mac_map.items()) + list(guest_map.items())
            for m, t in combined_mac_list:
                if t == canonical_mac:
                    equivalent_macs.add(m)

            if dclass in monitor_classes and canonical_mac not in tracked_monitor_macs:
                sensor = GLiNetMonitorSensor(coordinator, entry, canonical_mac, equivalent_macs)
                sensor._attr_has_entity_name = True
                new_entities.append(sensor)
                tracked_monitor_macs.add(canonical_mac)

            traffic_key = f"traffic_{canonical_mac}"
            if traffic_key not in tracked_monitor_macs:
                new_entities.append(GLiNetClientTrafficSensor(coordinator, entry, canonical_mac, equivalent_macs, "total_rx"))
                new_entities.append(GLiNetClientTrafficSensor(coordinator, entry, canonical_mac, equivalent_macs, "total_tx"))
                new_entities.append(GLiNetClientTrafficSensor(coordinator, entry, canonical_mac, equivalent_macs, "rx"))
                new_entities.append(GLiNetClientTrafficSensor(coordinator, entry, canonical_mac, equivalent_macs, "tx"))
                tracked_monitor_macs.add(traffic_key)

        return new_entities

    initial_dynamic = _build_client_sensors()
    if initial_dynamic:
        async_add_entities(initial_dynamic)

    def _on_coordinator_update():
        new_dynamic = _build_client_sensors()
        if new_dynamic:
            async_add_entities(new_dynamic)

    entry.async_on_unload(coordinator.async_add_listener(_on_coordinator_update))


class GLiNetStatusSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    """Total online clients (all bands including guest)."""
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "clients"
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Total Clients"
        self._attr_unique_id = f"glinet_api_{entry.entry_id}_online"
        self._attr_icon = "mdi:devices"

    @property
    def native_value(self):
        return self.coordinator.data.get("online_count", 0)

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)

    @property
    def extra_state_attributes(self):
        return {}


class GLiNetLANSensor(CoordinatorEntity, SensorEntity):
    """Online clients on main (non-guest) WiFi bands and wired connections."""
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "clients"
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "LAN Clients"
        self._attr_unique_id = f"glinet_api_{entry.entry_id}_lan"
        self._attr_icon = "mdi:lan-connect"

    @property
    def native_value(self):
        val = self.coordinator.data.get("lan_count", 0)
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)

    @property
    def extra_state_attributes(self):
        return {}


class GLiNetGuestSensor(CoordinatorEntity, SensorEntity):
    """Online clients connected to any guest WiFi network."""
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "clients"
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry):
        """Initializes the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Guest Clients"
        self._attr_unique_id = f"glinet_api_{entry.entry_id}_guest"
        self._attr_icon = "mdi:lan-disconnect"

    @property
    def native_value(self):
        val = self.coordinator.data.get("guest_count", 0)
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)

    @property
    def extra_state_attributes(self):
        return {}

class GLiNetFanSensor(CoordinatorEntity, SensorEntity):
    """Fan speed sensor."""
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Fan Speed"
        self._attr_unique_id = f"glinet_api_{entry.entry_id}_fan"
        self._attr_icon = "mdi:fan"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        fan_data = self.coordinator.data.get("fan", {})
        speed = fan_data.get("speed")
        if speed is None:
            return 0
        return round(speed / MAX_FAN_SPEED * 100, 2)

    @property
    def suggested_display_precision(self) -> int:
        """Return the number of decimal places to show in the UI."""
        return 0

    @property
    def extra_state_attributes(self):
        fan_data = self.coordinator.data.get("fan", {})
        return {
            "Speed (rpm)": fan_data.get("speed"),
            "Max Speed (rpm)": MAX_FAN_SPEED,
        }

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)

class GLiNetTemperatureSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    """Temperature sensor."""
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Temperature"
        self._attr_unique_id = f"glinet_api_{entry.entry_id}_temperature"
        self._attr_icon = "mdi:thermometer"
        self._attr_native_unit_of_measurement = "°C"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        sys_stat = self.coordinator.data.get("system_status", {}).get("system", {})
        cpu_stats = sys_stat.get("cpu", {})
        return cpu_stats.get("temperature")

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)


class GLiNetCPUSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "CPU Usage"
        self._attr_unique_id = f"glinet_api_cpu_{entry.entry_id}"
        self._attr_icon = "mdi:cpu-64-bit"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        sys_stat = self.coordinator.data.get("system_status", {}).get("system", {})
        load = sys_stat.get("load_average", [])
        sys_info = self.coordinator.data.get("system", {})
        cores = sys_info.get("cpu_num", 1)
        if load and cores > 0:
            return round((float(load[0]) / int(cores)) * 100, 4)
        return None

    @property
    def suggested_display_precision(self) -> int:
        """Return the number of decimal places to show in the UI."""
        return 0

    @property
    def extra_state_attributes(self):
        sys_info = self.coordinator.data.get("system", {})
        sys_stat = self.coordinator.data.get("system_status", {}).get("system", {})
        load = sys_stat.get("load_average", [])
        cores = sys_info.get("cpu_num", 0)
        if len(load) >= 3:
            return {
                "Cores": cores,
                "Architecture": sys_info.get("board_info", {}).get("architecture", ""),
                "1m Load": load[0],
                "5m Load": load[1],
                "15m Load": load[2],

            }
        return {}

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)

class GLiNetMemorySensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Memory Usage"
        self._attr_unique_id = f"glinet_api_{entry.entry_id}_memory"
        self._attr_icon = "mdi:memory"
        self._attr_native_unit_of_measurement = "%"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        sys_stat = self.coordinator.data.get("system_status", {}).get("system", {})
        total = sys_stat.get("memory_total", 0)
        free = sys_stat.get("memory_free", 0)
        cache = sys_stat.get("memory_buff_cache", 0)
        if total > 0:
            used = total - free - cache
            return round((used / total) * 100)
        return None

    @property
    def extra_state_attributes(self):
        sys_stat = self.coordinator.data.get("system_status", {}).get("system", {})
        total = sys_stat.get("memory_total", 0)
        free = sys_stat.get("memory_free", 0)
        cache = sys_stat.get("memory_buff_cache", 0)
        used = total - free - cache
        return {"Used (MB)": round(used / 1024**2, 2), "Total (MB)": round(total / 1024**2, 2), "Free (MB)": round(free / 1024**2, 2), "Cache (MB)": round(cache / 1024**2, 2)}

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)

class GLiNetStorageSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "eMMC Usage"
        self._attr_unique_id = f"glinet_api_{entry.entry_id}_storage"
        self._attr_icon = "mdi:harddisk"
        self._attr_native_unit_of_measurement = "%"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        sys_stat = self.coordinator.data.get("system_status", {}).get("system", {})
        total = sys_stat.get("flash_total", 0)
        free = sys_stat.get("flash_free", 0)
        if total > 0:
            return round(((total - free) / total) * 100)
        return None

    @property
    def extra_state_attributes(self):
        sys_stat = self.coordinator.data.get("system_status", {}).get("system", {})
        total = sys_stat.get("flash_total", 0)
        free = sys_stat.get("flash_free", 0)
        return {"Used (GB)": round((total - free) / 1024**3, 2), "Total (GB)": round(total / 1024**3, 2), "Free (GB)": round(free / 1024**3, 2)}

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)

class GLiNetUptimeSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Uptime"
        self._attr_unique_id = f"glinet_api_{entry.entry_id}_uptime"
        self._attr_icon = "mdi:clock-outline"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        sys_stat = self.coordinator.data.get("system_status", {}).get("system", {})
        uptime = sys_stat.get("uptime", 0)
        if uptime is None:
            return None
        boot_time = dt_util.utcnow() - timedelta(seconds=float(uptime))
        return boot_time

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)

class GLiNetFirmwareUpdateSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Firmware"
        self._attr_unique_id = f"glinet_api_{entry.entry_id}_firmware"
        self._attr_icon = "mdi:update"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        fw_check = self.coordinator.data.get("upgrade_check_firmware_online")
        if not fw_check or isinstance(fw_check, Exception):
            return "Unknown"
        
        current_fw = fw_check.get("current_version")
        latest_fw = fw_check.get("version_new")

        if not latest_fw or latest_fw == current_fw:
            return "Up to date"
            
        return "Update available"

    @property
    def extra_state_attributes(self):
        fw_check = self.coordinator.data.get("upgrade_check_firmware_online", {})
        sys_info = self.coordinator.data.get("system", {})
        current_version = fw_check.get("current_version")
        latest_version = fw_check.get("version_new")
        
        attrs = {
            "OpenWRT Version": sys_info.get("board_info", {}).get("openwrt_version", ""),
            "Current Version": current_version,
        }
        if latest_version:
            attrs["New Version"] = latest_version
            attrs["Type"] = fw_check.get("firmware_type", "")
            attrs["Release Date"] = fw_check.get("new_compile_time", "")
            attrs["Prompt"] = fw_check.get("prompt", "")
            attrs["Release Notes"] = fw_check.get("release_note", "")
            
        return attrs

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)

class GLiNetWANStatusSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Internet"
        self._attr_unique_id = f"glinet_api_{entry.entry_id}_internet"
        self._attr_icon = "mdi:wan"

    @property
    def native_value(self):
        kmwan_status = self.coordinator.data.get("kmwan_status", {})
        kmwan_config = self.coordinator.data.get("kmwan_config", {})

        interfaces = kmwan_status.get("interfaces", [])
        mode = kmwan_config.get("mode")

        online_interfaces = [i.get("interface") for i in interfaces if i.get("status_v4") == 0]
        primary_online = any(iface in ["wan", "wan6"] for iface in online_interfaces)
        secondary_online = any(iface not in ["wan", "wan6"] for iface in online_interfaces)
        
        if not online_interfaces:
            return "Offline"
        if not primary_online and secondary_online:
            return "Fallback"
        if mode == 1 and primary_online and secondary_online:
            return "MultiWAN"
        if primary_online:
            return "Online"
        else:
            return "Unknown"

    @property
    def extra_state_attributes(self):
        attrs = {}

        kmwan_status = self.coordinator.data.get("kmwan_status", {})
        kmwan_config = self.coordinator.data.get("kmwan_config", {})
        cable_status = self.coordinator.data.get("cable_status", {})

        interfaces = kmwan_status.get("interfaces", [])
        online_interfaces = [i.get("interface") for i in interfaces if i.get("status_v4") == 0]
        status_map = {0: "Online", 1: "Offline", 2: "Error"}
        
        connection_map = {
            "wan": "WAN",
            "secondwan": "LAN1 (Second WAN)",
            "wwan": "Repeater (Wireless WAN)",
            "modem_1_1_2": "Cellular Modem",
            "tethering": "USB Tethering",
            "": "Unknown"
        }
        
        attrs["Primary Interface"] = online_interfaces[0] if online_interfaces else "None"
        
        trusted = self._entry.options.get(CONF_TRUSTED_MODE, True)
        if trusted:
            ipv4_raw = cable_status.get("ipv4", {}).get("ip", "Unavailable")
            attrs["IPv4 Address"] = ipv4_raw.split('/')[0] if ipv4_raw != "Unavailable" else ipv4_raw

            ipv6_raw = cable_status.get("ipv6", [])
            if isinstance(ipv6_raw, list) and len(ipv6_raw) > 0:
                ipv6_raw = ipv6_raw[0].get("ip", "Unavailable")
                attrs["IPv6 Address"] = ipv6_raw.split('/')[0] if ipv6_raw != "Unavailable" else ipv6_raw
            else:
                attrs["IPv6 Address"] = "Unavailable"
        
        mode = kmwan_config.get("mode")
        mode_map = {0: "Failover", 1: "Load Balancing"}
        attrs["MultiWAN Mode"] = mode_map.get(mode, f"Unknown ({mode})")
        
        for iface in interfaces:
            name = iface.get("interface", "")
            friendly_name = connection_map.get(name, name)
            s_v4 = iface.get("status_v4", 1)
            attrs[f"{friendly_name}"] = status_map.get(s_v4, f"Unknown ({s_v4})")


        return attrs

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)



class GLiNetServiceStatusSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, svc_id):
        super().__init__(coordinator)
        self.svc_id = svc_id
        self._coordinator = coordinator
        self._entry = entry
        self._attr_name = f"{svc_id.replace('_', ' ').title()}"
        self._attr_unique_id = f"{entry.entry_id}_{svc_id}"
        self._attr_icon = "mdi:server-network"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        """Return 'On' or 'Off' based on the status integer."""
        for s in self.coordinator.data.get("services", []):
            if s["name"] == self.svc_id:
                return "On" if s["status"] == 1 else "Off"
        return "Unknown"

    @property
    def device_info(self):
        return router_device_info(self._entry, self._coordinator)


class GLiNetPeopleHomeSensor(CoordinatorEntity, SensorEntity):
    """Count of unique canonical devices from tracked presence classes that are online."""
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "people"
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, mac_map):
        super().__init__(coordinator)
        self._entry = entry
        self._mac_map = mac_map
        self._attr_name = "People Home"
        self._attr_unique_id = f"{entry.entry_id}_people_home"
        self._attr_icon = "mdi:account-group"

    @property
    def native_value(self):
        from .const import CONF_TRACKED_CLASSES, DEFAULT_TRACKED
        tracked_classes = self._entry.options.get(
            CONF_TRACKED_CLASSES, 
            self._entry.data.get(CONF_TRACKED_CLASSES, DEFAULT_TRACKED)
        )
        
        online_canonical_macs = set()
        clients = self.coordinator.data.get("clients", [])
        for client in clients:
            if not client.get("online"):
                continue
            dclass = str(client.get("class", "")).lower()
            if dclass in tracked_classes:
                raw_mac = client.get("mac", "").lower()
                canonical_mac = self._mac_map.get(raw_mac, raw_mac)
                online_canonical_macs.add(canonical_mac)
        
        return len(online_canonical_macs)

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)


class GLiNetGuestCountSensor(CoordinatorEntity, SensorEntity):
    """Count of unique canonical guest devices (from Guest MAC groups or Guest WiFi) that are online."""
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "guests"
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, guest_map):
        super().__init__(coordinator)
        self._entry = entry
        self._guest_map = guest_map
        self._attr_name = "Guest Count"
        self._attr_unique_id = f"{entry.entry_id}_guest_count"
        self._attr_icon = "mdi:account-plus"

    @property
    def native_value(self):
        online_canonical_guests = set()
        clients = self.coordinator.data.get("clients", [])
        for client in clients:
            if not client.get("online"):
                continue
            
            raw_mac = client.get("mac", "").lower()
            is_guest_wifi = client.get("type") in GUEST_CLIENT_TYPES
            
            if is_guest_wifi or raw_mac in self._guest_map:
                canonical_mac = self._guest_map.get(raw_mac, raw_mac)
                online_canonical_guests.add(canonical_mac)
        
        return len(online_canonical_guests)

    @property
    def device_info(self):
        return router_device_info(self._entry, self.coordinator)


class GLiNetMACGroupSensor(CoordinatorEntity, SensorEntity):
    """Presence sensor that attaches to the specific device's own page."""

    def __init__(self, coordinator, entry, group_name, mac_map):
        super().__init__(coordinator)
        self._entry = entry
        self._group_name = group_name
        self._mac_map = mac_map
        self._member_macs = {m for m, target in mac_map.items() if target == group_name}
        
        self._attr_name = "Presence"
        self._attr_unique_id = f"{entry.entry_id}_presence_{group_name.lower()}"
        self._attr_icon = "mdi:account-check"

    @property
    def native_value(self):
        clients = self.coordinator.data.get("clients", [])
        for client in clients:
            if client.get("mac", "").lower() in self._member_macs and client.get("online"):
                return "Home"
        return "Away"

    @property
    def device_info(self) -> dict:
        """Link this sensor to the same identity as the tracker."""
        return {
            "identifiers": {(DOMAIN, f"glinet_client_{self._group_name.lower()}")},
            "name": self._group_name.upper(),
            "connections": {(dr.CONNECTION_NETWORK_MAC, m) for m in self._member_macs},
            "via_device": (DOMAIN, self._entry.entry_id),
        }


class GLiNetMonitorSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing Online/Offline for a smart-appliance class device.

    Unlike device_tracker entities (which always show 'Home'/'Away'),
    this sensor shows 'Online' or 'Offline' — more meaningful for things
    like TVs, printers, and smart-home gear.
    """

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["Online", "Offline"]
    _attr_icon = "mdi:connection"

    def __init__(self, coordinator, entry, canonical_mac: str, macs: set[str]):
        super().__init__(coordinator)
        self._entry = entry
        self._canonical_mac = canonical_mac
        self._macs = macs
        self._attr_name = "Connection"
        self._attr_unique_id = f"{entry.entry_id}_connection_{canonical_mac}"

    def _get_client(self):
        """Return the active client record for this MAC group, or None."""
        for client in self.coordinator.data.get("clients", []):
            if client.get("mac", "").lower() in self._macs:
                return client
        return None

    @property
    def native_value(self) -> str:
        client = self._get_client()
        if client and client.get("online"):
            return "Online"
        return "Offline"

    @property
    def extra_state_attributes(self) -> dict:
        client = self._get_client()
        trusted = self._entry.options.get(CONF_TRUSTED_MODE, True)
        if not client:
            return {"mac": self._canonical_mac} if trusted else {}
            
        attrs = {
            "interface": CLIENT_TYPE_MAP.get(client.get("type"), f"Unknown ({client.get('type')})"),
            "online_since": client.get("online_time"),
        }
        if trusted:
            attrs.update({
                "hostname": client.get("name"),
                "alias": client.get("alias"),
                "ip": client.get("ip"),
                "mac": client.get("mac"),
            })
        return attrs

    @property
    def device_info(self) -> dict:
        """Each client gets its own device card, nested under the router."""
        client = self._get_client()
        device_name = None
        device_class = None
        if client:
            device_name = client.get("alias") or client.get("name")
            raw_class = client.get("class", "")
            if raw_class:
                device_class = raw_class.capitalize()
                if raw_class.lower() == "nas":
                    device_class = "NAS"

        info = {
            "identifiers": {(DOMAIN, f"glinet_client_{self._canonical_mac}")},
            "name": device_name or f"Monitored {self._canonical_mac}",
            "connections": {(dr.CONNECTION_NETWORK_MAC, m) for m in self._macs},
            "via_device": (DOMAIN, self._entry.entry_id),
        }
        if device_class:
            info["model"] = device_class
        else:
            info["model"] = "Monitored Client"
        return info


class GLiNetClientTrafficSensor(CoordinatorEntity, SensorEntity):
    """Aggregate traffic sensor for a (potentially grouped) client device."""
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, canonical_mac: str, macs: set[str], key: str):
        super().__init__(coordinator)
        self._entry = entry
        self._canonical_mac = canonical_mac
        self._macs = macs
        self._key = key
        
        titles = {
            "total_tx": "Data Downloaded",
            "total_rx": "Data Uploaded",
            "tx": "Download Speed",
            "rx": "Upload Speed",
        }
        icons = {
            "total_tx": "mdi:download",
            "total_rx": "mdi:upload",
            "tx": "mdi:transfer-down",
            "rx": "mdi:transfer-up"
        }
        units = {
            "total_tx": "GB",
            "total_rx": "GB",
            "tx": "MB/s",
            "rx": "MB/s"
        }
        
        self._attr_name = titles.get(key)
        self._attr_unique_id = f"{entry.entry_id}_{key}_{canonical_mac}"
        self._attr_icon = icons.get(key)
        self._attr_native_unit_of_measurement = units.get(key)
        
        if "total" in key:
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_device_class = SensorDeviceClass.DATA_SIZE
            self._attr_suggested_display_precision = 1
        else:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_device_class = SensorDeviceClass.DATA_RATE
            self._attr_suggested_display_precision = 1

    @property
    def native_value(self):
        """Sum the traffic values across all MACs in the group."""
        total = 0.0
        found = False
        for client in self.coordinator.data.get("clients", []):
            if client.get("mac", "").lower() in self._macs:
                val = client.get(self._key, 0)
                try:
                    total += float(val)
                    found = True
                except (ValueError, TypeError):
                    pass
        
        if "total" in self._key:
            # API returns Bytes for totals -> Convert to GB
            return total / (1024**3)
        else:
            # API returns reported speed (Bytes/s) -> Convert to MB/s
            return total / (1024**2)

    @property
    def extra_state_attributes(self) -> dict:
        """Return speed in Megabits per second in attributes."""
        if "total" in self._key:
            return {}
        
        # recalculate based on raw value for attributes
        total = 0.0
        for client in self.coordinator.data.get("clients", []):
            if client.get("mac", "").lower() in self._macs:
                total += float(client.get(self._key, 0))
        
        # Convert Bytes/s to Mbps
        mbps = (total * 8) / (1024**2)
        kbps = (total * 8) / 1024
        return {"Speed (Mbps)": round(mbps, 2), "Speed (Kbps)": round(kbps, 2)}

    @property
    def device_info(self) -> dict:
        """Link this sensor to the same identity as the tracker."""
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

        info = {
            "identifiers": {(DOMAIN, f"glinet_client_{self._canonical_mac}")},
            "name": device_name or f"Device {self._canonical_mac}",
            "connections": {(dr.CONNECTION_NETWORK_MAC, m) for m in self._macs if mac_regex.match(m)},
            "via_device": (DOMAIN, self._entry.entry_id),
        }
        if device_class:
            info["model"] = device_class
        return info