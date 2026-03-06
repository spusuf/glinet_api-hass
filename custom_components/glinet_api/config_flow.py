"""Config flow for GL-iNet API integration."""
import logging
import re
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from typing import Any
from .const import (
    DOMAIN, DEFAULT_HOST, DEFAULT_USERNAME, 
    CONF_TRACKED_CLASSES, CONF_MONITOR_CLASSES, 
    ALL_DEVICE_CLASSES, CONF_MAC_GROUPS, CONF_GUEST_GROUPS,
    DEFAULT_TRACKED, DEFAULT_MONITORED, CONF_USE_HTTPS,
    CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, CONF_TRUSTED_MODE
)
from .api import GLiNetAPI

import subprocess

_LOGGER = logging.getLogger(__name__)

MAC_REGEX = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")

def _class_label(c: str) -> str:
    if c == "nas":
        return "NAS"
    if c == "smartappliances":
        return "Appliances"
    return c.capitalize()

def _parse_to_groups(raw_string: str) -> dict[str, list[str]]:
    """Convert the raw storage string into {name: [macs]}."""
    groups = {}
    if not isinstance(raw_string, str):
        return groups
    
    for line in raw_string.splitlines():
        line = line.strip()
        if not line: continue
        
        parts = line.split()
        if len(parts) >= 2:
            macs = [p.lower() for p in parts if MAC_REGEX.match(p)]
            name_parts = [p for p in parts if not MAC_REGEX.match(p)]
            name = " ".join(name_parts)
            if name and macs:
                groups[name] = list(set(groups.get(name, []) + macs))
    return groups

def _groups_to_string(groups: dict[str, list[str]]) -> str:
    """Convert {name: [macs]} back into the storage string."""
    lines = []
    for name, macs in groups.items():
        if name and macs:
            lines.append(f"{name} {' '.join(macs)}")
    return "\n".join(lines)


class GLiNetConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GL-iNet API."""
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GLiNetOptionsFlowHandler(config_entry)

    def __init__(self):
        """Initialize the flow."""
        self._flow_data = {
            CONF_TRACKED_CLASSES: DEFAULT_TRACKED,
            CONF_MONITOR_CLASSES: DEFAULT_MONITORED,
            CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            CONF_MAC_GROUPS: "",
            CONF_GUEST_GROUPS: "",
            CONF_USE_HTTPS: True,
            CONF_TRUSTED_MODE: True,
        }
        self._conn_data = {}
        self._editing_type = None # "presence" or "guest"

    async def async_step_user(self, user_input=None):
        """Step 1: Connection Details."""
        if not self.context.get("title_placeholders", {}).get("host"):
            self.context["title_placeholders"] = {"host": "Manual Setup"}
        errors = {}
        if user_input is not None and "username" in user_input and "password" in user_input:
            use_https = not user_input.get("disable_https", False)
            self._flow_data[CONF_USE_HTTPS] = use_https
            
            api = GLiNetAPI(
                user_input["host"], 
                user_input["username"], 
                user_input["password"],
                use_https=use_https,
                verify_ssl=False
            )
            try:
                await api.login()

                if not self.unique_id:
                    try:
                        info = await api.system_get_info()
                        router_mac = info.get("mac", "").lower().replace(":", "")
                        if router_mac:
                            _LOGGER.warning("API router MAC: %s", router_mac)
                            await self.async_set_unique_id(router_mac, raise_on_progress=True)
                            self._abort_if_unique_id_configured()
                    except Exception as info_err:
                        _LOGGER.warning("Could not fetch router MAC: %s", info_err, exc_info=True)
                
                self._conn_data = {
                    "host": user_input["host"],
                    "username": user_input["username"],
                    "password": user_input["password"],
                    "use_https": use_https,
                }
                return await self.async_step_settings()
            except Exception as e:
                _LOGGER.error("Connection failed: %s", e)
                errors["base"] = "cannot_connect"

        host_default = (user_input or {}).get("host")
        if not host_default:
            host_default = DEFAULT_HOST
            try:
                result = await self.hass.async_add_executor_job(
                    lambda: subprocess.check_output(["ip", "route", "show", "default"], encoding="utf-8")
                )
                match = re.search(r"via ([\d\.]+)", result)
                if match:
                    host_default = match.group(1)
            except Exception:
                pass

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("host", default=host_default): str,
                vol.Required("username", default=DEFAULT_USERNAME): str,
                vol.Required("password"): str,
                vol.Optional("disable_https", default=False): bool,
            }),
            errors=errors,
        )

    async def async_step_dhcp(self, discovery_info: Any):
        """Handle DHCP discovery."""
        host = discovery_info.ip
        mac = discovery_info.macaddress.lower().replace(":", "")

        await self.async_set_unique_id(mac, raise_on_progress=True)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        for entry in self._async_current_entries():
            if entry.data.get(CONF_HOST) == host:
                return self.async_abort(reason="already_configured")

        self._discovered_host = host
        self.context.update({"host": host, "title_placeholders": {"host": host}})
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input=None):
        """Show a single confirmation dialog for any discovery method."""
        if user_input is not None:
            return await self.async_step_user({"host": self._discovered_host})

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"host": self._discovered_host},
            data_schema=vol.Schema({}),
        )

    async def async_step_settings(self, user_input=None):
        """Step 2: Tracking Associations & Interval."""
        if user_input is not None:
            self._flow_data.update(user_input)
            return await self.async_step_groups()

        return self.async_show_form(
            step_id="settings",
            data_schema=_get_settings_schema(self._flow_data),
        )

    async def async_step_groups(self, user_input=None):
        """Step 3: Device & Guest Combiners."""
        if user_input is not None:
            self._flow_data["mac_groups"] = [l for l in user_input.get("mac_groups", []) if l.strip()]
            self._flow_data["guest_groups"] = [l for l in user_input.get("guest_groups", []) if l.strip()]
            
            return self.async_create_entry(
                title=f"{self._conn_data.get('host')}",
                data=self._conn_data,
                options=self._flow_data
            )

        return self.async_show_form(
            step_id="groups",
            data_schema=_get_groups_schema(self._flow_data),
        )

def _get_settings_schema(data):
    """Shared settings schema."""
    return vol.Schema({
        vol.Optional(
            "tracked_classes", 
            default=data.get("tracked_classes", DEFAULT_TRACKED)
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[{"value": c, "label": _class_label(c)} for c in ALL_DEVICE_CLASSES],
                multiple=True, mode=selector.SelectSelectorMode.DROPDOWN
            )
        ),
        vol.Optional(
            "monitor_classes", 
            default=data.get("monitor_classes", DEFAULT_MONITORED)
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[{"value": c, "label": _class_label(c)} for c in ALL_DEVICE_CLASSES],
                multiple=True, mode=selector.SelectSelectorMode.DROPDOWN
            )
        ),
        vol.Optional("scan_interval", default=data.get("scan_interval", DEFAULT_SCAN_INTERVAL)): 
            vol.All(vol.Coerce(int), vol.Range(min=10, max=600)),
        vol.Optional(CONF_TRUSTED_MODE, default=data.get(CONF_TRUSTED_MODE, True)): bool,
    })

def _get_groups_schema(data):
    """Shared groups schema."""
    return vol.Schema({
        vol.Optional(
            "mac_groups", 
            default=_to_list(data.get("mac_groups", ""))
        ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
        vol.Optional(
            "guest_groups", 
            default=_to_list(data.get("guest_groups", ""))
        ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
    })

def _to_list(val):
    """Helper to ensure we have a list for multiple-item selectors."""
    if isinstance(val, list): return val if val else [""]
    if isinstance(val, str) and val.strip(): return val.splitlines()
    return [""]


class GLiNetOptionsFlowHandler(config_entries.OptionsFlow):
    """Options Flow handler."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Step 1 of Options: Settings."""
        if not hasattr(self, "_flow_data"):
            self._flow_data = dict(self._config_entry.options)

        if user_input is not None:
            self._flow_data.update(user_input)
            return await self.async_step_groups()

        return self.async_show_form(
            step_id="init",
            data_schema=_get_settings_schema(self._flow_data),
        )

    async def async_step_groups(self, user_input=None):
        """Step 2 of Options: Groups."""
        if user_input is not None:
            self._flow_data[CONF_MAC_GROUPS] = [l for l in user_input.get(CONF_MAC_GROUPS, []) if l.strip()]
            self._flow_data[CONF_GUEST_GROUPS] = [l for l in user_input.get(CONF_GUEST_GROUPS, []) if l.strip()]
            return self.async_create_entry(title="", data=self._flow_data)

        return self.async_show_form(
            step_id="groups",
            data_schema=_get_groups_schema(self._flow_data),
        )
