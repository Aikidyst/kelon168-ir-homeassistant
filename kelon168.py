"""
KELON168 IR Protocol Generator — Bedroom AC
Fully reverse-engineered from remote captures.

Usage:
    from kelon168 import build_raw, build_power_raw
    raw = build_raw("cool", temp=22, fan="auto")
    # raw → "raw:8308,4527,554,1712,..."

    # Power ON sequence (turbo frame + state frame):
    turbo_raw = build_raw("cool", turbo=True)   # always turns AC on
    state_raw = build_raw("cool", temp=22, fan="auto")

    # Power OFF (toggle — no absolute off in KELON168):
    power_raw = build_power_raw("cool", temp=22, fan="auto")

Notes:
    - ZER_SPACE in actual remote captures is 554µs (some variation to 625µs).
      Both values are accepted by the AC as logical 0.
    - Power OFF is a toggle — protocol has no absolute power-off command.
    - Power ON uses the TURBO frame which always turns the AC on regardless
      of current state, followed immediately by a normal state frame.
    - The power toggle frame (byte2 bit2=Power, byte6=0x95, byte15=0x01)
      is a toggle command. Turbo (byte5=0x90) is a guaranteed power-on.
"""

# ── Timing constants (µs) ──────────────────────────────────────────────────
HDR_MARK  = 8308
HDR_SPACE = 4527
BIT_MARK  = 554
ONE_SPACE = 1712
ZER_SPACE = 554   # actual remote uses 554 (some captures show 625, both accepted)
GAP       = 8308  # inter-frame gap (low/space)

# ── Mode codes (byte3 lower nibble) ───────────────────────────────────────
MODE_LO = {"cool": 0x2, "heat": 0x0, "dry": 0x3, "fan_only": 0x4}

# ── Fan speed → byte2 ─────────────────────────────────────────────────────
#   For COOL / HEAT:                For FAN_ONLY (AUTO captured as 0x01)
FAN_B2 = {"auto": 0x00, "low": 0x03, "medium": 0x02, "high": 0x01}
FAN_B2_FAN_ONLY = {"auto": 0x01, "low": 0x03, "medium": 0x02, "high": 0x01}

# ── byte7 per mode+fan (captured values) ─────────────────────────────────
BYTE7 = {
    ("cool",     "auto"):   0x05,
    ("cool",     "low"):    0x32,
    ("cool",     "medium"): 0x2E,
    ("cool",     "high"):   0x2E,
    ("heat",     "auto"):   0x25,
    ("heat",     "low"):    0x32,
    ("heat",     "medium"): 0x2E,
    ("heat",     "high"):   0x2E,
    ("dry",      "auto"):   0x28,
    ("fan_only", "auto"):   0x2A,
    ("fan_only", "low"):    0x32,
    ("fan_only", "medium"): 0x2E,
    ("fan_only", "high"):   0x2E,
}

# ── byte15 per mode+fan ───────────────────────────────────────────────────
def _byte15(mode, fan, ifeel=False):
    base = 0x02 if mode in ("cool", "heat") else 0x06
    if mode in ("cool", "heat") and fan != "auto":
        base = 0x11
    if mode == "dry":
        base = 0x06
    if mode == "fan_only":
        base = 0x06
    if ifeel:
        base = 0x0D
    return base


