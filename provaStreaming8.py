import os
import time
import datetime
import re
import pandas as pd
import vitaldb
import numpy as np 

# --- CONFIGURACIÓN ---
BASE_DIR = r"C:\Users\UX636EU\OneDrive - EY\Desktop\recordings" 
POLLING_INTERVAL = 1 # Segundos entre comprobaciones.

# Directorio donde se guardarán los archivos CSV de onda
# NOTA: Asegúrate de que esta ruta sea válida para ti
OUTPUT_DIR = r"C:\Users\UX636EU\OneDrive - EY\Desktop\UNI\PAEST\VitalParser-main\wave_output" 

# Asegúrate de que el directorio de salida exista
os.makedirs(OUTPUT_DIR, exist_ok=True)


# --- FRECUENCIA POR DEFECTO Y CONFIGURACIÓN POR TRACK ---
# Frecuencia de muestreo estándar asumida para tracks no definidos
WAVE_STANDARD_RATE = 100.0 # Hz

# Si un track está aquí, usa su valor. Si no está, usa WAVE_STANDARD_RATE (100.0 Hz).
WAVE_TRACKS_FREQUENCIES = {
    'Demo/ECG': 0,    # Frecuencia personalizada en caso de saber qual es, en Hz
    'Demo/PLETH': 0,  
    'Demo/ART': 0,    
    'Demo/CVP': 0,        # Si se pone 0, o no existe, usará WAVE_STANDARD_RATE
    'Demo/EEG': 0,
    'Demo/CO2': 0,
}
# ---------------------

# --------------------------------------------------------------------------------------
## FUNCIONES DE UTILIDAD (MODIFICADAS: guardar_muestras_csv y obtener_vital_timestamp)
# --------------------------------------------------------------------------------------

def obtener_vital_timestamp(vital_path):
    """
    Extrae la parte YMD_HMS (ej. '251025_154310') del nombre del archivo .vital.
    """
    filename = os.path.basename(vital_path)
    # Busca el patrón de 6 dígitos_6 dígitos antes de .vital
    match = re.search(r'(\d{6}_\d{6})\.vital$', filename)
    if match:
        return match.group(1)
    # Intenta buscar el patrón justo antes de .vital (menos seguro)
    match = re.search(r'_(\d{6}_\d{6})\.vital$', filename)
    if match:
        return match.group(1)
    return "UnknownTimestamp"

def guardar_muestras_csv(track_name, samples_array, real_rate, start_index, vital_path, session_timestamp):
    """
    Exporta el array de muestras WAVE con su timestamp a un archivo CSV.
    Usa el session_timestamp en el nombre del archivo.
    Agrega los nuevos datos al final del archivo CSV con nombre fijo para la sesión/track.
    """
    total_samples = len(samples_array)
    if total_samples == 0 or real_rate <= 0:
        return

    try:
        # 1. Generar la columna de tiempo (Time Offset)
        start_time_s = start_index / real_rate
        time_offsets = start_time_s + np.arange(total_samples) / real_rate
        
        # 2. Crear el DataFrame
        df_wave = pd.DataFrame({
            'Time (s)': time_offsets,
            'Value': samples_array,
            'Track': track_name,
            'SampleRate (Hz)': real_rate
        })
        
        # 3. Determinar el nombre y la ruta del archivo (NOMBRE FIJO con TIMESTAMP de sesión)
        safe_track_name = track_name.replace('/', '_').replace(' ', '_')
        
        # Nuevo Nombre: TrackName_SESSION_TIMESTAMP.csv (ej. Demo_ECG_251025_154310.csv)
        filename = f"{safe_track_name}_{session_timestamp}.csv" 
        filepath = os.path.join(OUTPUT_DIR, filename)

        # 4. Guardar en CSV en modo de 'append' (a)
        header_needed = not os.path.exists(filepath)
        
        df_wave.to_csv(filepath, mode='a', header=header_needed, index=False)
        
        print(f"  > 💾 **AÑADIDO:** {total_samples} puntos al archivo '{filename}' (Total hasta ahora: {start_index + total_samples} puntos)")

    except Exception as e:
        print(f"  > ⚠️ Error al guardar el CSV para {track_name}: {e}")
        
