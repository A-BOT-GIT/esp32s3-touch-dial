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

    adv_decl = "  BLEAdvertisementData bleAdvData;"
    scan_decl = "  BLEAdvertisementData bleScanRespData;"
    adv_service = "  bleAdvData.setCompleteServices(bleDialHid->hidService()->getUUID());"
    scan_name = "  bleScanRespData.setName(USB_PRODUCT_NAME);"
    apply_adv = "  bleDialAdvertising->setAdvertisementData(bleAdvData);"
    apply_scan = "  bleDialAdvertising->setScanResponseData(bleScanRespData);"

    for needle, message in [
        (adv_decl, "BLE advertising init should build explicit advertisement data"),
        (scan_decl, "BLE advertising init should build explicit scan response data"),
        (adv_service, "BLE advertising data should explicitly expose the HID service UUID"),
        (scan_name, "BLE scan response should explicitly expose the device name"),
        (apply_adv, "BLE advertising init should apply explicit advertisement data"),
        (apply_scan, "BLE advertising init should apply explicit scan response data"),
    ]:
        assert needle in ino, message

    assert ino.index(adv_decl) < ino.index(apply_adv), "advertisement payload must be built before being applied"
    assert ino.index(scan_decl) < ino.index(apply_scan), "scan response payload must be built before being applied"


def test_ble_hid_advertising_uses_explicit_random_address_before_start():
    ino = INO_PATH.read_text(encoding="utf-8")

    random_addr_fn = "void fillBleDialRandomAddress(esp_bd_addr_t addr) {"
    static_random_msb = "  addr[0] = static_cast<uint8_t>((r0 & 0x3F) | 0xC0);"
    set_random_address = "  bleDialAdvertising->setDeviceAddress(bleDialRandomAddress, BLE_ADDR_TYPE_RANDOM);"
    start_advertising = "  bleDialServer->startAdvertising();"

    assert random_addr_fn in ino, "BLE path should provide a helper that builds a static random BLE address"
    assert static_random_msb in ino, "BLE random-address helper should force the static-random top bits on the BLE address MSB"
    assert set_random_address in ino, "BLE advertising init should explicitly use a random BLE address for discovery compatibility"
    assert start_advertising in ino, "BLE advertising init should still start advertising"
    assert ino.index(set_random_address) < ino.index(start_advertising), "BLE random address must be configured before advertising starts"


def test_ble_send_helper_records_attempted_send_type_before_ready_gate():
    ino = INO_PATH.read_text(encoding="utf-8")

    send_fn = "bool bleDialSendReport(uint8_t buttons, int8_t delta, const char* sendType) {"
    set_send_type = "  setBleLastSendType(sendType);"
    ready_gate = "  if (!dialBackendReady() || bleDialInputReport == nullptr) {"

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
