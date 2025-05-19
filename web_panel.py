#!/usr/bin/env python3
import os
import posixpath
import shutil
import psutil
import subprocess
import tempfile
from datetime import datetime
from flask import (
    Flask, request, render_template_string, redirect, url_for,
    send_from_directory, flash, abort, Response, jsonify
)
from functools import wraps
from werkzeug.utils import secure_filename

# --- Configuration file handling ---
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.cfg")

def load_config():
    config = {
        "login": "admin",
        "password": "admin",
        "secret_key": "your_secret_key",
        "port": 5000,
        "monitor_refresh": 0.5,
        "ssd_sensor": "",
        "show_nvme": False,
        "config_location": "64"
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key, val = key.strip(), val.strip()
                    if key == "port":
                        try: config[key] = int(val)
                        except: pass
                    elif key == "monitor_refresh":
                        try: config[key] = float(val)
                        except: pass
                    elif key == "show_nvme":
                        config[key] = (val.lower() == "true")
                    else:
                        config[key] = val
    else:
        save_config(config)
    return config

def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            for k, v in config.items():
                if isinstance(v, bool):
                    f.write(f"{k}={'True' if v else 'False'}\n")
                else:
                    f.write(f"{k}={v}\n")
    except PermissionError:
        os.chmod(CONFIG_FILE, 0o666)
        with open(CONFIG_FILE, "w") as f:
            for k, v in config.items():
                if isinstance(v, bool):
                    f.write(f"{k}={'True' if v else 'False'}\n")
                else:
                    f.write(f"{k}={v}\n")

CONFIG = load_config()

# --- Temporary directory setup ---
TEMP_DIR = '/home/pi/tmp'
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR, mode=0o1777)
os.environ['TMPDIR'] = TEMP_DIR
tempfile.tempdir = TEMP_DIR

# --- Flask application ---
app = Flask(__name__)
app.secret_key = CONFIG["secret_key"]
BASE_DIR = os.path.abspath("/home/pi/RetroPie")

# --- Jinja2 filters ---
def format_datetime(ts):
    return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

def format_filesize(b):
    if b is None:
        return ''
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b < 1024:
            return f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} PB"

app.jinja_env.filters['datetimeformat'] = format_datetime
app.jinja_env.filters['filesizeformat'] = format_filesize

# --- Authentication helpers ---
def check_auth(u, p):
    return u == CONFIG["login"] and p == CONFIG["password"]

def authenticate():
    return Response('Access denied.\n', 401,
                    {'WWW-Authenticate': 'Basic realm="Login Required"'})

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

# --- Monitoring helpers ---
def round1(x): return round(x, 1)

def get_cpu_temp():
    try:
        out = subprocess.check_output(['vcgencmd', 'measure_temp']).decode().strip()
        return out.split('=')[1].split("'")[0] + "°C"
    except:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                v = float(f.read().strip()) / 1000
                return f"{round(v,1)}°C"
        except:
            return "N/A"

def get_ssd_temperatures():
    if not CONFIG.get("show_nvme"):
        return {}
    sensors = {}
    try:
        out = subprocess.check_output(
            ["sudo", "nvme", "smart-log", "/dev/nvme0"],
            stderr=subprocess.STDOUT, universal_newlines=True
        )
        for line in out.splitlines():
            if "temperature" in line.lower():
                k, v = line.split(":", 1)
                sensors[k.strip()] = v.strip().split()[0] + "°C"
    except:
        pass
    return sensors

