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
                        config[key] = (val.lower()=="true")
                    else:
                        config[key] = val
    else:
        save_config(config)
    return config

def save_config(config):
    try:
        with open(CONFIG_FILE, "w") as f:
            for k,v in config.items():
                if isinstance(v,bool):
                    f.write(f"{k}={'True' if v else 'False'}\n")
                else:
                    f.write(f"{k}={v}\n")
    except PermissionError:
        os.chmod(CONFIG_FILE,0o666)
        with open(CONFIG_FILE, "w") as f:
            for k,v in config.items():
                if isinstance(v,bool):
                    f.write(f"{k}={'True' if v else 'False'}\n")
                else:
                    f.write(f"{k}={v}\n")

CONFIG = load_config()

# --- Temporary directory ---
TEMP_DIR = '/home/pi/tmp'
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR, mode=0o1777)
os.environ['TMPDIR'] = TEMP_DIR
tempfile.tempdir = TEMP_DIR

app = Flask(__name__)
app.secret_key = CONFIG["secret_key"]

USERNAME = CONFIG["login"]
PASSWORD = CONFIG["password"]
BASE_DIR = os.path.abspath("/home/pi/RetroPie")

def format_datetime(v):
    return datetime.fromtimestamp(v).strftime('%Y-%m-%d %H:%M:%S')
def format_filesize(v):
    if v is None: return ''
    for u in ['B','KB','MB','GB','TB']:
        if v<1024: return f"{v:.2f} {u}"
        v/=1024
    return f"{v:.2f} PB"

app.jinja_env.filters['datetimeformat'] = format_datetime
app.jinja_env.filters['filesizeformat'] = format_filesize

def check_auth(u,p): return u==CONFIG["login"] and p==CONFIG["password"]
def authenticate():
    return Response('Access denied\n',401,{'WWW-Authenticate':'Basic realm="Login Required"'})
def requires_auth(f):
    @wraps(f)
    def decorated(*a,**kw):
        auth = request.authorization
        if not auth or not check_auth(auth.username,auth.password):
            return authenticate()
        return f(*a,**kw)
    return decorated

def safe_path(path):
    abs_path = os.path.abspath(os.path.join(BASE_DIR,path))
    if os.path.commonpath([abs_path,BASE_DIR])!=BASE_DIR:
        abort(403)
    return abs_path

def round_1(x): return round(x,1)
def get_cpu_temp():
    try:
        t = subprocess.check_output(['vcgencmd','measure_temp']).decode().strip()
        return t.split('=')[1].split("'")[0]+"°C"
    except:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                v = float(f.read().strip())/1000
                return f"{round(v,1)}°C"
        except:
            return "N/A"
def get_ssd_temperatures():
    if not CONFIG.get("show_nvme"): return {}
    sensors={}
    try:
        out = subprocess.check_output(["sudo","nvme","smart-log","/dev/nvme0"],
                                      stderr=subprocess.STDOUT,universal_newlines=True)
        for line in out.splitlines():
            if "temperature" in line.lower():
                k,v=line.split(":",1)
                val=v.strip().split()[0]
                sensors[k.strip()]=val if val.lower().endswith("c") else val+"°C"
    except:
        pass
    return sensors

def get_monitoring_data(sensor=None):
    if sensor is None: sensor=CONFIG.get("ssd_sensor")
    cpu_usage=round_1(psutil.cpu_percent(interval=0.0))
    mem=psutil.virtual_memory(); mem_percent=round_1(mem.percent)
    disk=psutil.disk_usage(BASE_DIR); disk_percent=round_1((disk.used/disk.total)*100 if disk.total>0 else 0)
    disk_free=disk.total-disk.used; cpu_temp=get_cpu_temp()
    ssd_temps=get_ssd_temperatures()
    if not ssd_temps:
        ssd_name,ssd_temp=None,"N/A"
    else:
        if sensor and sensor in ssd_temps:
            ssd_name,ssd_temp=sensor,ssd_temps[sensor]
        else:
            ssd_name,ssd_temp=next(iter(ssd_temps.items()))
    try:
        freq=psutil.cpu_freq()
        cf_cur=round_1(freq.current) if freq else 0
        cf_max=round_1(freq.max) if freq else 0
    except:
        cf_cur,cf_max="N/A","N/A"
    bt=psutil.boot_time(); delta=datetime.now()-datetime.fromtimestamp(bt)
    d,h=delta.days,delta.seconds//3600; m=(delta.seconds%3600)//60; s=delta.seconds%60
    uptime=f"{d}d {h}h {m}m {s}s" if d>0 else f"{h}h {m}m {s}s"
    return {
        'cpu_usage':cpu_usage,'cpu_temp':cpu_temp,
        'cpu_freq_current':cf_cur,'cpu_freq_max':cf_max,
        'mem_total':mem.total,'mem_used':mem.used,'mem_percent':mem_percent,
        'disk_total':disk.total,'disk_used':disk.used,'disk_free':disk_free,'disk_percent':disk_percent,
        'ssd_all':ssd_temps,'ssd_selected_name':ssd_name,'ssd_temp':ssd_temp,
        'uptime':uptime
    }

