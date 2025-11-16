import os
import time
import datetime
import re
import pandas as pd
import vitaldb
import numpy as np
import random 

BASE_DIR = r"C:\Users\UX636EU\OneDrive - EY\Desktop\recordings" # Directorio base donde se encuentran las carpetas diarias de registros Vital 
POLLING_INTERVAL = 1 # Segundos entre comprobaciones.

# -------------------------------------------------------------------------------------------
PRUEVAS = True # True para cuando estemos haciendo pruevas, False para cuando sea conectado real

DIRECTORIO_PRUEVA = r"C:\Users\Usuari\OneDrive\Escritorio\VitalParse\VitalParser-main\records\10\250629" # Directorio en el que se encuentra el archivo de prueva
ARCHIVO_VITAL = r"tvpir4b4i_250629_225235.vital" # Nombre del archivo .vital de prueva (con el .vital incluido)

SIM_MIN_SECS = 20
SIM_MAX_SECS = 30 # Segundos maximos/minimos que se simularan como crecimiento del archivo en cada ciclo
# -------------------------------------------------------------------------------------------

OUTPUT_DIR = r"C:\Users\Usuari\OneDrive\Escritorio\VitalParse\VitalParser-main\results" # Directorio donde se guardarán los archivos CSV de onda

os.makedirs(OUTPUT_DIR, exist_ok=True) # En caso de que el directorio no exista, se crea

# -------------------------------------------------------------------------------------------
WAVE_STANDARD_RATE = 100.0 # Frecuencia de muestreo estándar asumida para tracks no definidos (en Hz)

