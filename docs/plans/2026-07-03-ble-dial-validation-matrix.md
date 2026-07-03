# BLE Dial Validation Matrix

> 目标：在 Windows 上验证当前 `ble_hid_dial` backend 是否已经达到“可发现、可配对、可重连、可发送、可被主机消费”的状态，并把每次实验结果沉淀成可比较证据，而不是停留在口头印象。

---

## 0. 本文使用方式

每做一轮 Windows BLE 实机验证，都应：

1. 先确认当前固件构建和提交上下文
2. 按本文矩阵逐项执行
3. 记录串口日志观察、Windows 主机行为、抓包/截图/文字证据
4. 最后把本轮结果归类为以下四种之一：
   - `link_only`
   - `partial_hid`
   - `working_input_path`
   - `needs_descriptor_tuning`

如果本轮没有落到这四类之一，则本轮验证视为记录不完整。

---

## 1. 验证前准备

### 1.1 固件前提

使用当前 BLE backend 构建：

```bash
rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3' /home/zza/projects/esp32s3_touch_dial
```

验证前建议再次确认：

```bash
rtk proxy python3 -m pytest /home/zza/projects/esp32s3_touch_dial/tests -q
rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3' /home/zza/projects/esp32s3_touch_dial
rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/esp32s3_touch_dial
```

说明：
- `esp32:esp32:esp32s3` = 当前 BLE/hwcdc 验证目标
- `USBMode=default,CDCOnBoot=cdc` = USB TinyUSB 参考路径，验证 BLE 变更没有把 USB 行为搞坏

Linux 侧当前已知补充：
- `arduino-cli upload` 在这块板子的原生 USB 路径上，收尾阶段可能报：
  - `A fatal error occurred: Packet content transfer stopped (received 25 bytes)`
- 若出现该错误，不要只凭 upload exit code 判断“刷写失败”；应以启动串口和运行态日志为准
- 当前已验证可用的保守刷写路径：先固定 `--build-path` 编译，再用核心自带 `esptool.py --no-stub write_flash` 手工写入 4 段镜像
- 本轮 Linux 实测已经确认：修复后的 BLE 固件可以稳定输出 `>BLE advertising start` 与 `reason=ble_advertising_start`

### 1.2 Windows 侧前提

- 打开 Windows 蓝牙设置页
- 关闭与本设备无关的串口终端、旧 listener、桥口监控工具
- 若机器此前配对过同名 BLE 设备，先记录是否保留旧配对
- 本轮记录中注明 Windows 版本与目标应用场景（系统级 / 某应用）

### 1.3 串口观察前提

BLE 版本当前主要通过 hwcdc 路径输出调试与状态。
建议至少保留一份串口观察，重点看：

- `>BLE init`
- `>BLE advertising start`
- `>BLE connected`
- `>BLE disconnected`
- `>BLE report ...`
- `>BLE report skip reason=...`
- `>HID_STATUS ...`

重点字段：
- `dial_backend`
- `dial_backend_ready`
- `backend_status`
- `ble_connected`
- `ble_advertising`
- `last_backend_error`
- `last_send_type`

语义约束（本轮开始固定使用）：
- `dial_backend_ready=1` 目前只表示 BLE 链路已连接，且固件侧 input report notify 路径存在，可尝试发送。
- `dial_backend_ready=1` 不等于“Windows 已确认消费 rotate / press 输入”。
- “主机已消费输入”只能通过以下证据判定：
  - Windows 或目标应用出现明确可观察到的 rotate / press 效果；或
  - 有独立主机侧抓取/日志证明输入已进入上层。
- 因此首轮实机验证中，`connected_idle + dial_backend_ready=1 + last_send_type=...` 最多只能证明：
  - 固件已经走到 link-ready 并尝试发送；
  - 不能单凭这些字段就把结果归类为 `working_input_path`。

