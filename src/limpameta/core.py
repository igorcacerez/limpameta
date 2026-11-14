"""Leitura e remoção de metadados de fotos e vídeos.

JPEG, PNG e WebP são limpos sem recompressão: os blocos de metadados são
removidos ou reescritos diretamente no arquivo e os pixels ficam idênticos.
Vídeos são remuxados pelo ffmpeg com ``-c copy`` (sem recodificar).
"""
from __future__ import annotations

import glob
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zlib
from dataclasses import dataclass, field

from PIL import ExifTags, Image

try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HAS_HEIF = True
except Exception:  # pragma: no cover
    HAS_HEIF = False

# --------------------------------------------------------------------------- tipos

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic", ".heif", ".avif", ".gif", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".3gp", ".mts", ".m2ts", ".wmv", ".flv"}
SUPPORTED_EXT = IMAGE_EXT | VIDEO_EXT

LOCATION, DEVICE, DATE, AUTHOR, COLOR, TECH = "location", "device", "date", "author", "color", "tech"
CATEGORY_ORDER = [LOCATION, DEVICE, DATE, AUTHOR, COLOR, TECH]
CATEGORIES = {
    LOCATION: ("Localização", "Coordenadas de GPS e endereço de onde o arquivo foi criado"),
    DEVICE: ("Aparelho e software", "Fabricante, modelo, número de série e programas usados"),
    DATE: ("Datas e horários", "Quando o arquivo foi criado, editado ou digitalizado"),
    AUTHOR: ("Autoria e conteúdo", "Nome do autor, títulos, comentários e miniaturas"),
    COLOR: ("Perfil de cor", "Ajuda a exibir as cores corretamente — em geral é seguro manter"),
    TECH: ("Técnicos", "Informações de formato que não identificam você"),
}
PRIVACY = {LOCATION, DEVICE, DATE, AUTHOR}


@dataclass
class Field:
    category: str
    group: str
    key: str
    label: str
    value: str
    ref: tuple
    checked: bool = True


@dataclass
class MediaInfo:
    path: str
    kind: str  # "image" | "video"
    fields: list[Field] = field(default_factory=list)
    size: int = 0
    details: str = ""
    gps: tuple[float, float] | None = None
    error: str | None = None
    note: str | None = None  # aviso exibido na interface (ex.: recompressão)
    streams: int = 0

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    def count(self, cat: str) -> int:
        return sum(1 for f in self.fields if f.category == cat)

    @property
    def risk(self) -> str:
        cats = {f.category for f in self.fields}
        if LOCATION in cats:
            return "high"
        if cats & PRIVACY:
            return "medium"
        if cats:
            return "low"
        return "clean"


@dataclass
class CleanResult:
    source: str
    output: str
    removed: int
    remaining_privacy: list[Field]


class MetaError(Exception):
    pass


# --------------------------------------------------------------------------- ffmpeg

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ffmpeg_cache: dict[str, str | None] = {}


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_tool(name: str) -> str | None:
    if name in _ffmpeg_cache:
        return _ffmpeg_cache[name]
    exe = name + (".exe" if os.name == "nt" else "")
    local = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(_app_dir(), "ffmpeg", exe),
        os.path.join(_app_dir(), exe),
        shutil.which(name),
        os.path.join(local, "Microsoft", "WinGet", "Links", exe),
        *glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "*", "bin", exe)),
        os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), "chocolatey", "bin", exe),
        os.path.join(os.path.expanduser("~"), "scoop", "shims", exe),
        os.path.join("C:\\", "ffmpeg", "bin", exe),
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "ffmpeg", "bin", exe),
    ]
    found = next((c for c in candidates if c and os.path.isfile(c)), None)
    _ffmpeg_cache[name] = found
    return found


def reset_tool_cache() -> None:
    _ffmpeg_cache.clear()


def has_ffmpeg() -> bool:
    return bool(find_tool("ffmpeg") and find_tool("ffprobe"))


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout,
                          creationflags=NO_WINDOW)


# --------------------------------------------------------------------------- rótulos

