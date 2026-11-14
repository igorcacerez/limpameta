"""LimpaMeta - identifica e remove metadados de fotos e videos (cria copia limpa)."""
import json, os, shutil, subprocess, sys, threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ExifTags

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
VID_EXT = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".3gp", ".mts", ".wmv", ".flv"}
OTHER_IMG = {".heic", ".heif", ".bmp", ".gif", ".avif"}
try:
    import ctypes; ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def find_tool(name):
    p = shutil.which(name)
    if p:
        return p
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages")
    if os.path.isdir(base):
        for root, _, files in os.walk(base):
            if name + ".exe" in files:
                return os.path.join(root, name + ".exe")
    return None


FFMPEG, FFPROBE = find_tool("ffmpeg"), find_tool("ffprobe")


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", creationflags=NOWIN)


# ---------- leitura ----------
# item: dict(group, key, value, rm) ; rm identifica como remover
def read_image(path):
    items = []
    im = Image.open(path)
    ex = im.getexif()
    for tid, val in ex.items():
        if tid in (0x8769, 0x8825, 0xA005):
            continue
        items.append(dict(group="EXIF", key=ExifTags.TAGS.get(tid, hex(tid)), value=str(val)[:200], rm=("exif", None, tid)))
    for ifd_id, gname in ((0x8769, "EXIF"), (0x8825, "GPS"), (0xA005, "Interop")):
        try:
            sub = ex.get_ifd(ifd_id)
        except Exception:
            sub = {}
        tags = ExifTags.GPSTAGS if ifd_id == 0x8825 else ExifTags.TAGS
        for tid, val in sub.items():
            items.append(dict(group=gname, key=tags.get(tid, hex(tid)), value=str(val)[:200], rm=("exif", ifd_id, tid)))
    for k, v in im.info.items():
        if k in ("exif",):
            continue
        if k == "icc_profile":
            items.append(dict(group="Perfil de cor", key="icc_profile", value=f"{len(v)} bytes", rm=("info", k)))
        elif k in ("xmp", "XML:com.adobe.xmp"):
            items.append(dict(group="XMP", key=k, value=f"{len(v)} bytes", rm=("info", k)))
        elif isinstance(v, (str, bytes)):
            s = v.decode("utf-8", "replace") if isinstance(v, bytes) else v
            items.append(dict(group="Texto/Info", key=str(k), value=s[:200], rm=("info", k)))
        elif k in ("dpi", "jfif", "jfif_version", "jfif_unit", "jfif_density", "progressive", "progression", "adobe", "adobe_transform", "dpi"):
            continue
    return items


