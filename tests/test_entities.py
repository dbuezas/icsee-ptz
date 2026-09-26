"""Entities created from the fake Garten camera, and writing settings."""

from __future__ import annotations

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .conftest import SERIAL


async def test_legacy_unique_ids_kept(hass: HomeAssistant, setup_integration) -> None:
    """Entity IDs of 4.x users must keep working."""
    registry = er.async_get(hass)
    for platform, unique_id in [
        ("binary_sensor", f"{SERIAL}_alarm_0"),
        ("switch", f"{SERIAL}_MotionDetect_0"),
        ("switch", f"{SERIAL}_HumanDetection_0"),
        ("select", f"{SERIAL}_DayNightColorSelect_0"),
        ("select", f"{SERIAL}_WhiteLightSelect_0"),
        ("button", f"{SERIAL}_ptz_stop_0"),
        ("button", f"{SERIAL}_home_set_0"),
        ("button", f"{SERIAL}_reboot"),
    ]:
        assert registry.async_get_entity_id(platform, "icsee_ptz", unique_id), unique_id


async def test_entities_created(hass: HomeAssistant, setup_integration) -> None:
    states = {s.entity_id for s in hass.states.async_all()}
    for entity_id in [
        "binary_sensor.garten_motion_alarm",
        "camera.garten_main_stream",
        "camera.garten_sub_stream",
        "media_player.garten_speaker",
        "select.garten_day_night_mode",
        "select.garten_white_light_mode",
        "select.garten_main_stream_resolution",
        "select.garten_main_stream_quality",
        "switch.garten_white_light",
        "switch.garten_privacy_mode",
        "switch.garten_motion_tracking",
        "switch.garten_flip_image",
        "number.garten_main_stream_frame_rate",
        "number.garten_speaker_volume",
        "number.garten_white_light_brightness",
        "button.garten_synchronize_clock",
    ]:
        assert entity_id in states, entity_id
    # Garten has no manual siren ability
    assert not any(e.startswith("siren.") for e in states)


async def test_day_night_select(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    state = hass.states.get("select.garten_day_night_mode")
    assert state.state == "auto_infrared"  # 0x00000005
    assert "color" in state.attributes["options"]
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.garten_day_night_mode", "option": "color"},
        blocking=True,
    )
    assert mock_device.writes[-1][0] == "Camera.Param.[0]"
    assert mock_device.writes[-1][1]["DayNightColor"] == "0x00000001"
    assert hass.states.get("select.garten_day_night_mode").state == "color"


async def test_white_light_switch(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    assert hass.states.get("switch.garten_white_light").state == "off"  # WorkMode Auto
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.garten_white_light"}, blocking=True
    )
    name, value = mock_device.writes[-1]
    assert name == "Camera.WhiteLight"
    # the whole object is sent, not only WorkMode
    assert value["WorkMode"] == "KeepOpen" and "MoveTrigLight" in value
    assert hass.states.get("switch.garten_white_light").state == "on"


async def test_flip_hex_values(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    assert hass.states.get("switch.garten_flip_image").state == "on"
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.garten_flip_image"}, blocking=True
    )
    assert mock_device.writes[-1][1]["PictureFlip"] == "0x00000000"


async def test_fps_and_budget(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    entity_id = "number.garten_main_stream_frame_rate"
    assert float(hass.states.get(entity_id).state) == 25
    assert hass.states.get(entity_id).attributes["max"] == 25  # PAL
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 15}, blocking=True
    )
    # Simplify.Encode has no per-channel name: the whole list is written
    name, value = mock_device.writes[-1]
    assert name == "Simplify.Encode"
    assert value[0]["MainFormat"]["Video"]["FPS"] == 15
    # Garten is exactly at its budget at 3M@25 + D1@25; 25 fps on the sub stream
    # plus a higher sub resolution would not fit
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 25}, blocking=True
    )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.garten_sub_stream_frame_rate", "value": 30},
            blocking=True,
        )


