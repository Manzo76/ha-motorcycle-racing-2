# Motorcycle Racing for Home Assistant - Made by Manzo.
# Copyright (c) 2026 Manzo76. All rights reserved. See LICENSE.
"""The Motorcycle Racing integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CARD_FILENAME,
    CARD_URL,
    CARD_VERSION,
    CONF_REGISTER_CARD,
    DOMAIN,
    PANEL_FILENAME,
    PANEL_MODULE_URL,
    PANEL_URL_PATH,
    PANEL_VERSION,
    PLATFORMS,
)
from .coordinator import RacingCoordinator
from . import websocket_api as _ws

_LOGGER = logging.getLogger(__name__)

type RacingConfigEntry = ConfigEntry[RacingCoordinator]


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the bundled Lovelace card and add it as a frontend resource.

    Every series' config entry calls this during startup, all roughly at
    once. Claim the "already registered" flag *before* the first await so a
    second entry sees it set and bails out instead of racing the first entry
    to register the same static route (which raises RuntimeError from
    aiohttp and, uncaught, used to fail that entry's entire setup).
    """
    if hass.data.get(f"{DOMAIN}_card_registered"):
        return
    hass.data[f"{DOMAIN}_card_registered"] = True

    card_path = Path(__file__).parent / "www" / CARD_FILENAME
    if not card_path.is_file():
        _LOGGER.warning("Bundled card %s is missing; skipping registration", card_path)
        return

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(card_path), cache_headers=False)]
        )
    except RuntimeError as err:
        # Another entry (or a previous reload) already registered the route.
        _LOGGER.debug("Card route already registered: %s", err)
        return

    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, f"{CARD_URL}?v={CARD_VERSION}")
    except Exception as err:  # noqa: BLE001 - never block setup over the card
        _LOGGER.debug("Could not auto-register the card as a resource: %s", err)

    _LOGGER.info("Motorcycle Racing card served at %s", CARD_URL)


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Add the Motorcycle Racing dashboard to the sidebar (once)."""
    if hass.data.get(f"{DOMAIN}_panel_registered"):
        return
    hass.data[f"{DOMAIN}_panel_registered"] = True

    panel_path = Path(__file__).parent / "www" / PANEL_FILENAME
    if not panel_path.is_file():
        _LOGGER.warning("Bundled panel %s is missing; skipping", panel_path)
        return
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_MODULE_URL, str(panel_path), cache_headers=False)]
        )
    except RuntimeError as err:
        _LOGGER.debug("Panel route already registered: %s", err)
    from homeassistant.components import panel_custom

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="motorcycle-racing-panel",
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{PANEL_MODULE_URL}?v={PANEL_VERSION}",
        sidebar_title="Motorcycle Racing",
        sidebar_icon="mdi:motorbike",
        require_admin=False,
        config={},
    )


async def async_setup_entry(hass: HomeAssistant, entry: RacingConfigEntry) -> bool:
    """Set up one series from a config entry."""
    if entry.options.get(CONF_REGISTER_CARD, True):
        try:
            await _async_register_card(hass)
        except Exception:  # noqa: BLE001 - the card is a nice-to-have, never block setup
            _LOGGER.exception("Could not register the bundled dashboard card")

    _ws.async_register(hass)
    try:
        await _async_register_panel(hass)
    except Exception:  # noqa: BLE001 - the panel is optional
        _LOGGER.exception("Could not register the sidebar panel")

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
