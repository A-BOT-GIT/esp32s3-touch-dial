# Windows BLE 验证清单

> 目标：在当前 `ble_hid_dial` 固件已经能稳定进入 `advertising` 的前提下，在 Windows 上完成首轮 BLE discovery / pairing / rotate / press / reconnect 验证，并沉淀成可回传的日志与分析报告。

---

## 0. 你最终只需要执行什么

优先执行这一个脚本：

```cmd
tools\run_ble_validation_and_analyze.bat
```

如果自动选串口不稳定，再手动指定原生 USB CDC 的 COM 号：

```cmd
tools\run_ble_validation_and_analyze.bat COM16 45
```

说明：
- `COM16` 只是例子，换成你机器上这块板子的原生 USB CDC 口
- `45` 是抓取秒数，可按需要改成 `60`

脚本会自动完成：
1. host-only 枚举抓取
2. full capture（主机 + 串口）
3. 自动分析并输出 `analysis_report.txt`

---

## 1. Windows 前提

### 1.1 Python 依赖

机器上需要有 Python 3，并安装 `pyserial`：

```cmd
pip install pyserial
```

或：

```cmd
py -3 -m pip install pyserial
```

### 1.2 本轮不要开的东西

不要启动这些：
- `pc-client\dial_listener.py`
- 任何旧 listener / 串口桥接工具
- 与本设备无关的串口监视器
- 会占住板子原生 USB CDC 口的终端程序

### 1.3 设备连接方式

- 板子保持通过 USB 连到 Windows
- 用原生 USB 口，不要只接桥口
- 目标串口/设备身份优先看：
  - `VID:PID=303A:1001`
  - `USB JTAG/Serial debug unit`
  - `ESP32-S3 Touch Dial`

---

## 2. 运行脚本前先确认什么

### 2.1 蓝牙设置页打开

建议先打开：
- Windows 设置 → 蓝牙和设备
- 准备好“添加设备”界面

### 2.2 如果以前配对过同名设备

建议先记一下当前状态：
- 是否已经存在旧的 `ESP32-S3 Touch Dial`
- 若有旧条目但行为异常，可先删除旧配对再测一轮

---

## 3. 脚本运行期间你要手工做什么

脚本开始后，在 full capture 阶段，请按这个顺序做：

1. 在 Windows 蓝牙里搜索设备
2. 确认是否看到：`ESP32-S3 Touch Dial`
3. 点击配对 / 连接
4. 连接后，做真实操作：
   - 左转
   - 右转
   - 按压
5. 如果时间够，再做一次：
   - 主动断开
   - 再重新连接
   - 再做一轮左转 / 右转 / 按压

---

## 4. 产物在哪里

脚本会生成两个目录：

```text
tools\captures\ble_<timestamp>_host
tools\captures\ble_<timestamp>_full
```

重点看：

- `tools\captures\ble_<timestamp>_host\host_pnp_usb.txt`
- `tools\captures\ble_<timestamp>_host\host_cim_pnp.txt`
- `tools\captures\ble_<timestamp>_full\capture.log`
- `tools\captures\ble_<timestamp>_full\summary.json`
- `tools\captures\ble_<timestamp>_full\analysis_report.txt`
- `tools\captures\ble_<timestamp>_full\analysis_report.json`

你执行完后，把 `analysis_report.txt` 的内容贴给我，或者直接告诉我 `ble_<timestamp>_full` 目录名也行。

---

## 5. 我最关心的字段

`analysis_report.txt` 里重点看这些：

- `preferred_port`
- `preferred_port_kind`
- `selected_port_matches_preferred`
- `dial_backend`
- `dial_backend_ready`
- `backend_status`
- `ble_connected`
- `ble_advertising`
- `last_backend_error`
- `last_send_type`

本轮理想倾向：

- `dial_backend: ble_hid_dial`
- `backend_status: connected_idle`（连接后）
- `ble_connected: True`
- `ble_advertising: False`（连接后）
- rotate/press 后 `last_send_type` 有更新
- 没有卡在 `last_backend_error=not_ready`

---

## 6. 本轮结论怎么判断

### 结论 A：link_only

满足倾向：
- Windows 能发现/配对
- 串口状态能看到 advertising / connected / disconnected 切换
- 但 Windows 或目标应用对 rotate / press 没有明确消费

### 结论 B：partial_hid

满足倾向：
- 能发现并连接
- 某些输入有迹象，但不稳定或不完整
- 例如 rotate 有一点反应，但 press 不稳定

### 结论 C：working_input_path

满足倾向：
- 发现、连接、重连都稳定
- rotate 和 press 都被系统或目标应用稳定消费

### 结论 D：needs_descriptor_tuning

满足倾向：
- 串口和状态机显示 BLE 链路、send 路径都正常
- 但 Windows 对 HID 语义消费不正确或完全不消费
- 说明后续重点该回到 descriptor / report 结构

---

## 7. 执行完后回传给我什么

至少回传其中之一：

1. `analysis_report.txt` 全文
2. `capture.log` 里与 BLE 相关的关键片段
3. 目录名，例如：
   - `tools\captures\ble_20260703_213500_full`

如果你愿意，也顺手补这几项：

```text
Windows 版本：
是否看到了 ESP32-S3 Touch Dial：
是否配对成功：
左转效果：
右转效果：
按压效果：
断开重连是否成功：
```

---

## 8. 当前固件前提（这次已经准备好）

这次你拿到的是 BLE / hwcdc 构建，不是 USB TinyUSB HID-only 构建。

Linux 侧已实际确认：
- 固件可正常启动
- 不再卡在 `>BLE init`
- 已进入 `>BLE advertising start`
- 可输出 `HID_STATUS reason=ble_advertising_start`

所以这轮 Windows 侧的目标不是“证明固件能启动”，而是直接验证：
- 能否被发现
- 能否配对
- 配对后 rotate / press 是否被消费