@app.route('/api/monitoring')
@requires_auth
def api_monitoring():
    sensor=request.args.get('ssd_sensor') or CONFIG.get("ssd_sensor")
    m=get_monitoring_data(sensor)
    return jsonify({
        'cpu_usage':m['cpu_usage'],'cpu_temp':m['cpu_temp'],
        'cpu_freq_current':m['cpu_freq_current'],'cpu_freq_max':m['cpu_freq_max'],
        'mem_percent':m['mem_percent'],'mem_used_human':format_filesize(m['mem_used']),
        'mem_total_human':format_filesize(m['mem_total']),
        'disk_percent':m['disk_percent'],'disk_used_human':format_filesize(m['disk_used']),
        'disk_total_human':format_filesize(m['disk_total']),'disk_free_human':format_filesize(m['disk_free']),
        'ssd_temp':m['ssd_temp'],'ssd_selected_name':m['ssd_selected_name'],'ssd_all':m['ssd_all'],
        'uptime':m['uptime']
    })

@app.route('/control', methods=['POST'])
@requires_auth
def control():
    action=request.form.get("action")
    if action=="reboot":
        flash("Rebooting Raspberry Pi successfully.")
        subprocess.Popen(["reboot"])
    elif action=="shutdown":
        flash("Shutting down Raspberry Pi...")
        subprocess.Popen(["shutdown","now"])
    else:
        flash("Invalid action.")
    return redirect(url_for('dir_listing',req_path=""))

