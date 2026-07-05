#!/usr/bin/env python3
"""
roto_setup.py — HDC2450 serial configuration tool (host-side: macOS / Linux)

Writes and *verifies* Roboteq HDC2450 configuration over USB or RS232 serial,
using the Roboteq ASCII protocol. This tool is CONFIG-ONLY: it never issues a
motor command (no `!` / `!G`). It is meant for one-time / occasional bench
commissioning of the controller into analog-command mode for RA Roto Control.

Safety model (matches the project's "hardware-first, verify everything" rule):
  * Dry-run by DEFAULT — reads current values and prints a current->target
    diff, but writes NOTHING. You must pass --apply to write.
  * On --apply, every write is followed by a read-back and a VERIFY compare.
  * Writes land in controller RAM only. They are NOT persisted to flash unless
    you ALSO pass --save (which issues %EESAV). This lets you test, power-cycle,
    and re-test before committing anything permanent.
  * --audit does a pure read-only dump of the manifest keys (no writes at all).
  * Manifest items whose value is null or "TODO" are treated as "needs a value"
    and are SKIPPED on write (so a placeholder can never be flashed by accident).

Protocol reference (Roboteq Advanced Digital Motor Controllers, HDC2450 family):
  ^KEY [idx] value   SetConfig   -> reply '+' (accepted) or '-' (rejected)
  ~KEY [idx]         GetConfig   -> reply 'KEY=value'
  ?FID               firmware id (used as a connection sanity check)
  %EESAV             save config from RAM to EEPROM/flash
  Link: 115200 8N1, no flow control; commands terminated with CR ('\r').
  NOTE: the controller echoes commands by default; this tool parses tolerantly
        so it works whether echo is on or off.

The exact config *mnemonics and values* live in the JSON manifest and are marked
DRAFT there — verify each against the HDC2450 config command reference before you
--apply. This script is the safe transport + verify harness around them.

Usage:
  ./roto_setup.py --audit                         # read-only dump, auto-detect port
  ./roto_setup.py                                 # dry-run: show planned changes
  ./roto_setup.py --apply                         # write to RAM + verify
  ./roto_setup.py --apply --save                  # write to RAM, verify, then %EESAV
  ./roto_setup.py --port /dev/tty.usbmodem1101    # pin the port explicitly
  ./roto_setup.py --manifest config/other.json    # use a different manifest
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import serial  # pyserial
except ImportError:  # pragma: no cover - helpful message, not a crash
    serial = None

DEFAULT_BAUD = 115200
EOL = b"\r"
RESP_TIMEOUT = 0.5          # seconds to wait for a reply to one command
INTERCMD_DELAY = 0.03       # gentle pacing between commands
DEFAULT_MANIFEST = Path(__file__).parent / "config" / "hdc2450-analog.json"

# Ports that a Roboteq shows up as. The HDC2450 enumerates as USB CDC-ACM
# (macOS: /dev/tty.usbmodem*, Linux: /dev/ttyACM*). A USB<->RS232 adapter on
# the DB25 serial pins shows up as usbserial / ttyUSB.
PORT_GLOBS = [
    "/dev/tty.usbmodem*",
    "/dev/tty.usbserial*",
    "/dev/cu.usbmodem*",
    "/dev/cu.usbserial*",
    "/dev/ttyACM*",
    "/dev/ttyUSB*",
]

PLACEHOLDER_VALUES = {None, "", "TODO", "todo", "TBD", "tbd"}


# --------------------------------------------------------------------------- #
# Manifest model
# --------------------------------------------------------------------------- #
@dataclass
class ConfigItem:
    key: str
    value: Optional[str]
    index: Optional[str] = None
    note: str = ""

    @property
    def is_placeholder(self) -> bool:
        return self.value in PLACEHOLDER_VALUES

    def label(self) -> str:
        return f"{self.key}{(' ' + self.index) if self.index else ''}"


def load_manifest(path: Path) -> tuple[dict, list[ConfigItem]]:
    data = json.loads(path.read_text())
    items = []
    for raw in data.get("items", []):
        items.append(
            ConfigItem(
                key=str(raw["key"]).strip(),
                value=(str(raw["value"]).strip() if raw.get("value") is not None else None),
                index=(str(raw["index"]).strip() if raw.get("index") is not None else None),
                note=str(raw.get("note", "")),
            )
        )
    return data, items


# --------------------------------------------------------------------------- #
# Serial transport
# --------------------------------------------------------------------------- #
class RoboteqSerial:
    """Minimal, tolerant Roboteq ASCII client. Config + queries only."""

    def __init__(self, port: str, baud: int = DEFAULT_BAUD, debug: bool = False):
        if serial is None:
            raise RuntimeError(
                "pyserial is not installed. Run:  pip install pyserial"
            )
        self.port = port
        self.baud = baud
        self.debug = debug
        self._ser: Optional["serial.Serial"] = None

    # -- lifecycle -------------------------------------------------------- #
    def __enter__(self) -> "RoboteqSerial":
        self._ser = serial.Serial(
            self.port, self.baud, timeout=RESP_TIMEOUT,
            bytesize=8, parity="N", stopbits=1, xonxoff=False, rtscts=False,
        )
        time.sleep(0.2)
        self._ser.reset_input_buffer()
        return self

    def __exit__(self, *exc) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()

    # -- low level -------------------------------------------------------- #
    def _write(self, text: str) -> None:
        assert self._ser is not None
        if self.debug:
            print(f"  >> {text!r}")
        self._ser.write(text.encode("ascii") + EOL)
        self._ser.flush()
        time.sleep(INTERCMD_DELAY)

    def _read_lines(self) -> list[str]:
        """Read whatever the controller sent back within the timeout window."""
        assert self._ser is not None
        deadline = time.time() + RESP_TIMEOUT
        buf = b""
        while time.time() < deadline:
            chunk = self._ser.read(64)
            if chunk:
                buf += chunk
                deadline = time.time() + 0.1  # extend slightly after data
            elif buf:
                break
        lines = [l.strip() for l in buf.replace(b"\r", b"\n").split(b"\n")]
        out = [l.decode("ascii", "replace") for l in lines if l]
        if self.debug and out:
            for l in out:
                print(f"  << {l!r}")
        return out

    # -- protocol --------------------------------------------------------- #
    def firmware_id(self) -> Optional[str]:
        """?FID — used purely as a 'is anyone home?' check."""
        self._write("?FID")
        for line in self._read_lines():
            if line.startswith("FID="):
                return line[4:].strip()
            # some firmwares answer ?FID with a bare version string
            if line and not line.startswith(("+", "-")) and "=" not in line:
                return line.strip()
        return None

    def get_config(self, key: str, index: Optional[str] = None) -> Optional[str]:
        """~KEY [idx] -> 'KEY=value'. Returns the value string, or None."""
        cmd = f"~{key}" + (f" {index}" if index else "")
        self._write(cmd)
        prefix = f"{key}="
        for line in self._read_lines():
            if line.startswith(prefix):
                return line[len(prefix):].strip()
        return None

    def set_config(self, key: str, index: Optional[str], value: str) -> bool:
        """^KEY [idx] value -> '+' accepted / '-' rejected."""
        parts = [f"^{key}"]
        if index:
            parts.append(index)
        parts.append(value)
        self._write(" ".join(parts))
        for line in self._read_lines():
            if line == "+":
                return True
            if line == "-":
                return False
        # No clear +/-; treat as unknown -> caller will verify via read-back.
        return False

    def save_eeprom(self) -> bool:
        """%EESAV — persist RAM config to flash. Verify success out-of-band."""
        self._write("%EESAV")
        lines = self._read_lines()
        # Success signalling varies; a '-' is a clear failure.
        return "-" not in lines


# --------------------------------------------------------------------------- #
# Value comparison (verify step)
# --------------------------------------------------------------------------- #
def values_match(target: str, readback: Optional[str]) -> bool:
    if readback is None:
        return False
    a, b = target.strip(), readback.strip()
    if a == b:
        return True
    try:
        return int(a) == int(b)
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# Port discovery
# --------------------------------------------------------------------------- #
def discover_ports() -> list[str]:
    found: list[str] = []
    for pattern in PORT_GLOBS:
        found.extend(sorted(glob.glob(pattern)))
    # de-dup, keep order
    seen, uniq = set(), []
    for p in found:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def choose_port(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    ports = discover_ports()
    if not ports:
        sys.exit(
            "No serial port found. Plug in the HDC2450 (USB) or your USB-RS232 "
            "adapter, or pass --port explicitly.\n"
            "Tip: `ls /dev/tty.usb*` (macOS) before and after plugging in."
        )
    if len(ports) > 1:
        print("Multiple serial ports found:")
        for p in ports:
            print(f"  {p}")
        print(f"Using the first one: {ports[0]}  (override with --port)\n")
    return ports[0]


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def banner(meta: dict, port: str, mode: str) -> None:
    print("=" * 68)
    print(f"  RA Roto Control — HDC2450 serial setup   [{mode}]")
    print(f"  controller : {meta.get('controller', '?')}")
    print(f"  profile    : {meta.get('profile', '?')}")
    print(f"  port       : {port} @ {DEFAULT_BAUD} 8N1")
    print("=" * 68)
    print("  !  MOTOR POWER MUST BE OFF. This tool writes config, not motion,")
    print("     but validate on the bench with the motor stage disconnected.")
    print("=" * 68)


def print_row(label: str, current: str, target: str, status: str) -> None:
    print(f"  {label:<14} {current:<12} -> {target:<12} {status}")


# --------------------------------------------------------------------------- #
# Main flows
# --------------------------------------------------------------------------- #
def run_audit(dev: RoboteqSerial, items: list[ConfigItem]) -> int:
    print("\nCurrent controller values (read-only):\n")
    for it in items:
        cur = dev.get_config(it.key, it.index)
        cur_s = cur if cur is not None else "(no reply)"
        print(f"  {it.label():<14} = {cur_s}")
    print("\nAudit complete. No changes were made.")
    return 0


def run_configure(dev: RoboteqSerial, items: list[ConfigItem],
                  do_apply: bool, do_save: bool) -> int:
    failures = 0
    skipped = 0
    print()
    for it in items:
        cur = dev.get_config(it.key, it.index)
        cur_s = cur if cur is not None else "?"

        if it.is_placeholder:
            print_row(it.label(), cur_s, "(TODO)", "· skipped, no value in manifest")
            skipped += 1
            continue

        if not do_apply:
            same = values_match(it.value, cur)
            status = "· already set" if same else "· would write"
            print_row(it.label(), cur_s, it.value, status)
            continue

        ok_set = dev.set_config(it.key, it.index, it.value)
        readback = dev.get_config(it.key, it.index)
        verified = values_match(it.value, readback)
        if verified:
            status = "OK set & verified" if not values_match(it.value, cur) else "OK verified (unchanged)"
        else:
            status = f"FAIL VERIFY (read '{readback}', set-ack={ok_set})"
            failures += 1
        print_row(it.label(), cur_s, it.value, status)

    print()
    if skipped:
        print(f"  {skipped} item(s) skipped — fill in their value in the manifest.")

    if not do_apply:
        print("  Dry-run only. Re-run with --apply to write these to RAM.")
        return 0

    if failures:
        print(f"  {failures} item(s) FAILED verification. NOT saving. Fix and re-run.")
        return 1

    if do_save:
        print("  Saving to EEPROM (%EESAV) ...", end=" ")
        ok = dev.save_eeprom()
        print("done." if ok else "controller reported a problem — check manually.")
        return 0 if ok else 1

    print("  Written to RAM and verified. Values are NOT yet persisted.")
    print("  Power-cycle to confirm your fail-safe behavior, then re-run with")
    print("  --apply --save to commit to flash.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="HDC2450 serial config tool (config-only, verify-on-write).")
    ap.add_argument("--port", help="serial port (auto-detect if omitted)")
    ap.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--apply", action="store_true",
                    help="write config to RAM and verify (default is dry-run)")
    ap.add_argument("--save", action="store_true",
                    help="after a verified --apply, persist to flash (%%EESAV)")
    ap.add_argument("--audit", action="store_true",
                    help="read-only dump of manifest keys; no writes")
    ap.add_argument("--debug", action="store_true", help="print raw serial I/O")
    args = ap.parse_args()

    if args.save and not args.apply:
        ap.error("--save requires --apply (nothing to save otherwise).")

    if not args.manifest.exists():
        sys.exit(f"Manifest not found: {args.manifest}")

    meta, items = load_manifest(args.manifest)
    if not items:
        sys.exit("Manifest has no items.")

    port = choose_port(args.port)
    mode = "AUDIT" if args.audit else ("APPLY+SAVE" if args.save else
                                       ("APPLY" if args.apply else "DRY-RUN"))
    banner(meta, port, mode)

    try:
        with RoboteqSerial(port, args.baud, debug=args.debug) as dev:
            fid = dev.firmware_id()
            if fid:
                print(f"  Connected. Firmware ID: {fid}\n")
            else:
                print("  !  No firmware-ID reply. Check cabling/port/baud, or the")
                print("     controller may be busy running a script. Continuing...\n")

            if args.audit:
                return run_audit(dev, items)
            return run_configure(dev, items, do_apply=args.apply, do_save=args.save)
    except Exception as exc:  # noqa: BLE001 - surface a clean message
        sys.exit(f"Serial error: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
