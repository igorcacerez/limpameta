"""Interface gráfica do LimpaMeta (PySide6)."""
from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
import tempfile
import traceback

from PIL import Image
from PySide6.QtCore import (QByteArray, QObject, QPoint, QRect, QRectF, QRunnable, QSettings, QSize, Qt,
                            QThreadPool, QTimer, QUrl, Signal)
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QFontMetrics, QIcon, QImage,
                           QKeySequence, QPainter, QPainterPath, QPalette, QPen, QPixmap, QShortcut)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QComboBox, QDialog, QFileDialog,
                               QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMenu, QMessageBox, QProgressBar, QPushButton, QSizePolicy, QSplitter,
                               QStackedWidget, QStyle, QStyledItemDelegate, QToolButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from . import __version__, core
from .core import CATEGORIES, CATEGORY_ORDER, PRIVACY, MediaInfo

APP_NAME = "LimpaMeta"
REPO_URL = "https://github.com/igorcacerez/limpameta"
LOG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "LimpaMeta", "logs")
log = logging.getLogger("limpameta")

# --------------------------------------------------------------------------- tema

C = dict(
    bg="#0E1014", surface="#15181E", surface2="#1C2028", surface3="#242934", border="#2A303C", border2="#353C4A",
    text="#E8EAF0", muted="#98A0B3", faint="#6B7385", accent="#5B8CFF", accent_hover="#7AA2FF", accent_dim="#2A3A66",
    danger="#F2616D", danger_dim="#3A1E24", warning="#F5A524", warning_dim="#3A2C14", success="#2BC48A",
    success_dim="#14332A",
)
CAT_COLOR = {"location": C["danger"], "device": "#B38CFF", "date": "#4FC3F7", "author": C["warning"],
             "color": "#7BD88F", "tech": C["faint"]}
CAT_ICON = {"location": "pin", "device": "phone", "date": "clock", "author": "user", "color": "palette",
            "tech": "gear"}
RISK = {
    "high": ("Risco alto", "Revela onde a foto ou o vídeo foi feito", C["danger"], C["danger_dim"]),
    "medium": ("Risco médio", "Revela aparelho, autor ou datas", C["warning"], C["warning_dim"]),
    "low": ("Risco baixo", "Só dados técnicos de formato", C["success"], C["success_dim"]),
    "clean": ("Limpo", "Nenhum metadado encontrado", C["success"], C["success_dim"]),
}

SVG = {
    "pin": '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    "phone": '<rect x="7" y="2.5" width="10" height="19" rx="2.2"/><path d="M11 18h2"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
    "palette": '<circle cx="12" cy="12" r="9"/><circle cx="8" cy="10" r="1.2"/><circle cx="12" cy="7.5" r="1.2"/>'
               '<circle cx="16" cy="10" r="1.2"/><path d="M12 21a3 3 0 0 1 0-6h2"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6'
            'l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2.5"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
    "film": '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M7.5 4v16M16.5 4v16M3 9h4.5M3 15h4.5M16.5 9H21'
            'M16.5 15H21"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "trash": '<path d="M4 7h16M9.5 7V4.5h5V7M6 7l1 13h10l1-13"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
    "external": '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "upload": '<path d="M12 15V4M7 9l5-5 5 5M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    "alert": '<path d="M12 3.5l9.5 17h-19z"/><path d="M12 10v4.5M12 17.5v.5"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "sparkle": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6"/>',
    "download": '<path d="M12 4v11M7 10l5 5 5-5M4 19h16"/>',
}
_icon_cache: dict = {}


def svg_pixmap(name: str, color: str, size: int = 18, stroke: float = 1.8) -> QPixmap:
    key = (name, color, size, stroke)
    if key in _icon_cache:
        return _icon_cache[key]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{SVG[name]}</svg>')
    dpr = 2.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    _icon_cache[key] = pm
    return pm


def icon(name: str, color: str = C["text"], size: int = 18) -> QIcon:
    return QIcon(svg_pixmap(name, color, size))


def asset(name: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "limpameta", "assets", name)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", name)


def _indicator_files() -> dict:
    d = os.path.join(tempfile.gettempdir(), "limpameta-ui")
    os.makedirs(d, exist_ok=True)
    files = {
        "unchecked": f'<rect x="1" y="1" width="16" height="16" rx="4.5" fill="{C["surface"]}" stroke="{C["border2"]}" stroke-width="1.5"/>',
        "checked": f'<rect x="0.5" y="0.5" width="17" height="17" rx="4.5" fill="{C["accent"]}"/>'
                   '<path d="M4.5 9.2l3 3 6-6.4" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
        "partial": f'<rect x="0.5" y="0.5" width="17" height="17" rx="4.5" fill="{C["accent_dim"]}" stroke="{C["accent"]}"/>'
                   '<path d="M5 9h8" stroke="#fff" stroke-width="2" stroke-linecap="round"/>',
        "branch-open": f'<path d="M5 7l4 4 4-4" fill="none" stroke="{C["muted"]}" stroke-width="1.6" stroke-linecap="round"/>',
        "branch-closed": f'<path d="M7 5l4 4-4 4" fill="none" stroke="{C["muted"]}" stroke-width="1.6" stroke-linecap="round"/>',
        "chevron": f'<path d="M5 7l4 4 4-4" fill="none" stroke="{C["muted"]}" stroke-width="1.6" stroke-linecap="round"/>',
    }
    out = {}
    for k, body in files.items():
        p = os.path.join(d, f"{k}.svg")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(f'<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 18 18">{body}</svg>')
        out[k] = p.replace("\\", "/")
    return out