EXIF_LABELS = {
    "Make": "Fabricante", "Model": "Modelo", "Software": "Software", "HostComputer": "Computador",
    "LensMake": "Fabricante da lente", "LensModel": "Modelo da lente", "LensSerialNumber": "Nº de série da lente",
    "BodySerialNumber": "Nº de série da câmera", "CameraOwnerName": "Dono da câmera", "MakerNote": "Dados do fabricante",
    "DateTime": "Data de modificação", "DateTimeOriginal": "Data em que foi tirada",
    "DateTimeDigitized": "Data de digitalização", "OffsetTime": "Fuso horário", "OffsetTimeOriginal": "Fuso horário (original)",
    "OffsetTimeDigitized": "Fuso horário (digitalização)", "SubsecTime": "Fração de segundo",
    "SubsecTimeOriginal": "Fração de segundo (original)", "SubsecTimeDigitized": "Fração de segundo (digitalização)",
    "Artist": "Autor", "Copyright": "Direitos autorais", "ImageDescription": "Descrição", "UserComment": "Comentário",
    "XPTitle": "Título (Windows)", "XPComment": "Comentário (Windows)", "XPAuthor": "Autor (Windows)",
    "XPKeywords": "Palavras-chave (Windows)", "XPSubject": "Assunto (Windows)", "ImageUniqueID": "ID único da imagem",
    "GPSLatitude": "Latitude", "GPSLatitudeRef": "Hemisfério (latitude)", "GPSLongitude": "Longitude",
    "GPSLongitudeRef": "Hemisfério (longitude)", "GPSAltitude": "Altitude", "GPSAltitudeRef": "Referência da altitude",
    "GPSTimeStamp": "Horário do GPS", "GPSDateStamp": "Data do GPS", "GPSSpeed": "Velocidade",
    "GPSImgDirection": "Direção da câmera", "GPSDestBearing": "Direção do destino", "GPSHPositioningError": "Precisão do GPS",
    "GPSProcessingMethod": "Método do GPS", "GPSVersionID": "Versão do GPS",
    "Orientation": "Orientação", "XResolution": "Resolução horizontal", "YResolution": "Resolução vertical",
    "ExposureTime": "Tempo de exposição", "FNumber": "Abertura (f)", "ISOSpeedRatings": "ISO", "FocalLength": "Distância focal",
    "Flash": "Flash", "WhiteBalance": "Balanço de branco", "ColorSpace": "Espaço de cor",
}
VIDEO_LABELS = {
    "title": "Título", "comment": "Comentário", "description": "Descrição", "synopsis": "Sinopse", "artist": "Artista",
    "album_artist": "Artista do álbum", "album": "Álbum", "author": "Autor", "composer": "Compositor",
    "copyright": "Direitos autorais", "genre": "Gênero", "keywords": "Palavras-chave", "date": "Data",
    "creation_time": "Data de criação", "location": "Localização (GPS)", "location-eng": "Localização (GPS)",
    "com.apple.quicktime.location.ISO6709": "Localização (GPS)", "com.apple.quicktime.make": "Fabricante",
    "com.apple.quicktime.model": "Modelo", "com.apple.quicktime.software": "Versão do sistema",
    "com.apple.quicktime.creationdate": "Data de criação", "com.android.version": "Versão do Android",
    "com.android.capture.fps": "Quadros por segundo da captura", "encoder": "Programa que gerou o arquivo",
    "handler_name": "Nome da trilha", "vendor_id": "Fornecedor", "language": "Idioma",
    "major_brand": "Formato (marca)", "minor_version": "Versão do formato", "compatible_brands": "Formatos compatíveis",
}

_DEVICE_WORDS = ("make", "model", "lens", "serial", "software", "hostcomputer", "makernote", "encoder",
                 "android.version", "vendor", "device", "camera")
_LOCATION_WORDS = ("gps", "location", "iso6709", "latitude", "longitude", "altitude")
_AUTHOR_WORDS = ("artist", "author", "copyright", "owner", "title", "comment", "description", "synopsis", "album",
                 "composer", "genre", "keyword", "subject", "uniqueid", "xp")
_TECH_OVERRIDE = {"major_brand", "minor_version", "compatible_brands", "handler_name", "language",
                  "colorspace", "orientation", "timecode"}


def categorize(key: str, group: str = "") -> str:
    k = key.lower()
    if k in _TECH_OVERRIDE:
        return TECH
    if group == "GPS" or any(w in k for w in _LOCATION_WORDS):
        return LOCATION
    if any(w in k for w in _DEVICE_WORDS):
        return DEVICE
    if ("date" in k or "time" in k) and "exposure" not in k:
        return DATE
    if any(w in k for w in _AUTHOR_WORDS):
        return AUTHOR
    if "icc" in k:
        return COLOR
    return TECH


def _fmt(val, limit: int = 300) -> str:
    if isinstance(val, bytes):
        if len(val) > 64:
            return f"{len(val):,} bytes de dados binários".replace(",", ".")
        try:
            txt = val.decode("utf-16-le") if val[1:2] == b"\x00" else val.decode("utf-8")
            txt = txt.strip("\x00").strip()
            if txt and txt.isprintable():
                return txt[:limit]
        except Exception:
            pass
        return f"{len(val)} bytes"
    if isinstance(val, tuple):
        return ", ".join(_fmt(v, 40) for v in val)[:limit]
    if isinstance(val, float):
        return f"{val:g}"
    s = str(val).strip("\x00").strip()
    return s[:limit] + ("…" if len(s) > limit else "")


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return str(n)


# --------------------------------------------------------------------------- EXIF

IFD0, IFD_EXIF, IFD_GPS, IFD_INTEROP = None, 0x8769, 0x8825, 0xA005
_POINTER_TAGS = {0x8769, 0x8825, 0xA005}


def _load_exif(raw: bytes) -> Image.Exif:
    ex = Image.Exif()
    ex.load(raw)
    return ex


