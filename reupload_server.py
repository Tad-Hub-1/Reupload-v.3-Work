#!/usr/bin/env python3
"""
reupload_server_v3.py
Combines the Flask server from the user's example with our robust
sequential processing. Includes auth verification, colorama, and 
the (cookie-only) "find existing asset" feature.
"""

import os
import sys
import json
import random
import time
import mimetypes
from pathlib import Path

# --- Imports (ต้องติดตั้ง) ---
try:
    from flask import Flask, request, jsonify
except Exception:
    print("Flask is required. Install: pip install flask requests colorama")
    sys.exit(1)

try:
    import requests
except Exception:
    print("Requests required. Install: pip install flask requests colorama")
    sys.exit(1)

try:
    import colorama
    from colorama import Fore, Style
    colorama.init(autoreset=True) # <-- ทำให้สีกลับมาเป็นปกติอัตโนมัติ
except Exception:
    print("Colorama is recommended for colored output: pip install colorama")
    class DummyFore: __getattr__ = lambda self, name: ""
    Fore = DummyFore()
# --- จบ Imports ---


# --- Config Setup ---
BASE_DIR = Path(__file__).parent if '__file__' in locals() else Path.cwd()
CFG_PATH = BASE_DIR / "reupload_server_config.json"

DEFAULT_CFG = {
    "auth_method": None,
    "roblosecurity": None,
    "x_api_key": None,
    "port": None,
    "user_id": None, # <--- [ใหม่] เก็บ UserID ถ้าใช้ Cookie
    "download_endpoint": "https://apis.roblox.com/asset-delivery-api/v1/assetId/{assetId}",
    "download_fallback": "https://assetdelivery.roblox.com/v1/asset/?id={assetId}",
    "upload_endpoint": "https://apis.roblox.com/assets/v1/assets"
}

# โหลด config หรือสร้างใหม่
if CFG_PATH.exists():
    try:
        cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
        if "user_id" not in cfg: cfg["user_id"] = None
    except Exception:
        cfg = DEFAULT_CFG.copy()
else:
    cfg = DEFAULT_CFG.copy()

# --- Auth & API Helpers ---

def build_headers():
    """ สร้าง Headers สำหรับ API call """
    headers = {"User-Agent": "AssetReuploaderServer/V3"}
    if cfg.get("auth_method") == "x_api_key" and cfg.get("x_api_key"):
        headers["x-api-key"] = cfg["x_api_key"]
    if cfg.get("auth_method") == "roblosecurity" and cfg.get("roblosecurity"):
        headers["Cookie"] = f".ROBLOSECURITY={cfg['roblosecurity']}"
    return headers

def verify_auth():
    """ [ใหม่] ตรวจสอบว่า Key/Cookie ใช้งานได้จริง """
    headers = build_headers()
    print("[INFO] Checking authentication validity...")

    try:  
        if cfg["auth_method"] == "roblosecurity":  
            # ตรวจสอบ Cookie โดยการดึงข้อมูลผู้ใช้
            r = requests.get("https://users.roblox.com/v1/users/authenticated", headers=headers, timeout=10)  
            if r.status_code == 200:
                user_json = r.json()
                user = user_json.get("name", "?")
                user_id = user_json.get("id")
                if not user_id:
                    print(Fore.RED + f"[ERR] .ROBLOSECURITY valid, but could not retrieve user ID.")
                    return False
                cfg['user_id'] = user_id # <--- เก็บ UserID ไว้ใช้ค้นหา
                print(Fore.GREEN + f"[OK] .ROBLOSECURITY valid (Logged in as {user}, ID: {user_id})")  
                return True  
            else:  
                print(Fore.RED + f"[ERR] Invalid .ROBLOSECURITY cookie (HTTP {r.status_code})")  
                return False  
        elif cfg["auth_method"] == "x_api_key":  
            # ตรวจสอบ API Key โดยการพยายาม List Universes
            cfg['user_id'] = None # API Key ไม่สามารถใช้ UserID ได้
            r = requests.get("https://apis.roblox.com/cloud/v2/universes", headers=headers, timeout=10)  
            if r.status_code == 200: # 200 = OK
                print(Fore.GREEN + f"[OK] x-api-key appears valid (HTTP {r.status_code})")  
                return True
            elif r.status_code == 401: # 401 = Unauthorized
                print(Fore.RED + f"[ERR] Invalid x-api-key (HTTP {r.status_code})")  
                return False
            else: # 403, 404, ฯลฯ แปลว่า Key ถูก แต่แค่ไม่มีสิทธิ์ (ซึ่ง OK)
                print(Fore.GREEN + f"[OK] x-api-key is valid, but may lack permissions (HTTP {r.status_code})")
                return True
        else:  
            print(Fore.RED + "[ERR] Unknown auth method.")  
            return False  
    except Exception as e:  
        print(Fore.RED + f"[ERR] Auth check failed: {e}")  
        return False