def stylesheet() -> str:
    i = _indicator_files()
    return f"""
    * {{ font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 10pt; color: {C['text']}; }}
    QMainWindow, #Root {{ background: {C['bg']}; }}
    QToolTip {{ background: {C['surface3']}; color: {C['text']}; border: 1px solid {C['border2']}; padding: 6px 8px; border-radius: 6px; }}
    #Sidebar {{ background: {C['surface']}; border-right: 1px solid {C['border']}; }}
    #Card {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 14px; }}
    #Footer {{ background: {C['surface']}; border-top: 1px solid {C['border']}; }}
    QLabel#H1 {{ font-size: 15pt; font-weight: 600; }}
    QLabel#H2 {{ font-size: 12pt; font-weight: 600; }}
    QLabel#Muted {{ color: {C['muted']}; }}
    QLabel#Faint {{ color: {C['faint']}; font-size: 9pt; }}
    QLabel#Brand {{ font-size: 13pt; font-weight: 700; }}
    QPushButton {{ background: {C['surface2']}; border: 1px solid {C['border2']}; border-radius: 9px; padding: 8px 14px; font-weight: 600; }}
    QPushButton:hover {{ background: {C['surface3']}; }}
    QPushButton:pressed {{ background: {C['border']}; }}
    QPushButton:disabled {{ color: {C['faint']}; background: {C['surface']}; border-color: {C['border']}; }}
    QPushButton#Primary {{ background: {C['accent']}; border: 1px solid {C['accent']}; color: #fff; }}
    QPushButton#Primary:hover {{ background: {C['accent_hover']}; border-color: {C['accent_hover']}; }}
    QPushButton#Primary:disabled {{ background: {C['accent_dim']}; border-color: {C['accent_dim']}; color: {C['muted']}; }}
    QPushButton#Ghost {{ background: transparent; border: none; color: {C['muted']}; padding: 6px 8px; }}
    QPushButton#Ghost:hover {{ color: {C['text']}; background: {C['surface2']}; }}
    QPushButton#Link {{ background: transparent; border: none; color: {C['accent']}; padding: 2px 0; font-weight: 600; text-align: left; }}
    QPushButton#Link:hover {{ color: {C['accent_hover']}; text-decoration: underline; }}
    QPushButton#Seg {{ background: transparent; border: none; border-radius: 7px; padding: 6px 12px; color: {C['muted']}; }}
    QPushButton#Seg:hover {{ color: {C['text']}; }}
    QPushButton#Seg:checked {{ background: {C['surface3']}; color: {C['text']}; }}
    #SegBox {{ background: {C['surface2']}; border: 1px solid {C['border']}; border-radius: 9px; }}
    QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
    QToolButton:hover {{ background: {C['surface2']}; }}
    QLineEdit {{ background: {C['surface2']}; border: 1px solid {C['border']}; border-radius: 9px; padding: 7px 10px; selection-background-color: {C['accent']}; }}
    QLineEdit:focus {{ border-color: {C['accent']}; }}
    QComboBox {{ background: {C['surface2']}; border: 1px solid {C['border']}; border-radius: 9px; padding: 7px 10px; min-width: 210px; }}
    QComboBox:hover {{ border-color: {C['border2']}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox::down-arrow {{ image: url({i['chevron']}); width: 14px; height: 14px; }}
    QComboBox QAbstractItemView {{ background: {C['surface2']}; border: 1px solid {C['border2']}; selection-background-color: {C['surface3']}; outline: 0; padding: 4px; }}
    QListWidget {{ background: transparent; border: none; outline: 0; }}
    QTreeWidget {{ background: transparent; border: none; outline: 0; alternate-background-color: transparent; }}
    QTreeWidget::item {{ padding: 5px 2px; border: none; }}
    QTreeWidget::item:hover {{ background: {C['surface2']}; }}
    QTreeWidget::item:selected {{ background: {C['surface2']}; color: {C['text']}; }}
    QTreeView::indicator {{ width: 18px; height: 18px; }}
    QTreeView::indicator:unchecked {{ image: url({i['unchecked']}); }}
    QTreeView::indicator:checked {{ image: url({i['checked']}); }}
    QTreeView::indicator:indeterminate {{ image: url({i['partial']}); }}
    QTreeView::branch {{ background: transparent; }}
    QTreeView::branch:has-children:!has-siblings:closed, QTreeView::branch:closed:has-children:has-siblings {{ image: url({i['branch-closed']}); }}
    QTreeView::branch:open:has-children:!has-siblings, QTreeView::branch:open:has-children:has-siblings {{ image: url({i['branch-open']}); }}
    QHeaderView::section {{ background: transparent; color: {C['faint']}; border: none; border-bottom: 1px solid {C['border']}; padding: 6px 4px; font-size: 9pt; font-weight: 600; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {C['border2']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {C['faint']}; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
    QScrollBar:horizontal {{ height: 0; }}
    QProgressBar {{ background: {C['surface2']}; border: none; border-radius: 3px; max-height: 6px; }}
    QProgressBar::chunk {{ background: {C['accent']}; border-radius: 3px; }}
    QSplitter::handle {{ background: {C['border']}; width: 1px; }}
    QMenu {{ background: {C['surface2']}; border: 1px solid {C['border2']}; padding: 4px; border-radius: 8px; }}
    QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {C['surface3']}; }}
    QMessageBox, QDialog {{ background: {C['surface']}; }}
    QMessageBox QPushButton {{ min-width: 90px; }}
    """


# --------------------------------------------------------------------------- tarefas em segundo plano

class _Signals(QObject):
    scanned = Signal(str, object, object)  # path, MediaInfo, QImage | None
    cleaned = Signal(int, str, object, object)  # índice, path, CleanResult | None, erro | None
    finished = Signal()


def _thumb_bytes(info: MediaInfo, size: int = 160) -> bytes | None:
    try:
        if info.kind == "video":
            return core.video_thumbnail(info.path, size * 2)
        with Image.open(info.path) as im:
            try:
                from PIL import ImageOps
                im = ImageOps.exif_transpose(im)
            except Exception:
                pass
            im.thumbnail((size * 2, size * 2))
            buf = io.BytesIO()
            im.convert("RGBA").save(buf, "PNG")
            return buf.getvalue()
    except Exception:
        return None


class ScanTask(QRunnable):
    def __init__(self, path: str, signals: _Signals):
        super().__init__()
        self.path, self.signals = path, signals

    def run(self):
        try:
            info = core.read_media(self.path)
        except Exception as e:  # nunca deixa a interface travada em "Analisando…"
            info = MediaInfo(self.path, "image", error=str(e))
        data = None if info.error else _thumb_bytes(info)
        img = QImage.fromData(data) if data else None
        self.signals.scanned.emit(self.path, info, img)


class CleanTask(QRunnable):
    def __init__(self, jobs: list[MediaInfo], out_dir: str | None, signals: _Signals):
        super().__init__()
        self.jobs, self.out_dir, self.signals = jobs, out_dir, signals

    def run(self):
        for i, info in enumerate(self.jobs):
            try:
                res = core.clean_media(info, out_dir=self.out_dir)
                self.signals.cleaned.emit(i, info.path, res, None)
            except Exception as e:
                log.exception("falha ao limpar %s", info.path)
                self.signals.cleaned.emit(i, info.path, None, str(e))
        self.signals.finished.emit()


# --------------------------------------------------------------------------- widgets auxiliares

