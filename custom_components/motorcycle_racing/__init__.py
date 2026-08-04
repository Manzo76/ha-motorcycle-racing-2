"""The Motorcycle Racing integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CARD_FILENAME, CARD_URL, CONF_REGISTER_CARD, DOMAIN, PLATFORMS
from .coordinator import RacingCoordinator

_LOGGER = logging.getLogger(__name__)

type RacingConfigEntry = ConfigEntry[RacingCoordinator]


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the bundled Lovelace card and add it as a frontend resource."""
    if hass.data.get(f"{DOMAIN}_card_registered"):
        return

    card_path = Path(__file__).parent / "www" / CARD_FILENAME
    if not card_path.is_file():
        _LOGGER.warning("Bundled card %s is missing; skipping registration", card_path)
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(card_path), cache_headers=False)]
    )

    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, f"{CARD_URL}?v={hass.data.get('integrations_version', '1')}")
    except Exception as err:  # noqa: BLE001 - never block setup over the card
        _LOGGER.debug("Could not auto-register the card as a resource: %s", err)

    hass.data[f"{DOMAIN}_card_registered"] = True
    _LOGGER.info("Motorcycle Racing card served at %s", CARD_URL)


async def async_setup_entry(hass: HomeAssistant, entry: RacingConfigEntry) -> bool:
    """Set up one series from a config entry."""
    if entry.options.get(CONF_REGISTER_CARD, True):
        await _async_register_card(hass)

    coordinator = RacingCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RacingConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: RacingConfigEntry) -> None:
    """Reload when the user changes options."""
    await hass.config_entries.async_reload(entry.entry_id)
