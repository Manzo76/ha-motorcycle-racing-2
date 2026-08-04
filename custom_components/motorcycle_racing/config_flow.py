"""Config flow for the Motorcycle Racing integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .api import ProviderError, SportsDBProvider, build_provider
from .const import (
    CONF_API_KEY,
    CONF_FAVOURITE_RIDER,
    CONF_LEAGUE_ID,
    CONF_LIVE_SCAN_INTERVAL,
    CONF_PROVIDER,
    CONF_REGISTER_CARD,
    CONF_SCAN_INTERVAL,
    CONF_SERIES,
    DEFAULT_SPORTSDB_KEY,
    DOMAIN,
    PROVIDER_SPORTSDB,
    SERIES_CATALOGUE,
)

_LOGGER = logging.getLogger(__name__)

SERIES_OPTIONS = [
    SelectOptionDict(value=key, label=meta["name"])
    for key, meta in SERIES_CATALOGUE.items()
]


class MotorcycleRacingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Walk the user through picking a series."""

    VERSION = 1

    def __init__(self) -> None:
        self._series: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            series = user_input[CONF_SERIES]
            if series == "custom":
                self._series = series
                return await self.async_step_league()

            await self.async_set_unique_id(f"{DOMAIN}_{series}")
            self._abort_if_unique_id_configured()

            config = {
                CONF_SERIES: series,
                CONF_PROVIDER: SERIES_CATALOGUE[series]["provider"],
                CONF_LEAGUE_ID: SERIES_CATALOGUE[series].get("league_id"),
                "series_name": SERIES_CATALOGUE[series]["name"],
            }
            error = await self._async_validate(config)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=SERIES_CATALOGUE[series]["name"], data=config
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SERIES, default="motogp"): SelectSelector(
                        SelectSelectorConfig(
                            options=SERIES_OPTIONS, mode=SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_league(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick any other motorcycle league from TheSportsDB."""
        errors: dict[str, str] = {}
        session = async_get_clientsession(self.hass)

        try:
            leagues = await SportsDBProvider.async_list_motorcycle_leagues(session)
        except ProviderError as err:
            _LOGGER.error("Could not list leagues: %s", err)
            return self.async_abort(reason="cannot_connect")

        if not leagues:
            return self.async_abort(reason="no_leagues")

        if user_input is not None:
            league_id = user_input[CONF_LEAGUE_ID]
            name = next(
                (item["name"] for item in leagues if item["id"] == league_id),
                "Motorcycle Racing",
            )
            await self.async_set_unique_id(f"{DOMAIN}_sportsdb_{league_id}")
            self._abort_if_unique_id_configured()

            config = {
                CONF_SERIES: "custom",
                CONF_PROVIDER: PROVIDER_SPORTSDB,
                CONF_LEAGUE_ID: league_id,
                CONF_API_KEY: user_input.get(CONF_API_KEY) or DEFAULT_SPORTSDB_KEY,
                "series_name": name,
            }
            error = await self._async_validate(config)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(title=name, data=config)

        return self.async_show_form(
            step_id="league",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LEAGUE_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(value=item["id"], label=item["name"])
                                for item in leagues
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_API_KEY): TextSelector(),
                }
            ),
            errors=errors,
        )

    async def _async_validate(self, config: dict[str, Any]) -> str | None:
        """Return an error key, or None when the series fetches cleanly."""
        try:
            provider = build_provider(async_get_clientsession(self.hass), config)
            await provider.async_get_data()
        except ProviderError as err:
            _LOGGER.warning("Validation failed for %s: %s", config[CONF_SERIES], err)
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error validating %s", config[CONF_SERIES])
            return "unknown"
        return None

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return MotorcycleRacingOptionsFlow()


class MotorcycleRacingOptionsFlow(OptionsFlow):
    """Tune polling, artwork and the favourite rider."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_FAVOURITE_RIDER,
                        description={
                            "suggested_value": options.get(CONF_FAVOURITE_RIDER, "")
                        },
                    ): TextSelector(),
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, 30),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=720)),
                    vol.Optional(
                        CONF_LIVE_SCAN_INTERVAL,
                        default=options.get(CONF_LIVE_SCAN_INTERVAL, 2),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),
                    vol.Optional(
                        CONF_API_KEY,
                        description={"suggested_value": options.get(CONF_API_KEY, "")},
                    ): TextSelector(),
                    vol.Optional(
                        CONF_REGISTER_CARD,
                        default=options.get(CONF_REGISTER_CARD, True),
                    ): bool,
                }
            ),
        )
