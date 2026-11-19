"""Command-line interface for G715 Customizer."""

from __future__ import annotations

import argparse
import sys

from .hidpp import HidppError, discover_g715_devices
from .presets import (
    BUILTIN_ONBOARD_PRESETS,
    build_builtin_perkey_presets,
    generate_gradient_layout,
    list_backups,
    load_backup,
    load_user_onboard_presets,
    load_user_perkey_presets,
    save_backup,
)
from .protocol import (
    BootAnimation,
    EFFECT_AURORA_PLAYFUL,
    EFFECT_BREATHE,
    EFFECT_CYCLE,
    EFFECT_NAMES,
    EFFECT_OFF,
    EFFECT_RIPPLE,
    EFFECT_STATIC,
    EFFECT_WAVE,
    G715Device,
    LedEffect,
    WAVE_DIRECTIONS,
    dim_color,
    format_hex_color,
    parse_hex_color,
)

EFFECT_CLI_MAP = {
    "off": EFFECT_OFF,
    "static": EFFECT_STATIC,
    "breathe": EFFECT_BREATHE,
    "cycle": EFFECT_CYCLE,
    "wave": EFFECT_WAVE,
    "ripple": EFFECT_RIPPLE,
    "aurora": EFFECT_AURORA_PLAYFUL,
}

DIRECTION_CLI_MAP = {v.lower().replace(" ", "-"): k for k, v in WAVE_DIRECTIONS.items()}


def _describe_effect(eff: LedEffect) -> str:
    name = EFFECT_NAMES.get(eff.effect_id, f"0x{eff.effect_id:02X}")
    if eff.effect_id == EFFECT_STATIC:
        return f"{name} ({format_hex_color(eff.color)})"
    if eff.effect_id == EFFECT_BREATHE:
        return f"{name} ({format_hex_color(eff.color)}, period={eff.period}ms, intensity={eff.intensity}%)"
    if eff.effect_id == EFFECT_CYCLE:
        return f"{name} (period={eff.period}ms, sat={eff.saturation}, intensity={eff.intensity}%)"
    if eff.effect_id == EFFECT_WAVE:
        dname = WAVE_DIRECTIONS.get(eff.direction, str(eff.direction))
        return f"{name} (dir={dname}, period={eff.period}ms, sat={eff.saturation}, intensity={eff.intensity}%)"
    if eff.effect_id == EFFECT_RIPPLE:
        return f"{name} ({format_hex_color(eff.color)}, speed={eff.period})"
    return name


def cmd_status(_args: argparse.Namespace) -> int:
    devices = discover_g715_devices()
    if not devices:
        print("No Logitech G715 keyboard detected.")
        return 1

    with G715Device.connect(devices[0]) as dev:
        st = dev.get_status()
        prof = dev.read_onboard_profile(1)
        startup = dev.get_boot_animation("startup")
        shutdown = dev.get_boot_animation("shutdown")

        hz = {1: 1000, 2: 500, 4: 250, 8: 125}.get(st.report_rate_ms, 0)
        print(f"Device:           {st.name}")
        print(f"Connection:       {st.connection.upper()} ({st.hidraw_path}, HID++ {st.protocol_version})")
        if st.battery:
            print(f"Battery:          {st.battery.percentage}% ({st.battery.status_text})")
        print(f"Mode:             {'Onboard Memory' if st.onboard_mode else 'Host / SW Control'} (SW override={'ON' if st.sw_control else 'OFF'})")
        print(f"Brightness:       {st.brightness_pct}%")
        print(f"Polling Rate:     {hz} Hz ({st.report_rate_ms} ms)")
        print()
        print(f"Onboard Profile (Sector 0x{prof.sector:04X}): {prof.name!r}")
        print(f"  Keys Active:      {_describe_effect(prof.keys_active)}")
        print(f"  Perimeter Active: {_describe_effect(prof.perimeter_active)}")
        print(f"  Keys Dim:         {_describe_effect(prof.keys_dim)}")
        print(f"  Perimeter Dim:    {_describe_effect(prof.perimeter_dim)}")
        ps_txt = "Disabled" if prof.ps_timeout_s in (0, 0xFFFF) else f"{prof.ps_timeout_s}s"
        po_txt = "Disabled" if prof.po_timeout_s in (0, 0xFFFF) else f"{prof.po_timeout_s}s"
        print(f"  Dim Timeout:      {ps_txt}")
        print(f"  Sleep Timeout:    {po_txt}")
        print()
        print(
            f"Startup Anim:     {'ON' if startup.enabled else 'OFF'} "
            f"({format_hex_color(startup.color1)} -> {format_hex_color(startup.color2)})"
        )
        print(
            f"Shutdown Anim:    {'ON' if shutdown.enabled else 'OFF'} "
            f"({format_hex_color(shutdown.color1)} -> {format_hex_color(shutdown.color2)})"
        )
    return 0