@app.route('/settings', methods=['GET','POST'])
@requires_auth
def settings():
    global CONFIG,USERNAME,PASSWORD,app
    msg=""
    if request.method=='POST':
        if 'save_credentials' in request.form:
            nl, np = request.form.get('login','').strip(), request.form.get('password','').strip()
            if nl: CONFIG['login']=nl; USERNAME=nl
            if np: CONFIG['password']=np; PASSWORD=np
            msg+="Credentials updated. "
        elif 'save_app_settings' in request.form:
            sk = request.form.get('secret_key','').strip()
            p = request.form.get('port','').strip()
            r = request.form.get('monitor_refresh','').strip()
            CONFIG['show_nvme'] = (request.form.get('show_nvme')=='on')
            cl = request.form.get('config_location','64').strip()
            CONFIG['config_location']=cl
            if sk: CONFIG['secret_key']=sk; app.secret_key=sk
            if p.isdigit(): CONFIG['port']=int(p)
            try:
                rv=float(r)
                if rv>=0.5: CONFIG['monitor_refresh']=rv
            except:
                pass
            msg+="App settings updated. (Port change on restart.) "
        elif 'restart_service' in request.form:
            subprocess.call(["systemctl","restart","web_panel.service"]); msg+="Service restarted. "
        elif 'enable_service' in request.form:
            subprocess.call(["systemctl","enable","web_panel.service"]); msg+="Service enabled. "
        elif 'disable_service' in request.form:
            subprocess.call(["systemctl","disable","web_panel.service"]); msg+="Service disabled. "
        elif 'stop_service' in request.form:
            subprocess.call(["systemctl","stop","web_panel.service"]); msg+="Service stopped. "
        save_config(CONFIG)
        flash(msg)
        return redirect(url_for('settings'))
    return render_template_string("""
<!doctype html>
<html lang="en"><head>
  <meta charset="utf-8">
  <title>Settings</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>.nav-tabs .nav-link{cursor:pointer;}</style>
</head><body>
  <div class="container py-4">
    <h1>Settings</h1>
    {% with messages=get_flashed_messages() %}
      {% if messages %}
        {% for m in messages %}
          <div class="alert alert-info">{{m}}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    <ul class="nav nav-tabs" id="tab" role="tablist">
      <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#creds">Credentials</button></li>
      <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#app">App Settings</button></li>
      <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#svc">Service</button></li>
    </ul>
    <div class="tab-content pt-3">
      <div class="tab-pane fade show active" id="creds">
        <form method="post">
          <div class="mb-3"><label class="form-label">Login</label><input class="form-control" name="login" value="{{config['login']}}"></div>
          <div class="mb-3"><label class="form-label">Password</label><input class="form-control" name="password" value="{{config['password']}}"></div>
          <button class="btn btn-primary" name="save_credentials">Save Credentials</button>
        </form>
      </div>
      <div class="tab-pane fade" id="app">
        <form method="post">
          <div class="mb-3"><label class="form-label">Secret Key</label><input class="form-control" name="secret_key" value="{{config['secret_key']}}"></div>
          <div class="mb-3"><label class="form-label">Port</label><input type="number" class="form-control" name="port" value="{{config['port']}}"></div>
          <div class="mb-3"><label class="form-label">Refresh Interval (sec, ≥0.5)</label><input type="number" step="0.1" class="form-control" name="monitor_refresh" value="{{config['monitor_refresh']}}"></div>
          <div class="form-check mb-3"><input class="form-check-input" type="checkbox" name="show_nvme" {% if config['show_nvme'] %}checked{% endif %}><label class="form-check-label">Display NVMe Temp</label></div>
          <div class="mb-3"><label class="form-label">Config File Location</label>
            <select class="form-select" name="config_location">
              <option value="64" {% if config['config_location']=='64' %}selected{% endif %}>64-bit (/boot/firmware/config.txt)</option>
              <option value="32" {% if config['config_location']=='32' %}selected{% endif %}>32-bit (/boot/config.txt)</option>
            </select>
          </div>
          <button class="btn btn-primary" name="save_app_settings">Save App Settings</button>
        </form>
      </div>
      <div class="tab-pane fade" id="svc">
        <form method="post">
          <button class="btn btn-warning mb-2" name="restart_service">Restart Service</button>
          <button class="btn btn-danger mb-2" name="stop_service">Stop Service</button>
          <button class="btn btn-success mb-2" name="enable_service">Enable Service</button>
          <button class="btn btn-danger mb-2" name="disable_service">Disable Service</button>
        </form>
      </div>
    </div>
    <a href="{{url_for('dir_listing',req_path='')}}" class="btn btn-secondary mt-3">Back to File Manager</a>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/js/bootstrap.bundle.min.js"></script>
</body></html>
""", config=CONFIG)

@app.route('/edit/<path:req_path>', methods=['GET','POST'])
@requires_auth
def edit_file(req_path):
    abs_path=safe_path(req_path)
    if not os.path.isfile(abs_path):
        flash("Not a file."); return redirect(url_for('dir_listing',req_path=posixpath.dirname(req_path)))
    if request.method=='POST':
        c=request.form.get('content','')
        try:
            with open(abs_path,'w',encoding='utf-8') as f: f.write(c)
            flash("File updated."); return redirect(url_for('dir_listing',req_path=posixpath.dirname(req_path)))
        except Exception as e:
            flash(f"Error saving: {e}")
    else:
        try:
            with open(abs_path,'r',encoding='utf-8') as f: content=f.read()
        except Exception as e:
            flash(f"Error reading: {e}"); return redirect(url_for('dir_listing',req_path=posixpath.dirname(req_path)))
        return render_template_string("""
<!doctype html>
<html lang="en"><head>
  <meta charset="utf-8"><title>Edit File</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet">
</head><body>
  <div class="container py-4">
    <h1>Edit file: {{filename}}</h1>
    <form method="post">
      <div class="mb-3"><textarea name="content" rows="20" class="form-control">{{content}}</textarea></div>
      <button class="btn btn-primary">Save Changes</button>
      <a href="{{url_for('dir_listing',req_path=parent)}}" class="btn btn-secondary">Cancel</a>
    </form>
  </div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/js/bootstrap.bundle.min.js"></script>
</body></html>
""", filename=os.path.basename(abs_path),content=content,parent=posixpath.dirname(req_path))

