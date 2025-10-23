import os
import time
import datetime
import re
import pandas as pd
import vitaldb

BASE_DIR = r"C:\Users\UX636EU\OneDrive - EY\Desktop\recordings" # Directorio configurado en el VitalRecorder para guardar los archivos
POLLING_INTERVAL = 2  # Segundos entre comprobaciones. Ajustar si es necesario. (Siguientes pasos)

# funcion para obtener la carpeta del dia actual (YYMMDD)
def obtener_directorio_del_dia(base_dir):
    hoy = datetime.datetime.now()                               # Obtener fecha actual
    nombre_carpeta = hoy.strftime("%y%m%d")                     # Nombre que deberia tener la carpeta
    directorio_dia = os.path.join(base_dir, nombre_carpeta)     # Busca si existe la carpeta
    if not os.path.exists(directorio_dia):                      # Si no existe, lanza error
        raise FileNotFoundError(f"No existe la carpeta para hoy: {directorio_dia}")
    return directorio_dia 

# funcion para obtener el archivo .vital mas reciente (o el que este siendo escrito)
def obtener_vital_mas_reciente(directorio):
    archivos = [f for f in os.listdir(directorio) if f.endswith(".vital")]  # Lista de archivos .vital
    if not archivos:                                                        # Si no hay archivos, lanza error
        raise FileNotFoundError(f"No se encontraron archivos .vital en {directorio}")

    pattern = re.compile(r'_(\d{6})_(\d{6})\.vital$')  # Patron para extraer timestamp
    with_timestamp = []

    for fname in archivos:
        m = pattern.search(fname) # Comparando el patron descrito con el de los archivos
        fullpath = os.path.join(directorio, fname)  # Guardar ruta completa

        yymmdd = m.group(1)  # Separar patron yymmdd
        hhmmss = m.group(2)  # Separar patron hhmmss
        yy = int(yymmdd[0:2])
        mm = int(yymmdd[2:4])   # Definir variables de cada uno
        dd = int(yymmdd[4:6])
        hh = int(hhmmss[0:2])
        mi = int(hhmmss[2:4])
        ss = int(hhmmss[4:6])
        year = 2000 + yy
        dt = datetime.datetime(year, mm, dd, hh, mi, ss) # Crear objeto datetime
        with_timestamp.append((fullpath, dt)) # Guardar ruta y timestamp (tupla)

    with_timestamp.sort(key=lambda x: x[1], reverse=True) # Ordenar por timestamp descendente
    return with_timestamp[0][0] # Devolver ruta del archivo mas reciente (La primera tupla)