def get_monitoring_data(sensor=None):
    if sensor is None:
        sensor = CONFIG.get("ssd_sensor")
    cpu_usage = round1(psutil.cpu_percent(interval=0.0))
    mem = psutil.virtual_memory()
    mem_p = round1(mem.percent)
    disk = psutil.disk_usage(BASE_DIR)
    disk_p = round1((disk.used/disk.total)*100) if disk.total > 0 else 0
    cpu_t = get_cpu_temp()
    ssd = get_ssd_temperatures()
    if ssd:
        if sensor in ssd:
            ssd_name, ssd_temp = sensor, ssd[sensor]
        else:
            ssd_name, ssd_temp = next(iter(ssd.items()))
    else:
        ssd_name, ssd_temp = None, "N/A"
    try:
        f = psutil.cpu_freq()
        curr = round1(f.current) if f else 0
        mx   = round1(f.max)     if f else 0
    except:
        curr, mx = "N/A", "N/A"
    bt = psutil.boot_time()
    delta = datetime.now() - datetime.fromtimestamp(bt)
    d = delta.days
    h, rem = divmod(delta.seconds, 3600)
    m, s = divmod(rem, 60)
    up = f"{d}d {h}h {m}m {s}s" if d > 0 else f"{h}h {m}m {s}s"
    return {
        'cpu_usage': cpu_usage,
        'cpu_temp': cpu_t,
        'cpu_freq_current': curr,
        'cpu_freq_max': mx,
        'mem_total': mem.total,
        'mem_used': mem.used,
        'mem_percent': mem_p,
        'disk_total': disk.total,
        'disk_used': disk.used,
        'disk_free': disk.total - disk.used,
        'disk_percent': disk_p,
        'ssd_all': ssd,
        'ssd_selected_name': ssd_name,
        'ssd_temp': ssd_temp,
        'uptime': up
    }

# --- API endpoint for monitoring data ---
@app.route('/api/monitoring')
@requires_auth
def api_monitoring():
    s = request.args.get('ssd_sensor') or CONFIG.get("ssd_sensor")
    m = get_monitoring_data(s)
    return jsonify({
        'cpu_usage': m['cpu_usage'],
        'cpu_temp': m['cpu_temp'],
        'cpu_freq_current': m['cpu_freq_current'],
        'cpu_freq_max': m['cpu_freq_max'],
        'mem_percent': m['mem_percent'],
        'mem_used_human': format_filesize(m['mem_used']),
        'mem_total_human': format_filesize(m['mem_total']),
        'disk_percent': m['disk_percent'],
        'disk_used_human': format_filesize(m['disk_used']),
        'disk_total_human': format_filesize(m['disk_total']),
        'disk_free_human': format_filesize(m['disk_free']),
        'ssd_temp': m['ssd_temp'],
        'ssd_selected_name': m['ssd_selected_name'],
        'ssd_all': m['ssd_all'],
        'uptime': m['uptime']
    })

# --- Control endpoint (reboot/shutdown) ---
@app.route('/control', methods=['POST'])
@requires_auth
def control():
    act = request.form.get('action')
    if act == 'reboot':
        flash("Rebooting Raspberry Pi...")
        subprocess.Popen(["reboot"])
    elif act == 'shutdown':
        flash("Shutting down Raspberry Pi...")
        subprocess.Popen(["shutdown", "now"])
    else:
        flash("Invalid action.")
    return redirect(url_for('dir_listing', req_path=""))