def _exif_fields(raw: bytes, ref_prefix: tuple = ("exif",)) -> tuple[list[Field], tuple | None]:
    fields: list[Field] = []
    ex = _load_exif(raw)
    for tid, val in ex.items():
        if tid in _POINTER_TAGS:
            continue
        name = ExifTags.TAGS.get(tid, f"Tag 0x{tid:04X}")
        fields.append(Field(categorize(name), "EXIF", name, EXIF_LABELS.get(name, name), _fmt(val), (*ref_prefix, IFD0, tid)))
    gps_dict = {}
    for ifd_id, group, names in ((IFD_EXIF, "EXIF", ExifTags.TAGS), (IFD_GPS, "GPS", ExifTags.GPSTAGS),
                                 (IFD_INTEROP, "EXIF", ExifTags.TAGS)):
        try:
            sub = ex.get_ifd(ifd_id)
        except Exception:
            sub = {}
        for tid, val in sub.items():
            name = names.get(tid, f"Tag 0x{tid:04X}")
            if ifd_id == IFD_GPS:
                gps_dict[name] = val
            fields.append(Field(categorize(name, group), group, name, EXIF_LABELS.get(name, name), _fmt_gps(name, val),
                                (*ref_prefix, ifd_id, tid)))
    # miniatura embutida (IFD1) — pode mostrar a foto original antes de um recorte
    if raw.find(b"\xff\xd8\xff", 8) != -1:
        fields.append(Field(AUTHOR, "EXIF", "Thumbnail", "Miniatura embutida",
                            "Prévia da foto original (pode mostrar partes recortadas)", (*ref_prefix, "thumb", 0)))
    return fields, _gps_to_decimal(gps_dict)


def _fmt_gps(name: str, val) -> str:
    try:
        if name in ("GPSLatitude", "GPSLongitude") and len(val) == 3:
            d, m, s = (float(x) for x in val)
            return f"{d:.0f}° {m:.0f}′ {s:.2f}″".replace(".", ",")
        if name == "GPSAltitude":
            return f"{float(val):.1f} m".replace(".", ",")
        if name in ("GPSLatitudeRef", "GPSLongitudeRef"):
            return {"N": "Norte (N)", "S": "Sul (S)", "E": "Leste (E)", "W": "Oeste (W)"}.get(str(val), str(val))
    except Exception:
        pass
    return _fmt(val)


def _gps_to_decimal(g: dict) -> tuple[float, float] | None:
    try:
        def conv(v, r):
            d, m, s = (float(x) for x in v)
            dec = d + m / 60 + s / 3600
            return -dec if r in ("S", "W") else dec
        return conv(g["GPSLatitude"], g.get("GPSLatitudeRef", "N")), conv(g["GPSLongitude"], g.get("GPSLongitudeRef", "E"))
    except Exception:
        return None


def _rebuild_exif(raw: bytes, selected_refs: set) -> bytes | None:
    """Retorna o EXIF (sem prefixo 'Exif\\0\\0') sem as tags selecionadas, ou None se ficar vazio."""
    ex = _load_exif(raw)
    for ref in selected_refs:
        ifd, tid = ref[-2], ref[-1]
        if ifd == "thumb":
            continue  # o Pillow nunca regrava a miniatura (IFD1)
        if ifd is IFD0:
            ex.pop(tid, None)
        else:
            try:
                ex.get_ifd(ifd).pop(tid, None)
            except Exception:
                pass
    for ptr in (IFD_EXIF, IFD_GPS, IFD_INTEROP):  # remove ponteiros para IFDs vazios
        try:
            if ptr in ex and not ex.get_ifd(ptr):
                del ex[ptr]
        except Exception:
            pass
    if not any(tid not in _POINTER_TAGS for tid in ex) and not any(
            ex.get_ifd(p) for p in (IFD_EXIF, IFD_GPS) if p in ex):
        return None
    data = ex.tobytes()
    return data[6:] if data.startswith(b"Exif\x00\x00") else data


def _xmp_summary(xmp: bytes) -> tuple[str, str]:
    txt = xmp.decode("utf-8", "ignore")
    keys = sorted(set(re.findall(r"\b(?:exif|tiff|xmp|dc|photoshop|Iptc4xmpCore|aux):([A-Za-z]+)", txt)))
    cat = LOCATION if "GPS" in txt else (DEVICE if any(k in keys for k in ("Make", "Model", "CreatorTool")) else AUTHOR)
    shown = ", ".join(keys[:14]) + ("…" if len(keys) > 14 else "")
    return cat, (f"{len(keys)} campos: {shown}" if keys else f"{len(xmp)} bytes")


# --------------------------------------------------------------------------- JPEG