Linux 侧当前基线（已实测）：
- `>PROBE setup.begin`
- `>BLE init`
- `>BLE advertising start`
- `>HID_STATUS reason=ble_advertising_start ... backend_status=advertising ... ble_connected=0 ble_advertising=1 ... last_backend_error=none`
- `>PROBE setup.done`
- `>HELLO`

---

## 2. 结果分类规则

### A. link_only

满足倾向：
- Windows 能发现/配对设备
- 串口显示 advertising / connected / disconnected 正常切换
- 但旋转/按压没有被系统或目标应用明确消费
- 只能证明链路与状态机存在，不能证明输入路径可用

### B. partial_hid

满足倾向：
- Windows 能发现并连接
- 某些输入有迹象，但不稳定、不连续或只有部分动作生效
- 例如 rotate 有反应但 press 没反应，或首次有反应但重连后失效

### C. working_input_path

满足倾向：
- Windows 能稳定发现、连接、重连
- rotate 与 press 都能被系统或目标应用稳定消费
- 高频输入、断开重连、重新广播后仍保持一致

### D. needs_descriptor_tuning

满足倾向：
- 链路和 backend 状态机明显正常
- 串口也显示 send 路径在工作
- 但 Windows 对 HID 语义消费不正确或完全不消费
- 说明问题更可能在 descriptor / identity / report 结构，而不是简单链路问题

---

## 3. 验证矩阵

### 3.1 Discovery（发现）

目标：确认 Windows 能看到 BLE 设备，并且设备命名/身份符合预期。

执行：
1. 设备上电
2. 打开 Windows 蓝牙添加设备界面
3. 观察设备是否出现

记录：
- 是否出现设备
- 设备显示名称
- 从上电到出现所需时间
- 串口是否出现：
  - `>BLE init`
  - `>BLE advertising start`
  - `backend_status=advertising`
  - `ble_advertising=1`

通过标准：
- Windows 在合理时间内发现设备
- 串口侧 advertising 状态与主机发现时间一致

失败信号：
- 串口说 advertising，但 Windows 长时间看不到设备
- 设备名异常、重复、无法区分

---

### 3.2 Pairing（配对）

目标：确认 Windows 能成功发起并完成配对/连接。

执行：
1. 在 Windows 里点击配对/连接
2. 等待系统结果
3. 观察串口状态变化

记录：
- 是否配对成功
- 是否需要重复点击
- 是否出现失败提示
- 串口是否出现：
  - `>BLE connected`
  - `dial_backend_ready=1`
  - `backend_status=connected_idle`
  - `ble_connected=1`
  - `ble_advertising=0`

通过标准：
- Windows 配对动作能把串口状态切到 connected/ready

失败信号：
- Windows 提示配对失败
- 串口没有 connect 事件
- backend 停留在 advertising 或 error

---

### 3.3 Ready Transition（ready 状态切换）

目标：确认 `dial_backend_ready` 的含义在实机上稳定成立。

执行：
1. 设备未连接时查询/观察一次状态
2. 连接后再次观察状态
3. 断开后再次观察状态

记录：
- 未连接时：
  - `dial_backend_ready=0`
  - `backend_status=advertising` 或其他等待态
- 已连接时：
  - `dial_backend_ready=1`
  - `backend_status=connected_idle`
- 断开后：
  - `dial_backend_ready=0`
  - 是否重新进入 advertising

通过标准：
- ready 与链路状态一致切换
- 没有“Windows 已断开但固件还卡在 ready”之类错误状态

---

### 3.4 Rotate Behavior（旋转）

目标：验证 rotate 语义是否被 Windows 或目标应用消费。

执行：
1. 连接完成后，做低速左转/右转
2. 再做连续快速旋转
3. 观察系统/应用反应与串口日志

记录：
- 左转是否有效
- 右转是否有效
- 快速旋转是否出现漏发/过量/无反应
- 串口是否出现：
  - `>BLE report rotate delta=...`
  - `last_send_type=rotate_left/right`
  - `last_backend_error=none`
  - 或 `rate_limited_rotate`

通过标准：
- 至少低速 rotate 可稳定消费
- 快速 rotate 的表现可解释（例如被节流）