def build_state(mode, temp=22, fan="auto", ifeel_temp=None, turbo=False):
    """
    Build 21-byte KELON168 state array.

    Parameters
    ----------
    mode      : "cool" | "heat" | "dry" | "fan_only"
    temp      : int, 16–27 (°C); ignored for dry/fan_only
    fan       : "auto" | "low" | "medium" | "high"
    ifeel_temp: int | None  — remote sensor temp for I Feel mode
    turbo     : bool         — turbo preset (forces 16°C cool, high fan)
    """
    s = bytearray(21)
    s[0] = 0x83
    s[1] = 0x06
    s[18] = 0x08  # always

    if turbo:
        s[2]  = 0x01            # HIGH fan displayed
        s[3]  = 0x02            # 16°C cool (0 << 4 | 2)
        s[5]  = 0x90            # turbo flag
        s[6]  = 0x8C
        s[7]  = 0x38
        s[15] = 0x04

    elif mode == "dry":
        s[2]  = 0x00            # DRY none level
        s[3]  = (7 << 4) | 0x3 # no temp, mode=DRY
        s[6]  = 0x8C
        s[7]  = 0x28
        s[15] = 0x06

    elif mode == "fan_only":
        fan_b2 = FAN_B2_FAN_ONLY.get(fan, 0x01)
        s[2]  = fan_b2
        s[3]  = (7 << 4) | 0x4 # no temp, mode=FAN
        s[6]  = 0x8C
        s[7]  = BYTE7.get(("fan_only", fan), 0x2A)
        s[15] = 0x06

    else:  # cool or heat
        temp = max(16, min(30, int(temp)))
        s[2]  = FAN_B2.get(fan, 0x00)
        s[3]  = ((temp - 16) << 4) | MODE_LO[mode]
        s[6]  = 0x8C
        s[7]  = BYTE7.get((mode, fan), 0x05)
        s[15] = _byte15(mode, fan)

    # I Feel overlay
    if ifeel_temp is not None and not turbo:
        s[6]  = 0x8D
        s[11] = 0x80
        s[12] = int(ifeel_temp)
        s[15] = 0x0D

    # ── Checksum frame 1+2: XOR(bytes 0-12) XOR 0x85 → byte13 ────────────
    xor = 0x00
    for i in range(13):
        xor ^= s[i]
    s[13] = xor ^ 0x85

    # ── Checksum frame 3: byte20 = byte15 XOR 0x08 ───────────────────────
    s[20] = s[15] ^ 0x08

    return list(s)


def state_to_raw(s):
    """Convert 21-byte state to raw IR pulse string (for remote.send_command)."""
    def bits_of(byte_list):
        bits = []
        for b in byte_list:
            for i in range(8):
                bits.append((b >> i) & 1)
        return bits

    def encode(bits, header=False):
        p = []
        if header:
            p += [HDR_MARK, HDR_SPACE]
        for b in bits:
            p += [BIT_MARK, ONE_SPACE if b else ZER_SPACE]
        p += [BIT_MARK]   # stop mark
        return p

    f1 = encode(bits_of(s[0:6]),  header=True)
    f2 = encode(bits_of(s[6:14]), header=False)
    f3 = encode(bits_of(s[14:21]),header=False)

    pulses = f1 + [GAP] + f2 + [GAP] + f3
    assert len(pulses) == 343, f"Expected 343 pulses, got {len(pulses)}"
    return "raw:" + ",".join(str(v) for v in pulses)


def build_raw(mode, temp=22, fan="auto", ifeel_temp=None, turbo=False):
    """One-shot: build state and return raw pulse string."""
    return state_to_raw(build_state(mode, temp, fan, ifeel_temp, turbo))


def build_power_raw(mode="cool", temp=22, fan="auto"):
    """
    Build the KELON168 power TOGGLE frame.

    This frame toggles AC power — sends current remote state + power bit.
    Use for Power OFF only. For Power ON use turbo frame + state frame.

    Power frame signature (from reverse engineering):
      byte2  = 0x04 | fan_code_power  (auto=0x04, high=0x05, med=0x06, low=0x07)
      byte3  = (temp-16)<<4 | mode_lo  (encodes last known state)
      byte6  = 0x95  (power frame marker)
      byte7  = 0x24  (fixed)
      byte15 = 0x01  (power indicator)
      byte20 = 0x09  (byte15 ^ 0x08)
      byte13 = XOR checksum
    """
    temp = max(16, min(30, int(temp)))
    mlo = MODE_LO.get(mode, 0x2)
    pfan = {"auto": 0x04, "low": 0x07, "medium": 0x06, "high": 0x05}
    b2  = pfan.get(fan, 0x04)
    b3  = ((temp - 16) << 4) | mlo
    b6  = 0x95
    b7  = 0x24
    b15 = 0x01
    b20 = b15 ^ 0x08

    s = bytearray(21)
    s[0]  = 0x83
    s[1]  = 0x06
    s[2]  = b2
    s[3]  = b3
    s[6]  = b6
    s[7]  = b7
    s[15] = b15
    s[18] = 0x08
    s[20] = b20

    xor = 0x00
    for i in range(13):
        xor ^= s[i]
    s[13] = xor ^ 0x85

    return state_to_raw(list(s))


TURBO_RAW = None  # lazy-init below

def build_turbo_raw():
    """
    Return the hardcoded TURBO frame raw string.
    TURBO always turns the AC ON regardless of current state.
    Use this as the first frame of a power-on sequence,
    followed immediately by build_raw() with desired state.
    """
    turbo_state = build_state("cool", turbo=True)
    return state_to_raw(turbo_state)


