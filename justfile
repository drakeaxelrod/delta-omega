# Delta Omega split keyboard — ZMK firmware build commands

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

# Build firmware — optional keymap argument (default: gallium, or "qwerty")
# Usage: just build | just build qwerty
build keymap="delta_omega":
    #!/usr/bin/env bash
    set -euo pipefail
    keymap_arg=""
    if [ "{{keymap}}" = "qwerty" ]; then
        keymap_arg="-DKEYMAP_FILE={{config}}/delta_omega_qwerty.keymap"
    fi
    west build -s {{zmk_app}} -d {{bdir}}/left -b xiao_ble//zmk -S studio-rpc-usb-uart -- \
        -DSHIELD=delta_omega_left -DZMK_CONFIG={{config}} $keymap_arg
    west build -s {{zmk_app}} -d {{bdir}}/right -b xiao_ble//zmk -S studio-rpc-usb-uart -- \
        -DSHIELD=delta_omega_right -DZMK_CONFIG={{config}} $keymap_arg
    west build -s {{zmk_app}} -d {{bdir}}/reset -b xiao_ble//zmk -- \
        -DSHIELD=settings_reset -DZMK_CONFIG={{config}}
    mkdir -p {{out}}
    install -m 644 {{bdir}}/left/zephyr/zmk.uf2   {{out}}/delta-omega-left.uf2
    install -m 644 {{bdir}}/right/zephyr/zmk.uf2   {{out}}/delta-omega-right.uf2
    install -m 644 {{bdir}}/reset/zephyr/zmk.uf2   {{out}}/delta-omega-reset.uf2
    echo ""
    echo "Firmware ready (keymap: {{keymap}}):"
    ls -1 {{out}}/delta-omega-*.uf2

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
    cp "{{out}}/delta-omega-{{target}}.uf2" "$mountpoint/"
    echo "Flashed {{target}}"

# Download XIAO nRF52840 Sense bootloader (UF2 update — flash via bootloader drive)
bootloader-uf2:
    mkdir -p {{out}}
    curl -fSL -o {{out}}/xiao-bootloader-update.uf2 \
        "https://github.com/0hotpotman0/BLE_52840_Core/raw/main/bootloader/Seeed_XIAO_nRF52840_Sense/update-Seeed_XIAO_nRF52840_Sense_bootloader-0.6.1_nosd.uf2"
    @echo "Saved to {{out}}/xiao-bootloader-update.uf2"
    @echo "Double-tap reset, then copy to XIAO-SENSE drive."

# Download XIAO nRF52840 Sense bootloader (HEX — flash via J-Link after recovery)
bootloader-hex:
    mkdir -p {{out}}
    curl -fSL -o /tmp/xiao-bootloader.zip \
        "https://forum.seeedstudio.com/uploads/short-url/eSDX0bezkia89iZ77eduYRwycAt.zip"
    python3 -c "import zipfile; zipfile.ZipFile('/tmp/xiao-bootloader.zip').extractall('{{out}}')"
    @echo "Saved to {{out}}/Seeed_XIAO_nRF52840_Sense_bootloader-0.6.1_s140_7.3.0.hex"
    @echo "Flash via: nrfjprog --program {{out}}/Seeed_XIAO_nRF52840_Sense_bootloader-0.6.1_s140_7.3.0.hex --verify --reset"

# Flash bootloader hex via J-Link (after recovery)
flash-bootloader-jlink:
    just bootloader-hex
    nrfjprog --program {{out}}/Seeed_XIAO_nRF52840_Sense_bootloader-0.6.1_s140_7.3.0.hex --verify --reset
    @echo "Bootloader flashed. XIAO should mount as XIAO-SENSE."

# Generate SVG layer diagrams
gen-svg:
    python tools/gen_svg_layers.py

# Open serial console
serial device="/dev/ttyACM0":
    picocom -b 115200 {{device}}

# ── SWD / J-Link commands ───────────────────────────────────────────

# Unlock a chip with APPROTECT set — full chip erase via J-Link
recover-jlink:
    nrfjprog --recover
    @echo "Chip unlocked. Reflash the bootloader and firmware."

# Write UICR to enable NFC pins (P0.09/P0.10) as GPIO via J-Link
uicr-jlink:
    nrfjprog --memwr 0x1000120C --val 0xFFFFFFFE
    nrfjprog --reset
    @echo "UICR written — NFC pins are now GPIO."

# Write UICR to enable NFC pins as GPIO via OpenOCD (CMSIS-DAP / ST-Link)
uicr-openocd probe="cmsis-dap":
    openocd -f interface/{{probe}}.cfg -f target/nrf52.cfg \
        -c "init; halt; flash fillw 0x1000120C 0xFFFFFFFE 1; reset; exit"
    @echo "UICR written — NFC pins are now GPIO."

# Clean build artifacts
clean:
    rm -rf {{bdir}}
    @echo "Cleaned .build/"
