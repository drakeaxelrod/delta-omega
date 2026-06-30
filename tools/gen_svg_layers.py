#!/usr/bin/env python3
"""Generate SVG layer visualizations from the ZMK keymap.

Usage: python tools/gen_svg_layers.py

Reads config/delta_omega.keymap, parses layer bindings,
and generates one SVG per layer into assets/svg/layers/.
"""

import re
from pathlib import Path
from html import escape

ROOT = Path(__file__).resolve().parent.parent
KEYMAP = ROOT / "config" / "delta_omega.keymap"
BLANK_SVG = ROOT / "assets" / "layouts" / "blank.svg"
SVG_DIR = ROOT / "assets" / "svg" / "layers"

# ── Key position transforms (from blank.svg) ──────────────────────────
# (x, y, rotation) — matches the 34-key delta-omega layout

KEY_POSITIONS = [
    # Top row (0-9)
    (99, 135, -22), (168, 77, -12), (242, 42, -4), (312, 66, 0), (372, 81, 0),
    (509, 81, 0), (569, 66, 0), (639, 42, 4), (714, 77, 12), (782, 135, 22),
    # Home row (10-19)
    (120, 190, -22), (179, 136, -12), (246, 102, -4), (312, 126, 0), (372, 141, 0),
    (509, 141, 0), (569, 126, 0), (635, 102, 4), (702, 136, 12), (761, 190, 22),
    # Bottom row (20-29)
    (141, 246, -22), (191, 194, -12), (250, 162, -4), (312, 186, 0), (372, 201, 0),
    (509, 201, 0), (569, 186, 0), (631, 162, 4), (690, 194, 12), (740, 246, 22),
    # Thumbs (30-33)
    (304, 261, 0), (371, 262, 2),
    (510, 262, -2), (577, 261, 0),
]

LAYER_NAMES = ["base", "qwerty", "nav", "num", "fun", "util", "game"]
LAYER_DISPLAY = ["Base (Gallium)", "QWERTY", "Nav", "Num", "Fun", "Util + Mouse", "Game"]

# Which thumb position activates each layer (for "held" highlighting)
HELD_THUMBS = {
    2: 31,   # NAV  → hold Space thumb
    3: 32,   # NUM  → hold Enter thumb
    4: 33,   # FUN  → hold Backspace thumb
    5: 30,   # UTIL → hold Escape thumb
    # GAME (6) is toggled, no held thumb
}

# ── Key code → display label mapping ──────────────────────────────────

