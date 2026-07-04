# 08 Git 分支、提交、回退、发布计划

版本：v1.1

## 1. 分支结构

建议：

```text
main
├── test/ble-consumer-volume-no-force-encrypt-working
├── feature/ble-radial-controller-mvp
├── feature/win-radial-probe
├── experiment/ble-radial-haptics
└── experiment/ble-radial-onscreen
```

---

## 2. main 分支原则

`main` 只合并：

- 编译通过；
- pytest 通过；
- 实机验证通过；
- 文档同步更新；
- 不含明显调试脏代码；
- 默认不强制 `setEncryptionLevel`。

---

## 3. Consumer Control 诊断分支

用途：

```text
只做 BLE HID 传输诊断，不作为最终 Surface Dial 产品。
```

命名：

```text
test/ble-consumer-volume-no-force-encrypt-working
```

tag：

```text
ble-hid-no-force-encrypt-working
```

不建议合并到 main，除非作为可选诊断模式隐藏在编译开关后。

---

## 4. Radial MVP 分支

命名：

```text
feature/ble-radial-controller-mvp
```

起点：

```text
no-force-encryption 稳定 BLE 初始化策略
```

提交建议：

```bash
git commit -m "fix(ble): default to no forced encryption level"
git commit -m "feat(ble): add radial controller HID report map"
git commit -m "fix(ble): send radial HOGP report without report id"
git commit -m "test(hid): validate radial payload packing"
git commit -m "docs(radial): add validation playbook"
```

---

## 5. Windows Probe 分支

命名：

```text
feature/win-radial-probe
```

提交建议：

```bash
git commit -m "tools(windows): add radial controller probe app"
git commit -m "docs(windows): document radial probe workflow"
```

---

## 6. 实验分支

### Haptic

```text
experiment/ble-radial-haptics
```

### On-screen puck

```text
experiment/ble-radial-onscreen
```

这些不阻塞 MVP。

---

## 7. 回退策略

如果 Radial 分支出现连接抖动：

```bash
git checkout test/ble-consumer-volume-no-force-encrypt-working
```

验证 BLE 基础链路。

如果 Consumer no-force working 正常，说明 Radial 分支问题在：

- descriptor；
- report reference；
- report value；
- Windows cache；
- 多 characteristic；
- identity 未变；
- 或 Radial 特有 usage。

如果 Consumer no-force working 也异常，说明：

- Windows 蓝牙状态变了；
- ESP32 蓝牙状态变了；
- 运行环境/供电/驱动问题；
- 需要更换 identity 或清理配对。

---

## 8. 提交前检查清单

```bash
git status
pytest -q
arduino-cli compile --fqbn esp32:esp32:esp32s3 .
```

再检查：

- 是否误提交 captures 大日志；
- 是否误提交临时 build；
- 是否误提交本机路径；
- 是否保留了过多 `HELLO`；
- 是否设备名和 address perturb 有文档记录；
- 是否默认 `BLE_FORCE_ENCRYPTION_LEVEL=0`；
- 是否测试报告已保存。

---

## 9. .gitignore 建议

确保忽略：

```gitignore
captures/
*.log
summary*.txt
summary*.json
events*.csv
/tmp/
build/
dist/
```

如果需要保留关键验证日志，放入：

```text
docs/validation/
```

并裁剪为小文件。

---

## 10. 发布版本定义

### v0.1

```text
BLE Consumer Control diagnostic working
```

### v0.2

```text
BLE no-force-encryption baseline working
```

### v0.3

```text
Radial MVP report descriptor compiles and tests pass
```

### v0.4

```text
Windows Probe receives RotationChanged and Button events
```

### v0.5

```text
Radial menu interaction works
```

### v1.0

```text
可作为 Surface Dial 替代设备日常使用
```