def obtener_directorio_del_dia(base_dir):
    hoy = datetime.datetime.now()
    nombre_carpeta = hoy.strftime("%y%m%d")
    directorio_dia = os.path.join(base_dir, nombre_carpeta)
    if not os.path.exists(directorio_dia):
        raise FileNotFoundError(f"No existe la carpeta para hoy: {directorio_dia}")
    return directorio_dia

def obtener_vital_mas_reciente(directorio):
    archivos = [f for f in os.listdir(directorio) if f.endswith(".vital")]
    if not archivos:
        raise FileNotFoundError(f"No se encontraron archivos .vital en {directorio}")

    pattern = re.compile(r'_(\d{6})_(\d{6})\.vital$')
    with_timestamp = []

    for fname in archivos:
        m = pattern.search(fname)
        if not m:
            continue
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

    if not with_timestamp:
        raise FileNotFoundError(f"No se encontraron archivos .vital válidos en {directorio}")

    with_timestamp.sort(key=lambda x: x[1], reverse=True)
    return with_timestamp[0][0]


# --------------------------------------------------------------------------------------
## 🎯 Función de procesamiento (Llamada actualizada con el timestamp)
# --------------------------------------------------------------------------------------

def verificar_y_procesar(vital_path, last_size, last_read_counts, session_timestamp):
    """
    Lee el archivo, clasifica los tracks (NUM/WAVE), usa la frecuencia configurada 
    o la estándar (100 Hz) para el WAVE y guarda las nuevas muestras WAVE en CSV.
    Se pasa session_timestamp para nombrar los archivos.
    """
    if not os.path.exists(vital_path):
        print(f" Error: El archivo {os.path.basename(vital_path)} ya no existe.")
        return last_size, last_read_counts

    current_size = os.path.getsize(vital_path)

    if current_size == last_size:
        return last_size, last_read_counts

    if last_size == -1 or current_size > last_size:
        action = "ha encontrado" if last_size == -1 else "ha cambiado"
        print(f"\n El archivo {os.path.basename(vital_path)} se {action}. Tamaño: {last_size if last_size != -1 else 0} -> {current_size} bytes.")
    else:
        return current_size, last_read_counts

    rec = None
    available_tracks = []
    
    for attempt in range(3):
        try:
            time.sleep(0.1)
            rec = vitaldb.VitalFile(vital_path)
            available_tracks = rec.get_track_names()
            if not available_tracks:
                raise ValueError("El archivo está vacío o no contiene tracks aún.")
            break
        except Exception as e:
            if attempt < 2:
                time.sleep(0.5)
            else:
                print(f" Error al procesar el archivo después de 3 intentos: {e}")
                return last_size, last_read_counts

    nuevos_num = {}
    nuevos_wav = {}
    
    for s in available_tracks:
        
        try:
            is_wav = False
            real_rate = 0.0
            
            # --- ASIGNACIÓN DE FRECUENCIA Y CLASIFICACIÓN ---
            if s in WAVE_TRACKS_FREQUENCIES:
                is_wav = True
                rate_configurada = WAVE_TRACKS_FREQUENCIES.get(s, 0)
                if rate_configurada > 0:
                    real_rate = rate_configurada
                else:
                    real_rate = WAVE_STANDARD_RATE # 100.0 Hz
            
            if s not in WAVE_TRACKS_FREQUENCIES:
                 is_wav = False
            
            # 1. Cargar muestras con el intervalo CORRECTO
            if is_wav:
                samples_all_raw = rec.to_numpy([s], interval=0) 
                samples_all = samples_all_raw.flatten() 
            else:
                samples_all = rec.get_track_samples(s, interval=1)
                
            if samples_all is None or len(samples_all) == 0:
                continue
            
            # --- Lógica de Detección de Novedades ---
            if is_wav:
                 current_total_count = len(samples_all) 
                 last_count = last_read_counts.get(s, 0)
                 if current_total_count <= last_count:
                     continue
                 nuevas_muestras = samples_all[last_count:]
                 
                 start_index = last_count
                 nuevos_wav[s] = (nuevas_muestras, real_rate, start_index) 
                 
            else:
                current_total_count = len(samples_all)
                last_count = last_read_counts.get(s, 0)
                if current_total_count <= last_count:
                    continue
                nuevas_muestras = samples_all[last_count:]
                nuevos_num[s] = nuevas_muestras

            # 3. Actualizar el conteo total de muestras/bloques leídos
            last_read_counts[s] = current_total_count
            
        except Exception as track_e:
            print(f"[{s}] -> Error inesperado al procesar track: {track_e}")
            pass

    # 4. IMPRIMIR NUEVOS DATOS NOMINALES (NUM)
    num_samples_count = sum(len(v) for v in nuevos_num.values())
    if num_samples_count > 0 and nuevos_num:
        duracion_s_real = len(list(nuevos_num.values())[0]) 

        print(f"\n--- NUEVOS REGISTROS NOMINALES (NUM) ({num_samples_count} muestras) ---")
        print(f" Se detectaron {duracion_s_real} muestras (segundos).")
        
        data_for_df = {}
        for k, v in nuevos_num.items():
            start_index_for_track = last_read_counts.get(k, len(v)) - len(v) 
            data_for_df[k] = pd.Series([val for val in v], index=[start_index_for_track + i for i in range(len(v))])
            
        df_num = pd.DataFrame(data_for_df)
        print(df_num)
    
    # 5. PROCESAR Y GUARDAR NUEVOS DATOS WAV
    if nuevos_wav:
        print(f"\n--- PROCESANDO Y GUARDANDO DATOS WAVE (Alta Resolución) ---")
    
        wav_high_res_detected = 0
        
        for track_name, (samples_array, real_rate, start_index) in nuevos_wav.items(): 
            
            if isinstance(samples_array, np.ndarray) and samples_array.ndim == 1:
                wav_high_res_detected += 1
                total_samples = len(samples_array)
                duracion_calculada = total_samples / real_rate
                
                print(f"[{track_name}] -> Cargado {total_samples} puntos nuevos.")
                print(f"  > Frecuencia Asignada: {real_rate:.1f} Hz.")
                print(f"  > Duración Calculada: {duracion_calculada:.2f} segundos.")
                
                valid_data_points = np.isfinite(samples_array)
                if np.any(valid_data_points):
                    min_val = np.nanmin(samples_array)
                    max_val = np.nanmax(samples_array)
                    print(f"  > Rango de valores (Valores Válidos): {min_val:.2f} a {max_val:.2f}")
                else:
                    print(f"  > Rango de valores: Data Nula.")

                # --- EXPORTAR A CSV (ACUMULATIVO con TIMESTAMP) ---
                guardar_muestras_csv(track_name, samples_array, real_rate, start_index, vital_path, session_timestamp)

            else:
                 print(f" Track '{track_name}': Se clasificó como WAVE pero devolvió data inesperada.")

        if not wav_high_res_detected:
            print(" No se encontraron nuevos datos de onda de alta resolución.")

    if not nuevos_num and not nuevos_wav:
        print(" El archivo creció, pero no se encontraron nuevas muestras con el intervalo especificado.")

    return current_size, last_read_counts

