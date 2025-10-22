import os
import time
import datetime
import re
import pandas as pd
import vitaldb

# === CONFIGURACIÓN BASE ===
BASE_DIR = r"C:\Users\Usuari\OneDrive\Escritorio\recordings"
POLLING_INTERVAL = 2  # Segundos entre comprobaciones. Ajustar si es necesario.

# funcion para obtener la carpeta del dia actual (YYMMDD)
def obtener_directorio_del_dia(base_dir):
    hoy = datetime.datetime.now() # Obtener fecha actual
    nombre_carpeta = hoy.strftime("%y%m%d")  # Nombre que deberia tener la carpeta
    directorio_dia = os.path.join(base_dir, nombre_carpeta) # Busca si existe la carpeta
    if not os.path.exists(directorio_dia): # Si no existe, lanza error
        raise FileNotFoundError(f"No existe la carpeta para hoy: {directorio_dia}")
    return directorio_dia 

# funcion para obtener el archivo .vital mas reciente (o el que este siendo escrito)
def obtener_vital_mas_reciente(directorio):
    archivos = [f for f in os.listdir(directorio) if f.endswith(".vital")] # Lista de archivos .vital
    if not archivos: # Si no hay archivos, lanza error
        raise FileNotFoundError(f"No se encontraron archivos .vital en {directorio}")

    pattern = re.compile(r'_(\d{6})_(\d{6})\.vital$') # Patron para extraer timestamp
    with_timestamp = []

    for fname in archivos:
        m = pattern.search(fname)
        fullpath = os.path.join(directorio, fname)

        yymmdd = m.group(1)
        hhmmss = m.group(2)
        yy = int(yymmdd[0:2])
        mm = int(yymmdd[2:4])
        dd = int(yymmdd[4:6])
        hh = int(hhmmss[0:2])
        mi = int(hhmmss[2:4])
        ss = int(hhmmss[4:6])
        year = 2000 + yy
        dt = datetime.datetime(year, mm, dd, hh, mi, ss)
        with_timestamp.append((fullpath, dt))

    with_timestamp.sort(key=lambda x: x[1], reverse=True)
    return with_timestamp[0][0]


# ----------------------------------------------------------------------

# === FUNCIÓN: Comprobación y Procesamiento de Archivo (Polling) ===
def verificar_y_procesar(vital_path, last_size, last_data):
    """
    Verifica si el archivo ha cambiado (por tamaño) y procesa todos los nuevos datos.
    Retorna (nuevo_tamaño, nuevos_datos) para actualizar el estado.
    """
    
    # 1. Comprobar si el archivo existe y obtener su tamaño actual
    if not os.path.exists(vital_path):
        print(f" Error: El archivo {os.path.basename(vital_path)} ya no existe.")
        return last_size, last_data

    current_size = os.path.getsize(vital_path)

    # 2. Comprobación del cambio
    if current_size == last_size:
        return last_size, last_data

    # 3. Procesamiento si ha habido cambio
    print(f" El archivo {os.path.basename(vital_path)} ha cambiado. Tamaño: {last_size} -> {current_size} bytes.")
    
    df = pd.DataFrame() 

    # ⚠️ Bucle de REINTENTO ROBUSTO
    for attempt in range(3):
        try:
            time.sleep(0.1) # Pausa mínima
            
            # --- LECTURA DE DATOS USANDO 'TRACK' API (COMPATIBLE) ---
            rec = vitaldb.VitalFile(vital_path)
            
            # PASO 1: Obtener TODOS los tracks disponibles
            available_tracks = rec.get_track_names() 
            
            if not available_tracks:
                 raise ValueError("El archivo está vacío o no contiene tracks aún.")

            data = {}
            for s in available_tracks:
                try:
                    # ✅ CORRECCIÓN 1: Intervalo reducido a 100 ms (10 Hz) 
                    # para forzar a la API a devolver más historial.
                    samples = rec.get_track_samples(s, interval=1) 

                    if samples is not None and len(samples) > 0:
                        data[s] = samples
                except Exception as track_e:
                    # Si falla un track, continuamos con el siguiente
                    print(f"Advertencia: Fallo al leer track '{s}': {track_e}")
                    pass 

            if not data:
                raise ValueError("Se encontraron tracks, pero no se pudo obtener ninguna muestra de datos.")

            # 2. Convertir el diccionario de arrays a DataFrame
            df = pd.DataFrame(dict([ (k, pd.Series(v)) for k,v in data.items() ]))
            
            break # Éxito en la lectura
            
        except Exception as e:
            if "get_track_names" in str(e) or "get_track_samples" in str(e):
                 print(f" Advertencia: Posible error de API de VitalDB ({e}).") 
            
            if attempt < 2:
                print(f"Intento {attempt + 1} fallido de leer el archivo: {e}. Reintentando...")
                time.sleep(0.5)
            else:
                print(f" Error al procesar el archivo después de 3 intentos: {e}") 
                return last_size, last_data

    # Si el DataFrame no se creó correctamente
    if df.empty:
         return current_size, last_data 

    # --- Detección de Nuevos Registros ---
    # Compara los índices (muestras/timestamps) del DataFrame completo anterior y el actual
    # Esto busca cualquier índice que esté en 'df' pero no en 'last_data'
    nuevos = df.loc[~df.index.isin(last_data.index)]

    if not nuevos.empty:
        # ✅ CORRECCIÓN 2: Imprimir la información del nuevo bloque
        print(f" Se detectaron {len(nuevos)} nuevos registros (desde índice {nuevos.index.min()} hasta {nuevos.index.max()}).")
        
        # ✅ CORRECCIÓN 3: Imprimir TODOS los nuevos valores
        print(" Nuevos valores detectados (TODAS las variables):")
        print(nuevos)
        nuevos = []
        
        return current_size, df  # Actualizar tamaño y datos
    else:
        # Se ha leído el archivo, pero los índices no han crecido (el archivo está estancado o el intervalo es muy grande)
        print(f" Archivo cambiado, pero no se encontraron nuevos registros (tamaño actual: {len(df.index)}, anterior: {len(last_data.index)}).")
        return current_size, df
        

# ----------------------------------------------------------------------

# === INICIO DEL MONITOREO ===
def main_loop():
    # ... (El código de main_loop() no ha cambiado)
    try:
        directorio_dia = obtener_directorio_del_dia(BASE_DIR)
        vital_path = obtener_vital_mas_reciente(directorio_dia)
    except FileNotFoundError as e:
        print(f" Error: {e}")
        return

    print(f" Carpeta del día: {directorio_dia}")
    print(f" Archivo .vital más reciente: {os.path.basename(vital_path)}")
    print(f" Iniciando Polling cada {POLLING_INTERVAL} segundos...")

    # VARIABLES DE ESTADO INICIAL
    last_size = -1  
    last_data = pd.DataFrame() 

    try:
        while True:
            last_size, last_data = verificar_y_procesar(vital_path, last_size, last_data)
            time.sleep(POLLING_INTERVAL)

    except KeyboardInterrupt:
        print("\n Finalizando Polling.")

if __name__ == "__main__":
    main_loop()
