"""Main PySide6 Qt6 application window for G715 Customizer."""

from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..hidpp import HidppError, discover_g715_devices
from ..protocol import G715Device
from .hardware_tab import HardwareTab
from .onboard_tab import OnboardMemoryTab
from .perkey_tab import PerKeyStudioTab

STYLESHEET = """
QMainWindow {
    background-color: #12141E;
    color: #E2E8F0;
    font-family: "Inter", "Noto Sans", "Segoe UI", sans-serif;
    font-size: 13px;
}

QWidget {
    color: #E2E8F0;
    font-family: "Inter", "Noto Sans", "Segoe UI", sans-serif;
    font-size: 13px;
}

QScrollArea, QScrollArea > QWidget > QWidget {
    background-color: #12141E;
}

QLabel, QCheckBox {
    background: transparent;
}

QScrollBar:vertical {
    background: #141724;
    width: 9px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #2D3450;
    border-radius: 4px;
    min-height: 28px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QFrame#HeaderBar {
    background-color: #181B29;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

QLabel#AppTitle {
    font-size: 18px;
    font-weight: 800;
    color: #F8FAFC;
    letter-spacing: 0.3px;
}

QLabel#Pill {
    background-color: #23283D;
    color: #CBD5E1;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 600;
}

QLabel#PillOk {
    background-color: rgba(107, 229, 245, 0.14);
    color: #6BE5F5;
    border: 1px solid rgba(107, 229, 245, 0.45);
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 700;
}

QLabel#PillWarn {
    background-color: rgba(255, 115, 185, 0.16);
    color: #FF8ACA;
    border: 1px solid rgba(255, 115, 185, 0.45);
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 700;
}

QFrame#Card {
    background-color: #1A1E2E;
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 12px;
}

QLabel#CardTitle {
    font-size: 14px;
    font-weight: 700;
    color: #F8FAFC;
}

QTabWidget::pane {
    border: none;
    background-color: #12141E;
}

QTabBar::tab {
    background-color: #181B29;
    color: #94A3B8;
    padding: 10px 22px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background-color: #23283D;
    color: #FFFFFF;
    border-bottom: 2px solid #FF73B9;
}

QTabBar::tab:hover:!selected {
    color: #E2E8F0;
    background-color: #1E2235;
}

QPushButton {
    background-color: #252A40;
    color: #F1F5F9;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #2F3652;
    border-color: rgba(255, 255, 255, 0.28);
}

QPushButton:pressed {
    background-color: #1E2336;
}

QPushButton#PrimaryButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #D946EF, stop:1 #38BDF8);
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 700;
}

QPushButton#PrimaryButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E879F9, stop:1 #67E8F9);
}

QPushButton#DangerButton {
    background-color: rgba(239, 68, 68, 0.18);
    color: #FCA5A5;
    border: 1px solid rgba(239, 68, 68, 0.45);
}

QPushButton#DangerButton:hover {
    background-color: rgba(239, 68, 68, 0.30);
    color: #FFFFFF;
}

QComboBox, QLineEdit, QSpinBox, QListWidget, QTableWidget {
    background-color: #131623;
    color: #F1F5F9;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 7px;
    padding: 5px 10px;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #272D45;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #FF73B9;
    border: 2px solid #FFFFFF;
    width: 15px;
    height: 15px;
    margin: -5px 0;
    border-radius: 8px;
}

QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #D946EF, stop:1 #38BDF8);
    border-radius: 3px;
}

QHeaderView::section {
    background-color: #20253A;
    color: #CBD5E1;
    padding: 6px;
    border: none;
    font-weight: 600;
}

QStatusBar {
    background-color: #181B29;
    color: #94A3B8;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
}
"""


