"""Gera amostras fictícias e salva capturas da interface em docs/."""
import os, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from PIL import Image, ImageCms, ImageDraw
from PySide6.QtWidgets import QApplication
from limpameta import core, ui

D = os.path.join(tempfile.gettempdir(), "Fotos de exemplo")
os.makedirs(D, exist_ok=True)
for f in os.listdir(D):
    os.remove(os.path.join(D, f))

def photo(path, color, **kw):
    im = Image.new("RGB", (1200, 800), color)
    dr = ImageDraw.Draw(im)
    for i in range(0, 1200, 40):
        dr.line((i, 800, i + 400, 0), fill=tuple(min(255, c + 25) for c in color), width=14)
    dr.ellipse((820, 120, 1020, 320), fill=(255, 214, 120))
    im.save(path, **kw)

e = Image.Exif()
e[0x010F], e[0x0110], e[0x0131] = "Apple", "iPhone 15 Pro", "17.4.1"
e[0x0132], e[0x013B] = "2024:05:01 10:00:00", "Maria Exemplo"
ex = e.get_ifd(0x8769); ex[0x9003] = "2024:05:01 10:00:00"; ex[0xA434] = "iPhone 15 Pro back camera"
g = e.get_ifd(0x8825); g[1], g[2], g[3], g[4] = "S", (22.0, 57.0, 6.8), "W", (43.0, 12.0, 37.4)
g[6] = 12.5
icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
photo(f"{D}/praia_ferias.jpg", (40, 120, 190), exif=e.tobytes(), icc_profile=icc, quality=92)
e2 = Image.Exif(); e2[0x010F], e2[0x0110], e2[0x0132] = "Canon", "EOS R6", "2023:12:24 21:30:00"; e2[0x013B] = "Estúdio Exemplo"
photo(f"{D}/retrato_natal.jpg", (150, 60, 70), exif=e2.tobytes(), quality=92)
photo(f"{D}/print_tela.png", (60, 60, 70))
ff = core.find_tool("ffmpeg")
subprocess.run([ff, "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=d=3:s=1280x720", "-f", "lavfi",
                "-i", "sine=d=3", "-shortest", "-metadata", "title=Aniversário", "-metadata", "location=+22.9519-043.2105/",
                "-metadata", "com.apple.quicktime.make=Apple", "-metadata", "creation_time=2024-06-10T18:00:00Z",
                "-movflags", "+use_metadata_tags", f"{D}/aniversario.mov"], check=True)

app = QApplication(sys.argv)
ui._setup_logging()
app.setStyle("Fusion"); app.setPalette(ui._palette()); app.setStyleSheet(ui.stylesheet())
w = ui.MainWindow(); w.settings.clear(); w.out_dir = ""; w.refresh_out_combo()
w.resize(1360, 860); w.show()
out = os.path.join(ROOT, "docs")
os.makedirs(out, exist_ok=True)

def snap(name):
    for _ in range(20):
        app.processEvents(); time.sleep(0.03)
    w.grab().save(os.path.join(out, name))

def wait_scans():
    for _ in range(300):
        app.processEvents()
        if all(x.state != "scanning" for x in w.entries.values()):
            return
        time.sleep(0.05)

snap("01-inicio.png")
w.add_paths([f"{D}/praia_ferias.jpg", f"{D}/aniversario.mov", f"{D}/retrato_natal.jpg", f"{D}/print_tela.png"])
wait_scans(); w.select_path(os.path.normpath(f"{D}/praia_ferias.jpg")); snap("02-foto.png")
w.select_path(os.path.normpath(f"{D}/aniversario.mov")); snap("03-video.png")
w.select_path(os.path.normpath(f"{D}/praia_ferias.jpg")); w.detail.apply_preset(1); snap("04-privacidade.png")
w.detail.apply_preset(0); w.clean_current()
for _ in range(300):
    app.processEvents()
    if not w.cleaning: break
    time.sleep(0.05)
snap("05-pronto.png")
w.close()
print("ok", os.listdir(out))
