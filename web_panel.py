#!/usr/bin/env python3
import os
import posixpath
import shutil
import psutil
import subprocess
import tempfile
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, url_for, send_from_directory, flash, abort, Response, jsonify
from functools import wraps
from werkzeug.utils import secure_filename

# Ustawienie katalogu tymczasowego – aby ominąć problemy przy przesyłaniu dużych plików
TEMP_DIR = '/home/pi/tmp'
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR, mode=0o1777)
os.environ['TMPDIR'] = TEMP_DIR
tempfile.tempdir = TEMP_DIR

app = Flask(__name__)
app.secret_key = 'twoj_sekretny_klucz'  # Zamień na własny, trudny ciąg

# Konfiguracja autoryzacji i głównego katalogu
USERNAME = 'admin'
PASSWORD = 'mawerik1'
BASE_DIR = os.path.abspath("/home/pi/RetroPie")

# ------------------ Filtry Jinja2 ------------------ #
def format_datetime(value):
    return datetime.fromtimestamp(value).strftime('%Y-%m-%d %H:%M:%S')

def format_filesize(value):
    if value is None:
        return ''
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if value < 1024:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} PB"

app.jinja_env.filters['datetimeformat'] = format_datetime
app.jinja_env.filters['filesizeformat'] = format_filesize