class G715MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("G715 Customizer — Onboard Memory & RGB Studio")
        self.resize(1080, 820)
        self.setMinimumSize(880, 680)

        self._device: Optional[G715Device] = None

        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QVBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # --- Top Header Bar ---
        header = QFrame()
        header.setObjectName("HeaderBar")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(18, 12, 18, 12)
        h_lay.setSpacing(10)

        title = QLabel("Logitech G715 Customizer")
        title.setObjectName("AppTitle")
        h_lay.addWidget(title)
        h_lay.addStretch()

        self.conn_pill = QLabel("Disconnected")
        self.conn_pill.setObjectName("PillWarn")
        self.batt_pill = QLabel("Battery: --")
        self.batt_pill.setObjectName("Pill")
        self.mode_pill = QLabel("Mode: --")
        self.mode_pill.setObjectName("Pill")

        self.btn_reconnect = QPushButton("Reconnect")
        self.btn_reconnect.clicked.connect(self.connect_device)

        h_lay.addWidget(self.conn_pill)
        h_lay.addWidget(self.batt_pill)
        h_lay.addWidget(self.mode_pill)
        h_lay.addWidget(self.btn_reconnect)
        main_lay.addWidget(header)

        # --- Tabs ---
        self.tabs = QTabWidget()
        self.tabs.setContentsMargins(0, 8, 0, 0)

        self.onboard_tab = OnboardMemoryTab(
            get_device=self.get_device,
            notify=self.notify,
            refresh_header=self.refresh_header,
        )
        self.perkey_tab = PerKeyStudioTab(
            get_device=self.get_device,
            notify=self.notify,
            refresh_header=self.refresh_header,
        )
        self.hardware_tab = HardwareTab(
            get_device=self.get_device,
            notify=self.notify,
            refresh_all=self.refresh_all,
        )

        self.tabs.addTab(self.onboard_tab, "  Onboard Memory  ")
        self.tabs.addTab(self.perkey_tab, "  Per-Key && Perimeter Studio  ")
        self.tabs.addTab(self.hardware_tab, "  Hardware, Boot && Bindings  ")
        main_lay.addWidget(self.tabs, stretch=1)

        self.statusBar().showMessage("Scanning for Logitech G715...")

        # Connect shortly after window shows so UI renders immediately
        QTimer.singleShot(80, self.connect_device)

        # Gentle battery & status refresh every 30s
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(30_000)
        self._poll_timer.timeout.connect(self.refresh_header)
        self._poll_timer.start()

    def get_device(self) -> Optional[G715Device]:
        return self._device

    def notify(self, message: str, is_error: bool = False) -> None:
        prefix = "Error: " if is_error else ""
        self.statusBar().showMessage(f"{prefix}{message}", 7000)
        self.statusBar().setStyleSheet(
            "QStatusBar { color: #FCA5A5; }" if is_error else "QStatusBar { color: #A7F3D0; }"
        )

    def connect_device(self) -> None:
        if self._device is not None:
            self._device.close()
            self._device = None
        try:
            devices = discover_g715_devices()
            if not devices:
                self._set_disconnected("No G715 detected (check USB/Lightspeed dongle & udev rules)")
                return
            self._device = G715Device.connect(devices[0])
            self.refresh_all()
        except HidppError as e:
            self._set_disconnected(str(e))

    def _set_disconnected(self, reason: str) -> None:
        self.conn_pill.setText("Disconnected")
        self.conn_pill.setObjectName("PillWarn")
        self.conn_pill.style().unpolish(self.conn_pill)
        self.conn_pill.style().polish(self.conn_pill)
        self.batt_pill.setText("Battery: --")
        self.mode_pill.setText("Mode: --")
        self.notify(reason, True)

    def refresh_header(self) -> None:
        if self._device is None:
            return
        try:
            st = self._device.get_status()
            self.conn_pill.setText(f"{st.connection.upper()}  •  HID++ {st.protocol_version}")
            self.conn_pill.setObjectName("PillOk")
            self.conn_pill.style().unpolish(self.conn_pill)
            self.conn_pill.style().polish(self.conn_pill)

            if st.battery:
                icon = "⚡ " if st.battery.charging else ""
                self.batt_pill.setText(f"{icon}{st.battery.percentage}% ({st.battery.status_text})")
            else:
                self.batt_pill.setText("Battery: N/A")

            if st.sw_control:
                self.mode_pill.setText("Live SW Mode (RAM)")
                self.mode_pill.setObjectName("PillWarn")
            else:
                self.mode_pill.setText("Onboard Flash Mode")
                self.mode_pill.setObjectName("PillOk")
            self.mode_pill.style().unpolish(self.mode_pill)
            self.mode_pill.style().polish(self.mode_pill)
        except HidppError as e:
            self._set_disconnected(f"Connection lost: {e}")

    def refresh_all(self) -> None:
        self.refresh_header()
        self.onboard_tab.load_from_device()
        self.hardware_tab.load_from_device()

    def closeEvent(self, event) -> None:
        if self._device is not None:
            self._device.close()
            self._device = None
        super().closeEvent(event)


def launch_gui() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("G715 Customizer")
    app.setStyleSheet(STYLESHEET)
    win = G715MainWindow()
    win.show()
    return app.exec()
