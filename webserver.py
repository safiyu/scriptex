from flask import Flask, render_template, request, redirect, url_for, Response, send_from_directory
import os
from functools import wraps
import shutil
from config import USERNAME, PASSWORD
from datetime import datetime, timedelta
from collections import defaultdict
import subprocess
import threading
import logging
import sys

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# CONFIG
MAX_FAILED_ATTEMPTS = 3
FAIL_WINDOW = timedelta(minutes=30)
BAN_DURATION = timedelta(minutes=600)

# Load trusted IPs from environment variable
trusted_ips_raw = os.environ.get("TRUSTED_IPS", "")
TRUSTED_IPS = set(ip.strip() for ip in trusted_ips_raw.split(",") if ip.strip())

# Track attempts
failed_attempts = defaultdict(list)  # { ip: [datetime, ...] }
banned_ips = {}  # { ip: ban_expiry_datetime }

def check_auth(username, password):
    return username == USERNAME and password == PASSWORD

def nauthenticate():
    from flask import Response
    return Response(
        'Could not verify your login.', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        ip = request.remote_addr
        now = datetime.now()
        logger.info(f"Incoming request from IP: {ip}")
        
        # ✅ Bypass auth for trusted IPs
        if ip in TRUSTED_IPS:
            logger.info(f"Trusted IP bypassing auth: {ip}")
            return f(*args, **kwargs)
        
        # Check if IP is banned
        if ip in banned_ips:
            if now < banned_ips[ip]:
                logger.info(f"Blocked request from banned IP: {ip}")
                return Response("Too many failed attempts. Try again later.", 429)
            else:
                # Ban expired
                logger.info(f"Ban expired for IP: {ip}")
                banned_ips.pop(ip)
        
        auth = request.authorization
        
        # Validate credentials
        if not auth or auth.username != USERNAME or auth.password != PASSWORD:
            # Clean old attempts
            failed_attempts[ip] = [t for t in failed_attempts[ip] if now - t < FAIL_WINDOW]
            failed_attempts[ip].append(now)
            
            if len(failed_attempts[ip]) >= MAX_FAILED_ATTEMPTS:
                logger.info(f"Banning IP due to failed attempts: {ip}")
                banned_ips[ip] = now + BAN_DURATION
                failed_attempts.pop(ip, None)
                return Response("Too many failed attempts. You are temporarily blocked.", 429)
            
            logger.info(f"Failed login attempt from IP: {ip}")
            return Response("Invalid credentials", 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})
        
        # On success: reset attempt history
        failed_attempts.pop(ip, None)
        logger.info(f"Successful authentication from IP: {ip}")
        return f(*args, **kwargs)
    
    return decorated

@app.route('/')
@requires_auth
def home():
    return render_template('index.html')

@app.route('/run-script')
@requires_auth
def run_script():
    script_path = "/app/scriptorun.sh"
    log_path = "/app/scriptorun.log"

    if not os.path.exists(script_path):
        logger.error(f"Script not found at {script_path}")
        return (f"Script not found at {script_path}", 500)

    try:
        # Start the script asynchronously so the Gunicorn worker isn't blocked.
        # If available, use `stdbuf -oL` to force line-buffered output when the
        # process is connected to a pipe; otherwise fall back to running bash.
        stdbuf_path = shutil.which("stdbuf")
        if stdbuf_path:
            cmd = [stdbuf_path, "-oL", "/bin/bash", script_path]
            logger.info(f"Using stdbuf at {stdbuf_path} to enable line buffering")
        else:
            cmd = ["/bin/bash", script_path]
            logger.info("stdbuf not found; proceeding without explicit line buffering")

        # We'll capture stdout/stderr and stream it to both a log file and the
        # Flask logger (which prints to stdout -> visible in `docker logs`).
        # decode errors='replace' prevents UnicodeDecodeError when subprocess
        # emits bytes that are not valid UTF-8; replacement characters will
        # be inserted instead of raising.
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', bufsize=1, start_new_session=True)

        def _stream_output(p, logfile_path):
            try:
                logger.info(f"Streamer thread started for pid {p.pid}")
                with open(logfile_path, "a") as lf:
                    # Read line-by-line and write to both log file and logger
                    for line in iter(p.stdout.readline, ""):
                        if not line:
                            break
                        lf.write(line)
                        lf.flush()
                        logger.info(line.rstrip())
                # ensure we've consumed stdout; wait for process exit and report code
                rc = p.wait()
                logger.info(f"Process pid {p.pid} exited with return code {rc}")
            except Exception:
                logger.exception("Error while streaming process output")

        t = threading.Thread(target=_stream_output, args=(proc, log_path), daemon=True)
        t.start()

        logger.info(f"Started script as PID {proc.pid}, streaming output to logger and {log_path}")
        # Return immediately; script runs in background
        return (f"Script started (pid={proc.pid}). See {log_path}", 202)
    except FileNotFoundError as e:
        logger.error(f"Interpreter not found or script missing: {e}")
        return ("Interpreter not found or script missing", 500)
    except PermissionError as e:
        logger.error(f"Permission error starting script: {e}")
        return ("Permission error starting script; check file permissions or mount options", 500)
    except Exception:
        logger.exception("Unexpected error starting script")
        return ("Script execution failed!", 500)

@app.route('/favicon.ico')
@requires_auth
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 
                                'favicon.ico', 
                                mimetype='image/vnd.microsoft.icon')

if __name__ == '__main__':
    logger.info(f"Contains trusted IP's: {TRUSTED_IPS}")
    app.run(host='0.0.0.0', port=5100)