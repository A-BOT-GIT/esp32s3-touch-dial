#!/usr/bin/env python3
"""ESP32-S3 Touch Dial DIAG automated test script.

Usage:
  python3 diag_test.py              # run all tests once
  python3 diag_test.py --loop       # run in loop with DTR resets
  python3 diag_test.py --reset-only # just reset the device

Requires: pyserial (python3 -m pip install --user pyserial)
Ports: /dev/ttyACM1 (CH343P, command+log), /dev/ttyACM0 (HWCDC, flash only)
"""

import serial
import time
import sys
import argparse


PORT = '/dev/ttyACM1'
BAUD = 115200
BOOT_WAIT = 15  # seconds to wait after reset for BLE firmware to boot


def connect():
    """Open serial port without triggering DTR reset."""
    s = serial.Serial(PORT, BAUD, timeout=2, dsrdtr=False)
    s.rts = True
    s.dtr = True
    time.sleep(0.3)
    return s


def cmd(s, text, wait=0.5):
    """Send a command and wait."""
    s.write((text + '\r\n').encode())
    time.sleep(wait)


def read_all(s, wait=3):
    """Read all available data."""
    time.sleep(wait)
    data = b''
    while s.in_waiting > 0:
        data += s.read(s.in_waiting)
    return data.decode('latin-1').replace('\r', '\n')


def reset_via_dtr():
    """Reset ESP32 by pulsing CH343P DTR low."""
    s = connect()
    s.dtr = False
    time.sleep(0.5)
    s.dtr = True
    time.sleep(0.5)
    s.close()
    print('[RESET] DTR pulse done')
    time.sleep(BOOT_WAIT)


def run_tests():
    """Run full diagnostic test suite."""
    s = connect()

    # --- Quiet mode ---
    cmd(s, 'LOG QUIET')
    print('[TEST] LOG QUIET sent')

    # --- Enable all diagnostics ---
    cmd(s, 'DIAG ALL ON', 0.5)
    print('[TEST] DIAG ALL ON sent')

    # --- DIAG STATUS ---
    cmd(s, 'DIAG STATUS', 0.3)
    out = read_all(s)
    print('[TEST] DIAG STATUS:')
    for line in out.split('\n'):
        if 'DIAG_STATUS' in line:
            print(f'  {line.strip()}')

    # --- BLE STATUS ---
    cmd(s, 'BLE STATUS', 2)
    out = read_all(s)
    print('[TEST] BLE STATUS:')
    for line in out.split('\n'):
        if 'BLE_STATUS' in line:
            print(f'  {line.strip()}')

    # --- HID STATUS ---
    cmd(s, 'HID STATUS', 3)
    out = read_all(s)
    print('[TEST] HID STATUS:')
    for line in out.split('\n'):
        if 'HID_STATUS' in line:
            parts = line.strip().split()
            # Print key fields
            for p in parts:
                if any(k in p for k in ('notify_enabled', 'cccd_value',
                                         'hid_sent_count', 'hid_skip_count',
                                         'last_notify_result', 'ble_connected',
                                         'dial_backend_ready')):
                    print(f'  {p}')

    # --- RADIAL TEST CW ---
    cmd(s, 'RADIAL TEST CW', 2)
    out = read_all(s)
    print('[TEST] RADIAL TEST CW:')
    for line in out.split('\n'):
        if 'RADIAL_NOTIFY' in line or 'RADIAL_TEST' in line:
            print(f'  {line.strip()}')

    # --- RADIAL TEST DOWN ---
    cmd(s, 'RADIAL TEST DOWN', 1)
    out = read_all(s)
    print('[TEST] RADIAL TEST DOWN:')
    for line in out.split('\n'):
        if 'RADIAL_NOTIFY' in line or 'RADIAL_TEST' in line:
            print(f'  {line.strip()}')

    # --- RADIAL TEST UP ---
    cmd(s, 'RADIAL TEST UP', 1)
    out = read_all(s)
    print('[TEST] RADIAL TEST UP:')
    for line in out.split('\n'):
        if 'RADIAL_NOTIFY' in line or 'RADIAL_TEST' in line:
            print(f'  {line.strip()}')

    s.close()
    print('[TEST] All tests done.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--loop', action='store_true', help='Run tests in loop with DTR resets')
    parser.add_argument('--reset-only', action='store_true', help='Just reset the device')
    parser.add_argument('--count', type=int, default=3, help='Number of loop iterations')
    args = parser.parse_args()

    if args.reset_only:
        reset_via_dtr()
        return

    if args.loop:
        for i in range(args.count):
            print(f'\n{"="*60}')
            print(f'ITERATION {i+1}/{args.count}')
            print(f'{"="*60}')
            run_tests()
            if i < args.count - 1:
                print(f'\n[RESET] Resetting for next iteration...')
                reset_via_dtr()
        return

    run_tests()


if __name__ == '__main__':
    main()
