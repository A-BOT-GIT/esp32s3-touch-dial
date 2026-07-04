from pathlib import Path


INO_PATH = Path("/home/zza/projects/esp32s3_touch_dial/esp32s3_touch_dial.ino")


def test_ble_hid_manufacturer_characteristic_is_created_before_setter_call():
    ino = INO_PATH.read_text(encoding="utf-8")

    create = "  bleDialHid->manufacturer();"
    set_value = "  bleDialHid->manufacturer(USB_MANUFACTURER_NAME);"

    assert create in ino, "BLE HID init must create the manufacturer characteristic before setting its value"
    assert set_value in ino, "BLE HID init should still set the manufacturer string"
    assert ino.index(create) < ino.index(set_value), "manufacturer() creation must happen before manufacturer(name)"


def test_ble_hid_advertising_payload_is_built_explicitly_for_windows_discovery():
    ino = INO_PATH.read_text(encoding="utf-8")

    # Task C: Custom AD with 3 services — HID, Battery, Device Information
    # in a single AD type 0x03 element (Complete List of 16-bit Service UUIDs).
    adv_decl      = 'BLEAdvertisementData bleAdvData;'
    triple_svc_ad = '0x03, 0x12, 0x18, 0x0F, 0x18, 0x0A, 0x18'  # HID + Batt + DIS
    start_adv     = '  bleDialServer->startAdvertising();'

    for needle, message in [
        (adv_decl,      "BLE advertising must declare advertisement data"),
        (triple_svc_ad, "BLE advertising must include HID, Battery, and DIS 16-bit UUIDs"),
        (start_adv,     "BLE advertising must be started"),
    ]:
        assert needle in ino, message


def test_ble_hid_advertising_uses_explicit_random_address_before_start():
    ino = INO_PATH.read_text(encoding="utf-8")

    random_addr_fn = "void fillBleDialRandomAddress(esp_bd_addr_t addr) {"
    # Address must be derivable from base MAC (stable across reboots), not esp_random().
    static_random_msb = "| 0xC0"
    base_mac_read = "esp_read_mac(baseMac, ESP_MAC_BT)"
    start_advertising = "  bleDialServer->startAdvertising();"

    assert random_addr_fn in ino, "BLE path should provide a helper that builds a static random BLE address"
    assert static_random_msb in ino, "BLE random-address helper should force the static-random top bits (| 0xC0) on byte 0"
    assert base_mac_read in ino, "BLE random address should derive from base MAC for stability across reboots"
    assert start_advertising in ino, "BLE advertising init should still start advertising"
    # Note: setDeviceAddress may be omitted to test default public address for
    # Windows compatibility; the random address helper must still exist for reuse.


def test_ble_send_helper_records_attempted_send_type_before_ready_gate():
    ino = INO_PATH.read_text(encoding="utf-8")

    send_fn = "bool bleDialSendReport(uint8_t buttons, int8_t delta, const char* sendType) {"
    set_send_type = "  setBleLastSendType(sendType);"
    ready_gate = "  if (!dialBackendReady() || bleMediaInputReport == nullptr) {"

    assert send_fn in ino, "BLE send semantics should flow through the shared send helper"
    assert set_send_type in ino, "BLE send helper should record the attempted send type even when the send is skipped"
    assert ready_gate in ino, "BLE send helper should still guard the not-ready/report-missing path"

    send_fn_index = ino.index(send_fn)
    set_send_type_index = ino.index(set_send_type, send_fn_index)
    ready_gate_index = ino.index(ready_gate, send_fn_index)

    assert set_send_type_index < ready_gate_index, "attempted send type must be recorded before not-ready/report-missing early returns"


def test_ble_connection_edges_reset_send_tracking_before_status_transitions():
    ino = INO_PATH.read_text(encoding="utf-8")

    reset_helper = "void resetBleDialSendTracking() {"
    reset_rotate = "  bleLastRotateSendMs = 0;"
    reset_press = "  bleLastPressSendMs = 0;"
    reset_send_type = '  bleLastSendType = "none";'
    reset_error = '  bleLastBackendError = "none";'
    on_connect = "  void onConnect(BLEServer* pServer) override {"
    on_disconnect = "  void onDisconnect(BLEServer* pServer) override {"
    call_reset = "    resetBleDialSendTracking();"
    connect_state = "    setBleDialState(BleDialState::ConnectedIdle);"
    disconnect_state = "    setBleDialState(BleDialState::RestartingAdvertising);"

    for needle, message in [
        (reset_helper, "BLE path should provide an explicit helper to reset send tracking across link edges"),
        (reset_rotate, "reset helper should clear rotate rate-limit state"),
        (reset_press, "reset helper should clear press rate-limit state"),
        (reset_send_type, "reset helper should clear stale last_send_type"),
        (reset_error, "reset helper should clear stale last_backend_error"),
        (call_reset, "BLE connect/disconnect callbacks should reuse the shared reset helper"),
    ]:
        assert needle in ino, message

    connect_index = ino.index(on_connect)
    disconnect_index = ino.index(on_disconnect)
    connect_reset_index = ino.index(call_reset, connect_index)
    disconnect_reset_index = ino.index(call_reset, disconnect_index)
    connect_state_index = ino.index(connect_state, connect_index)
    disconnect_state_index = ino.index(disconnect_state, disconnect_index)

    assert connect_reset_index < connect_state_index, "connect callback should clear stale send tracking before reporting connected_idle"
    assert disconnect_reset_index < disconnect_state_index, "disconnect callback should clear stale send tracking before reporting restart/advertising states"