def read_video(path):
    r = run([FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", "-show_chapters", path])
    d = json.loads(r.stdout or "{}")
    items = []
    for k, v in d.get("format", {}).get("tags", {}).items():
        items.append(dict(group="Arquivo", key=k, value=str(v)[:200], rm=("fmt", k)))
    for s in d.get("streams", []):
        i = s["index"]
        label = f"Stream {i} ({s.get('codec_type')})"
        for k, v in s.get("tags", {}).items():
            items.append(dict(group=label, key=k, value=str(v)[:200], rm=("stream", i, k)))
        if s.get("disposition", {}).get("attached_pic"):
            items.append(dict(group=label, key="miniatura/capa embutida", value="imagem anexada", rm=("drop_stream", i)))
    for c in d.get("chapters", []):
        items.append(dict(group="Capitulos", key=f"capitulo {c.get('id')}", value=str(c.get("tags", {}))[:200], rm=("chapters",)))
    return items


def read_any(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in IMG_EXT:
        try:
            return read_image(path)
        except Exception:
            pass
    if FFPROBE:
        return read_video(path)
    return []


# ---------- limpeza ----------
def out_path(path):
    b, e = os.path.splitext(path)
    n = f"{b}_limpo{e}"
    c = 2
    while os.path.exists(n):
        n = f"{b}_limpo{c}{e}"
        c += 1
    return n


def clean_image_pil(path, items, remove_all):
    im = Image.open(path)
    fmt = im.format
    ex = im.getexif()
    info_drop = set()
    if remove_all:
        ex = Image.Exif()
        info_drop = set(im.info.keys())
    else:
        for it in items:
            rm = it["rm"]
            if rm[0] == "exif":
                _, ifd, tid = rm
                try:
                    if ifd is None:
                        ex.pop(tid, None)
                    else:
                        ex.get_ifd(ifd).pop(tid, None)
                except Exception:
                    pass
            elif rm[0] == "info":
                info_drop.add(rm[1])
    out = out_path(path)
    kw = {}
    if fmt == "JPEG":
        kw["quality"] = "keep"
        if "icc_profile" in im.info and "icc_profile" not in info_drop:
            kw["icc_profile"] = im.info["icc_profile"]
        if len(ex):
            kw["exif"] = ex.tobytes()
    elif fmt == "PNG":
        if len(ex):
            kw["exif"] = ex.tobytes()
        if "icc_profile" in im.info and "icc_profile" not in info_drop:
            kw["icc_profile"] = im.info["icc_profile"]
    elif fmt == "WEBP":
        kw["lossless"] = False
        kw["quality"] = 95
        if len(ex):
            kw["exif"] = ex.tobytes()
        if "icc_profile" in im.info and "icc_profile" not in info_drop:
            kw["icc_profile"] = im.info["icc_profile"]
    elif fmt == "TIFF":
        pass
    # recria pixels sem carregar info herdada
    for k in list(im.info):
        if k != "icc_profile" or k in info_drop:
            im.info.pop(k, None)
    im.save(out, format=fmt, **kw)
    return out


def clean_ffmpeg(path, items, remove_all):
    out = out_path(path)
    cmd = [FFMPEG, "-y", "-v", "error", "-i", path]
    ext = os.path.splitext(path)[1].lower()
    is_img = ext in IMG_EXT or ext in OTHER_IMG
    drops = [it["rm"][1] for it in items if it["rm"][0] == "drop_stream"] if not remove_all else []
    if remove_all:
        cmd += ["-map", "0", "-map_metadata", "-1", "-map_chapters", "-1"]
    else:
        cmd += ["-map", "0"] + [x for i in drops for x in ("-map", f"-0:{i}")]
        cmd += ["-map_metadata", "0"]
        if any(it["rm"][0] == "chapters" for it in items):
            cmd += ["-map_chapters", "-1"]
        for it in items:
            rm = it["rm"]
            if rm[0] == "fmt":
                cmd += ["-metadata", f"{rm[1]}="]
            elif rm[0] == "stream":
                cmd += [f"-metadata:s:{rm[1]}", f"{rm[2]}="]
    if not is_img:
        cmd += ["-c", "copy"]
    cmd += ["-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]
    cmd.append(out)
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "erro no ffmpeg")
    return out


def clean(path, items, remove_all):
    ext = os.path.splitext(path)[1].lower()
    if ext in IMG_EXT:
        try:
            return clean_image_pil(path, items, remove_all)
        except Exception:
            if not (remove_all and FFMPEG):
                raise
    if not FFMPEG:
        raise RuntimeError("ffmpeg nao encontrado")
    return clean_ffmpeg(path, items, remove_all)


# ---------- categorias amigaveis ----------
BG, PANEL, PANEL2 = "#13151b", "#1c1f28", "#262a36"
ACC, TXT, MUTED = "#4f8cff", "#e8eaf0", "#8b91a3"
DANGER, OK, WARN = "#ff6b7a", "#3ecf8e", "#ffb454"

CATS = [
    ("📍 Localização", ("gps", "location", "latitude", "longitude")),
    ("📱 Dispositivo e software", ("make", "model", "lens", "serial", "software", "encoder", "device", "camera", "handler", "com.apple.quicktime.make")),
    ("🕒 Datas e horas", ("date", "time", "creation")),
    ("👤 Autoria e textos", ("artist", "author", "copyright", "owner", "title", "comment", "description", "xmp", "texto", "album", "genre", "composer")),
    ("🎨 Perfil de cor", ("icc", "perfil")),
]
SENSITIVE = "📍 Localização"


def categorize(it):
    hay = (it["group"] + " " + it["key"]).lower()
    if it["group"] == "GPS":
        return CATS[0][0]
    for name, words in CATS:
        if any(w in hay for w in words):
            return name
    return "⚙️ Técnico"


try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _Base = TkinterDnD.Tk
except Exception:
    TkinterDnD = None
    _Base = tk.Tk


class App(_Base):
    def __init__(self):
        super().__init__()
        self.title("LimpaMeta")
        self.geometry("1120x700")
        self.minsize(900, 560)
        self.configure(bg=BG)
        self.files = {}        # path -> items (cada item tem 'on')
        self.current = None
        self.nodes = {}        # iid da arvore -> item | ('cat', nome)
        self.last_dir = None
        self.style_setup()
        self.build()
        if TkinterDnD:
            try:
                self.drop_target_register(DND_FILES)
                self.dnd_bind("<<Drop>>", lambda e: self.add_paths(self.tk.splitlist(e.data)))
            except Exception:
                pass

    def style_setup(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TXT, font=("Segoe UI", 10))
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TXT,
                    rowheight=30, borderwidth=0, font=("Segoe UI", 10))
        s.map("Treeview", background=[("selected", PANEL2)], foreground=[("selected", TXT)])
        s.configure("Treeview.Heading", background=PANEL2, foreground=MUTED, relief="flat", font=("Segoe UI", 9, "bold"))
        s.configure("Vertical.TScrollbar", background=PANEL2, troughcolor=PANEL, borderwidth=0, arrowcolor=MUTED)
        s.configure("TProgressbar", background=ACC, troughcolor=PANEL2, borderwidth=0)

    def btn(self, parent, text, cmd, kind="ghost"):
        colors = {"primary": (ACC, "#fff"), "danger": (DANGER, "#fff"), "ghost": (PANEL2, TXT)}
        bg, fg = colors[kind]
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                      relief="flat", bd=0, padx=16, pady=9, cursor="hand2", font=("Segoe UI", 10, "bold"))
        b.bind("<Enter>", lambda e: b.config(bg=self.lighten(bg)))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    @staticmethod
    def lighten(h):
        r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        return "#%02x%02x%02x" % tuple(min(255, c + 22) for c in (r, g, b))

    def build(self):
        head = tk.Frame(self, bg=BG)
        head.pack(fill="x", padx=20, pady=(16, 8))
        tk.Label(head, text="🧹 LimpaMeta", bg=BG, fg=TXT, font=("Segoe UI", 18, "bold")).pack(side="left")
        tk.Label(head, text="   Veja o que está escondido nas suas fotos e vídeos e remova.", bg=BG, fg=MUTED,
                 font=("Segoe UI", 10)).pack(side="left", pady=(6, 0))

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=20)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # --- passo 1: arquivos
        left = tk.Frame(body, bg=PANEL, width=350)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 12))
        left.grid_propagate(False)
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        top = tk.Frame(left, bg=PANEL)
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        tk.Label(top, text="1  Seus arquivos", bg=PANEL, fg=TXT, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        row = tk.Frame(top, bg=PANEL)
        row.pack(fill="x", pady=(8, 0))
        self.btn(row, "+ Arquivos", self.add_files, "primary").pack(side="left")
        self.btn(row, "+ Pasta", self.add_folder).pack(side="left", padx=6)
        self.flist = ttk.Treeview(left, show="tree", selectmode="browse")
        self.flist.column("#0", width=330)
        self.flist.grid(row=1, column=0, sticky="nsew", padx=6)
        self.flist.bind("<<TreeviewSelect>>", self.on_pick)
        self.empty = tk.Label(left, text="Clique em  + Arquivos\n" + ("ou arraste-os para cá" if TkinterDnD else "para começar"),
                              bg=PANEL, fg=MUTED, font=("Segoe UI", 10), justify="center")
        self.empty.place(relx=0.5, rely=0.5, anchor="center")
        self.btn(left, "Remover da lista", self.drop_file).grid(row=2, column=0, sticky="ew", padx=12, pady=12)

        # --- passo 2: metadados
        right = tk.Frame(body, bg=PANEL)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)
        top = tk.Frame(right, bg=PANEL)
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 0))
        tk.Label(top, text="2  O que foi encontrado", bg=PANEL, fg=TXT, font=("Segoe UI", 11, "bold")).pack(side="left")
        self.b_none = self.btn(top, "Desmarcar tudo", lambda: self.mark_all(False))
        self.b_none.pack(side="right")
        self.btn(top, "Marcar tudo", lambda: self.mark_all(True)).pack(side="right", padx=6)
        self.summary = tk.Label(right, text="Selecione um arquivo à esquerda.", bg=PANEL, fg=MUTED,
                                font=("Segoe UI", 10), anchor="w")
        self.summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 8))
        wrap = tk.Frame(right, bg=PANEL)
        wrap.grid(row=2, column=0, sticky="nsew", padx=8)
        self.tree = ttk.Treeview(wrap, columns=("campo", "valor"), selectmode="none")
        self.tree.heading("#0", text="  Remover?")
        self.tree.heading("campo", text="Campo")
        self.tree.heading("valor", text="Valor")
        self.tree.column("#0", width=230, stretch=False)
        self.tree.column("campo", width=170, stretch=False)
        self.tree.column("valor", width=420)
        self.tree.tag_configure("sens", foreground=WARN)
        self.tree.tag_configure("cat", font=("Segoe UI", 10, "bold"), background=PANEL2)
        sb = ttk.Scrollbar(wrap, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Button-1>", self.on_click)
        tk.Label(right, text="Clique numa linha para marcar ☑ ou desmarcar ☐. Linhas em laranja revelam onde você esteve.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 9), anchor="w").grid(row=3, column=0, sticky="ew", padx=14, pady=8)

        # --- passo 3: limpar
        bot = tk.Frame(self, bg=BG)
        bot.pack(fill="x", padx=20, pady=14)
        tk.Label(bot, text="3  Limpar", bg=BG, fg=TXT, font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 14))
        self.b_sel = self.btn(bot, "Limpar os marcados", self.rm_selected, "primary")
        self.b_sel.pack(side="left")
        self.btn(bot, "Limpar TUDO (todos os arquivos)", self.rm_all, "danger").pack(side="left", padx=8)
        self.pb = ttk.Progressbar(bot, length=140)
        self.msg = tk.Label(bot, text="Original intacto: criamos uma cópia “_limpo”.",
                            bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.msg.pack(side="left", padx=12)
        self.b_open = self.btn(bot, "Abrir pasta", self.open_dir)

    # ----- arquivos
    def add_files(self):
        self.add_paths(filedialog.askopenfilenames(title="Escolha fotos e vídeos"))

    def add_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.add_paths([os.path.join(r, f) for r, _, fs in os.walk(d) for f in fs])

    def add_paths(self, paths):
        new = None
        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            if p in self.files or ext not in IMG_EXT | VID_EXT | OTHER_IMG:
                continue
            try:
                items = read_any(p)
            except Exception:
                items = []
            for it in items:
                it["on"] = True
                it["cat"] = categorize(it)
            self.files[p] = items
            icon = "🎞" if ext in VID_EXT else "🖼"
            n = len(items)
            sens = any(i["cat"] == SENSITIVE for i in items)
            label = f"{icon}  {os.path.basename(p)}  ·  {n}" + ("  ⚠" if sens else "")
            self.flist.insert("", "end", iid=p, text=label)
            new = new or p
        self.empty.place_forget() if self.files else None
        if new:
            self.flist.selection_set(new)

    def drop_file(self):
        s = self.flist.selection()
        if s:
            self.flist.delete(s[0])
            self.files.pop(s[0], None)
            self.current = None
            self.show([])
        if not self.files:
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

    def on_pick(self, _=None):
        s = self.flist.selection()
        if s:
            self.current = s[0]
            self.show(self.files[s[0]])

    # ----- tabela
    def show(self, items):
        self.tree.delete(*self.tree.get_children())
        self.nodes = {}
        if not self.current:
            self.summary.config(text="Selecione um arquivo à esquerda.", fg=MUTED)
            return
        if not items:
            self.summary.config(text="✅ Este arquivo já está limpo: nenhum metadado encontrado.", fg=OK)
            return
        cats = {}
        for it in items:
            cats.setdefault(it["cat"], []).append(it)
        order = [c[0] for c in CATS] + ["⚙️ Técnico"]
        for c in order:
            if c not in cats:
                continue
            cid = self.tree.insert("", "end", text="", values=(c, f"{len(cats[c])} item(ns)"), open=True, tags=("cat",))
            self.nodes[cid] = ("cat", c)
            for it in cats[c]:
                iid = self.tree.insert(cid, "end", text="", values=(it["key"], it["value"]),
                                       tags=("sens",) if c == SENSITIVE else ())
                self.nodes[iid] = it
        self.refresh()

    def refresh(self):
        items = self.files.get(self.current, [])
        for iid, node in self.nodes.items():
            if isinstance(node, tuple):
                kids = [self.nodes[k] for k in self.tree.get_children(iid)]
                state = "☑" if all(k["on"] for k in kids) else ("☐" if not any(k["on"] for k in kids) else "▣")
                self.tree.item(iid, text=f"  {state}  inteira")
            else:
                self.tree.item(iid, text=f"      {'☑' if node['on'] else '☐'}")
        n = len(items)
        on = sum(i["on"] for i in items)
        sens = sum(1 for i in items if i["cat"] == SENSITIVE)
        txt = f"{n} encontrado(s) · {on} marcado(s) para remover"
        if sens:
            txt += f" · ⚠ {sens} de LOCALIZAÇÃO"
        self.summary.config(text=txt, fg=WARN if sens else TXT)

    def on_click(self, e):
        iid = self.tree.identify_row(e.y)
        node = self.nodes.get(iid)
        if node is None:
            return "break"
        if isinstance(node, tuple):
            kids = [self.nodes[k] for k in self.tree.get_children(iid)]
            val = not all(k["on"] for k in kids)
            for k in kids:
                k["on"] = val
        else:
            node["on"] = not node["on"]
        self.refresh()
        return "break"

    def mark_all(self, v):
        for it in self.files.get(self.current, []):
            it["on"] = v
        self.refresh()

    # ----- limpeza
    def rm_selected(self):
        if not self.current:
            return messagebox.showinfo("LimpaMeta", "Escolha um arquivo na lista à esquerda.")
        items = self.files[self.current]
        sel = [i for i in items if i["on"]]
        if not sel:
            return messagebox.showinfo("LimpaMeta", "Marque pelo menos um campo para remover.")
        self.work([(self.current, sel, len(sel) == len(items))])

    def rm_all(self):
        if not self.files:
            return messagebox.showinfo("LimpaMeta", "Adicione arquivos primeiro.")
        if messagebox.askyesno("Limpar tudo", f"Remover TODOS os metadados de {len(self.files)} arquivo(s)?\n"
                                              "Os originais não serão alterados."):
            self.work([(p, it, True) for p, it in self.files.items()])

    def work(self, jobs):
        self.pb.config(maximum=len(jobs), value=0)
        self.pb.pack(side="left", before=self.msg)
        self.b_open.pack_forget()
        self.msg.config(text="Limpando...", fg=TXT)

        def go():
            ok, errs = [], []
            for p, items, all_ in jobs:
                try:
                    ok.append(clean(p, items, all_))
                except Exception as e:
                    errs.append(f"{os.path.basename(p)}: {e}")
                self.after(0, lambda: self.pb.step(1))
            self.after(0, lambda: self.done(ok, errs))
        threading.Thread(target=go, daemon=True).start()

    def done(self, ok, errs):
        self.pb.pack_forget()
        if ok:
            self.last_dir = os.path.dirname(ok[0])
            self.b_open.pack(side="right")
        if errs:
            self.msg.config(text=f"✅ {len(ok)} limpo(s) · ❌ {len(errs)} erro(s): {errs[0][:90]}", fg=DANGER)
        else:
            self.msg.config(text=f"✅ Pronto! {len(ok)} cópia(s) “_limpo” criada(s).", fg=OK)

    def open_dir(self):
        if self.last_dir:
            os.startfile(self.last_dir)


if __name__ == "__main__":
    App().mainloop()

