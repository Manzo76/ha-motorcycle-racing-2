"""Base entity for the Motorcycle Racing integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import RacingCoordinator


class RacingEntity(CoordinatorEntity[RacingCoordinator]):
    """Common device info and attribution."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RacingCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_attribution = coordinator.attribution
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.series_name,
            manufacturer=MANUFACTURER,
            model=f"{coordinator.series_name} season {coordinator.data.season or ''}".strip(),
            entry_type=None,
            configuration_url="https://www.motogp.com/"
            if coordinator.series_key in ("motogp", "moto2", "moto3", "motoe")
            else "https://www.thesportsdb.com/",
        )

    @property
    def series(self):
        """Shorthand for the current series data."""
        return self.coordinator.data
