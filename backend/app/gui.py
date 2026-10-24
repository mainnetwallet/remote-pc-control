"""The app window of Remote PC Control: a real desktop UI (tkinter), not a web page.

It does everything the browser control panel does (connect the phone, password, autostart, firewall, PIN lock,
internet link, speed settings, restart/stop, logs). It talks to the local agent through the same private
/panel/api (loopback only + access token), so it works whether the agent runs inside this program or was started
earlier by the autostart task."""
import json, os, queue, subprocess, sys, threading, time, urllib.error, urllib.request
from pathlib import Path
from .gui_text import TEXT
from .paths import data_dir, frozen

TITLE = "Remote PC Control"

# Texts that only the app window needs (the rest is in gui_text.py).
EXTRA = {
    "en": {"tab_connect": "Connect", "tab_startup": "Startup", "tab_lock": "Lock", "tab_link": "Internet",
           "tab_settings": "Settings", "tab_agent": "Agent", "no_server": "Cannot reach the agent on this PC. Is it running?",
           "closing_note": "Closing this window keeps the agent running in the background. Open the app again to see it.",
           "offline": "Agent not reachable", "loading": "Loading...", "restarting_app": "Restarting... this window reconnects in a few seconds.",
           "server_on": "Server: ON", "server_off": "Server: OFF", "server_starting": "Server: starting...", "server_stopping": "Server: stopping...",
           "turn_on": "Turn on server", "turn_off": "Turn off server", "server_off_note": "The phone cannot connect while the server is off.",
           "server_stopped": "Server turned off."},
    "bn": {"tab_connect": "কানেক্ট", "tab_startup": "স্টার্টআপ", "tab_lock": "লক", "tab_link": "ইন্টারনেট",
           "tab_settings": "সেটিংস", "tab_agent": "এজেন্ট", "no_server": "এই PC র এজেন্টের সাথে যোগাযোগ হচ্ছে না। এটা কি চালু আছে?",
           "closing_note": "এই উইন্ডো বন্ধ করলেও এজেন্ট ব্যাকগ্রাউন্ডে চালু থাকে। আবার অ্যাপ খুললে এটা দেখা যাবে।",
           "offline": "এজেন্ট পাওয়া যাচ্ছে না", "loading": "লোড হচ্ছে...", "restarting_app": "রিস্টার্ট হচ্ছে... কয়েক সেকেন্ডে উইন্ডো আবার কানেক্ট হবে।",
           "server_on": "সার্ভার: চালু", "server_off": "সার্ভার: বন্ধ", "server_starting": "সার্ভার: চালু হচ্ছে...", "server_stopping": "সার্ভার: বন্ধ হচ্ছে...",
           "turn_on": "সার্ভার চালু করুন", "turn_off": "সার্ভার বন্ধ করুন", "server_off_note": "সার্ভার বন্ধ থাকলে ফোন কানেক্ট হবে না।",
           "server_stopped": "সার্ভার বন্ধ হয়েছে।"},
}
OK, BAD, MUTED = "#12805c", "#b42318", "#5d6b7e"


class ApiError(Exception):
    def __init__(self, message="", status=0):
        super().__init__(message); self.status = status


class PanelClient:
    """Small HTTP client for the agent's local panel API."""

    def __init__(self, port, token):
        self.port, self.token = int(port), token
        # Never go through a system proxy for 127.0.0.1.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, path, method="GET", body=None, timeout=60):
        data = json.dumps(body).encode("utf-8") if body is not None else (b"" if method == "POST" else None)
        headers = {"Authorization": "Bearer " + self.token}
        if body is not None: headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/panel/api{path}", data=data, method=method, headers=headers)
        try:
            with self._opener.open(req, timeout=timeout) as r:
                raw = r.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                d = json.loads(e.read().decode("utf-8", "replace")).get("detail")
                detail = d if isinstance(d, str) else ""
            except Exception:
                pass
            raise ApiError(detail or f"Error {e.code}", e.code) from None
        except (urllib.error.URLError, OSError, ValueError):
            raise ApiError("") from None   # the window shows its own "cannot reach the agent" text


