import tkinter as tk
from tkinter import filedialog, messagebox
import csv
import time
import socket
import json
import threading
import sys

try:
    import openpyxl
except Exception:
    openpyxl = None

HOST = '127.0.0.1'
PORT = 9999


def choose_file_and_stream():
    root = tk.Tk()
    root.withdraw()
    fp = filedialog.askopenfilename(title='Selecciona .csv o .xlsx')
    if not fp:
        print('No file selected')
        return
    if fp.lower().endswith('.csv'):
        with open(fp, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            rows = list(reader)
    elif fp.lower().endswith(('.xlsx', '.xls')):
        if openpyxl is None:
            print('openpyxl no está instalado. Instálalo para leer xlsx')
            return
        wb = openpyxl.load_workbook(fp, read_only=True)
        ws = wb.active
        rows = [[cell.value if cell.value is not None else '' for cell in row] for row in ws.iter_rows()]
    else:
        print('Formato no soportado')
        return

    if not rows:
        print('Archivo vacío')
        return

    header = [str(x) for x in rows[0]]
    data_rows = rows[1:]

    print('Conectando a', HOST, PORT)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOST, PORT))
    except Exception as e:
        print('No se pudo conectar al receptor:', e)
        return

    # send header as JSON
    msg = json.dumps({'type': 'header', 'vars': header}) + '\n'
    s.sendall(msg.encode('utf-8'))
    print('Header enviado:', header)

    # Stream rows at 1s interval; if not enough rows, loop
    idx = 0
    try:
        while True:
            if not data_rows:
                time.sleep(0.15)
                continue
            row = data_rows[idx % len(data_rows)]
            payload = {header[i]: row[i] if i < len(row) else '' for i in range(len(header))}
            msg = json.dumps({'type': 'row', 'data': payload}) + '\n'
            try:
                s.sendall(msg.encode('utf-8'))
            except Exception as e:
                print('Error enviando:', e)
                break
            idx += 1
            time.sleep(0.15)
    finally:
        try:
            s.close()
        except Exception:
            pass


if __name__ == '__main__':
    choose_file_and_stream()