失败信号：
- 串口显示发送了 rotate，但 Windows/应用完全没反应
- 左右方向不一致
- 快速输入导致明显卡死或错误状态

---

### 3.5 Press Behavior（按压）

目标：验证 press pulse 语义是否被 Windows 或目标应用消费。

执行：
1. 单次按压
2. 间隔按压
3. 快速连续按压

记录：
- 单次 press 是否生效
- 多次 press 是否稳定
- 快速连按是否触发：
  - `last_send_type=press`
  - `last_backend_error=none`
  - 或 `rate_limited_press`

通过标准：
- 单击行为可稳定消费
- 快速连按时即使被节流，也应有可解释日志

失败信号：
- 串口侧 press 已发送，但主机完全无消费
- 连按导致连接异常或状态卡住

---

### 3.6 Disconnect / Re-advertise（断开 / 重新广播）

目标：验证断开后状态机是否能回到可发现状态。

执行：
1. 已连接状态下，从 Windows 侧断开或关蓝牙
2. 观察设备是否重新广播
3. 再次在 Windows 蓝牙列表确认设备可见

记录：
- 是否出现：
  - `>BLE disconnected`
  - `>BLE advertising restart`
  - `backend_status=advertising`
  - `ble_advertising=1`
- Windows 是否能再次看到设备

通过标准：
- 断开后能自动回到 advertising
- 无需重启板子即可再次被发现

失败信号：
- 断开后无法再次发现设备
- 状态停在错误态或未重新广播

---

### 3.7 Reconnect（重连）

目标：验证断开后的第二次连接是否与第一次一致。

执行：
1. 完成一次连接和基本输入测试
2. 主动断开
3. 再次连接
4. 重新测试 rotate / press

记录：
- 第二次连接是否成功
- 第二次连接后 `dial_backend_ready` 是否恢复正常
- 第二次连接后 rotate / press 是否仍可消费

通过标准：
- 重连后的行为与首次连接基本一致

失败信号：
- 首次可用，重连后失效
- 重连后只剩 link，没有 HID 输入效果

---

### 3.8 Repeated Input（重复输入 / 节流行为）

目标：验证 send-rate control 是否符合预期，而不是引入不可解释丢包。

执行：
1. 慢速 rotate 10 次
2. 快速 rotate 一小段
3. 慢速 press 5 次
4. 快速连按一小段

记录：
- 正常输入是否仍可靠
- 高频输入是否触发：
  - `rate_limited_rotate`
  - `rate_limited_press`
- 节流发生时，设备是否仍保持 connected_idle / advertising 等稳定态

通过标准：
- 节流只在高频输入下触发
- 节流不会把 backend 状态打坏

失败信号：
- 正常低频输入也频繁被 rate-limit
- 节流后 backend 状态异常

---

### 3.9 Sleep / Wake Retest（睡眠 / 唤醒复测）

目标：确认 Windows 睡眠、蓝牙重置或设备重上电后仍可恢复。

执行：
可选至少做一种：
1. Windows 睡眠再唤醒
2. 关闭再打开蓝牙
3. 板子重启后重新连接

记录：
- 唤醒后是否还能发现设备
- 是否需要删除旧配对再重新配对
- 重连后 rotate / press 是否保持原有表现

通过标准：
- 经过一次恢复场景后，仍能回到 discovery -> connect -> input 的闭环

失败信号：
- 恢复后只能发现不能连接
- 或只能连接不能输入

---

## 4. 首轮建议执行顺序（可直接照做）

适用于“还没有任何 Windows BLE 实机结论”的第一轮验证。

### 4.1 验证前本地确认

先在 Linux 仓库侧确认当前基线：

```bash
rtk proxy python3 -m pytest /home/zza/projects/esp32s3_touch_dial/tests -q
rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3' /home/zza/projects/esp32s3_touch_dial
rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/esp32s3_touch_dial
```

预期：
- pytest 全绿
- BLE/hwcdc compile 通过
- USB TinyUSB compile 通过

