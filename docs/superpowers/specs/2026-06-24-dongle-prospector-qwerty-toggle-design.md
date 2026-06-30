# Delta Omega — Optional Dongle, Prospector, and Runtime QWERTY Toggle

**Date:** 2026-06-24
**Status:** Approved design, pending implementation plan

## Goal

Add two capabilities to the Delta Omega ZMK config without losing the current
standalone behavior:

1. **Optional dongle central** — run the keyboard with a third XIAO controller as
   the BLE central (both halves become peripherals), in two flavors:
   - **Screenless dongle** — a bare Seeed XIAO nRF52840.
   - **Prospector dongle** — XIAO + Waveshare 1.69" round LCD via the
     [`carrefinho/prospector-zmk-module`](https://github.com/carrefinho/prospector-zmk-module).
2. **Runtime QWERTY toggle** — switch the base alphas between Gallium and QWERTY
   from a key on the Util layer, replacing the separate compile-time QWERTY firmware.

All three central modes (standalone / screenless dongle / Prospector) are kept and
selectable. Building targets ZMK `main` (Zephyr 4.1).

## Background / current state

- Split keyboard, two Seeed XIAO nRF52840 halves. **Left half is hard-wired central**
  (`ZMK_SPLIT_ROLE_CENTRAL default y` in the shield's `Kconfig.defconfig`); right is
  peripheral.
- Two separate keymaps today: `config/delta_omega.keymap` (Gallium) and
  `config/delta_omega_qwerty.keymap` (QWERTY). A diff shows they are **identical
  except the 3 base alpha rows** (letters + home-row mods); every other layer, combo,
  thumb, and the mouse keys are the same.
- Shield module lives in a separate repo `zmk-keyboard-delta-omega` (referenced from
  `config/west.yml`).
- **CI is currently failing for all builds** with the Zephyr-4.1 board-variant error
  (`CONFIG_ZMK_BOARD_COMPAT` / "the selected board is not set up for ZMK and there is
  a ZMK variant available"). Local builds use an older cached ZMK and still pass.

Key ZMK fact that shapes the design: **only the central runs the keymap.** Peripheral
firmware just scans the matrix and reports key positions, so it is *keymap-independent*
and identical regardless of Gallium/QWERTY. The only half that changes between modes is
the left one (central in standalone, peripheral with a dongle).

## Component A — Runtime QWERTY toggle

### Layer model

Renumber layers so QWERTY sits just above the Gallium base and below all functional
layers (correct precedence):

```
0 BASE    (Gallium)            ← default layer
1 QWERTY  (alternate base)     ← qwerty alphas + qwerty HRM; thumbs & rest = &trans
2 NAV   3 NUM   4 FUN   5 UTIL   6 GAME
```

- Only the `#define` block changes the numbers; all bindings reference layers by name
  (`&lt_th NAV …`, `&tog GAME`, etc.), so they update automatically. Audit for any
  literal layer numbers.
- **QWERTY layer contents:** redefine the 30 alpha positions (0–29) with the QWERTY
  letters and QWERTY home-row mods lifted verbatim from the current
  `delta_omega_qwerty.keymap` base layer. Set the 4 thumb positions (30–33) to `&trans`
  so they inherit the shared thumb behaviors from the Gallium base.

### Toggle key

- Add `&tog QWERTY` on the **Util layer, top-right corner (position 9)** — currently
  `&trans`. One key toggles both directions: while QWERTY is on, holding the Util thumb
  still works (thumbs are `&trans` → Gallium `lt_th UTIL`), so the same key turns it off.

### Precedence / correctness rationale

- QWERTY on → layers 0 and 1 active; QWERTY alphas override Gallium, everything else
  falls through to Gallium.
- Holding NAV/NUM/FUN/UTIL/GAME (layers 2–6) overrides QWERTY (higher number wins), so
  those layers behave identically in either base.
- Combos use `layers = <BASE>` (layer 0, always active) → continue to fire in both bases.

### Persistence (known limitation, accepted)

ZMK holds toggled-layer state in RAM and resets to the default (Gallium) on reboot /
power-off. This is accepted: instant runtime switching, reverts to Gallium after a power
cycle. No persistence work in scope.

### Removal of the separate QWERTY firmware

- Delete `config/delta_omega_qwerty.keymap` after lifting its base into the QWERTY layer.
- Remove all QWERTY-specific build entries (`build.yaml`) and the `just build qwerty`
  path; there is now a single keymap (`delta_omega.keymap`).

### SVG generator

`tools/gen_svg_layers.py` updated for 7 layers:
- `LAYER_NAMES` → `["base","qwerty","nav","num","fun","util","game"]`
- `LAYER_DISPLAY` → matching display names
- `HELD_THUMBS` → remap to the new layer indices (nav=2, num=3, fun=4, util=5)
- `len(layers) != 6` check → 7; emit `qwerty.svg`.

## Component B — Dongle central shield

New shield `delta_omega_dongle` in the `zmk-keyboard-delta-omega` repo, under
`boards/shields/delta_omega/`, **modeled on totem's `totem_dongle` shield**
(`/home/draxel/Projects/totem/config/boards/shields/totem/`):

- `delta_omega_dongle.overlay` — `chosen` central, reuses the existing
  `default_transform` (matrix-transform) and `physical_layout0` from the shared `.dtsi`
  so the central can interpret the halves' key events and drive ZMK Studio. **No real
  kscan** (the dongle has no keys); use a no-op/mock kscan or omit per ZMK dongle
  convention — resolve the exact mechanism during implementation.
- `Kconfig.shield` — `SHIELD_DELTA_OMEGA_DONGLE`.
- `Kconfig.defconfig` — keyboard name "Delta Omega Dongle", `ZMK_SPLIT_ROLE_CENTRAL=y`,
  `ZMK_SPLIT_BLE_CENTRAL_PERIPHERALS=2` (talks to both halves), `ZMK_SPLIT=y`, central
  battery proxy.
- Shared `.conf` (`config/delta_omega.conf`) already provides pointing, studio, RGB,
  power, debounce — applies to the dongle too.

## Component C — Left half: dedicated per-role shields

Follow totem's shield structure (cleaner than a cmake-args/conf role override): split the
left half into two shields.

- `delta_omega_left` — **peripheral** (no central role in defconfig; used in dongle modes).
- `delta_omega_left_central` — **central**, `ZMK_SPLIT_BLE_CENTRAL_PERIPHERALS=1`, central
  battery fetching/proxy (used in standalone mode).
- `delta_omega_right` — peripheral, unchanged across all modes.

Standalone builds `delta_omega_left_central` + `delta_omega_right`; dongle/Prospector builds
`delta_omega_dongle` + `delta_omega_left` (peripheral) + `delta_omega_right`. Move the
central-battery proxy settings out of `delta_omega_left.conf` into
`delta_omega_left_central.conf` so the peripheral build is clean.

**Reference:** totem ships `totem_left` (peripheral) and `totem_left_central` (central) as
separate shields for exactly this; we mirror it and keep standalone in addition.

## Component D — Prospector module integration

- `config/west.yml`: add remote `carrefinho` (`https://github.com/carrefinho`) and project
  `prospector-zmk-module`, **revision `feat/new-status-screens`** — verified identical to the
  user's working **totem** config.
- Prospector build = dongle shield **plus** `prospector_adapter` (from the module) on
  board `xiao_ble//zmk`.
- Optional later: `display-name` on keymap layers already aids the Prospector layer
  roller (we are adding display-names via the layer work).

## Component E — Build outputs, justfile, CI

### Firmware set (single keymap each)

| Mode | Central | Peripherals |
|------|---------|-------------|
| Standalone | `delta_omega_left` (central) | `delta_omega_right` |
| Screenless dongle | `delta_omega_dongle` | `delta_omega_left` (peripheral), `delta_omega_right` |
| Prospector | `delta_omega_dongle prospector_adapter` | `delta_omega_left` (peripheral), `delta_omega_right` |
| Reset | `settings_reset` | — |

### `just build` → all three modes in subdirectories

```
build/
├── standalone/   delta-omega-left.uf2 (central), delta-omega-right.uf2
├── dongle/       delta-omega-dongle.uf2, delta-omega-left.uf2 (periph), delta-omega-right.uf2
├── prospector/   delta-omega-prospector.uf2, delta-omega-left.uf2 (periph), delta-omega-right.uf2
└── settings-reset.uf2
```

- Each directory is self-contained for flashing that mode (the peripheral half UF2s are
  copied into each dongle/prospector dir even though they are the same binary).
- Use a **separate `.build/<mode>-<target>` cache dir per build** and always pass an
  explicit keymap/shield/conf, to avoid the stale-CMake-cache clobbering we previously hit.
- Add `just build-standalone`, `just build-dongle`, `just build-prospector` for single-mode
  builds.

### CI (`build.yaml`)

Builds the same set with descriptive `artifact-name`s (e.g. `delta-omega-standalone-left`,
`delta-omega-left-peripheral`, `delta-omega-right`, `delta-omega-dongle`,
`delta-omega-prospector`, `delta-omega-settings-reset`). Use `cmake-args` +
`${GITHUB_WORKSPACE}` paths for the peripheral `EXTRA_CONF_FILE`, matching existing convention.

## Component F — Prerequisite: fix Zephyr-4.1 board-variant CI failure

CI runs against ZMK `main` (Zephyr 4.1) and currently fails for all builds. The user's
**totem** config builds on the same `xiao_ble//zmk` board, ZMK `main`, and prospector
`feat/new-status-screens` — so the board reference is fine and the failure is specific to the
`zmk-keyboard-delta-omega` **shield module**. Plan:

1. Diff the delta-omega shield module against totem's working shield structure
   (`config/boards/shields/totem/`) — look for the HWMv2 / board-variant differences
   (board overlay naming `boards/xiao_ble_zmk.overlay`, `Kconfig.*`, defconfig flags) per
   [the ZMK 4.1 blog](https://zmk.dev/blog/2025/12/09/zephyr-4-1).
2. Apply the migration fix in the shield module; reproduce locally against ZMK `main`.
3. Verify a green CI build before layering the dongle/Prospector matrix on top.

This is a prerequisite — none of the new builds work in CI until it's fixed.

## Out of scope / non-goals

- Persisting the QWERTY toggle across reboots.
- Building the dongle/Prospector centrals with a *separate* QWERTY keymap (superseded by
  the runtime toggle).
- Hardware/matrix debugging of the assembled boards (tracked separately).

## Risks / open items

- Exact dongle kscan mechanism (mock vs omit) under Zephyr 4.1 — resolve at implementation.
- Whether `delta_omega_left.conf` central-battery settings must move to be peripheral-clean.
- Prospector `feat/new-status-screens` is WIP upstream; pin a known-good revision if `main`
  of that branch breaks.
- The board-variant fix (Component F) may itself require changes in the separate shield repo.

## Verification

- `just build` produces the three populated subdirectories + `settings-reset.uf2`.
- A green CI run producing all expected artifacts.
- Manual: flash standalone → type Gallium; toggle from Util top-right → type QWERTY;
  hold NAV/NUM/etc. while QWERTY is on → functional layers still correct; reboot → reverts
  to Gallium. Flash screenless dongle + both peripherals → both halves work through the
  dongle. Flash Prospector → LCD shows status.
