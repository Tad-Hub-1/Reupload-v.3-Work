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

# ----------------- Global Config (จะถูกตั้งค่าตอนเริ่ม) -----------------
cfg = {
    "x_api_key": None,
    "roblosecurity": None,
    "download_endpoint": "https://apis.roblox.com/asset-delivery-api/v1/assetId/{assetId}",
    "upload_endpoint": "https://apis.roblox.com/assets/v1/assets"
}

# ----------------- Helpers (เหมือนเดิม) -----------------
def build_headers():
    headers = { "User-Agent": "AssetReuploaderServer/1.0" }
    # ใช้ Config ที่ตั้งไว้ตอนเริ่ม
    if cfg["x_api_key"]:
        headers["x-api-key"] = cfg["x_api_key"]
    if cfg["roblosecurity"]:
        headers["Cookie"] = f".ROBLOSECURITY={cfg['roblosecurity']}"
    return headers

def guess_mime_from_name(name: str):
    t, _ = mimetypes.guess_type(name)
    return t or "application/octet-stream"

# ----------------- Download/Upload (เหมือนเดิม) -----------------
def download_asset(asset_id):
    url = cfg["download_endpoint"].format(assetId=asset_id)
    headers = build_headers()
    try:
        r = requests.get(url, headers=headers, timeout=15, allow_redirects=True, stream=True)
    except Exception as e:
        return False, f"Request error: {e}"
    if r.status_code >= 400:
        return False, f"Download failed {r.status_code}: {r.text[:400]}"
    
    filename = f"asset_{asset_id}.bin" # ชื่อไฟล์ไม่สำคัญมากสำหรับ server
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
        """ ส่ง Headers เพื่อให้ Roblox Studio (localhost) คุยได้ """
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        """ ตอบกลับ OPTIONS (pre-flight) request """
        self.send_response(204) # No Content
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        """ จัดการ Request ที่ Plugin ส่งมา """
        if self.path == '/reupload':
            try:
                # 1. อ่านข้อมูล (Body) ที่ Plugin ส่งมา
                content_length = int(self.headers['Content-Length'])
                body = self.rfile.read(content_length)
                data = json.loads(body)
                
                old_id = data.get('oldId')
                asset_name = data.get('name')
                asset_type = data.get('type') # 'Animation' หรือ 'Sound'

                if not old_id or not asset_name or not asset_type:
                    self._send_response(400, {"status": "error", "message": "Missing oldId, name, or type"})
                    return

                print(f"[+] RX: Request to process {asset_type} ID: {old_id} (Name: {asset_name})")

                # 2. ดาวน์โหลด Asset เก่า
                print(f"  [1/3] Downloading asset {old_id}...")
                dl_ok, dl_data = download_asset(old_id)
                if not dl_ok:
                    print(f"  [!] Download failed: {dl_data}")
                    self._send_response(500, {"status": "error", "message": f"Download failed: {dl_data}"})
                    return

                print(f"  [2/3] Uploading new asset as '{asset_name}'...")
                # 3. อัปโหลด Asset ใหม่
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

                # 4. ค้นหา ID ใหม่ในผลลัพธ์
                new_id = None
                if isinstance(up_res, dict):
                    new_id = up_res.get("assetId") or up_res.get("id") or up_res.get("data", {}).get("assetId")

                if not new_id:
                    print(f"  [!] Upload OK, but no new ID found in response: {up_res}")
                    self._send_response(500, {"status": "error", "message": "Upload OK, but no new ID found"})
                    return
                
                print(f"  [3/3] Success! {old_id}  --->  {new_id}")
                
                # 5. ส่ง ID ใหม่กลับไปให้ Plugin
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
        """ ส่ง JSON response กลับไปหา Plugin """
        try:
            self.send_response(http_code)
            self._send_cors_headers()
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(payload_dict).encode('utf-8'))
        except Exception as e:
            print(f"Error sending response: {e}")

    def log_message(self, format, *args):
        """ ปิด log ของ server ที่รกๆ (เช่น GET /... 200) """
        pass

# ----------------- Main -----------------
def find_free_port(start_port=27000):
    """ หา Port ว่างๆ ตั้งแต่ 27000 ขึ้นไป """
    for port in range(start_port, 65535):
        with socketserver.socket.socket(socketserver.AF_INET, socketserver.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                return port
            except OSError:
                continue # Port ไม่ว่าง
    raise IOError("No free ports found")

def main():
    print("--- Roblox Asset Re-uploader Server ---")
    print("เลือกวิธียืนยันตัวตน:")
    print("  1: .ROBLOSECURITY Cookie (ง่าย, ไม่ปลอดภัย)")
    print("  2: OpenCloud x-api-key (แนะนำ, ปลอดภัยกว่า)")
    
    auth_choice = ""
    while auth_choice not in ('1', '2'):
        auth_choice = input("เลือก (1 หรือ 2): ").strip()
        
    if auth_choice == '1':
        cfg["roblosecurity"] = input("วาง .ROBLOSECURITY Cookie ของคุณ: ").strip()
    else:
        cfg["x_api_key"] = input("วาง x-api-key ของคุณ: ").strip()
        
    if not cfg["roblosecurity"] and not cfg["x_api_key"]:
        print("ไม่ได้ป้อนข้อมูลยืนยันตัวตน, ออกจากโปรแกรม")
        sys.exit(1)

    try:
        port = find_free_port()
        server_address = ('localhost', port)
        
        # ตั้งค่า Server
        with socketserver.TCPServer(server_address, PluginRequestHandler) as httpd:
            httpd.allow_reuse_address = True
            print("\n" + "="*40)
            print(f"✅ Server พร้อมทำงานแล้ว!")
            print(f"📡 Plugin ของคุณสามารถเชื่อมต่อได้ที่:")
            print(f"      http://localhost:{port}")
            print("\n👉 กรุณาคัดลอก Port Number ต่อไปนี้ไปใส่ใน Roblox Plugin:")
            print(f"      {port}")
            print("="*40)
            print("\n(Server นี้จะทำงานไปเรื่อยๆ, กด Ctrl+C เพื่อปิด)")
            
            # เริ่ม Server
            httpd.serve_forever()
            
    except KeyboardInterrupt:
        print("\n[INFO] ปิด Server...")
    except Exception as e:
        print(f"[ERROR] ไม่สามารถเริ่ม Server: {e}")
        print("อาจมีโปรแกรมอื่นใช้ Port นี้อยู่ หรือ Antivirus บล็อกไว้")
        input("กด Enter เพื่อปิด...")

if __name__ == "__main__":
    main()