def cli_setup():
    """ [ใหม่] หน้าจอ Setup ที่ถาม 1 หรือ 2 """
    print("--- Roblox Asset Re-uploader Server V3 ---")
    
    # ถ้าใน config มี key/cookie อยู่แล้ว ถามว่าจะใช้ซ้ำไหม
    if (cfg.get("roblosecurity") or cfg.get("x_api_key")) and cfg.get("port"):
        print(f"[INFO] Found saved config for method: {cfg.get('auth_method')}")
        use_saved = input("Use saved credentials? (Y/n): ").strip().lower()
        if use_saved in ('y', 'yes', ''):
            if verify_auth():
                return # ใช้ของเก่าได้เลย
            else:
                print("[WARN] Saved credentials failed verification. Please re-enter.")

    print("Select Authentication Method:")
    print("  1: .ROBLOSECURITY Cookie (Can check for existing assets)")
    print("  2: OpenCloud x-api-key (Cannot check for existing assets)")
    
    choice = ""
    while choice not in ("1", "2"):
        choice = input("Choice (1/2): ").strip()
        
    if choice == "1":  
        cfg["auth_method"] = "roblosecurity"  
        cfg["x_api_key"] = None
        cfg["roblosecurity"] = input("Paste your .ROBLOSECURITY Cookie: ").strip()  
    else:  
        cfg["auth_method"] = "x_api_key"  
        cfg["roblosecurity"] = None
        cfg["user_id"] = None
        cfg["x_api_key"] = input("Paste your x-api-key (OpenCloud): ").strip()  
    
    suggested = random.randint(27000, 40000)  
    p = input(f"Enter port to run server on (or press Enter to use {suggested}): ").strip()  
    try:  
        cfg["port"] = int(p) if p else suggested  
    except:  
        cfg["port"] = suggested  
        
    print("\n[STEP] Verifying credentials...")  
    if not verify_auth():  
        print(Fore.RED + "[FATAL] Authentication failed. Please check your credentials.")  
        sys.exit(1)  
        
    CFG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")  
    print(Fore.GREEN + f"[OK] Auth verified successfully.")  
    print(f"[INFO] Config saved to {CFG_PATH} for next time.")  
    print(f"[INFO] Server will listen on http://localhost:{cfg['port']}\n")

def guess_mime(filename):
    t,_ = mimetypes.guess_type(filename)
    return t or "application/octet-stream"

# --- Main Re-upload Logic ---

def print_success_location(newId):
    """ [ใหม่] พิมพ์ Link สีเขียว หลังอัปโหลดเสร็จ """
    dashboard_url = ""
    if cfg.get("auth_method") == "roblosecurity":
        # ถ้าใช้ Cookie, มันจะไปที่ "My Creations"
        dashboard_url = f"https://create.roblox.com/dashboard/creations/configure?id={newId}"
    else:
        # ถ้าใช้ API Key, มันจะไปที่ "Group Creations" หรือหน้า Asset
        dashboard_url = f"https://www.roblox.com/library/{newId}/"
    
    print(Fore.GREEN + f"    -> Asset is ready. Configure it at: {dashboard_url}")


