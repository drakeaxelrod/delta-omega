# Delta Lambda split keyboard — ZMK firmware build commands

root    := justfile_directory()
zmk_app := root / "zmk/app"
bdir    := root / ".build"
out     := root / "build"
config  := root / "config"

# List available commands
default:
    @just --list

# Initialize west workspace (first time only)
init:
    west init -l config
    west update
    west zephyr-export

# Update west modules (ZMK, Zephyr, etc.)
update:
    west update

# Build firmware (left half acts as central via BLE)
build: _build-left _build-right _build-reset
    mkdir -p {{out}}
    install -m 644 {{bdir}}/left/zephyr/zmk.uf2   {{out}}/delta-lambda-left.uf2
    install -m 644 {{bdir}}/right/zephyr/zmk.uf2   {{out}}/delta-lambda-right.uf2
    install -m 644 {{bdir}}/reset/zephyr/zmk.uf2   {{out}}/delta-lambda-reset.uf2
    @echo ""
    @echo "Firmware ready:"
    @ls -1 {{out}}/delta-lambda-*.uf2

# ── Internal build targets ──────────────────────────────────────────

_build-left:
    west build -s {{zmk_app}} -d {{bdir}}/left -b xiao_ble//zmk -- \
        -DSHIELD=delta_lambda_left -DZMK_CONFIG={{config}}

_build-right:
    west build -s {{zmk_app}} -d {{bdir}}/right -b xiao_ble//zmk -- \
        -DSHIELD=delta_lambda_right -DZMK_CONFIG={{config}}

_build-reset:
    west build -s {{zmk_app}} -d {{bdir}}/reset -b xiao_ble//zmk -- \
        -DSHIELD=settings_reset -DZMK_CONFIG={{config}}

# Flash a target to plugged-in XIAO (double-tap reset first)
# Usage: just flash left | right | reset
flash target:
    #!/usr/bin/env bash
    set -euo pipefail
    dev="/dev/disk/by-label/XIAO-SENSE"
    if [ ! -e "$dev" ]; then
        echo "XIAO not found — double-tap reset and try again"
        exit 1
    fi
    mountpoint=$(udisksctl mount -b "$dev" 2>/dev/null | grep -oP 'at \K.*' || true)
    if [ -z "$mountpoint" ]; then
        mountpoint="/run/media/$USER/XIAO-SENSE"
    fi
    cp "{{out}}/delta-lambda-{{target}}.uf2" "$mountpoint/"
    echo "Flashed {{target}}"

# Download XIAO nRF52840 bootloader
bootloader:
    mkdir -p {{out}}
    curl -fSL -o {{out}}/xiao-bootloader-update.uf2 \
        "https://github.com/0hotpotman0/BLE_52840_Core/raw/main/bootloader/Seeed_XIAO_nRF52840_Sense/update-Seeed_XIAO_nRF52840_Sense_bootloader-0.6.1_nosd.uf2"
    @echo "Bootloader saved to {{out}}/xiao-bootloader-update.uf2"

# Generate SVG layer diagrams
gen-svg:
    python tools/gen_svg_layers.py

# Open serial console
serial device="/dev/ttyACM0":
    picocom -b 115200 {{device}}

# Generate a UF2 that writes UICR to enable NFC pins (P0.09/P0.10) as GPIO
# Flash via UF2 bootloader — no SWD probe needed
uicr-uf2:
    #!/usr/bin/env python3
    import struct, os
    # UICR NFCPINS register at 0x1000120C — set bit 0 to 0 to disable NFC
    addr = 0x10001200
    # Build a 256-byte block: 12 bytes of 0xFF padding + our 4-byte value at offset 0x0C
    data = bytearray(b'\xff' * 256)
    struct.pack_into('<I', data, 0x0C, 0xFFFFFFFE)
    # UF2 block
    block = struct.pack('<IIIIIIII',
        0x0A324655,  # magic start 0
        0x9E5D5157,  # magic start 1
        0x00002000,  # family ID present flag
        addr,        # target address
        256,         # payload size
        0,           # block number
        1,           # total blocks
        0xADA52840,  # family ID: nRF52840
    )
    block += data
    block += b'\x00' * (512 - 4 - len(block))
    block += struct.pack('<I', 0x0AB16F30)  # magic end
    out = os.path.join("{{out}}", "uicr-nfc-as-gpio.uf2")
    os.makedirs("{{out}}", exist_ok=True)
    with open(out, 'wb') as f:
        f.write(block)
    print(f"UF2 written to {out}")
    print("Double-tap reset on XIAO, then copy to XIAO-SENSE drive")

# Unlock a chip with APPROTECT set (e.g. after RMK) via J-Link — full chip erase
recover-jlink:
    nrfjprog --recover
    @echo "Chip unlocked. Reflash the bootloader and firmware."

# Burn UICR to enable NFC pins (P0.09/P0.10) as GPIO via J-Link
# One-time operation — connect J-Link to XIAO BLE SWD pads first
uicr-jlink:
    nrfjprog --memwr 0x1000120C --val 0xFFFFFFFE
    nrfjprog --reset
    @echo "UICR written — NFC pins are now GPIO. UF2 flashing works as normal."

# Burn UICR to enable NFC pins as GPIO via OpenOCD (ST-Link or CMSIS-DAP)
uicr-openocd probe="stlink":
    openocd -f interface/{{probe}}.cfg -f target/nrf52.cfg \
        -c "init; halt; flash fillw 0x1000120C 0xFFFFFFFE 1; reset; exit"
    @echo "UICR written — NFC pins are now GPIO. UF2 flashing works as normal."

# Clean build artifacts
clean:
    rm -rf {{bdir}}
    @echo "Cleaned .build/"
