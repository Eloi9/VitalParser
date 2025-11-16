import os
import time
import datetime
import re
import pandas as pd
import vitaldb
import numpy as np
import random 
# --- Imports Zarr ---
import zarr
# Mantenim la importació de Blosc
from numcodecs import Blosc 
from vitaldb import VitalFile 

BASE_DIR = r"C:\Users\UX636EU\OneDrive - EY\Desktop\recordings" 
POLLING_INTERVAL = 1 

# -------------------------------------------------------------------------------------------
PRUEVAS = True 

DIRECTORIO_PRUEVA = r"C:\Users\Usuari\OneDrive\Escritorio\VitalParse\VitalParser-main\records\10\250629" 
ARCHIVO_VITAL = r"tvpir4b4i_250629_225235.vital" 

SIM_MIN_SECS = 20
SIM_MAX_SECS = 30
# -------------------------------------------------------------------------------------------

OUTPUT_DIR = r"C:\Users\Usuari\OneDrive\Escritorio\VitalParse\VitalParser-main\results" 
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------------------------------------------------------------------------------------------
# CONFIGURACIÓ DE FREQÜÈNCIES
# -------------------------------------------------------------------------------------------
WAVE_STANDARD_RATE = 100.0 

WAVE_TRACKS_FREQUENCIES = {
    'Intellivue/ABP': 125.0, 'Intellivue/AOP': 125.0, 'Intellivue/ART': 125.0,     
    'Intellivue/AWP': 62.5, 'Intellivue/CO2': 62.5, 'Intellivue/CVP': 125.0,
    'Intellivue/ECG_AI': 0.0, 'Intellivue/ECG_AS': 0.0, 'Intellivue/ECG_AVR': 500.0,
    'Intellivue/ECG_ES': 0.0, 'Intellivue/ECG_I': 500.0, 'Intellivue/ECG_II': 500.0,
    'Intellivue/ECG_III': 500.0, 'Intellivue/ECG_V': 500.0, 'Intellivue/EEG': 125.0,
    'Intellivue/FLOW': 62.5, 'Intellivue/ICP': 125.0, 'Intellivue/PLETH': 125.0,
    'Intellivue/RESP': 62.5,
}

# -------------------------------------------------------------------------------------------
# CONFIGURACIÓ ZARR
# -------------------------------------------------------------------------------------------
ZARR_PATH = os.path.join(OUTPUT_DIR, "session_data.zarr") 

# CORRECCIÓ CLAU 1: Instanciar l'objecte Blosc directament. 
# Aquesta és la forma més fiable de passar un compressor en Zarr V2.
_COMPRESSOR = Blosc(cname='zstd', clevel=5, shuffle=Blosc.BITSHUFFLE)


# -------------------------------------------------------------------------------------------
# ZARR HELPER FUNCTIONS 
# -------------------------------------------------------------------------------------------

def _safe_group(root: zarr.hierarchy.Group, path: str) -> zarr.hierarchy.Group:
    """Crea (si cal) i retorna el subgrup dins root (p.ex. 'signals/Intellivue/PLETH')."""
    parts = [p for p in path.split("/") if p]
    g = root
    for p in parts:
        g = g.require_group(p)
    return g

def _get_group_if_exists(root: zarr.hierarchy.Group, path: str):
    """Retorna el grup si existeix, o None si no existeix (no crea res)."""
    parts = [p for p in path.split("/") if p]
    g = root
    for p in parts:
        if p in g:
            obj = g[p]
            if isinstance(obj, zarr.hierarchy.Group): 
                g = obj
            else:
                return None
        else:
            return None
    return g

def _append_1d(ds: zarr.core.Array, values: np.ndarray) -> None:
    """Append eficient a un dataset 1D."""
    if values.size == 0:
        return
    n0 = ds.shape[0]
    ds.resize(n0 + values.size)
    ds[n0:] = values

