"""Per-Key & 16-LED Perimeter RGB Studio tab (0x8081 PerKeyLighting v2)."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..hidpp import HidppError
from ..layout import ARROW_ZONE_IDS, G715_LAYOUT, KEY_ZONE_IDS, PERIMETER_ZONE_IDS, WASD_ZONE_IDS
from ..presets import (
    build_builtin_perkey_presets,
    delete_user_perkey_preset,
    generate_gradient_layout,
    load_user_perkey_presets,
    save_user_perkey_preset,
)
from ..protocol import G715Device, format_hex_color
from .keyboard_widget import G715KeyboardWidget
from .widgets import ColorSwatchButton, QUICK_SWATCHES


class GradientDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Create Horizontal Gradient")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.left_btn = ColorSwatchButton(0xFF66B2)
        self.right_btn = ColorSwatchButton(0x64EEFF)
        self.perim_left_btn = ColorSwatchButton(0x64EEFF)
        self.perim_right_btn = ColorSwatchButton(0xFF66B2)
        form.addRow("Keys Left Color:", self.left_btn)
        form.addRow("Keys Right Color:", self.right_btn)
        form.addRow("Perimeter Left Color:", self.perim_left_btn)
        form.addRow("Perimeter Right Color:", self.perim_right_btn)
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)


class PerKeyStudioTab(QWidget):
    """Interactive per-key and 16-LED perimeter painter backed by HID++ 0x8081."""

    def __init__(
        self,
        get_device: Callable[[], Optional[G715Device]],
        notify: Callable[[str, bool], None],
        refresh_header: Callable[[], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._get_device = get_device
        self._notify = notify
        self._refresh_header = refresh_header
        self._builtin_presets = build_builtin_perkey_presets()

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(12)

        # --- Preset & Info Header ---
        top_card = QFrame()
        top_card.setObjectName("Card")
        top_lay = QHBoxLayout(top_card)
        top_lay.setContentsMargins(14, 10, 14, 10)
        top_lay.setSpacing(10)

        top_lay.addWidget(QLabel("Layout Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(220)
        self._reload_presets()
        top_lay.addWidget(self.preset_combo, stretch=1)

        btn_load = QPushButton("Load Layout")
        btn_load.clicked.connect(self._load_selected_preset)
        btn_save = QPushButton("Save Layout")
        btn_save.clicked.connect(self._save_layout)
        btn_del = QPushButton("Delete")
        btn_del.clicked.connect(self._delete_layout)
        top_lay.addWidget(btn_load)
        top_lay.addWidget(btn_save)
        top_lay.addWidget(btn_del)
        root.addWidget(top_card)

        # --- Brush & Fill Toolbar ---
        tool_card = QFrame()
        tool_card.setObjectName("Card")
        tool_v = QVBoxLayout(tool_card)
        tool_v.setContentsMargins(14, 10, 14, 10)
        tool_v.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(QLabel("Brush:"))
        self.brush_btn = ColorSwatchButton(0xFF73B9)
        self.brush_btn.colorChanged.connect(self._on_brush_changed)
        row1.addWidget(self.brush_btn)

        for sw in QUICK_SWATCHES:
            b = QPushButton()
            b.setFixedSize(22, 22)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(format_hex_color(sw))
            b.setStyleSheet(
                f"QPushButton {{ background: {format_hex_color(sw)}; border: 1px solid rgba(255,255,255,0.3); border-radius: 11px; }}"
                f"QPushButton:hover {{ border: 2px solid #FFFFFF; }}"
            )
            b.clicked.connect(lambda _c=False, col=sw: self.brush_btn.set_color(col, emit=True))
            row1.addWidget(b)

        row1.addStretch()
        hint = QLabel("Left-click/drag: paint  •  Right-click: eyedropper")
        hint.setStyleSheet("color: #94A3B8; font-size: 12px;")
        row1.addWidget(hint)
        tool_v.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        for label, cb in [
            ("Fill All Keys", self._fill_keys),
            ("Fill Perimeter (16 LEDs)", self._fill_perimeter),
            ("Fill WASD", self._fill_wasd),
            ("Fill Arrows", self._fill_arrows),
            ("Fill Modifiers", self._fill_modifiers),
            ("Gradient...", self._open_gradient),
            ("Clear (Black)", self._clear_all),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(cb)
            row2.addWidget(btn)
        row2.addStretch()
        tool_v.addLayout(row2)
        root.addWidget(tool_card)

        # --- Interactive Keyboard Canvas ---
        canvas_card = QFrame()
        canvas_card.setObjectName("Card")
        cv_lay = QVBoxLayout(canvas_card)
        cv_lay.setContentsMargins(10, 10, 10, 10)
        self.canvas = G715KeyboardWidget(interactive=True)
        self.canvas.set_zone_colors(self._builtin_presets["Aurora Gradient"])
        self.canvas.set_brush_color(self.brush_btn.color)
        self.canvas.paintStrokeFinished.connect(self._on_stroke_finished)
        self.canvas.colorPicked.connect(lambda c: self.brush_btn.set_color(c, emit=True))
        cv_lay.addWidget(self.canvas)
        root.addWidget(canvas_card, stretch=1)

        # --- Live Hardware Controls ---
        foot_card = QFrame()
        foot_card.setObjectName("Card")
        foot = QHBoxLayout(foot_card)
        foot.setContentsMargins(14, 10, 14, 10)
        foot.setSpacing(12)

        self.auto_sync_cb = QCheckBox("Auto-sync to keyboard as I paint")
        self.auto_sync_cb.setChecked(False)
        foot.addWidget(self.auto_sync_cb)

        note = QLabel("Streams live via 0x8081  •  CLI: `g715 perkey apply <name>`")
        note.setStyleSheet("color: #94A3B8; font-size: 12px;")
        foot.addWidget(note, stretch=1)

        btn_release = QPushButton("Return to Onboard Memory")
        btn_release.setMinimumHeight(38)
        btn_release.clicked.connect(self._release_to_onboard)

        btn_apply = QPushButton("Apply Per-Key Layout Live")
        btn_apply.setObjectName("PrimaryButton")
        btn_apply.setMinimumHeight(38)
        btn_apply.clicked.connect(self._push_to_keyboard)

        foot.addWidget(btn_release)
        foot.addWidget(btn_apply)
        root.addWidget(foot_card)

    def _reload_presets(self) -> None:
        self.preset_combo.clear()
        for name in self._builtin_presets:
            self.preset_combo.addItem(name, ("builtin", name))
        user_pk = load_user_perkey_presets()
        if user_pk:
            self.preset_combo.insertSeparator(self.preset_combo.count())
            for name in user_pk:
                self.preset_combo.addItem(f"★ {name}", ("user", name))

    def _on_brush_changed(self, color: int) -> None:
        self.canvas.set_brush_color(color)

    def _fill_group(self, zone_ids: list[int], color: Optional[int] = None) -> None:
        col = self.brush_btn.color if color is None else color
        cur = self.canvas.get_zone_colors()
        for z in zone_ids:
            cur[z] = col
        self.canvas.set_zone_colors(cur)
        if self.auto_sync_cb.isChecked():
            self._push_to_keyboard()

    def _fill_keys(self) -> None:
        self._fill_group(KEY_ZONE_IDS)

    def _fill_perimeter(self) -> None:
        self._fill_group(PERIMETER_ZONE_IDS)

    def _fill_wasd(self) -> None:
        self._fill_group(WASD_ZONE_IDS)

    def _fill_arrows(self) -> None:
        self._fill_group(ARROW_ZONE_IDS)

    def _fill_modifiers(self) -> None:
        mods = [c.zone_id for c in G715_LAYOUT if c.group in ("modifiers", "function")]
        self._fill_group(mods)

    def _clear_all(self) -> None:
        self._fill_group([c.zone_id for c in G715_LAYOUT], color=0x000000)

    def _open_gradient(self) -> None:
        dlg = GradientDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            frame = generate_gradient_layout(
                dlg.left_btn.color,
                dlg.right_btn.color,
                dlg.perim_left_btn.color,
                dlg.perim_right_btn.color,
            )
            self.canvas.set_zone_colors(frame)
            if self.auto_sync_cb.isChecked():
                self._push_to_keyboard()

    def _on_stroke_finished(self) -> None:
        if self.auto_sync_cb.isChecked():
            self._push_to_keyboard()

    def _load_selected_preset(self) -> None:
        data = self.preset_combo.currentData()
        if not data:
            return
        kind, name = data
        src = self._builtin_presets if kind == "builtin" else load_user_perkey_presets()
        if name in src:
            self.canvas.set_zone_colors(src[name])
            self._notify(f"Loaded per-key layout '{name}'.", False)
            if self.auto_sync_cb.isChecked():
                self._push_to_keyboard()

    def _save_layout(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Per-Key Layout", "Layout name:")
        if not ok or not name.strip():
            return
        save_user_perkey_preset(name.strip(), self.canvas.get_zone_colors())
        self._reload_presets()
        self._notify(f"Saved per-key layout '{name.strip()}'.", False)

    def _delete_layout(self) -> None:
        data = self.preset_combo.currentData()
        if not data or data[0] != "user":
            QMessageBox.information(self, "Delete Layout", "Built-in layouts cannot be deleted. Select a saved (★) layout.")
            return
        delete_user_perkey_preset(data[1])
        self._reload_presets()
        self._notify(f"Deleted per-key layout '{data[1]}'.", False)

    def _push_to_keyboard(self) -> None:
        dev = self._get_device()
        if dev is None:
            self._notify("No G715 connected.", True)
            return
        try:
            dev.apply_perkey_frame(self.canvas.get_zone_colors(), base_color=0x000000, ensure_sw_control=True)
            self._refresh_header()
            self._notify("Applied per-key & 16-LED perimeter layout live!", False)
        except HidppError as e:
            self._notify(f"Per-key update failed: {e}", True)

    def _release_to_onboard(self) -> None:
        dev = self._get_device()
        if dev is None:
            self._notify("No G715 connected.", True)
            return
        try:
            dev.release_sw_control()
            self._refresh_header()
            self._notify("Released SW control — keyboard is back on onboard flash memory.", False)
        except HidppError as e:
            self._notify(f"Failed to release SW control: {e}", True)
