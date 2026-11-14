import os
import subprocess
import sys

import pytest
from PIL import Image, ImageCms, PngImagePlugin

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from limpameta import core  # noqa: E402
from limpameta.core import AUTHOR, DATE, DEVICE, LOCATION, PRIVACY  # noqa: E402

XMP = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
       b'<rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:CreatorTool="Lightroom"/></rdf:RDF></x:xmpmeta>')


def make_exif():
    e = Image.Exif()
    e[0x010F] = "Canon"
    e[0x0110] = "EOS 80D"
    e[0x0132] = "2024:05:01 10:00:00"
    e[0x013B] = "Fulano"
    g = e.get_ifd(0x8825)
    g[1], g[2], g[3], g[4] = "S", (23.0, 33.0, 0.0), "W", (46.0, 38.0, 0.0)
    return e


def picture():
    im = Image.new("RGB", (64, 48))
    im.putdata([(x * 4 % 256, y * 5 % 256, (x * y) % 256) for y in range(48) for x in range(64)])
    return im


def pixels(path):
    with Image.open(path) as im:
        return im.convert("RGB").tobytes()


def privacy(info):
    return [f for f in info.fields if f.category in PRIVACY]


@pytest.fixture
def jpg(tmp_path):
    p = tmp_path / "foto.jpg"
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    picture().save(p, exif=make_exif().tobytes(), icc_profile=icc, comment=b"segredo", xmp=XMP, quality=90)
    return str(p)


def test_jpeg_read(jpg):
    info = core.read_media(jpg)
    assert info.error is None
    cats = {f.category for f in info.fields}
    assert {LOCATION, DEVICE, DATE, AUTHOR} <= cats
    assert info.risk == "high"
    lat, lon = info.gps
    assert lat == pytest.approx(-23.55, abs=0.01) and lon == pytest.approx(-46.633, abs=0.01)


def test_jpeg_clean_all_is_lossless(jpg):
    info = core.read_media(jpg)
    res = core.clean_media(info)
    after = core.read_media(res.output)
    assert [f for f in after.fields if f.category != "color"] == [] and not after.fields
    assert pixels(jpg) == pixels(res.output)
    assert res.remaining_privacy == []


def test_jpeg_clean_only_location(jpg):
    info = core.read_media(jpg)
    loc = [f for f in info.fields if f.category == LOCATION]
    res = core.clean_media(info, loc)
    after = core.read_media(res.output)
    assert not any(f.category == LOCATION for f in after.fields)
    keys = {f.key for f in after.fields}
    assert {"Make", "Model", "Artist", "XMP"} <= keys
    assert pixels(jpg) == pixels(res.output)


def test_png(tmp_path):
    p = str(tmp_path / "a.png")
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Author", "Fulano")
    meta.add_itxt("Comment", "olá", zip=True)
    picture().save(p, pnginfo=meta, exif=make_exif().tobytes())
    info = core.read_media(p)
    assert {"Author", "Comment", "GPSLatitude"} <= {f.key for f in info.fields}
    only_author = [f for f in info.fields if f.key == "Author"]
    after = core.read_media(core.clean_media(info, only_author).output)
    assert "Author" not in {f.key for f in after.fields} and "GPSLatitude" in {f.key for f in after.fields}
    res = core.clean_media(core.read_media(p))
    assert core.read_media(res.output).fields == [] and pixels(p) == pixels(res.output)


def test_webp(tmp_path):
    p = str(tmp_path / "a.webp")
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    picture().save(p, exif=make_exif().tobytes(), xmp=XMP, icc_profile=icc, lossless=True)
    info = core.read_media(p)
    assert info.risk == "high"
    res = core.clean_media(info)
    assert core.read_media(res.output).fields == []
    assert pixels(p) == pixels(res.output)
    gps = [f for f in core.read_media(p).fields if f.category == LOCATION]
    after = core.read_media(core.clean_media(core.read_media(p), gps).output)
    assert not any(f.category == LOCATION for f in after.fields) and any(f.key == "Make" for f in after.fields)


@pytest.mark.skipif(not core.HAS_HEIF, reason="pillow-heif ausente")
def test_heic(tmp_path):
    p = str(tmp_path / "a.heic")
    picture().save(p, exif=make_exif().tobytes(), quality=90)
    info = core.read_media(p)
    assert info.risk == "high"
    assert privacy(core.read_media(core.clean_media(info).output)) == []


def test_gif_comment(tmp_path):
    p = str(tmp_path / "a.gif")
    picture().convert("P").save(p, comment=b"feito por fulano")
    info = core.read_media(p)
    assert any(f.key == "comment" for f in info.fields)
    assert core.read_media(core.clean_media(info).output).fields == []


needs_ffmpeg = pytest.mark.skipif(not core.has_ffmpeg(), reason="ffmpeg ausente")


def make_video(path, extra=()):
    ff = core.find_tool("ffmpeg")
    subprocess.run([ff, "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=d=1:s=160x120",
                    "-f", "lavfi", "-i", "sine=d=1", "-shortest", "-metadata", "title=Viagem",
                    "-metadata", "comment=privado", "-metadata", "location=+23.5505-046.6333/",
                    "-metadata", "creation_time=2024-05-01T10:00:00Z", *extra, path], check=True)


@needs_ffmpeg
@pytest.mark.parametrize("ext", [".mp4", ".mov", ".mkv"])
def test_video_clean_all(tmp_path, ext):
    p = str(tmp_path / ("v" + ext))
    make_video(p)
    info = core.read_media(p)
    assert info.error is None and privacy(info)
    res = core.clean_media(info)
    after = core.read_media(res.output)
    assert privacy(after) == [], [(f.key, f.value) for f in privacy(after)]
    assert after.streams == info.streams


@needs_ffmpeg
def test_video_selective(tmp_path):
    p = str(tmp_path / "v.mp4")
    make_video(p)
    info = core.read_media(p)
    title = [f for f in info.fields if f.key == "title"]
    after = core.read_media(core.clean_media(info, title).output)
    keys = {f.key for f in after.fields}
    assert "title" not in keys and "comment" in keys and "location" in keys


def test_output_path_never_overwrites(tmp_path):
    src = tmp_path / "x.jpg"
    src.write_bytes(b"")
    first = core.output_path(str(src))
    open(first, "w").close()
    assert core.output_path(str(src)) != first


def test_broken_file(tmp_path):
    p = tmp_path / "quebrado.jpg"
    p.write_bytes(b"isso nao e uma imagem")
    info = core.read_media(str(p))
    assert info.error
    with pytest.raises(core.MetaError):
        core.clean_media(info)