def cmd_onboard_set_color(args: argparse.Namespace) -> int:
    with G715Device.connect() as dev:
        prof = dev.read_onboard_profile(1)
        if args.keys:
            kc = parse_hex_color(args.keys)
            prof.keys_active = LedEffect(EFFECT_STATIC, color=kc)
            kdim = parse_hex_color(args.keys_dim) if args.keys_dim else dim_color(kc, args.dim_factor)
            prof.keys_dim = LedEffect(EFFECT_STATIC, color=kdim)
        if args.perimeter:
            pc = parse_hex_color(args.perimeter)
            prof.perimeter_active = LedEffect(EFFECT_STATIC, color=pc)
            pdim = parse_hex_color(args.perimeter_dim) if args.perimeter_dim else dim_color(pc, args.dim_factor)
            prof.perimeter_dim = LedEffect(EFFECT_STATIC, color=pdim)
        if args.name:
            prof.name = args.name[:24]
        dev.write_onboard_profile(prof, activate=True)
        print("Saved onboard colors to flash memory and activated!")
        print(f"  Keys:      {_describe_effect(prof.keys_active)}  (dim: {_describe_effect(prof.keys_dim)})")
        print(f"  Perimeter: {_describe_effect(prof.perimeter_active)}  (dim: {_describe_effect(prof.perimeter_dim)})")
    return 0


def cmd_onboard_set_effect(args: argparse.Namespace) -> int:
    eid = EFFECT_CLI_MAP[args.effect]
    color = parse_hex_color(args.color) if args.color else 0xF552FF
    direction = DIRECTION_CLI_MAP.get(args.direction.lower(), 1) if args.direction else 1
    eff = LedEffect(
        effect_id=eid,
        color=color,
        period=args.period,
        intensity=args.intensity,
        saturation=args.saturation,
        direction=direction,
    )
    dim_eff = LedEffect(
        effect_id=eid,
        color=dim_color(color, args.dim_factor),
        period=args.period,
        intensity=max(10, int(args.intensity * args.dim_factor)),
        saturation=args.saturation,
        direction=direction,
    )
    with G715Device.connect() as dev:
        prof = dev.read_onboard_profile(1)
        if args.zone in ("keys", "both"):
            prof.keys_active = eff
            prof.keys_dim = dim_eff
        if args.zone in ("perimeter", "both"):
            if eid == EFFECT_RIPPLE:
                print("Warning: Ripple/Echo Press is only supported on the keys zone; skipping perimeter.")
            else:
                prof.perimeter_active = eff
                prof.perimeter_dim = dim_eff
        dev.write_onboard_profile(prof, activate=True)
        print(f"Saved onboard effect to flash ({args.zone}): {_describe_effect(eff)}")
    return 0


def cmd_onboard_preset(args: argparse.Namespace) -> int:
    all_presets = {**BUILTIN_ONBOARD_PRESETS, **load_user_onboard_presets()}
    if args.preset_name is None:
        print("Available onboard presets:")
        for name in all_presets:
            print(f"  - {name}")
        return 0
    match = next((k for k in all_presets if k.lower() == args.preset_name.lower()), None)
    if match is None:
        print(f"Unknown preset {args.preset_name!r}. Available: {', '.join(all_presets)}")
        return 1
    p = all_presets[match]
    with G715Device.connect() as dev:
        prof = dev.read_onboard_profile(1)
        prof.keys_active = LedEffect.from_dict(p["keys_active"])
        prof.perimeter_active = LedEffect.from_dict(p["perimeter_active"])
        prof.keys_dim = LedEffect.from_dict(p["keys_dim"])
        prof.perimeter_dim = LedEffect.from_dict(p["perimeter_dim"])
        dev.write_onboard_profile(prof, activate=True)
        print(f"Saved preset {match!r} to onboard flash memory!")
    return 0


def cmd_onboard_timeouts(args: argparse.Namespace) -> int:
    with G715Device.connect() as dev:
        prof = dev.read_onboard_profile(1)
        if args.dim is not None:
            prof.ps_timeout_s = 0xFFFF if args.dim <= 0 else args.dim
        if args.sleep is not None:
            prof.po_timeout_s = 0xFFFF if args.sleep <= 0 else args.sleep
        dev.write_onboard_profile(prof, activate=True)
        print(f"Saved timeouts to flash: dim={prof.ps_timeout_s}s, sleep={prof.po_timeout_s}s")
    return 0