def find_existing_asset(displayName, assetType):
    """ [ใหม่] ค้นหา Asset ที่มีอยู่ (เฉพาะ Cookie) """
    if cfg.get("auth_method") != "roblosecurity" or not cfg.get("user_id"):
        return False, None # ทำงานเฉพาะเมื่อใช้ Cookie และมี UserID
        
    userId = cfg["user_id"]
    headers = build_headers()
    cursor = ""
    url_template = f"https://economy.roblox.com/v2/users/{userId}/assets/creations?assetTypes={assetType}&limit=100"
    
    print(f"    [?] Checking inventory for '{displayName}'...")
    
    while True: 
        url = url_template
        if cursor:
            url += f"&cursor={cursor}"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                print(Fore.YELLOW + f"    [WARN] Inventory check failed (HTTP {r.status_code}). Skipping check.")
                return False, None
            data = r.json()
            if not data.get("data"):
                return False, None 
            
            for item in data["data"]:
                if item.get("name") == displayName:
                    asset_id = item.get("assetId")
                    if asset_id:
                        print(Fore.CYAN + f"    [OK] Found matching asset: {displayName} -> {asset_id}")
                        return True, asset_id
                        
            cursor = data.get("nextPageCursor")
            if not cursor:
                break # ไม่เจอ และไม่มีหน้าถัดไป
        except Exception as e:
            print(Fore.YELLOW + f"    [WARN] Inventory check error: {e}. Skipping check.")
            return False, None
    return False, None # ไม่เจอ

def download_asset(asset_id):
    """ ดาวน์โหลด Asset (เหมือนเดิม) """
    url = cfg["download_endpoint"].format(assetId=asset_id)
    headers = build_headers()
    try:
        r = requests.get(url, headers=headers, timeout=15)
    except Exception as e:
        return False, f"Download error: {e}"
    
    if r.status_code >= 400:
        # ถ้าล้มเหลว, ลอง Fallback URL
        fb = cfg["download_fallback"].format(assetId=asset_id)
        try:
            r2 = requests.get(fb, headers=headers, timeout=10)
            if r2.status_code >= 400:
                return False, f"Download failed {r.status_code} + fallback {r2.status_code}"
            r = r2
        except Exception as e:
            return False, f"Primary download failed {r.status_code}, fallback error: {e}"
            
    return True, {"bytes": r.content, "filename": f"asset_{asset_id}.bin"}

def upload_asset(file_bytes, filename, displayName, assetType):
    """ อัปโหลด Asset (เหมือนเดิม) """
    url = cfg["upload_endpoint"]
    headers = build_headers()
    request_payload = {
        "assetType": assetType,
        "displayName": displayName,
        "description": f"Re-uploaded via Plugin at {time.ctime()}",
        "creationContext": {}
    }
    files = {
        "request": (None, json.dumps(request_payload), "application/json"),
        "fileContent": (filename, file_bytes, guess_mime(filename))
    }
    try:
        r = requests.post(url, headers=headers, files=files, timeout=30)
    except Exception as e:
        return False, f"Upload request failed: {e}"
        
    if r.status_code >= 400:
        return False, f"Upload failed {r.status_code}: {r.text[:300]}"
    return True, r.json()