async def test_quality_select(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    assert hass.states.get("select.garten_main_stream_quality").state == "bad"
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.garten_main_stream_quality", "option": "best"},
        blocking=True,
    )
    assert mock_device.writes[-1][1][0]["MainFormat"]["Video"]["Quality"] == 6


async def test_ignored_write_raises(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    mock_device.ignore_writes = True
    with pytest.raises(HomeAssistantError, match="did not apply"):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.garten_privacy_mode"},
            blocking=True,
        )


async def test_refused_write_raises(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    mock_device.set_ret = 102
    with pytest.raises(HomeAssistantError, match="error 102"):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.garten_privacy_mode"},
            blocking=True,
        )


async def test_reboot_needed_creates_issue(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    from homeassistant.helpers import issue_registry as ir

    mock_device.set_ret = 603
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.garten_privacy_mode"}, blocking=True
    )
    assert ir.async_get(hass).async_get_issue(
        "icsee_ptz", f"reboot_required_{setup_integration.entry_id}"
    )


async def test_motion_alarm_push(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    mock_device.fire_alarm({"Channel": 0, "Status": "Start", "Event": "HumanDetect"})
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.garten_motion_alarm").state == "on"
    mock_device.fire_alarm({"Channel": 0, "Status": "Stop", "Event": "HumanDetect"})
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.garten_motion_alarm").state == "off"


async def test_move_action(hass: HomeAssistant, setup_integration, mock_device) -> None:
    await hass.services.async_call(
        "icsee_ptz",
        "move",
        {"entity_id": "binary_sensor.garten_motion_alarm", "cmd": "DirectionLeft"},
        blocking=True,
    )
    mock_device.async_ptz.assert_awaited_with("DirectionLeft", 2, 0, 0)


async def test_ptz_button(hass: HomeAssistant, setup_integration, mock_device) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.garten_ptz_stop"}, blocking=True
    )
    mock_device.async_ptz.assert_awaited_with("Stop", 2, 0, 0)


async def test_camera_stream_source(hass: HomeAssistant, setup_integration) -> None:
    from homeassistant.components.camera import async_get_stream_source

    assert await async_get_stream_source(hass, "camera.garten_sub_stream") == (
        "dvrip://admin:secret@192.0.2.10:34567?channel=0&subtype=1"
    )


async def test_speaker_volume(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    await hass.services.async_call(
        "media_player",
        "volume_set",
        {"entity_id": "media_player.garten_speaker", "volume_level": 0.4},
        blocking=True,
    )
    name, value = mock_device.writes[-1]
    assert name == "fVideo.Volume.[0]"
    assert value["LeftVolume"] == value["RightVolume"] == 40


async def test_security_entities(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    assert hass.states.get("switch.garten_cloud_access_p2p").state == "off"
    assert hass.states.get("switch.garten_cloud_push_notifications").state == "on"
    assert (
        hass.states.get(
            "binary_sensor.garten_password_reset_by_security_questions"
        ).state
        == "off"
    )
    assert (
        hass.states.get("binary_sensor.garten_password_reset_email_or_phone_set").state
        == "off"
    )
    extra = hass.states.get("sensor.garten_extra_users")
    assert extra.state == "1"
    assert extra.attributes["users"] == ["hiddenuser"]
    assert "hiddenpass" not in str(extra.attributes)
    # the camera has no VerifyCodeRestorePwdType field
    assert hass.states.get("switch.garten_password_reset_by_code") is None
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.garten_cloud_access_p2p"},
        blocking=True,
    )
    assert mock_device.writes[-1] == (
        "NetWork.Nat",
        {**mock_device.configs["NetWork.Nat"], "NatEnable": True},
    )


async def test_move_only_targets_motion_sensor(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    from homeassistant.exceptions import ServiceNotSupported

    with pytest.raises(ServiceNotSupported):
        await hass.services.async_call(
            "icsee_ptz",
            "move",
            {
                "entity_id": "binary_sensor.garten_password_reset_by_security_questions",
                "cmd": "Stop",
            },
            blocking=True,
        )
    mock_device.async_ptz.assert_not_awaited()