def cmd_perkey(args: argparse.Namespace) -> int:
    if args.action == "release":
        with G715Device.connect() as dev:
            dev.release_sw_control()
        print("Released software RGB control; keyboard returned to onboard flash memory.")
        return 0

    all_pk = {**build_builtin_perkey_presets(), **load_user_perkey_presets()}
    if args.action == "list":
        print("Available per-key presets:")
        for name in all_pk:
            print(f"  - {name}")
        return 0

    if args.action == "apply":
        match = next((k for k in all_pk if k.lower() == (args.name or "").lower()), None)
        if match is None:
            print(f"Unknown per-key preset {args.name!r}. Available: {', '.join(all_pk)}")
            return 1
        with G715Device.connect() as dev:
            dev.apply_perkey_frame(all_pk[match], base_color=0x000000)
        print(f"Applied per-key preset {match!r} live to keyboard!")
        return 0

    if args.action == "gradient":
        c1 = parse_hex_color(args.left)
        c2 = parse_hex_color(args.right)
        frame = generate_gradient_layout(c1, c2)
        with G715Device.connect() as dev:
            dev.apply_perkey_frame(frame, base_color=c1)
        print(f"Applied live per-key gradient {format_hex_color(c1)} -> {format_hex_color(c2)}!")
        return 0

    return 1


def cmd_boot_anim(args: argparse.Namespace) -> int:
    with G715Device.connect() as dev:
        cur = dev.get_boot_animation(args.kind)
        enabled = cur.enabled
        if args.enable:
            enabled = True
        elif args.disable:
            enabled = False
        c1 = parse_hex_color(args.color1) if args.color1 else cur.color1
        c2 = parse_hex_color(args.color2) if args.color2 else cur.color2
        anim = BootAnimation(kind=args.kind, enabled=enabled, color1=c1, color2=c2)
        dev.set_boot_animation(anim)
        print(
            f"Saved {args.kind} animation to NvConfig flash: "
            f"{'ON' if anim.enabled else 'OFF'} ({format_hex_color(c1)} -> {format_hex_color(c2)})"
        )
    return 0


def cmd_brightness(args: argparse.Namespace) -> int:
    with G715Device.connect() as dev:
        if args.percent is None:
            print(f"Brightness: {dev.get_brightness()}%")
        else:
            dev.set_brightness(args.percent)
            print(f"Set brightness to {args.percent}%")
    return 0


