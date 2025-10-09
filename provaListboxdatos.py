import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog
import threading
import time
import os
import difflib

import math
import random
from collections import deque
import socket
import json

# Shared latest values received from the emitter
latest_data = {}


def start_receiver(host='127.0.0.1', port=9999):
    def run():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((host, port))
            srv.listen(1)
            print('Receiver listening on', host, port)
        except Exception as e:
            print('Failed to start receiver:', e)
            return

        conn = None
        buf = ''
        while True:
            try:
                if conn is None:
                    conn, addr = srv.accept()
                    print('Emitter connected from', addr)
                data = conn.recv(4096).decode('utf-8')
                if not data:
                    # connection closed
                    conn.close()
                    conn = None
                    continue
                buf += data
                while '\n' in buf:
                    line, buf = buf.split('\n', 1)
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue
                    mtype = msg.get('type')
                    if mtype == 'header':
                        vars = msg.get('vars', [])
                        # update the listbox on the main thread
                        def do_update():
                            listbox.delete(0, tk.END)
                            for v in vars:
                                listbox.insert(tk.END, v)
                        try:
                            root.after(0, do_update)
                        except Exception:
                            pass
                    elif mtype == 'row':
                        data_map = msg.get('data', {})
                        # update latest_data
                        for k, v in data_map.items():
                            latest_data[k] = v
            except Exception as e:
                print('Receiver error:', e)
                try:
                    if conn:
                        conn.close()
                except Exception:
                    pass
                conn = None
                time.sleep(1.0)

    th = threading.Thread(target=run, daemon=True)
    th.start()


# start receiver automatically
start_receiver()


root = tk.Tk()
root.title("Selección múltiple")
root.geometry("400x500")

# Aixo a posteriori sera analitzat i carregat des del fitxer (variable)
opciones = [
    "ECG", "RR", "ST_I", "ST_II", "ST_III", "NIBP_SYS",
    "ECG", "RR", "ST_I", "ST_II", "ST_III", "NIBP_SYS",
    "ECG", "RR", "ST_I", "ST_II", "ST_III", "NIBP_SYS",
    "ECG", "RR", "ST_I", "ST_II", "ST_III", "NIBP_SYS",
]

# Frame per mantenir Listbox i Scrollbar
main_frame = tk.Frame(root)
main_frame.grid(row=0, column=0, sticky='nsew', padx=8, pady=8)

# Configuracio que fa la finestra expendible (finestra de seleccio inicial)
root.grid_rowconfigure(0, weight=1)
root.grid_columnconfigure(0, weight=1)

# Scrollbar i Listbox que s'adaptin a la finestra (configuracio inicial de la scrollbar i listbox)
scrollbar = tk.Scrollbar(main_frame, orient=tk.VERTICAL)
listbox = tk.Listbox(main_frame, selectmode='multiple', yscrollcommand=scrollbar.set)
scrollbar.config(command=listbox.yview)
listbox.grid(row=0, column=0, sticky='nsew')
scrollbar.grid(row=0, column=1, sticky='ns')

# Configuracio que fa la listbox expansible
main_frame.grid_rowconfigure(0, weight=1)
main_frame.grid_columnconfigure(0, weight=1)

# Obrir les opcions de la listbox i omplir la listbox
for opcion in opciones:
    listbox.insert(tk.END, opcion)

