import os
import time
import datetime
import re
import pandas as pd
import vitaldb
import numpy as np
import random 

BASE_DIR = r"C:\Users\UX636EU\OneDrive - EY\Desktop\recordings" 
POLLING_INTERVAL = 1 # Segundos entre comprobaciones.

PRUEVAS = True # True para cuando estemos haciendo pruevas, False para cuando sea conectado real

DIRECTORIO_PRUEVA = r"C:\Users\UX636EU\OneDrive - EY\Desktop\recordings\Proves" # Directori en el que es troba el archiu de prova
ARCHIVO_VITAL = r"n5j8vrrsb_241209_115630.vital" # Nom del archiu de prova

SIM_MIN_SECS = 20
SIM_MAX_SECS = 30

# Directorio donde se guardarán los archivos CSV de onda
OUTPUT_DIR = r"C:\Users\UX636EU\OneDrive - EY\Desktop\UNI\PAEST\VitalParser-main\wave_output" 

# Asegúrate de que el directorio de salida exista
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------------------------------------------------------------------------------
# Frecuencia de muestreo estándar asumida para tracks no definidos
WAVE_STANDARD_RATE = 100.0 # Hz

# Si un track está aquí, usa su valor. Si no está, usa WAVE_STANDARD_RATE (100.0 Hz).
WAVE_TRACKS_FREQUENCIES = {
    'Intellivue/ABP': 125.0,    # Frecuencia personalizada en caso de saber qual es, en Hz
    'Intellivue/AOP': 125.0,  
    'Intellivue/ART': 125.0,    
    'Intellivue/AWP': 62.5,        # Si se pone 0, o no existe, usará WAVE_STANDARD_RATE
    'Intellivue/CO2': 62.5,
    'Intellivue/CVP': 125.0,
    'Intellivue/ECG_AVR': 500.0,
    'Intellivue/ECG_I': 500.0,
    'Intellivue/ECG_II': 500.0,
    'Intellivue/ECG_III': 500.0,
    'Intellivue/ECG_V': 500.0,
    'Intellivue/EEG': 125.0,
    'Intellivue/FLOW': 62.5, ## Ni idea de este
    'Intellivue/ICP': 125.0,
    'Intellivue/PLETH': 125.0,
    'Intellivue/RESP': 62.5,
}
# -------------------------------------------------------------------------------------------

def obtener_vital_timestamp(vital_path): 
    """
    Extrae la parte YMD_HMS (ej. '251025_154310') del nombre del archivo .vital.
    En formato PRUEVAS no se usa
    """

    filename = os.path.basename(vital_path)
    # Busca el patrón de 6 dígitos + _ + 6 dígitos antes de .vital
    match = re.search(r'(\d{6}_\d{6})\.vital$', filename)
    if match:
        return match.group(1)
    return "UnknownTimestamp"

def guardar_muestras_csv(track_name, samples_array, time_offsets_array, real_rate, start_index, vital_path, session_timestamp):
    """
    Exporta el array de muestras WAVE con su timestamp a un archivo CSV.
    Usa el session_timestamp en el nombre del archivo.
    Agrega los nuevos datos al final del archivo CSV con nombre fijo para la sesión/track.
    """

    total_samples = len(samples_array)
    if total_samples == 0 or real_rate <= 0:
        return

    try:
        
        # 2. Crear el DataFrame
        df_wave = pd.DataFrame({
            'Time (s)': time_offsets_array,
            'Value': samples_array,
            'Track': track_name,
            'SampleRate (Hz)': real_rate
        })
        
        # 3. Determinar el nombre y la ruta del archivo (NOMBRE FIJO con TIMESTAMP de sesión)
        safe_track_name = track_name.replace('/', '_').replace(' ', '_')
        
        # Nuevo Nombre: TrackName_VARIABLE_TIMESTAMP.csv (ej. Intellivue_ECG_251025_154310.csv)
        filename = f"{safe_track_name}_{session_timestamp}.csv" 
        filepath = os.path.join(OUTPUT_DIR, filename)

        # 4. Guardar en CSV en modo de 'append' (a)
        header_needed = not os.path.exists(filepath)
        
        df_wave.to_csv(filepath, mode='a', header=header_needed, index=False)
        
        print(f"  > **AÑADIDO:** {total_samples} puntos al archivo '{filename}' (Total hasta ahora: {start_index + total_samples} puntos)")

    except Exception as e:
        print(f"  > Error al guardar el CSV para {track_name}: {e}")
        