def _jpeg_segments(data: bytes) -> tuple[list[tuple[int, bytes]], bytes, bytes]:
    """Divide o JPEG em (segmentos antes do SOS, dados da imagem, dados extras após o EOI)."""
    if data[:2] != b"\xff\xd8":
        raise MetaError("JPEG inválido")
    segs, i, n = [], 2, len(data)
    while i < n:
        if data[i] != 0xFF:
            raise MetaError("JPEG corrompido")
        while i < n and data[i] == 0xFF:
            i += 1
        marker = data[i]
        i += 1
        if marker == 0xDA:
            body = data[i - 2:]
            eoi = _find_eoi(body)
            return segs, body[:eoi], body[eoi:]
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        length = struct.unpack(">H", data[i:i + 2])[0]
        segs.append((marker, data[i + 2:i + length]))
        i += length
    raise MetaError("JPEG sem dados de imagem")


def _find_eoi(body: bytes) -> int:
    """Posição logo após o EOI (FFD9). Nos dados comprimidos, FF só aparece seguido de 00, RSTn ou outro marcador."""
    pos = body.find(b"\xff\xd9")
    return len(body) if pos == -1 else pos + 2


_JPEG_KINDS = [
    (0xE1, b"Exif\x00\x00", "exif"),
    (0xE1, b"http://ns.adobe.com/xap/1.0/\x00", "xmp"),
    (0xE1, b"http://ns.adobe.com/xmp/extension/\x00", "xmp"),
    (0xED, b"Photoshop 3.0\x00", "iptc"),
    (0xE2, b"ICC_PROFILE\x00", "icc"),
    (0xE2, b"MPF\x00", "mpf"),
]


def _jpeg_kind(marker: int, payload: bytes) -> str | None:
    for m, sig, kind in _JPEG_KINDS:
        if marker == m and payload.startswith(sig):
            return kind
    if marker == 0xFE:
        return "comment"
    if marker in (0xE0, 0xEE):  # JFIF/Adobe: necessários para decodificar
        return None
    if 0xE1 <= marker <= 0xEF:
        return "app"
    return None


def _read_jpeg(path: str, info: MediaInfo) -> None:
    data = open(path, "rb").read()
    segs, _, trailer = _jpeg_segments(data)
    seen_xmp = False
    for idx, (marker, payload) in enumerate(segs):
        kind = _jpeg_kind(marker, payload)
        if kind == "exif":
            fs, gps = _exif_fields(payload[6:])
            info.fields += fs
            info.gps = info.gps or gps
        elif kind == "xmp" and not seen_xmp:
            seen_xmp = True
            raw = b"".join(p for m, p in segs if _jpeg_kind(m, p) == "xmp")
            cat, summary = _xmp_summary(raw)
            info.fields.append(Field(cat, "XMP", "XMP", "Bloco XMP (Adobe/edição)", summary, ("jpeg", "xmp")))
        elif kind == "iptc":
            info.fields.append(Field(AUTHOR, "IPTC", "IPTC", "Bloco IPTC (legendas, créditos)",
                                     f"{len(payload)} bytes", ("jpeg", "iptc")))
        elif kind == "icc" and not any(f.ref == ("jpeg", "icc") for f in info.fields):
            desc = _icc_name(b"".join(p[14:] for m, p in segs if _jpeg_kind(m, p) == "icc"))
            info.fields.append(Field(COLOR, "ICC", "ICC", "Perfil de cor", desc, ("jpeg", "icc")))
        elif kind == "comment":
            info.fields.append(Field(AUTHOR, "JPEG", "Comment", "Comentário",
                                     _fmt(payload), ("jpeg", "seg", idx)))
        elif kind == "mpf":
            info.fields.append(Field(TECH, "JPEG", "MPF", "Índice de imagens extras (MPF)",
                                     f"{len(payload)} bytes", ("jpeg", "seg", idx)))
        elif kind == "app":
            sig = payload[:20].split(b"\x00")[0].decode("latin-1", "replace")
            info.fields.append(Field(TECH, "JPEG", f"APP{marker - 0xE0}", f"Bloco APP{marker - 0xE0} ({sig or 'dados'})",
                                     f"{len(payload)} bytes", ("jpeg", "seg", idx)))
    if len(trailer) > 16:
        info.fields.append(Field(AUTHOR, "JPEG", "Trailer", "Imagens/dados extras após a foto",
                                 f"{human_size(len(trailer))} (ex.: mapa de profundidade, HDR, outras fotos)",
                                 ("jpeg", "trailer")))


def _icc_name(icc: bytes) -> str:
    try:
        from PIL import ImageCms
        prof = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        return (ImageCms.getProfileDescription(prof) or "").strip() or f"{len(icc)} bytes"
    except Exception:
        return f"{len(icc)} bytes"