### 4.2 首轮 Windows 侧最短流程

1. 烧录当前 BLE/hwcdc 版本固件
2. 打开 Windows 蓝牙设置页，进入“添加设备”界面
3. 打开串口观察，准备记录 `>BLE ...` 与 `>HID_STATUS ...`
4. 观察 discovery
5. 点击配对/连接
6. 连接成功后先做：
   - 低速左转 3 次
   - 低速右转 3 次
   - 单击 3 次
7. 再做一轮高频输入：
   - 快速旋转一小段
   - 快速连按一小段
8. 从 Windows 侧断开
9. 确认是否自动重新 advertising
10. 再次连接并重复一次 rotate + press

### 4.3 首轮建议证据最小集

首轮至少保留下面这些证据：

- 一份串口原始日志
- 一段 discovery/配对界面观察文字
- 一段 rotate/press 的主机反应文字
- 一段断开/重连后的状态文字
- 最终结论分类

如果无法截图，至少把关键串口行和 Windows 侧现象文字抄进本文记录区。

## 5. 本轮记录模板

```text
验证日期：
固件构建：
Windows 版本：
目标应用/场景：
串口观察方式：

A. Discovery
- 是否发现设备：
- 设备名：
- advertising 串口证据：

B. Pairing
- 是否配对成功：
- connect 串口证据：
- ready 状态：

C. Rotate
- 低速左转：
- 低速右转：
- 快速旋转：
- send/skip 证据：

D. Press
- 单次按压：
- 间隔按压：
- 快速连按：
- send/skip 证据：

E. Disconnect / Re-advertise
- 是否自动重新广播：
- 串口证据：

F. Reconnect
- 是否成功：
- 重连后 rotate：
- 重连后 press：

G. Sleep / Wake
- 场景：
- 结果：

H. 本轮结论分类
- link_only / partial_hid / working_input_path / needs_descriptor_tuning

I. 下一步动作
-
```

### 5.1 首轮记录骨架（待回填）

```text
验证日期：待填
固件构建：esp32:esp32:esp32s3
Windows 版本：待填
目标应用/场景：系统级蓝牙发现 + 基础 rotate/press 消费验证
串口观察方式：待填

A. Discovery
- 是否发现设备：待填
- 设备名：待填
- advertising 串口证据：待填

B. Pairing
- 是否配对成功：待填
- connect 串口证据：待填
- ready 状态：待填

C. Rotate
- 低速左转：待填
- 低速右转：待填
- 快速旋转：待填
- send/skip 证据：待填

D. Press
- 单次按压：待填
- 间隔按压：待填
- 快速连按：待填
- send/skip 证据：待填

E. Disconnect / Re-advertise
- 是否自动重新广播：待填
- 串口证据：待填

F. Reconnect
- 是否成功：待填
- 重连后 rotate：待填
- 重连后 press：待填

G. Sleep / Wake
- 场景：首轮可暂不做
- 结果：待填

H. 本轮结论分类
- 待填

I. 下一步动作
- 待填
```

---

## 6. 当前已知重点观察点

基于当前固件实现，实机时应特别关注：

1. `dial_backend_ready=1` 目前表示“链路 ready”，不是“Windows 已确认正确消费输入”
2. `last_send_type` 只表示最近一次尝试发送的类型，不等于主机一定消费成功
3. `last_backend_error=rate_limited_rotate/press` 是预期节流现象，不一定是故障
4. 如果串口显示 rotate/press 都在发送，但 Windows 无消费，更应优先怀疑 descriptor / report / identity 兼容性，而不是简单链路问题

---

## 6. 下一步衔接

如果验证结果是：

- `link_only`：继续确认 descriptor / host consumption 问题，不要误判为可用
- `partial_hid`：优先补证据，确认是 rotate/press 哪一类更不稳定
- `working_input_path`：进入 README、验证流程、触摸辅助化收尾
- `needs_descriptor_tuning`：按单变量原则调整 descriptor / report 结构，每轮修改后回填本文记录