# Comprobar cambios en el archivo y procesar nuevos datos (utilizando polling)
def verificar_y_procesar(vital_path, last_size, last_data):

    # Comprobar si el archivo existe (ha podido ser borrado externamente)
    if not os.path.exists(vital_path):
        print(f" Error: El archivo {os.path.basename(vital_path)} ya no existe.")
        return last_size, last_data

    current_size = os.path.getsize(vital_path) # En caso de que exista, obtener su tamaño

    
    if current_size == last_size: # Si no ha cambiado, salir
        return last_size, last_data

    # En caso de que haya cambiado
    print(f" El archivo {os.path.basename(vital_path)} ha cambiado. Tamaño: {last_size} -> {current_size} bytes.") # Notificar cambio de tamaño
    
    df = pd.DataFrame() 

    for attempt in range(3):
        try:
            time.sleep(0.1)
            
            rec = vitaldb.VitalFile(vital_path) # Abrir el archivo VitalDB
            
            available_tracks = rec.get_track_names() # Obtener nombres de tracks disponibles
            
            if not available_tracks: # Si no hay tracks, lanzar error
                 raise ValueError("El archivo está vacío o no contiene tracks aún.")

            data = {} 
            for s in available_tracks: # Iterar sobre cada track disponible
                try:
                    samples = rec.get_track_samples(s, interval=1) # Leer muestras del track con intervalo de 1 segundo

                    if samples is not None and len(samples) > 0: # Si se obtienen muestras, guardarlas en la variable data
                        data[s] = samples
                except Exception as track_e: # Si falla un track, continuamos con el siguiente (no abortamos toda la lectura)
                    print(f"Advertencia: Fallo al leer track '{s}': {track_e}")
                    pass 

            if not data: # Si no se obtuvieron datos de ningún track, lanzar error
                raise ValueError("Se encontraron tracks, pero no se pudo obtener ninguna muestra de datos.")

            # Construir DataFrame a partir del diccionario de datos (cada clave es un track, cada valor es una serie de muestras)
            df = pd.DataFrame(dict([ (k, pd.Series(v)) for k,v in data.items() ]))
            
            break # Éxito en la lectura
            
        except Exception as e: # Captura errores de lectura
            if "get_track_names" in str(e) or "get_track_samples" in str(e):
                 print(f" Advertencia: Posible error de API de VitalDB ({e}).")  # No contamos estos errores como intentos fallidos
            
            if attempt < 2:
                print(f"Intento {attempt + 1} fallido de leer el archivo: {e}. Reintentando...") # Reintentar hasta 3 veces
                time.sleep(0.5)
            else:
                print(f" Error al procesar el archivo después de 3 intentos: {e}")  # Abortar después de 3 intentos
                return last_size, last_data

    # Si el DataFrame no se creó correctamente
    if df.empty:
         return current_size, last_data 

    # Busca nuevos datos comparando con el DataFrame anterior
    # Compara los índices (muestras/timestamps) del DataFrame completo anterior y el actual
    # Esto busca cualquier índice que esté en 'df' pero no en 'last_data'
    nuevos = df.loc[~df.index.isin(last_data.index)]

    if not nuevos.empty: # Si se encontraron nuevos datos
        # Imprimir información sobre los nuevos datos detectados
        print(f" Se detectaron {len(nuevos)} nuevos registros (desde índice {nuevos.index.min()} hasta {nuevos.index.max()}).")
        
        # Imprimir los nuevos valores detectados
        print(" Nuevos valores detectados (todas las variables):")
        print(nuevos)
        nuevos = [] # Limpiar lista de nuevos datos después de imprimir
        
        return current_size, df  # Actualizar tamaño y datos
    else:
        # Se ha leído el archivo, pero los índices no han crecido (el archivo está estancado o el intervalo es muy grande)
        print(f" Archivo cambiado, pero no se encontraron nuevos registros (tamaño actual: {len(df.index)}, anterior: {len(last_data.index)}).")
        return current_size, df


def main_loop():
    try:
        directorio_dia = obtener_directorio_del_dia(BASE_DIR) # Conseguir el directorio que buscar para hoy
        vital_path = obtener_vital_mas_reciente(directorio_dia) # Buscar el ultimo .vital
    except FileNotFoundError as e:
        print(f" Error: {e}") # Si alguno de estos falla envia el error
        return


    # Imprime lo que esta passando (porque tenia el problema de que petava i no sabia donde)
    print(f" Carpeta del día: {directorio_dia}")
    print(f" Archivo .vital más reciente: {os.path.basename(vital_path)}")
    print(f" Iniciando Polling cada {POLLING_INTERVAL} segundos")

    last_size = -1   # Inicializado a -1 para que asi lea el primer dato
    last_data = pd.DataFrame() # Inicializa el DataFrame

    try:
        while True: # BUCLE INFINITO !!!!!!!!!!!
            last_size, last_data = verificar_y_procesar(vital_path, last_size, last_data) # funcion en bucle infinito
            time.sleep(POLLING_INTERVAL) # Espera el tiempo de polling

    except KeyboardInterrupt: # En caso de querer finalizar abortar el programa (Se tiene que canviar, pero para tener algo)
        print("\n Finalizando Polling.")

if __name__ == "__main__": # Funcion que se ejecuta al iniciar el programa
    main_loop() 