@app.route('/edit_config', methods=['GET','POST'])
@requires_auth
def edit_config():
    config_path = '/boot/config.txt' if CONFIG.get("config_location")=="32" else '/boot/firmware/config.txt'
    if request.method=='POST':
        c=request.form.get('content','')
        try:
            with open(config_path,'w',encoding='utf-8') as f: f.write(c)
            flash(f"Updated config.txt at {config_path}"); return redirect(url_for('dir_listing',req_path=''))
        except Exception as e:
            flash(f"Error saving: {e}")
    try:
        with open(config_path,'r',encoding='utf-8') as f: content=f.read()
    except Exception as e:
        flash(f"Error reading: {e}"); return redirect(url_for('dir_listing',req_path=''))
    return render_template_string("""
<!doctype html>
<html lang="en"><head>
  <meta charset="utf-8"><title>Edit RPI config.txt</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet">
</head><body>
  <div class="container py-4">
    <h1>Edit RPI config.txt at {{path}}</h1>
    <form method="post">
      <div class="mb-3"><textarea name="content" rows="20" class="form-control">{{content}}</textarea></div>
      <button class="btn btn-primary">Save Changes</button>
      <a href="{{url_for('dir_listing',req_path='')}}" class="btn btn-secondary">Cancel</a>
    </form>
  </div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/js/bootstrap.bundle.min.js"></script>
</body></html>
""",content=content,path=config_path)

@app.route('/delete_bulk', methods=['POST'])
@requires_auth
def delete_bulk():
    sel=request.form.getlist('selected_files')
    for f in sel:
        p=safe_path(f)
        try:
            if os.path.isdir(p): shutil.rmtree(p)
            elif os.path.isfile(p): os.remove(p)
        except Exception as e: flash(f"Error deleting {f}: {e}")
    flash("Selected items deleted.")
    return redirect(url_for('dir_listing',req_path=posixpath.dirname(sel[0]) if sel else ''))

@app.route('/create_folder/<path:req_path>', methods=['POST'])
@requires_auth
def create_folder(req_path):
    d=safe_path(req_path)
    name=request.form.get('folder_name','').strip()
    if not name: flash("Folder name empty."); return redirect(url_for('dir_listing',req_path=req_path))
    new=os.path.join(d,secure_filename(name))
    try: os.makedirs(new); flash("Folder created.")
    except Exception as e: flash(f"Error creating folder: {e}")
    return redirect(url_for('dir_listing',req_path=req_path))

@app.route('/upload/<path:req_path>', methods=['POST'])
@requires_auth
def upload_file(req_path):
    d=safe_path(req_path)
    if 'file' not in request.files:
        flash("No file selected."); return redirect(url_for('dir_listing',req_path=req_path))
    for f in request.files.getlist('file'):
        if f.filename=='':
            flash("One file missing name."); continue
        fn=secure_filename(f.filename)
        dest=os.path.join(d,fn)
        try:
            with open(dest,'wb') as o:
                while True:
                    chunk = f.stream.read(8192)
                    if not chunk: break
                    o.write(chunk)
            flash(f"File '{fn}' uploaded successfully.")
        except Exception as e:
            flash(f"Error saving '{fn}': {e}")
    return redirect(url_for('dir_listing',req_path=req_path))

@app.route('/delete/<path:req_path>')
@requires_auth
def delete_file(req_path):
    p=safe_path(req_path)
    if not os.path.isfile(p):
        flash("Not a file.")
    else:
        try: os.remove(p); flash("File deleted.")
        except Exception as e: flash(f"Error deleting file: {e}")
    return redirect(url_for('dir_listing',req_path=posixpath.dirname(req_path)))

@app.route('/delete_folder/<path:req_path>')
@requires_auth
def delete_folder(req_path):
    p=safe_path(req_path)
    if not os.path.isdir(p):
        flash("Not a folder.")
    else:
        try: shutil.rmtree(p); flash("Folder deleted.")
        except Exception as e: flash(f"Error deleting folder: {e}")
    return redirect(url_for('dir_listing',req_path=posixpath.dirname(req_path)))

