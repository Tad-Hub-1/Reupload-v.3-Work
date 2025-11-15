#!/usr/bin/env python3
"""
reupload_server.py
A local HTTP server that listens for requests from a Roblox plugin,
downloads the old asset, re-uploads it, and sends back the new ID.
"""

import os
import sys
import json
import time
import mimetypes
import socketserver
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

try:
    import requests
except Exception:
    print("Please install requests: pip install requests")
    sys.exit(1)

# ----------------- Global Config (will be set at start) -----------------
cfg = {
    "x_api_key": None,
    "roblosecurity": None,
    "download_endpoint": "https://apis.roblox.com/asset-delivery-api/v1/assetId/{assetId}",
    "upload_endpoint": "https://apis.roblox.com/assets/v1/assets"
}

# ----------------- Helpers -----------------
def build_headers():
    headers = { "User-Agent": "AssetReuploaderServer/1.0" }
    if cfg["x_api_key"]:
        headers["x-api-key"] = cfg["x_api_key"]
    if cfg["roblosecurity"]:
        headers["Cookie"] = f".ROBLOSECURITY={cfg['roblosecurity']}"
    return headers

def guess_mime_from_name(name: str):
    t, _ = mimetypes.guess_type(name)
    return t or "application/octet-stream"

# ----------------- Download/Upload -----------------
def download_asset(asset_id):
    url = cfg["download_endpoint"].format(assetId=asset_id)
    headers = build_headers()
    try:
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=True, stream=True)
    except Exception as e:
        return False, f"Request error: {e}"
    if r.status_code >= 400:
        return False, f"Download failed {r.status_code}: {r.text[:400]}"
    
    filename = f"asset_{asset_id}.bin"
    try:
        content = r.content
    except Exception as e:
        return False, f"Failed read content: {e}"
    return True, {"bytes": content, "filename": filename}

def upload_asset(file_bytes, filename, display_name, description, asset_type):
    url = cfg["upload_endpoint"]
    headers = build_headers()
    request_payload = {
        "assetType": asset_type or "Model",
        "displayName": display_name,
        "description": description,
        "creationContext": {}
    }
    files = {
        "request": (None, json.dumps(request_payload), "application/json"),
        "fileContent": (filename, file_bytes, guess_mime_from_name(filename))
    }
    try:
        r = requests.post(url, headers=headers, files=files, timeout=30)
    except Exception as e:
        return False, f"Upload request failed: {e}"
    if r.status_code >= 400:
        return False, f"Upload failed {r.status_code}: {r.text[:1000]}"
    try:
        return True, r.json()
    except Exception:
        return False, f"Upload returned non-json: {r.text[:1000]}"

# ----------------- HTTP Server Handler -----------------
class PluginRequestHandler(BaseHTTPRequestHandler):
    
    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == '/reupload':
            try:
                content_length = int(self.headers['Content-Length'])
                body = self.rfile.read(content_length)
                data = json.loads(body)
                
                old_id = data.get('oldId')
                asset_name = data.get('name')
                asset_type = data.get('type')

                if not old_id or not asset_name or not asset_type:
                    self._send_response(400, {"status": "error", "message": "Missing oldId, name, or type"})
                    return

                print(f"[+] RX: Request to process {asset_type} ID: {old_id} (Name: {asset_name})")

                print(f"  [1/3] Downloading asset {old_id}...")
                dl_ok, dl_data = download_asset(old_id)
                if not dl_ok:
                    print(f"  [!] Download failed: {dl_data}")
                    self._send_response(500, {"status": "error", "message": f"Download failed: {dl_data}"})
                    return

                print(f"  [2/3] Uploading new asset as '{asset_name}'...")
                up_ok, up_res = upload_asset(
                    dl_data["bytes"], 
                    dl_data["filename"], 
                    display_name=asset_name, 
                    description="Re-uploaded via Plugin", 
                    asset_type=asset_type
                )
                
                if not up_ok:
                    print(f"  [!] Upload failed: {up_res}")
                    self._send_response(500, {"status": "error", "message": f"Upload failed: {up_res}"})
                    return

                new_id = None
                if isinstance(up_res, dict):
                    new_id = up_res.get("assetId") or up_res.get("id") or up_res.get("data", {}).get("assetId")

                if not new_id:
                    print(f"  [!] Upload OK, but no new ID found in response: {up_res}")
                    self._send_response(500, {"status": "error", "message": "Upload OK, but no new ID found"})
                    return
                
                print(f"  [3/3] Success! {old_id}  --->  {new_id}")
                
                self._send_response(200, {
                    "status": "success",
                    "oldId": old_id,
                    "newId": new_id
                })

            except Exception as e:
                print(f"[!] Server Error: {e}")
                self._send_response(500, {"status": "error", "message": str(e)})
        else:
            self._send_response(404, {"status": "error", "message": "Not Found"})

    def _send_response(self, http_code, payload_dict):
        try:
            self.send_response(http_code)
            self._send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(payload_dict).encode('utf-8'))
        except Exception as e:
            print(f"Error sending response: {e}")

    def log_message(self, format, *args):
        pass

# ----------------- Main -----------------
def find_free_port(start_port=27000):
    for port in range(start_port, 65535):
        with socketserver.socket.socket(socketserver.AF_INET, socketserver.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                return port
            except OSError:
                continue
    raise IOError("No free ports found")

def main():
    print("--- Roblox Asset Re-uploader Server ---")
    print("Select Authentication Method:")
    print("  1: .ROBLOSECURITY Cookie (Simple, less secure)")
    print("  2: OpenCloud x-api-key (Recommended, more secure)")
    
    auth_choice = ""
    while auth_choice not in ('1', '2'):
        auth_choice = input("Select (1 or 2): ").strip()
        
    if auth_choice == '1':
        cfg["roblosecurity"] = input("Paste your .ROBLOSECURITY Cookie: ").strip()
    else:
        cfg["x_api_key"] = input("Paste your x-api-key: ").strip()
        
    if not cfg["roblosecurity"] and not cfg["x_api_key"]:
        print("No credentials provided, exiting.")
        sys.exit(1)

    try:
        port = find_free_port()
        server_address = ('localhost', port)
        
        with socketserver.TCPServer(server_address, PluginRequestHandler) as httpd:
            httpd.allow_reuse_address = True
            print("\n" + "="*40)
            print(f"✅ Server is running!")
            print(f"📡 Your plugin can connect at:")
            print(f"      http://localhost:{port}")
            print("\n👉 Please copy this Port Number into your Roblox Plugin:")
            print(f"      {port}")
            print("="*40)
            print("\n(Server is running. Press Ctrl+C to stop)")
            
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        print("\n[INFO] Stopping server...")
    except Exception as e:
        print(f"[ERROR] Failed to start server: {e}")
        print("Another program might be using this port, or Antivirus is blocking it.")
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
