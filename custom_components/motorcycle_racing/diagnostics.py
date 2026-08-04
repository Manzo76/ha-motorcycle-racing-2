"""Diagnostics support for the Motorcycle Racing integration."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import RacingConfigEntry
from .const import CONF_API_KEY


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: RacingConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data

    return {
        "entry": {
            "data": {k: v for k, v in entry.data.items() if k != CONF_API_KEY},
            "options": {k: v for k, v in entry.options.items() if k != CONF_API_KEY},
        },
        "coordinator": {
            "series": coordinator.series_name,
            "update_interval": str(coordinator.update_interval),
            "last_update_success": coordinator.last_update_success,
        },
        "data": {
            "season": data.season if data else None,
            "event_count": len(data.events) if data else 0,
            "next_event": data.next_event.as_dict() if data and data.next_event else None,
            "last_event": data.last_event.as_dict() if data and data.last_event else None,
            "results_rows": len(data.last_results) if data else 0,
            "standings_rows": len(data.rider_standings) if data else 0,
        },
    }
