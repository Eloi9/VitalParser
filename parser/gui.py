import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from parser.vital_utils import DARK_BG, LIGHT_BG, FG_COLOR

class VitalApp:
    def __init__(self, root, processor, configs):
        self.root = root
        self.processor = processor
        self.configs = configs
        # Flags para control del bucle
        self.running = False
        self.poll_ms = 1000  # Intervalo en milisegundos
        self._init_vars()
        self._build_ui()

    def _init_vars(self):
        self.record_dir = tk.StringVar()
        self.use_mean = tk.BooleanVar(value=False)
        self.mode = tk.StringVar(value='tabular')   # Selector de modo

    def _build_ui(self):
        self.root.title("Vital Processor GUI")
        self.root.geometry("900x600")
        self.root.configure(bg=DARK_BG)

        top = tk.Frame(self.root, bg=LIGHT_BG)
        top.pack(fill='x', padx=10, pady=10)

        # Directorio de grabaciones
        tk.Label(top, text="Recordings Dir:", bg=LIGHT_BG, fg=FG_COLOR).grid(row=0, column=0)
        tk.Entry(top, textvariable=self.record_dir, width=40,
                 bg=DARK_BG, fg=FG_COLOR, insertbackground=FG_COLOR).grid(row=0, column=1)
        tk.Button(top, text="Browse...", command=self._browse,
                  bg=LIGHT_BG, fg=FG_COLOR).grid(row=0, column=2)

        # Selector de modo (Tabular / Wave)
        tk.Label(top, text="Modo:", bg=LIGHT_BG, fg=FG_COLOR).grid(row=0, column=3, padx=(20,0))
        tk.Radiobutton(top, text="Tabular", variable=self.mode, value="tabular",
                       bg=LIGHT_BG, fg=FG_COLOR, selectcolor=LIGHT_BG).grid(row=0, column=4)
        tk.Radiobutton(top, text="Wave",    variable=self.mode, value="wave",
                       bg=LIGHT_BG, fg=FG_COLOR, selectcolor=LIGHT_BG).grid(row=0, column=5)

        # Botones Start / Stop
        tk.Button(top, text="Start", command=self._start_loop,
                  bg=LIGHT_BG, fg=FG_COLOR).grid(row=0, column=6, pady=5)
        tk.Button(top, text="Stop",  command=self._stop_loop,
                  bg=LIGHT_BG, fg=FG_COLOR).grid(row=0, column=7, pady=5)

        # Consola de log
        self.log = scrolledtext.ScrolledText(self.root, bg=DARK_BG, fg=FG_COLOR, height=15)
        self.log.pack(fill='both', expand=True, padx=10, pady=5)

        # Botón para mostrar resultados
        bot = tk.Frame(self.root, bg=DARK_BG)
        bot.pack(fill='x', padx=10, pady=5)
        tk.Checkbutton(bot, text="Use Mean", variable=self.use_mean,
                       bg=DARK_BG, fg=FG_COLOR).pack(side='left')
        tk.Button(bot, text="Show Results", command=self._show,
                  bg=LIGHT_BG, fg=FG_COLOR).pack(side='left')

    def _browse(self):
        d = filedialog.askdirectory()
        if d:
            self.record_dir.set(d)

    def _process(self):
        df = self.processor.process_once(self.record_dir.get(), mode=self.mode.get())
        if df is None:
            messagebox.showwarning("No data", "No datos válidos.")
            self.running = False
            return
        self._log_tail(df)

    def _log_tail(self, df):
        self.log.configure(state='normal')
        self.log.insert(tk.END, 'New iteration \n')
        for row in df.tail(3).to_dicts():
            line = ' '.join([f"{k}: {v}" for k,v in row.items()])
            self.log.insert(tk.END, line + '\n')
        self.log.configure(state='disabled')

    def _start_loop(self):
        if not self.running:
            self.running = True
            self._loop()

    def _stop_loop(self):
        self.running = False

    def _loop(self):
        if not self.running:
            return
        self._process()
        self.root.after(self.poll_ms, self._loop)

    def _show(self):
        if not hasattr(self.processor, 'latest_df') or self.processor.latest_df is None:
            messagebox.showwarning("No data", "Sin resultados.")
            return
        win = tk.Toplevel(self.root)
        win.configure(bg=DARK_BG)
        for cfg in self.configs:
            var = cfg['output_var']
            if var not in self.processor.latest_df:
                continue
            value = (self.processor.latest_df[var].mean()
                     if self.use_mean.get() else self.processor.latest_df[var].iloc[-1])
            tk.Label(win, text=f"{var}: {value:.3f}", font=(None, 16),
                     bg=DARK_BG, fg=FG_COLOR).pack(anchor='w', padx=10, pady=5)