# --- Settings page ---
@app.route('/settings', methods=['GET', 'POST'])
@requires_auth
def settings():
    global CONFIG, app
    msg = ""
    if request.method == 'POST':
        if 'save_credentials' in request.form:
            nl = request.form.get('login','').strip()
            npw = request.form.get('password','').strip()
            if nl: CONFIG['login'] = nl
            if npw: CONFIG['password'] = npw
            msg += "Credentials updated. "
        elif 'save_app_settings' in request.form:
            sk = request.form.get('secret_key','').strip()
            p  = request.form.get('port','').strip()
            mr = request.form.get('monitor_refresh','').strip()
            nv = request.form.get('show_nvme') == 'on'
            cl = request.form.get('config_location','64').strip()
            CONFIG['show_nvme'] = nv
            CONFIG['config_location'] = cl
            if sk: CONFIG['secret_key'] = sk; app.secret_key = sk
            if p.isdigit(): CONFIG['port'] = int(p)
            try:
                fr = float(mr)
                if fr >= 0.5: CONFIG['monitor_refresh'] = fr
            except:
                pass
            msg += "App settings updated. "
        elif 'restart_service' in request.form:
            subprocess.call(["systemctl", "restart", "web_panel.service"]); msg += "Service restarted. "
        elif 'enable_service' in request.form:
            subprocess.call(["systemctl", "enable", "web_panel.service"]); msg += "Service enabled. "
        elif 'disable_service' in request.form:
            subprocess.call(["systemctl", "disable", "web_panel.service"]); msg += "Service disabled. "
        elif 'stop_service' in request.form:
            subprocess.call(["systemctl", "stop", "web_panel.service"]); msg += "Service stopped. "
        save_config(CONFIG)
        flash(msg)
        return redirect(url_for('settings'))

    settings_html = """
    <!doctype html>
    <html lang="en"><head><meta charset="utf-8"><title>Settings</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>.nav-tabs .nav-link{cursor:pointer;}</style></head><body>
    <div class="container py-4">
      <h1>Settings</h1>
      {% with msgs = get_flashed_messages() %}
        {% if msgs %}
          {% for m in msgs %}<div class="alert alert-info">{{ m }}</div>{% endfor %}
        {% endif %}
      {% endwith %}
      <ul class="nav nav-tabs">
        <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#cred">Credentials</button></li>
        <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#app">App Settings</button></li>
        <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#svc">Service Management</button></li>
      </ul>
      <div class="tab-content pt-3">
        <div id="cred" class="tab-pane fade show active">
          <form method="post">
            <div class="mb-3"><label class="form-label">Login</label><input class="form-control" name="login" value="{{ config['login'] }}"></div>
            <div class="mb-3"><label class="form-label">Password</label><input class="form-control" name="password" value="{{ config['password'] }}"></div>
            <button name="save_credentials" class="btn btn-primary">Save Credentials</button>
          </form>
        </div>
        <div id="app" class="tab-pane fade">
          <form method="post">
            <div class="mb-3"><label class="form-label">Secret Key</label><input class="form-control" name="secret_key" value="{{ config['secret_key'] }}"></div>
            <div class="mb-3"><label class="form-label">Port</label><input type="number" class="form-control" name="port" value="{{ config['port'] }}"></div>
            <div class="mb-3"><label class="form-label">Monitoring Refresh Interval (s, min 0.5)</label><input step="0.1" type="number" class="form-control" name="monitor_refresh" value="{{ config['monitor_refresh'] }}"></div>
            <div class="form-check mb-3">
              <input class="form-check-input" type="checkbox" id="nvme" name="show_nvme" {% if config['show_nvme'] %}checked{% endif %}>
              <label class="form-check-label" for="nvme">Display NVMe Temperature</label>
            </div>
            <div class="mb-3"><label class="form-label">RPI Config File Location</label>
              <select class="form-select" name="config_location">
                <option value="64" {% if config['config_location']=='64' %}selected{% endif %}>64-bit: /boot/firmware/config.txt</option>
                <option value="32" {% if config['config_location']=='32' %}selected{% endif %}>32-bit: /boot/config.txt</option>
              </select>
            </div>
            <button name="save_app_settings" class="btn btn-primary">Save App Settings</button>
          </form>
        </div>
        <div id="svc" class="tab-pane fade">
          <form method="post">
            <button name="restart_service" class="btn btn-warning mb-2">Restart Service</button><br>
            <button name="stop_service" class="btn btn-danger mb-2">Stop Service</button><br>
            <button name="enable_service" class="btn btn-success mb-2">Enable Service</button><br>
            <button name="disable_service" class="btn btn-danger mb-2">Disable Service</button>
          </form>
        </div>
      </div>
      <br><a href="{{ url_for('dir_listing', req_path='') }}" class="btn btn-secondary">Back to File Manager</a>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/js/bootstrap.bundle.min.js"></script>
    </body></html>
    """
    return render_template_string(settings_html, config=CONFIG)

# --- Edit RPI config.txt endpoint ---
@app.route('/edit_config', methods=['GET', 'POST'])
@requires_auth
def edit_config():
    cfg_path = '/boot/config.txt' if CONFIG.get("config_location") == "32" else '/boot/firmware/config.txt'
    if request.method == 'POST':
        new = request.form.get('content', '')
        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                f.write(new)
            flash(f"Updated {cfg_path}")
            return redirect(url_for('dir_listing', req_path=''))
        except Exception as e:
            flash(f"Error saving config.txt: {e}")
    try:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        flash(f"Error reading config.txt: {e}")
        return redirect(url_for('dir_listing', req_path=''))
    tmpl = """
    <!doctype html><html lang="en"><head><meta charset="utf-8"><title>Edit RPI config.txt</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet"></head>
    <body><div class="container py-4">
      <h1>Edit RPI config.txt at {{ path }}</h1>
      <form method="post">
        <textarea name="content" class="form-control" rows="20">{{ content }}</textarea><br>
        <button class="btn btn-primary">Save Changes</button>
        <a class="btn btn-secondary" href="{{ url_for('dir_listing', req_path='') }}">Cancel</a>
      </form>
    </div></body></html>
    """
    return render_template_string(tmpl, path=cfg_path, content=content)

