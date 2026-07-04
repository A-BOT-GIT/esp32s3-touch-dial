<#
ESP32-S3 BLE HID Serial Capture Script
Version: v4
Target: Windows PowerShell 5.1 compatible
Change from v3: no Add-Type -AssemblyName System.IO.Ports
No Python required.
ASCII-only script body.
#>

[CmdletBinding()]
param(
  [string]$Port = "",
  [int]$BaudRate = 115200,
  [int]$DurationSec = 120,
  [string]$LogRoot = "",
  [switch]$ListPorts,
  [switch]$NoPrompt,
  [switch]$NoCommands,
  [string[]]$Commands = @("HID STATUS", "ENC STATUS", "HID STATUS"),
  [bool]$DtrEnable = $true,
  [bool]$RtsEnable = $false
)

$ErrorActionPreference = "Stop"

function Write-Info {
  param([string]$Message)
  Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Warn2 {
  param([string]$Message)
  Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Err2 {
  param([string]$Message)
  Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Test-SerialPortType {
  try {
    $null = [System.IO.Ports.SerialPort]
    return $true
  } catch {
    return $false
  }
}

function Get-ComNumber {
  param([string]$PortName)
  if ($PortName -match '^COM(\d+)$') {
    return [int]$Matches[1]
  }
  return 0
}

function Get-SerialPortNamesSafe {
  $names = @()

  try {
    $names = [System.IO.Ports.SerialPort]::GetPortNames()
  } catch {
    $names = @()
  }

  if ($names.Count -eq 0) {
    try {
      $items = Get-WmiObject Win32_SerialPort
      foreach ($item in $items) {
        if ($item.DeviceID -match '^COM\d+$') {
          $names += $item.DeviceID
        }
      }
    } catch {
    }
  }

  return @($names | Sort-Object)
}

function Get-SerialPortInventory {
  $names = @(Get-SerialPortNamesSafe)

  $pnps = @()
  try {
    $pnps = Get-CimInstance Win32_PnPEntity |
      Where-Object { $_.Name -match '\(COM\d+\)' } |
      Select-Object Name, Manufacturer, PNPDeviceID
  } catch {
    try {
      $pnps = Get-WmiObject Win32_PnPEntity |
        Where-Object { $_.Name -match '\(COM\d+\)' } |
        Select-Object Name, Manufacturer, PNPDeviceID
    } catch {
      $pnps = @()
    }
  }

  $items = @()

  foreach ($n in $names) {
    $desc = ""
    $mfg = ""
    $pnpid = ""

    foreach ($p in $pnps) {
      if ($p.Name -match "\($([regex]::Escape($n))\)") {
        $desc = [string]$p.Name
        $mfg = [string]$p.Manufacturer
        $pnpid = [string]$p.PNPDeviceID
        break
      }
    }

    $score = 0
    $joined = "$desc $mfg $pnpid"

    if ($joined -match 'ESP32|Espressif|USB JTAG|USB Serial|CP210|CH340|CH910|Silicon Labs|WCH|Arduino|CDC') {
      $score = $score + 10
    }

    if ($joined -match 'Bluetooth|Modem|Intel|Microsoft') {
      $score = $score - 10
    }

    $items += New-Object PSObject -Property @{
      Port = $n
      Description = $desc
      Manufacturer = $mfg
      PNPDeviceID = $pnpid
      Score = $score
      ComNumber = (Get-ComNumber $n)
    }
  }

  return $items
}

function Get-PreferredPortItem {
  param([array]$Ports)

  if ($Ports.Count -eq 0) {
    return $null
  }

  $best = $Ports[0]

  foreach ($p in $Ports) {
    if ($p.Score -gt $best.Score) {
      $best = $p
    } elseif ($p.Score -eq $best.Score) {
      if ($p.ComNumber -gt $best.ComNumber) {
        $best = $p
      }
    }
  }

  return $best
}

function Select-SerialPort {
  param(
    [string]$RequestedPort,
    [bool]$NoPromptMode
  )

  $ports = @(Get-SerialPortInventory)

  if ($RequestedPort -ne "") {
    $upper = $RequestedPort.ToUpperInvariant()
    if ($upper -notmatch '^COM\d+$') {
      throw "Invalid port format: $RequestedPort. Example: COM6"
    }
    return $upper
  }

  if ($ports.Count -eq 0) {
    throw "No COM port found. Check USB cable, driver, and whether another serial monitor is using the port."
  }

  Write-Host ""
  Write-Host "Detected serial ports:" -ForegroundColor Green

  for ($i = 0; $i -lt $ports.Count; $i++) {
    $p = $ports[$i]
    $line = "{0,2}. {1,-7} {2}" -f ($i + 1), $p.Port, $p.Description

    if ($p.Score -gt 0) {
      Write-Host $line -ForegroundColor Green
    } else {
      Write-Host $line
    }
  }

  Write-Host ""

  $preferred = Get-PreferredPortItem -Ports $ports

  if ($NoPromptMode) {
    Write-Warn2 "NoPrompt was used without -Port. Auto select: $($preferred.Port)"
    return $preferred.Port
  }

  $defaultIndex = 1
  for ($j = 0; $j -lt $ports.Count; $j++) {
    if ($ports[$j].Port -eq $preferred.Port) {
      $defaultIndex = $j + 1
      break
    }
  }

  $answer = Read-Host "Select port number, or press Enter for [$defaultIndex] $($preferred.Port)"

  if ([string]::IsNullOrWhiteSpace($answer)) {
    return $preferred.Port
  }

  $answerUpper = $answer.ToUpperInvariant()
  if ($answerUpper -match '^COM\d+$') {
    return $answerUpper
  }

  $idx = 0
  if (-not [int]::TryParse($answer, [ref]$idx)) {
    throw "Invalid selection: $answer"
  }

  if ($idx -lt 1 -or $idx -gt $ports.Count) {
    throw "Selection out of range: $idx"
  }

  return $ports[$idx - 1].Port
}

function New-CaptureDirectory {
  param([string]$Root)

  if ([string]::IsNullOrWhiteSpace($Root)) {
    $Root = Join-Path $PSScriptRoot "captures"
  }

  $ts = Get-Date -Format "yyyyMMdd_HHmmss"
  $dir = Join-Path $Root "esp32_ble_hid_serial_$ts"
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  return $dir
}

function Add-LogLine {
  param(
    [string]$Line,
    [string]$RawLog,
    [string]$TimestampLog
  )

  $now = Get-Date
  $stamp = $now.ToString("yyyy-MM-dd HH:mm:ss.fff")
  Add-Content -LiteralPath $RawLog -Value $Line -Encoding UTF8
  Add-Content -LiteralPath $TimestampLog -Value "[$stamp] $Line" -Encoding UTF8
}

function Test-InterestingLine {
  param([string]$Line)

  if ($Line -match '\[BLE-HID\]|radial report|media report|notify report|hid=sent|hid=skip|connected|disconnected|ENC STATUS|HID STATUS|ENC_BUTTON|ENC raw|RADIAL dispatch|CCCD|2902|2908|2A4B|2A4D|error|fail|failed|auth|bond|encrypt|pair|force encryption') {
    return $true
  }

  return $false
}

function Update-Stats {
  param(
    [hashtable]$Stats,
    [string]$Line
  )

  if ($Line -match '\[BLE-HID\].*\bconnected\b|\bconnected\b') { $Stats.connected = $Stats.connected + 1 }
  if ($Line -match '\[BLE-HID\].*\bdisconnected\b|\bdisconnected\b') { $Stats.disconnected = $Stats.disconnected + 1 }
  if ($Line -match 'radial report.*hid=sent') { $Stats.radial_report = $Stats.radial_report + 1 }
  if ($Line -match 'media report.*hid=sent') { $Stats.media_report = $Stats.media_report + 1 }
  if ($Line -match 'notify report') { $Stats.notify_report = $Stats.notify_report + 1 }
  if ($Line -match 'hid=sent') { $Stats.hid_sent = $Stats.hid_sent + 1 }
  if ($Line -match 'hid=skip') { $Stats.hid_skip = $Stats.hid_skip + 1 }
  if ($Line -match 'ENC STATUS') { $Stats.enc_status = $Stats.enc_status + 1 }
  if ($Line -match 'HID STATUS') { $Stats.hid_status = $Stats.hid_status + 1 }
  if ($Line -match 'ENC_BUTTON raw down') { $Stats.radial_button_down = $Stats.radial_button_down + 1 }
  if ($Line -match 'ENC_BUTTON raw up|ENC_BUTTON up held') { $Stats.radial_button_up = $Stats.radial_button_up + 1 }
  if ($Line -match 'ENC raw delta') { $Stats.enc_raw_delta = $Stats.enc_raw_delta + 1 }
  if ($Line -match 'RADIAL dispatch') { $Stats.radial_dispatch = $Stats.radial_dispatch + 1 }
  if ($Line -match 'force encryption level:\s*disabled') { $Stats.force_encryption_disabled = $Stats.force_encryption_disabled + 1 }
  if ($Line -match 'CCCD|2902') { $Stats.cccd = $Stats.cccd + 1 }
  if ($Line -match '2908|Report Reference') { $Stats.report_reference = $Stats.report_reference + 1 }
  if ($Line -match '2A4B|Report Map') { $Stats.report_map = $Stats.report_map + 1 }
  if ($Line -match 'error|fail|failed|auth fail|encrypt.*fail|pair.*fail') { $Stats.errors = $Stats.errors + 1 }
}

function Write-Summary {
  param(
    [string]$SummaryTxt,
    [string]$SummaryJson,
    [hashtable]$Stats,
    [array]$Events,
    [string]$Port,
    [int]$BaudRate,
    [datetime]$StartTime,
    [datetime]$EndTime,
    [string]$RawLog,
    [string]$TimestampLog,
    [string]$EventsCsv
  )

  $duration = [math]::Round(($EndTime - $StartTime).TotalSeconds, 3)

  $interpretation = @()

  if ($Stats.connected -gt 0) {
    $interpretation += "Connected log found. BLE connection event happened at least once."
  } else {
    $interpretation += "No connected log found. Check whether the device is connected or whether firmware prints connection logs."
  }

  if ($Stats.disconnected -gt 0 -and $Stats.connected -eq 0) {
    $interpretation += "Disconnected but no connected. Possible BLE stack restart / encryption failure."
  }

  if ($Stats.radial_report -gt 0) {
    $interpretation += "Radial report sent. Firmware attempted Radial Controller HID input."
  } elseif ($Stats.hid_sent -gt 0) {
    $interpretation += "hid=sent found (non-radial). Firmware attempted to send HID input reports."
  } else {
    $interpretation += "No hid=sent found. Check encoder event path and bleDialConnected state first."
  }

  if ($Stats.radial_button_down -gt 0 -and $Stats.radial_button_up -gt 0) {
    $interpretation += "Button down/up pair found. Button state machine is producing both press and release."
  } elseif ($Stats.radial_button_down -gt 0) {
    $interpretation += "Button down found but no matching up. Release report may be missing."
  }

  if ($Stats.force_encryption_disabled -gt 0) {
    $interpretation += "Force encryption is disabled. This is the expected stable configuration."
  }

  if ($Stats.cccd -gt 0) {
    $interpretation += "CCCD / 2902 related log found. Continue checking whether host enabled notifications."
  }

  if ($Stats.errors -gt 0) {
    $interpretation += "Error/fail/auth/encrypt related log found. Inspect timestamp log context first."
  }

  $summaryLines = @()
  $summaryLines += "ESP32-S3 BLE HID Serial Capture Summary"
  $summaryLines += "======================================"
  $summaryLines += "Start:       $($StartTime.ToString('yyyy-MM-dd HH:mm:ss.fff'))"
  $summaryLines += "End:         $($EndTime.ToString('yyyy-MM-dd HH:mm:ss.fff'))"
  $summaryLines += "Duration:    $duration seconds"
  $summaryLines += "Port:        $Port"
  $summaryLines += "BaudRate:    $BaudRate"
  $summaryLines += ""
  $summaryLines += "Counters:"

  foreach ($k in @("connected","disconnected","radial_report","media_report","hid_sent","hid_skip","enc_status","hid_status","radial_button_down","radial_button_up","enc_raw_delta","radial_dispatch","force_encryption_disabled","cccd","report_reference","report_map","errors","total_lines","interesting_lines")) {
    $summaryLines += ("  {0,-20} {1}" -f $k, $Stats[$k])
  }

  $summaryLines += ""
  $summaryLines += "Interpretation:"

  foreach ($item in $interpretation) {
    $summaryLines += "  - $item"
  }

  $summaryLines += ""
  $summaryLines += "Files:"
  $summaryLines += "  Raw log:        $RawLog"
  $summaryLines += "  Timestamp log:  $TimestampLog"
  $summaryLines += "  Events CSV:     $EventsCsv"
  $summaryLines += "  Summary JSON:   $SummaryJson"

  Set-Content -LiteralPath $SummaryTxt -Value $summaryLines -Encoding UTF8

  $jsonObj = @{
    start = $StartTime.ToString("o")
    end = $EndTime.ToString("o")
    duration_sec = $duration
    port = $Port
    baud_rate = $BaudRate
    counters = $Stats
    files = @{
      raw_log = $RawLog
      timestamp_log = $TimestampLog
      events_csv = $EventsCsv
      summary_txt = $SummaryTxt
      summary_json = $SummaryJson
    }
    interpretation = $interpretation
    events = $Events
  }

  $jsonObj | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $SummaryJson -Encoding UTF8
}

try {
  if (-not (Test-SerialPortType)) {
    throw "System.IO.Ports.SerialPort is not available in this PowerShell/.NET runtime. Use Windows PowerShell 5.1, or install/use PowerShell with System.IO.Ports support."
  }

  if ($ListPorts) {
    $ports = @(Get-SerialPortInventory)

    if ($ports.Count -eq 0) {
      Write-Warn2 "No COM port found."
      exit 1
    }

    $ports | Format-Table Port, Score, Description, Manufacturer -AutoSize
    exit 0
  }

  $selectedPort = Select-SerialPort -RequestedPort $Port -NoPromptMode:$NoPrompt
  $captureDir = New-CaptureDirectory -Root $LogRoot

  $rawLog = Join-Path $captureDir "serial_raw.log"
  $timestampLog = Join-Path $captureDir "serial_timestamped.log"
  $eventsCsv = Join-Path $captureDir "events.csv"
  $summaryTxt = Join-Path $captureDir "summary.txt"
  $summaryJson = Join-Path $captureDir "summary.json"

  "time,kind,line" | Set-Content -LiteralPath $eventsCsv -Encoding UTF8

  Write-Host ""
  Write-Host "========================================" -ForegroundColor Green
  Write-Host "ESP32-S3 BLE HID Serial Capture v4" -ForegroundColor Green
  Write-Host "Port:      $selectedPort"
  Write-Host "BaudRate:  $BaudRate"
  Write-Host "Duration:  $DurationSec seconds"
  Write-Host "Output:    $captureDir"
  Write-Host "DTR/RTS:   DTR=$DtrEnable RTS=$RtsEnable"
  Write-Host "========================================" -ForegroundColor Green
  Write-Host ""
  Write-Host "Before capture:" -ForegroundColor Yellow
  Write-Host "  1. Close Arduino Serial Monitor or PlatformIO monitor."
  Write-Host "  2. Keep ESP32-S3 Touch Dial connected."
  Write-Host "  3. During capture: rotate left/right, short press, long press."
  Write-Host "  4. Ctrl+C can stop capture early."
  Write-Host ""

  if (-not $NoPrompt) {
    Read-Host "Press Enter to start capture"
  }

  $sp = New-Object System.IO.Ports.SerialPort
  $sp.PortName = $selectedPort
  $sp.BaudRate = $BaudRate
  $sp.Parity = [System.IO.Ports.Parity]::None
  $sp.DataBits = 8
  $sp.StopBits = [System.IO.Ports.StopBits]::One
  $sp.Handshake = [System.IO.Ports.Handshake]::None
  $sp.ReadTimeout = 100
  $sp.WriteTimeout = 1000
  $sp.DtrEnable = $DtrEnable
  $sp.RtsEnable = $RtsEnable

  try {
    $sp.Encoding = New-Object System.Text.UTF8Encoding $false
  } catch {
  }

  $stats = @{
    connected = 0
    disconnected = 0
    radial_report = 0
    media_report = 0
    notify_report = 0
    hid_sent = 0
    hid_skip = 0
    enc_status = 0
    hid_status = 0
    radial_button_down = 0
    radial_button_up = 0
    enc_raw_delta = 0
    radial_dispatch = 0
    force_encryption_disabled = 0
    cccd = 0
    report_reference = 0
    report_map = 0
    errors = 0
    total_lines = 0
    interesting_lines = 0
  }

  $events = @()
  $buffer = ""
  $start = Get-Date
  $end = $start

  try {
    $sp.Open()
    Write-Info "Serial opened: $selectedPort"

    Start-Sleep -Milliseconds 700

    if (-not $NoCommands) {
      foreach ($cmd in $Commands) {
        if ([string]::IsNullOrWhiteSpace($cmd)) {
          continue
        }

        try {
          $sp.WriteLine($cmd)
          $sentLine = ">>> $cmd"
          Add-LogLine -Line $sentLine -RawLog $rawLog -TimestampLog $timestampLog
          Write-Host $sentLine -ForegroundColor DarkYellow
          Start-Sleep -Milliseconds 250
        } catch {
          Write-Warn2 "Failed to send command: $cmd ; $($_.Exception.Message)"
        }
      }
    }

    $deadline = $null
    if ($DurationSec -gt 0) {
      $deadline = $start.AddSeconds($DurationSec)
    }

    while ($true) {
      if ($deadline -ne $null -and (Get-Date) -ge $deadline) {
        break
      }

      $chunk = ""
      try {
        $chunk = $sp.ReadExisting()
      } catch {
        Write-Warn2 "Serial read failed: $($_.Exception.Message)"
        Start-Sleep -Milliseconds 100
        continue
      }

      if ($chunk.Length -gt 0) {
        $buffer = $buffer + $chunk.Replace("`r", "")

        while ($buffer.Contains("`n")) {
          $idx2 = $buffer.IndexOf("`n")
          $line = $buffer.Substring(0, $idx2)
          $buffer = $buffer.Substring($idx2 + 1)
          $line = $line.TrimEnd()

          if ($line.Length -eq 0) {
            continue
          }

          $stats.total_lines = $stats.total_lines + 1
          Update-Stats -Stats $stats -Line $line
          Add-LogLine -Line $line -RawLog $rawLog -TimestampLog $timestampLog

          $isInteresting = Test-InterestingLine -Line $line

          if ($isInteresting) {
            $stats.interesting_lines = $stats.interesting_lines + 1

            $now = Get-Date
            $eventObj = New-Object PSObject -Property @{
              time = $now.ToString("o")
              line = $line
            }

            $events += $eventObj

            $escaped = $line.Replace('"','""')
            Add-Content -LiteralPath $eventsCsv -Value ('"{0}","serial","{1}"' -f $now.ToString("o"), $escaped) -Encoding UTF8

            Write-Host ("[{0}] {1}" -f $now.ToString("HH:mm:ss.fff"), $line) -ForegroundColor Green
          } else {
            Write-Host $line
          }
        }
      } else {
        Start-Sleep -Milliseconds 30
      }
    }

    if ($buffer.Trim().Length -gt 0) {
      $line = $buffer.Trim()
      $stats.total_lines = $stats.total_lines + 1
      Update-Stats -Stats $stats -Line $line
      Add-LogLine -Line $line -RawLog $rawLog -TimestampLog $timestampLog

      if (Test-InterestingLine -Line $line) {
        $stats.interesting_lines = $stats.interesting_lines + 1
      }
    }
  } finally {
    $end = Get-Date

    if ($sp -and $sp.IsOpen) {
      $sp.Close()
      Write-Info "Serial closed."
    }

    Write-Summary `
      -SummaryTxt $summaryTxt `
      -SummaryJson $summaryJson `
      -Stats $stats `
      -Events $events `
      -Port $selectedPort `
      -BaudRate $BaudRate `
      -StartTime $start `
      -EndTime $end `
      -RawLog $rawLog `
      -TimestampLog $timestampLog `
      -EventsCsv $eventsCsv

    Write-Host ""
    Write-Host "Done." -ForegroundColor Green
    Write-Host "Summary:       $summaryTxt"
    Write-Host "Summary JSON:  $summaryJson"
    Write-Host "Timestamp log: $timestampLog"
    Write-Host ""
  }
} catch {
  Write-Err2 $_.Exception.Message
  Write-Host ""
  Write-Host "Common causes:" -ForegroundColor Yellow
  Write-Host "  - COM port is used by Arduino IDE, PlatformIO monitor, or another tool."
  Write-Host "  - Wrong COM port."
  Write-Host "  - ESP32 is not connected or USB driver is missing."
  Write-Host "  - Current PowerShell runtime lacks System.IO.Ports.SerialPort."
  Write-Host ""
  if (-not $NoPrompt) {
    pause
  }
  exit 1
}
