"""Reusable styled Qt6 widgets for G715 Customizer."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..protocol import (
    EFFECT_AURORA_PLAYFUL,
    EFFECT_BREATHE,
    EFFECT_CYCLE,
    EFFECT_NAMES,
    EFFECT_OFF,
    EFFECT_RIPPLE,
    EFFECT_STATIC,
    EFFECT_WAVE,
    LedEffect,
    WAVE_DIRECTIONS,
    format_hex_color,
)

QUICK_SWATCHES = [
    0xFF73B9,  # Aurora Pink
    0xF552FF,  # Electric Magenta
    0xB388FF,  # Lavender
    0x6BE5F5,  # Aurora Cyan
    0x00F0FF,  # Neon Aqua
    0x7CFFB2,  # Mint Matcha
    0xFFE6C8,  # Warm White
    0xFFB36B,  # Sunset Peach
    0xFF3B6B,  # Coral Red
    0xFFFFFF,  # Pure White
]


class ColorSwatchButton(QPushButton):
    """Rounded color picker button displaying hex color and opening QColorDialog."""

    colorChanged = Signal(int)

    def __init__(self, color: int = 0xF552FF, parent: QWidget | None = None):
        super().__init__(parent)
        self._color = color & 0xFFFFFF
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(34)
        self.setMinimumWidth(116)
        self.clicked.connect(self._pick_color)
        self._refresh_style()

    @property
    def color(self) -> int:
        return self._color

    def set_color(self, color: int, emit: bool = False) -> None:
        c = color & 0xFFFFFF
        if c != self._color:
            self._color = c
            self._refresh_style()
            if emit:
                self.colorChanged.emit(self._color)
        else:
            self._refresh_style()

    def _refresh_style(self) -> None:
        r = (self._color >> 16) & 0xFF
        g = (self._color >> 8) & 0xFF
        b = self._color & 0xFF
        luma = 0.299 * r + 0.587 * g + 0.114 * b
        fg = "#11131A" if luma > 145 else "#F8FAFC"
        hx = format_hex_color(self._color)
        self.setText(hx)
        self.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {hx};"
            f"  color: {fg};"
            f"  border: 2px solid rgba(255, 255, 255, 0.28);"
            f"  border-radius: 8px;"
            f"  font-weight: 700;"
            f"  font-family: monospace;"
            f"  padding: 4px 10px;"
            f"}}"
            f"QPushButton:hover {{ border-color: #FFFFFF; }}"
        )

    def _pick_color(self) -> None:
        initial = QColor((self._color >> 16) & 0xFF, (self._color >> 8) & 0xFF, self._color & 0xFF)
        chosen = QColorDialog.getColor(initial, self, "Choose RGB Color")
        if chosen.isValid():
            val = (chosen.red() << 16) | (chosen.green() << 8) | chosen.blue()
            self.set_color(val, emit=True)


class EffectEditorWidget(QFrame):
    """Adaptive editor card for a single G715 LED lighting zone (Keys or Perimeter)."""

    effectChanged = Signal()

    def __init__(self, title: str, allow_ripple: bool = True, allow_factory: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header = QLabel(title)
        header.setObjectName("CardTitle")
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        # Effect type dropdown
        self.effect_combo = QComboBox()
        effect_ids = [EFFECT_STATIC, EFFECT_BREATHE, EFFECT_CYCLE, EFFECT_WAVE]
        if allow_ripple:
            effect_ids.append(EFFECT_RIPPLE)
        if allow_factory:
            effect_ids.append(EFFECT_AURORA_PLAYFUL)
        effect_ids.append(EFFECT_OFF)
        for eid in effect_ids:
            self.effect_combo.addItem(EFFECT_NAMES[eid], eid)
        self.effect_combo.currentIndexChanged.connect(self._on_effect_type_changed)
        form.addRow("Effect", self.effect_combo)

        # Primary color picker + quick swatches
        self.color_row_widget = QWidget()
        col_v = QVBoxLayout(self.color_row_widget)
        col_v.setContentsMargins(0, 0, 0, 0)
        col_v.setSpacing(6)

        self.color_btn = ColorSwatchButton(0xF552FF)
        self.color_btn.colorChanged.connect(lambda _: self._emit_changed())
        col_v.addWidget(self.color_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        sw_row = QHBoxLayout()
        sw_row.setSpacing(5)
        for sw in QUICK_SWATCHES:
            b = QPushButton()
            b.setFixedSize(20, 20)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(format_hex_color(sw))
            b.setStyleSheet(
                f"QPushButton {{ background: {format_hex_color(sw)}; border: 1px solid rgba(255,255,255,0.3); border-radius: 10px; }}"
                f"QPushButton:hover {{ border: 2px solid #FFFFFF; }}"
            )
            b.clicked.connect(lambda _checked=False, c=sw: self.color_btn.set_color(c, emit=True))
            sw_row.addWidget(b)
        sw_row.addStretch()
        col_v.addLayout(sw_row)

        self.color_label = QLabel("Color")
        form.addRow(self.color_label, self.color_row_widget)

        # Speed / Period slider
        self.period_row = QWidget()
        per_h = QHBoxLayout(self.period_row)
        per_h.setContentsMargins(0, 0, 0, 0)
        self.period_slider = QSlider(Qt.Orientation.Horizontal)
        self.period_slider.setRange(500, 15000)
        self.period_slider.setValue(5000)
        self.period_slider.valueChanged.connect(self._on_period_changed)
        self.period_val_lbl = QLabel("5.0 s")
        self.period_val_lbl.setMinimumWidth(50)
        per_h.addWidget(self.period_slider)
        per_h.addWidget(self.period_val_lbl)
        self.period_label = QLabel("Cycle Period")
        form.addRow(self.period_label, self.period_row)

        # Intensity slider
        self.intensity_row = QWidget()
        int_h = QHBoxLayout(self.intensity_row)
        int_h.setContentsMargins(0, 0, 0, 0)
        self.intensity_slider = QSlider(Qt.Orientation.Horizontal)
        self.intensity_slider.setRange(10, 100)
        self.intensity_slider.setValue(100)
        self.intensity_slider.valueChanged.connect(self._on_intensity_changed)
        self.intensity_val_lbl = QLabel("100%")
        self.intensity_val_lbl.setMinimumWidth(50)
        int_h.addWidget(self.intensity_slider)
        int_h.addWidget(self.intensity_val_lbl)
        self.intensity_label = QLabel("Intensity")
        form.addRow(self.intensity_label, self.intensity_row)

        # Saturation slider
        self.sat_row = QWidget()
        sat_h = QHBoxLayout(self.sat_row)
        sat_h.setContentsMargins(0, 0, 0, 0)
        self.sat_slider = QSlider(Qt.Orientation.Horizontal)
        self.sat_slider.setRange(0, 255)
        self.sat_slider.setValue(255)
        self.sat_slider.valueChanged.connect(self._on_sat_changed)
        self.sat_val_lbl = QLabel("100%")
        self.sat_val_lbl.setMinimumWidth(50)
        sat_h.addWidget(self.sat_slider)
        sat_h.addWidget(self.sat_val_lbl)
        self.sat_label = QLabel("Saturation")
        form.addRow(self.sat_label, self.sat_row)

        # Direction combo (Wave)
        self.dir_combo = QComboBox()
        for did, dname in WAVE_DIRECTIONS.items():
            self.dir_combo.addItem(dname, did)
        self.dir_combo.setCurrentIndex(1)  # Right
        self.dir_combo.currentIndexChanged.connect(lambda _: self._emit_changed())
        self.dir_label = QLabel("Direction")
        form.addRow(self.dir_label, self.dir_combo)

        layout.addLayout(form)
        self._update_field_visibility()

    def _emit_changed(self) -> None:
        if not self._updating:
            self.effectChanged.emit()

    def _on_effect_type_changed(self) -> None:
        eid = self.effect_combo.currentData()
        self._updating = True
        if eid == EFFECT_RIPPLE:
            self.period_slider.setRange(2, 200)
            if self.period_slider.value() > 200:
                self.period_slider.setValue(20)
            self.period_label.setText("Ripple Speed")
        else:
            self.period_slider.setRange(500, 15000)
            if self.period_slider.value() < 500:
                self.period_slider.setValue(5000)
            self.period_label.setText("Cycle Period")
        self._updating = False
        self._update_period_label()
        self._update_field_visibility()
        self._emit_changed()

    def _update_period_label(self) -> None:
        eid = self.effect_combo.currentData()
        val = self.period_slider.value()
        if eid == EFFECT_RIPPLE:
            self.period_val_lbl.setText(f"{val}")
        else:
            self.period_val_lbl.setText(f"{val / 1000.0:.1f} s")

    def _on_period_changed(self, _v: int) -> None:
        self._update_period_label()
        self._emit_changed()

    def _on_intensity_changed(self, v: int) -> None:
        self.intensity_val_lbl.setText(f"{v}%")
        self._emit_changed()

    def _on_sat_changed(self, v: int) -> None:
        self.sat_val_lbl.setText(f"{int(round(v * 100 / 255))}%")
        self._emit_changed()

    def _update_field_visibility(self) -> None:
        eid = self.effect_combo.currentData()
        show_color = eid in (EFFECT_STATIC, EFFECT_BREATHE, EFFECT_RIPPLE)
        show_period = eid in (EFFECT_BREATHE, EFFECT_CYCLE, EFFECT_WAVE, EFFECT_RIPPLE)
        show_intensity = eid in (EFFECT_BREATHE, EFFECT_CYCLE, EFFECT_WAVE)
        show_sat = eid in (EFFECT_CYCLE, EFFECT_WAVE, EFFECT_RIPPLE)
        show_dir = eid == EFFECT_WAVE

        for lbl, w, vis in [
            (self.color_label, self.color_row_widget, show_color),
            (self.period_label, self.period_row, show_period),
            (self.intensity_label, self.intensity_row, show_intensity),
            (self.sat_label, self.sat_row, show_sat),
            (self.dir_label, self.dir_combo, show_dir),
        ]:
            lbl.setVisible(vis)
            w.setVisible(vis)

    def get_effect(self) -> LedEffect:
        eid = int(self.effect_combo.currentData())
        return LedEffect(
            effect_id=eid,
            color=self.color_btn.color,
            period=self.period_slider.value(),
            intensity=self.intensity_slider.value(),
            saturation=self.sat_slider.value(),
            direction=int(self.dir_combo.currentData() or 1),
            ramp=2,
            form=1,
        )

    def set_effect(self, effect: LedEffect) -> None:
        self._updating = True
        idx = self.effect_combo.findData(effect.effect_id)
        if idx >= 0:
            self.effect_combo.setCurrentIndex(idx)
        else:
            # Unknown / factory effect — fall back to Aurora Playful if present, else Static
            idx = self.effect_combo.findData(EFFECT_AURORA_PLAYFUL)
            if idx >= 0:
                self.effect_combo.setCurrentIndex(idx)
        self.color_btn.set_color(effect.color, emit=False)
        if effect.effect_id == EFFECT_RIPPLE:
            self.period_slider.setRange(2, 200)
            self.period_slider.setValue(max(2, min(200, effect.period)))
            self.period_label.setText("Ripple Speed")
        else:
            self.period_slider.setRange(500, 15000)
            self.period_slider.setValue(max(500, min(15000, effect.period)))
            self.period_label.setText("Cycle Period")
        self.intensity_slider.setValue(max(10, min(100, effect.intensity)))
        self.intensity_val_lbl.setText(f"{self.intensity_slider.value()}%")
        self.sat_slider.setValue(max(0, min(255, effect.saturation)))
        self.sat_val_lbl.setText(f"{int(round(self.sat_slider.value() * 100 / 255))}%")
        didx = self.dir_combo.findData(effect.direction)
        if didx >= 0:
            self.dir_combo.setCurrentIndex(didx)
        self._updating = False
        self._update_period_label()
        self._update_field_visibility()