# --- File editing endpoint ---
@app.route('/edit/<path:req_path>', methods=['GET', 'POST'])
@requires_auth
def edit_file(req_path):
    abs_path = safe_path(req_path)
    if not os.path.isfile(abs_path):
        flash("The selected item is not a file.")
        return redirect(url_for('dir_listing', req_path=posixpath.dirname(req_path)))
    if request.method == 'POST':
        new_content = request.form.get('content', '')
        try:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            flash("File has been updated.")
            return redirect(url_for('dir_listing', req_path=posixpath.dirname(req_path)))
        except Exception as e:
            flash(f"Error saving the file: {e}")
    try:
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        flash(f"Error reading the file: {e}")
        return redirect(url_for('dir_listing', req_path=posixpath.dirname(req_path)))
    edit_template = """
    <!doctype html><html lang="en"><head><meta charset="utf-8"><title>Edit File</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet"></head>
    <body><div class="container py-4">
      <h1>Edit file: {{ filename }}</h1>
      <form method="post">
        <textarea name="content" class="form-control" rows="20">{{ content }}</textarea><br>
        <button class="btn btn-primary">Save Changes</button>
        <a class="btn btn-secondary" href="{{ url_for('dir_listing', req_path=parent_path) }}">Cancel</a>
      </form>
    </div></body></html>
    """
    return render_template_string(
        edit_template,
        filename=os.path.basename(abs_path),
        content=content,
        parent_path=posixpath.dirname(req_path)
    )

# --- Bulk delete endpoint ---
@app.route('/delete_bulk', methods=['POST'])
@requires_auth
def delete_bulk():
    selected = request.form.getlist('selected_files')
    for file_rel in selected:
        abs_p = safe_path(file_rel)
        try:
            if os.path.isdir(abs_p):
                shutil.rmtree(abs_p)
            elif os.path.isfile(abs_p):
                os.remove(abs_p)
        except Exception as e:
            flash(f"Error deleting {file_rel}: {e}")
    flash("Selected items have been deleted.")
    parent = posixpath.dirname(selected[0]) if selected else ''
    return redirect(url_for('dir_listing', req_path=parent))

# --- Create folder endpoint ---
@app.route('/create_folder/<path:req_path>', methods=['POST'])
@requires_auth
def create_folder(req_path):
    abs_p = safe_path(req_path)
    folder_name = request.form.get('folder_name', '').strip()
    if folder_name == '':
        flash("Folder name is empty.")
        return redirect(url_for('dir_listing', req_path=req_path))
    new_dir = os.path.join(abs_p, secure_filename(folder_name))
    try:
        os.makedirs(new_dir)
        flash("Folder created successfully.")
    except Exception as e:
        flash(f"Error creating folder: {e}")
    return redirect(url_for('dir_listing', req_path=req_path))

# --- File upload endpoint ---
@app.route('/upload/<path:req_path>', methods=['POST'])
@requires_auth
def upload_file(req_path):
    abs_dir = safe_path(req_path)
    if 'file' not in request.files:
        flash("No file selected.")
        return redirect(url_for('dir_listing', req_path=req_path))
    for file in request.files.getlist('file'):
        if file.filename == '':
            flash("One of the uploaded files has no name.")
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
            flash(f"File '{filename}' uploaded successfully.")
        except Exception as e:
            flash(f"Error saving file '{filename}': {e}")
    return redirect(url_for('dir_listing', req_path=req_path))

# --- Single file delete endpoint ---
@app.route('/delete/<path:req_path>')
@requires_auth
def delete_file(req_path):
    abs_p = safe_path(req_path)
    if not os.path.isfile(abs_p):
        flash("The selected item is not a file or does not exist.")
    else:
        try:
            os.remove(abs_p)
            flash("File has been deleted.")
        except Exception as e:
            flash(f"Error deleting file: {e}")
    parent = posixpath.dirname(req_path)
    return redirect(url_for('dir_listing', req_path=parent))

