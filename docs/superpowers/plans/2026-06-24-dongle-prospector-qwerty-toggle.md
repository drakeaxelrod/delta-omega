# Delta Omega — Dongle, Prospector & Runtime QWERTY Toggle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional screenless-XIAO and Prospector dongle centrals (both halves as peripherals) and a runtime Gallium↔QWERTY base-layer toggle, while keeping the existing standalone (left-as-central) mode, and fix the Zephyr-4.1 CI failure.

**Architecture:** Mirror the user's proven **totem** config (`/home/draxel/Projects/totem`): dedicated per-role shields (`_left` peripheral, `_left_central` central, `_right` peripheral, `_dongle` central), a shared `*-layout.dtsi`, a `mock_kscan` for the keyless dongle, and per-role `.conf` files. QWERTY becomes layer 1 (alternate base) toggled from a Util key, replacing the separate compile-time QWERTY keymap. `just build` produces three self-contained mode directories under `build/`.

**Tech Stack:** ZMK (`main`, Zephyr 4.1), Seeed XIAO nRF52840 (`xiao_ble//zmk`), `carrefinho/prospector-zmk-module@feat/new-status-screens`, west, just, Nix dev shell, Python (stdlib) for SVG generation.

## Global Constraints

- ZMK target: `main` / Zephyr 4.1. Board reference: `xiao_ble//zmk` (matches totem).
- Prospector module pinned to **`feat/new-status-screens`** (verified identical to totem).
- All firmware builds run inside the Nix shell: prefix commands with `nix develop -c`.
- Each `west build` uses a **separate `.build/<name>` dir** and explicit `-DSHIELD` / `-DKEYMAP_FILE` (stale shared CMake caches previously produced wrong firmware — never reuse a build dir across shields/keymaps).
- The shield module currently lives in the separate repo `zmk-keyboard-delta-omega` (fetched via `config/west.yml`). Shield edits happen there and must be committed+pushed for CI; local builds read the on-disk checkout.
- Single keymap after this work: `config/delta_omega.keymap` (QWERTY is a layer in it). `config/delta_omega_qwerty.keymap` is deleted.
- "Tests" = successful builds + asserted `.config` contents (ZMK has no unit-test harness). Each task verifies with a build and/or a `grep` of the generated `.config`, then commits.

---

## Phase 0 — Fix the Zephyr-4.1 board-variant CI failure (prerequisite)

CI fails for all builds with `CONFIG_ZMK_BOARD_COMPAT` / "the selected board is not set up
for ZMK and there is a ZMK variant available". Totem builds on the **same** `xiao_ble//zmk` +
ZMK `main`, so the board reference is fine; the difference is structural between totem
(in-config shield, no `boards/` subdir) and delta-omega (separate module + a
`boards/xiao_ble_zmk.overlay` file).

### Task 0.1: Reproduce the failure locally against ZMK `main`

**Files:** none (diagnostic)

- [ ] **Step 1: Update the local ZMK checkout to current `main`** so local reproduces CI.

```bash
cd /home/draxel/Projects/delta-omega
nix develop -c west update zmk
```

- [ ] **Step 2: Attempt the current standalone build and capture the error**

```bash
nix develop -c just build-standalone 2>&1 | tee /tmp/dz-boardvariant.log | tail -40
```
Expected: the same `CONFIG_ZMK_BOARD_COMPAT` / board-variant error CI shows. If it now
builds clean, the CI failure was a transient/old commit — skip to Task 0.4 (verify CI) and
proceed.

- [ ] **Step 3: Diff our shield structure against totem's working shield**

```bash
diff <(cd /home/draxel/Projects/totem/config/boards/shields/totem && ls) \
     <(cd /home/draxel/Projects/delta-omega/zmk-keyboard-delta-omega/boards/shields/delta_omega && ls)
cat /home/draxel/Projects/delta-omega/zmk-keyboard-delta-omega/boards/shields/delta_omega/boards/xiao_ble_zmk.overlay
cat /home/draxel/Projects/delta-omega/zmk-keyboard-delta-omega/boards/shields/delta_omega/delta_omega.zmk.yml
```
Note: totem has **no** `boards/` subdir and its `zmk.yml` uses `requires: [seeeduino_xiao_ble]`;
ours uses `requires: [xiao_ble]` and carries a `boards/xiao_ble_zmk.overlay`.