# Si un track está aquí, usa su valor. Si no está, usa WAVE_STANDARD_RATE (100.0 Hz).
WAVE_TRACKS_FREQUENCIES = {
    'Intellivue/ABP': 125.0,    # Frecuencia personalizada en caso de saber qual es, en Hz
    'Intellivue/AOP': 125.0,  
    'Intellivue/ART': 125.0,    
    'Intellivue/AWP': 62.5,        # Si se pone 0, usará WAVE_STANDARD_RATE
    'Intellivue/CO2': 62.5,
    'Intellivue/CVP': 125.0,
    'Intellivue/ECG_AI': 0.0, # Ni idea de este
    'Intellivue/ECG_AS': 0.0, # Ni idea de este
    'Intellivue/ECG_AVR': 500.0,
    'Intellivue/ECG_ES': 0.0, # Ni idea de este
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

def obtener_vital_timestamp(vital_path): 
    """
    Extrae la parte YMD_HMS (ej. '251025_154310') del nombre del archivo .vital.
    En formato PRUEVAS no se usa
    """
    filename = os.path.basename(vital_path)
    match = re.search(r'(\d{6}_\d{6})\.vital$', filename) # Busca el patrón de 6 dígitos + _ + 6 dígitos antes de .vital
    if match:
        return match.group(1)
    return "UnknownTimestamp"

def guardar_muestras_csv(track_name, samples_array, start_index, session_timestamp, time_offsets_array):
    """
    Exporta el array de muestras (WAVE o NUM) con su timestamp a un archivo CSV.
    Usa el session_timestamp en el nombre del archivo.
    Si el time_offsets_array es None, genera timestamps basados en el start_index y real_rate (para NUM).
    Agrega los nuevos datos al final del archivo CSV con nombre fijo para la sesión/track.
    """
    if len(samples_array) == 0: # No hay muestras para guardar
        return

    try:
        # Crear DataFrame con timestamps y valores
        df = pd.DataFrame({
        'Time (s)': time_offsets_array,
        'Value': samples_array,
        })
        
        # Determinar el nombre y la ruta del archivo (NOMBRE FIJO con TIMESTAMP de sesión)
        safe_track_name = track_name.replace('/', '_').replace(' ', '_')
        
        # TrackName_VARIABLE_TIMESTAMP.csv (ej. Intellivue_ECG_WAVE_251025_154310.csv, Intellivue_ABP_NUM_251025_154310.csv)
        label = "_WAVE_" if track_name in WAVE_TRACKS_FREQUENCIES else "_NUM_"
        filename = f"{safe_track_name}{label}_{session_timestamp}.csv" 
        filepath = os.path.join(OUTPUT_DIR, filename)

        # Guardar en CSV en modo de 'append' (a)
        header_needed = not os.path.exists(filepath)
        df.to_csv(filepath, mode='a', header=header_needed, index=False)
        print(f"  > **AÑADIDO:** {len(samples_array)} puntos al archivo '{filename}' (Total hasta ahora: {start_index + len(samples_array)} puntos)")

    except Exception as e:
        print(f"  > Error al guardar el CSV para {track_name}: {e}")
        
def obtener_directorio_del_dia(base_dir):
    """
    Obtiene el directorio basandose en el dia de hoy
    En el formato PRUEVAS no se usa
    """
    directorio_dia = os.path.join(base_dir, datetime.datetime.now().strftime("%y%m%d"))
    if not os.path.exists(directorio_dia):
        raise FileNotFoundError(f"No existe la carpeta para hoy: {directorio_dia}")
    return directorio_dia

def obtener_vital_mas_reciente(directorio):
    """
    Busca en el directorio el archivo .vital con el timestamp mas grande (Por lo tanto el mas viejo o el ultimo creado)
    En el formato PRUEVAS no se usa
    """
    archivos = [f for f in os.listdir(directorio) if f.endswith(".vital")]
    if not archivos:
        raise FileNotFoundError(f"No se encontraron archivos .vital en {directorio}")

    with_timestamp = []

    for fname in archivos:
        m = re.compile(r'_(\d{6})_(\d{6})\.vital$').search(fname)
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
        dt = datetime.datetime(2000 + yy, mm, dd, hh, mi, ss)
        with_timestamp.append((fullpath, dt))

    if not with_timestamp:
        raise FileNotFoundError(f"No se encontraron archivos .vital válidos en {directorio}")

    with_timestamp.sort(key=lambda x: x[1], reverse=True)
    return with_timestamp[0][0]

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
            Guarda las nuevas muestras NUM en CSV.
    Devuelve el nuevo tamaño y el diccionario actualizado de conteos leídos.
    """
    if PRUEVAS:
        print("\n--- MODO PRUEVAS ACTIVADO ---")

    if not os.path.exists(vital_path): # Mirar si aun existe el .vital
        print(f" Error: El archivo {os.path.basename(vital_path)} ya no existe.")
        return last_size, last_read_counts, False

    current_size = os.path.getsize(vital_path) # Mirar el tamaño del .vital

    if not PRUEVAS and current_size == last_size: # Comparalo con el último tamaño conocido 
        return last_size, last_read_counts, False

    if not PRUEVAS and last_size == -1 or current_size < last_size: 
        return current_size, last_read_counts, False
    
    # Si el tamaño ha canviado, MODIFICACIÓN!!
    print(f"\n El archivo {os.path.basename(vital_path)} se ha {"simulado" if PRUEVAS else "cambiado"}. Tamaño: {last_size if last_size != -1 else 0} -> {current_size} bytes.")

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
            if attempt < 4:
                time.sleep(0.5)
            else:
                print(f" Error al procesar el archivo después de {attempt} intentos: {e}")
                return last_size, last_read_counts, False

    if PRUEVAS:
        rec_finished_tracks = 0 # Contador para verificar si todos los tracks han alcanzado su longitud máxima
        available_tracks_count = len(available_tracks) # Usar la longitud fuera del bucle

    nuevos_num = {}
    nuevos_wav = {}

    for s in available_tracks:
        try:
            is_wav = False
            real_rate = 0.0
            
            if s in WAVE_TRACKS_FREQUENCIES: # Track de tipo WAVE
                is_wav = True
                rate_configurada = WAVE_TRACKS_FREQUENCIES.get(s, 0)
                if rate_configurada > 0: # En caso de tener una frecuencia asignada
                    real_rate = rate_configurada
                else: # Si no tiene frecuencia asignada, usar la estándar
                    real_rate = WAVE_STANDARD_RATE # 100.0 Hz
            
            # Cargar muestras con el intervalo CORRECTO
            if is_wav:
                samples_period = 1.0 / real_rate
                samples_all_raw = rec.to_numpy([s], interval=samples_period, return_timestamp = True)
                time_offset = samples_all_raw[:, 0] # Columna 0: Time offset
                samples_all = samples_all_raw[:, 1] # Columna 1: Samples values
            else:
                samples_all_raw = rec.to_numpy([s], interval=1, return_timestamp = True)
                time_offset = samples_all_raw[:, 0] # Columna 0: Time offset
                samples_all = samples_all_raw[:, 1] # Columna 1: Samples values
                
            if samples_all is None or len(samples_all) == 0:
                if PRUEVAS:
                    available_tracks_count -= 1
                    continue

            # Determinar nuevas muestras/bloques desde la última lectura
            last_count = last_read_counts.get(s, 0)
            current_total_count = len(samples_all)
            
            if current_total_count <= last_count:
                continue

            # Calcular el índice de corte para la simulación
            if PRUEVAS:
                # Si estamos en modo PRUEBAS, la "última muestra" es la anterior + el crecimiento simulado.
                simulated_added_samples = int(simulated_growth_seconds * rate) # Número de muestras que se añadirían en la simulación
                
                target_count = min(last_count + simulated_added_samples, current_total_count) # El nuevo contador TOTAL que deberíamos alcanzar (limitado por el tamaño real del archivo)
                
                if target_count <= last_count: # Si ya hemos leído hasta el final y no hay nuevo crecimiento simulado, saltar.
                     continue
                
                end_index = target_count
            else:
                end_index = current_total_count # En modo Streaming, simplemente leemos hasta el final del archivo.

            nuevas_muestras = samples_all[last_count:end_index] # Extraer solo las muestras *nuevas* (desde last_count hasta end_index)

            nuevos_tiempos = time_offset[last_count:end_index] # Extraer los offsets de tiempo correspondientes

            if len(nuevas_muestras) == 0:
                continue

            start_index = last_count # Passar el indice de inicio para guardar en CSV (el ultimo leido de la vez anterior)
        
            if is_wav: # Almacenar los datos
                nuevos_wav[s] = (nuevas_muestras, nuevos_tiempos, real_rate, start_index) 
            else: # NUM
                nuevos_num[s] = (nuevas_muestras, nuevos_tiempos, 1.0, start_index)

            # Actualizar el conteo total de muestras/bloques leídos
            # En modo PRUEBAS, actualizamos a 'target_count' (que es 'end_index')
            # En modo REAL, actualizamos a 'current_total_count' (que es 'end_index')
            last_read_counts[s] = end_index
            
            if PRUEVAS and end_index == current_total_count:
                print(f"[{s}] -> Se han procesado todas las muestras disponibles para este track.") # Si se ha llegado al final de las muestras en PRUEVAS, se para el programa
                rec_finished_tracks += 1
            
        except Exception as track_e:
            print(f"[{s}] -> Error inesperado al procesar track: {track_e}")
            pass
    
    all_track_finished = False
    if PRUEVAS and available_tracks_count > 0 and rec_finished_tracks == available_tracks_count:
        all_track_finished = True
        print(" *** SIMULACION FINALIZADA: Se han procesado todos los datos del archivo. ")

    # GUARDAR NUEVOS DATOS NUM EN CSV
    num_samples_count = sum(len(samples) for samples in nuevos_num.values())
    if num_samples_count > 0 and nuevos_num:
        print(f"\n--- PROCESAMOS I GUARDANDO DATOS NUM ({num_samples_count} muestras) ---")
        print(f" Se detectaron {len(list(nuevos_num.values())[0][0]) } muestras (segundos).")
        
        for track_name, (samples_array, time_offsets_array, rate, start_index) in nuevos_num.items():
            print(f"[{track_name}] -> Cargado {len(samples_array)} puntos nuevos. Rango Índices: [{start_index}] a [{start_index + len(samples_array) - 1}]")

            # Llamar a la función de guardado SIN time_offsets_array
            guardar_muestras_csv(
                track_name, 
                samples_array, 
                start_index, 
                session_timestamp,
                time_offsets_array  
            )
    
    # PROCESAR Y GUARDAR NUEVOS DATOS WAV
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

                guardar_muestras_csv(
                    track_name, 
                    samples_array,  
                    start_index, 
                    session_timestamp, 
                    time_offsets_array
                )

            else:
                 print(f" Track '{track_name}': Se clasificó como WAVE pero devolvió data inesperada.")

        if not wav_high_res_detected:
            print(" No se encontraron nuevos datos de onda de alta resolución.")

    if not nuevos_num and not nuevos_wav:
        print(" El archivo creció, pero no se encontraron nuevas muestras con el intervalo especificado.")

    return current_size, last_read_counts, all_track_finished

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

    # Extraer el timestamp de la sesión
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
            if PRUEVAS:
                simulated_growth_seconds = random.randint(SIM_MIN_SECS, SIM_MAX_SECS) # Determinar el tamaño de la actualización simulada (en segundos)
                
                # Reemplazar 'last_size' con un valor ficticio para forzar el procesamiento.
                # Como no podemos modificar el tamaño real del archivo, usamos un truco:
                # last_size = -1 (o cualquier valor != current_size)
                # La lógica de verificación y procesamiento siempre se ejecutará en modo PRUEVAS.
                print(f"\n--- SIMULACIÓN ---: Procesando un bloque de {simulated_growth_seconds} segundos.")
            else:
                simulated_growth_seconds = 0 # No se usa en modo real

            # Pasar el timestamp a la función de procesamiento
            last_size, last_read_counts, finished = verificar_y_procesar(
                vital_path, 
                last_size, 
                last_read_counts, 
                session_timestamp, 
                simulated_growth_seconds
            )
            
            if PRUEVAS and finished:
                print(" *** SIMULACION FINALIZADA: Se han procesado todos los datos del archivo. ")
                break
            
            time.sleep(POLLING_INTERVAL)

    except KeyboardInterrupt:
        print("\n Finalizando Polling.")

if __name__ == "__main__":
    main_loop()