# --- Single folder delete endpoint ---
@app.route('/delete_folder/<path:req_path>')
@requires_auth
def delete_folder(req_path):
    abs_p = safe_path(req_path)
    if not os.path.isdir(abs_p):
        flash("The selected item is not a folder or does not exist.")
    else:
        try:
            shutil.rmtree(abs_p)
            flash("Folder has been deleted.")
        except Exception as e:
            flash(f"Error deleting folder: {e}")
    parent = posixpath.dirname(req_path)
    return redirect(url_for('dir_listing', req_path=parent))

# --- Main directory listing endpoint ---
@app.route('/', defaults={'req_path': ''})
@app.route('/<path:req_path>')
@requires_auth
def dir_listing(req_path):
    selected_sensor_param = request.args.get('ssd_sensor')
    if selected_sensor_param:
        CONFIG['ssd_sensor'] = selected_sensor_param
        save_config(CONFIG)
    abs_path = safe_path(req_path)
    if os.path.isfile(abs_path):
        return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path), as_attachment=True)
    mon = get_monitoring_data(CONFIG.get("ssd_sensor"))
    files = []
    try:
        for filename in os.listdir(abs_path):
            full_path = os.path.join(abs_path, filename)
            files.append({
                'name': filename,
                'path': os.path.join(req_path, filename),
                'is_dir': os.path.isdir(full_path),
                'mtime': os.path.getmtime(full_path),
                'size': os.path.getsize(full_path) if os.path.isfile(full_path) else None,
                'file_type': 'folder' if os.path.isdir(full_path) else os.path.splitext(filename)[1].lower()
            })
    except PermissionError:
        flash("Insufficient permissions to read directory contents.")
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

    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>RetroPie Light Web Game Manager</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <style>
    canvas { max-width: 300px; max-height: 300px; }
    .progress { height: 40px; }
    .progress-bar { color: black; font-size: 1.2em; font-weight: bold; }
  </style>
