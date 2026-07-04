# 05 验证与排障手册

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

## 2. 串口抓取

使用 v5 或更新的脚本：

```bat
run_serial_capture.bat COM15 120
```

抓取期间操作：等待 Windows 连接；右转 5 格；左转 5 格；按下释放 3 次；长按 2 秒后释放；再右转/左转。

## 3. Radial MVP 正常日志

启动：

```text
[BLE-HID] init start
[BLE-HID] security: SC_BOND + IO_NONE + ENC
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

## 4. 异常模式与处理

### 4.1 连接反复断开

症状：

```text
connected
disconnected
connected
disconnected
BT_BTM: Device not found
bta_dm_set_encryption...
```

处理：确认设备名和地址扰动已变化；打印完整地址；确认 Windows 连接的是新设备；确认 Report ID 日志正确；确认只创建一个 input report；确认没有旧 Consumer Control 代码；如仍不稳定，换 `addr[5] ^= 0x32` 和新设备名；回退到 Consumer working 分支验证 BLE 基础链路。

### 4.2 串口 `hid_skip`

症状：

```text
hid=skip
ble_connected=0
backend_status=advertising
```

处理：先解决连接稳定；不要调 payload；检查是否在连接前操作编码器；检查 `bleDialConnected`；检查 `bleRadialInputReport != nullptr`。

### 4.3 串口 `hid=sent` 但 Probe 无事件

处理顺序：确认 notify value 是 2 字节；确认不含 Report ID；确认 Report Reference 为 `01 01`；确认 Report Map top-level 是 `0x01 / 0x0E`；确认 Dial 是 `Input Data Var Rel`；确认 delta 非 0；确认 Probe 是前台窗口；改 identity 避免缓存；用 Raw HID probe 看 Windows HID 层是否收到 report。

### 4.4 Windows 不显示 radial menu

处理：先确认 Probe 能收到 RotationChanged；确认按下不是只发瞬时 click，而是长按期间保持 button=1；长按至少 1 秒；释放时发 button=0；不要在长按时发 Consumer Mute。

## 5. summary 指标解读

正常：

```text
connected >= 1
disconnected = 0 或很少
hid_sent > 0
hid_skip = 0
errors = 0 或只是假阳性
```

不正常：

```text
connected 很多
disconnected 很多
hid_sent = 0
hid_skip > 0
```

优先查 BLE 连接和缓存，不要继续改 report payload。

## 6. 分支回归测试

每当 Radial 分支失败时，切回：

```bash
git checkout test/ble-consumer-volume-working
```

烧录并测试：音量键是否有效；短按是否有效；BLE 是否稳定。

## 7. 每轮验证报告模板

```markdown
# 验证报告

## 分支
feature/ble-radial-controller-mvp

## 固件 identity
- Device name:
- Address:
- Address perturb:

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
| errors | |

## 关键日志
粘贴 startup、connect、rotation、button 日志

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