### Task 0.2: Apply the board-variant fix in the shield module

**Files:**
- Modify: `zmk-keyboard-delta-omega/boards/shields/delta_omega/delta_omega.zmk.yml`
- Move: `.../boards/xiao_ble_zmk.overlay` → fold its LED/NFC/I2C/serial content into each shield overlay (or rename per variant rules)

The board-specific overlay `boards/xiao_ble_zmk.overlay` is the leading suspect: under the
Zephyr-4.1 variant system the file must match the variant board id. totem avoids the issue by
not using a board-named overlay at all — it puts the XIAO LED/NFC setup directly in its
`.dtsi`. Mirror that.

- [ ] **Step 1: Read the current board overlay content** (so it isn't lost)

```bash
cat /home/draxel/Projects/delta-omega/zmk-keyboard-delta-omega/boards/shields/delta_omega/boards/xiao_ble_zmk.overlay
```
(It defines the RGB LED `gpio-leds` aliases, `nfct-pins-as-gpios`, and disables `xiao_i2c`/`xiao_serial`.)

- [ ] **Step 2: Move that content into the shared shield dtsi** (created/renamed in Phase 2;
  for now, append it to `delta_omega.dtsi` under the root node) and **delete** the
  `boards/xiao_ble_zmk.overlay` file and the now-empty `boards/` dir.

```bash
cd /home/draxel/Projects/delta-omega/zmk-keyboard-delta-omega/boards/shields/delta_omega
git rm boards/xiao_ble_zmk.overlay
```
Append the LED `aliases`/`leds` node, `&uicr { nfct-pins-as-gpios; }`, and the
`&xiao_i2c { status = "disabled"; }` / `&xiao_serial { status = "disabled"; }` blocks into
`delta_omega.dtsi` (root level), verbatim from Step 1.

- [ ] **Step 3: Rebuild to confirm the board-variant error is gone**

```bash
cd /home/draxel/Projects/delta-omega
nix develop -c just build-standalone 2>&1 | tail -20
```
Expected: build proceeds past board selection and produces `zmk.uf2` for left + right.

- [ ] **Step 4: Commit (shield module repo)**

```bash
cd /home/draxel/Projects/delta-omega/zmk-keyboard-delta-omega
git add -A
git commit -m "fix: drop board-named overlay for Zephyr 4.1 variant compatibility"
git push origin main
```

### Task 0.3: If Step 0.2 is insufficient — fold the shield into the config repo

**Only if** CI still errors after 0.2 (the separate module isn't resolving its board_root
under the new variant rules). totem keeps its shield in-config; do the same.

**Files:**
- Create: `config/boards/shields/delta_omega/` (move all shield files here)
- Modify: `config/west.yml` (remove the `zmk-keyboard-delta-omega` project)

- [ ] **Step 1: Move the shield into the config tree**

```bash
cd /home/draxel/Projects/delta-omega
mkdir -p config/boards/shields
cp -r zmk-keyboard-delta-omega/boards/shields/delta_omega config/boards/shields/
```

- [ ] **Step 2: Remove the module project from `config/west.yml`** (delete the
  `zmk-keyboard-delta-omega` project entry; keep zmk + rgbled-widget). The in-config
  `boards/` is found automatically via `ZMK_CONFIG`.

- [ ] **Step 3: Re-init west and rebuild**

```bash
nix develop -c just clean
nix develop -c just build-standalone 2>&1 | tail -20
```
Expected: clean build.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: move delta_omega shield into config tree (Zephyr 4.1 reliability)"
```

### Task 0.4: Verify CI is green

- [ ] **Step 1: Push and watch the run**

```bash
cd /home/draxel/Projects/delta-omega
git push
gh run watch "$(gh run list --limit 1 --json databaseId -q '.[0].databaseId')" || gh run list --limit 1
```
Expected: the `build` job's matrix entries complete and upload UF2 artifacts.

---

## Phase 1 — Runtime QWERTY toggle

Replaces the separate `delta_omega_qwerty.keymap` firmware with a layer-1 QWERTY base
toggled from the Util layer.

### Task 1.1: Renumber layers and add the QWERTY layer

**Files:**
- Modify: `config/delta_omega.keymap` (the `#define` block, insert `qwerty_layer`, edit `util_layer` pos 9)

**Interfaces:**
- Produces: layer indices `BASE=0, QWERTY=1, NAV=2, NUM=3, FUN=4, UTIL=5, GAME=6` consumed by Task 1.2 (SVG) and Task 1.3 (cleanup).

- [ ] **Step 1: Update the layer `#define` block** (currently `BASE 0 … GAME 5`) to:

```c
#define BASE   0
#define QWERTY 1
#define NAV    2
#define NUM    3
#define FUN    4
#define UTIL   5
#define GAME   6
```

- [ ] **Step 2: Insert the `qwerty_layer` immediately after `base_layer`** (so it is layer
  index 1). Alphas + home-row mods are lifted from the current QWERTY base; thumbs are
  `&trans` to inherit the Gallium thumb behaviors:

```c
        qwerty_layer {
            display-name = "QWERTY";
            bindings = <
       &kp Q        &kp W        &kp E            &kp R                    &kp T    &kp Y  &kp U                    &kp I                 &kp O        &kp P
       &hml LGUI A  &hml LALT S  &hml LCTRL D     &hml LSHFT F             &kp G    &kp H  &hmr RSHFT J             &hmr RCTRL K          &hmr RALT L  &hmr RGUI SEMI
       &kp Z        &kp X        &kp C            &hml LS(LC(LA(LGUI))) V  &kp B    &kp N  &hmr RS(RC(RA(RGUI))) M  &kp COMMA             &kp DOT      &kp FSLH
                                                  &trans        &trans            &trans     &trans
            >;
        };
```

- [ ] **Step 3: Add the toggle key to `util_layer` top-right (position 9)** — change the
  last `&trans` on the util top row to `&tog QWERTY`:

```c
       &bt BT_SEL 0  &bt BT_SEL 1  &bt BT_SEL 2  &bt BT_SEL 3  &bt BT_SEL 4      &trans     &trans          &trans          &trans        &tog QWERTY
```

- [ ] **Step 4: Add `display-name` to each existing layer** (aids the Prospector layer
  roller) if not already present: `base_layer` → "Base", `nav_layer` → "Nav", etc. (Several
  already have `display-name`; add to any that don't.)

- [ ] **Step 5: Build standalone and assert it compiles with 7 layers**

```bash
cd /home/draxel/Projects/delta-omega
nix develop -c just build-standalone 2>&1 | tail -15
```
Expected: build succeeds (left + right `zmk.uf2` produced), no devicetree/keymap errors.

- [ ] **Step 6: Commit**

```bash
git add config/delta_omega.keymap
git commit -m "feat(keymap): add runtime QWERTY toggle layer (Util top-right)"
```

### Task 1.2: Update the SVG generator for 7 layers

**Files:**
- Modify: `tools/gen_svg_layers.py`

**Interfaces:**
- Consumes: layer indices from Task 1.1.

- [ ] **Step 1: Update the layer arrays and held-thumb map**

```python
LAYER_NAMES = ["base", "qwerty", "nav", "num", "fun", "util", "game"]
LAYER_DISPLAY = ["Base (Gallium)", "QWERTY", "Nav", "Num", "Fun", "Util + Mouse", "Game"]

# Which thumb position activates each layer (for "held" highlighting)
HELD_THUMBS = {
    2: 31,   # NAV  → hold Space thumb
    3: 32,   # NUM  → hold Enter thumb
    4: 33,   # FUN  → hold Backspace thumb
    5: 30,   # UTIL → hold Escape thumb
}
```

- [ ] **Step 2: Update the layer-count sanity check** from `!= 6` to `!= 7`:

```python
    if len(layers) != 7:
        print(f"Warning: expected 7 layers, found {len(layers)}")
```

- [ ] **Step 3: Run the generator and confirm a qwerty SVG is produced**

```bash
cd /home/draxel/Projects/delta-omega
python3 tools/gen_svg_layers.py
ls assets/svg/layers/qwerty.svg
```
Expected: prints 7 layer paths incl. `assets/svg/layers/qwerty.svg`; no "expected 7" warning.

- [ ] **Step 4: Commit**

```bash
git add tools/gen_svg_layers.py assets/svg/layers/
git commit -m "feat(svg): render the QWERTY layer; renumber held-thumb map"
```

### Task 1.3: Remove the separate QWERTY keymap & its build paths

**Files:**
- Delete: `config/delta_omega_qwerty.keymap`
- Modify: `justfile` (remove `qwerty` arg handling — superseded), `README.md`

- [ ] **Step 1: Delete the standalone QWERTY keymap**

```bash
cd /home/draxel/Projects/delta-omega
git rm config/delta_omega_qwerty.keymap
```

- [ ] **Step 2: Remove the `qwerty` branch from the `build` recipe** in `justfile` (the
  recipe is fully replaced in Phase 3; for now drop the `if {{keymap}} = qwerty` block and
  the `keymap` argument so nothing references the deleted file).

- [ ] **Step 3: Update `README.md`** — replace the "Gallium / QWERTY are separate builds"
  wording with: a single firmware containing both; switch with the Util top-right toggle key;
  reverts to Gallium on reboot.

- [ ] **Step 4: Grep to confirm no dangling references**

```bash
grep -rn "delta_omega_qwerty" . --include="*.yml" --include="*.yaml" --include="justfile" --include="*.md" | grep -v docs/superpowers || echo "clean"
```
Expected: `clean`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: drop separate QWERTY firmware in favor of runtime toggle"
```

---

## Phase 2 — Dongle & per-role shields (shield module)

All paths below are in `zmk-keyboard-delta-omega/boards/shields/delta_omega/` (or
`config/boards/shields/delta_omega/` if Task 0.3 ran). Model on totem.

### Task 2.1: Split the physical layout into a shared dtsi

**Files:**
- Create: `delta_omega-layout.dtsi`
- Modify: `delta_omega.dtsi`

- [ ] **Step 1: Create `delta_omega-layout.dtsi`** containing only the
  `physical_layouts.dtsi` include and the `physical_layout0` node (the `keys` block currently
  in `delta_omega.dtsi`), named so it can be shared. Keep the existing PG1316S key dimensions.

- [ ] **Step 2: Edit `delta_omega.dtsi`** to `#include "delta_omega-layout.dtsi"`, keep the
  `kscan0` matrix + `default_transform` + `chosen { zmk,kscan = &kscan0; zmk,physical-layout = &physical_layout0; }`,
  and remove the inline `physical_layout0` block (now in the shared file).

- [ ] **Step 3: Build standalone to confirm the refactor is inert**

```bash
cd /home/draxel/Projects/delta-omega
nix develop -c just build-standalone 2>&1 | tail -12
```
Expected: builds identically to before.

- [ ] **Step 4: Commit (module repo)**

```bash
cd zmk-keyboard-delta-omega && git add -A && git commit -m "refactor: split physical layout into delta_omega-layout.dtsi" && cd ..
```

### Task 2.2: Make `delta_omega_left` the peripheral; add `delta_omega_left_central`

**Files:**
- Modify: `Kconfig.shield`, `Kconfig.defconfig`, `delta_omega_left.conf`
- Create: `delta_omega_left_central.overlay`, `delta_omega_left_central.conf`
- Modify: `delta_omega.zmk.yml`

**Interfaces:**
- Produces: shields `delta_omega_left` (peripheral), `delta_omega_left_central` (central, PERIPHERALS=1), consumed by build matrix (Phase 3).

- [ ] **Step 1: Add the central shield symbol to `Kconfig.shield`**

```
config SHIELD_DELTA_OMEGA_LEFT
    def_bool $(shields_list_contains,delta_omega_left)

config SHIELD_DELTA_OMEGA_LEFT_CENTRAL
    def_bool $(shields_list_contains,delta_omega_left_central)

config SHIELD_DELTA_OMEGA_RIGHT
    def_bool $(shields_list_contains,delta_omega_right)

config SHIELD_DELTA_OMEGA_DONGLE
    def_bool $(shields_list_contains,delta_omega_dongle)
```

- [ ] **Step 2: Rewrite `Kconfig.defconfig`** so `_left` is a plain peripheral and
  `_left_central` is the central (modeled on totem):

```
if SHIELD_DELTA_OMEGA_LEFT_CENTRAL
config ZMK_KEYBOARD_NAME
    default "Delta Omega"
config ZMK_SPLIT_ROLE_CENTRAL
    default y
config ZMK_SPLIT_BLE_CENTRAL_PERIPHERALS
    default 1
config ZMK_SPLIT
    default y
config ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING
    default y
config ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_PROXY
    default y
endif

if SHIELD_DELTA_OMEGA_LEFT
config ZMK_KEYBOARD_NAME
    default "Delta Omega L"
config ZMK_SPLIT
    default y
endif

if SHIELD_DELTA_OMEGA_RIGHT
config ZMK_KEYBOARD_NAME
    default "Delta Omega R"
config ZMK_SPLIT
    default y
endif
```

- [ ] **Step 3: Create `delta_omega_left_central.overlay`** (same kscan col-gpios as
  `delta_omega_left.overlay`):

```c
#include "delta_omega.dtsi"

&kscan0 {
    col-gpios
        = <&xiao_d 0 GPIO_ACTIVE_HIGH>
        , <&xiao_d 1 GPIO_ACTIVE_HIGH>
        , <&xiao_d 2 GPIO_ACTIVE_HIGH>
        , <&xiao_d 3 GPIO_ACTIVE_HIGH>
        , <&xiao_d 4 GPIO_ACTIVE_HIGH>
        ;
};
```

- [ ] **Step 4: Move the central-battery proxy conf** out of `delta_omega_left.conf` into a
  new `delta_omega_left_central.conf` (so the peripheral left build is clean). Result:

`delta_omega_left.conf` (peripheral) — keep only peripheral-safe settings (BLE experimental conn).
`delta_omega_left_central.conf`:

```
# Left half as central (no dongle)
CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING=y
CONFIG_ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_PROXY=y
```

- [ ] **Step 5: Add `delta_omega_left_central` to `delta_omega.zmk.yml` siblings.**

- [ ] **Step 6: Build standalone using the new central shield**

```bash
cd /home/draxel/Projects/delta-omega
nix develop -c west build -p -s zmk/app -d .build/lc -b xiao_ble//zmk -- \
  -DSHIELD=delta_omega_left_central -DZMK_CONFIG=config
grep -E "CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y|CONFIG_ZMK_SPLIT_BLE_CENTRAL_PERIPHERALS=1" .build/lc/zephyr/.config
```
Expected: both CONFIG lines present; build succeeds.

- [ ] **Step 7: Build `delta_omega_left` and assert it is a peripheral**

```bash
nix develop -c west build -p -s zmk/app -d .build/lp -b xiao_ble//zmk -- \
  -DSHIELD=delta_omega_left -DZMK_CONFIG=config
grep -E "CONFIG_ZMK_SPLIT_ROLE_CENTRAL" .build/lp/zephyr/.config || echo "not central (correct)"
```
Expected: `CONFIG_ZMK_SPLIT_ROLE_CENTRAL` is not `=y` (peripheral).

- [ ] **Step 8: Commit (module repo)**

```bash
cd zmk-keyboard-delta-omega && git add -A && git commit -m "feat: split left into peripheral + central shields" && cd ..
```

### Task 2.3: Add the `delta_omega_dongle` shield

**Files:**
- Create: `delta_omega_dongle.overlay`, `delta_omega_dongle.conf`
- Modify: `Kconfig.defconfig`, `delta_omega.zmk.yml`

- [ ] **Step 1: Create `delta_omega_dongle.overlay`** (keyless central; mock kscan; reuse
  transform + shared layout), modeled on `totem_dongle.overlay`:

```c
#include <dt-bindings/zmk/matrix_transform.h>
#include "delta_omega-layout.dtsi"

/ {
    chosen {
        zmk,kscan = &mock_kscan;
        zmk,physical-layout = &physical_layout0;
    };

    mock_kscan: mock_kscan_0 {
        compatible = "zmk,kscan-mock";
        columns = <0>;
        rows = <0>;
        events = <0>;
    };

    default_transform: keymap_transform_0 {
        compatible = "zmk,matrix-transform";
        columns = <10>;
        rows = <4>;
        map = <
            RC(0,0) RC(0,1) RC(0,2) RC(0,3) RC(0,4)    RC(0,5) RC(0,6) RC(0,7) RC(0,8) RC(0,9)
            RC(1,0) RC(1,1) RC(1,2) RC(1,3) RC(1,4)    RC(1,5) RC(1,6) RC(1,7) RC(1,8) RC(1,9)
            RC(2,0) RC(2,1) RC(2,2) RC(2,3) RC(2,4)    RC(2,5) RC(2,6) RC(2,7) RC(2,8) RC(2,9)
                                    RC(3,3) RC(3,4)    RC(3,5) RC(3,6)
        >;
    };
};

&physical_layout0 {
    transform = <&default_transform>;
};
```
(Note: the `map` matches `delta_omega.dtsi`'s existing 34-key transform — copy it verbatim.)

- [ ] **Step 2: Add the dongle block to `Kconfig.defconfig`** (central, 2 peripherals,
  always-on), modeled on totem:

```
if SHIELD_DELTA_OMEGA_DONGLE
config ZMK_KEYBOARD_NAME
    default "Delta Omega"
config ZMK_SPLIT_ROLE_CENTRAL
    default y
config ZMK_SPLIT
    default y
config ZMK_SPLIT_BLE_CENTRAL_PERIPHERALS
    default 2
config BT_MAX_CONN
    default 7
config BT_MAX_PAIRED
    default 7
config ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_FETCHING
    default y
config ZMK_SPLIT_BLE_CENTRAL_BATTERY_LEVEL_PROXY
    default y
config ZMK_USB_BOOT
    default y
config ZMK_SLEEP
    default n
endif
```

- [ ] **Step 3: Create `delta_omega_dongle.conf`** (always-on, BLE output, studio; Prospector
  screen options are read only when the adapter shield is present):

```
# Dongle: always-on USB/BLE central
CONFIG_ZMK_IDLE_TIMEOUT=86400000
CONFIG_ZMK_SLEEP=n
CONFIG_ZMK_BLE=y
CONFIG_BT_CTLR_TX_PWR_PLUS_8=y
CONFIG_ZMK_BLE_EXPERIMENTAL_CONN=y
CONFIG_ZMK_STUDIO=y

# Prospector status screen (ignored on the screenless build)
CONFIG_PROSPECTOR_STATUS_SCREEN_OPERATOR=y
CONFIG_PROSPECTOR_MODIFIER_OS_GENERIC=y
CONFIG_PROSPECTOR_USE_AMBIENT_LIGHT_SENSOR=n
CONFIG_PROSPECTOR_FIXED_BRIGHTNESS=100
```

- [ ] **Step 4: Add `delta_omega_dongle` to `delta_omega.zmk.yml` siblings.**

- [ ] **Step 5: Build the screenless dongle and assert central+2 peripherals**

```bash
cd /home/draxel/Projects/delta-omega
nix develop -c west build -p -s zmk/app -d .build/dg -b xiao_ble//zmk -- \
  -DSHIELD=delta_omega_dongle -DZMK_CONFIG=config -DSNIPPET=studio-rpc-usb-uart
grep -E "CONFIG_ZMK_SPLIT_ROLE_CENTRAL=y|CONFIG_ZMK_SPLIT_BLE_CENTRAL_PERIPHERALS=2" .build/dg/zephyr/.config
```
Expected: both CONFIG lines present; `zmk.uf2` produced.

- [ ] **Step 6: Commit (module repo) and push**

```bash
cd zmk-keyboard-delta-omega && git add -A && git commit -m "feat: add delta_omega_dongle central shield (keyless, mock kscan)" && git push origin main && cd ..
```

---

## Phase 3 — Prospector module, build system, CI matrix

### Task 3.1: Add the Prospector module to west

**Files:**
- Modify: `config/west.yml`

- [ ] **Step 1: Add the carrefinho remote + module** (mirror totem exactly):

```yaml
  remotes:
    - name: zmkfirmware
      url-base: https://github.com/zmkfirmware
    - name: caksoylar
      url-base: https://github.com/caksoylar
    - name: carrefinho
      url-base: https://github.com/carrefinho
  projects:
    # …existing zmk, zmk-rgbled-widget, zmk-keyboard-delta-omega…
    - name: prospector-zmk-module
      remote: carrefinho
      revision: feat/new-status-screens
```

- [ ] **Step 2: Fetch the module**

```bash
cd /home/draxel/Projects/delta-omega
nix develop -c west update prospector-zmk-module
ls prospector-zmk-module/boards/shields/prospector_adapter
```
Expected: the `prospector_adapter` shield dir exists.

- [ ] **Step 3: Build the Prospector dongle**

```bash
nix develop -c west build -p -s zmk/app -d .build/pro -b xiao_ble//zmk -- \
  -DSHIELD='delta_omega_dongle prospector_adapter' -DZMK_CONFIG=config -DSNIPPET=studio-rpc-usb-uart
ls .build/pro/zephyr/zmk.uf2
```
Expected: builds; `zmk.uf2` produced.

- [ ] **Step 4: Commit**

```bash
git add config/west.yml
git commit -m "feat: add prospector-zmk-module (feat/new-status-screens)"
```

### Task 3.2: Rewrite the `justfile` to build all three modes into subdirectories

**Files:**
- Modify: `justfile`

- [ ] **Step 1: Replace the `build` recipe and add per-mode recipes** (separate `.build`
  dirs; `-p always` to avoid stale caches; explicit shields; single keymap):

```just
config  := root / "config"

# Build ALL modes into build/<mode>/ subdirectories
build: build-standalone build-dongle build-prospector
    install -m 644 {{bdir}}/reset/zephyr/zmk.uf2 {{out}}/settings-reset.uf2
    @echo "" ; @echo "All modes built under {{out}}/:" ; @ls -R {{out}}

# Standalone (left half is central, no dongle)
build-standalone: _b-left-central _b-right _b-reset
    mkdir -p {{out}}/standalone
    install -m 644 {{bdir}}/left-central/zephyr/zmk.uf2 {{out}}/standalone/delta-omega-left.uf2
    install -m 644 {{bdir}}/right/zephyr/zmk.uf2         {{out}}/standalone/delta-omega-right.uf2

# Screenless XIAO dongle (both halves peripheral)
build-dongle: _b-dongle _b-left _b-right _b-reset
    mkdir -p {{out}}/dongle
    install -m 644 {{bdir}}/dongle/zephyr/zmk.uf2 {{out}}/dongle/delta-omega-dongle.uf2
    install -m 644 {{bdir}}/left/zephyr/zmk.uf2    {{out}}/dongle/delta-omega-left.uf2
    install -m 644 {{bdir}}/right/zephyr/zmk.uf2   {{out}}/dongle/delta-omega-right.uf2

# Prospector dongle (LCD)
build-prospector: _b-prospector _b-left _b-right _b-reset
    mkdir -p {{out}}/prospector
    install -m 644 {{bdir}}/prospector/zephyr/zmk.uf2 {{out}}/prospector/delta-omega-prospector.uf2
    install -m 644 {{bdir}}/left/zephyr/zmk.uf2         {{out}}/prospector/delta-omega-left.uf2
    install -m 644 {{bdir}}/right/zephyr/zmk.uf2        {{out}}/prospector/delta-omega-right.uf2

_b-left-central:
    nix develop -c west build -p always -s {{zmk_app}} -d {{bdir}}/left-central -b xiao_ble//zmk -- \
        -DSHIELD=delta_omega_left_central -DZMK_CONFIG={{config}}
_b-left:
    nix develop -c west build -p always -s {{zmk_app}} -d {{bdir}}/left -b xiao_ble//zmk -- \
        -DSHIELD=delta_omega_left -DZMK_CONFIG={{config}}
_b-right:
    nix develop -c west build -p always -s {{zmk_app}} -d {{bdir}}/right -b xiao_ble//zmk -- \
        -DSHIELD=delta_omega_right -DZMK_CONFIG={{config}}
_b-dongle:
    nix develop -c west build -p always -s {{zmk_app}} -d {{bdir}}/dongle -b xiao_ble//zmk -- \
        -DSHIELD=delta_omega_dongle -DZMK_CONFIG={{config}} -DSNIPPET=studio-rpc-usb-uart
_b-prospector:
    nix develop -c west build -p always -s {{zmk_app}} -d {{bdir}}/prospector -b xiao_ble//zmk -- \
        -DSHIELD='delta_omega_dongle prospector_adapter' -DZMK_CONFIG={{config}} -DSNIPPET=studio-rpc-usb-uart
_b-reset:
    nix develop -c west build -p always -s {{zmk_app}} -d {{bdir}}/reset -b xiao_ble//zmk -- \
        -DSHIELD=settings_reset -DZMK_CONFIG={{config}}
```
(Keep the existing `flash`, `bootloader-*`, `gen-svg`, `serial`, SWD, and `clean` recipes.)

- [ ] **Step 2: Run the full build**

```bash
cd /home/draxel/Projects/delta-omega
just build 2>&1 | tail -20
```
Expected: `build/standalone/`, `build/dongle/`, `build/prospector/` populated + `build/settings-reset.uf2`.

- [ ] **Step 3: Assert the tree**

```bash
ls -R build | grep -E "standalone|dongle|prospector|settings-reset"
```
Expected: all three dirs with their UF2s and the reset file.

- [ ] **Step 4: Commit**

```bash
git add justfile
git commit -m "feat(just): build standalone/dongle/prospector into build/ subdirs"
```

### Task 3.3: Rewrite `build.yaml` for the new matrix

**Files:**
- Modify: `build.yaml`

- [ ] **Step 1: Replace `build.yaml`** with the per-role matrix (one keymap; descriptive
  artifact names; peripheral halves shared across dongle modes):

```yaml
---
include:
  # Standalone (left = central)
  - board: xiao_ble//zmk
    shield: delta_omega_left_central
    snippet: studio-rpc-usb-uart zmk-usb-logging
    artifact-name: delta-omega-standalone-left
  - board: xiao_ble//zmk
    shield: delta_omega_right
    artifact-name: delta-omega-right
  # Peripheral left (for dongle modes)
  - board: xiao_ble//zmk
    shield: delta_omega_left
    artifact-name: delta-omega-left-peripheral
  # Screenless dongle
  - board: xiao_ble//zmk
    shield: delta_omega_dongle
    snippet: studio-rpc-usb-uart zmk-usb-logging
    artifact-name: delta-omega-dongle
  # Prospector dongle
  - board: xiao_ble//zmk
    shield: delta_omega_dongle prospector_adapter
    snippet: studio-rpc-usb-uart
    artifact-name: delta-omega-prospector
  # Settings reset
  - board: xiao_ble//zmk
    shield: settings_reset
    artifact-name: delta-omega-settings-reset
```

- [ ] **Step 2: Push and verify CI builds every artifact**

```bash
cd /home/draxel/Projects/delta-omega
git add build.yaml
git commit -m "ci: build standalone + screenless dongle + prospector + peripherals"
git push
gh run watch "$(gh run list --limit 1 --json databaseId -q '.[0].databaseId')" || gh run list --limit 1
```
Expected: 6 artifacts produced, all jobs green.

### Task 3.4: Update README with the three modes & flashing

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the three modes**, the QWERTY toggle (Util top-right; reverts on
  reboot), the `just build` subdirectory outputs, and the pairing order for dongle mode
  (flash dongle, reset both halves, pair **left then right** so the Prospector battery
  widgets order correctly).

- [ ] **Step 2: Regenerate SVGs if any keymap display-names changed and commit**

```bash
cd /home/draxel/Projects/delta-omega
python3 tools/gen_svg_layers.py
git add README.md assets/svg/layers/
git commit -m "docs: document dongle/prospector modes and QWERTY toggle"
```

---

## Self-review notes

- **Spec coverage:** QWERTY runtime toggle (Tasks 1.1–1.3), dongle shield (2.3), screenless vs
  Prospector (3.1–3.3 via shield ± adapter), left-as-peripheral (2.2 dedicated shields — chosen
  over the cmake-args approach after seeing totem uses dedicated shields), `just build` subdirs
  (3.2), CI matrix (3.3), board-variant CI fix (Phase 0), gen_svg (1.2), README (3.4). All covered.
- **Design note:** Component C in the spec described a `dongle_peripheral.conf`/cmake-args
  override; this plan instead uses **dedicated per-role shields** (totem's proven structure),
  which is cleaner. Update the spec's Component C accordingly when implementing.
- **Persistence caveat** (QWERTY reverts to Gallium on reboot) is intentional and documented.
- **Open item:** exact board-variant root cause is confirmed empirically in Task 0.1 before the
  fix in 0.2/0.3 — the diagnostic is concrete (reproduce + diff vs totem), not hand-waved.
```