# ── Self-test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    TESTS = [
        ("COOL 22 AUTO",  {"mode":"cool","temp":22,"fan":"auto"},
         [0x83,0x06,0x00,0x62,0x00,0x00,0x8C,0x05,0x00,0x00,0x00,0x00,0x00,0xEB,0x00,0x02,0x00,0x00,0x08,0x00,0x0A]),
        ("COOL 22 LOW",   {"mode":"cool","temp":22,"fan":"low"},
         [0x83,0x06,0x03,0x62,0x00,0x00,0x8C,0x32,0x00,0x00,0x00,0x00,0x00,0xDF,0x00,0x11,0x00,0x00,0x08,0x00,0x19]),
        ("COOL 22 MED",   {"mode":"cool","temp":22,"fan":"medium"},
         [0x83,0x06,0x02,0x62,0x00,0x00,0x8C,0x2E,0x00,0x00,0x00,0x00,0x00,0xC2,0x00,0x11,0x00,0x00,0x08,0x00,0x19]),
        ("COOL 22 HIGH",  {"mode":"cool","temp":22,"fan":"high"},
         [0x83,0x06,0x01,0x62,0x00,0x00,0x8C,0x2E,0x00,0x00,0x00,0x00,0x00,0xC1,0x00,0x11,0x00,0x00,0x08,0x00,0x19]),
        ("COOL 18 AUTO",  {"mode":"cool","temp":18,"fan":"auto"},
         [0x83,0x06,0x00,0x22,0x00,0x00,0x8C,0x05,0x00,0x00,0x00,0x00,0x00,0xAB,0x00,0x02,0x00,0x00,0x08,0x00,0x0A]),
        ("HEAT 22 AUTO",  {"mode":"heat","temp":22,"fan":"auto"},
         [0x83,0x06,0x00,0x60,0x00,0x00,0x8C,0x25,0x00,0x00,0x00,0x00,0x00,0xC9,0x00,0x02,0x00,0x00,0x08,0x00,0x0A]),
        ("DRY none",      {"mode":"dry"},
         [0x83,0x06,0x00,0x73,0x00,0x00,0x8C,0x28,0x00,0x00,0x00,0x00,0x00,0xD7,0x00,0x06,0x00,0x00,0x08,0x00,0x0E]),
        ("FAN_ONLY AUTO", {"mode":"fan_only","fan":"auto"},
         [0x83,0x06,0x01,0x74,0x00,0x00,0x8C,0x2A,0x00,0x00,0x00,0x00,0x00,0xD3,0x00,0x06,0x00,0x00,0x08,0x00,0x0E]),
        ("TURBO",         {"mode":"cool","turbo":True},
         [0x83,0x06,0x01,0x02,0x00,0x90,0x8C,0x38,0x00,0x00,0x00,0x00,0x00,0x27,0x00,0x04,0x00,0x00,0x08,0x00,0x0C]),
        ("I FEEL 26",     {"mode":"cool","temp":22,"fan":"auto","ifeel_temp":26},
         [0x83,0x06,0x00,0x62,0x00,0x00,0x8D,0x05,0x00,0x00,0x00,0x80,0x1A,0x70,0x00,0x0D,0x00,0x00,0x08,0x00,0x05]),
    ]

    all_ok = True
    for label, kwargs, expected in TESTS:
        got = build_state(**kwargs)
        ok = (got == expected)
        if not ok:
            diffs = [(i, expected[i], got[i]) for i in range(21) if expected[i] != got[i]]
            print(f"  FAIL {label}: {[(i, f'exp=0x{e:02X}', f'got=0x{g:02X}') for i,e,g in diffs]}")
            all_ok = False
        else:
            raw = state_to_raw(got)
            print(f"  OK   {label}  ({len(raw.split(','))} pulses)")

    if all_ok:
        print("\nAll tests passed ✓")
        print("\nSample raw codes:")
        for mode, temp, fan in [("cool",22,"auto"),("cool",18,"auto"),("cool",27,"high"),
                                  ("heat",22,"auto"),("heat",20,"low"),
                                  ("dry",22,"auto"),("fan_only",22,"auto")]:
            raw = build_raw(mode, temp, fan)
            print(f"  {mode:8s} T{temp} {fan:6s}: {raw[:70]}...")
