"""Desktop window: connect, pick tables, generate an HTML or PDF report.

Built on Tkinter (ships with Python) so the packaged executable stays small
and has no extra GUI dependencies.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import APP_NAME, __version__
from .connection import DB_TYPES, build_url, db_type, safe_url
from .generate import generate
from .introspect import SchemaReader

ACCENT = "#1f3a5f"
ACCENT_HOVER = "#2b4d7a"
BG = "#f4f6f9"
PANEL = "#ffffff"
INK = "#1d2b3a"
MUTED = "#5f6f82"
LINE = "#d5dde6"
ERROR = "#b42318"
OK = "#0f766e"

UNCHECKED, CHECKED = "☐", "☑"


def open_file(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        import webbrowser
        webbrowser.open(path.resolve().as_uri())


def friendly_error(exc: BaseException) -> str:
    if isinstance(exc, ModuleNotFoundError):
        return (f"The database driver '{exc.name}' isn't installed.\n\n"
                "If you're running from source, install it with pip (see README).")
    orig = getattr(exc, "orig", None)
    msg = (str(orig).strip() if orig is not None else "") or str(exc)
    low = msg.lower()
    if "timeout" in low or "timed out" in low or "refused" in low:
        msg += ("\n\nThe server couldn't be reached. Check the host and port, and make sure "
                "the database accepts connections from outside its own network.")
    return msg


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.reader: SchemaReader | None = None
        self.all_tables: list[str] = []
        self.selected: set[str] = set()
        self.busy = False

        root.title(APP_NAME)
        root.geometry("1040x680")
        root.minsize(860, 560)
        root.configure(bg=BG)
        self._style()
        self._build()
        self._on_type_change()

    # ------------------------------------------------------------ styling
    def _style(self):
        base = tkfont.nametofont("TkDefaultFont")
        base.configure(size=10)
        for name in ("TkTextFont", "TkMenuFont"):
            tkfont.nametofont(name).configure(size=10)
        family = base.actual("family")
        self.f_title = tkfont.Font(family=family, size=15, weight="bold")
        self.f_head = tkfont.Font(family=family, size=11, weight="bold")
        self.f_small = tkfont.Font(family=family, size=9)
        self.f_list = tkfont.Font(family=family, size=10)

        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=INK, bordercolor=LINE, focuscolor=ACCENT)
        s.configure("Panel.TFrame", background=PANEL)
        s.configure("Panel.TLabel", background=PANEL, foreground=INK)
        s.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=self.f_small)
        s.configure("Head.TLabel", background=PANEL, foreground=INK, font=self.f_head)
        s.configure("Status.TLabel", background=BG, foreground=MUTED)
        s.configure("TEntry", fieldbackground=PANEL, padding=5)
        s.configure("TCombobox", fieldbackground=PANEL, padding=4)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL)])
        s.configure("TButton", padding=(12, 6), background=PANEL)
        s.map("TButton", background=[("active", "#eef3f8")])
        s.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", bordercolor=ACCENT,
                    padding=(16, 8), font=(family, 10, "bold"))
        s.map("Accent.TButton", background=[("disabled", "#9aa9ba"), ("active", ACCENT_HOVER)],
              foreground=[("disabled", "#eef2f6")])
        s.configure("Panel.TRadiobutton", background=PANEL)
        s.configure("Panel.TCheckbutton", background=PANEL)
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, rowheight=26, font=self.f_list,
                    bordercolor=LINE)
        s.map("Treeview", background=[("selected", "#e3ecf6")], foreground=[("selected", INK)])
        s.configure("TProgressbar", background=ACCENT, troughcolor="#e4e9ef", bordercolor=BG)

    # ------------------------------------------------------------ layout
    def _panel(self, parent, title, subtitle):
        outer = tk.Frame(parent, bg=LINE, padx=1, pady=1)
        inner = ttk.Frame(outer, style="Panel.TFrame", padding=16)
        inner.pack(fill="both", expand=True)
        ttk.Label(inner, text=title, style="Head.TLabel").pack(anchor="w")
        ttk.Label(inner, text=subtitle, style="Muted.TLabel").pack(anchor="w", pady=(2, 12))
        return outer, inner

    def _build(self):
        bar = tk.Frame(self.root, bg=ACCENT, padx=20, pady=12)
        bar.pack(fill="x")
        tk.Label(bar, text=APP_NAME, bg=ACCENT, fg="#ffffff", font=self.f_title).pack(side="left")
        tk.Label(bar, text="ERD and schema reference from a live database", bg=ACCENT, fg="#c9d7e8",
                 font=self.f_small).pack(side="left", padx=(12, 0), pady=(4, 0))

        body = ttk.Frame(self.root, padding=(16, 16, 16, 8))
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # --- connection panel
        left_outer, left = self._panel(body, "1. Connect", "Where are the tables?")
        left_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left_outer.configure(width=330)

        ttk.Label(left, text="Database type", style="Panel.TLabel").pack(anchor="w")
        self.v_type = tk.StringVar(value=DB_TYPES[0].label)
        cb = ttk.Combobox(left, textvariable=self.v_type, values=[t.label for t in DB_TYPES],
                          state="readonly", width=32)
        cb.pack(fill="x", pady=(2, 10))
        cb.bind("<<ComboboxSelected>>", lambda e: self._on_type_change())

        self.fields = ttk.Frame(left, style="Panel.TFrame")
        self.fields.pack(fill="x")
        self.v_host, self.v_port = tk.StringVar(value="localhost"), tk.StringVar()
        self.v_db, self.v_user, self.v_pass = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.v_file, self.v_url = tk.StringVar(), tk.StringVar()

        self.btn_connect = ttk.Button(left, text="Connect", style="Accent.TButton", command=self.connect)
        self.btn_connect.pack(fill="x", pady=(14, 8))
        self.lbl_conn = tk.Label(left, text="Not connected", bg=PANEL, fg=MUTED, font=self.f_small,
                                 wraplength=290, justify="left", anchor="w")
        self.lbl_conn.pack(fill="x")

        # --- table picker
        right_outer, right = self._panel(body, "2. Choose tables", "Tick the tables to include in the document.")
        right_outer.grid(row=0, column=1, sticky="nsew")

        tools = ttk.Frame(right, style="Panel.TFrame")
        tools.pack(fill="x", pady=(0, 8))
        self.schema_box = ttk.Frame(tools, style="Panel.TFrame")
        self.schema_box.pack(side="left")
        self.schema_label = ttk.Label(self.schema_box, text="Schema", style="Panel.TLabel")
        self.v_schema = tk.StringVar()
        self.cb_schema = ttk.Combobox(self.schema_box, textvariable=self.v_schema, state="readonly", width=18)
        self.cb_schema.bind("<<ComboboxSelected>>", lambda e: self.load_tables())
        ttk.Label(tools, text="Search", style="Panel.TLabel").pack(side="left")
        self.v_search = tk.StringVar()
        self.v_search.trace_add("write", lambda *a: self._refresh_list())
        ttk.Entry(tools, textvariable=self.v_search, width=24).pack(side="left", padx=(6, 12))
        ttk.Button(tools, text="Clear", command=self.select_none).pack(side="right")
        ttk.Button(tools, text="Select all", command=self.select_all).pack(side="right", padx=(0, 6))

        list_frame = tk.Frame(right, bg=LINE, padx=1, pady=1)
        list_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(list_frame, show="tree", selectmode="browse")
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<space>", self._on_space)
        self.empty_msg = tk.Label(self.tree, text="Connect to a database to see its tables.",
                                  bg=PANEL, fg=MUTED)
        self.empty_msg.place(relx=0.5, rely=0.4, anchor="center")

        self.lbl_count = ttk.Label(right, text="", style="Muted.TLabel")
        self.lbl_count.pack(anchor="w", pady=(8, 0))

        # --- output bar
        out_outer = tk.Frame(self.root, bg=LINE, padx=1, pady=1)
        out_outer.pack(fill="x", padx=16, pady=(0, 8))
        out = ttk.Frame(out_outer, style="Panel.TFrame", padding=(16, 12))
        out.pack(fill="x")
        ttk.Label(out, text="3. Output", style="Head.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 16))
        ttk.Label(out, text="Title", style="Panel.TLabel").grid(row=0, column=1, sticky="e")
        self.v_title = tk.StringVar()
        ttk.Entry(out, textvariable=self.v_title, width=30).grid(row=0, column=2, sticky="we", padx=(6, 16))
        self.v_fmt = tk.StringVar(value="html")
        ttk.Radiobutton(out, text="HTML page", value="html", variable=self.v_fmt,
                        style="Panel.TRadiobutton").grid(row=0, column=3, padx=(0, 8))
        ttk.Radiobutton(out, text="PDF document", value="pdf", variable=self.v_fmt,
                        style="Panel.TRadiobutton").grid(row=0, column=4, padx=(0, 16))
        self.v_open = tk.BooleanVar(value=True)
        ttk.Checkbutton(out, text="Open when finished", variable=self.v_open,
                        style="Panel.TCheckbutton").grid(row=0, column=5, padx=(0, 16))
        self.btn_generate = ttk.Button(out, text="Generate document", style="Accent.TButton",
                                       command=self.generate, state="disabled")
        self.btn_generate.grid(row=0, column=6, sticky="e")
        out.columnconfigure(2, weight=1)

        status = ttk.Frame(self.root, padding=(18, 0, 18, 10))
        status.pack(fill="x")
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=120)
        self.lbl_status = ttk.Label(status, text=f"Version {__version__}", style="Status.TLabel")
        self.lbl_status.pack(side="left")

    # ------------------------------------------------------------ connection form
    def _field(self, label, var, show=None, width=None):
        ttk.Label(self.fields, text=label, style="Panel.TLabel").pack(anchor="w")
        e = ttk.Entry(self.fields, textvariable=var, show=show or "")
        e.pack(fill="x", pady=(2, 8))
        e.bind("<Return>", lambda ev: self.connect())
        return e

    def _on_type_change(self):
        for w in self.fields.winfo_children():
            w.destroy()
        kind = db_type(self.v_type.get())
        if kind.is_custom:
            self._field("SQLAlchemy URL", self.v_url)
            ttk.Label(self.fields, text="e.g. oracle+oracledb://user:pass@host:1521/?service_name=XE",
                      style="Muted.TLabel", wraplength=290).pack(anchor="w")
        elif kind.is_file:
            ttk.Label(self.fields, text="Database file", style="Panel.TLabel").pack(anchor="w")
            row = ttk.Frame(self.fields, style="Panel.TFrame")
            row.pack(fill="x", pady=(2, 8))
            ttk.Entry(row, textvariable=self.v_file).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Browse…", command=self._browse_sqlite).pack(side="left", padx=(6, 0))
        else:
            self.v_port.set(str(kind.default_port or ""))
            self._field("Host", self.v_host)
            self._field("Port", self.v_port)
            self._field("Database", self.v_db)
            self._field("Username", self.v_user)
            self._field("Password", self.v_pass, show="•")

    def _browse_sqlite(self):
        path = filedialog.askopenfilename(
            title="Open SQLite database",
            filetypes=[("SQLite databases", "*.db *.sqlite *.sqlite3 *.db3"), ("All files", "*.*")])
        if path:
            self.v_file.set(path)

    # ------------------------------------------------------------ background work
    def _set_busy(self, busy: bool, message: str = ""):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.btn_connect.configure(state=state)
        self.btn_generate.configure(state="disabled" if busy or not self.selected else "normal")
        if busy:
            self.progress.pack(side="right")
            self.progress.start(12)
            self._status(message)
        else:
            self.progress.stop()
            self.progress.pack_forget()
        self.root.configure(cursor="watch" if busy else "")

    def _run(self, work, done, message):
        self._set_busy(True, message)
        q: queue.Queue = queue.Queue()

        def target():
            try:
                q.put((True, work()))
            except BaseException as exc:  # report every failure in the UI
                q.put((False, exc))

        threading.Thread(target=target, daemon=True).start()

        def poll():
            try:
                ok, value = q.get_nowait()
            except queue.Empty:
                self.root.after(80, poll)
                return
            self._set_busy(False)
            if ok:
                done(value)
            else:
                self._status("Something went wrong. See the message for details.", ERROR)
                messagebox.showerror(APP_NAME, friendly_error(value))

        poll()

    def _status(self, text, color=MUTED):
        self.lbl_status.configure(text=text, foreground=color)

    # ------------------------------------------------------------ actions
    def connect(self):
        if self.busy:
            return
        kind = db_type(self.v_type.get())
        try:
            url = build_url(kind, self.v_host.get(), self.v_port.get(), self.v_db.get(), self.v_user.get(),
                            self.v_pass.get(), self.v_file.get(), self.v_url.get())
        except ValueError as exc:
            messagebox.showwarning(APP_NAME, str(exc))
            return
        if kind.is_file and not Path(self.v_file.get()).is_file():
            messagebox.showwarning(APP_NAME, "That SQLite file doesn't exist.")
            return

        def work():
            reader = SchemaReader(url)
            schemas = reader.list_schemas() if reader.dialect != "sqlite" else []
            default = reader.default_schema()
            return reader, schemas, default

        def done(result):
            reader, schemas, default = result
            if self.reader:
                self.reader.close()
            self.reader = reader
            self.lbl_conn.configure(text=f"Connected to {safe_url(url)}", fg=OK)
            if len(schemas) > 1:
                self.cb_schema.configure(values=schemas)
                self.v_schema.set(default if default in schemas else schemas[0])
                self.schema_label.pack(side="left")
                self.cb_schema.pack(side="left", padx=(6, 16))
            else:
                self.v_schema.set("")
                self.schema_label.pack_forget()
                self.cb_schema.pack_forget()
            if not self.v_title.get():
                self.v_title.set(f"{reader.database_name} schema")
            self.load_tables()

        self._run(work, done, "Connecting…")

    def _schema(self):
        return self.v_schema.get() or None

    def load_tables(self):
        if not self.reader:
            return
        schema = self._schema()
        reader = self.reader

        def done(tables):
            self.all_tables = tables
            self.selected.clear()
            self._refresh_list()
            where = f" in {schema}" if schema else ""
            self._status(f"Found {len(tables)} tables{where}.", OK)

        self._run(lambda: reader.list_tables(schema), done, "Reading table list…")

    def _refresh_list(self):
        q = self.v_search.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        shown = [t for t in self.all_tables if q in t.lower()]
        for t in shown:
            self.tree.insert("", "end", iid=t, text=f"  {CHECKED if t in self.selected else UNCHECKED}   {t}")
        if not self.all_tables:
            msg = "No tables found in this schema." if self.reader else "Connect to a database to see its tables."
            self.empty_msg.configure(text=msg)
            self.empty_msg.place(relx=0.5, rely=0.4, anchor="center")
        elif not shown:
            self.empty_msg.configure(text="No tables match your search.")
            self.empty_msg.place(relx=0.5, rely=0.4, anchor="center")
        else:
            self.empty_msg.place_forget()
        self._update_count()

    def _toggle(self, iid):
        if iid in self.selected:
            self.selected.discard(iid)
        else:
            self.selected.add(iid)
        self.tree.item(iid, text=f"  {CHECKED if iid in self.selected else UNCHECKED}   {iid}")
        self._update_count()

    def _on_click(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.focus(iid)
            self.tree.selection_set(iid)
            self._toggle(iid)
            return "break"

    def _on_space(self, event):
        iid = self.tree.focus()
        if iid:
            self._toggle(iid)
        return "break"

    def select_all(self):
        self.selected |= set(self.tree.get_children())
        self._refresh_list()

    def select_none(self):
        visible = set(self.tree.get_children())
        self.selected -= visible if self.v_search.get() else set(self.selected)
        self._refresh_list()

    def _update_count(self):
        if self.all_tables:
            self.lbl_count.configure(text=f"{len(self.selected)} of {len(self.all_tables)} tables selected")
        else:
            self.lbl_count.configure(text="")
        if not self.busy:
            self.btn_generate.configure(state="normal" if self.selected else "disabled")

    def generate(self):
        if self.busy or not self.reader or not self.selected:
            return
        fmt = self.v_fmt.get()
        title = self.v_title.get().strip() or None
        base = (title or self.reader.database_name or "schema").replace(" ", "_")
        path = filedialog.asksaveasfilename(
            title="Save document", defaultextension=f".{fmt}", initialfile=f"{base}.{fmt}",
            filetypes=[("HTML page", "*.html")] if fmt == "html" else [("PDF document", "*.pdf")])
        if not path:
            return
        tables = [t for t in self.all_tables if t in self.selected]  # keep database order
        reader, schema = self.reader, self._schema()

        def done(out: Path):
            self._status(f"Saved {out}", OK)
            if self.v_open.get():
                open_file(out)

        self._run(lambda: generate(reader, tables, path, fmt, schema=schema, title=title), done,
                  f"Documenting {len(tables)} tables…")


def _hidpi():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def main() -> int:
    _hidpi()
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
