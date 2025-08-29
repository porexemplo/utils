#!/usr/bin/env python3
# keep_green_stealth.py — randomized, human-like “presence nudge” for Teams testing.
# For testing/research only. Follow your org’s policies.

import argparse, random, time, platform, math, sys, re
from contextlib import suppress
from datetime import datetime, time as dtime
import psutil

OS = platform.system()

# --- deps ---
try:
    from pynput.mouse import Controller as MouseController
    from pynput.keyboard import Controller as KeyController, Key
except Exception as e:
    print(f"[!] pynput not available: {e}\nRun: pip install pynput", file=sys.stderr)
    sys.exit(1)

mouse = MouseController()
kb = KeyController()

# --- idle time (Windows/macOS reliable; else None) ---
def get_idle_seconds():
    if OS == "Windows":
        import ctypes
        from ctypes import wintypes
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not user32.GetLastInputInfo(ctypes.byref(lii)):
            return None
        tick = kernel32.GetTickCount()
        return max(0.0, (tick - lii.dwTime) / 1000.0)
    elif OS == "Darwin":
        with suppress(Exception):
            from Quartz import (
                CGEventSourceSecondsSinceLastEventType,
                kCGEventSourceStateCombinedSessionState,
                kCGAnyInputEventType,
            )
            return float(
                CGEventSourceSecondsSinceLastEventType(
                    kCGEventSourceStateCombinedSessionState, kCGAnyInputEventType
                )
            )
        return None
    else:
        return None  # Wayland/X11 variability: fall back to time-based strategy

# --- optional Windows display inhibitor ---
class WinDisplayInhibitor:
    def __init__(self, enabled=False):
        self.enabled = enabled and OS == "Windows"
        if self.enabled:
            try:
                import ctypes
                self._k32 = ctypes.windll.kernel32
                self.ES_CONTINUOUS = 0x80000000
                self.ES_DISPLAY_REQUIRED = 0x00000002
            except Exception:
                self.enabled = False
    def poke(self):
        if self.enabled:
            self._k32.SetThreadExecutionState(self.ES_CONTINUOUS | self.ES_DISPLAY_REQUIRED)

# --- helpers ---
def parse_quiet(spec: str):
    # "HH:MM-HH:MM" (24h). Multiple ranges separated by comma.
    ranges = []
    for part in spec.split(","):
        m = re.fullmatch(r"\s*(\d{2}):(\d{2})-(\d{2}):(\d{2})\s*", part)
        if not m: continue
        a = dtime(int(m.group(1)), int(m.group(2)))
        b = dtime(int(m.group(3)), int(m.group(4)))
        ranges.append((a, b))
    return ranges

def in_quiet_hours(ranges):
    if not ranges: return False
    now = datetime.now().time()
    for a, b in ranges:
        if a <= b:
            if a <= now <= b: return True
        else:
            # wraps midnight
            if now >= a or now <= b: return True
    return False

def machine_is_busy():
    # cheap signals that you’re actually doing stuff
    try:
        if psutil.cpu_percent(interval=0.1) > 25:  # short spike
            return True
        if any(p.info["name"] and "Teams" in p.info["name"] for p in psutil.process_iter(["name"])):
            # If Teams is open & CPU>5% over 1s, likely active call/meeting
            if psutil.cpu_percent(interval=1.0) > 5:
                return True
    except Exception:
        pass
    return False

# --- human-ish actions ---
def bezier_mouse_move(total_pixels, duration=0.35, steps=12):
    # Move along a subtle curve with slight jitter
    if total_pixels == 0:
        total_pixels = 1
    angle = random.uniform(0, 2 * math.pi)
    dx = math.cos(angle) * total_pixels
    dy = math.sin(angle) * total_pixels

    # control points create a tiny arc
    cx1 = dx * random.uniform(0.25, 0.45)
    cy1 = dy * random.uniform(0.25, 0.45)
    cx2 = dx * random.uniform(0.55, 0.75)
    cy2 = dy * random.uniform(0.55, 0.75)

    start = mouse.position

    def bezier(t, p0, c1, c2, p3):
        x = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * c1[0] + 3 * (1 - t) * t ** 2 * c2[0] + t ** 3 * p3[0]
        y = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * c1[1] + 3 * (1 - t) * t ** 2 * c2[1] + t ** 3 * p3[1]
        return (x, y)

    p0 = start
    p3 = (start[0] + dx, start[1] + dy)
    c1 = (start[0] + cx1, start[1] + cy1)
    c2 = (start[0] + cx2, start[1] + cy2)

    for i in range(1, steps + 1):
        t = i / steps
        x, y = bezier(t, p0, c1, c2, p3)
        # micro jitter
        x += random.uniform(-0.3, 0.3)
        y += random.uniform(-0.3, 0.3)
        mouse.position = (x, y)
        time.sleep(duration / steps)