def cmd_report_rate(args: argparse.Namespace) -> int:
    hz_to_ms = {1000: 1, 500: 2, 250: 4, 125: 8}
    with G715Device.connect() as dev:
        ms = hz_to_ms[args.hz]
        dev.set_report_rate(ms)
        prof = dev.read_onboard_profile(1)
        prof.report_rate_ms = ms
        dev.write_onboard_profile(prof, activate=True)
        print(f"Set report rate to {args.hz} Hz ({ms} ms) and saved to onboard profile.")
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    with G715Device.connect() as dev:
        sectors = dev.dump_all_sectors()
    path = save_backup(sectors, label=args.label)
    print(f"Saved onboard flash backup to {path}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    if args.file is None:
        backups = list_backups()
        if not backups:
            print("No backups found.")
            return 1
        print("Available backups:")
        for b in backups:
            print(f"  {b}")
        return 0
    data = load_backup(args.file)
    with G715Device.connect() as dev:
        n = dev.restore_sectors(data["sectors"])
    print(f"Restored {n} flash sector(s) from {args.file} and activated onboard memory.")
    return 0


def cmd_factory_reset(_args: argparse.Namespace) -> int:
    with G715Device.connect() as dev:
        dev.restore_factory_profile_from_rom()
    print("Restored Sector 0x0001 from factory ROM (0x0101) and activated!")
    return 0


def cmd_gui(_args: argparse.Namespace) -> int:
    from .gui.app import launch_gui
    return launch_gui()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="g715",
        description="Logitech G715 Customizer — Onboard Memory & RGB Studio for Linux",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show keyboard status, battery, onboard colors, and boot animations")
    sub.add_parser("gui", help="Launch the native Qt6 desktop application")

    # Onboard memory commands
    p_ob = sub.add_parser("onboard", help="Customize & save lighting/timeouts to onboard flash memory (0x8100)")
    ob_sub = p_ob.add_subparsers(dest="ob_cmd", required=True)

    p_col = ob_sub.add_parser("set-color", help="Set solid keys/perimeter color and save to onboard flash")
    p_col.add_argument("--keys", help="Keys active hex color, e.g. #FF73B9")
    p_col.add_argument("--perimeter", help="Perimeter underglow active hex color, e.g. #6BE5F5")
    p_col.add_argument("--keys-dim", help="Keys dimmed hex color (defaults to active * dim-factor)")
    p_col.add_argument("--perimeter-dim", help="Perimeter dimmed hex color (defaults to active * dim-factor)")
    p_col.add_argument("--dim-factor", type=float, default=0.45, help="Auto-dim multiplier (default: 0.45)")
    p_col.add_argument("--name", help="Optional onboard profile name (max 24 chars)")

    p_eff = ob_sub.add_parser("set-effect", help="Set animated or static onboard effect and save to flash")
    p_eff.add_argument("--zone", choices=["keys", "perimeter", "both"], default="both")
    p_eff.add_argument("--effect", choices=list(EFFECT_CLI_MAP), required=True)
    p_eff.add_argument("--color", default="#F552FF")
    p_eff.add_argument("--period", type=int, default=5000, help="Period in ms (or 2..200 for ripple)")
    p_eff.add_argument("--intensity", type=int, default=100, help="0..100")
    p_eff.add_argument("--saturation", type=int, default=255, help="0..255")
    p_eff.add_argument("--direction", default="right", choices=list(DIRECTION_CLI_MAP))
    p_eff.add_argument("--dim-factor", type=float, default=0.45)

    p_pre = ob_sub.add_parser("preset", help="Apply & save a named onboard preset (omit name to list)")
    p_pre.add_argument("preset_name", nargs="?")

    p_to = ob_sub.add_parser("timeouts", help="Configure dim & sleep timeouts in onboard flash (seconds; 0=off)")
    p_to.add_argument("--dim", type=int, help="Idle dim timeout in seconds (0 = disabled)")
    p_to.add_argument("--sleep", type=int, help="Sleep power-off timeout in seconds (0 = disabled)")

    # Per-key commands
    p_pk = sub.add_parser("perkey", help="Live per-key & 16-LED perimeter RGB control (0x8081)")
    pk_sub = p_pk.add_subparsers(dest="action", required=True)
    pk_sub.add_parser("list", help="List available per-key presets")
    pk_apply = pk_sub.add_parser("apply", help="Apply a saved per-key preset live")
    pk_apply.add_argument("name")
    pk_grad = pk_sub.add_parser("gradient", help="Apply a horizontal per-key gradient live")
    pk_grad.add_argument("left", help="Left hex color, e.g. #FF66B2")
    pk_grad.add_argument("right", help="Right hex color, e.g. #64EEFF")
    pk_sub.add_parser("release", help="Release software RGB control and return to onboard memory")

    # Boot animations
    p_boot = sub.add_parser("boot-anim", help="Configure persistent startup/shutdown animations (0x8071 NvConfig)")
    p_boot.add_argument("kind", choices=["startup", "shutdown"])
    grp = p_boot.add_mutually_exclusive_group()
    grp.add_argument("--on", dest="enable", action="store_true")
    grp.add_argument("--off", dest="disable", action="store_true")
    p_boot.add_argument("--color1", help="Primary hex color")
    p_boot.add_argument("--color2", help="Secondary hex color")

    # Brightness & report rate
    p_bri = sub.add_parser("brightness", help="Read or set keyboard brightness (0..100)")
    p_bri.add_argument("percent", type=int, nargs="?")

    p_rr = sub.add_parser("report-rate", help="Set polling rate (Hz)")
    p_rr.add_argument("hz", type=int, choices=[1000, 500, 250, 125])

    # Backup / Restore / Factory Reset
    p_bk = sub.add_parser("backup", help="Back up all onboard flash sectors to JSON")
    p_bk.add_argument("--label", default="manual")

    p_rs = sub.add_parser("restore", help="Restore onboard flash from a backup JSON (omit path to list)")
    p_rs.add_argument("file", nargs="?")

    sub.add_parser("factory-reset", help="Reset Sector 0x0001 to factory ROM defaults (0x0101)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        return cmd_gui(args)

    try:
        if args.command == "status":
            return cmd_status(args)
        if args.command == "gui":
            return cmd_gui(args)
        if args.command == "onboard":
            if args.ob_cmd == "set-color":
                return cmd_onboard_set_color(args)
            if args.ob_cmd == "set-effect":
                return cmd_onboard_set_effect(args)
            if args.ob_cmd == "preset":
                return cmd_onboard_preset(args)
            if args.ob_cmd == "timeouts":
                return cmd_onboard_timeouts(args)
        if args.command == "perkey":
            return cmd_perkey(args)
        if args.command == "boot-anim":
            return cmd_boot_anim(args)
        if args.command == "brightness":
            return cmd_brightness(args)
        if args.command == "report-rate":
            return cmd_report_rate(args)
        if args.command == "backup":
            return cmd_backup(args)
        if args.command == "restore":
            return cmd_restore(args)
        if args.command == "factory-reset":
            return cmd_factory_reset(args)
    except (HidppError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