def _seg_bytes(marker: int, payload: bytes) -> bytes:
    if len(payload) + 2 > 0xFFFF:
        raise MetaError("Bloco de metadados grande demais para JPEG")
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def _clean_jpeg(path: str, out: str, sel: set, everything: bool) -> None:
    data = open(path, "rb").read()
    segs, body, trailer = _jpeg_segments(data)
    exif_refs = {r for r in sel if r[0] == "exif"}
    parts = [b"\xff\xd8"]
    for idx, (marker, payload) in enumerate(segs):
        kind = _jpeg_kind(marker, payload)
        if kind is None:
            parts.append(_seg_bytes(marker, payload))
            continue
        if everything:
            continue
        if kind == "exif":
            if exif_refs:
                new = _rebuild_exif(payload[6:], exif_refs)
                if new is not None:
                    parts.append(_seg_bytes(0xE1, b"Exif\x00\x00" + new))
            else:
                parts.append(_seg_bytes(marker, payload))
        elif kind in ("xmp", "iptc", "icc"):
            if ("jpeg", kind) not in sel:
                parts.append(_seg_bytes(marker, payload))
        elif ("jpeg", "seg", idx) not in sel:
            parts.append(_seg_bytes(marker, payload))
    parts.append(body)
    if not everything and ("jpeg", "trailer") not in sel:
        parts.append(trailer)
    _write(out, b"".join(parts))


# --------------------------------------------------------------------------- PNG

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(PNG_SIG):
        raise MetaError("PNG inválido")
    i, chunks = 8, []
    while i + 8 <= len(data):
        ln = struct.unpack(">I", data[i:i + 4])[0]
        typ = data[i + 4:i + 8]
        chunks.append((typ, data[i + 8:i + 8 + ln]))
        i += 12 + ln
        if typ == b"IEND":
            break
    return chunks


def _png_text(typ: bytes, body: bytes) -> tuple[str, str]:
    key, _, rest = body.partition(b"\x00")
    k = key.decode("latin-1")
    try:
        if typ == b"tEXt":
            return k, rest.decode("latin-1")
        if typ == b"zTXt":
            return k, zlib.decompress(rest[1:]).decode("latin-1")
        comp = rest[0]
        rest = rest[2:]
        _lang, _, rest = rest.partition(b"\x00")
        _tkey, _, txt = rest.partition(b"\x00")
        return k, (zlib.decompress(txt) if comp else txt).decode("utf-8", "replace")
    except Exception:
        return k, f"{len(body)} bytes"


def _read_png(path: str, info: MediaInfo) -> None:
    for idx, (typ, body) in enumerate(_png_chunks(open(path, "rb").read())):
        if typ in (b"tEXt", b"zTXt", b"iTXt"):
            k, v = _png_text(typ, body)
            if k == "XML:com.adobe.xmp":
                cat, summary = _xmp_summary(v.encode())
                info.fields.append(Field(cat, "XMP", "XMP", "Bloco XMP (Adobe/edição)", summary, ("png", idx)))
            else:
                cat = categorize(k)
                info.fields.append(Field(cat if cat != TECH else AUTHOR, "Texto PNG", k, k, _fmt(v), ("png", idx)))
        elif typ == b"eXIf":
            fs, gps = _exif_fields(body, ("pngexif", idx))
            info.fields += fs
            info.gps = info.gps or gps
        elif typ == b"tIME":
            y, mo, d, h, mi, s = struct.unpack(">HBBBBB", body)
            info.fields.append(Field(DATE, "PNG", "tIME", "Data de modificação",
                                     f"{d:02d}/{mo:02d}/{y} {h:02d}:{mi:02d}:{s:02d}", ("png", idx)))
        elif typ == b"iCCP":
            name = body.split(b"\x00")[0].decode("latin-1")
            info.fields.append(Field(COLOR, "ICC", "iCCP", "Perfil de cor", name, ("png", idx)))