</head>
<body>
<div class="container py-4">
  <h1 class="mb-4">RetroPie Light Web Game Manager</h1>
  <div class="text-end mb-3">
    <a href="{{ url_for('edit_config') }}" class="btn btn-outline-warning">
      <i class="fas fa-edit"></i> Edit RPI config.txt
    </a>
    <a href="{{ url_for('settings') }}" class="btn btn-outline-secondary">
      <i class="fas fa-cog"></i> Settings
    </a>
  </div>
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      {% for message in messages %}
        <div class="alert alert-warning">{{ message }}</div>
      {% endfor %}
    {% endif %}
  {% endwith %}

  <!-- Monitoring Section -->
  <div class="card mb-4">
    <div class="card-header"><h3>Monitoring</h3></div>
    <div class="card-body">
      <div class="row mb-3">
        <div class="col-md-3"><strong>CPU Temp:</strong> <span id="cpu-temp">{{ mon['cpu_temp'] }}</span></div>
        <div class="col-md-3">
          <strong>SSD Temp:</strong> <span id="ssd-temp">{{ mon['ssd_temp'] }}</span>
          {% if mon['ssd_selected_name'] %}<br><small>{{ mon['ssd_selected_name'] }}</small>{% endif %}
        </div>
        <div class="col-md-3"><strong>Uptime:</strong> <span id="uptime">{{ mon['uptime'] }}</span></div>
        <div class="col-md-3">
          {% if config['show_nvme'] and mon['ssd_all'] %}
            <form method="get" class="d-flex align-items-center flex-wrap">
              <label for="ssd_sensor" class="me-2 mb-1"><small>Select SSD Sensor:</small></label>
              <input type="hidden" name="req_path" value="{{ req_path }}">
              <select id="ssd_sensor" name="ssd_sensor" class="form-select" style="max-width: 200px;" onchange="this.form.submit()">
                {% for sensor, temp in mon['ssd_all'].items() %}
                  <option value="{{ sensor }}" {% if sensor == mon['ssd_selected_name'] %}selected{% endif %}>{{ sensor }}: {{ temp }}</option>
                {% endfor %}
              </select>
            </form>
          {% endif %}
        </div>
      </div>
      <div class="row mb-3">
        <div class="col-md-4"><strong>CPU Frequency:</strong> <span id="cpu-usage-text">{{ mon['cpu_freq_current'] }} MHz / {{ mon['cpu_freq_max'] }} MHz</span></div>
        <div class="col-md-4"><strong>Memory Usage:</strong> <span id="memory-usage-text">{{ mon['mem_used_human'] }} / {{ mon['mem_total_human'] }}</span></div>
        <div class="col-md-4"><strong>Disk Usage:</strong> <span id="disk-usage-text">{{ mon['disk_used_human'] }} / {{ mon['disk_total_human'] }}</span></div>
      </div>
      <div class="row mb-3">
        <div class="col-md-4">
          <div class="mb-1"><strong>CPU Usage:</strong></div>
          <div class="progress">
            <div id="cpuBar" class="progress-bar" role="progressbar" style="width: {{ mon['cpu_usage'] }}%;" aria-valuenow="{{ mon['cpu_usage'] }}" aria-valuemin="0" aria-valuemax="100">{{ mon['cpu_usage'] }}%</div>
          </div>
        </div>
        <div class="col-md-4">
          <div class="mb-1"><strong>Memory Usage:</strong></div>
          <div class="progress">
            <div id="memBar" class="progress-bar bg-success" role="progressbar" style="width: {{ mon['mem_percent'] }}%;" aria-valuenow="{{ mon['mem_percent'] }}" aria-valuemin="0" aria-valuemax="100">{{ mon['mem_percent'] }}%</div>
          </div>
        </div>
        <div class="col-md-4">
          <div class="mb-1"><strong>Disk Usage:</strong></div>
          <div class="progress">
            <div id="diskBar" class="progress-bar bg-info" role="progressbar" style="width: {{ mon['disk_percent'] }}%;" aria-valuenow="{{ mon['disk_percent'] }}" aria-valuemin="0" aria-valuemax="100">{{ mon['disk_percent'] }}%</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Control Section -->
  <div class="card mb-4">
    <div class="card-header"><h3>Control</h3></div>
    <div class="card-body">
      <form method="post" action="{{ url_for('control') }}">
        <button type="submit" name="action" value="reboot" class="btn btn-warning mb-2">Reboot Raspberry Pi</button>
        <button type="submit" name="action" value="shutdown" class="btn btn-danger mb-2">Shutdown Raspberry Pi</button>
      </form>
    </div>
  </div>

  <!-- Upload and Create Folder Section -->
  <div class="card mb-4">
    <div class="card-header"><h3>Upload Files / Create Folder</h3></div>
    <div class="card-body">
      <div class="row">
        <div class="col-md-6">
          <form id="uploadForm" action="{{ url_for('upload_file', req_path=req_path) }}" method="post" enctype="multipart/form-data">
            <div class="mb-3"><input type="file" name="file" class="form-control" multiple></div>
            <button type="submit" class="btn btn-primary"><i class="fas fa-upload"></i> Upload</button>
            <button type="button" id="cancelUpload" class="btn btn-warning" style="display:none;"><i class="fas fa-ban"></i> Cancel</button>
          </form>
          <div id="uploadProgress" class="progress mt-2" style="display:none;">
            <div id="uploadProgressBar" class="progress-bar" role="progressbar" style="width: 0%;">0%</div>
          </div>
          <div class="mt-2 text-center">
            <div id="uploadSpeed"></div>
            <div id="uploadStats"></div>
            <div id="uploadETA"></div>
          </div>
        </div>
        <div class="col-md-6">
          <form action="{{ url_for('create_folder', req_path=req_path) }}" method="post">
            <div class="mb-3"><input type="text" name="folder_name" placeholder="Folder Name" class="form-control"></div>
            <button type="submit" class="btn btn-secondary"><i class="fas fa-folder-plus"></i> Create Folder</button>
          </form>
        </div>
      </div>
    </div>
  </div>

  <!-- Bulk Delete & File List Section -->
  <form method="post" action="{{ url_for('delete_bulk') }}">
    <div class="card">
      <div class="card-header">
        <h3>File and Folder List</h3>
        <div class="mt-2">
          Sort by:
          <a href="{{ url_for('dir_listing', req_path=req_path, sort='name', order='asc') }}" class="btn btn-sm btn-outline-primary">Name ↑</a>
          <a href="{{ url_for('dir_listing', req_path=req_path, sort='name', order='desc') }}" class="btn btn-sm btn-outline-primary">Name ↓</a>
          <a href="{{ url_for('dir_listing', req_path=req_path, sort='date', order='asc') }}" class="btn btn-sm btn-outline-secondary">Date ↑</a>
          <a href="{{ url_for('dir_listing', req_path=req_path, sort='date', order='desc') }}" class="btn btn-sm btn-outline-secondary">Date ↓</a>
          <a href="{{ url_for('dir_listing', req_path=req_path, sort='type', order='asc') }}" class="btn btn-sm btn-outline-info">Type ↑</a>
          <a href="{{ url_for('dir_listing', req_path=req_path, sort='type', order='desc') }}" class="btn btn-sm btn-outline-info">Type ↓</a>
          <a href="{{ url_for('dir_listing', req_path=req_path, sort='size', order='asc') }}" class="btn btn-sm btn-outline-dark">Size ↑</a>
          <a href="{{ url_for('dir_listing', req_path=req_path, sort='size', order='desc') }}" class="btn btn-sm btn-outline-dark">Size ↓</a>
        </div>
      </div>
      <div class="card-body">
        <nav aria-label="breadcrumb">
          <ol class="breadcrumb">
            <li class="breadcrumb-item"><a href="{{ url_for('dir_listing', req_path='') }}"><i class="fas fa-home"></i> Home</a></li>
            {% if req_path %}
              {% set parts = req_path.split('/') %}
              {% set acc = "" %}
              {% for part in parts %}
                {% set acc = acc + part %}
                <li class="breadcrumb-item"><a href="{{ url_for('dir_listing', req_path=acc) }}">{{ part }}</a></li>
                {% set acc = acc + "/" %}
              {% endfor %}
            {% endif %}
          </ol>
        </nav>
        <table class="table table-striped table-hover">
          <thead>
            <tr>
              <th><input type="checkbox" id="select-all" onclick="toggleSelectAll(this)"></th>
              <th>Icon</th><th>Name</th><th>Type</th><th>Modified</th><th>Size</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {% if req_path %}
              <tr><td colspan="7"><a href="{{ url_for('dir_listing', req_path=parent_path) }}" class="btn btn-sm btn-outline-dark"><i class="fas fa-level-up-alt"></i> [..]</a></td></tr>
            {% endif %}
            {% for f in files %}
              <tr>
                <td><input type="checkbox" name="selected_files" value="{{ f['path'] }}"></td>
                <td>{% if f.is_dir %}<i class="fas fa-folder text-warning"></i>{% else %}<i class="fas fa-file text-secondary"></i>{% endif %}</td>
                <td>{% if f.is_dir %}<a href="{{ url_for('dir_listing', req_path=f.path) }}">{{ f.name }}/</a>{% else %}{{ f.name }}{% endif %}</td>
                <td>{{ f.file_type }}</td>
                <td>{{ f.mtime | datetimeformat }}</td>
                <td>{{ f.size | filesizeformat }}</td>
                <td>
                  {% if f.is_dir %}
                    <a href="{{ url_for('dir_listing', req_path=f.path) }}" class="btn btn-sm btn-primary"><i class="fas fa-folder-open"></i></a>
                    <a href="{{ url_for('delete_folder', req_path=f.path) }}" class="btn btn-sm btn-danger" onclick="return confirm('Delete folder?');"><i class="fas fa-trash-alt"></i></a>
                  {% else %}
                    <a href="{{ url_for('dir_listing', req_path=f.path) }}" class="btn btn-sm btn-success"><i class="fas fa-download"></i></a>
                    <a href="{{ url_for('edit_file', req_path=f.path) }}" class="btn btn-sm btn-warning"><i class="fas fa-edit"></i></a>
                    <a href="{{ url_for('delete_file', req_path=f.path) }}" class="btn btn-sm btn-danger" onclick="return confirm('Delete file?');"><i class="fas fa-trash-alt"></i></a>
                  {% endif %}
                </td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
        <button type="submit" class="btn btn-danger" onclick="return confirm('Delete selected items?');">Delete Selected</button>
      </div>
    </div>
  </form>