@app.route('/', defaults={'req_path':''})
@app.route('/<path:req_path>')
@requires_auth
def dir_listing(req_path):
    sel=request.args.get('ssd_sensor')
    if sel:
        CONFIG['ssd_sensor']=sel; save_config(CONFIG)
    path=safe_path(req_path)
    if not os.path.exists(path):
        return f"Not found: {req_path}",404
    if os.path.isfile(path):
        return send_from_directory(os.path.dirname(path),os.path.basename(path),as_attachment=True)
    mon=get_monitoring_data(request.args.get('ssd_sensor',CONFIG.get("ssd_sensor")))
    files=[]
    try:
        for fn in os.listdir(path):
            full=os.path.join(path,fn)
            files.append({
                'name':fn,
                'path':os.path.join(req_path,fn),
                'is_dir':os.path.isdir(full),
                'mtime':os.path.getmtime(full),
                'size':os.path.getsize(full) if os.path.isfile(full) else None,
                'file_type':'folder' if os.path.isdir(full) else os.path.splitext(fn)[1].lower()
            })
    except PermissionError:
        flash("Permission denied.")
    sort=request.args.get('sort','name')
    order=request.args.get('order','asc')
    rev=(order=='desc')
    if sort=='date':
        files.sort(key=lambda x:x['mtime'],reverse=rev)
    elif sort=='type':
        files.sort(key=lambda x:(x['file_type'],x['name'].lower()),reverse=rev)
    elif sort=='size':
        files.sort(key=lambda x:x['size'] or 0,reverse=rev)
    else:
        files.sort(key=lambda x:x['name'].lower(),reverse=rev)
    parent=posixpath.dirname(req_path)
    return render_template_string("""
<!doctype html>
<html lang="en"><head>
  <meta charset="utf-8"><title>RetroPie Light Web Game Manager</title>
  <meta name="viewport"content="width=device-width,initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <style>
  canvas { max-width: 300px; max-height: 300px; }
  .progress { height: 35px; }
  .progress-bar { color: black; font-size: 1.2em; font-weight: bold; }

  /* ─── Upload specific styles ─── */

  /* Container for upload progress */
  #uploadProgress {
    height: 16px;                   /* slightly smaller than default */
    background-color: #e9ecef;      /* light grey background */
    margin-top: 8px;                /* space above it */
    border-radius: 4px;             /* rounded corners */
  }

  /* Inner bar for upload progress */
  #uploadProgressBar {
    background-color: #17a2b8;      /* a distinct color (teal) */
    transition: width 0.3s ease;    /* smooth animation */
  }

  /* Optional striped/animated state */
  #uploadProgressBar.striped {
    background-image: linear-gradient(
      45deg,
      rgba(255,255,255,0.15) 25%,
      transparent 25%,
      transparent 50%,
      rgba(255,255,255,0.15) 50%,
      rgba(255,255,255,0.15) 75%,
      transparent 75%,
      transparent
    );
    background-size: 1rem 1rem;     /* stripe size */
  }
  #uploadProgressBar.animated {
    animation: progress-bar-stripes 1s linear infinite;
  }

  @keyframes progress-bar-stripes {
    from { background-position: 1rem 0; }
    to   { background-position: 0   0; }
  }
</style>
</head><body>
  <div class="container py-4">
    <h1 class="mb-4">RetroPie Light Web Game Manager</h1>
    <div class="text-end mb-3">
      <a href="{{url_for('edit_config')}}" class="btn btn-outline-warning"><i class="fas fa-edit"></i> Edit RPI config.txt</a>
      <a href="{{url_for('settings')}}" class="btn btn-outline-secondary"><i class="fas fa-cog"></i> Settings</a>
    </div>
    {% with msgs=get_flashed_messages() %}
      {% if msgs %}
        {% for m in msgs %}
          <div class="alert alert-warning">{{m}}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}
    <!-- Monitoring -->
    <div class="card mb-4">
      <div class="card-header"><h3>Monitoring</h3></div>
      <div class="card-body">
        <div class="row mb-3">
          <div class="col-md-3"><strong>CPU Temp:</strong> <span id="cpu-temp">{{mon.cpu_temp}}</span></div>
          <div class="col-md-3"><strong>SSD Temp:</strong> <span id="ssd-temp">{{mon.ssd_temp}}</span>{% if mon.ssd_selected_name %}<br><small>{{mon.ssd_selected_name}}</small>{% endif %}</div>
          <div class="col-md-3"><strong>Uptime:</strong> <span id="uptime">{{mon.uptime}}</span></div>
          <div class="col-md-3">
            {% if config.show_nvme and mon.ssd_all %}
              <form method="get" class="d-flex align-items-center flex-wrap">
                <label class="me-2 mb-1"><small>Select SSD Sensor:</small></label>
                <input type="hidden" name="req_path" value="{{req_path}}">
                <select name="ssd_sensor" id="ssd_sensor_select" class="form-select" style="max-width:200px" onchange="this.form.submit()">
                  {% for s,t in mon.ssd_all.items() %}
                    <option value="{{s}}" {% if s==mon.ssd_selected_name %}selected{% endif %}>{{s}}: {{t}}</option>
                  {% endfor %}
                </select>
              </form>
            {% endif %}
          </div>
        </div>
        <div class="row mb-3">
          <div class="col-md-4"><strong>CPU Frequency:</strong> <span id="cpu-usage-text">{{mon.cpu_freq_current}} MHz / {{mon.cpu_freq_max}} MHz</span></div>
          <div class="col-md-4"><strong>Memory Usage:</strong> <span id="memory-usage-text">{{mon.mem_used | filesizeformat}} / {{mon.mem_total | filesizeformat}}</span></div>
          <div class="col-md-4"></div>
        </div>
        <div class="row mb-3">
          <div class="col-md-4"><strong>CPU Usage (Progress):</strong>
            <div class="progress"><div id="cpuBar" class="progress-bar" role="progressbar" style="width:{{mon.cpu_usage}}%" aria-valuenow="{{mon.cpu_usage}}" aria-valuemin="0" aria-valuemax="100">{{mon.cpu_usage}}%</div></div>
          </div>
          <div class="col-md-4"><strong>Memory Usage (Progress):</strong>
            <div class="progress"><div id="memBar" class="progress-bar bg-success" role="progressbar" style="width:{{mon.mem_percent}}%" aria-valuenow="{{mon.mem_percent}}" aria-valuemin="0" aria-valuemax="100">{{mon.mem_percent}}%</div></div>
          </div>
          <div class="col-md-4"><strong>Disk Usage:</strong> ({{mon.disk_used | filesizeformat}} / {{mon.disk_total | filesizeformat}})
            <div class="progress"><div id="diskBar" class="progress-bar bg-info" role="progressbar" style="width:{{mon.disk_percent}}%" aria-valuenow="{{mon.disk_percent}}" aria-valuemin="0" aria-valuemax="100">{{mon.disk_percent}}%</div></div>
          </div>
        </div>
      </div>
    </div>
    <!-- Control -->
    <div class="card mb-4">
      <div class="card-header"><h3>Control</h3></div>
      <div class="card-body">
        <form method="post" action="{{url_for('control')}}">
          <button class="btn btn-warning mb-2" name="action" value="reboot">Reboot Raspberry Pi</button>
          <button class="btn btn-danger mb-2" name="action" value="shutdown">Shutdown Raspberry Pi</button>
        </form>
      </div>
    </div>
    <!-- Upload & Create -->
    <div class="card mb-4">
      <div class="card-header"><h3>Upload Files / Create Folder</h3></div>
      <div class="card-body">
        <div class="row">
          <div class="col-md-6">
            <form id="uploadForm" action="{{url_for('upload_file',req_path=req_path)}}" method="post" enctype="multipart/form-data">
              <div class="mb-3"><input type="file" name="file" class="form-control" multiple></div>
              <button type="submit" class="btn btn-primary"><i class="fas fa-upload"></i> Upload</button>
              <button type="button" id="cancelUpload" class="btn btn-secondary" style="display:none;">Cancel Upload</button>
            </form>
            <div id="uploadProgress" class="progress" style="display:none;">
              <div id="uploadProgressBar" class="progress-bar" role="progressbar" style="width:0%;">0%</div>
            </div>
            <div id="uploadInfo" class="text-center mt-2"></div>
          </div>
          <div class="col-md-6">
            <form action="{{url_for('create_folder',req_path=req_path)}}" method="post">
              <div class="mb-3"><input type="text" name="folder_name" placeholder="Folder Name" class="form-control"></div>
              <button class="btn btn-secondary"><i class="fas fa-folder-plus"></i> Create Folder</button>
            </form>
          </div>
        </div>
      </div>
    </div>
    <!-- File List -->
    <form method="post" action="{{url_for('delete_bulk')}}">
      <div class="card">
        <div class="card-header"><h3>File and Folder List</h3>
          <div class="mt-2">
            <span>Sort by:</span>
            <a href="{{url_for('dir_listing',req_path=req_path,sort='name',order='asc')}}" class="btn btn-sm btn-outline-primary">Name ↑</a>
            <a href="{{url_for('dir_listing',req_path=req_path,sort='name',order='desc')}}" class="btn btn-sm btn-outline-primary">Name ↓</a>
            <a href="{{url_for('dir_listing',req_path=req_path,sort='date',order='asc')}}" class="btn btn-sm btn-outline-secondary">Date ↑</a>
            <a href="{{url_for('dir_listing',req_path=req_path,sort='date',order='desc')}}" class="btn btn-sm btn-outline-secondary">Date ↓</a>
            <a href="{{url_for('dir_listing',req_path=req_path,sort='type',order='asc')}}" class="btn btn-sm btn-outline-info">Type ↑</a>
            <a href="{{url_for('dir_listing',req_path=req_path,sort='type',order='desc')}}" class="btn btn-sm btn-outline-info">Type ↓</a>
            <a href="{{url_for('dir_listing',req_path=req_path,sort='size',order='asc')}}" class="btn btn-sm btn-outline-dark">Size ↑</a>
            <a href="{{url_for('dir_listing',req_path=req_path,sort='size',order='desc')}}" class="btn btn-sm btn-outline-dark">Size ↓</a>
          </div>
        </div>
        <div class="card-body">
          <nav aria-label="breadcrumb"><ol class="breadcrumb">
            <li class="breadcrumb-item"><a href="{{url_for('dir_listing',req_path='')}}"><i class="fas fa-home"></i> Home</a></li>
            {% if req_path %}
              {% set parts=req_path.split('/') %}{% set acc="" %}
              {% for p in parts %}
                {% set acc=acc+p %}
                <li class="breadcrumb-item"><a href="{{url_for('dir_listing',req_path=acc)}}">{{p}}</a></li>
                {% set acc=acc+"/" %}
              {% endfor %}
            {% endif %}
          </ol></nav>
          <table class="table table-striped table-hover">
            <thead><tr>
              <th><input type="checkbox" id="select-all" onclick="toggleSelectAll(this)"></th>
              <th>Icon</th><th>Name</th><th>Type</th><th>Modified</th><th>Size</th><th>Actions</th>
            </tr></thead>
            <tbody>
              {% if req_path %}
                <tr><td colspan="7">
                  <a href="{{url_for('dir_listing',req_path=parent)}}" class="btn btn-sm btn-outline-dark">
                    <i class="fas fa-level-up-alt"></i> [..]
                  </a>
                </td></tr>
              {% endif %}
              {% for f in files %}
                <tr>
                  <td><input type="checkbox" name="selected_files" value="{{f.path}}"></td>
                  <td>{% if f.is_dir %}<i class="fas fa-folder fa-lg text-warning"></i>{% else %}<i class="fas fa-file fa-lg text-secondary"></i>{% endif %}</td>
                  <td>{% if f.is_dir %}<a href="{{url_for('dir_listing',req_path=f.path)}}">{{f.name}}/</a>{% else %}{{f.name}}{% endif %}</td>
                  <td>{{f.file_type}}</td>
                  <td>{{f.mtime|datetimeformat}}</td>
                  <td>{{f.size|filesizeformat}}</td>
                  <td>
                    {% if f.is_dir %}
                      <a href="{{url_for('dir_listing',req_path=f.path)}}" class="btn btn-sm btn-primary"><i class="fas fa-folder-open"></i></a>
                      <a href="{{url_for('delete_folder',req_path=f.path)}}" class="btn btn-sm btn-danger" onclick="return confirm('Delete folder?');"><i class="fas fa-trash-alt"></i></a>
                    {% else %}
                      <a href="{{url_for('dir_listing',req_path=f.path)}}" class="btn btn-sm btn-success"><i class="fas fa-download"></i></a>
                      <a href="{{url_for('edit_file',req_path=f.path)}}" class="btn btn-sm btn-warning"><i class="fas fa-edit"></i></a>
                      <a href="{{url_for('delete_file',req_path=f.path)}}" class="btn btn-sm btn-danger" onclick="return confirm('Delete file?');"><i class="fas fa-trash-alt"></i></a>
                    {% endif %}
                  </td>
                </tr>
              {% endfor %}
            </tbody>
          </table>
          <button class="btn btn-danger" onclick="return confirm('Delete selected?');">Delete Selected</button>
        </div>
      </div>
    </form>
  </div>
<script>
function humanSize(b){
  if(b>=1024*1024*1024) return (b/1024/1024/1024).toFixed(2)+" GB";
  if(b>=1024*1024) return (b/1024/1024).toFixed(2)+" MB";
  return (b/1024).toFixed(2)+" KB";
}
function toggleSelectAll(src){
  document.querySelectorAll('input[name="selected_files"]').forEach(cb=>cb.checked=src.checked);
}
// Monitoring update
function updateMonitoring(){
  let sensor=document.getElementById("ssd_sensor_select");
  let param=sensor?"?ssd_sensor="+sensor.value:"";
  fetch("/api/monitoring"+param).then(r=>r.json()).then(data=>{
    document.getElementById("cpu-temp").textContent=data.cpu_temp;
    document.getElementById("ssd-temp").textContent=data.ssd_temp;
    let cpuBar=document.getElementById("cpuBar");
    cpuBar.style.width=data.cpu_usage+"%"; cpuBar.textContent=data.cpu_usage+"%";
    let memBar=document.getElementById("memBar");
    memBar.style.width=data.mem_percent+"%"; memBar.textContent=data.mem_percent+"%";
    let diskBar=document.getElementById("diskBar");
    diskBar.style.width=data.disk_percent+"%"; diskBar.textContent=data.disk_percent+"%";
    document.getElementById("cpu-usage-text").textContent=data.cpu_freq_current+" MHz / "+data.cpu_freq_max+" MHz";
    document.getElementById("memory-usage-text").textContent=data.mem_used_human+" / "+data.mem_total_human;
    document.getElementById("uptime").textContent=data.uptime;
  }).catch(e=>console.error(e));
}
document.addEventListener("DOMContentLoaded",()=>{
  setInterval(updateMonitoring, {{config['monitor_refresh']*1000}});
  let form=document.getElementById("uploadForm"), xhr;
  const prog=document.getElementById("uploadProgress"),
        bar=document.getElementById("uploadProgressBar"),
        info=document.getElementById("uploadInfo"),
        btnCancel=document.getElementById("cancelUpload");
  form.addEventListener("submit",e=>{
    e.preventDefault();
    const fd=new FormData(form);
    xhr=new XMLHttpRequest();
    xhr.open("POST", form.action, true);
    prog.style.display="block"; btnCancel.style.display="inline-block";
    let lastLoaded=0, lastTime=Date.now(), totalSize=0;
    xhr.upload.addEventListener("loadstart",()=>{
      totalSize=0;
      for(let v of fd.values()){
        if(v.size) totalSize+=v.size;
      }
    });
    xhr.upload.addEventListener("progress",e=>{
      if(e.lengthComputable){
        const now=Date.now(), deltaTime=(now-lastTime)/1000, deltaLoaded=e.loaded-lastLoaded;
        const speed=deltaLoaded/deltaTime, rem=totalSize-e.loaded, eta=rem/speed;
        lastTime=now; lastLoaded=e.loaded;
        bar.style.width=Math.round((e.loaded/totalSize)*100)+"%";
        bar.textContent=Math.round((e.loaded/totalSize)*100)+"%";
        let speedStr="", remStr="", doneStr="";
        if(speed>=1024*1024*1024) speedStr=(speed/1024/1024/1024).toFixed(2)+" GB/s";
        else if(speed>=1024*1024) speedStr=(speed/1024/1024).toFixed(2)+" MB/s";
        else if(speed>=1024) speedStr=(speed/1024).toFixed(2)+" KB/s";
        else speedStr=speed.toFixed(2)+" B/s";
        doneStr=humanSize(e.loaded)+"/"+humanSize(totalSize);
        remStr=humanSize(rem)+" Remaining";
        let h=Math.floor(eta/3600), m=Math.floor((eta%3600)/60), s=Math.floor(eta%60);
        let etaStr=(h?h+"h ":"")+(m?m+"m ":"")+(s? s+"s":"");
        info.textContent=`Speed: ${speedStr} • Done upload: ${doneStr} • ${remStr} • ETA: ${etaStr}`;
      }
    });
    xhr.onload=()=>{
      if(xhr.status==200){
        alert("File(s) uploaded successfully.");
        window.location.reload();
      } else alert("Error uploading file.");
    };
    xhr.send(fd);
    btnCancel.onclick=()=>{
      if(xhr){xhr.abort(); info.textContent="Upload canceled."; btnCancel.style.display="none";}
    };
  });
});
</script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.1/dist/js/bootstrap.bundle.min.js"></script>
</body></html>
""", mon=mon, files=files, req_path=req_path, parent=parent, config=CONFIG)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=CONFIG["port"], debug=True)
