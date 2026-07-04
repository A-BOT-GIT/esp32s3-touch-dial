# 05 验证与排障手册

版本：v1.1

## 1. 每轮测试必须保存的文件

每次烧录后测试都保存：

```text
summary.txt
serial_raw.log
serial_timestamped.log
events.csv
summary.json
```

文件夹命名建议：

```text
captures/radial_mvp_<identity>_<date>_<test_case>/
```

例如：

```text
captures/radial_mvp_0x31_20260704_rotation_button/
```

---

## 2. 串口抓取

使用 v5 或更新的脚本：

```bat
run_serial_capture.bat COM15 120
```

抓取期间操作：

1. 等待 Windows 连接；
2. 右转 5 格；
3. 左转 5 格；
4. 按下释放 3 次；
5. 长按 2 秒后释放；
6. 再右转/左转。

---

## 3. Radial MVP 正常日志

启动：

```text
[BLE-HID] init start
[BLE-HID] security: SC_BOND + IO_NONE
[BLE-HID] force encryption level: disabled
[BLE-HID] address: XX:XX:XX:XX:XX:XX
[BLE-HID] radial report id: 1
[BLE-HID] radial report map size: N
[BLE-HID] radial input report created
[BLE-HID] radial report ref: 01 01
[BLE-HID] descriptor permissions patched: 2908=yes, 2902=yes
[BLE-HID] services started
[BLE-HID] adv services: 1812,180F,180A
[BLE-HID] advertising started
```

连接：

```text
>BLE connected
[BLE-HID] connected
>HID_STATUS ... dial_backend_ready=1 backend_status=connected_idle ble_connected=1
```

旋转：

```text
>BLE radial report len=2 data=02 00 button=0 delta=1 hid=sent
>BLE radial report len=2 data=FE FF button=0 delta=-1 hid=sent
```

按键：

```text
>BLE radial report len=2 data=01 00 button=1 delta=0 hid=sent
>BLE radial report len=2 data=00 00 button=0 delta=0 hid=sent
```

---

## 4. no-force-encryption 诊断基线正常日志

Consumer Control 诊断分支正常时类似：

```text
[BLE-HID] security: SC_BOND + IO_NONE
[BLE-HID] force encryption level: disabled
[BLE-HID] media report id: 2
[BLE-HID] media report ref: 02 01
connected=2
disconnected=0
hid_sent=86
hid_skip=0
```

旋转和按键：

```text
data=02 action=volume_down hid=sent
data=01 action=volume_up hid=sent
data=04 action=play_pause hid=sent
data=08 action=mute hid=sent
```

这只证明 BLE HID 传输链路稳定，不代表 Surface Dial 完成。

---

## 5. 异常模式与处理

### 5.1 连接反复断开

症状：

```text
connected
disconnected
connected
disconnected
BT_BTM: Device not found
bta_dm_set_encryption...
```

处理：

1. 先检查是否误启用：
   ```text
   BLE_FORCE_ENCRYPTION_LEVEL=1
   ```
2. 确认日志为：
   ```text
   force encryption level: disabled
   ```
3. 确认设备名和地址扰动已变化；
4. 打印完整地址；
5. 确认 Windows 连接的是新设备；
6. 确认 Report ID 日志正确；
7. 确认只创建一个 input report；
8. 确认没有旧 Consumer Control 代码；
9. 如仍不稳定，换 `addr[5] ^= 0x32` 和新设备名；
10. 回退 no-force-encryption Consumer baseline 对照。

---

### 5.2 串口 `hid_skip`

症状：

```text
hid=skip
ble_connected=0
backend_status=advertising
```

处理：

1. 先解决连接稳定；
2. 不要调 payload；
3. 检查是否在连接前操作编码器；
4. 检查 `bleDialConnected` 状态；
5. 检查 `bleRadialInputReport != nullptr`。

---

### 5.3 串口 `hid=sent` 但 Probe 无事件

处理顺序：

1. 确认 notify value 是 2 字节；
2. 确认不含 Report ID；
3. 确认 Report Reference 为 `01 01`；
4. 确认 Report Map top-level 是 `0x01 / 0x0E`；
5. 确认 Dial 是 `Input Data Var Rel`；
6. 确认 delta 非 0；
7. 确认 Probe 是前台窗口；
8. 改 identity 避免缓存；
9. 用 Raw HID probe 看 Windows HID 层是否收到 report。

---

### 5.4 Windows 不显示 radial menu

处理：

1. 先确认 Probe 能收到 RotationChanged；
2. 确认按下不是只发瞬时 click，而是长按期间保持 button=1；
3. 长按至少 1 秒；
4. 释放时发 button=0；
5. 不要在长按时发 Consumer Mute；
6. 检查 Windows 设置中 Wheel/Radial 相关设置。

---

## 6. summary 指标解读

### 6.1 正常

```text
connected >= 1
disconnected = 0 或很少
hid_sent > 0
hid_skip = 0
无真实 BT_APPL / BT_BTM / auth / encryption 失败刷屏
```

### 6.2 注意 errors 误报

旧脚本可能会把：

```text
last_backend_error=none
```

误计入 `errors`。

所以不要只看 summary 的 `errors` 数字。优先看：

```text
disconnected
hid_sent
hid_skip
真实 BT_APPL / BT_BTM / auth / encryption 错误上下文
```

### 6.3 不正常

```text
connected 很多
disconnected 很多
hid_sent = 0
hid_skip > 0
```

优先查 BLE 连接、缓存和 forced encryption，不要继续改 report payload。

---

## 7. 分支回归测试

每当 Radial 分支失败时，切回：

```bash
git checkout test/ble-consumer-volume-no-force-encrypt-working
```

烧录并测试：

- 音量键是否有效；
- 短按/长按是否有效；
- BLE 是否稳定；
- 是否仍然 `force encryption level: disabled`。

如果 Consumer no-force baseline 也失败，说明环境或 Windows 端状态变了。  
如果 Consumer no-force baseline 成功，说明 Radial 分支 descriptor/report 有问题。

---

## 8. 每轮验证报告模板

```markdown
# 验证报告

## 分支

feature/ble-radial-controller-mvp

## 固件 identity

- Device name:
- Address:
- Address perturb:
- Force encryption level:

## 编译结果

| 命令 | 结果 |
|---|---|
| compile BLE | |
| compile USB+CDC | |
| pytest -q | |

## 串口结果

| 指标 | 值 |
|---|---|
| connected | |
| disconnected | |
| hid_sent | |
| hid_skip | |
| real BT errors | |

## 关键日志

```text
粘贴 startup、connect、rotation、button 日志
```

## Windows Probe 结果

| 事件 | 是否收到 |
|---|---|
| RotationChanged right | |
| RotationChanged left | |
| Button event | |
| Long press menu | |

## 结论

- PASS / FAIL
- 下一步
```
