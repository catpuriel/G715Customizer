# G715 Customizer

A native Linux desktop app (Qt6 / PySide6) and CLI for customizing the **Logitech G715** keyboard — including **saving custom colors, effects, timeouts, and F1–F12 bindings directly to onboard flash memory** without Logitech G HUB.

## Features

- **Onboard Memory Editor (`0x8100`)**: Customize **Keys (Zone 0)** and **16-LED Perimeter Underglow (Zone 1)** independently (Static, Breathing, Color Cycle, Color Wave, Echo Press/Ripple, Aurora Playful, or Off), plus dimmed/idle colors and dim/sleep timers — written directly to flash Sector `0x0001` with verified CRC-16/CCITT checksums so your colors survive reboots, unplugs, Linux, Windows, and Bluetooth/Lightspeed switches.
- **Per-Key & 16-LED Perimeter RGB Studio (`0x8081`)**: Interactive click-and-drag visual G715 TKL + underglow painter with quick fill tools, horizontal gradients, right-click eyedropper, and saved layout presets.
- **Persistent Boot & Shutdown Animations (`0x8071` NvConfig)**: Customize the startup/wake and shutdown animations stored in hardware flash.
- **Full Hardware Controls**: Live LED brightness (`0x8040`), polling rate (`0x8060`), battery readout (`0x1004`), F1–F12 & G-Shift onboard key remapping, flash memory backups/restore, and one-click factory reset from ROM (`0x0101`).
- **Wired USB + Lightspeed Wireless + Bluetooth**: Automatically detects wired USB (`046d:c347`), Lightspeed wireless receivers (`046d:c547`, etc.), and Bluetooth (`046d:b368`).

## Quick Start

### Launch the Desktop App
```bash
python3 g715_gui.py
```

### Use the CLI
```bash
# Inspect keyboard status, battery, and current onboard colors
python3 g715_cli.py status

# Save custom solid colors permanently to onboard flash memory
python3 g715_cli.py onboard set-color --keys "#FF73B9" --perimeter "#6BE5F5"

# Apply a built-in onboard preset to flash
python3 g715_cli.py onboard preset "Aurora Pink & Cyan"

# Set an animated onboard effect
python3 g715_cli.py onboard set-effect --zone keys --effect breathe --color "#FF55BB" --period 4500

# Customize startup/shutdown animations in flash
python3 g715_cli.py boot-anim startup --on --color1 "#FF8DAA" --color2 "#8BE4E9"

# Apply a per-key gradient live (0x8081) or return to onboard flash
python3 g715_cli.py perkey gradient "#FF66B2" "#64EEFF"
python3 g715_cli.py perkey release

# Back up & restore onboard flash memory
python3 g715_cli.py backup --label before-tweaks
python3 g715_cli.py restore
```

## Permissions (udev Rules)

If you get a permission error opening `/dev/hidraw*` (especially over a Lightspeed receiver):
```bash
sudo cp udev/99-logitech-g715.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Backups

All flash backups and user presets are stored in `~/.local/share/g715-customizer/`.

## Contributors

- **[@catpuriel](https://github.com/catpuriel)** — Creator, hardware testing & design
- **Antigravity (Google DeepMind)** — AI pair programmer (HID++ protocol implementation, Qt6 desktop UI & CLI)

## License

Released under the [MIT License](LICENSE).
