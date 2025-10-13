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

import matplotlib
matplotlib.use('TkAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt 

# Variable global para almacenar los últimos datos recibidos
latest_data = {}

def start_receiver(host='127.0.0.1', port=9999): # Comunicacion TCP/IP con el data_emitter.py (Primero se debe ejecutar el receiver (este programa))
    def run():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((host, port)) # Connexion al puerto/host
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
                while '\n' in buf:  # Procesado de mensajes separados por linea
                    line, buf = buf.split('\n', 1)
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue
                    mtype = msg.get('type')
                    if mtype == 'header': # Mirar el tipo del paquete recibido
                        vars = msg.get('vars', []) # En caso de ser header, actualizar la listbox
                        def do_update():
                            #listbox.delete(0, tk.END) # Eliminar todo lo que tiene y colocar los nuevos (Esto se puede variar por si se quieren actualizar variables a posteriori)
                            for v in vars:
                                listbox.insert(tk.END, v)   # Insertar las variables en la listbox
                        try:
                            root.after(0, do_update)
                        except Exception:
                            pass
                    elif mtype == 'row':  # Si es un paquete de datos, actualizar la variable latest_data
                        data_map = msg.get('data', {})
                        for k, v in data_map.items():
                            latest_data[k] = v # Guarda los datos
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
    th.start()  # Iniciar el hilo del receptor


root = tk.Tk() # Ventana principal
root.title("Selección múltiple") 
root.geometry("400x500")

def comprovar_finestra(root): # Funcion para comprobar si ya hay una ventana de resultados abierta y cerrarla (Evitar uno de los errors que havia)
    try:
        prev = getattr(root, '_current_results', None)
        if prev is not None and prev.winfo_exists():
            eliminar_finestra(prev)
    except Exception:
        pass
    try:
        for child in list(root.winfo_children()): 
            try:
                if child.winfo_class() == 'Toplevel' or isinstance(child, tk.Toplevel):
                    eliminar_finestra(child)
            except Exception:
                pass
    except Exception:
        pass
    
def eliminar_finestra(prev): # Funcion para eliminar la ventana de resultados 
    if hasattr(prev, '_jobs'):
        for job in list(prev._jobs):
            try:
                prev.after_cancel(job)
            except Exception:
                pass
    try:
        prev.destroy()
    except Exception:
        pass


# Variable que almacena las opciones de la listbox
opciones = []

# Frame para mantener Listbox i Scrollbar
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

# Ahora podemos llamar a start_receiver
start_receiver()

# Funcio que s'activa al clicar el boto "Mostrar seleccion"
def mostrar_seleccion():
    seleccion = [listbox.get(i) for i in listbox.curselection()]
    if not seleccion:
        messagebox.showwarning("Error", "No ha seleccionado nada")
        return
    
    # Si el checkbox de agrupar está marcado, abrir la ventana de agrupación
    groups = []
    if group_var.get():
        # Lógica para pedir buffer_count y abrir la ventana de agrupación...
        try:
            buffer_count = simpledialog.askinteger("Series por gráfica",
                                                    "¿Cuántas líneas por gráfica?",
                                                    parent=root,
                                                    initialvalue=2,
                                                    minvalue=1,
                                                    maxvalue=8) # Limitar entre 1 y 8 líneas por gráfica
            if buffer_count is None: buffer_count = 1
        except Exception: buffer_count = 1

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
            for it in available: avail_lb.insert(tk.END, it)
            info.config(text=f'Restantes: {len(available)} variables. Selecciona hasta {buffer_count} por grupo.')
        def save_group():
            sel = avail_lb.curselection()
            if not sel: return messagebox.showwarning('Atención', 'Selecciona al menos una variable para guardar el grupo', parent=group_win)
            sel_names = [available[i] for i in sel]
            if len(sel_names) > buffer_count: return messagebox.showwarning('Atención', f'Has seleccionado más de {buffer_count} variables', parent=group_win)
            if len(sel_names) < buffer_count and (len(available) - len(sel_names)) > 0: return messagebox.showwarning('Atención', f'Tienes que seleccionar {buffer_count} variables por grupo, excepto para el último grupo', parent=group_win)
            groups.append(sel_names)
            saved_lb.insert(tk.END, ', '.join(sel_names))
            for name in sorted(sel_names, reverse=True):
                try: available.remove(name)
                except ValueError: pass
            refresh_available()
            if not available: group_win.destroy()
        def finish_grouping():
            if available:
                if len(available) <= buffer_count:
                    if messagebox.askyesno('Confirmar', f'Quedan {len(available)} variables. Añadirlas como último grupo?', parent=group_win):
                        groups.append(list(available))
                        saved_lb.insert(tk.END, ', '.join(available))
                        available.clear()
                        group_win.destroy()
                else: messagebox.showwarning('Atención', f'Aún quedan {len(available)} variables, selecciona más grupos.', parent=group_win)
            else: group_win.destroy()
        def cancel_grouping():
            groups.clear()
            group_win.destroy()

        btn_frame = tk.Frame(group_win)
        btn_frame.pack(fill='x', padx=6, pady=6)
        tk.Button(btn_frame, text='Guardar grupo', command=save_group).pack(side='left')
        tk.Button(btn_frame, text='Terminar', command=finish_grouping).pack(side='left', padx=6)
        tk.Button(btn_frame, text='Cancelar', command=cancel_grouping).pack(side='right')

        refresh_available()
        group_win.transient(root)
        group_win.grab_set()
        root.wait_window(group_win)
        if not groups: return
    else:
        groups = [[v] for v in seleccion]
    # Final de la ventana de agrupación


    # Distribuir las gráficas en una cuadrícula lo más cuadrada posible
    n = len(groups)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)

    comprovar_finestra(root) # Comprobar si ya hay una ventana de resultados abierta y cerrarla

    results_root = tk.Toplevel(root)
    root._current_results = results_root
    results_root._jobs = [] # Para almacenar los IDs de los jobs programados
    results_root.title("Pagina de Datos para cada dato seleccionado (En graficas)")
    results_root.geometry("800x600")

    try:
        btn.config(state='disabled')
    except Exception:
        pass
    
    for r in range(rows):
        results_root.grid_rowconfigure(r, weight=1)
    for c in range(cols):
        results_root.grid_columnconfigure(c, weight=1)

    update_jobs = []  # Lista para almacenar los IDs de los jobs que se tendran que actualizar o destruir
    idx = 0
    for r in range(rows):
        for c in range(cols): # Crear un frame para cada gráfica
            if idx >= n:
                break
            group = groups[idx]
            group_title = ', '.join(group) # Título de la gráfica con los nombres de las variables (Juntarlas con comas)
            frame = tk.Frame(results_root, bd=1, relief='solid', padx=6, pady=6)
            frame.grid(row=r, column=c, sticky='nsew', padx=4, pady=4)

            MAX_POINTS = 50  # Máximo número de puntos a mostrar en el gráfico (ventana deslizante) (Si se quiere cambiar el tamaño de la ventana, cambiar este valor)
            COLORS = ['#d62728', '#2ca02c', '#ff7f0e', '#9467bd', '#1f77b4'
                      '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

            # Crear la figura de Matplotlib y los Axes
            fig = Figure(figsize=(5, 4), dpi=100)
            ax = fig.add_subplot(111)
            
            fig.patch.set_facecolor("#cccccc") 
            ax.set_facecolor("#10059e")
            ax.grid(True, linestyle='--', alpha=0.6) 

            # Incrustar la figura en el frame de Tkinter
            canvas_agg = FigureCanvasTkAgg(fig, master=frame)
            canvas_widget = canvas_agg.get_tk_widget()
            canvas_widget.pack(fill='both', expand=True, pady=(6,0))
            
            # Placeholder para guardar el estado y las referencias de las líneas
            state = {
                'fig': fig,
                'ax': ax,
                'canvas': canvas_agg,
                'name': group_title,
                'job': None,
                'buffers': [deque(maxlen=MAX_POINTS) for _ in range(len(group))], # Buffers inician VACÍOS
                'lines': [], 
                'vars': list(group),
                'total_points': 0, # Contador de puntos totales (para el eje X continuo) (Esto deberia ser el timestamp pero aun no lo consigo implementar, tamo en ello)
            }

            # Inicializar las líneas del gráfico con un punto mínimo [0], [0.0], para evitar el error de Matplotlib al intentar dibujar una línea vacía.
            x_init = [0]
            y_init = [0.0]
            for ib in range(len(group)):
                line, = ax.plot(x_init, y_init, label=group[ib], color=COLORS[ib % len(COLORS)])
                state['lines'].append(line)
            
            ax.legend(loc='upper right', fontsize=8)
            ax.set_title(group_title, fontsize=10)
            ax.set_xlim(0, MAX_POINTS) # Limites X iniciales 
            ax.set_ylim(-1, 1) # Limites Y iniciales (se auto-escalarán)

            def schedule_update_multiseries(s=state, interval=500):
                try:
                    if not results_root.winfo_exists():
                        return
                except Exception:
                    return
                
                # GENERAR NUEVOS DATOS (Recogidos de latest_data)
                try:
                    for ib, varname in enumerate(s.get('vars', [])):
                        val = latest_data.get(varname)
                        v = 0.0
                        if val is not None:
                            try:
                                v = float(val)  # Intentar convertir a float (hay error con valores no numéricos, strings o decimales mal formateados)
                            except Exception:
                                v = 0.0
                        s['buffers'][ib].append(v)
                    
                    s['total_points'] += 1
                    
                except Exception:
                    pass
                
                # Si no hay puntos, solo se actualizan los ejes con el valor inicial [0, 0.0]
                if s['total_points'] == 0:
                     s['canvas'].draw_idle()
                     return

                # ACTUALIZAR LOS EJES (X y Y)
                x_current = s['total_points']
                
                # Eje X: Deslizamiento. Se ajusta la ventana visible a los últimos MAX_POINTS
                x_start_limit = max(0, x_current - MAX_POINTS) 
                x_end_limit = x_current
                s['ax'].set_xlim(x_start_limit, x_end_limit) # Esto hace que se cree la ventana deslizante
                
                # Eje Y: Auto-escalado dinámico con margen
                all_pts = [v for buf in s['buffers'] for v in list(buf)] # Recoger TODOS los puntos visibles de TODOS los buffers
                if all_pts:
                    minv_raw = min(all_pts)
                    maxv_raw = max(all_pts)
                    span_raw = maxv_raw - minv_raw
                    
                    # Aplicar margen para el auto-escalado
                    if span_raw == 0: # Si todos los puntos son iguales, usar un margen fijo
                        min_y = minv_raw - 1.0 
                        max_y = maxv_raw + 1.0
                    else: # Si no son iguales, reajustar el eje Y con un margen del 10% del rango actual (intente que sea un valor fijo pero a grandes valores no se veia bien)
                        margin = 0.1 * span_raw
                        min_y = minv_raw - margin
                        max_y = maxv_raw + margin
                        
                    s['ax'].set_ylim(min_y, max_y)
                    
                # ACTUALIZAR LAS LÍNEAS DEL GRÁFICO
                for ib, buf in enumerate(s['buffers']):
                    # Y Data: Lista de los puntos en el búfer
                    y_data = list(buf)
                    data_length = len(y_data)

                    # X Data: La longitud debe coincidir con Y Data (data_length)
                    x_start_data = s['total_points'] - data_length # El rango X debe comenzar en s['total_points'] - data_length
                    x_data_visible = list(range(x_start_data, s['total_points']))

                    # set_data debe tener el mismo número de elementos para X e Y (havia algun elemento que tenia duplicados y daba error)
                    s['lines'][ib].set_data(x_data_visible, y_data)
                    
                # REDIBUJAR
                s['canvas'].draw_idle()
                
                # REPROGRAMAR
                try:
                    job = results_root.after(interval, lambda: schedule_update_multiseries(s, interval))
                    s['job'] = job
                    update_jobs.append(job)
                    results_root._jobs.append(job)
                except Exception:
                    pass

            # Iniciar las actualizaciones periódicas (cada 500 ms (se puede canviar este valor))
            schedule_update_multiseries(state, interval=500) 

            idx += 1

    # Oculta la finestra de selecció (root)
    try:
        root.withdraw()
    except Exception:
        pass

    # Boto Volver de la finestra de les Grafiques
    def volver():
        try:
            jobs = getattr(results_root, '_jobs', None)
            if jobs:
                for job in list(jobs):
                    try: results_root.after_cancel(job)
                    except Exception: pass
                results_root._jobs.clear()
            else:
                for job in list(update_jobs):
                    try: results_root.after_cancel(job)
                    except Exception: pass
                update_jobs.clear()
        except Exception: pass

        try: results_root.destroy()
        except Exception: pass
        try:
            if getattr(root, '_current_results', None) is results_root:
                root._current_results = None
        except Exception: pass
        try: btn.config(state='normal')
        except Exception: pass
        try: root.deiconify()
        except Exception: pass

    # Si tenques la finestra per la 'X' que faci el mateix que el boto de volver
    try:
        results_root.protocol('WM_DELETE_WINDOW', volver)
    except Exception:
        pass

    # Boto de volver
    volver_btn = tk.Button(results_root, text='Volver', command=volver)
    volver_btn.grid(row=rows, column=0, columnspan=cols, sticky='ew', padx=6, pady=6)
    results_root.grid_rowconfigure(rows, weight=0)


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