# ------------------ Funkcje autoryzacyjne ------------------ #
def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def authenticate():
    return Response(
        'Brak dostępu. Zaloguj się poprawnymi danymi.\n', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

def safe_path(path):
    abs_path = os.path.abspath(os.path.join(BASE_DIR, path))
    if os.path.commonpath([abs_path, BASE_DIR]) != BASE_DIR:
        abort(403)
    return abs_path

# ------------------ Funkcje pomocnicze ------------------ #
def round_1(x):
    return round(x, 1)

def get_cpu_temp():
    try:
        temp_str = subprocess.check_output(['vcgencmd', 'measure_temp']).decode().strip()
        return temp_str.split('=')[1].split("'")[0] + "°C"
    except Exception:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                temp_val = f.read().strip()
                return str(round(float(temp_val) / 1000, 1)) + "°C"
        except Exception:
            return "N/A"

def get_ssd_temperatures():
    sensors = {}
    try:
        output = subprocess.check_output(
            ["sudo", "nvme", "smart-log", "/dev/nvme0"],
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        for line in output.splitlines():
            if "temperature" in line.lower():
                parts = line.split(":")
                if len(parts) >= 2:
                    sensor_name = parts[0].strip()
                    temp_str = parts[1].strip()   # np. "28 C (301 K)"
                    tokens = temp_str.split()
                    if tokens:
                        raw_val = tokens[0].lower().replace("°c", "").replace("c", "").strip()
                        if raw_val.replace('.', '', 1).isdigit():
                            sensors[sensor_name] = raw_val + "°C"
                        else:
                            sensors[sensor_name] = tokens[0].replace("C", "").replace("c", "") + "°C"
        return sensors
    except Exception:
        return {}

def get_monitoring_data(selected_sensor=None):
    cpu_usage = round_1(psutil.cpu_percent(interval=0.0))
    mem = psutil.virtual_memory()
    mem_percent = round_1(mem.percent)
    disk = psutil.disk_usage(BASE_DIR)
    disk_percent = round_1((disk.used / disk.total) * 100) if disk.total > 0 else 0
    disk_free = disk.total - disk.used

    cpu_temp = get_cpu_temp()
    ssd_temps = get_ssd_temperatures()
    if not ssd_temps:
        ssd_selected_name = None
        ssd_selected_temp = "N/A"
    else:
        if selected_sensor and selected_sensor in ssd_temps:
            ssd_selected_name = selected_sensor
            ssd_selected_temp = ssd_temps[selected_sensor]
        else:
            ssd_selected_name = list(ssd_temps.keys())[0]
            ssd_selected_temp = ssd_temps[ssd_selected_name]
    return {
        'cpu_usage': cpu_usage,
        'cpu_temp': cpu_temp,
        'mem_total': mem.total,
        'mem_used': mem.used,
        'mem_percent': mem_percent,
        'disk_total': disk.total,
        'disk_used': disk.used,
        'disk_free': disk_free,
        'disk_percent': disk_percent,
        'ssd_all': ssd_temps,
        'ssd_selected_name': ssd_selected_name,
        'ssd_temp': ssd_selected_temp
    }

# ------------------ Endpoint API dla monitoringu ------------------ #
@app.route('/api/monitoring')
@requires_auth
def api_monitoring():
    selected_sensor = request.args.get('ssd_sensor', None)
    mon = get_monitoring_data(selected_sensor)
    response = {
        'cpu_usage': mon['cpu_usage'],
        'cpu_temp': mon['cpu_temp'],
        'mem_percent': mon['mem_percent'],
        'disk_percent': mon['disk_percent'],
        'disk_used_human': format_filesize(mon['disk_used']),
        'disk_total_human': format_filesize(mon['disk_total']),
        'disk_free_human': format_filesize(mon['disk_free']),
        'ssd_temp': mon['ssd_temp'],
        'ssd_selected_name': mon['ssd_selected_name'],
        'ssd_all': mon['ssd_all']
    }
    return jsonify(response)

# ------------------ Endpoint do edycji plików wewnątrz BASE_DIR ------------------ #
@app.route('/edit/<path:req_path>', methods=['GET', 'POST'])
@requires_auth
def edit_file(req_path):
    abs_path = safe_path(req_path)
    if not os.path.isfile(abs_path):
        flash("Wybrany element nie jest plikiem.")
        return redirect(url_for('dir_listing', req_path=posixpath.dirname(req_path)))
    if request.method == 'POST':
        new_content = request.form.get('content', '')
        try:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            flash("Plik został zaktualizowany.")
            return redirect(url_for('dir_listing', req_path=posixpath.dirname(req_path)))
        except Exception as e:
            flash(f"Błąd podczas zapisywania pliku: {e}")
    else:
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            flash(f"Błąd podczas odczytu pliku: {e}")
            return redirect(url_for('dir_listing', req_path=posixpath.dirname(req_path)))
        edit_template = """
        <!doctype html>
        <html lang="pl">
        <head>
          <meta charset="utf-8">
          <title>Edycja pliku</title>
          <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
          <div class="container py-4">
            <h1>Edycja pliku: {{ filename }}</h1>
            <form method="post">
              <div class="mb-3">
                <textarea name="content" class="form-control" rows="20">{{ content }}</textarea>
              </div>
              <button type="submit" class="btn btn-primary">Zapisz zmiany</button>
              <a href="{{ url_for('dir_listing', req_path=parent_path) }}" class="btn btn-secondary">Anuluj</a>
            </form>
          </div>
          <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/js/bootstrap.bundle.min.js"></script>
        </body>
        </html>
        """
        return render_template_string(edit_template, filename=os.path.basename(abs_path),
                                      content=content, parent_path=posixpath.dirname(req_path))

# ------------------ Endpoint do edycji pliku /boot/firmware/config.txt ------------------ #
@app.route('/edit_config', methods=['GET', 'POST'])
@requires_auth
def edit_config():
    config_path = '/boot/firmware/config.txt'
    if request.method == 'POST':
        new_content = request.form.get('content', '')
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            flash("Plik config.txt został zaktualizowany.")
            return redirect(url_for('dir_listing', req_path=''))
        except Exception as e:
            flash(f"Błąd podczas zapisywania config.txt: {e}")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        flash(f"Błąd podczas odczytu config.txt: {e}")
        return redirect(url_for('dir_listing', req_path=''))
    edit_template = """
    <!doctype html>
    <html lang="pl">
    <head>
      <meta charset="utf-8">
      <title>Edycja config.txt</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
      <div class="container py-4">
        <h1>Edycja pliku: config.txt</h1>
        <form method="post">
          <div class="mb-3">
            <textarea name="content" class="form-control" rows="20">{{ content }}</textarea>
          </div>
          <button type="submit" class="btn btn-primary">Zapisz zmiany</button>
          <a href="{{ url_for('dir_listing', req_path='') }}" class="btn btn-secondary">Anuluj</a>
        </form>
      </div>
      <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    return render_template_string(edit_template, content=content)

# ------------------ Endpoint do bulk usuwania ------------------ #
@app.route('/delete_bulk', methods=['POST'])
@requires_auth
def delete_bulk():
    selected = request.form.getlist('selected_files')
    for file_rel in selected:
        abs_path = safe_path(file_rel)
        try:
            if os.path.isdir(abs_path):
                shutil.rmtree(abs_path)
            elif os.path.isfile(abs_path):
                os.remove(abs_path)
        except Exception as e:
            flash(f"Błąd podczas usuwania {file_rel}: {e}")
    flash("Wybrane elementy zostały usunięte.")
    parent = posixpath.dirname(selected[0]) if selected else ''
    return redirect(url_for('dir_listing', req_path=parent))

# ------------------ Endpoint do przesyłania plików (manualny zapis w blokach) ------------------ #
@app.route('/upload/<path:req_path>', methods=['POST'])
@requires_auth
def upload_file(req_path):
    abs_dir = safe_path(req_path)
    if 'file' not in request.files:
        flash("Nie wybrano pliku.")
        return redirect(url_for('dir_listing', req_path=req_path))
    uploaded_files = request.files.getlist('file')
    for file in uploaded_files:
        if file.filename == '':
            flash("Jeden z przesłanych plików nie ma nazwy.")
            continue
        filename = secure_filename(file.filename)
        save_path = os.path.join(abs_dir, filename)
        try:
            with open(save_path, 'wb') as f:
                while True:
                    chunk = file.stream.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
            flash(f"Plik '{filename}' przesłany pomyślnie.")
        except Exception as e:
            flash(f"Błąd przy zapisie pliku '{filename}': {e}")
    return redirect(url_for('dir_listing', req_path=req_path))

# ------------------ Endpoint do usuwania plików ------------------ #
@app.route('/delete/<path:req_path>')
@requires_auth
def delete_file(req_path):
    abs_path = safe_path(req_path)
    if not os.path.isfile(abs_path):
        flash("Wybrany element nie jest plikiem lub nie istnieje.")
    else:
        try:
            os.remove(abs_path)
            flash("Plik został usunięty.")
        except Exception as e:
            flash(f"Błąd podczas usuwania pliku: {e}")
    parent = posixpath.dirname(req_path)
    return redirect(url_for('dir_listing', req_path=parent))

# ------------------ Endpoint do usuwania katalogów ------------------ #
@app.route('/delete_folder/<path:req_path>')
@requires_auth
def delete_folder(req_path):
    abs_path = safe_path(req_path)
    if not os.path.isdir(abs_path):
        flash("Wybrany element nie jest katalogiem lub nie istnieje.")
    else:
        try:
            shutil.rmtree(abs_path)
            flash("Katalog został usunięty.")
        except Exception as e:
            flash(f"Błąd podczas usuwania katalogu: {e}")
    parent = posixpath.dirname(req_path)
    return redirect(url_for('dir_listing', req_path=parent))

# ------------------ Endpoint do tworzenia katalogów ------------------ #
@app.route('/create_folder/<path:req_path>', methods=['POST'])
@requires_auth
def create_folder(req_path):
    abs_path = safe_path(req_path)
    folder_name = request.form.get('folder_name', '').strip()
    if folder_name == '':
        flash("Nazwa katalogu jest pusta.")
        return redirect(url_for('dir_listing', req_path=req_path))
    new_dir = os.path.join(abs_path, secure_filename(folder_name))
    try:
        os.makedirs(new_dir)
        flash("Katalog utworzony pomyślnie.")
    except Exception as e:
        flash(f"Błąd przy tworzeniu katalogu: {e}")
    return redirect(url_for('dir_listing', req_path=req_path))

# ------------------ Główna strona – lista plików, monitoring i bulk ------------------ #
@app.route('/', defaults={'req_path': ''})
@app.route('/<path:req_path>')
@requires_auth
def dir_listing(req_path):
    abs_path = safe_path(req_path)
    if not os.path.exists(abs_path):
        return f'Katalog lub plik nie istnieje: {req_path}', 404
    if os.path.isfile(abs_path):
        return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path), as_attachment=True)
    selected_sensor = request.args.get('ssd_sensor', None)
    monitoring_info = get_monitoring_data(selected_sensor)
    files = []
    try:
        for filename in os.listdir(abs_path):
            path = os.path.join(req_path, filename)
            full_path = os.path.join(abs_path, filename)
            file_info = {
                'name': filename,
                'path': path,
                'is_dir': os.path.isdir(full_path),
                'mtime': os.path.getmtime(full_path),
                'size': os.path.getsize(full_path) if os.path.isfile(full_path) else None,
                'file_type': 'folder' if os.path.isdir(full_path) else os.path.splitext(filename)[1].lower()
            }
            files.append(file_info)
    except PermissionError:
        flash("Brak uprawnień do odczytu zawartości katalogu.")
        files = []
    sort_by = request.args.get('sort', 'name')
    order = request.args.get('order', 'asc')
    reverse_order = (order == 'desc')
    if sort_by == 'date':
        files.sort(key=lambda x: x['mtime'], reverse=reverse_order)
    elif sort_by == 'type':
        files.sort(key=lambda x: (x['file_type'], x['name'].lower()), reverse=reverse_order)
    elif sort_by == 'size':
        files.sort(key=lambda x: x['size'] if x['size'] is not None else 0, reverse=reverse_order)
    else:
        files.sort(key=lambda x: x['name'].lower(), reverse=reverse_order)
    parent_path = posixpath.dirname(req_path)
    # Szablon HTML – Monitoring z paskami postępu, formularz uploadu+utwórz katalog nad listą, bulk selection.
    html_template = """
    <!doctype html>
    <html lang="pl">
    <head>
      <meta charset="utf-8">
      <title>Lekki Panel Zarządzania Grami</title>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet">
      <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
      <style>
         /* Opcjonalnie ogranicz rozmiar elementów, jeżeli potrzeba */
         .progress { height: 25px; }
      </style>
    </head>
    <body>
      <div class="container py-4">
        <h1 class="mb-4">Panel Zarządzania Plikami</h1>
        <div class="text-end mb-3">
          <a href="{{ url_for('edit_config') }}" class="btn btn-outline-warning">
            <i class="fas fa-edit"></i> Edytuj config.txt
          </a>
        </div>
        {% with messages = get_flashed_messages() %}
          {% if messages %}
            {% for message in messages %}
              <div class="alert alert-warning" role="alert">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}
        
        <!-- Sekcja Monitoring z paskami postępu -->
        <div class="card mb-4">
          <div class="card-header">
            <h3>Monitoring</h3>
          </div>
          <div class="card-body">
            <div class="row mb-3">
              <div class="col-md-3">
                <strong>Temperatura CPU:</strong>
                <span id="cpu-temp">{{ monitoring_info.cpu_temp }}</span>
              </div>
              <div class="col-md-3">
                <strong>Temperatura SSD:</strong>
                <span id="ssd-temp">{{ monitoring_info.ssd_temp }}</span>
                {% if monitoring_info.ssd_selected_name %}
                  <br><small>{{ monitoring_info.ssd_selected_name }}</small>
                {% endif %}
              </div>
              <div class="col-md-6">
                {% if monitoring_info.ssd_all %}
                  <form method="get" class="d-flex align-items-center">
                    <label for="ssd_sensor_select" class="me-2"><small>Wybierz czujnik SSD:</small></label>
                    <input type="hidden" name="req_path" value="{{ req_path }}">
                    <select name="ssd_sensor" id="ssd_sensor_select" class="form-select" style="width:auto;" onchange="this.form.submit()">
                      {% for sensor, temp in monitoring_info.ssd_all.items() %}
                        <option value="{{ sensor }}" {% if sensor == monitoring_info.ssd_selected_name %}selected{% endif %}>
                          {{ sensor }}: {{ temp }}
                        </option>
                      {% endfor %}
                    </select>
                  </form>
                {% endif %}
              </div>
            </div>
            <div class="row mb-3">
              <div class="col-md-4">
                <div class="mb-1"><strong>CPU:</strong></div>
                <div class="progress">
                  <div id="cpuBar" class="progress-bar" role="progressbar" style="width: {{ monitoring_info.cpu_usage }}%;" aria-valuenow="{{ monitoring_info.cpu_usage }}" aria-valuemin="0" aria-valuemax="100">{{ monitoring_info.cpu_usage }}%</div>
                </div>
              </div>
              <div class="col-md-4">
                <div class="mb-1"><strong>Pamięć:</strong></div>
                <div class="progress">
                  <div id="memBar" class="progress-bar bg-success" role="progressbar" style="width: {{ monitoring_info.mem_percent }}%;" aria-valuenow="{{ monitoring_info.mem_percent }}" aria-valuemin="0" aria-valuemax="100">{{ monitoring_info.mem_percent }}%</div>
                </div>
              </div>
              <div class="col-md-4">
                <div class="mb-1"><strong>Dysk:</strong> ({{ monitoring_info.disk_used | filesizeformat }} / {{ monitoring_info.disk_total | filesizeformat }})</div>
                <div class="progress">
                  <div id="diskBar" class="progress-bar bg-info" role="progressbar" style="width: {{ monitoring_info.disk_percent }}%;" aria-valuenow="{{ monitoring_info.disk_percent }}" aria-valuemin="0" aria-valuemax="100">{{ monitoring_info.disk_percent }}%</div>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- Formularz uploadu plików oraz utwórz katalog -->
        <div class="card mb-4">
          <div class="card-header">
            <h3>Prześlij plik(e) / Utwórz katalog</h3>
          </div>
          <div class="card-body">
            <div class="row">
              <div class="col-md-6">
                <form id="uploadForm" action="{{ url_for('upload_file', req_path=req_path) }}" method="post" enctype="multipart/form-data">
                  <div class="mb-3">
                    <input type="file" name="file" class="form-control" multiple>
                  </div>
                  <button type="submit" class="btn btn-primary"><i class="fas fa-upload"></i> Prześlij</button>
                </form>
                <div id="uploadProgress" class="progress mt-2" style="display:none;">
                  <div id="uploadProgressBar" class="progress-bar" role="progressbar" style="width: 0%;">0%</div>
                </div>
              </div>
              <div class="col-md-6">
                <form action="{{ url_for('create_folder', req_path=req_path) }}" method="post">
                  <div class="mb-3">
                    <input type="text" name="folder_name" placeholder="Nazwa katalogu" class="form-control">
                  </div>
                  <button type="submit" class="btn btn-secondary"><i class="fas fa-folder-plus"></i> Utwórz katalog</button>
                </form>
              </div>
            </div>
          </div>
        </div>
        
        <!-- Bulk selection i lista plików/katalogów -->
        <form method="post" action="{{ url_for('delete_bulk') }}">
          <div class="card">
            <div class="card-header">
              <h3>Lista plików i folderów</h3>
              <div class="mt-2">
                <span>Sortuj wg: </span>
                <a href="{{ url_for('dir_listing', req_path=req_path, sort='name', order='asc') }}" class="btn btn-sm btn-outline-primary">Nazwa ↑</a>
                <a href="{{ url_for('dir_listing', req_path=req_path, sort='name', order='desc') }}" class="btn btn-sm btn-outline-primary">Nazwa ↓</a>
                <a href="{{ url_for('dir_listing', req_path=req_path, sort='date', order='asc') }}" class="btn btn-sm btn-outline-secondary">Data ↑</a>
                <a href="{{ url_for('dir_listing', req_path=req_path, sort='date', order='desc') }}" class="btn btn-sm btn-outline-secondary">Data ↓</a>
                <a href="{{ url_for('dir_listing', req_path=req_path, sort='type', order='asc') }}" class="btn btn-sm btn-outline-info">Typ ↑</a>
                <a href="{{ url_for('dir_listing', req_path=req_path, sort='type', order='desc') }}" class="btn btn-sm btn-outline-info">Typ ↓</a>
                <a href="{{ url_for('dir_listing', req_path=req_path, sort='size', order='asc') }}" class="btn btn-sm btn-outline-dark">Rozmiar ↑</a>
                <a href="{{ url_for('dir_listing', req_path=req_path, sort='size', order='desc') }}" class="btn btn-sm btn-outline-dark">Rozmiar ↓</a>
              </div>
            </div>
            <div class="card-body">
              <nav aria-label="breadcrumb">
                <ol class="breadcrumb">
                  <li class="breadcrumb-item">
                    <a href="{{ url_for('dir_listing', req_path='') }}"><i class="fas fa-home"></i> Home</a>
                  </li>
                  {% if req_path %}
                    {% set parts = req_path.split('/') %}
                    {% set path_acc = "" %}
                    {% for part in parts %}
                      {% set path_acc = path_acc + part %}
                      <li class="breadcrumb-item">
                        <a href="{{ url_for('dir_listing', req_path=path_acc) }}">{{ part }}</a>
                      </li>
                      {% set path_acc = path_acc + "/" %}
                    {% endfor %}
                  {% endif %}
                </ol>
              </nav>
              <table class="table table-striped table-hover">
                <thead>
                  <tr>
                    <th>Zaznacz</th>
                    <th>Ikona</th>
                    <th>Nazwa</th>
                    <th>Typ</th>
                    <th>Data modyfikacji</th>
                    <th>Rozmiar</th>
                    <th>Akcje</th>
                  </tr>
                </thead>
                <tbody>
                  {% if req_path %}
                  <tr>
                    <td colspan="7">
                      <a href="{{ url_for('dir_listing', req_path=parent_path) }}" class="btn btn-sm btn-outline-dark">
                        <i class="fas fa-level-up-alt"></i> [..]
                      </a>
                    </td>
                  </tr>
                  {% endif %}
                  {% for file in files %}
                  <tr>
                    <td class="align-middle">
                      <input type="checkbox" name="selected_files" value="{{ file.path }}">
                    </td>
                    <td class="align-middle">
                      {% if file.is_dir %}
                        <i class="fas fa-folder fa-lg text-warning"></i>
                      {% else %}
                        <i class="fas fa-file fa-lg text-secondary"></i>
                      {% endif %}
                    </td>
                    <td class="align-middle">
                      {% if file.is_dir %}
                        <a href="{{ url_for('dir_listing', req_path=file.path) }}">{{ file.name }}/</a>
                      {% else %}
                        {{ file.name }}
                      {% endif %}
                    </td>
                    <td class="align-middle">{{ file.file_type }}</td>
                    <td class="align-middle">{{ file.mtime | datetimeformat }}</td>
                    <td class="align-middle">{{ file.size | filesizeformat }}</td>
                    <td class="align-middle">
                      {% if file.is_dir %}
                        <a href="{{ url_for('dir_listing', req_path=file.path) }}" class="btn btn-sm btn-primary" title="Otwórz katalog"><i class="fas fa-folder-open"></i></a>
                        <a href="{{ url_for('delete_folder', req_path=file.path) }}" class="btn btn-sm btn-danger" title="Usuń katalog" onclick="return confirm('Czy na pewno usunąć ten katalog (rekurencyjnie)?');"><i class="fas fa-trash-alt"></i></a>
                      {% else %}
                        <a href="{{ url_for('dir_listing', req_path=file.path) }}" class="btn btn-sm btn-success" title="Pobierz plik"><i class="fas fa-download"></i></a>
                        <a href="{{ url_for('edit_file', req_path=file.path) }}" class="btn btn-sm btn-warning" title="Edytuj plik"><i class="fas fa-edit"></i></a>
                        <a href="{{ url_for('delete_file', req_path=file.path) }}" class="btn btn-sm btn-danger" title="Usuń plik" onclick="return confirm('Czy na pewno usunąć ten plik?');"><i class="fas fa-trash-alt"></i></a>
                      {% endif %}
                    </td>
                  </tr>
                  {% endfor %}
                </tbody>
              </table>
              <button type="submit" class="btn btn-danger" onclick="return confirm('Czy na pewno usunąć wybrane elementy?');">Usuń zaznaczone</button>
            </div>
          </div>
        </form>
      </div>

      <script>
        // Funkcja aktualizująca paski postępu w sekcji monitoringu
        function updateMonitoring() {
          let sensorSelect = document.getElementById("ssd_sensor_select");
          let sensorParam = "";
          if(sensorSelect) { sensorParam = "&ssd_sensor=" + sensorSelect.value; }
          fetch("/api/monitoring?" + sensorParam)
            .then(response => response.json())
            .then(data => {
              document.getElementById("cpu-temp").textContent = data.cpu_temp;
              document.getElementById("ssd-temp").textContent = data.ssd_temp;
              // Aktualizacja paska CPU
              let cpuBar = document.getElementById("cpuBar");
              cpuBar.style.width = data.cpu_usage + "%";
              cpuBar.textContent = data.cpu_usage + "%";
              // Aktualizacja paska pamięci
              let memBar = document.getElementById("memBar");
              memBar.style.width = data.mem_percent + "%";
              memBar.textContent = data.mem_percent + "%";
              // Aktualizacja paska dysku
              let diskBar = document.getElementById("diskBar");
              diskBar.style.width = data.disk_percent + "%";
              diskBar.textContent = data.disk_percent + "%";
              // Aktualizacja tekstowych elementów, jeżeli potrzeba
              document.getElementById("cpu-usage").textContent = data.cpu_usage;
              document.getElementById("disk-percent").textContent = data.disk_percent;
              document.getElementById("mem-text").innerHTML = data.mem_percent + "% użycia (" + data.mem_used_human + " / " + data.mem_total_human + ")";
            })
            .catch(err => console.error("Błąd pobierania /api/monitoring:", err));
        }
        document.addEventListener("DOMContentLoaded", function() {
          // Inicjalizacja pasków – zastąpienie wykresów
          // Dynamically utwórz paski, jeżeli nie istnieją:
          if(!document.getElementById("cpuBar")){
            var cpuBar = document.createElement("div");
            cpuBar.id = "cpuBar";
            cpuBar.className = "progress-bar";
            cpuBar.setAttribute("role", "progressbar");
            cpuBar.style.width = "{{ monitoring_info.cpu_usage }}%";
            cpuBar.textContent = "{{ monitoring_info.cpu_usage }}%";
            var cpuProgress = document.createElement("div");
            cpuProgress.className = "progress mb-3";
            cpuProgress.appendChild(cpuBar);
            // Dodaj CPU progress bar do kontenera monitoring (przed pozostalymi elementami)
            var monitoringCard = document.querySelector(".card.mb-4 .card-body");
            monitoringCard.insertBefore(cpuProgress, monitoringCard.firstChild);
          }
          if(!document.getElementById("memBar")){
            var memBar = document.createElement("div");
            memBar.id = "memBar";
            memBar.className = "progress-bar bg-success";
            memBar.setAttribute("role", "progressbar");
            memBar.style.width = "{{ monitoring_info.mem_percent }}%";
            memBar.textContent = "{{ monitoring_info.mem_percent }}%";
            var memProgress = document.createElement("div");
            memProgress.className = "progress mb-3";
            memProgress.appendChild(memBar);
            var monitoringCard = document.querySelector(".card.mb-4 .card-body");
            monitoringCard.insertBefore(memProgress, monitoringCard.children[1]);
          }
          if(!document.getElementById("diskBar")){
            var diskBar = document.createElement("div");
            diskBar.id = "diskBar";
            diskBar.className = "progress-bar bg-info";
            diskBar.setAttribute("role", "progressbar");
            diskBar.style.width = "{{ monitoring_info.disk_percent }}%";
            diskBar.textContent = "{{ monitoring_info.disk_percent }}%";
            var diskProgress = document.createElement("div");
            diskProgress.className = "progress mb-3";
            diskProgress.appendChild(diskBar);
            var monitoringCard = document.querySelector(".card.mb-4 .card-body");
            monitoringCard.insertBefore(diskProgress, monitoringCard.children[2]);
          }
          setInterval(updateMonitoring, 1000);
        });
        // Obsługa uploadu z paskiem postępu
        document.getElementById("uploadForm").addEventListener("submit", function(e) {
          e.preventDefault();
          var form = this;
          var formData = new FormData(form);
          var xhr = new XMLHttpRequest();
          xhr.open("POST", form.action, true);
          document.getElementById("uploadProgress").style.display = "block";
          xhr.upload.addEventListener("progress", function(e) {
            if (e.lengthComputable) {
              var percentComplete = Math.round((e.loaded / e.total) * 100);
              document.getElementById("uploadProgressBar").style.width = percentComplete + "%";
              document.getElementById("uploadProgressBar").textContent = percentComplete + "%";
            }
          });
          xhr.onload = function() {
            if (xhr.status === 200) {
              window.location.reload();
            } else {
              alert("Błąd przy przesyłaniu pliku");
            }
          };
          xhr.send(formData);
        });
      </script>
      <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/js/bootstrap.bundle.min.js"></script>
    </body>
    </html>
    """
    return render_template_string(html_template, files=files, req_path=req_path,
                                  parent_path=parent_path, monitoring_info=monitoring_info)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