# Funcio que s'activa al clicar el boto "Mostrar seleccion"
# Llegeix les opcions seleccionades i obre una finestra nova amb una matriu de graficas
def mostrar_seleccion():
    seleccion = [listbox.get(i) for i in listbox.curselection()]
    if not seleccion: # Si no s'ha seleccionat res
        messagebox.showwarning("Error", "No ha seleccionado nada")
    else: # Si s'ha seleccionat alguna cosa
        n = len(seleccion)
        # Decide grouping or single per-variable mode based on the checkbox
        if group_var.get():
            # We'll ask how many series per graph and let the user group variables
            # into graphs. Grouping UI will appear and block until the user finishes.
            try:
                buffer_count = simpledialog.askinteger("Series por gráfica",
                                                       "¿Cuántas líneas por gráfica?",
                                                       parent=root,
                                                       initialvalue=2,
                                                       minvalue=1,
                                                       maxvalue=20)
                if buffer_count is None:
                    buffer_count = 1
            except Exception:
                buffer_count = 1

            # Grouping Toplevel: let user select exactly 'buffer_count' variables per group
            groups = []
            available = list(seleccion)

            group_win = tk.Toplevel(root)
            group_win.title('Agrupar variables por gráfica')
            group_win.geometry('500x400')

            info = tk.Label(group_win, text=f'Selecciona hasta {buffer_count} variables por grupo y pulsa "Guardar grupo"')
            info.pack(fill='x', padx=6, pady=6)

            lb_frame = tk.Frame(group_win)
            lb_frame.pack(fill='both', expand=True, padx=6, pady=6)

            avail_lb = tk.Listbox(lb_frame, selectmode='multiple')
            avail_lb.grid(row=0, column=0, sticky='nsew')
            sb = tk.Scrollbar(lb_frame, command=avail_lb.yview)
            sb.grid(row=0, column=1, sticky='ns')
            avail_lb.config(yscrollcommand=sb.set)

            saved_lb = tk.Listbox(lb_frame)
            saved_lb.grid(row=0, column=2, sticky='nsew', padx=(6,0))

            lb_frame.grid_rowconfigure(0, weight=1)
            lb_frame.grid_columnconfigure(0, weight=1)
            lb_frame.grid_columnconfigure(2, weight=1)

            def refresh_available():
                avail_lb.delete(0, tk.END)
                for it in available:
                    avail_lb.insert(tk.END, it)
                info.config(text=f'Restantes: {len(available)} variables. Selecciona hasta {buffer_count} por grupo.')

            def save_group():
                sel = avail_lb.curselection()
                if not sel:
                    messagebox.showwarning('Atención', 'Selecciona al menos una variable para guardar el grupo', parent=group_win)
                    return
                sel_names = [available[i] for i in sel]
                if len(sel_names) > buffer_count:
                    messagebox.showwarning('Atención', f'Has seleccionado más de {buffer_count} variables', parent=group_win)
                    return
                # If there will remain variables and current selection is smaller than buffer_count, disallow
                if len(sel_names) < buffer_count and (len(available) - len(sel_names)) > 0:
                    messagebox.showwarning('Atención', f'Tienes que seleccionar {buffer_count} variables por grupo, excepto para el último grupo', parent=group_win)
                    return
                groups.append(sel_names)
                saved_lb.insert(tk.END, ', '.join(sel_names))
                # remove from available (by value)
                for name in sorted(sel_names, reverse=True):
                    try:
                        available.remove(name)
                    except ValueError:
                        pass
                refresh_available()
                if not available:
                    group_win.destroy()

            def finish_grouping():
                if available:
                    if len(available) <= buffer_count:
                        # confirm to add remaining as final group
                        if messagebox.askyesno('Confirmar', f'Quedan {len(available)} variables. Añadirlas como último grupo?', parent=group_win):
                            groups.append(list(available))
                            saved_lb.insert(tk.END, ', '.join(available))
                            available.clear()
                            group_win.destroy()
                    else:
                        messagebox.showwarning('Atención', f'Aún quedan {len(available)} variables, selecciona más grupos.', parent=group_win)
                else:
                    group_win.destroy()

            def cancel_grouping():
                groups.clear()
                group_win.destroy()

            btn_frame = tk.Frame(group_win)
            btn_frame.pack(fill='x', padx=6, pady=6)
            save_btn = tk.Button(btn_frame, text='Guardar grupo', command=save_group)
            save_btn.pack(side='left')
            finish_btn = tk.Button(btn_frame, text='Terminar', command=finish_grouping)
            finish_btn.pack(side='left', padx=6)
            cancel_btn = tk.Button(btn_frame, text='Cancelar', command=cancel_grouping)
            cancel_btn.pack(side='right')

            refresh_available()
            # Wait until grouping window is closed
            group_win.transient(root)
            group_win.grab_set()
            root.wait_window(group_win)

            # If user cancelled grouping (groups empty), abort
            if not groups:
                return

            # Now groups is a list of groups (each is list of variable names). Use groups_count for layout
            n = len(groups)
            cols = math.ceil(math.sqrt(n))
            rows = math.ceil(n / cols)

            # Comprobar que no existeixi cap altre finestre oberta abans d'obrir-ne una de nova (de resultats) (hi havia un error sino)
            comprovar_finestra(root)

            # Creem la finestra de resultats com a Toplevel perque es pugui tornar a la finestra de seleccio (i diferenciar-la despres per poder-la eliminar en el pas anterior)
            results_root = tk.Toplevel(root)
            # Identificadors per poder eliminar la finestra de resultats si es torna a clicar el boto sense tancar la finestra de resultats (i parar correctament els after jobs)
            root._current_results = results_root
            results_root._jobs = []
            results_root.title("Pagina de Datos para cada dato seleccionado (En graficas)")
            results_root.geometry("800x600")

            # En el moment de clicar que el boto no es pugui clicar fins que no es tanqui la finestra de resultats (per aixi evitar que es pugui obrir 2 finestres a l'hora)
            try:
                btn.config(state='disabled')
            except Exception:
                pass
        else:
            # Not grouping: one graph per selected variable
            groups = [[v] for v in seleccion]
            n = len(groups)
            cols = math.ceil(math.sqrt(n))
            rows = math.ceil(n / cols)
            comprovar_finestra(root)
            results_root = tk.Toplevel(root)
            root._current_results = results_root
            results_root._jobs = []
            results_root.title("Pagina de Datos para cada dato seleccionado (En graficas)")
            results_root.geometry("800x600")
            try:
                btn.config(state='disabled')
            except Exception:
                pass

        # Fer la matriu de cel·les que s'adapti a la finestra
        for r in range(rows):
            results_root.grid_rowconfigure(r, weight=1)
        for c in range(cols):
            results_root.grid_columnconfigure(c, weight=1)

        # Crea el que aniria dins de cada cel·la
        update_jobs = []  # Matriu on es guardaran els after jobs per poder-los eliminar despres (quan es premi volver)
        idx = 0
        for r in range(rows):
            for c in range(cols):
                if idx >= n: # Si ja s'han posat totes les variables seleccionades surt del bucle
                    break
                group = groups[idx]
                group_title = ', '.join(group)
                frame = tk.Frame(results_root, bd=1, relief='solid', padx=6, pady=6)
                frame.grid(row=r, column=c, sticky='nsew', padx=4, pady=4)

                # Label with the group's variables
                lbl = tk.Label(frame, text=group_title, anchor='w')
                lbl.pack(fill='x')

                # Placeholder per guardar el lloc on hi aniria la grafica, ja he ficat la grafica pero era de abans
                #placeholder = tk.Label(frame, text='[Gráfica reservada]', bg='#eee', fg='#666', bd=1, relief='ridge')
                #placeholder.pack(fill='both', expand=True, pady=(6,0))

                # Canvas on dibuixarem la grafica
                canvas = tk.Canvas(frame, bg='black', bd=1, relief='sunken')
                canvas.pack(fill='both', expand=True, pady=(6,0)) # Un altre cop nose la mitat de les merdes de aqui, fico perque estiguin maques (subjectiu a canvis si voleu)

                # Punts maxims dels grafics (Segurament s'haura de reduir)
                MAX_POINTS = 10
                # Estat definit pels canvas: suportem tantes series com elements al grup
                COLORS = ['#1f77b4', '#d62728', '#2ca02c', '#ff7f0e', '#9467bd',
                          '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
                state = {
                    'canvas': canvas,
                    'name': group_title,
                    'job': None,
                    'buffers': [deque(maxlen=MAX_POINTS) for _ in range(len(group))],
                    'colors': COLORS,
                    'vars': list(group),
                }

                def draw_multiseries_plot(s=state):
                    c = s['canvas']
                    name_local = s['name']
                    c.delete('all')
                    w = c.winfo_width()
                    h = c.winfo_height()
                    if w <= 4 or h <= 4:
                        return

                    left, right = 8, w - 8
                    top, bottom = 8, h - 8
                    width = right - left
                    height = bottom - top

                    # compute global min/max across all buffers to share scale
                    all_pts = [v for buf in s['buffers'] for v in list(buf)]
                    if not all_pts:
                        c.create_text(10, 10, anchor='nw', text=name_local, fill='#333')
                        return
                    minv = min(all_pts)
                    maxv = max(all_pts)
                    span = maxv - minv if maxv != minv else 1.0

                    # draw horizontal grid lines and value labels at the left
                    try:
                        grid_lines = 4
                        for gi in range(grid_lines + 1):
                            val = minv + (gi / grid_lines) * span
                            y = top + (1 - ((val - minv) / span)) * height
                            c.create_line(left, y, right, y, fill='#333', dash=(2, 4))
                            c.create_text(left - 6, y, anchor='e', text=f"{val:.2f}", fill='#bbb', font=(None, 8))
                    except Exception:
                        pass

                    # subtle axes
                    c.create_line(left, bottom, right, bottom, fill='#222')
                    c.create_line(left, top, left, bottom, fill='#222')

                    # draw each buffer
                    for idx_buf, buf in enumerate(s['buffers']):
                        pts = list(buf)
                        if not pts:
                            continue
                        count = len(pts)
                        xs = [left + (i / (count-1)) * width for i in range(count)] if count > 1 else [left + width]
                        ys = [top + (1 - ((v - minv) / span)) * height for v in pts]
                        color = s['colors'][idx_buf % len(s['colors'])]
                        for i in range(len(xs)-1):
                            c.create_line(xs[i], ys[i], xs[i+1], ys[i+1], fill=color, width=2)
                        # latest point marker
                        c.create_oval(xs[-1]-2, ys[-1]-2, xs[-1]+2, ys[-1]+2, fill=color, outline='')

                    c.create_text(left+6, top+6, anchor='nw', text=name_local, fill='#fff')

                def schedule_update_multiseries(s=state, interval=500):
                    # only draw/reschedule if both the results window and canvas still exist
                    try:
                        if not results_root.winfo_exists() or not s['canvas'].winfo_exists():
                            return
                    except Exception:
                        return
                    # append one new sample per buffer (random here; replace with real data source)
                    try:
                        # Prefer values from latest_data (sent by emitter). If absent, fall back to random.
                        for ib, varname in enumerate(s.get('vars', [])):
                            val = latest_data.get(varname)
                            if val is None:
                                v = random.random()
                            else:
                                try:
                                    v = float(val)
                                except Exception:
                                    v = random.random()
                            s['buffers'][ib].append(v)
                    except Exception:
                        pass
                    # draw updated buffers
                    draw_multiseries_plot(s)
                    # schedule next and save job id
                    try:
                        job = results_root.after(interval, lambda: schedule_update_multiseries(s, interval))
                        s['job'] = job
                        update_jobs.append(job)
                        try:
                            results_root._jobs.append(job)
                        except Exception:
                            pass
                    except Exception:
                        pass

                # redraw immediately when the canvas is resized
                canvas.bind('<Configure>', lambda e, s=state: draw_multiseries_plot(s))
                # start the periodic updates
                schedule_update_multiseries(state, interval=500)

                idx += 1

        # Oculta la finestra de selecció (root)
        try:
            root.withdraw()
        except Exception:
            pass

        # Boto Volver de la finestra de les Grafiques
        def volver():
            # Acabes amb totes les jobs de les grafiques (Eliminar les grafiques)
            try:
                jobs = getattr(results_root, '_jobs', None)
                if jobs:
                    for job in list(jobs):
                        try:
                            results_root.after_cancel(job)
                        except Exception:
                            pass
                    # Un cop parats i eliminats elimines els _jobs
                    results_root._jobs.clear()
                else: # Per si s'escapa algun que estiguin amb update_jobs (lo mateix)
                    for job in list(update_jobs):
                        try:
                            results_root.after_cancel(job)
                        except Exception:
                            pass
                    update_jobs.clear()
            except Exception:
                pass

            # Tencar la finestra de resultats
            try:
                results_root.destroy()
            except Exception:
                pass

            # Eliminar tots els current_results que quedin
            try:
                if getattr(root, '_current_results', None) is results_root:
                    root._current_results = None
            except Exception:
                pass

            # Fas que el boto anterior torni a funcionar (si, 45 minuts de la meva vida perduda en aixo)
            try:
                btn.config(state='normal')
            except Exception:
                pass

            # Torna a obrir la finestra de seleccio (root)
            try:
                root.deiconify()
            except Exception:
                pass

        # Si tenques la finestra per la 'X' que faci el mateix que el boto de volver
        try:
            results_root.protocol('WM_DELETE_WINDOW', volver)
        except Exception:
            pass

        # Boto de volver
        volver_btn = tk.Button(results_root, text='Volver', command=volver)
        volver_btn.grid(row=rows, column=0, columnspan=cols, sticky='ew', padx=6, pady=6)
        results_root.grid_rowconfigure(rows, weight=0)


def comprovar_finestra(root):
    try: # Buscar que no existeixi ninguna altre finestra oberta (de resultats)
        prev = getattr(root, '_current_results', None)
        if prev is not None and prev.winfo_exists():
            eliminar_finestra(prev) # En cas que si, destrueix la finestra de resultats anterior
    except Exception:
        pass

    # Tambe busca a veure si hi ha alguna finestra oberta (Toplevel) que no s'hagi tancat correctament (tambe pot ser que estiguin en threads diferents)
    try:
        for child in list(root.winfo_children()): # Mira dins dels threads de root 
            try:
                if child.winfo_class() == 'Toplevel' or isinstance(child, tk.Toplevel): # Si algun es Toplevel (llavors es una finestra de resultats)
                    eliminar_finestra(child) # Elimina la finestra
            except Exception:
                pass
    except Exception:
        pass
    
def eliminar_finestra(prev):
    if hasattr(prev, '_jobs'):
        for job in list(prev._jobs): # basicament busca si hi ha algun after job (grafica encara corrent o parada) i l'elimina
            try:
                prev.after_cancel(job)
            except Exception:
                pass
    try:
        prev.destroy() # Destrueix la finestra de resultats anterior
    except Exception:
        pass


# Controls frame inside main_frame so listbox keeps full width
controls_frame = tk.Frame(main_frame)
controls_frame.grid(row=1, column=0, columnspan=2, sticky='ew', padx=0, pady=(6,0))


# Use grid inside controls_frame and set weights so the button expands and checkbox stays right
controls_frame.grid_columnconfigure(0, weight=1)  # button column
controls_frame.grid_columnconfigure(1, weight=0)  # spacer
controls_frame.grid_columnconfigure(2, weight=0)  # checkbox

# Boto de la finestra original (inside controls frame) - this button will expand
btn = tk.Button(controls_frame, text="Mostrar selección", command=mostrar_seleccion)
btn.grid(row=0, column=0, sticky='ew')

# small spacer
spacer = tk.Frame(controls_frame, width=8)
spacer.grid(row=0, column=1)

# Checkbutton to toggle grouping mode: if checked, user groups variables into multi-line graphs
group_var = tk.BooleanVar(value=False)
chk = tk.Checkbutton(controls_frame, text='Agrupar variables', variable=group_var)
chk.grid(row=0, column=2, sticky='e')

root.grid_columnconfigure(0, weight=1)

root.mainloop()