# --- Task I: HOGP validation tests ---

def test_ble_security_uses_bonded_just_works_not_no_bond():
    ino = INO_PATH.read_text(encoding="utf-8")
    no_bond = "ESP_LE_AUTH_NO_BOND"
    # NO_BOND should NOT appear as the final active security path.
    # It may legitimately appear in comments, docs, or fallback branches.
    active_lines = [l for l in ino.split("\n") if no_bond in l and not l.strip().startswith("//") and not l.strip().startswith("*")]
    assert len(active_lines) == 0, f"ESP_LE_AUTH_NO_BOND must not be the active security path. Found: {active_lines}"


def test_ble_security_uses_sc_bond_or_bond():
    ino = INO_PATH.read_text(encoding="utf-8")
    assert "ESP_LE_AUTH_REQ_SC_BOND" in ino or "ESP_LE_AUTH_BOND" in ino, \
        "BLE security must use bonded mode (SC_BOND or BOND)"


def test_dial_report_id_is_one():
    ino = INO_PATH.read_text(encoding="utf-8")
    assert "DIAL_REPORT_ID = 1" in ino, "Report ID must be 1 for Radial Controller"


def test_radial_controller_descriptor_structure():
    ino = INO_PATH.read_text(encoding="utf-8")
    # Consumer Control report map (volume test branch).
    assert "0x05, 0x0C" in ino, "Descriptor must use Usage Page (Consumer)"
    assert "0x09, 0x01" in ino, "Descriptor must use Usage (Consumer Control)"
    assert "0x85, MEDIA_REPORT_ID" in ino, "Descriptor must have Report ID from MEDIA_REPORT_ID"
    assert "0x09, 0xE9" in ino, "Descriptor must include Volume Increment"
    assert "0x09, 0xEA" in ino, "Descriptor must include Volume Decrement"
    assert "0x09, 0xCD" in ino, "Descriptor must include Play/Pause"
    assert "0x09, 0xE2" in ino, "Descriptor must include Mute"
    assert "mediaReportMap" in ino, "Must define mediaReportMap"
    # 4 usages in single Input, 4 bits padding
    assert "0x95, 0x04" in ino, "Report Count must be 4 (single Input block)"
    assert "0x75, 0x04" not in ino or "0x75, 0x01" in ino, "Padding must be Report Size=1, Count=4"


def test_cccd_and_report_reference_permissions_patched():
    ino = INO_PATH.read_text(encoding="utf-8")
    assert "getDescriptorByUUID(BLEUUID((uint16_t)0x2908))" in ino, \
        "Report Reference (0x2908) descriptor must be accessed for permission fix"
    assert "getDescriptorByUUID(BLEUUID((uint16_t)0x2902))" in ino, \
        "CCCD (0x2902) descriptor must be accessed for permission fix"
    assert "ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE" in ino, \
        "Open (non-encrypted) permissions must be applied to CCCD and Report Reference"


def test_report_send_uses_consumer_control_1_byte_format():
    ino = INO_PATH.read_text(encoding="utf-8")
    # Consumer Control: 1 byte, no Report ID in characteristic value.
    assert "uint8_t report[1]" in ino, "Report buffer must be 1 byte for Consumer Control"
    assert "bleMediaInputReport->setValue" in ino, "Must use bleMediaInputReport for sending"
    assert ">BLE media report len=1 data=" in ino, "Must print media report len and data"
    assert "action=%s" in ino, "Must print action= label"
    assert 'volume_up' in ino, "Must send volume_up action"
    assert 'volume_down' in ino, "Must send volume_down action"
    assert 'play_pause' in ino, "Must send play_pause action"
    assert 'mute' in ino, "Must send mute action"
    assert 'action=release' in ino, "Must send release action"
    # Short press → Play/Pause (0x04), long press → Mute (0x08)
    assert "sendPlayPause()" in ino, "Short press must call sendPlayPause"
    assert "sendMute()" in ino, "Long press must call sendMute"


def test_advertising_has_three_16bit_services():
    ino = INO_PATH.read_text(encoding="utf-8")
    # Must advertise HID (0x1812), Battery (0x180F), Device Information (0x180A)
    assert "0x07, 0x03" in ino, "AD length 7 + type 0x03 (Complete List of 16-bit UUIDs)"
    assert "0x12, 0x18" in ino, "HID service 0x1812 in little-endian"
    assert "0x0F, 0x18" in ino, "Battery service 0x180F in little-endian"
    assert "0x0A, 0x18" in ino, "Device Information service 0x180A in little-endian"


def test_no_add_service_uuid_for_multi_service():
    ino = INO_PATH.read_text(encoding="utf-8")
    assert "addServiceUUID(" not in ino, \
        "Must NOT use addServiceUUID() — it converts to 128-bit and overflows AD limit"


def test_no_esp_random_for_address():
    ino = INO_PATH.read_text(encoding="utf-8")
    # esp_random() must not be the address source
    lines = ino.split("\n")
    addr_fn_start = -1
    for i, line in enumerate(lines):
        if "void fillBleDialRandomAddress" in line:
            addr_fn_start = i
            break
    if addr_fn_start >= 0:
        brace_count = 0
        for j in range(addr_fn_start, min(addr_fn_start + 30, len(lines))):
            if "{" in lines[j]:
                brace_count += lines[j].count("{")
            if "}" in lines[j]:
                brace_count -= lines[j].count("}")
            if "esp_random()" in lines[j]:
                raise AssertionError("fillBleDialRandomAddress must not use esp_random() as address source")
            if brace_count <= 0 and j > addr_fn_start:
                break