</div>

<script>
// Restore monitoring refresh at configured interval
function updateMonitoring() {
  const sel = document.getElementById("ssd_sensor");
  const param = sel ? "?ssd_sensor=" + encodeURIComponent(sel.value) : "";
  fetch("/api/monitoring" + param)
    .then(r => r.json())
    .then(data => {
      document.getElementById("cpu-temp").textContent = data.cpu_temp;
      document.getElementById("ssd-temp").textContent = data.ssd_temp;
      document.getElementById("uptime").textContent = data.uptime;
      const cpuBar = document.getElementById("cpuBar");
      cpuBar.style.width = data.cpu_usage + "%";
      cpuBar.textContent = data.cpu_usage + "%";
      const memBar = document.getElementById("memBar");
      memBar.style.width = data.mem_percent + "%";
      memBar.textContent = data.mem_percent + "%";
      const diskBar = document.getElementById("diskBar");
      diskBar.style.width = data.disk_percent + "%";
      diskBar.textContent = data.disk_percent + "%";
      document.getElementById("cpu-usage-text").textContent = data.cpu_freq_current + " MHz / " + data.cpu_freq_max + " MHz";
      document.getElementById("memory-usage-text").textContent = data.mem_used_human + " / " + data.mem_total_human;
      document.getElementById("disk-usage-text").textContent   = data.disk_used_human + " / " + data.disk_total_human;
    })
    .catch(console.error);
}