def label(text: str = "", obj: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    return lb


def button(text: str, obj: str | None = None, ic: str | None = None, color: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if obj:
        b.setObjectName(obj)
    if ic:
        b.setIcon(icon(ic, color or ("#ffffff" if obj == "Primary" else C["text"]), 16))
        b.setIconSize(QSize(16, 16))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def hline() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {C['border']};")
    return f


class Pill(QLabel):
    def __init__(self, text="", fg=C["text"], bg=C["surface2"], ic: str | None = None):
        super().__init__()
        self.set(text, fg, bg, ic)

    def set(self, text, fg, bg, ic=None):
        self.setText(text)
        self.setStyleSheet(f"background: {bg}; color: {fg}; border-radius: 10px; padding: 3px 10px; "
                           f"font-size: 9pt; font-weight: 600;")


class Thumb(QLabel):
    """Miniatura com cantos arredondados."""

    def __init__(self, size: int):
        super().__init__()
        self.sz = size
        self.setFixedSize(size, size)
        self._pm: QPixmap | None = None
        self._kind = "image"

    def set_image(self, img: QImage | None, kind: str):
        self._pm = QPixmap.fromImage(img) if img is not None and not img.isNull() else None
        self._kind = kind
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.sz, self.sz), 12, 12)
        p.setClipPath(path)
        p.fillRect(self.rect(), QColor(C["surface2"]))
        if self._pm:
            pm = self._pm.scaled(self.sz * 2, self.sz * 2, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(2)
            w, h = pm.width() / 2, pm.height() / 2
            p.drawPixmap(QPoint(int((self.sz - w) / 2), int((self.sz - h) / 2)), pm)
        else:
            ic = svg_pixmap("film" if self._kind == "video" else "image", C["faint"], self.sz // 2)
            p.drawPixmap(self.sz // 4, self.sz // 4, ic)
        if self._kind == "video" and self._pm:
            p.setBrush(QColor(0, 0, 0, 150))
            p.setPen(Qt.PenStyle.NoPen)
            r = self.sz // 4
            p.drawEllipse(QRect(self.sz // 2 - r // 2, self.sz // 2 - r // 2, r, r))
            p.setBrush(QColor("#ffffff"))
            t = r // 3
            cx, cy = self.sz // 2 + 1, self.sz // 2
            tri = QPainterPath()
            tri.moveTo(cx - t * 0.6, cy - t)
            tri.lineTo(cx + t, cy)
            tri.lineTo(cx - t * 0.6, cy + t)
            tri.closeSubpath()
            p.drawPath(tri)
        p.end()


# --------------------------------------------------------------------------- lista de arquivos

ROLE_PATH = Qt.ItemDataRole.UserRole + 1


class FileEntry:
    def __init__(self, path: str):
        self.path = path
        self.info: MediaInfo | None = None
        self.thumb: QPixmap | None = None
        self.thumb_img: QImage | None = None
        self.state = "scanning"  # scanning | ready | cleaning | cleaned | error
        self.result = None
        self.error: str | None = None

    @property
    def name(self):
        return os.path.basename(self.path)

    @property
    def kind(self):
        return "video" if os.path.splitext(self.path)[1].lower() in core.VIDEO_EXT else "image"


class FileDelegate(QStyledItemDelegate):
    H = 68

    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.win = window

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.H)

    def paint(self, p: QPainter, option, index):
        e: FileEntry = self.win.entries.get(index.data(ROLE_PATH))
        if not e:
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = option.rect.adjusted(8, 3, -8, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C["surface3"] if selected else C["surface2"]))
            p.drawRoundedRect(QRectF(r), 10, 10)
        if selected:
            p.setBrush(QColor(C["accent"]))
            p.drawRoundedRect(QRectF(r.left(), r.top() + 14, 3, r.height() - 28), 1.5, 1.5)
        # miniatura
        t = QRectF(r.left() + 10, r.top() + 9, 44, 44)
        clip = QPainterPath()
        clip.addRoundedRect(t, 9, 9)
        p.save()
        p.setClipPath(clip)
        p.fillRect(t, QColor(C["surface2"]))
        if e.thumb:
            pm = e.thumb
            sw, sh = pm.width(), pm.height()
            side = min(sw, sh)
            src = QRect((sw - side) // 2, (sh - side) // 2, side, side)
            p.drawPixmap(t.toRect(), pm, src)
        else:
            ic = svg_pixmap("film" if e.kind == "video" else "image", C["faint"], 22)
            p.drawPixmap(int(t.left() + 11), int(t.top() + 11), ic)
        p.restore()
        # status (direita)
        right = r.right() - 12
        status_txt, fg, bg = self._status(e)
        f = QFont(option.font)
        f.setPointSizeF(8.5)
        f.setWeight(QFont.Weight.DemiBold)
        fm = QFontMetrics(f)
        if status_txt:
            w = fm.horizontalAdvance(status_txt) + 16
            pill = QRectF(right - w, r.center().y() - 10, w, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(bg))
            p.drawRoundedRect(pill, 10, 10)
            p.setPen(QColor(fg))
            p.setFont(f)
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, status_txt)
            right = pill.left() - 8
        # textos
        x = t.right() + 12
        nf = QFont(option.font)
        nf.setPointSizeF(10)
        nf.setWeight(QFont.Weight.DemiBold)
        p.setFont(nf)
        p.setPen(QColor(C["text"]))
        name = QFontMetrics(nf).elidedText(e.name, Qt.TextElideMode.ElideMiddle, int(right - x))
        p.drawText(QRectF(x, r.top() + 12, right - x, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
        sf = QFont(option.font)
        sf.setPointSizeF(8.8)
        p.setFont(sf)
        p.setPen(QColor(C["danger"] if e.state == "error" else C["muted"]))
        sub = QFontMetrics(sf).elidedText(self._subtitle(e), Qt.TextElideMode.ElideRight, int(right - x))
        p.drawText(QRectF(x, r.top() + 33, right - x, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sub)
        p.restore()

    @staticmethod
    def _subtitle(e: FileEntry) -> str:
        if e.state == "scanning":
            return "Analisando…"
        if e.state == "cleaning":
            return "Limpando…"
        if e.state == "error":
            return e.error or "Erro"
        n = len(e.info.fields) if e.info else 0
        size = core.human_size(e.info.size) if e.info else ""
        if e.state == "cleaned" and e.result:
            return f"Cópia limpa: {os.path.basename(e.result.output)}"
        return f"{size} · {n} metadado{'s' if n != 1 else ''}" if n else f"{size} · sem metadados"

    @staticmethod
    def _status(e: FileEntry):
        if e.state == "cleaned":
            return "✓ Limpo", C["success"], C["success_dim"]
        if e.state in ("scanning", "cleaning") or not e.info:
            return "", "", ""
        if e.state == "error":
            return "Erro", C["danger"], C["danger_dim"]
        title, _, fg, bg = RISK[e.info.risk]
        short = {"high": "Alto", "medium": "Médio", "low": "Baixo", "clean": "Sem dados"}[e.info.risk]
        return short, fg, bg


class DropZone(QFrame):
    def __init__(self, on_files, on_folder):
        super().__init__()
        self.setObjectName("DropZone")
        self.setStyleSheet(f"#DropZone {{ border: 1.5px dashed {C['border2']}; border-radius: 14px; background: {C['bg']}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 28, 20, 28)
        lay.setSpacing(10)
        lay.addStretch()
        ic = QLabel()
        ic.setPixmap(svg_pixmap("upload", C["accent"], 36))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ic)
        t = label("Arraste fotos e vídeos para cá", "H2")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        s = label("Ou escolha arquivos ou uma pasta inteira.\nNada é enviado para a internet.", "Muted")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(s)
        row = QHBoxLayout()
        row.addStretch()
        b1 = button("Escolher arquivos", "Primary", "plus")
        b1.clicked.connect(on_files)
        b2 = button("Pasta", None, "folder")
        b2.clicked.connect(on_folder)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch()
        lay.addSpacing(6)
        lay.addLayout(row)
        fmt = label("JPG · PNG · WebP · HEIC · TIFF · GIF · MP4 · MOV · MKV e mais", "Faint", wrap=True)
        fmt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(6)
        lay.addWidget(fmt)
        lay.addStretch()


class DropOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(14, 16, 20, 215))
        r = QRectF(self.rect()).adjusted(24, 24, -24, -24)
        pen = QPen(QColor(C["accent"]), 2, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(91, 140, 255, 18))
        p.drawRoundedRect(r, 18, 18)
        ic = svg_pixmap("upload", C["accent"], 48)
        p.drawPixmap(int(r.center().x() - 24), int(r.center().y() - 60), ic)
        f = QFont(self.font())
        f.setPointSize(16)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(C["text"]))
        p.drawText(QRectF(r.left(), r.center().y() + 4, r.width(), 30), Qt.AlignmentFlag.AlignCenter,
                   "Solte para analisar")
        p.end()


# --------------------------------------------------------------------------- painel de detalhes

class Banner(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Banner")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(12)
        self.ic = QLabel()
        lay.addWidget(self.ic, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title = label("", None, wrap=True)
        self.title.setStyleSheet("font-weight: 600;")
        self.sub = label("", "Muted", wrap=True)
        for lb in (self.title, self.sub):
            lb.setMinimumWidth(120)
        col.addWidget(self.title)
        col.addWidget(self.sub)
        lay.addLayout(col, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(6)
        lay.addLayout(self.actions)
        close = QToolButton()
        close.setIcon(icon("x", C["muted"], 14))
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.hide)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        self.hide()

    def show_msg(self, kind: str, title: str, sub: str = "", actions=()):
        fg, bg, ic = {"ok": (C["success"], C["success_dim"], "shield"), "warn": (C["warning"], C["warning_dim"], "alert"),
                      "error": (C["danger"], C["danger_dim"], "alert"), "info": (C["accent"], C["accent_dim"], "info")}[kind]
        self.setStyleSheet(f"#Banner {{ background: {bg}; border: 1px solid {fg}; border-radius: 12px; }}"
                           f"#Banner QLabel {{ background: transparent; }}")
        self.ic.setPixmap(svg_pixmap(ic, fg, 22))
        self.title.setText(title)
        self.title.setStyleSheet(f"font-weight: 600; color: {fg};")
        self.sub.setText(sub)
        self.sub.setVisible(bool(sub))
        while self.actions.count():
            w = self.actions.takeAt(0).widget()
            if w:
                w.hide()
                w.deleteLater()
        for text, fn in actions:
            b = button(text)
            b.clicked.connect(fn)
            self.actions.addWidget(b)
        self.show()


class Welcome(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(48, 40, 48, 40)
        lay.addStretch(2)
        ic = QLabel()
        ic.setPixmap(svg_pixmap("shield", C["accent"], 56, 1.5))
        lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(12)
        t = label("Proteja sua privacidade antes de compartilhar", "H1")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        s = label("Fotos e vídeos guardam dados invisíveis: onde foram feitos, qual aparelho, quando e por quem.\n"
                  "O LimpaMeta mostra tudo e cria uma cópia limpa — seu arquivo original nunca é alterado.", "Muted")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(s)
        lay.addSpacing(28)
        row = QHBoxLayout()
        row.setSpacing(14)
        steps = [("upload", "1. Adicione", "Arraste arquivos ou pastas para a janela."),
                 ("search", "2. Revise", "Veja o que cada arquivo revela, por categoria."),
                 ("sparkle", "3. Limpe", "Escolha o que remover e gere a cópia limpa.")]
        row.addStretch()
        for ic_name, title, desc in steps:
            card = QFrame()
            card.setObjectName("Card")
            card.setFixedWidth(220)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(18, 18, 18, 18)
            cl.setSpacing(6)
            i = QLabel()
            i.setPixmap(svg_pixmap(ic_name, C["accent"], 24))
            cl.addWidget(i)
            cl.addWidget(label(title, "H2"))
            cl.addWidget(label(desc, "Muted", wrap=True))
            row.addWidget(card)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch(3)


class DetailPanel(QWidget):
    selection_changed = Signal()

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.win = window
        self.entry: FileEntry | None = None
        self._populating = False
        self._press_state = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 12)
        lay.setSpacing(16)

        # cabeçalho
        head = QHBoxLayout()
        head.setSpacing(18)
        self.thumb = Thumb(96)
        head.addWidget(self.thumb)
        col = QVBoxLayout()
        col.setSpacing(6)
        self.name = label("", "H1")
        self.name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.meta = label("", "Muted")
        col.addWidget(self.name)
        col.addWidget(self.meta)
        risk_row = QHBoxLayout()
        risk_row.setSpacing(10)
        self.risk = Pill()
        self.risk_desc = label("", "Muted")
        self.map_btn = button("Ver no mapa", "Link", "external", C["accent"])
        self.map_btn.clicked.connect(self.open_map)
        risk_row.addWidget(self.risk)
        risk_row.addWidget(self.risk_desc)
        risk_row.addWidget(self.map_btn)
        risk_row.addStretch()
        col.addLayout(risk_row)
        col.addStretch()
        head.addLayout(col, 1)
        lay.addLayout(head)

        self.chips = QHBoxLayout()
        self.chips.setSpacing(8)
        lay.addLayout(self.chips)

        self.banner = Banner()
        lay.addWidget(self.banner)
        self.note = Banner()
        lay.addWidget(self.note)

        # barra de ferramentas da tabela
        tb = QHBoxLayout()
        tb.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrar campos…")
        self.search.addAction(icon("search", C["faint"], 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(300)
        self.search.textChanged.connect(self.apply_filter)
        tb.addWidget(self.search)
        tb.addStretch()
        tb.addWidget(label("Remover:", "Muted"))
        seg = QFrame()
        seg.setObjectName("SegBox")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(3, 3, 3, 3)
        sl.setSpacing(2)
        self.seg_group = QButtonGroup(self)
        for i, (txt, tip) in enumerate([("Tudo", "Marca todos os campos"),
                                        ("Só privacidade", "Marca localização, aparelho, datas e autoria;\nmantém perfil de cor e dados técnicos"),
                                        ("Nada", "Desmarca tudo")]):
            b = QPushButton(txt)
            b.setObjectName("Seg")
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.seg_group.addButton(b, i)
            sl.addWidget(b)
        self.seg_group.idClicked.connect(self.apply_preset)
        tb.addWidget(seg)
        lay.addLayout(tb)

        # tabela
        card = QFrame()
        card.setObjectName("Card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(6, 6, 6, 6)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["CAMPO", "VALOR"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setDefaultSectionSize(320)
        self.tree.header().setStretchLastSection(True)
        self.tree.setIndentation(18)
        self.tree.setUniformRowHeights(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tree.setMouseTracking(True)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.context_menu)
        self.tree.itemChanged.connect(self.on_item_changed)
        self.tree.itemPressed.connect(lambda it, c: setattr(self, "_press_state", (it, it.checkState(0))))
        self.tree.itemClicked.connect(self.on_item_clicked)
        cl.addWidget(self.tree)
        self.empty_tree = QWidget()
        el = QVBoxLayout(self.empty_tree)
        el.addStretch()
        ei = QLabel()
        ei.setPixmap(svg_pixmap("shield", C["success"], 44, 1.5))
        el.addWidget(ei, 0, Qt.AlignmentFlag.AlignHCenter)
        self.empty_title = label("Nenhum metadado encontrado", "H2")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_sub = label("Este arquivo já está limpo.", "Muted", wrap=True)
        self.empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(self.empty_title)
        el.addWidget(self.empty_sub)
        el.addStretch()
        cl.addWidget(self.empty_tree)
        lay.addWidget(card, 1)

    # ---- preenchimento
    def show_entry(self, e: FileEntry | None):
        self.entry = e
        if not e:
            return
        info = e.info
        self.name.setText(e.name)
        self.thumb.set_image(e.thumb_img, e.kind)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.banner.hide()
        if e.state == "cleaned" and e.result:
            self.show_result_banner(e)
        if info and info.note:
            self.note.show_msg("info", "Observação", info.note)
        else:
            self.note.hide()
        if e.state == "scanning" or not info:
            self.meta.setText("Analisando…")
            self.risk.hide()
            self.risk_desc.setText("")
            self.map_btn.hide()
            self._fill([])
            return
        folder = os.path.basename(os.path.dirname(e.path)) or os.path.dirname(e.path)
        parts = [x for x in (info.details, core.human_size(info.size), f"pasta {folder}") if x]
        self.meta.setText("  ·  ".join(parts))
        self.meta.setToolTip(e.path)
        if info.error:
            self.risk.show()
            self.risk.set("Não foi possível ler", C["danger"], C["danger_dim"])
            self.risk_desc.setText(info.error)
            self.map_btn.hide()
            self._fill([])
            self.empty_title.setText("Arquivo não suportado ou corrompido")
            self.empty_sub.setText(info.error)
            return
        title, desc, fg, bg = RISK[info.risk]
        self.risk.show()
        self.risk.set(title, fg, bg)
        self.risk_desc.setText(desc)
        self.map_btn.setVisible(info.gps is not None)
        if info.gps:
            self.map_btn.setToolTip(f"{info.gps[0]:.5f}, {info.gps[1]:.5f}")
        self.empty_title.setText("Nenhum metadado encontrado")
        self.empty_sub.setText("Este arquivo já está limpo. Não há nada a remover.")
        self._fill(info.fields)

    def _fill(self, fields):
        while self.chips.count():
            w = self.chips.takeAt(0).widget()
            if w:
                w.hide()
                w.deleteLater()
        self._populating = True
        self.tree.clear()
        groups: dict[str, list] = {}
        for f in fields:
            groups.setdefault(f.category, []).append(f)
        bold = QFont(self.tree.font())
        bold.setWeight(QFont.Weight.DemiBold)
        for cat in CATEGORY_ORDER:
            if cat not in groups:
                continue
            title, desc = CATEGORIES[cat]
            n = len(groups[cat])
            chip = Pill(f"{title}  {n}", CAT_COLOR[cat], C["surface2"])
            chip.setToolTip(desc)
            self.chips.addWidget(chip)
            parent = QTreeWidgetItem(self.tree, [f"{title}", f"{n} {'itens' if n > 1 else 'item'} · {desc}"])
            parent.setIcon(0, icon(CAT_ICON[cat], CAT_COLOR[cat], 16))
            parent.setFont(0, bold)
            parent.setForeground(1, QBrush(QColor(C["faint"])))
            parent.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            parent.setData(0, Qt.ItemDataRole.UserRole, None)
            parent.setSizeHint(0, QSize(0, 38))
            for f in groups[cat]:
                child = QTreeWidgetItem(parent, [f.label, f.value])
                child.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                child.setCheckState(0, Qt.CheckState.Checked if f.checked else Qt.CheckState.Unchecked)
                child.setData(0, Qt.ItemDataRole.UserRole, f)
                child.setToolTip(0, f"{f.label}\n{f.group} · {f.key}")
                child.setToolTip(1, f.value)
                if cat == "location":
                    child.setForeground(0, QBrush(QColor(C["danger"])))
                    child.setForeground(1, QBrush(QColor("#F7A1A8")))
                else:
                    child.setForeground(1, QBrush(QColor(C["muted"])))
            parent.setExpanded(True)
        self.chips.addStretch()
        self._populating = False
        has = bool(fields)
        self.tree.setVisible(has)
        self.empty_tree.setVisible(not has)
        self.sync_preset()
        self.selection_changed.emit()

    def show_result_banner(self, e: FileEntry):
        res = e.result
        out = res.output
        acts = [("Mostrar na pasta", lambda: reveal(out)), ("Abrir", lambda: os.startfile(out)),
                ("Analisar cópia", lambda: self.win.add_paths([out], select=True))]
        if res.remaining_privacy:
            names = ", ".join(sorted({f.label for f in res.remaining_privacy}))[:200]
            self.banner.show_msg("warn", f"Cópia criada: {os.path.basename(out)}",
                                 f"Atenção: alguns dados pessoais permaneceram ({names}).", acts)
        else:
            self.banner.show_msg("ok", f"Cópia limpa criada: {os.path.basename(out)}",
                                 f"{res.removed} campo(s) removido(s) e verificado(s). O original não foi alterado.", acts)

    # ---- interação
    def _items(self):
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            for j in range(parent.childCount()):
                yield parent.child(j)

    def on_item_changed(self, item, col):
        if self._populating or col != 0:
            return
        f = item.data(0, Qt.ItemDataRole.UserRole)
        if f is not None:
            f.checked = item.checkState(0) == Qt.CheckState.Checked
            if not self._populating:
                self.sync_preset()
                self.selection_changed.emit()

    def on_item_clicked(self, item, col):
        """Clicar em qualquer parte da linha marca/desmarca (não só na caixinha)."""
        prev = self._press_state
        self._press_state = None
        if not prev or prev[0] is not item or item.checkState(0) != prev[1]:
            return
        if item.data(0, Qt.ItemDataRole.UserRole) is None:  # categoria
            new = Qt.CheckState.Unchecked if item.checkState(0) == Qt.CheckState.Checked else Qt.CheckState.Checked
        else:
            new = Qt.CheckState.Unchecked if item.checkState(0) == Qt.CheckState.Checked else Qt.CheckState.Checked
        item.setCheckState(0, new)

    def apply_preset(self, pid: int):
        if not self.entry or not self.entry.info:
            return
        self._populating = True
        for it in self._items():
            f = it.data(0, Qt.ItemDataRole.UserRole)
            f.checked = pid == 0 or (pid == 1 and f.category in PRIVACY)
            it.setCheckState(0, Qt.CheckState.Checked if f.checked else Qt.CheckState.Unchecked)
        self._populating = False
        self.sync_preset()
        self.selection_changed.emit()

    def sync_preset(self):
        fields = self.entry.info.fields if self.entry and self.entry.info else []
        on = {id(f) for f in fields if f.checked}
        if fields and len(on) == len(fields):
            pid = 0
        elif not on:
            pid = 2
        elif on == {id(f) for f in fields if f.category in PRIVACY}:
            pid = 1
        else:
            pid = -1
        self.seg_group.setExclusive(False)
        for b in self.seg_group.buttons():
            b.setChecked(self.seg_group.id(b) == pid)
        self.seg_group.setExclusive(True)

    def apply_filter(self, text: str):
        t = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            visible = 0
            for j in range(parent.childCount()):
                ch = parent.child(j)
                f = ch.data(0, Qt.ItemDataRole.UserRole)
                show = not t or t in f.label.lower() or t in f.value.lower() or t in f.key.lower()
                ch.setHidden(not show)
                visible += show
            parent.setHidden(visible == 0)

    def context_menu(self, pos):
        it = self.tree.itemAt(pos)
        if not it:
            return
        m = QMenu(self)
        a = m.addAction("Copiar valor")
        b = m.addAction("Copiar campo e valor")
        act = m.exec(self.tree.viewport().mapToGlobal(pos))
        if act == a:
            QApplication.clipboard().setText(it.text(1))
        elif act == b:
            QApplication.clipboard().setText(f"{it.text(0)}: {it.text(1)}")

    def open_map(self):
        if self.entry and self.entry.info and self.entry.info.gps:
            lat, lon = self.entry.info.gps
            QDesktopServices.openUrl(QUrl(f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=16/{lat:.6f}/{lon:.6f}"))


def reveal(path: str):
    if os.name == "nt":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))


# --------------------------------------------------------------------------- janela principal

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(asset("icon.png")))
        self.setAcceptDrops(True)
        self.settings = QSettings("LimpaMeta", "LimpaMeta")
        self.entries: dict[str, FileEntry] = {}
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(2, min(6, os.cpu_count() or 2)))
        self.sig = _Signals()
        self.sig.scanned.connect(self.on_scanned)
        self.sig.cleaned.connect(self.on_cleaned)
        self.sig.finished.connect(self.on_clean_finished)
        self.cleaning: list[MediaInfo] = []
        self.clean_ok, self.clean_err = [], []
        self._build()
        self._restore()
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.pick_files)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self.list, activated=self.remove_selected)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.clean_current)

    # ---- montagem
    def _build(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(1)
        outer.addWidget(split, 1)

        # --- barra lateral
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setMinimumWidth(320)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 18, 16, 14)
        sl.setSpacing(12)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(asset("icon.png")).pixmap(28, 28))
        brand.addWidget(logo)
        brand.addWidget(label("LimpaMeta", "Brand"))
        brand.addStretch()
        about = QToolButton()
        about.setIcon(icon("info", C["muted"], 18))
        about.setToolTip("Sobre o LimpaMeta")
        about.setCursor(Qt.CursorShape.PointingHandCursor)
        about.clicked.connect(self.show_about)
        brand.addWidget(about)
        sl.addLayout(brand)

        self.ff_banner = QFrame()
        self.ff_banner.setStyleSheet(f"background: {C['warning_dim']}; border: 1px solid {C['warning']}; border-radius: 10px;")
        fl = QVBoxLayout(self.ff_banner)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.setSpacing(6)
        fh = label("Vídeos precisam do FFmpeg", None)
        fh.setStyleSheet(f"color: {C['warning']}; font-weight: 600; border: none; background: transparent;")
        fs = label("É gratuito. Fotos funcionam sem ele.", None, wrap=True)
        fs.setStyleSheet(f"color: {C['muted']}; border: none; background: transparent;")
        self.ff_btn = button("Instalar FFmpeg", None, "download")
        self.ff_btn.clicked.connect(self.install_ffmpeg)
        fl.addWidget(fh)
        fl.addWidget(fs)
        fl.addWidget(self.ff_btn)
        self.ff_banner.setVisible(not core.has_ffmpeg())
        sl.addWidget(self.ff_banner)

        head = QHBoxLayout()
        self.count_lbl = label("Arquivos", "H2")
        head.addWidget(self.count_lbl)
        head.addStretch()
        for ic_name, tip, fn in (("plus", "Adicionar arquivos (Ctrl+O)", self.pick_files),
                                 ("folder", "Adicionar pasta", self.pick_folder),
                                 ("trash", "Limpar lista", self.clear_list)):
            tb = QToolButton()
            tb.setIcon(icon(ic_name, C["muted"], 18))
            tb.setToolTip(tip)
            tb.setCursor(Qt.CursorShape.PointingHandCursor)
            tb.clicked.connect(fn)
            head.addWidget(tb)
        sl.addLayout(head)

        self.side_stack = QStackedWidget()
        self.drop = DropZone(self.pick_files, self.pick_folder)
        self.list = QListWidget()
        self.list.setItemDelegate(FileDelegate(self))
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.currentItemChanged.connect(self.on_select)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.list_menu)
        self.side_stack.addWidget(self.drop)
        self.side_stack.addWidget(self.list)
        sl.addWidget(self.side_stack, 1)
        self.side_hint = label("Dica: arraste mais arquivos para a janela a qualquer momento.", "Faint", wrap=True)
        self.side_hint.hide()
        sl.addWidget(self.side_hint)
        split.addWidget(side)

        # --- área principal
        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        self.main_stack = QStackedWidget()
        self.welcome = Welcome()
        self.detail = DetailPanel(self)
        self.detail.selection_changed.connect(self.update_actions)
        self.main_stack.addWidget(self.welcome)
        self.main_stack.addWidget(self.detail)
        ml.addWidget(self.main_stack, 1)

        footer = QFrame()
        footer.setObjectName("Footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(28, 14, 28, 14)
        fl.setSpacing(12)
        fl.addWidget(label("Salvar cópias em", "Muted"))
        self.out_combo = QComboBox()
        self.out_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.out_combo.activated.connect(self.on_out_combo)
        fl.addWidget(self.out_combo)
        fl.addSpacing(8)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(160)
        self.progress.hide()
        self.progress_lbl = label("", "Muted")
        fl.addWidget(self.progress)
        fl.addWidget(self.progress_lbl, 1)
        fl.addStretch()
        self.sel_lbl = label("", "Muted")
        self.sel_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        for lb in (self.sel_lbl, self.progress_lbl):  # textos não podem alargar a janela
            lb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            lb.setMinimumWidth(40)
        self.sel_lbl.setMinimumWidth(190)
        fl.addWidget(self.sel_lbl, 1)
        self.btn_all = button("Limpar todos", None, "sparkle")
        self.btn_all.setToolTip("Cria cópias limpas de todos os arquivos da lista,\nusando o que estiver marcado em cada um.")
        self.btn_all.clicked.connect(self.clean_all)
        self.btn_one = button("Criar cópia limpa", "Primary", "shield", "#ffffff")
        self.btn_one.setToolTip("Ctrl+Enter")
        self.btn_one.clicked.connect(self.clean_current)
        fl.addWidget(self.btn_all)
        fl.addWidget(self.btn_one)
        ml.addWidget(footer)
        split.addWidget(main)
        split.setStretchFactor(1, 1)
        split.setSizes([360, 960])

        self.overlay = DropOverlay(root)
        self.update_actions()

    def _restore(self):
        geo = self.settings.value("geometry")
        if geo is None or not self.restoreGeometry(geo):
            self.resize(1320, 820)
            scr = QApplication.primaryScreen().availableGeometry()
            self.resize(min(1320, scr.width() - 80), min(820, scr.height() - 80))
            self.move(scr.center() - self.rect().center())
        self.out_dir = self.settings.value("out_dir", "") or ""
        self.refresh_out_combo()

    def closeEvent(self, ev):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("out_dir", self.out_dir)
        super().closeEvent(ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.overlay.setGeometry(self.centralWidget().rect())

    # ---- destino
    def refresh_out_combo(self):
        self.out_combo.clear()
        self.out_combo.addItem(icon("folder", C["muted"], 16), "Mesma pasta do original")
        if self.out_dir:
            self.out_combo.addItem(icon("folder", C["accent"], 16), _short_path(self.out_dir))
            self.out_combo.setItemData(1, self.out_dir, Qt.ItemDataRole.ToolTipRole)
        self.out_combo.addItem("Escolher outra pasta…")
        self.out_combo.setCurrentIndex(1 if self.out_dir and self.settings.value("use_out_dir", False, bool) else 0)

    def on_out_combo(self, idx):
        last = self.out_combo.count() - 1
        if idx == last:
            d = QFileDialog.getExistingDirectory(self, "Onde salvar as cópias limpas", self.out_dir or os.path.expanduser("~"))
            if d:
                self.out_dir = d
                self.settings.setValue("use_out_dir", True)
            self.refresh_out_combo()
        else:
            self.settings.setValue("use_out_dir", idx == 1 and bool(self.out_dir))

    def current_out_dir(self) -> str | None:
        return self.out_dir if (self.out_dir and self.out_combo.currentIndex() == 1) else None

    # ---- arquivos
    def pick_files(self):
        exts = " ".join(f"*{e}" for e in sorted(core.SUPPORTED_EXT))
        files, _ = QFileDialog.getOpenFileNames(self, "Escolha fotos e vídeos", self.settings.value("last_dir", ""),
                                                f"Fotos e vídeos ({exts});;Todos os arquivos (*.*)")
        if files:
            self.settings.setValue("last_dir", os.path.dirname(files[0]))
            self.add_paths(files)

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Escolha uma pasta", self.settings.value("last_dir", ""))
        if d:
            self.settings.setValue("last_dir", d)
            self.add_paths([d])

    def add_paths(self, paths, select: bool = False):
        files = core.expand_paths(paths)
        if not files:
            if paths:
                self.toast("Nenhuma foto ou vídeo compatível encontrado.")
            return
        first = None
        for p in files:
            p = os.path.normpath(p)
            if p in self.entries:
                first = first or p
                continue
            e = FileEntry(p)
            self.entries[p] = e
            it = QListWidgetItem()
            it.setData(ROLE_PATH, p)
            it.setToolTip(p)
            self.list.addItem(it)
            self.pool.start(ScanTask(p, self.sig))
            first = first or p
        self.side_stack.setCurrentWidget(self.list)
        self.update_count()
        if first and (select or self.list.currentItem() is None):
            self.select_path(first)

    def select_path(self, path):
        for i in range(self.list.count()):
            if self.list.item(i).data(ROLE_PATH) == path:
                self.list.setCurrentRow(i)
                return

    def on_scanned(self, path, info, img):
        e = self.entries.get(path)
        if not e:
            return
        e.info = info
        e.state = "error" if info.error else "ready"
        e.error = info.error
        if img is not None and not img.isNull():
            e.thumb_img = img
            e.thumb = QPixmap.fromImage(img)
        self.list.viewport().update()
        if self.detail.entry is e:
            self.detail.show_entry(e)
        self.update_actions()

    def on_select(self, cur, _prev=None):
        if cur is None:
            self.main_stack.setCurrentWidget(self.welcome)
            self.detail.entry = None
        else:
            self.main_stack.setCurrentWidget(self.detail)
            self.detail.show_entry(self.entries[cur.data(ROLE_PATH)])
        self.update_actions()

    def remove_selected(self):
        it = self.list.currentItem()
        if it:
            self.entries.pop(it.data(ROLE_PATH), None)
            self.list.takeItem(self.list.row(it))
        self._after_remove()

    def clear_list(self):
        if not self.entries or self.cleaning:
            return
        self.entries.clear()
        self.list.clear()
        self._after_remove()

    def _after_remove(self):
        if not self.entries:
            self.side_stack.setCurrentWidget(self.drop)
            self.main_stack.setCurrentWidget(self.welcome)
            self.detail.entry = None
        self.update_count()
        self.update_actions()

    def list_menu(self, pos):
        it = self.list.itemAt(pos)
        if not it:
            return
        e = self.entries[it.data(ROLE_PATH)]
        m = QMenu(self)
        a1 = m.addAction("Mostrar na pasta")
        a2 = m.addAction("Abrir")
        a3 = m.addAction("Remover da lista")
        act = m.exec(self.list.viewport().mapToGlobal(pos))
        if act == a1:
            reveal(e.path)
        elif act == a2:
            os.startfile(e.path)
        elif act == a3:
            self.list.setCurrentItem(it)
            self.remove_selected()

    def update_count(self):
        n = len(self.entries)
        self.count_lbl.setText(f"Arquivos  ·  {n}" if n else "Arquivos")
        self.side_hint.setVisible(n > 0)

    # ---- limpeza
    def ready_entries(self):
        return [e for e in self.entries.values() if e.state in ("ready", "cleaned") and e.info and e.info.fields]

    def update_actions(self):
        e = self.detail.entry if self.main_stack.currentWidget() is self.detail else None
        busy = bool(self.cleaning)
        if e and e.info and not e.info.error and e.state != "scanning":
            total = len(e.info.fields)
            on = sum(f.checked for f in e.info.fields)
            self.sel_lbl.setText(f"{on} de {total} campos marcados" if total else "")
            self.btn_one.setEnabled(on > 0 and not busy)
        else:
            self.sel_lbl.setText("")
            self.btn_one.setEnabled(False)
        n = len(self.ready_entries())
        self.btn_all.setText(f"Limpar todos ({n})" if n else "Limpar todos")
        self.btn_all.setEnabled(n > 0 and not busy)
        scanning = sum(1 for x in self.entries.values() if x.state == "scanning")
        if not busy:
            self.progress_lbl.setText(f"Analisando {scanning} arquivo(s)…" if scanning else "")

    def clean_current(self):
        e = self.detail.entry
        if not e or not e.info or self.cleaning or not self.btn_one.isEnabled():
            return
        self._start_clean([e])

    def clean_all(self):
        entries = self.ready_entries()
        if not entries or self.cleaning:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Limpar todos os arquivos")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Criar cópias limpas de {len(entries)} arquivo(s)?")
        box.setInformativeText("Cada arquivo usa o que estiver marcado nele (por padrão, todos os metadados).\n"
                               "Os originais não serão alterados.")
        ok = box.addButton("Limpar todos", QMessageBox.ButtonRole.AcceptRole)
        ok.setObjectName("Primary")
        box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is ok:
            self._start_clean([e for e in entries if any(f.checked for f in e.info.fields)])

    def _start_clean(self, entries):
        if not entries:
            return
        self.cleaning = [e.info for e in entries]
        self.clean_ok, self.clean_err = [], []
        for e in entries:
            e.state = "cleaning"
        self.list.viewport().update()
        self.progress.setRange(0, len(entries))
        self.progress.setValue(0)
        self.progress.show()
        self.progress_lbl.setText(f"Limpando 0 de {len(entries)}…")
        self.update_actions()
        self.pool.start(CleanTask(self.cleaning, self.current_out_dir(), self.sig))

    def on_cleaned(self, i, path, res, err):
        e = self.entries.get(path)
        if e:
            # em caso de falha o arquivo continua utilizável; o erro aparece no aviso
            e.state = "ready" if err else "cleaned"
            e.result = res
        (self.clean_err if err else self.clean_ok).append((path, res or err))
        self.progress.setValue(i + 1)
        self.progress_lbl.setText(f"Limpando {i + 1} de {len(self.cleaning)}…")
        self.list.viewport().update()

    def on_clean_finished(self):
        total = len(self.cleaning)
        self.cleaning = []
        self.progress.hide()
        self.progress_lbl.setText("")
        self.update_actions()
        cur = self.detail.entry
        if total == 1 and self.clean_ok and cur and cur.path == self.clean_ok[0][0]:
            self.detail.show_entry(cur)
        elif total == 1 and self.clean_err:
            self.detail.banner.show_msg("error", "Não foi possível limpar este arquivo", self.clean_err[0][1])
        else:
            outs = [r.output for _, r in self.clean_ok]
            warn = sum(1 for _, r in self.clean_ok if r.remaining_privacy)
            folder = os.path.dirname(outs[0]) if outs else None
            acts = [("Abrir pasta", lambda: os.startfile(folder))] if folder else []
            if self.clean_err:
                acts.append(("Ver erros", self.show_errors))
                self.detail.banner.show_msg("warn", f"{len(outs)} cópia(s) limpa(s) · {len(self.clean_err)} erro(s)",
                                            "Alguns arquivos não puderam ser limpos.", acts)
            else:
                sub = "Todas verificadas. Os originais não foram alterados."
                if warn:
                    sub = f"{warn} arquivo(s) ainda contêm algum dado pessoal — selecione-os para ver detalhes."
                self.detail.banner.show_msg("ok" if not warn else "warn", f"{len(outs)} cópia(s) limpa(s) criada(s)", sub, acts)
            if self.main_stack.currentWidget() is not self.detail and self.list.count():
                self.list.setCurrentRow(0)

    def show_errors(self):
        txt = "\n\n".join(f"{os.path.basename(p)}\n{err}" for p, err in self.clean_err)
        box = QMessageBox(self)
        box.setWindowTitle("Erros")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("Estes arquivos não puderam ser limpos:")
        box.setDetailedText(txt)
        box.setInformativeText(txt[:600])
        box.exec()

    # ---- ffmpeg
    def install_ffmpeg(self):
        self.ff_btn.setEnabled(False)
        self.ff_btn.setText("Instalando… (pode levar alguns minutos)")

        def work():
            try:
                r = subprocess.run(["winget", "install", "-e", "--id", "Gyan.FFmpeg", "--scope", "user",
                                    "--accept-package-agreements", "--accept-source-agreements",
                                    "--disable-interactivity"], capture_output=True, creationflags=core.NO_WINDOW,
                                   timeout=1800)
                ok = r.returncode == 0
            except Exception:
                ok = False
            QTimer.singleShot(0, lambda: self._ffmpeg_done(ok))

        import threading
        threading.Thread(target=work, daemon=True).start()

    def _ffmpeg_done(self, ok):
        core.reset_tool_cache()
        if core.has_ffmpeg():
            self.ff_banner.hide()
            self.toast("FFmpeg instalado. Vídeos já podem ser analisados.")
            for e in list(self.entries.values()):
                if e.kind == "video" and e.state == "error":
                    e.state = "scanning"
                    self.pool.start(ScanTask(e.path, self.sig))
        else:
            self.ff_btn.setEnabled(True)
            self.ff_btn.setText("Tentar novamente")
            QMessageBox.warning(self, "FFmpeg", "Não foi possível instalar automaticamente.\n"
                                "Instale manualmente com:  winget install Gyan.FFmpeg\n"
                                "e depois reabra o LimpaMeta.")

    # ---- diversos
    def toast(self, text: str):
        if self.main_stack.currentWidget() is self.detail:
            self.detail.banner.show_msg("info", text)
        else:
            self.progress_lbl.setText(text)
            QTimer.singleShot(4000, lambda: self.progress_lbl.setText(""))

    def show_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Sobre o LimpaMeta")
        dlg.setFixedWidth(440)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(24, 24, 24, 20)
        lay.setSpacing(10)
        top = QHBoxLayout()
        lg = QLabel()
        lg.setPixmap(QIcon(asset("icon.png")).pixmap(56, 56))
        top.addWidget(lg)
        col = QVBoxLayout()
        col.addWidget(label("LimpaMeta", "H1"))
        col.addWidget(label(f"Versão {__version__}", "Muted"))
        top.addLayout(col, 1)
        lay.addLayout(top)
        lay.addWidget(label("Mostra e remove metadados de fotos e vídeos, criando cópias limpas. "
                            "Tudo acontece no seu computador — nada é enviado para a internet.", "Muted", wrap=True))
        lay.addWidget(hline())
        ff = core.find_tool("ffmpeg")
        lay.addWidget(label(f"FFmpeg: {'encontrado' if ff else 'não encontrado'}", "Faint"))
        if ff:
            lay.addWidget(label(ff, "Faint", wrap=True))
        lay.addWidget(label(f"Registros: {LOG_DIR}", "Faint", wrap=True))
        row = QHBoxLayout()
        gh = button("Projeto no GitHub", None, "external")
        gh.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        logs = button("Abrir registros", None, "folder")
        logs.clicked.connect(lambda: os.startfile(LOG_DIR))
        close = button("Fechar", "Primary")
        close.clicked.connect(dlg.accept)
        row.addWidget(gh)
        row.addWidget(logs)
        row.addStretch()
        row.addWidget(close)
        lay.addSpacing(6)
        lay.addLayout(row)
        dlg.exec()

    # ---- arrastar e soltar
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()
            self.overlay.setGeometry(self.centralWidget().rect())
            self.overlay.raise_()
            self.overlay.show()

    def dragMoveEvent(self, ev):
        ev.acceptProposedAction()

    def dragLeaveEvent(self, ev):
        self.overlay.hide()

    def dropEvent(self, ev):
        self.overlay.hide()
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        self.add_paths(paths, select=True)


def _short_path(p: str, n: int = 38) -> str:
    return p if len(p) <= n else "…" + p[-(n - 1):]


# --------------------------------------------------------------------------- inicialização

def _setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logging.basicConfig(filename=os.path.join(LOG_DIR, "limpameta.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")


def _excepthook(exc_type, exc, tb):
    msg = "".join(traceback.format_exception(exc_type, exc, tb))
    log.error("erro não tratado:\n%s", msg)
    try:
        QMessageBox.critical(None, "LimpaMeta — erro inesperado",
                             f"Ocorreu um erro inesperado:\n\n{exc}\n\nDetalhes foram salvos em:\n{LOG_DIR}")
    except Exception:
        pass


def _palette() -> QPalette:
    pal = QPalette()
    for role, col in ((QPalette.ColorRole.Window, C["bg"]), (QPalette.ColorRole.WindowText, C["text"]),
                      (QPalette.ColorRole.Base, C["surface"]), (QPalette.ColorRole.AlternateBase, C["surface2"]),
                      (QPalette.ColorRole.Text, C["text"]), (QPalette.ColorRole.Button, C["surface2"]),
                      (QPalette.ColorRole.ButtonText, C["text"]), (QPalette.ColorRole.Highlight, C["accent"]),
                      (QPalette.ColorRole.HighlightedText, "#ffffff"), (QPalette.ColorRole.ToolTipBase, C["surface3"]),
                      (QPalette.ColorRole.ToolTipText, C["text"]), (QPalette.ColorRole.PlaceholderText, C["faint"])):
        pal.setColor(role, QColor(col))
    return pal


def bring_to_front(win: QMainWindow):
    """Garante que a janela está restaurada, dentro de um monitor e em primeiro plano."""
    if win.isMinimized():
        win.setWindowState(win.windowState() & ~Qt.WindowState.WindowMinimized)
        win.showNormal()
    screens = [s.availableGeometry() for s in QApplication.screens()]
    if not any(s.intersects(win.frameGeometry()) for s in screens):
        scr = QApplication.primaryScreen().availableGeometry()
        win.resize(min(win.width(), scr.width() - 40), min(win.height(), scr.height() - 40))
        win.move(scr.center() - win.rect().center())
    win.raise_()
    win.activateWindow()
    if os.name == "nt":
        try:
            import ctypes
            hwnd = int(win.winId())
            user32 = ctypes.windll.user32
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            # truque padrão para o Windows permitir trazer a janela para frente
            fg = user32.GetForegroundWindow()
            cur = ctypes.windll.kernel32.GetCurrentThreadId()
            other = user32.GetWindowThreadProcessId(fg, None)
            if other and other != cur:
                user32.AttachThreadInput(other, cur, True)
                user32.SetForegroundWindow(hwnd)
                user32.AttachThreadInput(other, cur, False)
            else:
                user32.SetForegroundWindow(hwnd)
        except Exception:
            log.exception("bring_to_front")


def main(argv=None):
    _setup_logging()
    sys.excepthook = _excepthook
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("igorcacerez.LimpaMeta")
        except Exception:
            pass
    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setStyleSheet(stylesheet())
    app.setWindowIcon(QIcon(asset("icon.png")))
    log.info("LimpaMeta %s iniciado; ffmpeg=%s", __version__, core.find_tool("ffmpeg"))
    win = MainWindow()
    win.setWindowState(Qt.WindowState.WindowNoState)
    win.showNormal()
    bring_to_front(win)
    # O Windows às vezes abre a janela minimizada quando o app é iniciado pelo Explorador
    # (proteção contra "roubo de foco"). Confere de novo logo depois e restaura se preciso.
    QTimer.singleShot(250, lambda: bring_to_front(win))
    QTimer.singleShot(1000, lambda: bring_to_front(win))
    if os.environ.get("LIMPAMETA_SMOKETEST"):  # usado pelo build para validar o .exe
        QTimer.singleShot(1500, app.quit)
    args = [a for a in app.arguments()[1:] if os.path.exists(a)]
    if args:
        win.add_paths(args, select=True)
    return app.exec()