class App:
    def __init__(self, root, client, starting=False):
        import tkinter as tk
        from tkinter import ttk, font as tkfont
        self.tk, self.ttk = tk, ttk
        self.root, self.client = root, client
        self.S, self.SYS = {}, None
        self.online = None   # None = not known yet, True = the server answers, False = it does not
        self.stop_until = 0.0   # right after "turn off" the server may still answer once or twice: ignore that
        self.deadline = time.time() + 45 if starting else 0.0   # until then "not answering" means "starting"
        self.token_shown = False
        self.lang = self._load_lang()
        self.q = queue.Queue(); self.pending = {}; self._job = 0
        self._tunnel_job = self._toast_job = None
        self.wrap = []
        root.title(TITLE)
        root.geometry("780x660"); root.minsize(660, 560)
        self._icon()
        base = tkfont.nametofont("TkDefaultFont")
        self.tkfont = tkfont
        self._ui_font()
        self.f_title = base.copy(); self.f_title.configure(size=base.actual("size") + 5, weight="bold")
        self.f_head = base.copy(); self.f_head.configure(size=base.actual("size") + 1, weight="bold")
        self.f_mono = tkfont.nametofont("TkFixedFont").copy()
        if sys.platform == "win32": self.f_mono.configure(family="Consolas", size=9)
        style = ttk.Style()
        try: style.theme_use("vista" if sys.platform == "win32" else "clam")
        except Exception: pass
        style.configure("Primary.TButton", font=self.f_head)
        self.build()
        root.after(80, self._pump)
        root.after(300, self.refresh_all)
        root.after(1500, self.poll)

    # ---- helpers -------------------------------------------------------------------------------------------
    def _ui_font(self):
        if sys.platform != "win32": return
        family = "Nirmala UI" if self.lang == "bn" else "Segoe UI"   # Nirmala UI has the Bengali letters
        for n in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"): self.tkfont.nametofont(n).configure(family=family, size=10)
        for f in ("f_title", "f_head"):
            if hasattr(self, f): getattr(self, f).configure(family=family)

    def _icon(self):
        for base in (getattr(sys, "_MEIPASS", None), Path(__file__).resolve().parents[2]):
            p = Path(base or "") / "assets" / "app.ico"
            if base and p.exists():
                try: self.root.iconbitmap(default=str(p)); return
                except Exception: pass

    def _lang_file(self): return data_dir() / "window_lang.txt"

    def _load_lang(self):
        try:
            v = self._lang_file().read_text(encoding="ascii").strip()
            if v in TEXT: return v
        except OSError: pass
        return "en"   # English until the user picks Bengali with the button (the choice is remembered)

    def t(self, key):
        return EXTRA[self.lang].get(key) or TEXT[self.lang].get(key) or TEXT["en"].get(key) or EXTRA["en"].get(key) or key

    def bg(self, fn, ok=None, err=None):
        """Run fn in a worker thread so the window never freezes; ok/err run on the window thread.
        The callbacks (which hold Tk objects) never enter the worker thread."""
        self._job += 1; n = self._job
        self.pending[n] = (ok, err)
        def work():
            try: res, e = fn(), None
            except BaseException as ex: res, e = None, ex
            self.q.put((n, res, e))
        threading.Thread(target=work, daemon=True).start()

    def _pump(self):
        try:
            while True:
                n, res, e = self.q.get_nowait()
                ok, err = self.pending.pop(n, (None, None))
                try:
                    if e is None:
                        if ok: ok(res)
                    elif err: err(e)
                    else: self.toast(self._msg(e), True)
                except Exception as ex:   # a failing callback must never stop the window from updating
                    print("window callback failed:", repr(ex))
        except queue.Empty: pass
        try: self.root.after(80, self._pump)
        except Exception: pass

    def _msg(self, e):
        if isinstance(e, ApiError):
            if e.status == 401: return self.t("bad_pw")
            if str(e): return str(e)
        return self.t("no_server")

    def toast(self, msg, bad=False):
        self.status.configure(text=msg, foreground=BAD if bad else OK)
        if self._toast_job: self.root.after_cancel(self._toast_job)
        self._toast_job = self.root.after(5000, lambda: self.status.configure(text=""))

    def copy(self, text):
        self.root.clipboard_clear(); self.root.clipboard_append(text); self.toast(self.t("copied"))

    # ---- layout --------------------------------------------------------------------------------------------
    def label(self, parent, text, muted=False, wrap=False, **kw):
        lab = self.ttk.Label(parent, text=text, **kw)
        if muted: lab.configure(foreground=MUTED)
        if wrap: lab.configure(wraplength=680, justify="left"); self.wrap.append(lab)
        return lab

    def heading(self, parent, key): self.label(parent, self.t(key), font=self.f_head).pack(anchor="w", pady=(0, 2))

    def helptext(self, parent, key_or_text, pady=(0, 8)):
        self.label(parent, self.t(key_or_text), muted=True, wrap=True).pack(anchor="w", pady=pady)

    def row(self, parent, pady=4):
        f = self.ttk.Frame(parent); f.pack(fill="x", pady=pady); return f

    def button(self, parent, key, cmd, primary=False, side="left", padx=(0, 8)):
        b = self.ttk.Button(parent, text=self.t(key), command=cmd, style="Primary.TButton" if primary else "TButton")
        b.pack(side=side, padx=padx); return b

    def tab(self, key):
        f = self.ttk.Frame(self.nb, padding=16); self.nb.add(f, text="  " + self.t(key) + "  "); return f

    def switch(self, parent, title_key, help_key, call):
        var = self.tk.BooleanVar(value=False)
        box = self.ttk.Frame(parent); box.pack(fill="x", pady=(6, 4))
        cb = self.ttk.Checkbutton(box, text=self.t(title_key), variable=var)
        cb.configure(command=lambda: self.toggle(var, cb, call)); cb.pack(anchor="w")
        self.label(box, self.t(help_key), muted=True, wrap=True).pack(anchor="w", padx=(24, 0))
        return var, cb

    def build(self):
        ttk = self.ttk
        for w in self.root.winfo_children(): w.destroy()
        self.wrap = []
        head = ttk.Frame(self.root, padding=(16, 12, 16, 0)); head.pack(fill="x")
        ttk.Label(head, text=TITLE, font=self.f_title).pack(side="left")
        ttk.Button(head, text="বাংলা" if self.lang == "en" else "English", command=self.toggle_lang).pack(side="right")
        self.admin_pill = ttk.Label(head); self.admin_pill.pack(side="right", padx=12)
        self.host_pill = ttk.Label(head, foreground=MUTED); self.host_pill.pack(side="right", padx=4)

        bar = ttk.Frame(self.root, padding=(16, 8, 16, 0)); bar.pack(fill="x")
        self.srv_pill = ttk.Label(bar, font=self.f_head); self.srv_pill.pack(side="left")
        self.srv_note = ttk.Label(bar, foreground=MUTED); self.srv_note.pack(side="left", padx=12)
        self.srv_btn = ttk.Button(bar, command=self.toggle_server, style="Primary.TButton"); self.srv_btn.pack(side="right")
        foot = ttk.Frame(self.root, padding=(16, 0, 16, 10)); foot.pack(side="bottom", fill="x")
        self.status = ttk.Label(foot, text="", wraplength=700); self.status.pack(anchor="w")
        self.label(foot, self.t("closing_note"), muted=True, wrap=True).pack(anchor="w")

        self.nb = ttk.Notebook(self.root); self.nb.pack(fill="both", expand=True, padx=16, pady=10)
        self.nb.bind("<Configure>", self._rewrap)
        self._build_connect(); self._build_startup(); self._build_lock()
        self._build_link(); self._build_settings(); self._build_agent()
        self.render_server()

    def _rewrap(self, e):
        for lab in self.wrap:
            try: lab.configure(wraplength=max(300, e.width - 70))
            except Exception: pass

    def _build_connect(self):
        f = self.tab("tab_connect")
        self.heading(f, "conn_title"); self.helptext(f, "conn_help")
        self.addr_box = self.ttk.Frame(f); self.addr_box.pack(fill="x")
        self.ttk.Separator(f).pack(fill="x", pady=12)
        r = self.row(f); self.label(r, self.t("password"), font=self.f_head).pack(side="left")
        self.button(r, "copy", lambda: self.copy(self.client.token), side="right", padx=(8, 0))
        self.show_btn = self.button(r, "hide" if self.token_shown else "show", self.toggle_token, side="right", padx=(8, 0))
        self.token_lab = self.ttk.Label(r, font=self.f_mono); self.token_lab.pack(side="right", padx=8)
        r = self.row(f, 8)
        self.new_pw = self.tk.StringVar()
        self.ttk.Entry(r, textvariable=self.new_pw).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.button(r, "save", self.save_password, primary=True); self.button(r, "random", self.random_password, padx=0)
        self.helptext(f, "pw_rules")
        self.render_token()

    def _build_startup(self):
        f = self.tab("tab_startup")
        self.heading(f, "startup_title")
        self.source_note = self.label(f, "", muted=True, wrap=True); self.source_note.pack(anchor="w")
        self.v_auto, self.c_auto = self.switch(f, "autostart", "autostart_help", lambda on: self.client.call("/autostart", "POST", {"enabled": on}))
        self.v_fwts, self.c_fwts = self.switch(f, "fw_ts", "fw_ts_help", lambda on: self.client.call("/firewall", "POST", {"rule": "tailscale", "enabled": on}))
        self.v_fwlan, self.c_fwlan = self.switch(f, "fw_lan", "fw_lan_help", lambda on: self.client.call("/firewall", "POST", {"rule": "lan", "enabled": on}))

    def _build_lock(self):
        f = self.tab("tab_lock")
        self.heading(f, "lock_title"); self.helptext(f, "lock_help")
        r = self.row(f); self.lock_pill = self.ttk.Label(r, font=self.f_head); self.lock_pill.pack(side="left")
        self.pin_pill = self.ttk.Label(r, foreground=MUTED); self.pin_pill.pack(side="left", padx=14)
        r = self.row(f, 8); self.pin = self.tk.StringVar()
        e = self.ttk.Entry(r, textvariable=self.pin, show="•", width=16); e.pack(side="left", padx=(0, 8))
        self.label(r, self.t("pin_ph"), muted=True).pack(side="left", padx=(0, 12))
        r = self.row(f, 8)
        self.button(r, "set_pin", self.save_pin, primary=True); self.button(r, "lock_now", lambda: self.set_lock(True)); self.button(r, "unlock", lambda: self.set_lock(False))
        self.v_locktask, self.c_locktask = self.switch(f, "lock_task", "lock_task_help", lambda on: self.client.call("/lock-task", "POST", {"enabled": on}))

    def _build_link(self):
        f = self.tab("tab_link")
        self.heading(f, "tunnel_title"); self.helptext(f, "tunnel_help")
        r = self.row(f); self.tunnel_pill = self.ttk.Label(r, font=self.f_head); self.tunnel_pill.pack(side="left", padx=(0, 14))
        self.t_install = self.ttk.Button(r, text=self.t("install_cf"), command=lambda: self.tunnel("install"))
        self.t_start = self.ttk.Button(r, text=self.t("start_tunnel"), command=lambda: self.tunnel("start"), style="Primary.TButton")
        self.t_stop = self.ttk.Button(r, text=self.t("stop_tunnel"), command=lambda: self.tunnel("stop"))
        self.t_row = self.row(f, 8)
        self.t_url = self.tk.StringVar()
        self.ttk.Entry(self.t_row, textvariable=self.t_url, state="readonly").pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.button(self.t_row, "copy", lambda: self.copy(self.t_url.get()), padx=0)
        self.t_msg = self.label(f, "", muted=True, wrap=True); self.t_msg.pack(anchor="w", pady=6)

    def _build_settings(self):
        f = self.tab("tab_settings")
        self.heading(f, "perf_title"); self.helptext(f, "perf_help")
        self.fields_box = self.ttk.Frame(f); self.fields_box.pack(fill="x")
        self.field_vars = {}
        r = self.row(f, 12); self.button(r, "save_settings", self.save_settings, primary=True)

    def _build_agent(self):
        f = self.tab("tab_agent")
        self.heading(f, "agent_title")
        r = self.row(f); self.button(r, "restart", self.restart)
        r = self.row(f, 8); self.label(r, self.t("logs"), font=self.f_head).pack(side="left", padx=(0, 8))
        self.log_sel = self.tk.StringVar(value="agent")
        cb = self.ttk.Combobox(r, textvariable=self.log_sel, values=["agent", "lock"], state="readonly", width=10)
        cb.pack(side="left", padx=(0, 8)); cb.bind("<<ComboboxSelected>>", lambda e: self.load_log())
        self.button(r, "refresh", self.load_log)
        box = self.ttk.Frame(f); box.pack(fill="both", expand=True, pady=(4, 0))
        self.log_text = self.tk.Text(box, height=12, wrap="word", font=self.f_mono, state="disabled", relief="flat",
                                     highlightthickness=1, highlightbackground="#c9d1dc")
        sb = self.ttk.Scrollbar(box, command=self.log_text.yview); self.log_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); self.log_text.pack(side="left", fill="both", expand=True)

    # ---- data ----------------------------------------------------------------------------------------------
    def refresh_all(self):
        self.bg(lambda: self.client.call("/state"), self._got_state, self._offline)
        self.bg(lambda: self.client.call("/token"), lambda d: self._set_token(d.get("token")), lambda e: None)
        self.load_system(); self.load_log()

    def _set_token(self, tok):
        if tok: self.client.token = tok; self.render_token()

    def _offline(self, e):
        self.set_online(False)
        if self.online is False and time.time() >= self.deadline: self.toast(self._msg(e), True)

    def _got_state(self, s):
        self.S = s
        self.set_online(True)
        self.render_pills(); self.render_addrs(); self.render_fields(); self.render_lock(); self.render_tunnel(s.get("tunnel"))
        self.source_note.configure(text="" if s.get("installed") else self.t("source_note"))

    def poll(self):
        """Keep the pills (lock state, tunnel) in step with changes made from the phone."""
        def got(s):
            self.S.update({k: s[k] for k in ("lock", "tunnel", "elevated", "hostname", "addresses") if k in s})
            if self.set_online(True) is False: return
            self.render_pills(); self.render_lock(); self.render_tunnel(s.get("tunnel"))
        self.bg(lambda: self.client.call("/state", timeout=8), got, lambda e: self.set_online(False))
        fast = self.online is not True or time.time() < self.stop_until or time.time() < self.deadline
        self.root.after(1500 if fast else 5000, self.poll)

    def set_online(self, flag):
        """Remember whether the server answers and update the ON/OFF bar. Returns False when the answer is ignored."""
        if flag and time.time() < self.stop_until: return False   # "turn off" was just pressed: this is the dying server
        was, self.online = self.online, flag
        if flag:
            self.deadline = 0.0
            if was is False: self.refresh_all()   # the server came back: load everything again
        else:
            self.stop_until = 0.0
            self.admin_pill.configure(text=""); self.host_pill.configure(text="")
        self.render_server()
        return True

    def render_server(self):
        starting = self.online is not True and time.time() < self.deadline
        stopping = time.time() < self.stop_until
        if stopping: text, color, btn, dis = "server_stopping", MUTED, "turn_off", True
        elif self.online: text, color, btn, dis = "server_on", OK, "turn_off", False
        elif starting or self.online is None: text, color, btn, dis = "server_starting", MUTED, "turn_on", True
        else: text, color, btn, dis = "server_off", BAD, "turn_on", False
        self.srv_pill.configure(text="● " + self.t(text), foreground=color)
        self.srv_note.configure(text=self.t("server_off_note") if (self.online is False and not starting and not stopping) else "")
        self.srv_btn.configure(text=self.t(btn)); self.srv_btn.state(["disabled"] if dis else ["!disabled"])

    def load_system(self, attempt=0):
        rows = ((self.v_auto, self.c_auto, "autostart", True), (self.v_locktask, self.c_locktask, "lock_task", True),
                (self.v_fwts, self.c_fwts, "fw_tailscale", False), (self.v_fwlan, self.c_fwlan, "fw_lan", False))
        for _var, cb, _key, _need in rows: cb.state(["disabled"])   # never show a guess: locked until Windows answered
        def got(d):
            self.SYS = d
            tools = bool(d.get("task_tools"))
            for var, cb, key, need_tools in rows:
                var.set(bool((d.get(key) or {}).get("exists")))
                cb.state(["disabled"] if (need_tools and not tools) else ["!disabled"])
        def failed(e):
            # Used to be ignored silently, which left every box unticked. Retry, then say so.
            if attempt < 3: self.root.after(4000, lambda: self.load_system(attempt + 1))
            else: self.toast(self._msg(e), True)
        self.bg(lambda: self.client.call("/system"), got, failed)

    def load_log(self):
        def got(d):
            self.log_text.configure(state="normal"); self.log_text.delete("1.0", "end")
            self.log_text.insert("end", d.get("text") or "-"); self.log_text.see("end"); self.log_text.configure(state="disabled")
        name = self.log_sel.get()   # read Tk values here, on the window thread, never inside the worker
        self.bg(lambda: self.client.call("/logs/" + name), got, lambda e: None)

    # ---- rendering -----------------------------------------------------------------------------------------
    def render_pills(self):
        s = self.S
        self.host_pill.configure(text=s.get("hostname", ""))
        ok = bool(s.get("elevated"))
        self.admin_pill.configure(text="● " + self.t("admin_yes" if ok else "admin_no"), foreground=OK if ok else BAD)

    def render_addrs(self):
        for w in self.addr_box.winfo_children(): w.destroy()
        addrs = self.S.get("addresses") or []
        if not addrs: self.label(self.addr_box, self.t("no_addr"), muted=True).pack(anchor="w")
        for a in addrs:
            url = f"http://{a['ip']}:{self.S.get('port', 8888)}"
            r = self.ttk.Frame(self.addr_box); r.pack(fill="x", pady=3)
            self.ttk.Label(r, text=url, font=self.f_mono).pack(side="left")
            self.label(r, "   -   " + self.t(a["kind"]), muted=True).pack(side="left")
            self.ttk.Button(r, text=self.t("copy"), command=lambda u=url: self.copy(u)).pack(side="right")

    def render_token(self):
        tok = self.client.token
        self.token_lab.configure(text=tok if self.token_shown else "•" * min(len(tok), 16))
        self.show_btn.configure(text=self.t("hide" if self.token_shown else "show"))

    def render_lock(self):
        l = self.S.get("lock") or {}
        locked = bool(l.get("locked"))
        self.lock_pill.configure(text="● " + self.t("locked" if locked else "unlocked"), foreground=BAD if locked else OK)
        self.pin_pill.configure(text=self.t("pin_set" if l.get("pin_set") else "pin_not_set"))

    def render_fields(self):
        for w in self.fields_box.winfo_children(): w.destroy()
        self.field_vars = {}
        ttk, tk = self.ttk, self.tk
        self.fields_box.columnconfigure((0, 1), weight=1, uniform="f")
        for i, f in enumerate(self.S.get("fields") or []):
            cell = ttk.Frame(self.fields_box); cell.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 14), pady=6)
            self.label(cell, self.t("f_" + f["key"]), muted=True).pack(anchor="w")
            var = tk.StringVar()
            if f["kind"] == "choice":
                var.set(f["value"]); w = ttk.Combobox(cell, textvariable=var, values=f["options"], state="readonly")
            elif f["kind"] == "bool":
                var.set(self.t("off") if f["value"] == "0" else self.t("on")); w = ttk.Combobox(cell, textvariable=var, values=[self.t("on"), self.t("off")], state="readonly")
            else:
                var.set(f["value"]); w = ttk.Spinbox(cell, textvariable=var, from_=f["min"], to=f["max"])
            w.pack(fill="x"); self.field_vars[f["key"]] = (var, f)

    def render_tunnel(self, s):
        if not s: return
        self.S["tunnel"] = s
        on = bool(s.get("running"))
        self.tunnel_pill.configure(text="● " + self.t("tunnel_on" if on else "tunnel_off"), foreground=OK if on else MUTED)
        for b in (self.t_install, self.t_start, self.t_stop): b.pack_forget()
        if not s.get("installed") and s.get("supported"):
            self.t_install.pack(side="left", padx=(0, 8)); self.t_install.state(["disabled"] if s.get("installing") else ["!disabled"])
        if s.get("installed") and not on: self.t_start.pack(side="left", padx=(0, 8))
        if on: self.t_stop.pack(side="left", padx=(0, 8))
        self.t_url.set(s.get("url") or "")
        if s.get("url"): self.t_row.pack(fill="x", pady=8, before=self.t_msg)
        else: self.t_row.pack_forget()
        msg = (self.t("installing") if s.get("installing") else s.get("error") or s.get("install_message")
               or (self.t("tunnel_wait") if on and not s.get("url") else (self.t("tunnel_missing") if not s.get("installed") else "")))
        self.t_msg.configure(text=msg)
        if self._tunnel_job: self.root.after_cancel(self._tunnel_job); self._tunnel_job = None
        if s.get("installing") or (on and not s.get("url")):
            self._tunnel_job = self.root.after(2000, lambda: self.bg(lambda: self.client.call("/tunnel"), self.render_tunnel, lambda e: None))

    # ---- actions -------------------------------------------------------------------------------------------
    def toggle_lang(self):
        self.lang = "bn" if self.lang == "en" else "en"
        try: self._lang_file().parent.mkdir(parents=True, exist_ok=True); self._lang_file().write_text(self.lang, encoding="ascii")
        except OSError: pass
        sel = self.nb.index(self.nb.select())
        self._ui_font(); self.build(); self.nb.select(sel)
        if self.S:
            self.render_pills(); self.render_addrs(); self.render_fields(); self.render_lock(); self.render_tunnel(self.S.get("tunnel"))
        self.load_system(); self.load_log()

    def toggle_token(self): self.token_shown = not self.token_shown; self.render_token()

    def toggle(self, var, cb, call):
        want = var.get(); cb.state(["disabled"])
        def done(_):
            self.toast(self.t("done")); self.load_system()
        def fail(e):
            var.set(not want); self.toast(self._msg(e), True); self.load_system()
        self.bg(lambda: call(want), done, fail)

    def save_password(self):
        v = self.new_pw.get()
        def done(_):
            self.client.token = v; self.new_pw.set(""); self.render_token(); self.toast(self.t("pw_saved"))
        self.bg(lambda: self.client.call("/token", "POST", {"token": v}), done)

    def random_password(self):
        def done(d):
            self.client.token = d["token"]; self.token_shown = True; self.render_token(); self.toast(self.t("pw_saved"))
        self.bg(lambda: self.client.call("/token/random", "POST"), done)

    def _reload_state(self, msg):
        def got(s): self.S.update(s); self.render_lock(); self.toast(msg)
        self.bg(lambda: self.client.call("/state"), got)

    def save_pin(self):
        pin = self.pin.get()
        def done(_): self.pin.set(""); self._reload_state(self.t("pin_saved"))
        self.bg(lambda: self.client.call("/pin", "POST", {"pin": pin}), done)

    def set_lock(self, locked):
        self.bg(lambda: self.client.call("/lock", "POST", {"locked": locked}), lambda _: self._reload_state(self.t("done")))

    def tunnel(self, action):
        self.bg(lambda: self.client.call("/tunnel/" + action, "POST"), self.render_tunnel)

    def save_settings(self):
        values = {}
        for key, (var, f) in self.field_vars.items():
            v = var.get()
            if f["kind"] == "bool": v = "0" if v == self.t("off") else "1"
            values[key] = v
        def done(_):
            self.toast(self.t("restart_needed")); self.bg(lambda: self.client.call("/state"), self._got_state)
        self.bg(lambda: self.client.call("/settings", "POST", {"values": values}), done)

    def restart(self):
        def done(_):
            self.toast(self.t("restarting_app")); self.deadline = time.time() + 45; self.render_server()
        self.bg(lambda: self.client.call("/restart", "POST"), done)

    def toggle_server(self):
        """Turn the server off (it stops answering the phone) or on again, without closing this window."""
        if self.online:
            from tkinter import messagebox
            if not messagebox.askokcancel(TITLE, self.t("quit_confirm"), parent=self.root): return
            self.stop_until = time.time() + 6; self.render_server()
            def done(_): self.toast(self.t("server_stopped"))
            def fail(e): self.stop_until = 0.0; self.render_server(); self.toast(self._msg(e), True)
            self.bg(lambda: self.client.call("/quit", "POST"), done, fail)
        else:
            self.deadline = time.time() + 45; self.render_server()
            def fail(e): self.deadline = 0.0; self.render_server(); self.toast(str(e) or self.t("no_server"), True)
            self.bg(start_server, None, fail)