KEY_LABELS = {
    # Letters (identity)
    **{c: c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"},
    # Numbers
    "N0": "0", "N1": "1", "N2": "2", "N3": "3", "N4": "4",
    "N5": "5", "N6": "6", "N7": "7", "N8": "8", "N9": "9",
    # Navigation
    "LEFT": "\u2190", "RIGHT": "\u2192", "UP": "\u2191", "DOWN": "\u2193",
    "LEFT_ARROW": "\u2190", "RIGHT_ARROW": "\u2192", "UP_ARROW": "\u2191", "DOWN_ARROW": "\u2193",
    "HOME": "Home", "END": "End", "PG_UP": "PgUp", "PG_DN": "PgDn",
    "INS": "Ins",
    # Modifiers
    "LSHFT": "LShf", "RSHFT": "RShf", "LEFT_SHIFT": "LShf",
    "LCTRL": "LCtl", "RCTRL": "RCtl",
    "LALT": "LAlt", "RALT": "RAlt",
    "LGUI": "LGui", "RGUI": "RGui", "LEFT_GUI": "LGui",
    # Special keys
    "SPACE": "Spc", "BSPC": "Bksp", "BACKSPACE": "Bksp",
    "DEL": "Del", "TAB": "Tab",
    "RET": "Ent", "ENTER": "Ent", "ESC": "Esc", "ESCAPE": "Esc",
    "PSCRN": "PrtSc", "SLCK": "ScrLk", "PAUSE_BREAK": "Pause",
    # Symbols
    "COMMA": ",", "DOT": ".", "SEMI": ";", "SQT": "'", "DQT": "\"",
    "EXCL": "!", "AT": "@", "HASH": "#", "DLLR": "$", "PRCNT": "%",
    "CARET": "^", "AMPS": "&", "STAR": "*", "LPAR": "(", "RPAR": ")",
    "MINUS": "-", "UNDER": "_", "EQUAL": "=", "PLUS": "+",
    "LBKT": "[", "RBKT": "]", "LBRC": "{", "RBRC": "}",
    "BSLH": "\\", "FSLH": "/", "PIPE": "|", "TILDE": "~", "GRAVE": "`",
    "LT": "<", "GT": ">", "QMARK": "?", "COLON": ":",
    # F-keys
    **{f"F{i}": f"F{i}" for i in range(1, 13)},
    # Consumer / media
    "C_VOL_UP": "Vol+", "C_VOL_DN": "Vol\u2212", "C_MUTE": "Mute",
    "C_BRI_UP": "Bri+", "C_BRI_DN": "Bri\u2212",
    "C_PP": "Play", "C_PREV": "Prev", "C_NEXT": "Next",
    "C_PLAY_PAUSE": "Play",
    # Edit
    "K_UNDO": "Undo", "K_CUT": "Cut", "K_COPY": "Copy",
    "K_PASTE": "Paste", "K_REDO": "Redo",
    "K_BACK": "Back", "K_FORWARD": "Fwd", "K_APP": "App",
    "K_MUTE": "Mute",
    # Keypad
    "KP_PLUS": "+", "KP_MULTIPLY": "*",
}

MOD_LABELS = {
    "LGUI": "Gui", "RGUI": "Gui",
    "LALT": "Alt", "RALT": "Alt",
    "LCTRL": "Ctrl", "RCTRL": "Ctrl",
    "LSHFT": "Shf", "RSHFT": "Shf",
}

LAYER_LABELS = {
    "BASE": "Base", "QWERTY": "QWERTY", "NAV": "Nav", "NUM": "Num",
    "FUN": "Fun", "UTIL": "Util", "GAME": "Game",
    "0": "Base", "1": "QWERTY", "2": "Nav",
    "3": "Num", "4": "Fun", "5": "Util", "6": "Game",
}


def key_label(code):
    """Map a ZMK key code to a display label."""
    if code in KEY_LABELS:
        return KEY_LABELS[code]
    # Handle modifier combos like LC(X) → Ctrl+X
    m = re.match(r"^L([CSAG])\((.+)\)$", code)
    if m:
        mod_map = {"C": "Ctrl", "S": "Shf", "A": "Alt", "G": "Gui"}
        inner = key_label(m.group(2))
        return f"{mod_map[m.group(1)]}+{inner}"
    return code


def mod_label(mod):
    """Map a ZMK modifier to a hold display label."""
    if mod in MOD_LABELS:
        return MOD_LABELS[mod]
    # Hyper: LS(LC(LA(LGUI))) or RS(RC(RA(RGUI)))
    if "LC(LA(LGUI))" in mod or "RC(RA(RGUI))" in mod:
        return "Hyper"
    return mod


def layer_label(layer):
    """Map a layer name/number to display label."""
    return LAYER_LABELS.get(layer, layer)


# ── Binding parser ────────────────────────────────────────────────────

def tokenize_bindings(bindings_str):
    """Split a ZMK bindings string into individual binding strings."""
    bindings = []
    i = 0
    s = bindings_str.strip()
    while i < len(s):
        if s[i] == "&":
            j = i + 1
            depth = 0
            while j < len(s):
                if s[j] == "(":
                    depth += 1
                elif s[j] == ")":
                    depth -= 1
                elif s[j] == "&" and depth == 0:
                    break
                j += 1
            bindings.append(s[i + 1 : j].strip())
            i = j
        else:
            i += 1
    return bindings


def parse_binding(binding_str):
    """Parse a binding into (tap_label, hold_label, is_trans)."""
    tokens = []
    current = ""
    depth = 0
    for ch in binding_str:
        if ch in " \t\n" and depth == 0:
            if current:
                tokens.append(current)
                current = ""
        else:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            current += ch
    if current:
        tokens.append(current)

    if not tokens:
        return ("", None, False)

    behavior = tokens[0]
    args = tokens[1:]

    if behavior == "trans":
        return ("\u25bd", None, True)

    if behavior == "none":
        return ("", None, False)

    if behavior == "kp":
        return (key_label(args[0]) if args else "?", None, False)

    if behavior in ("hml", "hmr"):
        tap = key_label(args[1]) if len(args) > 1 else "?"
        hold = mod_label(args[0]) if args else "?"
        return (tap, hold, False)

    if behavior == "lt_th":
        tap = key_label(args[1]) if len(args) > 1 else "?"
        hold = layer_label(args[0]) if args else "?"
        return (tap, hold, False)

    if behavior == "mt":
        tap = key_label(args[1]) if len(args) > 1 else "?"
        hold = mod_label(args[0]) if args else "?"
        return (tap, hold, False)

    if behavior == "caps_word":
        return ("CapsWd", None, False)

    if behavior == "bt":
        if args and args[0] == "BT_SEL":
            n = int(args[1]) + 1 if len(args) > 1 else "?"
            return (f"BT{n}", None, False)
        if args and args[0] == "BT_CLR":
            return ("BTClr", None, False)
        if args and args[0] == "BT_CLR_ALL":
            return ("ClrAll", None, False)
        if args and args[0] == "BT_PRV":
            return ("BTPrv", None, False)
        if args and args[0] == "BT_NXT":
            return ("BTNxt", None, False)
        return ("BT", None, False)

    if behavior == "out":
        if args and args[0] == "OUT_TOG":
            return ("USB/BT", None, False)
        return ("Out", None, False)

    if behavior == "mmv":
        mmv_map = {
            "MOVE_LEFT": "\u2190", "MOVE_RIGHT": "\u2192",
            "MOVE_UP": "\u2191", "MOVE_DOWN": "\u2193",
        }
        label = mmv_map.get(args[0], args[0]) if args else "Mouse"
        return (f"Ms{label}", None, False)

    if behavior == "msc":
        msc_map = {
            "SCRL_UP": "\u2191", "SCRL_DOWN": "\u2193",
            "SCRL_LEFT": "\u2190", "SCRL_RIGHT": "\u2192",
        }
        label = msc_map.get(args[0], args[0]) if args else "Scrl"
        return (f"Sc{label}", None, False)

    if behavior == "mkp":
        mkp_map = {
            "LCLK": "LClk", "RCLK": "RClk", "MCLK": "MClk",
            "MB4": "MB4", "MB5": "MB5",
        }
        return (mkp_map.get(args[0], args[0]) if args else "Click", None, False)

    if behavior == "tog":
        return (layer_label(args[0]) if args else "Tog", None, False)

    if behavior == "studio_unlock":
        return ("Studio", None, False)

    if behavior == "soft_off":
        return ("Off", None, False)

    # Fallback
    return (behavior, None, False)


# ── Keymap parser ─────────────────────────────────────────────────────

def parse_keymap(keymap_path):
    """Parse the ZMK keymap file and return a list of layers."""
    text = keymap_path.read_text()

    layer_pattern = re.compile(
        r"(\w+_layer)\s*\{[^}]*?bindings\s*=\s*<(.*?)>",
        re.DOTALL,
    )

    layers = []
    for match in layer_pattern.finditer(text):
        bindings_str = match.group(2)
        bindings = tokenize_bindings(bindings_str)
        layers.append(bindings)

    return layers


def parse_combos(keymap_path):
    """Parse combo definitions from the keymap."""
    text = keymap_path.read_text()

    # Match combo blocks with properties in any order
    combo_block_pattern = re.compile(
        r"(combo_\w+)\s*\{([^}]+)\}",
        re.DOTALL,
    )
    pos_pattern = re.compile(r"key-positions\s*=\s*<([^>]+)>")
    bind_pattern = re.compile(r"bindings\s*=\s*<([^>]+)>")

    combos = []
    for match in combo_block_pattern.finditer(text):
        name = match.group(1)
        body = match.group(2)
        pos_match = pos_pattern.search(body)
        bind_match = bind_pattern.search(body)
        if not pos_match or not bind_match:
            continue
        positions = [int(p) for p in pos_match.group(1).split()]
        binding_str = bind_match.group(1).strip()
        if binding_str.startswith("&"):
            binding_str = binding_str[1:]
        tap, _, _ = parse_binding(binding_str)
        combos.append((name, positions, tap))

    return combos


# ── SVG generation ────────────────────────────────────────────────────

def get_svg_header_footer():
    """Extract the SVG header (defs+style) and footer from blank.svg."""
    text = BLANK_SVG.read_text()
    marker = '<g transform="translate(30, 56)">'
    idx = text.index(marker)
    header = text[: idx + len(marker)] + "\n"
    footer = "  </g>\n</svg>"
    return header, footer


def render_key(pos_idx, tap, hold=None, is_trans=False, is_held=False):
    """Render a single key as an SVG <g> element."""
    x, y, rot = KEY_POSITIONS[pos_idx]

    transform = f"translate({x}, {y})"
    if rot:
        transform += f" rotate({float(rot)})"

    rect_class = "key"
    if is_held:
        rect_class = "key held"

    tap_esc = escape(tap)

    tap_class = "key tap"
    if is_trans:
        tap_class = "key tap trans"

    lines = []
    lines.append(f'    <g transform="{transform}" class="key keypos-{pos_idx}">')
    lines.append(f'      <rect rx="6" ry="6" x="-28" y="-26" width="55" height="52" class="{rect_class}" />')

    if hold:
        lines.append(f'      <text x="0" y="-6" class="{tap_class}">{tap_esc}</text>')
        lines.append(f'      <text x="0" y="0" class="key hold small">{escape(hold)}</text>')
    else:
        lines.append(f'      <text x="0" y="0" class="{tap_class}">{tap_esc}</text>')

    lines.append("    </g>")
    return "\n".join(lines)


def generate_layer_svg(header, footer, layer_idx, bindings):
    """Generate a complete SVG for one layer."""
    layer_display = LAYER_DISPLAY[layer_idx]
    held_pos = HELD_THUMBS.get(layer_idx)

    label = f'    <text x="5" y="-20" class="label" font-size="16">{escape(layer_display)}</text>'

    keys = []
    for pos_idx, binding_str in enumerate(bindings):
        tap, hold, is_trans = parse_binding(binding_str)

        is_held = pos_idx == held_pos
        if is_held:
            tap = layer_label(str(layer_idx))
            hold = None
            is_trans = False

        keys.append(render_key(pos_idx, tap, hold, is_trans, is_held))

    return header + label + "\n" + "\n".join(keys) + "\n" + footer


# ── Combo SVG generation ─────────────────────────────────────────────

COMBO_H = 20
COMBO_CHAR_W = 7.2
COMBO_PAD = 14
COMBO_MIN_W = 28


def combo_box_width(label):
    """Calculate combo box width based on label length."""
    return max(COMBO_MIN_W, len(label) * COMBO_CHAR_W + COMBO_PAD)


def combo_midpoint(positions):
    """Calculate the midpoint between key positions (ignoring rotation)."""
    xs = [KEY_POSITIONS[p][0] for p in positions]
    ys = [KEY_POSITIONS[p][1] for p in positions]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def resolve_overlaps(combo_data, iterations=20, pad=4):
    """Nudge overlapping combo boxes apart."""
    for _ in range(iterations):
        moved = False
        for i in range(len(combo_data)):
            for j in range(i + 1, len(combo_data)):
                ax, ay, aw, ah = combo_data[i]
                bx, by, bw, bh = combo_data[j]
                ox = (aw / 2 + bw / 2 + pad) - abs(ax - bx)
                oy = (ah / 2 + bh / 2 + pad) - abs(ay - by)
                if ox > 0 and oy > 0:
                    if ox < oy:
                        shift = ox / 2
                        if ax < bx:
                            combo_data[i][0] -= shift
                            combo_data[j][0] += shift
                        else:
                            combo_data[i][0] += shift
                            combo_data[j][0] -= shift
                    else:
                        shift = oy / 2
                        if ay < by:
                            combo_data[i][1] -= shift
                            combo_data[j][1] += shift
                        else:
                            combo_data[i][1] += shift
                            combo_data[j][1] -= shift
                    moved = True
        if not moved:
            break


def render_combo_lines(positions, cx, cy):
    """Render curved SVG path lines from each key center to the combo box center."""
    lines = []
    kbd_cx, kbd_cy = 440, 160

    for p in positions:
        kx, ky, _ = KEY_POSITIONS[p]
        dx, dy = cx - kx, cy - ky
        length = (dx**2 + dy**2) ** 0.5

        if length < 15:
            lines.append(f'    <path d="M {kx},{ky} L {cx},{cy}" class="combo" />')
            continue

        nx, ny = -dy / length, dx / length

        mid_x, mid_y = (kx + cx) / 2, (ky + cy) / 2
        outx, outy = mid_x - kbd_cx, mid_y - kbd_cy
        if nx * outx + ny * outy < 0:
            nx, ny = -nx, -ny

        bow = min(length * 0.25, 14)
        cpx = mid_x + nx * bow
        cpy = mid_y + ny * bow

        lines.append(
            f'    <path d="M {kx},{ky} Q {cpx:.1f},{cpy:.1f} {cx},{cy}" class="combo" />'
        )
    return "\n".join(lines)


def render_combo_box(cx, cy, label, w):
    """Render a combo box (rect + label) at the given center position."""
    hw, hh = w / 2, COMBO_H / 2
    label_esc = escape(label)
    return (
        f'    <g transform="translate({cx}, {cy})">\n'
        f'      <rect rx="4" ry="4" x="{-hw}" y="{-hh}" '
        f'width="{w}" height="{COMBO_H}" class="combo" />\n'
        f'      <text x="0" y="0" class="combo">{label_esc}</text>\n'
        f'    </g>'
    )


def generate_combos_svg(header, footer, base_bindings, combos):
    """Generate an SVG showing the base layer with combo overlays."""
    label = '    <text x="5" y="-20" class="label" font-size="16">Combos</text>'

    keys = []
    for pos_idx, binding_str in enumerate(base_bindings):
        tap, hold, is_trans = parse_binding(binding_str)
        keys.append(render_key(pos_idx, tap, hold, is_trans, False))

    combo_geom = []
    for name, positions, tap_label in combos:
        cx, cy = combo_midpoint(positions)
        w = combo_box_width(tap_label)
        combo_geom.append([cx, cy, w, COMBO_H])

    resolve_overlaps(combo_geom)

    combo_lines = []
    combo_boxes = []
    for idx, (name, positions, tap_label) in enumerate(combos):
        cx, cy, w, _ = combo_geom[idx]
        combo_lines.append(render_combo_lines(positions, cx, cy))
        combo_boxes.append(render_combo_box(cx, cy, tap_label, w))

    parts = [header, label]
    parts.extend(keys)
    parts.append("    <!-- combo connection lines -->")
    parts.extend(combo_lines)
    parts.append("    <!-- combo boxes -->")
    parts.extend(combo_boxes)
    parts.append(footer)

    return "\n".join(parts)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    layers = parse_keymap(KEYMAP)
    combos = parse_combos(KEYMAP)
    header, footer = get_svg_header_footer()

    if len(layers) != 7:
        print(f"Warning: expected 7 layers, found {len(layers)}")

    SVG_DIR.mkdir(parents=True, exist_ok=True)

    for i, bindings in enumerate(layers):
        name = LAYER_NAMES[i] if i < len(LAYER_NAMES) else f"layer{i}"
        svg = generate_layer_svg(header, footer, i, bindings)
        out_path = SVG_DIR / f"{name}.svg"
        out_path.write_text(svg)
        print(f"  \u2192 {out_path.relative_to(ROOT)}")

    # Generate combos overlay SVG
    if layers and combos:
        svg = generate_combos_svg(header, footer, layers[0], combos)
        out_path = SVG_DIR / "combos.svg"
        out_path.write_text(svg)
        print(f"  \u2192 {out_path.relative_to(ROOT)}")

    print(f"\nGenerated {len(layers)} layer SVGs + combos.")


if __name__ == "__main__":
    main()