def obtener_directorio_del_dia(base_dir):
    """
    Obtiene el directorio basandose en el dia de hoy
    En el formato PRUEVAS no se usa
    """

    hoy = datetime.datetime.now()
    nombre_carpeta = hoy.strftime("%y%m%d")
    directorio_dia = os.path.join(base_dir, nombre_carpeta)
    if not os.path.exists(directorio_dia):
        raise FileNotFoundError(f"No existe la carpeta para hoy: {directorio_dia}")
    return directorio_dia

def obtener_vital_mas_reciente(directorio):
    """
    Busca en el directorio el archivo .vital con el timestamp mas grande (Por lo tanto el mas viejo o actual)
    En el formato PRUEVAS no se usa
    """

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

#--------------------------------------------------------------------------------------

def verificar_y_procesar(vital_path, last_size, last_read_counts, session_timestamp, simulated_growth_seconds):
    """
    Lee el archivo
    y en caso de modificación:
    Clasifica los tracks (NUM/WAVE)
        WAVE (Nomes els declarats a WAVE_TRACKS_FREQUENCIES):
            Usa la frecuencia configurada
                En caso de no existir utiliza la Estandar (100 Hz)
            Guarda las nuevas muestras WAVE en CSV. 
        NUM (No formen part de WAVE_TRACKS_FREQUENCIES):
            Usa 1 Hz
            Imprime las nuevas muestras NUM en consola
    """

    if PRUEVAS:
        print("\n--- MODO PRUEVAS ACTIVADO ---")

    if not os.path.exists(vital_path): # Mirar si encara existeix el .vital
        print(f" Error: El archivo {os.path.basename(vital_path)} ya no existe.")
        return last_size, last_read_counts

    current_size = os.path.getsize(vital_path) # Mirar el tamany del .vital

    if not PRUEVAS and current_size == last_size: # Comparal amb el tamany del anterior cop 
        return last_size, last_read_counts

    if not PRUEVAS and last_size == -1 or current_size < last_size: 
        return current_size, last_read_counts
    
    # Si el tamany ha canviat, MODIFICACIÓ!!
    print(f"\n El archivo {os.path.basename(vital_path)} se ha cambiado/simulado. Tamaño: {last_size if last_size != -1 else 0} -> {current_size} bytes.")

    rec = None
    available_tracks = []
    
    for attempt in range(5):
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
                print(f" Error al procesar el archivo después de {attempt} intentos: {e}")
                return last_size, last_read_counts

    if PRUEVAS:
        # Contador para verificar si todos los tracks han alcanzado su longitud máxima
        rec_finished_tracks = 0
        available_tracks_count = len(available_tracks) # Usar la longitud fuera del bucle

    nuevos_num = {}
    nuevos_wav = {}

    for s in available_tracks:
        
        try:
            is_wav = False
            real_rate = 0.0
            
            if s in WAVE_TRACKS_FREQUENCIES:
                is_wav = True
                rate_configurada = WAVE_TRACKS_FREQUENCIES.get(s, 0)
                if rate_configurada > 0:
                    real_rate = rate_configurada
                else:
                    real_rate = WAVE_STANDARD_RATE # 100.0 Hz
            
            # 1. Cargar muestras con el intervalo CORRECTO
            if is_wav:
                samples_all_raw = rec.to_numpy([s], interval=0, return_timestamp = True)
                if samples_all_raw is None or samples_all_raw.ndim != 2 or samples_all_raw.shape[1] != 2:
                    continue
                time_offset = samples_all_raw[:, 0] # Columna 0: Time offset
                samples_all = samples_all_raw[:, 1] # Columna 1: Samples values
                rate = real_rate
            else:
                samples_all = rec.get_track_samples(s, interval=1)
                rate = 1.0 # 1 Hz para NUM
                
            if samples_all is None or len(samples_all) == 0:
                if PRUEVAS:
                    available_tracks_count -= 1
                    continue

            # 2. Determinar nuevas muestras/bloques desde la última lectura
            last_count = last_read_counts.get(s, 0)
            current_total_count = len(samples_all)
            
            if current_total_count <= last_count:
                continue

            # Calcular el índice de corte para la simulación
            if PRUEVAS:
                # Si estamos en modo PRUEBAS, la "última muestra" es la anterior + el crecimiento simulado.
                
                # Número de muestras que se añadirían en la simulación
                simulated_added_samples = int(simulated_growth_seconds * rate)
                
                # El nuevo contador TOTAL que deberíamos alcanzar (limitado por el tamaño real del archivo)
                target_count = min(last_count + simulated_added_samples, current_total_count)
                
                # Si ya hemos leído hasta el final y no hay nuevo crecimiento simulado, saltar.
                if target_count <= last_count:
                     continue
                
                end_index = target_count
            else:
                # En modo real, simplemente leemos hasta el final del archivo.
                end_index = current_total_count

            # Extraer solo las muestras *nuevas* (desde last_count hasta end_index)
            nuevas_muestras = samples_all[last_count:end_index] 

            if is_wav:
                nuevos_tiempos = time_offset[last_count:end_index]
            
            if len(nuevas_muestras) == 0:
                continue

            # 3. Almacenar los datos y ACTUALIZAR el conteo total a end_index
            start_index = last_count # Índex de la primera mostra nova
        
            if is_wav:
                nuevos_wav[s] = (nuevas_muestras, nuevos_tiempos, real_rate, start_index) 
            else: # NUM
                nuevos_num[s] = nuevas_muestras

            # 4. Actualizar el conteo total de muestras/bloques leídos
            # En modo PRUEBAS, actualizamos a 'target_count' (que es 'end_index')
            # En modo REAL, actualizamos a 'current_total_count' (que es 'end_index')
            last_read_counts[s] = end_index
            
            if PRUEVAS and end_index == current_total_count:
                rec_finished_tracks += 1
            
        except Exception as track_e:
            print(f"[{s}] -> Error inesperado al procesar track: {track_e}")
            pass
    
    all_track_finished = False
    if PRUEVAS and available_tracks_count > 0 and rec_finished_tracks == available_tracks_count:
        all_track_finished = True
        print(" *** SIMULACION FINALIZADA: Se han procesado todos los datos del archivo. ")

    # 4. IMPRIMIR NUEVOS DATOS NUM
    num_samples_count = sum(len(v) for v in nuevos_num.values())
    if num_samples_count > 0 and nuevos_num:
        duracion_s_real = len(list(nuevos_num.values())[0]) 

        print(f"\n--- NUEVOS REGISTROS NUM ({num_samples_count} muestras) ---")
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
        
        for track_name, (samples_array, time_offsets_array, real_rate, start_index) in nuevos_wav.items(): 
            
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

                guardar_muestras_csv(track_name, samples_array, time_offsets_array, real_rate, start_index, vital_path, session_timestamp)

            else:
                 print(f" Track '{track_name}': Se clasificó como WAVE pero devolvió data inesperada.")

        if not wav_high_res_detected:
            print(" No se encontraron nuevos datos de onda de alta resolución.")

    if not nuevos_num and not nuevos_wav:
        print(" El archivo creció, pero no se encontraron nuevas muestras con el intervalo especificado.")

    return current_size, last_read_counts, all_track_finished

