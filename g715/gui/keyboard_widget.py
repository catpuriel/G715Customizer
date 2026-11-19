"""Interactive vector-rendered Logitech G715 TKL + 16-LED Perimeter canvas."""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ..layout import G715_LAYOUT, LedCell
from ..protocol import (
    EFFECT_AURORA_PLAYFUL,
    EFFECT_BREATHE,
    EFFECT_CYCLE,
    EFFECT_OFF,
    EFFECT_RIPPLE,
    EFFECT_STATIC,
    EFFECT_WAVE,
    LedEffect,
    format_hex_color,
)


def _hsv_to_rgb_int(h: float, s: float, v: float) -> int:
    c = QColor.fromHsvF(h % 1.0, max(0.0, min(1.0, s)), max(0.0, min(1.0, v)))
    return (c.red() << 16) | (c.green() << 8) | c.blue()


class G715KeyboardWidget(QWidget):
    """Renders the Logitech G715 TKL keyboard with 16-LED perimeter glow.

    Supports:
      - Interactive paint mode (click/drag to paint keys & underglow LEDs, right-click eyedropper)
      - Animated preview mode for onboard effects (Static, Breathe, Cycle, Wave, Ripple, Aurora)
    """

    zonePainted = Signal(int, int)       # (zone_id, color_int)
    paintStrokeFinished = Signal()
    colorPicked = Signal(int)            # right-click eyedropper

    def __init__(self, interactive: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._interactive = interactive
        self._brush_color = 0xFF73B9
        self._painting = False
        self._hover_zone: Optional[int] = None
        self._zone_colors: dict[int, int] = {c.zone_id: 0xF552FF for c in G715_LAYOUT}

        # Preview mode effects (when not interactive)
        self._preview_keys_effect: Optional[LedEffect] = None
        self._preview_perim_effect: Optional[LedEffect] = None
        self._anim_phase = 0.0

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(250 if not interactive else 310)
        self.setMinimumWidth(620)

        self._timer = QTimer(self)
        self._timer.setInterval(45)
        self._timer.timeout.connect(self._tick_animation)
        if not interactive:
            self._timer.start()

    def set_brush_color(self, color: int) -> None:
        self._brush_color = color & 0xFFFFFF

    def set_zone_colors(self, colors: dict[int, int]) -> None:
        for zid, col in colors.items():
            self._zone_colors[zid] = col & 0xFFFFFF
        self.update()

    def get_zone_colors(self) -> dict[int, int]:
        return dict(self._zone_colors)

    def set_preview_effects(self, keys_eff: LedEffect, perim_eff: LedEffect) -> None:
        self._preview_keys_effect = keys_eff
        self._preview_perim_effect = perim_eff
        self._update_preview_colors()
        self.update()

    def _tick_animation(self) -> None:
        if self._interactive:
            return
        self._anim_phase = (self._anim_phase + 0.045) % 1000.0
        self._update_preview_colors()
        self.update()

    def _eval_effect_for_cell(self, eff: LedEffect, cell: LedCell) -> int:
        eid = eff.effect_id
        if eid == EFFECT_OFF:
            return 0x1A1D26
        if eid == EFFECT_STATIC:
            return eff.color
        if eid == EFFECT_BREATHE:
            period_s = max(0.5, eff.period / 1000.0)
            wave = 0.5 - 0.5 * math.cos(2 * math.pi * self._anim_phase / period_s)
            scale = (0.12 + 0.88 * wave) * (eff.intensity / 100.0)
            r = int(((eff.color >> 16) & 0xFF) * scale)
            g = int(((eff.color >> 8) & 0xFF) * scale)
            b = int((eff.color & 0xFF) * scale)
            return (r << 16) | (g << 8) | b
        if eid == EFFECT_CYCLE:
            period_s = max(0.5, eff.period / 1000.0)
            hue = (self._anim_phase / period_s) % 1.0
            return _hsv_to_rgb_int(hue, eff.saturation / 255.0, eff.intensity / 100.0)
        if eid == EFFECT_WAVE:
            period_s = max(0.5, eff.period / 1000.0)
            nx = (cell.x + cell.w * 0.5) / 19.0
            ny = (cell.y + cell.h * 0.5) / 8.5
            d = eff.direction
            if d == 1:
                spatial = -nx
            elif d == 6:
                spatial = nx
            elif d == 2:
                spatial = -ny
            elif d == 7:
                spatial = ny
            elif d in (3, 5):
                spatial = -math.hypot(nx - 0.5, ny - 0.5) * 1.6
            elif d in (4, 8):
                spatial = math.hypot(nx - 0.5, ny - 0.5) * 1.6
            else:
                spatial = 0.0
            hue = (self._anim_phase / period_s + spatial) % 1.0
            return _hsv_to_rgb_int(hue, eff.saturation / 255.0, eff.intensity / 100.0)
        if eid == EFFECT_RIPPLE:
            # Gentle animated ripple pulse from center
            nx = (cell.x + cell.w * 0.5) / 19.0
            ny = (cell.y + cell.h * 0.5) / 8.5
            dist = math.hypot(nx - 0.45, ny - 0.55)
            ring = (self._anim_phase * 0.55) % 1.2
            glow = max(0.18, math.exp(-((dist - ring) ** 2) / 0.025))
            r = int(((eff.color >> 16) & 0xFF) * glow)
            g = int(((eff.color >> 8) & 0xFF) * glow)
            b = int((eff.color & 0xFF) * glow)
            return (r << 16) | (g << 8) | b
        if eid == EFFECT_AURORA_PLAYFUL:
            nx = (cell.x + cell.w * 0.5) / 19.0
            hue = (0.85 + 0.35 * math.sin(self._anim_phase * 0.6 + nx * 3.0)) % 1.0
            return _hsv_to_rgb_int(hue, 0.55, 1.0)
        return eff.color

    def _update_preview_colors(self) -> None:
        if self._preview_keys_effect is None or self._preview_perim_effect is None:
            return
        for cell in G715_LAYOUT:
            eff = self._preview_perim_effect if cell.group == "perimeter" else self._preview_keys_effect
            self._zone_colors[cell.zone_id] = self._eval_effect_for_cell(eff, cell)

    def _compute_transform(self) -> tuple[float, float, float]:
        # Layout spans x in [-0.8, 19.1] (width ~20.0), y in [-0.85, 8.35] (height ~9.2)
        pad_x, pad_y = 22.0, 18.0
        avail_w = max(100.0, self.width() - 2 * pad_x)
        avail_h = max(80.0, self.height() - 2 * pad_y)
        unit = min(avail_w / 20.1, avail_h / 9.35)
        total_w = 20.1 * unit
        total_h = 9.35 * unit
        ox = (self.width() - total_w) * 0.5 + 0.9 * unit
        oy = (self.height() - total_h) * 0.5 + 0.9 * unit
        return ox, oy, unit

    def _cell_rect(self, cell: LedCell, ox: float, oy: float, unit: float) -> QRectF:
        gap = 0.08 * unit if cell.shape == "key" else 0.0
        return QRectF(
            ox + cell.x * unit + gap,
            oy + cell.y * unit + gap,
            cell.w * unit - 2 * gap,
            cell.h * unit - 2 * gap,
        )

    def _hit_test(self, pos: QPointF) -> Optional[LedCell]:
        ox, oy, unit = self._compute_transform()
        for cell in G715_LAYOUT:
            if self._cell_rect(cell, ox, oy, unit).contains(pos):
                return cell
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._interactive:
            return
        cell = self._hit_test(event.position())
        if cell is None:
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.colorPicked.emit(self._zone_colors.get(cell.zone_id, 0xFFFFFF))
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._painting = True
            self._paint_cell(cell)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        cell = self._hit_test(event.position())
        new_hover = cell.zone_id if cell else None
        if new_hover != self._hover_zone:
            self._hover_zone = new_hover
            self.update()
        if cell is not None:
            col = self._zone_colors.get(cell.zone_id, 0)
            tip = f"{cell.label}  (0x{cell.zone_id:02X})  •  {format_hex_color(col)}"
            if self._interactive:
                tip += "\nLeft-click/drag: paint  •  Right-click: eyedropper"
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        if self._interactive and self._painting and cell is not None:
            self._paint_cell(cell)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._interactive and self._painting and event.button() == Qt.MouseButton.LeftButton:
            self._painting = False
            self.paintStrokeFinished.emit()

    def leaveEvent(self, _event) -> None:
        self._hover_zone = None
        self.update()

    def _paint_cell(self, cell: LedCell) -> None:
        if self._zone_colors.get(cell.zone_id) != self._brush_color:
            self._zone_colors[cell.zone_id] = self._brush_color
            self.zonePainted.emit(cell.zone_id, self._brush_color)
            self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ox, oy, unit = self._compute_transform()

        # Soft ambient glow behind the entire keyboard driven by perimeter LEDs
        perim_cells = [c for c in G715_LAYOUT if c.group == "perimeter"]
        for cell in perim_cells:
            rect = self._cell_rect(cell, ox, oy, unit)
            col = self._zone_colors.get(cell.zone_id, 0xF552FF)
            r, g, b = (col >> 16) & 0xFF, (col >> 8) & 0xFF, col & 0xFF
            center = rect.center()
            rad = max(rect.width(), rect.height()) * 1.25
            grad = QRadialGradient(center, rad)
            grad.setColorAt(0.0, QColor(r, g, b, 130))
            grad.setColorAt(0.55, QColor(r, g, b, 42))
            grad.setColorAt(1.0, QColor(r, g, b, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(center, rad, rad * 0.72)

        # Draw G715 Cloud-White / Silver rounded chassis body
        chassis = QRectF(ox - 0.35 * unit, oy - 0.25 * unit, 18.95 * unit, 7.95 * unit)
        chassis_path = QPainterPath()
        chassis_path.addRoundedRect(chassis, 0.55 * unit, 0.55 * unit)

        body_grad = QLinearGradient(chassis.topLeft(), chassis.bottomRight())
        body_grad.setColorAt(0.0, QColor(42, 46, 59))
        body_grad.setColorAt(1.0, QColor(28, 31, 42))
        p.setBrush(QBrush(body_grad))
        p.setPen(QPen(QColor(255, 255, 255, 36), 1.4))
        p.drawPath(chassis_path)

        # Draw perimeter LED bars
        for cell in perim_cells:
            rect = self._cell_rect(cell, ox, oy, unit)
            col = self._zone_colors.get(cell.zone_id, 0xF552FF)
            qc = QColor((col >> 16) & 0xFF, (col >> 8) & 0xFF, col & 0xFF)
            is_hover = self._hover_zone == cell.zone_id
            p.setBrush(QBrush(qc))
            p.setPen(QPen(QColor("#FFFFFF") if is_hover else QColor(255, 255, 255, 95), 2.0 if is_hover else 1.0))
            p.drawRoundedRect(rect, 0.18 * unit, 0.18 * unit)

        # Draw keys, media pills, and G logo
        base_pt = max(6.5, unit * 0.24)
        small_pt = max(5.8, unit * 0.19)
        key_font = QFont("Sans Serif")
        key_font.setPointSizeF(base_pt)
        key_font.setWeight(QFont.Weight.DemiBold)
        small_font = QFont("Sans Serif")
        small_font.setPointSizeF(small_pt)
        small_font.setWeight(QFont.Weight.DemiBold)

        for cell in G715_LAYOUT:
            if cell.group == "perimeter":
                continue
            rect = self._cell_rect(cell, ox, oy, unit)
            col = self._zone_colors.get(cell.zone_id, 0xF552FF)
            r, g, b = (col >> 16) & 0xFF, (col >> 8) & 0xFF, col & 0xFF
            qc = QColor(r, g, b)
            is_hover = self._hover_zone == cell.zone_id

            # Subtle key under-glow halo
            halo = rect.adjusted(-1.5, -1.5, 1.5, 1.5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(r, g, b, 85))
            radius = rect.height() * 0.45 if cell.shape == "pill" else 0.18 * unit
            p.drawRoundedRect(halo, radius, radius)

            # Keycap face (dark tinted cap with illuminated legend & edge, like white/dark backlit PBT)
            cap_bg = QColor(
                int(24 + r * 0.28),
                int(26 + g * 0.28),
                int(34 + b * 0.28),
            )
            p.setBrush(QBrush(cap_bg))
            border_color = QColor("#FFFFFF") if is_hover else QColor(r, g, b, 210)
            p.setPen(QPen(border_color, 2.0 if is_hover else 1.25))
            p.drawRoundedRect(rect, radius, radius)

            # Illuminated legend text
            p.setFont(small_font if (len(cell.label) >= 4 and cell.w <= 1.1) else key_font)
            luma = 0.299 * r + 0.587 * g + 0.114 * b
            legend_color = qc if luma > 55 else QColor(175, 180, 195)
            p.setPen(legend_color)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, cell.label)

        p.end()