def do_mouse(p_min, p_max):
    dist = random.randint(p_min, p_max)
    bezier_mouse_move(dist, duration=random.uniform(0.2, 0.5), steps=random.randint(8, 14))
    # often return roughly back
    if random.random() < 0.6:
        bezier_mouse_move(-dist, duration=random.uniform(0.18, 0.4), steps=random.randint(7, 12))

def do_scroll():
    # tiny scroll bump up or down
    amount = random.choice([-1, 1])
    try:
        mouse.scroll(0, amount)
    except Exception:
        pass

def do_key():
    # light, innocuous keys: Shift or Ctrl (no text)
    key = random.choice([Key.shift, Key.ctrl])
    try:
        kb.press(key); kb.release(key)
    except Exception:
        pass

def choose_action(method, chance_key, chance_scroll, p_min, p_max):
    if method == "mouse":
        return lambda: do_mouse(p_min, p_max)
    if method == "keyboard":
        return do_key
    # auto mix
    r = random.random()
    if r < chance_scroll:
        return do_scroll
    elif r < chance_scroll + chance_key:
        return do_key
    else:
        return lambda: do_mouse(p_min, p_max)

def human_delay(min_s, max_s):
    # log-normal-ish randomness with clamped bounds
    base = random.lognormvariate(3.7, 0.35)  # ~40–60s center
    delay = max(min_s, min(max_s, base))
    # add small jitter
    delay += random.uniform(-3, 5)
    return max(min_s, min(max_s, delay))

def run(args):
    inhibitor = WinDisplayInhibitor(enabled=args.win_poke)
    quiet_ranges = parse_quiet(args.quiet) if args.quiet else []

    print("[info] keep_green_stealth running. Ctrl+C to stop.")
    print(f"[info] window={args.min}-{args.max}s, idle≥{args.idle}s, method={args.method}, quiet={args.quiet or 'none'}")

    last_win_poke = 0.0
    while True:
        now = time.time()
        if inhibitor.enabled and now - last_win_poke > max(30, (args.min + args.max) / 2):
            inhibitor.poke(); last_win_poke = now

        if in_quiet_hours(quiet_ranges):
            time.sleep(60)
            continue

        # back off if you're clearly using the machine
        if machine_is_busy():
            time.sleep(random.uniform(20, 45))
            continue

        idle = get_idle_seconds()
        if idle is not None and idle < args.idle:
            # you're not idle enough
            time.sleep(random.uniform(10, 25))
            continue

        act = choose_action(args.method, args.chance_key, args.chance_scroll, args.pixels[0], args.pixels[1])
        act()

        # random “human” delay
        time.sleep(human_delay(args.min, args.max))

def parse_args():
    p = argparse.ArgumentParser(description="Randomized, stealthy presence nudge for Teams testing.")
    p.add_argument("--min", type=int, default=45, help="Minimum seconds between actions.")
    p.add_argument("--max", type=int, default=180, help="Maximum seconds between actions.")
    p.add_argument("--idle", type=int, default=240, help="Act only if idle ≥ this many seconds (if detectable).")
    p.add_argument("--method", choices=["auto", "mouse", "keyboard"], default="auto", help="Action selection mode.")
    p.add_argument("--pixels", type=int, nargs=2, default=[1, 4], metavar=("MIN", "MAX"),
                   help="Mouse move distance range in pixels.")
    p.add_argument("--chance-key", type=float, default=0.25, help="Probability to use a key tap (auto mode).")
    p.add_argument("--chance-scroll", type=float, default=0.15, help="Probability to do a tiny scroll (auto mode).")
    p.add_argument("--quiet", type=str, default="", help="Quiet hours like '00:30-06:30,13:00-14:00'.")
    p.add_argument("--win-poke", action="store_true", help="Windows: keep display awake via SetThreadExecutionState.")
    return p.parse_args()

if __name__ == "__main__":
    try:
        run(parse_args())
    except KeyboardInterrupt:
        print("\n[info] Stopped. Bye!")

