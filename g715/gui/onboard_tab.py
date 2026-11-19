"""Onboard Memory Lighting tab — edit and permanently flash colors & effects to 0x8100."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..hidpp import HidppError
from ..presets import (
    BUILTIN_ONBOARD_PRESETS,
    delete_user_onboard_preset,
    load_user_onboard_presets,
    save_user_onboard_preset,
)
from ..protocol import (
    EFFECT_AURORA_PLAYFUL,
    EFFECT_AURORA_PLAYFUL_DIM,
    EFFECT_BREATHE,
    EFFECT_OFF,
    EFFECT_RIPPLE,
    EFFECT_STATIC,
    G715Device,
    LedEffect,
    OnboardProfileData,
    dim_color,
)
from .keyboard_widget import G715KeyboardWidget
from .widgets import ColorSwatchButton, EffectEditorWidget


class OnboardMemoryTab(QWidget):
    """Primary tab for editing & flashing the G715's onboard memory lighting profile."""

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
        self._profile: Optional[OnboardProfileData] = None
        self._syncing_ui = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(14)

        # --- Top Interactive Preview ---
        preview_card = QFrame()
        preview_card.setObjectName("Card")
        pv_lay = QVBoxLayout(preview_card)
        pv_lay.setContentsMargins(14, 10, 14, 10)
        pv_lay.setSpacing(6)

        pv_header = QHBoxLayout()
        pv_title = QLabel("Onboard Profile Visual Preview")
        pv_title.setObjectName("CardTitle")
        self.preview_state_combo = QComboBox()
        self.preview_state_combo.addItems(["Active Lighting", "Idle / Dimmed Lighting"])
        self.preview_state_combo.currentIndexChanged.connect(self._update_preview)
        pv_header.addWidget(pv_title)
        pv_header.addStretch()
        pv_header.addWidget(QLabel("Previewing:"))
        pv_header.addWidget(self.preview_state_combo)
        pv_lay.addLayout(pv_header)

        self.preview_widget = G715KeyboardWidget(interactive=False)
        pv_lay.addWidget(self.preview_widget)
        root.addWidget(preview_card)

        # --- Preset Selector Strip ---
        preset_card = QFrame()
        preset_card.setObjectName("Card")
        pr_lay = QHBoxLayout(preset_card)
        pr_lay.setContentsMargins(14, 10, 14, 10)
        pr_lay.setSpacing(10)

        pr_lay.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(240)
        self._reload_preset_list()
        pr_lay.addWidget(self.preset_combo, stretch=1)

        btn_load_preset = QPushButton("Load Preset")
        btn_load_preset.clicked.connect(self._apply_selected_preset)
        btn_save_preset = QPushButton("Save Current as Preset")
        btn_save_preset.clicked.connect(self._save_current_preset)
        btn_del_preset = QPushButton("Delete")
        btn_del_preset.clicked.connect(self._delete_selected_preset)
        pr_lay.addWidget(btn_load_preset)
        pr_lay.addWidget(btn_save_preset)
        pr_lay.addWidget(btn_del_preset)
        root.addWidget(preset_card)

        # --- Dual Zone Editors: Keys (Zone 0) + Perimeter Underglow (Zone 1) ---
        zones_row = QHBoxLayout()
        zones_row.setSpacing(14)

        self.keys_editor = EffectEditorWidget("Keys Backlight", allow_ripple=True, allow_factory=False)
        self.keys_editor.effectChanged.connect(self._on_keys_changed)

        self.perim_editor = EffectEditorWidget("Perimeter Underglow — 16 LEDs", allow_ripple=False, allow_factory=True)
        self.perim_editor.effectChanged.connect(self._on_perim_changed)

        self.sync_perim_cb = QCheckBox("Sync Perimeter color && effect with Keys")
        self.sync_perim_cb.toggled.connect(self._on_sync_toggled)
        self.perim_editor.layout().addWidget(self.sync_perim_cb)

        zones_row.addWidget(self.keys_editor, stretch=1)
        zones_row.addWidget(self.perim_editor, stretch=1)
        root.addLayout(zones_row)

        # --- Idle / Dimmed Power-Save Lighting Card ---
        dim_card = QFrame()
        dim_card.setObjectName("Card")
        dim_lay = QVBoxLayout(dim_card)
        dim_lay.setContentsMargins(16, 12, 16, 12)
        dim_lay.setSpacing(10)

        dim_top = QHBoxLayout()
        dim_title = QLabel("Idle / Power-Save Dimmed Colors (Saved to Flash)")
        dim_title.setObjectName("CardTitle")
        self.auto_dim_cb = QCheckBox("Auto-dim from active colors")
        self.auto_dim_cb.setChecked(True)
        self.auto_dim_cb.toggled.connect(self._on_auto_dim_toggled)
        dim_top.addWidget(dim_title)
        dim_top.addStretch()
        dim_top.addWidget(self.auto_dim_cb)
        dim_lay.addLayout(dim_top)

        # Auto dim percentage slider
        self.auto_dim_row = QWidget()
        ad_h = QHBoxLayout(self.auto_dim_row)
        ad_h.setContentsMargins(0, 0, 0, 0)
        ad_h.addWidget(QLabel("Dim Brightness:"))
        self.dim_pct_slider = QSlider(Qt.Orientation.Horizontal)
        self.dim_pct_slider.setRange(0, 90)
        self.dim_pct_slider.setValue(45)
        self.dim_pct_slider.valueChanged.connect(self._on_dim_pct_changed)
        self.dim_pct_lbl = QLabel("45%")
        self.dim_pct_lbl.setMinimumWidth(42)
        ad_h.addWidget(self.dim_pct_slider)
        ad_h.addWidget(self.dim_pct_lbl)
        dim_lay.addWidget(self.auto_dim_row)

        # Manual dim pickers
        self.manual_dim_row = QWidget()
        md_h = QHBoxLayout(self.manual_dim_row)
        md_h.setContentsMargins(0, 0, 0, 0)
        md_h.setSpacing(16)
        md_h.addWidget(QLabel("Dimmed Keys Color:"))
        self.keys_dim_btn = ColorSwatchButton(0x7A297F)
        self.keys_dim_btn.colorChanged.connect(lambda _: self._update_preview())
        md_h.addWidget(self.keys_dim_btn)
        md_h.addWidget(QLabel("Dimmed Perimeter Color:"))
        self.perim_dim_btn = ColorSwatchButton(0x7A297F)
        self.perim_dim_btn.colorChanged.connect(lambda _: self._update_preview())
        md_h.addWidget(self.perim_dim_btn)
        md_h.addStretch()
        self.manual_dim_row.setVisible(False)
        dim_lay.addWidget(self.manual_dim_row)

        root.addWidget(dim_card)

        # --- Sticky Bottom Action Bar (always visible outside scroll area) ---
        footer_bar = QFrame()
        footer_bar.setObjectName("HeaderBar")
        actions = QHBoxLayout(footer_bar)
        actions.setContentsMargins(16, 10, 16, 10)
        actions.setSpacing(12)

        self.btn_reload = QPushButton("Reload from Keyboard")
        self.btn_reload.setMinimumHeight(40)
        self.btn_reload.clicked.connect(self.load_from_device)

        self.btn_preview_live = QPushButton("Live Preview (RAM Only)")
        self.btn_preview_live.setMinimumHeight(40)
        self.btn_preview_live.setToolTip("Test these colors/effects live on the keyboard without writing to flash")
        self.btn_preview_live.clicked.connect(self._preview_live_on_hardware)

        self.btn_save_flash = QPushButton("Save to Onboard Memory (Flash)")
        self.btn_save_flash.setObjectName("PrimaryButton")
        self.btn_save_flash.setMinimumHeight(40)
        self.btn_save_flash.setToolTip("Write CRC-verified profile to Sector 0x0001 — persists across reboots & OSes!")
        self.btn_save_flash.clicked.connect(self._save_to_flash)

        actions.addWidget(self.btn_reload)
        actions.addStretch()
        actions.addWidget(self.btn_preview_live)
        actions.addWidget(self.btn_save_flash)
        outer.addWidget(footer_bar)

        self._update_preview()

    def _reload_preset_list(self) -> None:
        cur = self.preset_combo.currentText()
        self.preset_combo.clear()
        user_presets = load_user_onboard_presets()
        for name in BUILTIN_ONBOARD_PRESETS:
            self.preset_combo.addItem(name, ("builtin", name))
        if user_presets:
            self.preset_combo.insertSeparator(self.preset_combo.count())
            for name in user_presets:
                self.preset_combo.addItem(f"★ {name}", ("user", name))
        idx = self.preset_combo.findText(cur)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)

    def load_from_device(self) -> None:
        dev = self._get_device()
        if dev is None:
            return
        try:
            self._profile = dev.read_onboard_profile(1)
        except HidppError as e:
            self._notify(f"Failed to read onboard profile: {e}", True)
            return

        self._syncing_ui = True
        self.keys_editor.set_effect(self._profile.keys_active)
        self.perim_editor.set_effect(self._profile.perimeter_active)
        self.keys_dim_btn.set_color(self._profile.keys_dim.color)
        self.perim_dim_btn.set_color(self._profile.perimeter_dim.color)
        same_active = self._profile.keys_active.to_bytes() == self._profile.perimeter_active.to_bytes()
        self.sync_perim_cb.setChecked(same_active)
        self._syncing_ui = False
        self._update_preview()
        self._notify(f"Loaded onboard profile '{self._profile.name}' from Sector 0x0001.", False)

    def _compute_dim_effects(self, keys_eff: LedEffect, perim_eff: LedEffect) -> tuple[LedEffect, LedEffect]:
        if not self.auto_dim_cb.isChecked():
            return (
                LedEffect(EFFECT_STATIC, color=self.keys_dim_btn.color),
                LedEffect(EFFECT_STATIC, color=self.perim_dim_btn.color),
            )
        factor = self.dim_pct_slider.value() / 100.0
        if factor <= 0.01:
            return LedEffect(EFFECT_OFF), LedEffect(EFFECT_OFF)

        def make_dim(eff: LedEffect) -> LedEffect:
            if eff.effect_id == EFFECT_AURORA_PLAYFUL:
                return LedEffect(EFFECT_AURORA_PLAYFUL_DIM)
            if eff.effect_id in (EFFECT_STATIC, EFFECT_BREATHE, EFFECT_RIPPLE):
                return LedEffect(
                    effect_id=eff.effect_id,
                    color=dim_color(eff.color, factor),
                    period=eff.period,
                    intensity=max(10, int(eff.intensity * factor)),
                    saturation=eff.saturation,
                    direction=eff.direction,
                )
            return LedEffect(
                effect_id=eff.effect_id,
                color=dim_color(eff.color, factor),
                period=eff.period,
                intensity=max(10, int(eff.intensity * factor)),
                saturation=eff.saturation,
                direction=eff.direction,
            )

        return make_dim(keys_eff), make_dim(perim_eff)

    def _on_keys_changed(self) -> None:
        if self._syncing_ui:
            return
        if self.sync_perim_cb.isChecked():
            ke = self.keys_editor.get_effect()
            if ke.effect_id not in (EFFECT_RIPPLE, EFFECT_AURORA_PLAYFUL):
                self._syncing_ui = True
                self.perim_editor.set_effect(ke)
                self._syncing_ui = False
        self._update_preview()

    def _on_perim_changed(self) -> None:
        if self._syncing_ui:
            return
        if self.sync_perim_cb.isChecked():
            self._syncing_ui = True
            self.sync_perim_cb.setChecked(False)
            self._syncing_ui = False
        self._update_preview()

    def _on_sync_toggled(self, checked: bool) -> None:
        if checked and not self._syncing_ui:
            ke = self.keys_editor.get_effect()
            if ke.effect_id in (EFFECT_RIPPLE, EFFECT_AURORA_PLAYFUL):
                ke = LedEffect(EFFECT_STATIC, color=ke.color)
            self._syncing_ui = True
            self.perim_editor.set_effect(ke)
            self._syncing_ui = False
            self._update_preview()

    def _on_auto_dim_toggled(self, checked: bool) -> None:
        self.auto_dim_row.setVisible(checked)
        self.manual_dim_row.setVisible(not checked)
        if not checked:
            ke = self.keys_editor.get_effect()
            pe = self.perim_editor.get_effect()
            kd, pd = self._compute_dim_effects(ke, pe)
            self.keys_dim_btn.set_color(kd.color)
            self.perim_dim_btn.set_color(pd.color)
        self._update_preview()

    def _on_dim_pct_changed(self, v: int) -> None:
        self.dim_pct_lbl.setText("Off" if v == 0 else f"{v}%")
        self._update_preview()

    def _update_preview(self) -> None:
        ke = self.keys_editor.get_effect()
        pe = self.perim_editor.get_effect()
        if self.preview_state_combo.currentIndex() == 1:
            ke, pe = self._compute_dim_effects(ke, pe)
        self.preview_widget.set_preview_effects(ke, pe)

    def _apply_selected_preset(self) -> None:
        data = self.preset_combo.currentData()
        if not data:
            return
        kind, name = data
        src = BUILTIN_ONBOARD_PRESETS if kind == "builtin" else load_user_onboard_presets()
        if name not in src:
            return
        p = src[name]
        self._syncing_ui = True
        self.sync_perim_cb.setChecked(False)
        self.keys_editor.set_effect(LedEffect.from_dict(p["keys_active"]))
        self.perim_editor.set_effect(LedEffect.from_dict(p["perimeter_active"]))
        kd = LedEffect.from_dict(p["keys_dim"])
        pd = LedEffect.from_dict(p["perimeter_dim"])
        self.keys_dim_btn.set_color(kd.color)
        self.perim_dim_btn.set_color(pd.color)
        self._syncing_ui = False
        self._update_preview()
        self._notify(f"Loaded preset '{name}' into editor. Click 'Save to Onboard Memory' to flash it.", False)

    def _save_current_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Onboard Preset", "Preset name:")
        if not ok or not name.strip():
            return
        ke = self.keys_editor.get_effect()
        pe = self.perim_editor.get_effect()
        kd, pd = self._compute_dim_effects(ke, pe)
        save_user_onboard_preset(
            name.strip(),
            {
                "keys_active": ke.to_dict(),
                "perimeter_active": pe.to_dict(),
                "keys_dim": kd.to_dict(),
                "perimeter_dim": pd.to_dict(),
            },
        )
        self._reload_preset_list()
        self._notify(f"Saved preset '{name.strip()}'.", False)

    def _delete_selected_preset(self) -> None:
        data = self.preset_combo.currentData()
        if not data or data[0] != "user":
            QMessageBox.information(self, "Delete Preset", "Built-in presets cannot be deleted. Select a saved (★) preset.")
            return
        delete_user_onboard_preset(data[1])
        self._reload_preset_list()
        self._notify(f"Deleted preset '{data[1]}'.", False)

    def _preview_live_on_hardware(self) -> None:
        dev = self._get_device()
        if dev is None:
            self._notify("No G715 connected.", True)
            return
        ke = self.keys_editor.get_effect()
        pe = self.perim_editor.get_effect()
        if ke.effect_id == EFFECT_AURORA_PLAYFUL or pe.effect_id == EFFECT_AURORA_PLAYFUL:
            self._notify("Aurora Playful is a ROM preset — use 'Save to Onboard Memory' to view it.", False)
            return
        try:
            dev.claim_sw_control()
            dev.set_live_zone_effect(0, ke)
            dev.set_live_zone_effect(1, pe)
            self._refresh_header()
            self._notify("Live preview active (RAM only — flash not modified yet).", False)
        except HidppError as e:
            self._notify(f"Live preview failed: {e}", True)

    def _save_to_flash(self) -> None:
        dev = self._get_device()
        if dev is None:
            self._notify("No G715 connected.", True)
            return
        try:
            prof = dev.read_onboard_profile(1)
            ke = self.keys_editor.get_effect()
            pe = self.perim_editor.get_effect()
            kd, pd = self._compute_dim_effects(ke, pe)
            prof.keys_active = ke
            prof.perimeter_active = pe
            prof.keys_dim = kd
            prof.perimeter_dim = pd
            dev.write_onboard_profile(prof, activate=True)
            self._profile = prof
            self._refresh_header()
            self._notify("Saved to onboard flash memory (Sector 0x0001) & verified CRC!", False)
        except (HidppError, ValueError) as e:
            self._notify(f"Flash save failed: {e}", True)