def vital_to_zarr(
    vital_path: str,
    zarr_path: str,
    chunk_len: int = 30000,
    window_secs: float | None = None,
) -> None:
    """
    Processa l'arxiu vital utilitzant la lògica de freqüències definida per 
    diferenciar WAVE (alta freqüència) i NUM (1 Hz).
    """
    if not os.path.exists(vital_path):
        raise FileNotFoundError(f"No s'ha trobat el .vital: {vital_path}")

    # NOTA: vitaldb.VitalFile obre el fitxer. S'ha d'assegurar que es tanca.
    vf = VitalFile(vital_path)
    available_tracks = vf.get_track_names() 

    os.makedirs(os.path.dirname(zarr_path) or ".", exist_ok=True)
    # Ús de open_group per forçar l'API V2 síncrona
    root = zarr.open_group(zarr_path, mode="a") 

    root.attrs.setdefault("schema", "v1")
    root.attrs["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")

    signals_root = _safe_group(root, "signals")

    written_any = False
    total_added_samples = 0
    written_tracks = 0
    skipped_no_new = 0
    skipped_empty = 0
    
    for track in available_tracks:
        # 1. Determinar la freqüència i l'interval de mostreig (Lògica WAVE/NUM)
        rate = 1.0 
        interval = 1.0 
        track_type = "NUM"
        
        if track in WAVE_TRACKS_FREQUENCIES:
            track_type = "WAVE"
            rate_configurada = WAVE_TRACKS_FREQUENCIES.get(track, 0)
            if rate_configurada > 0:
                rate = rate_configurada
            else:
                rate = WAVE_STANDARD_RATE 
            
            interval = 1.0 / rate 

        # 2. Llegim del .vital utilitzant l'interval CORRECTE
        try:
            data = vf.to_numpy([track], interval=interval, return_timestamp=True)
        except Exception as e:
            print(f"[WARN] No s'ha pogut llegir el track '{track}' amb interval={interval}: {e}")
            skipped_empty += 1
            continue

        if data is None or data.size == 0:
            skipped_empty += 1
            continue

        ts = data[:, 0].astype(np.float64, copy=False)
        vals = data[:, 1].astype(np.float64, copy=False)

        # 3. Finestra temporal opcional (per a simulació)
        if window_secs is not None:
            t1 = ts[-1]
            t0 = t1 - float(window_secs)
            m = (ts >= t0) & (ts <= t1)
            ts = ts[m]
            vals = vals[m]

        if ts.size == 0:
            skipped_empty += 1
            continue

        ts_ms = np.rint(ts * 1000.0).astype(np.int64)
        vals_f32 = vals.astype(np.float32)

        # 4. Deduplicació (Només afegir mostres noves)
        track_group_path = f"signals/{track}"
        existing_grp = _get_group_if_exists(root, track_group_path)

        last_ts = -1
        if existing_grp is not None and "time_ms" in existing_grp and existing_grp["time_ms"].shape[0] > 0:
            try:
                last_ts = int(existing_grp["time_ms"][-1])
                mask_new = ts_ms > last_ts
                ts_ms = ts_ms[mask_new]
                vals_f32 = vals_f32[mask_new]
            except Exception as e:
                print(f"[WARN] No s'ha pogut llegir l'últim time_ms de '{track}': {e}")
                
        if ts_ms.size == 0:
            skipped_no_new += 1
            continue

        # 5. Escriure a Zarr
        grp = _safe_group(signals_root, track)

        try:
            # CORRECCIÓ CLAU 2: Passem l'objecte Blosc instanciat directament
            ds_time = grp.require_dataset(
                "time_ms", 
                shape=(0,), 
                chunks=(chunk_len,), 
                dtype="int64",
                compressor=_COMPRESSOR, 
            )
            ds_val = grp.require_dataset(
                "value", 
                shape=(0,), 
                chunks=(chunk_len,), 
                dtype="float32",
                compressor=_COMPRESSOR,
            )
            
        except Exception as e:
            # Si falla la creació (el punt més sensible)
            raise Exception(f"Falla la creació o el resize de l'array Zarr per a '{track}': {type(e).__name__}: {e}")


        _append_1d(ds_time, ts_ms)
        _append_1d(ds_val, vals_f32)

        # Afegim metadades de freqüència i tipus
        grp.attrs["track"] = track
        grp.attrs["sampling_rate_hz"] = rate
        grp.attrs["track_type"] = track_type 

        print(f"[{track_type} {rate:.1f} Hz] +{ts_ms.size} mostres (total={ds_time.shape[0]})")
        total_added_samples += int(ts_ms.size)
        written_tracks += 1
        written_any = True

    # 6. Resum
    if written_any:
        print(f"\n✅ Escrita/actualitzada la col·lecció a: {zarr_path}")
        print(f"   Tracks actualitzades: {written_tracks}, mostres afegides: {total_added_samples}")
    else:
        print(f"\n⚠️  No s'ha escrit cap mostra nova.")