document.addEventListener("DOMContentLoaded", () => {
  updateMonitoring();
  setInterval(updateMonitoring, {{ config['monitor_refresh'] * 1000 }});
});

// Upload form handlers (speed, stats, ETA, cancel)
function formatETA(sec) {
  sec = Math.round(sec);
  let h = Math.floor(sec/3600), m = Math.floor((sec%3600)/60), s = sec%60;
  return [h,m,s].map(v=>v<10?'0'+v:v).join(':');
}

document.getElementById("uploadForm").addEventListener("submit", function(e) {
  e.preventDefault();
  let form = this, data = new FormData(form), xhr = new XMLHttpRequest();
  let btnCancel = document.getElementById("cancelUpload");
  btnCancel.style.display = "inline-block";
  btnCancel.onclick = () => {
    xhr.abort();
    document.getElementById("uploadSpeed").textContent = "Upload cancelled";
    document.getElementById("uploadStats").textContent = "";
    document.getElementById("uploadETA").textContent = "";
    document.getElementById("uploadProgress").style.display = "none";
    btnCancel.style.display = "none";
  };
  xhr.open("POST", form.action, true);
  document.getElementById("uploadProgress").style.display = "block";
  let lastLoaded = 0, lastTime = Date.now();
  xhr.upload.addEventListener("progress", function(e) {
    if (!e.lengthComputable) return;
    let pct = Math.round(e.loaded / e.total * 100);
    let bar = document.getElementById("uploadProgressBar");
    bar.style.width = pct + "%";
    bar.textContent = pct + "%";
    let now = Date.now(), dt = (now - lastTime)/1000, dL = e.loaded - lastLoaded;
    if (dt > 0) {
      let sp = dL / dt, spStr;
      if (sp >= 1024*1024*1024) spStr = (sp/(1024*1024*1024)).toFixed(2)+" GB/s";
      else if (sp >= 1024*1024)    spStr = (sp/(1024*1024)).toFixed(2)+" MB/s";
      else if (sp >= 1024)         spStr = (sp/1024).toFixed(2)+" KB/s";
      else                          spStr = sp.toFixed(2)+" B/s";
      document.getElementById("uploadSpeed").textContent = "Speed: "+spStr;
      lastTime = now; lastLoaded = e.loaded;
      function fmt(b) {
        if (b>=1024*1024*1024) return (b/(1024*1024*1024)).toFixed(2)+" GB";
        if (b>=1024*1024)      return (b/(1024*1024)).toFixed(2)+" MB";
        return (b/1024).toFixed(2)+" KB";
      }
      let tr = fmt(e.loaded), rem = fmt(e.total-e.loaded);
      document.getElementById("uploadStats").textContent = "Transferred: "+tr+" • Remaining: "+rem;
      let eta = (e.total - e.loaded)/sp;
      document.getElementById("uploadETA").textContent = "ETA: "+formatETA(eta);
    }
  });
  xhr.onload = function() {
    if (xhr.status===200) {
      alert("File(s) uploaded successfully.");
      window.location.reload();
    } else alert("Error uploading file.");
  };
  xhr.send(data);
});

function toggleSelectAll(src) {
  document.querySelectorAll('input[name="selected_files"]').forEach(cb => cb.checked = src.checked);
}
</script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/js/bootstrap.bundle.min.js"></script>
</body></html>
"""
    return render_template_string(html,
                                  mon=mon,
                                  files=files,
                                  config=CONFIG,
                                  req_path=req_path,
                                  parent_path=parent_path)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=CONFIG["port"], debug=True)