# --------------------------------------------------------------------------------------
## Función Principal (MODIFICADA: Extracción y Paso del Timestamp)
# --------------------------------------------------------------------------------------

def main_loop():
    try:
        directorio_dia = obtener_directorio_del_dia(BASE_DIR)
        vital_path = obtener_vital_mas_reciente(directorio_dia)
    except FileNotFoundError as e:
        print(f" Error: {e}")
        return

    # 1. Extraer el timestamp de la sesión
    session_timestamp = obtener_vital_timestamp(vital_path)

    print(f" Carpeta del día: {directorio_dia}")
    print(f" Archivo .vital más reciente: {os.path.basename(vital_path)}")
    print(f" Timestamp de Sesión (para CSV): {session_timestamp}")
    print(f" Directorio de salida CSV (Acumulativo): {OUTPUT_DIR}")
    print(f" Frecuencia WAVE por defecto: {WAVE_STANDARD_RATE} Hz")
    print(f" Iniciando Polling cada {POLLING_INTERVAL} segundos")

    last_size = -1
    last_read_counts = {}

    try:
        while True:
            # 2. Pasar el timestamp a la función de procesamiento
            last_size, last_read_counts = verificar_y_procesar(vital_path, last_size, last_read_counts, session_timestamp)
            time.sleep(POLLING_INTERVAL)

    except KeyboardInterrupt:
        print("\n Finalizando Polling.")

if __name__ == "__main__":
    main_loop()
