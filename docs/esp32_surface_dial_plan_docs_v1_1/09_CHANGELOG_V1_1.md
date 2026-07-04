# 09 Changelog v1.1

## 更新原因

最新实机日志证明，关闭：

```cpp
BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
```

后，Consumer Control / Media Dial 分支从反复断连恢复为稳定连接：

```text
[BLE-HID] security: SC_BOND + IO_NONE
[BLE-HID] force encryption level: disabled
connected=2
disconnected=0
hid_sent=86
hid_skip=0
```

因此原计划需要优化。

---

## 主要修改

### 1. no-force-encryption 从实验升级为主线策略

旧计划：

```text
移除 setEncryptionLevel 只是一个实验。
```

新计划：

```text
后续 BLE HID 主线默认不强制调用 setEncryptionLevel。
```

---

### 2. Phase 0 稳定基线变更

旧基线：

```text
稳定 BLE HOGP 基线。
```

新基线：

```text
SC_BOND + IO_NONE + force encryption disabled + CCCD/ReportRef patched。
```

---

### 3. B+C 分支判断修正

旧判断：

```text
B+C 分支本身不稳定，不适合作为起点。
```

新判断：

```text
B+C 映射本身没有被证明有问题；
断连主要来自强制 setEncryptionLevel；
修复 no-force-encryption 后，B+C / Media Dial 可作为 Consumer Control 诊断基线。
```

但仍强调：

```text
B+C 不是 Surface Dial。
```

---

### 4. Radial MVP 起点更新

旧起点：

```text
稳定 BLE HOGP 基线。
```

新起点：

```text
no-force-encryption 稳定 BLE 初始化策略。
```

---

### 5. 验收标准更新

新增：

```text
force encryption level: disabled
```

新增失败条件：

```text
默认 BLE_FORCE_ENCRYPTION_LEVEL=1 不允许合并。
```

---

### 6. 排障手册更新

连接反复断开时第一步改为检查：

```text
BLE_FORCE_ENCRYPTION_LEVEL 是否被误设为 1
```

---

### 7. Agent 任务更新

新增 Task：

```text
Task 1：固化 no-force-encryption BLE 初始化策略
```

并让 Radial MVP 从该策略继续开发。

---

## 没有改变的内容

以下主目标不变：

```text
正式目标仍然是 Surface Dial / Radial Controller；
Consumer Control 仍然只是诊断基线；
Radial MVP 仍然必须使用:
- System Multi-Axis Controller
- Button + Dial
- RADIAL_REPORT_ID = 1
- ReportRef = 01 01
- 2-byte BLE payload without Report ID
```

---

## 当前下一步

建议立即执行：

```text
1. 保存 test/ble-consumer-volume-no-force-encrypt-working
2. 打 tag: ble-hid-no-force-encrypt-working
3. 从 no-force-encryption 策略创建 feature/ble-radial-controller-mvp
4. 将 Media Dial 替换为 Radial Controller MVP
5. 用 Windows Radial Probe 验证
```