def process_single(item):
    """
    [อัปเกรด] Process Asset 1 ชิ้น
    นี่คือ Logic หลักที่ Server ทำงาน
    """
    oldId = item.get("oldId")
    name = item.get("name", f"item_{oldId}")
    assetType = item.get("type", "Animation")
    check_existing = item.get("check_existing", False) # <--- [ใหม่] รับค่าจาก Plugin
    
    print(Fore.CYAN + f"[+] RX: Request to process {assetType} ID: {oldId} (Name: {name})")
    
    # --- [ใหม่] ตรวจสอบของเก่า ---
    if check_existing:
        found, existing_id = find_existing_asset(name, assetType)
        if found:
            print(Fore.CYAN + f"    [SKIP] Using existing asset {existing_id} for '{name}'.")
            print_success_location(existing_id)
            return {"oldId": oldId, "newId": existing_id, "status": "ok", "skipped": True}
    else:
        print("    [INFO] 'Check Existing' is OFF. Proceeding to re-upload.")
    # --- จบส่วนตรวจสอบ ---

    print(f"    [1/3] Downloading original asset {oldId}...")
    ok, data = download_asset(oldId)
    if not ok:
        print(Fore.RED + f"    [ERR] Download failed for {oldId}: {data}")
        return {"oldId": oldId, "status": "download_failed", "error": data, "name": name}
        
    print(f"    [2/3] Uploading new asset as '{name}'...")
    ok2, res = upload_asset(data["bytes"], data["filename"], name, assetType)
    
    if not ok2:
        print(Fore.RED + f"    [ERR] Upload failed for {oldId}: {res}")
        return {"oldId": oldId, "status": "upload_failed", "error": res, "name": name}
    
    newId = res.get("assetId")
    if not newId:
        print(Fore.RED + f"    [ERR] Upload succeeded but no assetId found for {oldId}.")
        return {"oldId": oldId, "status": "upload_failed", "error": "No assetId in response", "name": name}

    print(Fore.GREEN + f"    [3/3] Re-upload success: {oldId}  --->  {newId}")
    print_success_location(newId) # <--- [ใหม่] พิมพ์ Link สีเขียว
    return {"oldId": oldId, "newId": newId, "status": "ok", "name": name}

# --- Flask Server ---
app = Flask("asset_reupload_server_v3")

@app.route("/api/reupload_single", methods=["POST", "OPTIONS"])
def api_reupload_single():
    """ นี่คือ Endpoint ที่ Plugin จะเรียก """
    if request.method == "OPTIONS":
        return _build_cors_preflight_response()
        
    payload = request.get_json(force=True, silent=True)
    if not payload or "oldId" not in payload:
        return _corsify_actual_response(jsonify({"error": "Invalid payload, missing oldId"}), 400)
    
    # เรียก Logic หลัก
    result = process_single(payload)
    
    return _corsify_actual_response(jsonify(result))

@app.route("/api/ping", methods=["GET", "OPTIONS"])
def ping():
    if request.method == "OPTIONS":
        return _build_cors_preflight_response()
    return _corsify_actual_response(jsonify({"pong": True, "auth_method": cfg.get("auth_method")}))

# --- [ใหม่] Flask CORS Helpers ---
# (จำเป็นสำหรับ Flask Server)
def _build_cors_preflight_response():
    response = jsonify({"status": "ok"})
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add('Access-Control-Allow-Headers', "*")
    response.headers.add('Access-Control-Allow-Methods', "*")
    return response

def _corsify_actual_response(response, status_code=200):
    response.headers.add("Access-Control-Allow-Origin", "*")
    return response, status_code

# --- Main ---
if __name__ == "__main__":
    cli_setup() # <--- [ใหม่] รัน Setup ก่อน
    port = int(cfg.get("port", 27000))
    print("="*40)
    print(Fore.GREEN + f"✅ Server is running!")
    print(f"📡 Plugin can connect at: http://localhost:{port}")
    print(Fore.YELLOW + f"👉 Port Number for Plugin: {port}")
    print("="*40)
    print("\n(Server is running. Press Ctrl+C to stop)")
    try:
        app.run(host="0.0.0.0", port=port, threaded=True)
    except Exception as e:
        print(Fore.RED + f"[FATAL] Failed to start Flask server: {e}")
        input("Press Enter to exit...")
