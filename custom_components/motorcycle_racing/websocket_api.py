"""Websocket commands that feed the Motorcycle Racing sidebar panel."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .api import SeriesData
from .api.models import RaceEvent
from .const import DOMAIN
from .coordinator import RacingCoordinator


def _coordinators(hass: HomeAssistant) -> dict[str, RacingCoordinator]:
    found: dict[str, RacingCoordinator] = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if isinstance(coordinator, RacingCoordinator):
            found[coordinator.series_key] = coordinator
    return found


def _event(event: RaceEvent | None) -> dict[str, Any] | None:
    if event is None:
        return None
    out = event.as_dict()
    out["id"] = event.event_id
    return out


def _series_payload(coordinator: RacingCoordinator) -> dict[str, Any]:
    data: SeriesData | None = coordinator.data
    base = {
        "key": coordinator.series_key,
        "name": coordinator.series_name,
        "accent": coordinator.accent,
    }
    if data is None:
        return {**base, "ready": False}
    live = data.live_session
    return {
        **base,
        "ready": True,
        "season": data.season,
        "season_over": data.season_over,
        "live": live.as_dict() if live else None,
        "next_event": _event(data.next_event),
        "next_session": data.next_session.as_dict() if data.next_session else None,
        "next_season_event": _event(data.next_season_event),
        "last_event": _event(data.last_event),
        "last_results": [r.as_dict() for r in data.last_results],
        "calendar": [_event(e) for e in data.events],
        "riders": [r.as_dict() for r in data.rider_standings],
        "teams": [r.as_dict() for r in data.team_standings],
        "champion": data.champion_rider.as_dict() if data.champion_rider else None,
        "champion_team": data.champion_team.as_dict() if data.champion_team else None,
        "champions": [c.as_dict() for c in data.champions],
        "attribution": data.attribution,
    }


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the panel's websocket commands (idempotent)."""
    if hass.data.get(f"{DOMAIN}_ws_registered"):
        return
    hass.data[f"{DOMAIN}_ws_registered"] = True
    websocket_api.async_register_command(hass, ws_overview)
    websocket_api.async_register_command(hass, ws_event_results)
    websocket_api.async_register_command(hass, ws_live)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/overview"})
@callback
def ws_overview(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Everything the panel needs for every configured class, in one message."""
    series = [_series_payload(c) for c in _coordinators(hass).values()]
    connection.send_result(msg["id"], {"series": series})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/event_results",
        vol.Required("series"): str,
        vol.Required("event_id"): str,
    }
)
@websocket_api.async_response
async def ws_event_results(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """All sessions of one race weekend with their classifications."""
    coordinator = _coordinators(hass).get(msg["series"])
    if coordinator is None:
        connection.send_error(msg["id"], "not_found", "Unknown series")
        return
    finished = False
    if coordinator.data:
        finished = any(
            e.event_id == msg["event_id"] and e.finished for e in coordinator.data.events
        )
    result = await coordinator.async_event_results(msg["event_id"], finished)
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/live", vol.Required("series"): str}
)
@websocket_api.async_response
async def ws_live(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Fresh classification for the weekend in progress (or the latest one)."""
    coordinator = _coordinators(hass).get(msg["series"])
    if coordinator is None or coordinator.data is None:
        connection.send_error(msg["id"], "not_found", "Unknown series")
        return
    data = coordinator.data
    event = data.next_event if data.live_session else None
    if event is None and data.next_event and data.next_event.sessions:
        # Weekend underway (e.g. Saturday between sessions) still counts.
        event = data.next_event if coordinator.is_race_weekend(data) else None
    event = event or data.last_event
    if event is None:
        connection.send_result(msg["id"], {"live": None, "event": None, "sessions": []})
        return
    result = await coordinator.async_event_results(event.event_id, False)
    connection.send_result(
        msg["id"],
        {
            "live": data.live_session.as_dict() if data.live_session else None,
            "event": _event(event),
            "sessions": result.get("sessions", []),
        },
    )