# --------------------------------------------------------------------------------------

def main_loop():
    if PRUEVAS:
        directorio_dia = DIRECTORIO_PRUEVA
        vital_path = os.path.join(DIRECTORIO_PRUEVA, ARCHIVO_VITAL)

        print(f" SIMULACIÓN DE ACTUALIZACIÓN: {SIM_MIN_SECS}-{SIM_MAX_SECS} segundos por ciclo.")
        print(f" Iniciando Polling cada {POLLING_INTERVAL} segundos")

    else:
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
            # --- LÓGICA DE SIMULACIÓN (NUEVO) ---
            if PRUEVAS:
                # 1. Determinar el tamaño de la actualización simulada (en segundos)
                simulated_growth_seconds = random.randint(SIM_MIN_SECS, SIM_MAX_SECS)
                
                # 2. Reemplazar 'last_size' con un valor ficticio para forzar el procesamiento.
                # Como no podemos modificar el tamaño real del archivo, usamos un truco:
                # last_size = -1 (o cualquier valor != current_size)
                # La lógica de verificación y procesamiento siempre se ejecutará en modo PRUEVAS.
                
                print(f"\n--- SIMULACIÓN ---: Procesando un bloque de {simulated_growth_seconds} segundos.")
            else:
                simulated_growth_seconds = 0 # No se usa en modo real

            # 2. Pasar el timestamp a la función de procesamiento
            last_size, last_read_counts, finished = verificar_y_procesar(
                vital_path, 
                last_size, 
                last_read_counts, 
                session_timestamp, 
                simulated_growth_seconds # <--- NUEVO PARÁMETRO
            )
            
            if PRUEVAS and finished:
                break
            
            time.sleep(POLLING_INTERVAL)

    except KeyboardInterrupt:
        print("\n Finalizando Polling.")

if __name__ == "__main__":
    main_loop()
