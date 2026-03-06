import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import get_router_prefix
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the GL-iNet buttons."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    prefix = get_router_prefix(hass, entry, coordinator)
    
    button = GLiNetRebootButton(coordinator, entry)
    button._attr_has_entity_name = True
    obj_id = slugify(button.name)
    button.entity_id = f"button.{prefix}_{obj_id}"
    
    async_add_entities([button])

class GLiNetRebootButton(CoordinatorEntity, ButtonEntity):
    """Button to reboot the GL-iNet router."""
    _attr_has_entity_name = True
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Reboot"
        self._attr_unique_id = f"{entry.entry_id}_reboot"
        self._attr_icon = "mdi:restart"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.coordinator.api.system_reboot(delay=1)
        except Exception as err:
            _LOGGER.error("Failed to reboot GL-iNet: %s", err)

    @property
    def device_info(self):
        """Return device info so it links to the same router page."""
        from .coordinator import router_device_info 
        return router_device_info(self._entry, self.coordinator)