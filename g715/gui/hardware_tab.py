"""Hardware settings, startup/shutdown NvConfig animations, F1-F12 bindings, and backups."""

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
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..hidpp import HidppError
from ..presets import list_backups, load_backup, save_backup
from ..protocol import (
    BootAnimation,
    CONSUMER_KEYS,
    G715Device,
    KeyBinding,
    MODIFIER_BITS,
    OnboardProfileData,
    USB_HID_KEYS,
)
from .widgets import ColorSwatchButton


class BindingEditDialog(QDialog):
    """Dialog to edit a single F1-F12 or G-Shift onboard keybinding."""

    def __init__(self, slot_label: str, binding: KeyBinding, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Onboard Binding — {slot_label}")
        self.setMinimumWidth(380)
        self._orig = binding

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Keyboard Key (+ Modifiers)", "key")
        self.kind_combo.addItem("Media / Consumer Action", "consumer")
        self.kind_combo.addItem("Disabled (No Action)", "disabled")
        idx = self.kind_combo.findData(binding.kind)
        if idx >= 0:
            self.kind_combo.setCurrentIndex(idx)
        self.kind_combo.currentIndexChanged.connect(self._update_vis)
        form.addRow("Binding Type:", self.kind_combo)

        # Keyboard key picker
        self.key_combo = QComboBox()
        for code, name in sorted(USB_HID_KEYS.items(), key=lambda kv: kv[0]):
            self.key_combo.addItem(f"{name} (0x{code:02X})", code)
        kidx = self.key_combo.findData(binding.keycode if binding.kind == "key" else 0x3A)
        if kidx >= 0:
            self.key_combo.setCurrentIndex(kidx)
        self.key_lbl = QLabel("Key:")
        form.addRow(self.key_lbl, self.key_combo)

        # Modifiers checkboxes
        self.mod_widget = QWidget()
        mod_grid = QGridLayout(self.mod_widget)
        mod_grid.setContentsMargins(0, 0, 0, 0)
        self.mod_cbs: list[tuple[int, QCheckBox]] = []
        for i, (bit, name) in enumerate(MODIFIER_BITS[:4]):  # LCtrl, LShift, LAlt, LSuper
            cb = QCheckBox(name)
            cb.setChecked(bool(binding.modifiers & bit) if binding.kind == "key" else False)
            mod_grid.addWidget(cb, i // 2, i % 2)
            self.mod_cbs.append((bit, cb))
        self.mod_lbl = QLabel("Modifiers:")
        form.addRow(self.mod_lbl, self.mod_widget)

        # Consumer key picker
        self.cons_combo = QComboBox()
        for code, name in sorted(CONSUMER_KEYS.items(), key=lambda kv: kv[1]):
            self.cons_combo.addItem(f"{name} (0x{code:04X})", code)
        cidx = self.cons_combo.findData(binding.keycode if binding.kind == "consumer" else 0x00CD)
        if cidx >= 0:
            self.cons_combo.setCurrentIndex(cidx)
        self.cons_lbl = QLabel("Media Action:")
        form.addRow(self.cons_lbl, self.cons_combo)

        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._update_vis()

    def _update_vis(self) -> None:
        k = self.kind_combo.currentData()
        is_key = k == "key"
        is_cons = k == "consumer"
        self.key_lbl.setVisible(is_key)
        self.key_combo.setVisible(is_key)
        self.mod_lbl.setVisible(is_key)
        self.mod_widget.setVisible(is_key)
        self.cons_lbl.setVisible(is_cons)
        self.cons_combo.setVisible(is_cons)

    def result_binding(self) -> KeyBinding:
        k = self.kind_combo.currentData()
        if k == "disabled":
            return KeyBinding(kind="disabled")
        if k == "consumer":
            return KeyBinding(kind="consumer", keycode=int(self.cons_combo.currentData()))
        mods = 0
        for bit, cb in self.mod_cbs:
            if cb.isChecked():
                mods |= bit
        return KeyBinding(kind="key", modifiers=mods, keycode=int(self.key_combo.currentData()))


class HardwareTab(QWidget):
    """Hardware settings, persistent boot animations, F1-F12 remapper, and backup manager."""

    def __init__(
        self,
        get_device: Callable[[], Optional[G715Device]],
        notify: Callable[[str, bool], None],
        refresh_all: Callable[[], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._get_device = get_device
        self._notify = notify
        self._refresh_all = refresh_all
        self._profile: Optional[OnboardProfileData] = None
        self._f_keys: list[KeyBinding] = [KeyBinding(kind="key", modifiers=0, keycode=0x3A + i) for i in range(12)]
        self._g_keys: list[KeyBinding] = [KeyBinding(kind="key", modifiers=0, keycode=0x3A + i) for i in range(12)]
        self._syncing = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        root = QVBoxLayout(container)
        root.setContentsMargins(16, 14, 16, 16)
        root.setSpacing(14)

        # --- Top Row: Device Controls + Persistent Boot/Shutdown Animations ---
        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        # Card 1: Hardware & Timers
        hw_card = QFrame()
        hw_card.setObjectName("Card")
        hw_lay = QVBoxLayout(hw_card)
        hw_lay.setContentsMargins(16, 14, 16, 14)
        hw_lay.setSpacing(10)

        hw_title = QLabel("Hardware Controls & Power Timers")
        hw_title.setObjectName("CardTitle")
        hw_lay.addWidget(hw_title)

        hw_form = QFormLayout()
        hw_form.setSpacing(10)

        # Brightness slider (instant via 0x8040)
        bri_w = QWidget()
        bri_h = QHBoxLayout(bri_w)
        bri_h.setContentsMargins(0, 0, 0, 0)
        self.bri_slider = QSlider(Qt.Orientation.Horizontal)
        self.bri_slider.setRange(0, 100)
        self.bri_slider.setValue(100)
        self.bri_slider.sliderReleased.connect(self._apply_brightness)
        self.bri_slider.valueChanged.connect(lambda v: self.bri_lbl.setText(f"{v}%"))
        self.bri_lbl = QLabel("100%")
        self.bri_lbl.setMinimumWidth(40)
        bri_h.addWidget(self.bri_slider)
        bri_h.addWidget(self.bri_lbl)
        hw_form.addRow("LED Brightness:", bri_w)

        # Polling rate
        self.rate_combo = QComboBox()
        for hz, ms in [(1000, 1), (500, 2), (250, 4), (125, 8)]:
            self.rate_combo.addItem(f"{hz} Hz ({ms} ms)", ms)
        hw_form.addRow("Polling Rate:", self.rate_combo)

        # Profile Name
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(24)
        self.name_edit.setPlaceholderText("Onboard profile name (max 24 chars)")
        hw_form.addRow("Profile Name:", self.name_edit)

        # Dim & Sleep Timeouts
        self.dim_spin = QSpinBox()
        self.dim_spin.setRange(0, 3600)
        self.dim_spin.setSuffix(" sec  (0 = disabled)")
        hw_form.addRow("Idle Dim Timeout:", self.dim_spin)

        self.sleep_spin = QSpinBox()
        self.sleep_spin.setRange(0, 7200)
        self.sleep_spin.setSuffix(" sec  (0 = disabled)")
        hw_form.addRow("Sleep Timeout:", self.sleep_spin)

        hw_lay.addLayout(hw_form)

        hw_btns = QHBoxLayout()
        btn_save_hw = QPushButton("Save Hardware Settings to Flash")
        btn_save_hw.setObjectName("PrimaryButton")
        btn_save_hw.clicked.connect(self._save_hardware_settings)
        hw_btns.addStretch()
        hw_btns.addWidget(btn_save_hw)
        hw_lay.addLayout(hw_btns)
        top_row.addWidget(hw_card, stretch=1)

        # Card 2: Persistent Startup & Shutdown Animations (0x8071 NvConfig)
        boot_card = QFrame()
        boot_card.setObjectName("Card")
        boot_lay = QVBoxLayout(boot_card)
        boot_lay.setContentsMargins(16, 14, 16, 14)
        boot_lay.setSpacing(10)

        boot_title = QLabel("Startup & Shutdown Animations (NvConfig Flash)")
        boot_title.setObjectName("CardTitle")
        boot_lay.addWidget(boot_title)

        boot_sub = QLabel("Plays automatically on power-on / wake / power-off — stored in hardware flash.")
        boot_sub.setStyleSheet("color: #94A3B8; font-size: 12px;")
        boot_sub.setWordWrap(True)
        boot_lay.addWidget(boot_sub)

        # Startup row
        self.startup_cb = QCheckBox("Enable Startup / Wake Animation")
        self.startup_cb.setChecked(True)
        boot_lay.addWidget(self.startup_cb)
        st_row = QHBoxLayout()
        st_row.addWidget(QLabel("Primary:"))
        self.startup_c1 = ColorSwatchButton(0xFF8DAA)
        st_row.addWidget(self.startup_c1)
        st_row.addWidget(QLabel("Secondary:"))
        self.startup_c2 = ColorSwatchButton(0x8BE4E9)
        st_row.addWidget(self.startup_c2)
        st_row.addStretch()
        boot_lay.addLayout(st_row)

        # Shutdown row
        self.shutdown_cb = QCheckBox("Enable Shutdown Animation")
        self.shutdown_cb.setChecked(True)
        boot_lay.addWidget(self.shutdown_cb)
        sd_row = QHBoxLayout()
        sd_row.addWidget(QLabel("Primary:"))
        self.shutdown_c1 = ColorSwatchButton(0xFE8385)
        sd_row.addWidget(self.shutdown_c1)
        sd_row.addWidget(QLabel("Secondary:"))
        self.shutdown_c2 = ColorSwatchButton(0xCBE8CE)
        sd_row.addWidget(self.shutdown_c2)
        sd_row.addStretch()
        boot_lay.addLayout(sd_row)

        boot_lay.addStretch()
        boot_btns = QHBoxLayout()
        btn_save_boot = QPushButton("Save Boot Animations to Flash")
        btn_save_boot.setObjectName("PrimaryButton")
        btn_save_boot.clicked.connect(self._save_boot_animations)
        boot_btns.addStretch()
        boot_btns.addWidget(btn_save_boot)
        boot_lay.addLayout(boot_btns)
        top_row.addWidget(boot_card, stretch=1)

        root.addLayout(top_row)

        # --- Bottom Row: F1-F12 Bindings + Flash Backups ---
        bot_row = QHBoxLayout()
        bot_row.setSpacing(14)

        # Card 3: F1-F12 & G-Shift Bindings
        bind_card = QFrame()
        bind_card.setObjectName("Card")
        bind_lay = QVBoxLayout(bind_card)
        bind_lay.setContentsMargins(16, 14, 16, 14)
        bind_lay.setSpacing(10)

        bh = QHBoxLayout()
        bt = QLabel("F1–F12 Onboard Keybindings")
        bt.setObjectName("CardTitle")
        self.layer_combo = QComboBox()
        self.layer_combo.addItems(["Primary Layer (F1–F12)", "G-Shift Layer (Fn + F1–F12)"])
        self.layer_combo.currentIndexChanged.connect(self._populate_bindings_table)
        bh.addWidget(bt)
        bh.addStretch()
        bh.addWidget(self.layer_combo)
        bind_lay.addLayout(bh)

        self.bind_table = QTableWidget(12, 3)
        self.bind_table.setHorizontalHeaderLabels(["Key", "Assigned Action", ""])
        self.bind_table.verticalHeader().setVisible(False)
        self.bind_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.bind_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.bind_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.bind_table.setMinimumHeight(240)
        bind_lay.addWidget(self.bind_table)

        bb = QHBoxLayout()
        btn_reset_keys = QPushButton("Reset F1–F12 Defaults")
        btn_reset_keys.clicked.connect(self._reset_f_keys)
        btn_save_keys = QPushButton("Save Bindings to Flash")
        btn_save_keys.setObjectName("PrimaryButton")
        btn_save_keys.clicked.connect(self._save_bindings)
        bb.addWidget(btn_reset_keys)
        bb.addStretch()
        bb.addWidget(btn_save_keys)
        bind_lay.addLayout(bb)
        bot_row.addWidget(bind_card, stretch=3)

        # Card 4: Flash Backups & Factory Reset
        bk_card = QFrame()
        bk_card.setObjectName("Card")
        bk_lay = QVBoxLayout(bk_card)
        bk_lay.setContentsMargins(16, 14, 16, 14)
        bk_lay.setSpacing(10)

        bkt = QLabel("Flash Memory Backups & Safety")
        bkt.setObjectName("CardTitle")
        bk_lay.addWidget(bkt)

        self.backup_list = QListWidget()
        self.backup_list.setMinimumHeight(190)
        bk_lay.addWidget(self.backup_list)

        btn_create_bk = QPushButton("Create Backup Snapshot Now")
        btn_create_bk.clicked.connect(self._create_backup)
        btn_restore_bk = QPushButton("Restore Selected Backup to Flash")
        btn_restore_bk.clicked.connect(self._restore_backup)
        btn_factory = QPushButton("Factory Reset Profile from ROM (0x0101)")
        btn_factory.setObjectName("DangerButton")
        btn_factory.clicked.connect(self._factory_reset)

        bk_lay.addWidget(btn_create_bk)
        bk_lay.addWidget(btn_restore_bk)
        bk_lay.addWidget(btn_factory)
        bot_row.addWidget(bk_card, stretch=2)

        root.addLayout(bot_row)

        self._populate_bindings_table()
        self._reload_backups()

    def load_from_device(self) -> None:
        dev = self._get_device()
        if dev is None:
            return
        try:
            self._syncing = True
            self._profile = dev.read_onboard_profile(1)
            bri = dev.get_brightness()
            rate = dev.get_report_rate()
            startup = dev.get_boot_animation("startup")
            shutdown = dev.get_boot_animation("shutdown")

            self.bri_slider.setValue(bri)
            self.bri_lbl.setText(f"{bri}%")
            ridx = self.rate_combo.findData(rate)
            if ridx >= 0:
                self.rate_combo.setCurrentIndex(ridx)
            self.name_edit.setText(self._profile.name)
            self.dim_spin.setValue(0 if self._profile.ps_timeout_s == 0xFFFF else self._profile.ps_timeout_s)
            self.sleep_spin.setValue(0 if self._profile.po_timeout_s == 0xFFFF else self._profile.po_timeout_s)

            self.startup_cb.setChecked(startup.enabled)
            self.startup_c1.set_color(startup.color1)
            self.startup_c2.set_color(startup.color2)
            self.shutdown_cb.setChecked(shutdown.enabled)
            self.shutdown_c1.set_color(shutdown.color1)
            self.shutdown_c2.set_color(shutdown.color2)

            self._f_keys = list(self._profile.f_keys)
            self._g_keys = list(self._profile.g_shift_keys)
            self._syncing = False
            self._populate_bindings_table()
            self._reload_backups()
        except HidppError as e:
            self._syncing = False
            self._notify(f"Failed reading hardware settings: {e}", True)

    def _populate_bindings_table(self) -> None:
        layer = self._f_keys if self.layer_combo.currentIndex() == 0 else self._g_keys
        prefix = "F" if self.layer_combo.currentIndex() == 0 else "Fn+F"
        for i in range(12):
            key_item = QTableWidgetItem(f"{prefix}{i + 1}")
            key_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            val_item = QTableWidgetItem(layer[i].describe())
            val_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.bind_table.setItem(i, 0, key_item)
            self.bind_table.setItem(i, 1, val_item)
            btn = QPushButton("Edit")
            btn.clicked.connect(lambda _c=False, idx=i: self._edit_binding(idx))
            self.bind_table.setCellWidget(i, 2, btn)

    def _edit_binding(self, idx: int) -> None:
        is_primary = self.layer_combo.currentIndex() == 0
        layer = self._f_keys if is_primary else self._g_keys
        label = f"F{idx + 1}" if is_primary else f"G-Shift F{idx + 1}"
        dlg = BindingEditDialog(label, layer[idx], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            layer[idx] = dlg.result_binding()
            self._populate_bindings_table()

    def _reset_f_keys(self) -> None:
        defaults = [KeyBinding(kind="key", modifiers=0, keycode=0x3A + i) for i in range(12)]
        if self.layer_combo.currentIndex() == 0:
            self._f_keys = defaults
        else:
            self._g_keys = defaults
        self._populate_bindings_table()
        self._notify("Reset F1–F12 bindings in editor. Click 'Save Bindings to Flash' to persist.", False)

    def _apply_brightness(self) -> None:
        if self._syncing:
            return
        dev = self._get_device()
        if dev is None:
            return
        try:
            dev.set_brightness(self.bri_slider.value())
            self._notify(f"Brightness set to {self.bri_slider.value()}%.", False)
        except HidppError as e:
            self._notify(f"Failed setting brightness: {e}", True)

    def _save_hardware_settings(self) -> None:
        dev = self._get_device()
        if dev is None:
            self._notify("No G715 connected.", True)
            return
        try:
            ms = int(self.rate_combo.currentData())
            dev.set_brightness(self.bri_slider.value())
            dev.set_report_rate(ms)
            prof = dev.read_onboard_profile(1)
            prof.report_rate_ms = ms
            prof.name = self.name_edit.text().strip()[:24] or "G715_CUSTOM"
            prof.ps_timeout_s = 0xFFFF if self.dim_spin.value() == 0 else self.dim_spin.value()
            prof.po_timeout_s = 0xFFFF if self.sleep_spin.value() == 0 else self.sleep_spin.value()
            dev.write_onboard_profile(prof, activate=True)
            self._profile = prof
            self._refresh_all()
            self._notify("Saved hardware settings & power timers to onboard flash!", False)
        except HidppError as e:
            self._notify(f"Failed saving hardware settings: {e}", True)

    def _save_boot_animations(self) -> None:
        dev = self._get_device()
        if dev is None:
            self._notify("No G715 connected.", True)
            return
        try:
            dev.set_boot_animation(
                BootAnimation("startup", self.startup_cb.isChecked(), self.startup_c1.color, self.startup_c2.color)
            )
            dev.set_boot_animation(
                BootAnimation("shutdown", self.shutdown_cb.isChecked(), self.shutdown_c1.color, self.shutdown_c2.color)
            )
            self._notify("Saved startup & shutdown animations to persistent NvConfig flash!", False)
        except HidppError as e:
            self._notify(f"Failed saving boot animations: {e}", True)

    def _save_bindings(self) -> None:
        dev = self._get_device()
        if dev is None:
            self._notify("No G715 connected.", True)
            return
        try:
            prof = dev.read_onboard_profile(1)
            prof.f_keys = list(self._f_keys)
            prof.g_shift_keys = list(self._g_keys)
            dev.write_onboard_profile(prof, activate=True)
            self._profile = prof
            self._notify("Saved F1–F12 & G-Shift keybindings to onboard flash!", False)
        except HidppError as e:
            self._notify(f"Failed saving bindings: {e}", True)

    def _reload_backups(self) -> None:
        self.backup_list.clear()
        for path in list_backups():
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.backup_list.addItem(item)

    def _create_backup(self) -> None:
        dev = self._get_device()
        if dev is None:
            self._notify("No G715 connected.", True)
            return
        label, ok = QInputDialog.getText(self, "Create Flash Backup", "Backup label:", text="snapshot")
        if not ok:
            return
        try:
            sectors = dev.dump_all_sectors()
            path = save_backup(sectors, label=label or "snapshot")
            self._reload_backups()
            self._notify(f"Saved backup to {path.name}", False)
        except HidppError as e:
            self._notify(f"Backup failed: {e}", True)

    def _restore_backup(self) -> None:
        dev = self._get_device()
        if dev is None:
            self._notify("No G715 connected.", True)
            return
        item = self.backup_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Restore Backup", "Select a backup snapshot from the list first.")
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        ans = QMessageBox.question(
            self,
            "Restore Flash Backup",
            f"Write onboard memory sectors from '{item.text()}' to your G715?",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            data = load_backup(path)
            dev.restore_sectors(data["sectors"])
            self._refresh_all()
            self._notify(f"Restored onboard flash from {item.text()}!", False)
        except (HidppError, OSError, KeyError) as e:
            self._notify(f"Restore failed: {e}", True)

    def _factory_reset(self) -> None:
        dev = self._get_device()
        if dev is None:
            self._notify("No G715 connected.", True)
            return
        ans = QMessageBox.warning(
            self,
            "Factory Reset Onboard Profile",
            "Reset Sector 0x0001 to the keyboard's built-in factory ROM defaults (Aurora Playful)?\n"
            "Your saved backups in ~/.local/share/g715-customizer/backups/ are untouched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            dev.restore_factory_profile_from_rom()
            self._refresh_all()
            self._notify("Restored factory ROM profile (0x0101) to onboard flash!", False)
        except HidppError as e:
            self._notify(f"Factory reset failed: {e}", True)