# -------------------------------------------------------------------------------------------


# ... (La resta de funcions es mantenen) ...
def obtener_vital_timestamp(vital_path): 
    filename = os.path.basename(vital_path)
    match = re.search(r'(\d{6}_\d{6})\.vital$', filename)
    if match:
        return match.group(1)
    return "UnknownTimestamp"

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

#--------------------------------------------------------------------------------------

def verificar_y_procesar(vital_path, last_size, simulated_growth_seconds):
    """
    Comprova la mida i crida a la funció vital_to_zarr utilitzant 
    la configuració de freqüències.
    """

    if PRUEVAS:
        print("\n--- MODO PRUEVAS ACTIVADO ---")
    
    if not os.path.exists(vital_path):
        print(f" Error: El archivo {os.path.basename(vital_path)} ya no existe.")
        return -1, True

    current_size = os.path.getsize(vital_path)

    if not PRUEVAS and current_size == last_size: 
        return last_size, False

    if not PRUEVAS and (last_size == -1 or current_size < last_size): 
        return current_size, False
    
    print(f"\n El archivo {os.path.basename(vital_path)} se ha cambiado/simulado. Tamaño: {last_size if last_size != -1 else 0} -> {current_size} bytes.")

    # --- BLOC DE PROCESSAMENT ZARR AMB FREQÜÈNCIES ---
    try:
        print(f"\n--- INICIANT PROCESSAMENT ZARR AL FITXER: {ZARR_PATH} ---")
        
        window_to_process = simulated_growth_seconds if PRUEVAS else None

        vital_to_zarr(
            vital_path=vital_path,
            zarr_path=ZARR_PATH,  
            window_secs=window_to_process 
        )

    except Exception as e:
        # Impressió del tipus d'excepció (type(e).__name__)
        print(f" Error CRÍTIC al processar a Zarr: {type(e).__name__}: {e}")
        return last_size, False

    return current_size, False 

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

    session_timestamp = obtener_vital_timestamp(vital_path)

    print(f" Carpeta del día: {directorio_dia}")
    print(f" Archivo .vital más reciente: {os.path.basename(vital_path)}")
    print(f" Timestamp de Sesión (per a Zarr): {session_timestamp}")
    print(f" Directorio de salida ZARR (Acumulativo): {ZARR_PATH}")
    print(f" Iniciando Polling cada {POLLING_INTERVAL} segundos")

    last_size = -1

    if PRUEVAS:
        total_sim_cycles = 10 
        current_sim_cycle = 0

    try:
        while True:
            if PRUEVAS:
                simulated_growth_seconds = random.randint(SIM_MIN_SECS, SIM_MAX_SECS)
                print(f"\n--- SIMULACIÓN ---: Leyendo bloque de {simulated_growth_seconds} segundos (Ciclo {current_sim_cycle+1}/{total_sim_cycles}).")
            else:
                simulated_growth_seconds = 0

            current_size, finished = verificar_y_procesar(
                vital_path, 
                last_size, 
                simulated_growth_seconds
            )
            last_size = current_size 
            
            if PRUEVAS:
                current_sim_cycle += 1
                if current_sim_cycle >= total_sim_cycles:
                    print(" *** SIMULACION FINALIZADA: Límite de ciclos alcanzado.")
                    break
            
            time.sleep(POLLING_INTERVAL)

    except KeyboardInterrupt:
        print("\n Finalizando Polling.")

if __name__ == "__main__":
    main_loop()