def _png_chunk(typ: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + typ + body + struct.pack(">I", zlib.crc32(typ + body) & 0xFFFFFFFF)


def _clean_png(path: str, out: str, sel: set, everything: bool) -> None:
    meta = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME", b"iCCP"}
    parts = [PNG_SIG]
    for idx, (typ, body) in enumerate(_png_chunks(open(path, "rb").read())):
        if typ in meta and everything:
            continue
        if typ == b"eXIf":
            refs = {r for r in sel if r[0] == "pngexif" and r[1] == idx}
            if refs:
                new = _rebuild_exif(body, refs)
                if new is not None:
                    parts.append(_png_chunk(typ, new))
                continue
        elif ("png", idx) in sel:
            continue
        parts.append(_png_chunk(typ, body))
    _write(out, b"".join(parts))


# --------------------------------------------------------------------------- WebP

def _webp_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise MetaError("WebP inválido")
    i, chunks = 12, []
    while i + 8 <= len(data):
        typ = data[i:i + 4]
        ln = struct.unpack("<I", data[i + 4:i + 8])[0]
        chunks.append((typ, data[i + 8:i + 8 + ln]))
        i += 8 + ln + (ln & 1)
    return chunks


def _read_webp(path: str, info: MediaInfo) -> None:
    for typ, body in _webp_chunks(open(path, "rb").read()):
        if typ == b"EXIF":
            raw = body[6:] if body.startswith(b"Exif\x00\x00") else body
            fs, gps = _exif_fields(raw, ("webpexif",))
            info.fields += fs
            info.gps = info.gps or gps
        elif typ == b"XMP ":
            cat, summary = _xmp_summary(body)
            info.fields.append(Field(cat, "XMP", "XMP", "Bloco XMP (Adobe/edição)", summary, ("webp", "XMP ")))
        elif typ == b"ICCP":
            info.fields.append(Field(COLOR, "ICC", "ICCP", "Perfil de cor", _icc_name(body), ("webp", "ICCP")))


def _clean_webp(path: str, out: str, sel: set, everything: bool) -> None:
    chunks = _webp_chunks(open(path, "rb").read())
    exif_refs = {r for r in sel if r[0] == "webpexif"}
    kept: list[tuple[bytes, bytes]] = []
    for typ, body in chunks:
        if typ in (b"EXIF", b"XMP ", b"ICCP") and everything:
            continue
        if typ == b"EXIF" and exif_refs:
            raw = body[6:] if body.startswith(b"Exif\x00\x00") else body
            new = _rebuild_exif(raw, exif_refs)
            if new is not None:
                kept.append((typ, new))
            continue
        if typ in (b"XMP ", b"ICCP") and ("webp", typ.decode()) in sel:
            continue
        kept.append((typ, body))
    present = {t for t, _ in kept}
    fixed = []
    for typ, body in kept:
        if typ == b"VP8X":
            flags = body[0]
            flags = (flags | 0x20) if b"ICCP" in present else (flags & ~0x20)
            flags = (flags | 0x08) if b"EXIF" in present else (flags & ~0x08)
            flags = (flags | 0x04) if b"XMP " in present else (flags & ~0x04)
            body = bytes([flags]) + body[1:]
        fixed.append(typ + struct.pack("<I", len(body)) + body + (b"\x00" if len(body) & 1 else b""))
    payload = b"WEBP" + b"".join(fixed)
    _write(out, b"RIFF" + struct.pack("<I", len(payload)) + payload)


# --------------------------------------------------------------------------- outros formatos de imagem (Pillow)

def _read_pillow(path: str, info: MediaInfo, im: Image.Image) -> None:
    raw = im.info.get("exif")
    if raw:
        fs, gps = _exif_fields(raw[6:] if raw.startswith(b"Exif\x00\x00") else raw, ("pilexif",))
        info.fields += fs
        info.gps = info.gps or gps
    elif im.format == "TIFF":
        ex = im.getexif()
        if len(ex):
            fs, gps = _exif_fields(ex.tobytes()[6:], ("pilexif",))
            info.fields += [f for f in fs if f.category != TECH or f.key in ("Software", "DateTime")]
            info.gps = info.gps or gps
    for k in ("xmp", "XML:com.adobe.xmp"):
        if im.info.get(k):
            v = im.info[k]
            cat, summary = _xmp_summary(v if isinstance(v, bytes) else str(v).encode())
            info.fields.append(Field(cat, "XMP", "XMP", "Bloco XMP (Adobe/edição)", summary, ("pil", k)))
    if im.info.get("icc_profile"):
        info.fields.append(Field(COLOR, "ICC", "ICC", "Perfil de cor", _icc_name(im.info["icc_profile"]), ("pil", "icc_profile")))
    if im.info.get("comment"):
        info.fields.append(Field(AUTHOR, im.format or "", "comment", "Comentário", _fmt(im.info["comment"]), ("pil", "comment")))


def _clean_pillow(path: str, out: str, sel: set, everything: bool) -> None:
    im = Image.open(path)
    fmt = im.format
    kw: dict = {}
    raw = im.info.get("exif")
    if fmt == "TIFF" and not raw:
        ex = im.getexif()
        raw = ex.tobytes() if len(ex) else None
    if raw and not everything:
        raw = raw[6:] if raw.startswith(b"Exif\x00\x00") else raw
        refs = {r for r in sel if r[0] == "pilexif"}
        new = _rebuild_exif(raw, refs) if refs else raw
        if new:
            kw["exif"] = b"Exif\x00\x00" + new
    if not everything:
        if im.info.get("icc_profile") and ("pil", "icc_profile") not in sel:
            kw["icc_profile"] = im.info["icc_profile"]
        for k in ("xmp", "XML:com.adobe.xmp"):
            if im.info.get(k) and ("pil", k) not in sel:
                kw["xmp"] = im.info[k]
        if im.info.get("comment") and ("pil", "comment") not in sel:
            kw["comment"] = im.info["comment"]
    if fmt in ("HEIF", "AVIF"):
        kw["quality"] = 95
    elif fmt == "TIFF":
        kw["compression"] = im.info.get("compression", "tiff_lzw")
    elif fmt == "GIF":
        for k in ("duration", "loop", "transparency", "background"):
            if k in im.info:
                kw[k] = im.info[k]
    multi = getattr(im, "n_frames", 1) > 1 and fmt in ("GIF", "TIFF", "HEIF", "AVIF")
    im.info = {}
    tmp = out + ".tmp"
    im.save(tmp, format=fmt, save_all=multi, **kw)
    os.replace(tmp, out)


# --------------------------------------------------------------------------- vídeo

def _probe(path: str) -> dict:
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        raise MetaError("FFmpeg não encontrado — necessário para vídeos")
    r = _run([ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", "-show_chapters", path], 120)
    try:
        return json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError:
        raise MetaError("Não foi possível ler o vídeo")


_DATA_STREAMS = {"gpmd": ("Telemetria GoPro (inclui GPS)", LOCATION), "mebx": ("Metadados de câmera (iPhone)", LOCATION),
                 "tmcd": ("Trilha de timecode", TECH), "camm": ("Movimento/GPS da câmera", LOCATION)}


def _video_category(key: str, value) -> str:
    """Assinaturas genéricas do próprio FFmpeg (Lavf/FFMP) não identificam ninguém."""
    v = str(value).strip()
    if key in ("encoder", "vendor_id") and (v.startswith(("Lavf", "Lavc", "FFMP")) or v.strip("[0]") == ""):
        return TECH
    return categorize(key)


def _stream_label(s: dict) -> str:
    t = {"video": "vídeo", "audio": "áudio", "subtitle": "legenda", "data": "dados"}.get(s.get("codec_type"), s.get("codec_type"))
    return f"Trilha {s['index']} ({t})"


def _read_video(path: str, info: MediaInfo) -> None:
    d = _probe(path)
    fmt = d.get("format", {})
    if not d.get("streams"):
        raise MetaError("Arquivo de vídeo inválido ou não suportado")
    for k, v in fmt.get("tags", {}).items():
        shown = _fmt(v)
        if "iso6709" in k.lower() or k.lower().startswith("location"):
            pos = _parse_iso6709(str(v))
            info.gps = info.gps or pos
            if pos:
                shown = f"{pos[0]:.5f}, {pos[1]:.5f}"
        info.fields.append(Field(_video_category(k, v), "Arquivo", k, VIDEO_LABELS.get(k, k), shown, ("fmt", k)))
    vinfo = []
    info.streams = len(d["streams"])
    for s in d.get("streams", []):
        i = s["index"]
        kind = {"video": "vídeo", "audio": "áudio", "subtitle": "legenda", "data": "dados"}.get(s.get("codec_type"), "")
        for k, v in s.get("tags", {}).items():
            lbl = f"{VIDEO_LABELS.get(k, k)} · trilha de {kind}" if kind else VIDEO_LABELS.get(k, k)
            info.fields.append(Field(_video_category(k, v), _stream_label(s), k, lbl, _fmt(v), ("stream", i, k)))
        tag = s.get("codec_tag_string", "")
        if s.get("disposition", {}).get("attached_pic"):
            info.fields.append(Field(AUTHOR, _stream_label(s), "attached_pic", "Capa/miniatura embutida",
                                     f"Imagem {s.get('width')}×{s.get('height')}", ("drop", i)))
        elif s.get("codec_type") in ("data", "subtitle") and (tag in _DATA_STREAMS or s.get("codec_type") == "data"):
            label, cat = _DATA_STREAMS.get(tag, (f"Trilha de dados ({tag or s.get('codec_name', '?')})", TECH))
            info.fields.append(Field(cat, _stream_label(s), tag or "data", label, "Trilha inteira", ("drop", i)))
        if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic") and not vinfo:
            vinfo.append(f"{s.get('width')}×{s.get('height')}")
            vinfo.append((s.get("codec_name") or "").upper())
    for c in d.get("chapters", []):
        title = c.get("tags", {}).get("title", "")
        info.fields.append(Field(AUTHOR, "Capítulos", f"chapter{c.get('id')}", "Capítulo",
                                 title or f"{float(c.get('start_time', 0)):.0f}s", ("chapters",)))
    dur = float(fmt.get("duration", 0) or 0)
    if dur:
        vinfo.append(f"{int(dur // 60)}:{int(dur % 60):02d}")
    info.details = " · ".join(x for x in vinfo if x)


def _parse_iso6709(s: str) -> tuple[float, float] | None:
    m = re.match(r"([+-]\d+(?:\.\d+)?)([+-]\d+(?:\.\d+)?)", s.strip())
    return (float(m.group(1)), float(m.group(2))) if m else None


def _clean_video(path: str, out: str, info: MediaInfo, sel: set, everything: bool) -> None:
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        raise MetaError("FFmpeg não encontrado — necessário para vídeos")
    drops = sorted({r[1] for r in sel if r[0] == "drop"})
    cmd = [ffmpeg, "-nostdin", "-y", "-v", "error", "-i", path, "-map", "0"]
    cmd += [x for i in drops for x in ("-map", f"-0:{i}")]
    if everything:
        cmd += ["-map_metadata", "-1", "-map_chapters", "-1"]
    else:
        cmd += ["-map_metadata", "0"]
        if ("chapters",) in sel:
            cmd += ["-map_chapters", "-1"]
        # mapeia índices originais -> índices de saída (trilhas removidas deslocam a numeração)
        out_idx, n = {}, 0
        for i in range(info.streams):
            if i not in drops:
                out_idx[i] = n
                n += 1
        for r in sel:
            if r[0] == "fmt":
                cmd += ["-metadata", f"{r[1]}="]
            elif r[0] == "stream" and r[1] in out_idx:
                cmd += [f"-metadata:s:{out_idx[r[1]]}", f"{r[2]}="]
        if os.path.splitext(out)[1].lower() in (".mp4", ".mov", ".m4v", ".3gp"):
            cmd += ["-movflags", "+use_metadata_tags"]
    cmd += ["-c", "copy", "-ignore_unknown", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]
    tmp = out + ".part" + os.path.splitext(out)[1]
    cmd.append(tmp)
    r = _run(cmd, 3600)
    if r.returncode != 0:
        try:
            os.remove(tmp)
        except OSError:
            pass
        msg = r.stderr.decode("utf-8", "replace").strip().splitlines()
        raise MetaError("Falha no FFmpeg: " + (msg[-1] if msg else "erro desconhecido"))
    os.replace(tmp, out)


def video_thumbnail(path: str, width: int = 320) -> bytes | None:
    ffmpeg = find_tool("ffmpeg")
    if not ffmpeg:
        return None
    for ss in ("1", "0"):
        r = _run([ffmpeg, "-nostdin", "-v", "error", "-ss", ss, "-i", path, "-frames:v", "1",
                  "-vf", f"scale={width}:-2", "-f", "image2pipe", "-vcodec", "png", "-"], 60)
        if r.returncode == 0 and r.stdout:
            return r.stdout
    return None


# --------------------------------------------------------------------------- API pública

def is_supported(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXT


def read_media(path: str) -> MediaInfo:
    ext = os.path.splitext(path)[1].lower()
    info = MediaInfo(path=path, kind="video" if ext in VIDEO_EXT else "image")
    try:
        info.size = os.path.getsize(path)
        if info.kind == "video":
            _read_video(path, info)
        else:
            with Image.open(path) as im:
                info.details = f"{im.width}×{im.height} · {im.format}"
                fmt = im.format
                if fmt not in ("JPEG", "PNG", "WEBP"):
                    _read_pillow(path, info, im)
                    if fmt in ("HEIF", "AVIF"):
                        info.note = "Fotos HEIC/AVIF são recomprimidas em qualidade alta (95) ao limpar."
            if fmt == "JPEG":
                _read_jpeg(path, info)
            elif fmt == "PNG":
                _read_png(path, info)
            elif fmt == "WEBP":
                _read_webp(path, info)
    except MetaError as e:
        info.error = str(e)
    except Exception as e:  # arquivo corrompido, formato inesperado…
        info.error = f"Não foi possível ler: {e}"
    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    info.fields.sort(key=lambda f: order[f.category])
    return info


def output_path(src: str, out_dir: str | None = None, suffix: str = "_limpo") -> str:
    folder = out_dir or os.path.dirname(src)
    base, ext = os.path.splitext(os.path.basename(src))
    cand = os.path.join(folder, f"{base}{suffix}{ext}")
    n = 2
    while os.path.exists(cand):
        cand = os.path.join(folder, f"{base}{suffix}{n}{ext}")
        n += 1
    return cand


def _write(out: str, data: bytes) -> None:
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, out)


def clean_media(info: MediaInfo, fields: list[Field] | None = None, out_dir: str | None = None) -> CleanResult:
    """Cria uma cópia limpa. ``fields``: campos a remover (padrão: os marcados)."""
    if info.error:
        raise MetaError(info.error)
    chosen = [f for f in info.fields if f.checked] if fields is None else fields
    everything = len(chosen) == len(info.fields)
    if not chosen and info.fields:
        raise MetaError("Nenhum campo marcado para remover")
    sel = {f.ref for f in chosen}
    out = output_path(info.path, out_dir)
    if info.kind == "video":
        _clean_video(info.path, out, info, sel, everything)
    else:
        with Image.open(info.path) as im:
            fmt = im.format
        if fmt == "JPEG":
            _clean_jpeg(info.path, out, sel, everything)
        elif fmt == "PNG":
            _clean_png(info.path, out, sel, everything)
        elif fmt == "WEBP":
            _clean_webp(info.path, out, sel, everything)
        else:
            _clean_pillow(info.path, out, sel, everything)
    after = read_media(out)
    if after.error:
        try:
            os.remove(out)
        except OSError:
            pass
        raise MetaError(f"A cópia gerada não pôde ser validada: {after.error}")
    kept_keys = {(f.group, f.key) for f in info.fields if f not in chosen}
    leftover = [f for f in after.fields if f.category in PRIVACY and (f.group, f.key) not in kept_keys]
    return CleanResult(info.path, out, len(chosen), leftover)


def expand_paths(paths) -> list[str]:
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                out += [os.path.join(root, f) for f in sorted(files) if is_supported(f)]
        elif is_supported(p):
            out.append(p)
    return out