def start_server():
    """Start the agent as its own background process: it keeps running when this window is closed."""
    if frozen(): cmd = [sys.executable, "--background"]
    else: cmd = [sys.executable, str(Path(__file__).resolve().parents[2] / "run_agent.py"), "--background"]
    env = dict(os.environ); env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"   # a new, independent copy of the one-file exe
    kw = {"creationflags": 0x08000000 | 0x00000008} if sys.platform == "win32" else {"start_new_session": True}   # no console, detached
    subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, **kw)


def _single_instance() -> bool:
    """Windows: only one app window. A second start brings the open one to the front instead."""
    if sys.platform != "win32": return True
    try:
        import ctypes
        k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
        k32.CreateMutexW(None, False, "Local\\RemotePCControlWindow")
        if k32.GetLastError() != 183: return True   # ERROR_ALREADY_EXISTS
        hwnd = u32.FindWindowW(None, TITLE)
        if hwnd: u32.ShowWindow(hwnd, 9); u32.SetForegroundWindow(hwnd)
        return False
    except Exception:
        return True


def _dpi_aware():
    if sys.platform != "win32": return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def run(port, token, starting=False) -> bool:
    """Show the app window and block until it is closed (must be the main thread).
    Returns False when the window cannot be created, so the caller can open the browser panel instead."""
    try: import tkinter as tk
    except Exception as e:
        print("tkinter is not available:", e); return False
    if not _single_instance(): return True
    _dpi_aware()
    try: root = tk.Tk()
    except Exception as e:
        print("Could not open the app window:", e); return False
    App(root, PanelClient(port, token), starting)
    root.mainloop()
    return True
