"""Entities created from the fake Garten camera, and writing settings."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.icsee_ptz.switch import dst_period

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
        "switch.garten_image_flip",
        "number.garten_main_stream_frame_rate",
        "number.garten_speaker_volume",
        "number.garten_white_light_brightness",
        "button.garten_clock_synchronize",
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
    # with a white light, "auto" does not turn on the infrared light
    assert "auto" not in state.attributes["options"]
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
    assert hass.states.get("switch.garten_image_flip").state == "on"
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.garten_image_flip"}, blocking=True
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


async def test_camera_needs_rtsp(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    from homeassistant.components.camera import async_get_stream_source
    from homeassistant.helpers import issue_registry as ir

    issue = ("icsee_ptz", f"rtsp_disabled_{setup_integration.entry_id}")
    # RTSP server off: no video, and a repair issue explains it
    assert hass.states.get("camera.garten_sub_stream").state == "unavailable"
    assert ir.async_get(hass).async_get_issue(*issue)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.garten_rtsp_server"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("camera.garten_sub_stream").state != "unavailable"
    assert not ir.async_get(hass).async_get_issue(*issue)
    assert await async_get_stream_source(hass, "camera.garten_sub_stream") == (
        "rtsp://192.0.2.10:554/user=admin&password=secret&channel=1&stream=1.sdp?real_stream"
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
    users = hass.states.get("sensor.garten_users")
    assert users.state == "1"
    assert users.attributes["users"] == [{"name": "admin", "group": "admin"}]
    assert "hiddenpass" not in str(users.attributes)
    assert hass.states.get("sensor.garten_logged_in_as").state == "admin"
    assert hass.states.get("sensor.garten_wifi_signal").state == "61"
    assert hass.states.get("sensor.garten_cloud_status").state == "connected"
    # no SD card inserted
    assert hass.states.get("sensor.garten_sd_card_size") is None
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


async def test_all_entities_enabled(hass: HomeAssistant, setup_integration) -> None:
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, setup_integration.entry_id)
    assert entries
    assert [e.entity_id for e in entries if e.disabled_by] == []


async def test_camera_snapshots_from_stream(
    hass: HomeAssistant, setup_integration
) -> None:
    from homeassistant.components import camera

    cam = camera.get_camera_from_entity_id(hass, "camera.garten_main_stream")
    assert cam.use_stream_for_stills is True


async def test_more_settings(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    states = {s.entity_id: s.state for s in hass.states.async_all()}
    assert states["switch.garten_firmware_updates_install_automatically"] == "on"
    assert states["switch.garten_upnp_port_forwarding"] == "off"
    assert states["switch.garten_video_time_shown"] == "on"
    assert states["binary_sensor.garten_telnet_debug_access"] == "off"
    assert states["binary_sensor.garten_linked_to_app_account"] == "on"
    assert states["select.garten_restart_automatically"] == "tuesday"
    assert float(states["number.garten_restart_automatically_hour"]) == 3
    assert states["sensor.garten_restarts_abnormal"] == "3"
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.garten_firmware_updates_install_automatically"},
        blocking=True,
    )
    assert mock_device.writes[-1][0] == "NetWork.OnlineUpgrade"
    assert mock_device.writes[-1][1]["AutoUpgradeImp"] is False
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.garten_video_name_shown"},
        blocking=True,
    )
    assert mock_device.writes[-1][0] == "AVEnc.VideoWidget.[0]"
    assert mock_device.writes[-1][1]["ChannelTitleAttribute"]["EncodeBlend"] is True


async def test_ptz_preset_select(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    state = hass.states.get("select.garten_ptz_go_to_preset")
    assert state.attributes["options"] == ["Door", "Preset 250"]
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.garten_ptz_go_to_preset", "option": "Preset 250"},
        blocking=True,
    )
    mock_device.async_ptz.assert_awaited_with("GotoPreset", 2, 250, 0)


async def test_camera_refreshes_player_when_rtsp_turns_on(
    hass: HomeAssistant, setup_integration
) -> None:
    from unittest.mock import patch

    from custom_components.icsee_ptz.camera import ICSeeCamera

    with patch.object(ICSeeCamera, "async_refresh_providers") as refresh:
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.garten_rtsp_server"},
            blocking=True,
        )
        await hass.async_block_till_done()
    assert refresh.call_count == 2  # main and sub stream


async def test_reboot_issue_cleared_on_reconnect(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    from homeassistant.helpers import issue_registry as ir

    mock_device.set_ret = 603
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.garten_privacy_mode"}, blocking=True
    )
    issue = ("icsee_ptz", f"reboot_required_{setup_integration.entry_id}")
    assert ir.async_get(hass).async_get_issue(*issue)
    mock_device.connected = True
    for cb in list(mock_device._connection_callbacks):
        cb()
    assert not ir.async_get(hass).async_get_issue(*issue)


async def test_motion_alarm_polled(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    entity_id = "binary_sensor.garten_motion_alarm"
    # known at start, without waiting for an event
    assert hass.states.get(entity_id).state == "off"
    coordinator = setup_integration.runtime_data.coordinator
    # a pushed event wins for a while over the (older) polled state
    mock_device.fire_alarm({"Channel": 0, "Status": "Start"})
    await coordinator.async_refresh()
    assert hass.states.get(entity_id).state == "on"
    from custom_components.icsee_ptz import binary_sensor

    # camera that never reports motion in WorkState (like the tested Hiseeu):
    # a polled "off" must not end an ongoing alarm
    with patch.object(binary_sensor, "PUSH_GRACE", 0):
        await coordinator.async_refresh()
    assert hass.states.get(entity_id).state == "on"
    mock_device.fire_alarm({"Channel": 0, "Status": "Stop"})
    await hass.async_block_till_done()
    # camera that does report it: the poll is trusted in both directions,
    # e.g. to correct a missed "stop" event
    mock_device.configs["WorkState"]["AlarmState"]["VideoMotion"] = "0x00000001"
    with patch.object(binary_sensor, "PUSH_GRACE", 0):
        await coordinator.async_refresh()
    assert hass.states.get(entity_id).state == "on"
    mock_device.configs["WorkState"]["AlarmState"]["VideoMotion"] = "0x00000000"
    with patch.object(binary_sensor, "PUSH_GRACE", 0):
        await coordinator.async_refresh()
    assert hass.states.get(entity_id).state == "off"


async def test_image_and_alarm_settings(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    states = {s.entity_id: s.state for s in hass.states.async_all()}
    assert states["switch.garten_image_anti_flicker"] == "off"
    assert states["switch.garten_motion_push_notification"] == "on"
    assert states["switch.garten_motion_warning_light"] == "on"
    assert float(states["number.garten_image_noise_reduction_night"]) == 3
    assert float(states["number.garten_motion_alarm_hold_time"]) == 2
    assert states["select.garten_main_stream_smart_encoding"] == "h264"
    assert states["sensor.garten_video_standard"] == "PAL"
    # microphone: InVolume is missing, so VolumeIn is used
    assert float(states["number.garten_microphone_volume"]) == 50
    # the app also sets RecordMask when turning recording on
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.garten_motion_record"},
        blocking=True,
    )
    name, value = mock_device.writes[-1]
    assert name == "Detect.MotionDetect.[0]"
    assert value["EventHandler"]["RecordEnable"] is True
    assert value["EventHandler"]["RecordMask"] == "0x00000001"
    # H.265X sets both SmartH264 and SmartH264Plus on the main stream
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.garten_main_stream_smart_encoding", "option": "h265x"},
        blocking=True,
    )
    name, value = mock_device.writes[-1]
    assert name == "AVEnc.SmartH264V2.[0]"
    assert value["Smart264V2"][0]["SmartH264"] is True
    assert value["Smart264PlusV2"][0]["SmartH264Plus"] == 1
    assert hass.states.get("select.garten_main_stream_smart_encoding").state == "h265x"


async def test_sdk_header_settings(hass: HomeAssistant, setup_integration) -> None:
    states = {s.entity_id: s.state for s in hass.states.async_all()}
    assert states["switch.garten_image_stabilization"] == "off"
    assert states["switch.garten_image_lens_distortion_correction"] == "off"
    assert states["select.garten_exposure_metering"] == "average"
    assert states["select.garten_ir_filter_switching"] == "with_ir_light"
    assert float(states["sensor.garten_exposure_time"]) == 256  # 0x00000100
    assert float(states["number.garten_wide_dynamic_range_level"]) == 100


async def test_final_settings(
    hass: HomeAssistant, setup_integration, mock_device
) -> None:
    states = {s.entity_id: s.state for s in hass.states.async_all()}
    assert states["select.garten_sd_card_recording"] == "schedule"
    assert float(states["number.garten_sd_card_pre_recording"]) == 5
    assert float(states["number.garten_sd_card_file_length"]) == 5
    assert float(states["number.garten_cloud_push_notification_interval"]) == 10
    assert float(states["number.garten_tamper_detection_sensitivity"]) == 3
    assert float(states["number.garten_exposure_time_maximum"]) == 65.536
    assert states["sensor.garten_restarts_network_loss"] == "0"
    assert states["binary_sensor.garten_upnp_router_ports_open"] == "off"
    assert states["switch.garten_clock_daylight_saving_time"] == "on"
    # time top right, name bottom left
    assert states["select.garten_video_time_position"] == "top_right"
    assert states["select.garten_video_name_position"] == "bottom_left"
    # the camera says: no human sensitivity, no vehicles
    assert "select.garten_human_detection_sensitivity" not in states
    assert "select.garten_human_detection_targets" not in states

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.garten_exposure_time_maximum", "value": 33},
        blocking=True,
    )
    name, value = mock_device.writes[-1]
    assert name == "Camera.Param.[0]"
    assert value["ExposureParam"]["MostTime"] == "0x000080E8"  # 33000 µs

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.garten_video_name_position", "option": "top_left"},
        blocking=True,
    )
    name, value = mock_device.writes[-1]
    assert name == "AVEnc.VideoWidget.[0]"
    assert value["ChannelTitleAttribute"]["RelativePos"] == [76, 135, 255, 24]
    assert hass.states.get("select.garten_video_name_position").state == "top_left"

    # turning DST on also writes the dates of HA's time zone
    await hass.config.async_update(time_zone="Europe/Berlin")
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.garten_clock_daylight_saving_time"},
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.garten_clock_daylight_saving_time"},
        blocking=True,
    )
    name, value = mock_device.writes[-1]
    assert name == "General.Location"
    assert value["DSTRule"] == "On"
    year = dt_util.now().year
    assert (value["DSTStart"]["Year"], value["DSTStart"]["Month"]) == (year, 3)
    assert (value["DSTEnd"]["Year"], value["DSTEnd"]["Month"]) == (year, 10)
    assert value["DSTStart"]["Week"] == 0

    await hass.config.async_update(time_zone="Asia/Tokyo")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.garten_clock_daylight_saving_time"},
            blocking=True,
        )


def test_dst_period() -> None:
    berlin = dst_period(ZoneInfo("Europe/Berlin"), 2022)
    assert berlin == (date(2022, 3, 27), date(2022, 10, 30))  # what the app wrote
    sydney = dst_period(ZoneInfo("Australia/Sydney"), 2026)
    assert sydney == (date(2026, 10, 4), date(2027, 4, 4))
    assert dst_period(ZoneInfo("Asia/Tokyo"), 2026) is None


async def test_video_name(hass: HomeAssistant, setup_integration, mock_device) -> None:
    entity_id = "text.garten_video_name_text"
    assert hass.states.get(entity_id).state == "Garden"
    await hass.services.async_call(
        "text",
        "set_value",
        {"entity_id": entity_id, "value": "Back yard"},
        blocking=True,
    )
    # the camera only redraws the name after it also gets the channel titles
    assert mock_device.writes[-2][0] == "AVEnc.VideoWidget.[0]"
    assert mock_device.writes[-2][1]["ChannelTitle"]["Name"] == "Back yard"
    assert mock_device.writes[-1] == ("ChannelTitle", ["Back yard"])
    assert hass.states.get(entity_id).state == "Back yard"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "text",
            "set_value",
            {"entity_id": entity_id, "value": "ä" * 22},
            blocking=True,
        )
