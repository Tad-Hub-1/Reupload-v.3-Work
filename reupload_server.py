#!/usr/bin/env python3
"""
reupload_server_v4_1.py
Keyframe Reconstruction Mode.
อัปเดต: ตั้งชื่อ Asset และ KeyframeSequence ให้ตรงกับต้นฉบับ
"""

import os
import sys
import json
import time
from pathlib import Path

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
    colorama.init(autoreset=True)
except Exception:
    class DummyFore: __getattr__ = lambda self, name: ""
    Fore = DummyFore()

# --- Config ---
BASE_DIR = Path(__file__).parent if '__file__' in locals() else Path.cwd()
CFG_PATH = BASE_DIR / "reupload_server_config.json"

DEFAULT_CFG = {
    "auth_method": None,
    "roblosecurity": None,
    "x_api_key": None,
    "port": None,
    "user_id": None,
    "upload_endpoint": "https://apis.roblox.com/assets/v1/assets"
}

if CFG_PATH.exists():
    try:
        cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    except:
        cfg = DEFAULT_CFG.copy()
else:
    cfg = DEFAULT_CFG.copy()

# --- Helpers ---
def build_headers():
    headers = {"User-Agent": "AssetReuploaderServer/V4"}
    if cfg.get("auth_method") == "x_api_key" and cfg.get("x_api_key"):
        headers["x-api-key"] = cfg["x_api_key"]
    if cfg.get("auth_method") == "roblosecurity" and cfg.get("roblosecurity"):
        headers["Cookie"] = f".ROBLOSECURITY={cfg['roblosecurity']}"
    return headers

def verify_auth():
    headers = build_headers()
    print("[INFO] Checking authentication validity...")
    try:  
        if cfg["auth_method"] == "roblosecurity":  
            r = requests.get("https://users.roblox.com/v1/users/authenticated", headers=headers, timeout=10)  
            if r.status_code == 200:
                user_id = r.json().get("id")
                cfg['user_id'] = user_id
                print(Fore.GREEN + f"[OK] .ROBLOSECURITY valid (ID: {user_id})")  
                return True  
            else:  
                print(Fore.RED + f"[ERR] Invalid .ROBLOSECURITY (HTTP {r.status_code})")  
                return False  
        elif cfg["auth_method"] == "x_api_key":  
            r = requests.get("https://apis.roblox.com/cloud/v2/universes", headers=headers, timeout=10)  
            if r.status_code in (200, 403, 404):
                print(Fore.GREEN + f"[OK] x-api-key valid")  
                return True
            else:  
                print(Fore.RED + f"[ERR] Invalid x-api-key (HTTP {r.status_code})")  
                return False
        return False  
    except Exception as e:  
        print(Fore.RED + f"[ERR] Auth check failed: {e}")  
        return False

def cli_setup():
    if (cfg.get("roblosecurity") or cfg.get("x_api_key")) and cfg.get("port"):
        if verify_auth(): return

    print("Select Authentication Method:")
    print("  1: .ROBLOSECURITY Cookie")
    print("  2: OpenCloud x-api-key")
    choice = input("Choice (1/2): ").strip()
    
    if choice == "1":  
        cfg["auth_method"] = "roblosecurity"  
        cfg["roblosecurity"] = input("Paste Cookie: ").strip()  
    else:  
        cfg["auth_method"] = "x_api_key"  
        cfg["x_api_key"] = input("Paste x-api-key: ").strip()  
    
    cfg["port"] = 27000
    
    if not verify_auth():  
        print(Fore.RED + "[FATAL] Auth failed.")
        sys.exit(1)  
    CFG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def print_success(newId, oldId, name):
    url = f"https://create.roblox.com/dashboard/creations/configure?id={newId}"
    print(Fore.GREEN + f"    -> [SUCCESS] {name}")
    print(Fore.GREEN + f"       Map: {oldId} --> {newId}")
    print(Fore.CYAN  + f"       URL: {url}")

def upload_asset(file_bytes, filename, displayName, assetType):
    url = cfg["upload_endpoint"]
    headers = build_headers()
    req = {
        "assetType": assetType,
        "displayName": displayName,
        "description": "Reconstructed via Plugin V4",
        "creationContext": {}
    }
    files = {
        "request": (None, json.dumps(req), "application/json"),
        "fileContent": (filename, file_bytes, "application/xml")
    }
    r = requests.post(url, headers=headers, files=files, timeout=30)
    if r.status_code >= 400:
        return False, f"Upload failed {r.status_code}: {r.text[:300]}"
    return True, r.json()

# ========================================================
# [[  XML BUILDER  ]]
# ========================================================
def build_rbxmx(kfs_data, asset_name):
    """
    สร้างไฟล์ .rbxmx โดยใช้ชื่อ Asset ที่กำหนด
    """
    # ใช้ชื่อที่ส่งมา ใส่เข้าไปใน Property "Name" ของ KeyframeSequence
    xml = [
        '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">',
        '<External>null</External>',
        '<External>nil</External>',
        '<Item class="KeyframeSequence" referent="RBX0">',
        '<Properties>',
        f'<string name="Name">{asset_name}</string>', # <--- ใช้ชื่อที่ส่งมา
        f'<bool name="Loop">{"true" if kfs_data.get("Loop") else "false"}</bool>',
        f'<token name="Priority">{kfs_data.get("Priority", 2)}</token>',
        '</Properties>'
    ]

    for kf in kfs_data.get("Keyframes", []):
        xml.append('<Item class="Keyframe" referent="RBX_KF">')
        xml.append('<Properties>')
        xml.append(f'<string name="Name">{kf["Name"]}</string>')
        xml.append(f'<float name="Time">{kf["Time"]}</float>')
        xml.append('</Properties>')
        
        for pose in kf.get("Poses", []):
            xml.append(build_pose_xml(pose))
            
        xml.append('</Item>')

    xml.append('</Item>')
    xml.append('</roblox>')
    
    return "".join(xml).encode('utf-8')

def build_pose_xml(pose):
    cf = pose.get("CFrame", [0]*12)
    style = pose.get("EasingStyle", 0)
    dir = pose.get("EasingDirection", 0)
    
    p_xml = [
        '<Item class="Pose" referent="RBX_POSE">',
        '<Properties>',
        f'<string name="Name">{pose["Name"]}</string>',
        f'<float name="Weight">{pose.get("Weight", 1)}</float>',
        f'<token name="EasingStyle">{style}</token>',
        f'<token name="EasingDirection">{dir}</token>',
        '<CoordinateFrame name="CFrame">',
        f'<X>{cf[0]}</X><Y>{cf[1]}</Y><Z>{cf[2]}</Z>',
        f'<R00>{cf[3]}</R00><R01>{cf[4]}</R01><R02>{cf[5]}</R02>',
        f'<R10>{cf[6]}</R10><R11>{cf[7]}</R11><R12>{cf[8]}</R12>',
        f'<R20>{cf[9]}</R20><R21>{cf[10]}</R21><R22>{cf[11]}</R22>',
        '</CoordinateFrame>',
        '</Properties>'
    ]
    for sub in pose.get("SubPoses", []):
        p_xml.append(build_pose_xml(sub))
    p_xml.append('</Item>')
    return "".join(p_xml)

# --- Routes ---
app = Flask("reupload_v4")

@app.route("/api/reupload_data", methods=["POST", "OPTIONS"])
def api_reupload_data():
    if request.method == "OPTIONS":
        return _cors_resp()
        
    data = request.get_json(force=True, silent=True)
    if not data or "kfsData" not in data:
        return _cors_resp(jsonify({"error": "Missing kfsData"}), 400)
    
    oldId = data.get("oldId")
    name = data.get("name") # ชื่อที่ Plugin ส่งมา (เช่น "Run")
    kfsData = data.get("kfsData")
    
    print(Fore.CYAN + f"[+] Processing: {name} (Original ID: {oldId})")
    
    # 1. สร้างไฟล์โดยใช้ชื่อที่ถูกต้อง
    try:
        file_bytes = build_rbxmx(kfsData, name) # ส่ง name เข้าไปใน XML
    except Exception as e:
        print(Fore.RED + f"    [ERR] XML Build failed: {e}")
        return _cors_resp(jsonify({"error": f"Build failed: {e}"}), 500)
        
    # 2. อัปโหลดโดยใช้ชื่อที่ถูกต้อง
    print(f"    [..] Uploading as '{name}'...")
    ok, res = upload_asset(file_bytes, f"{name}.rbxmx", name, "Animation")
    
    if not ok:
        print(Fore.RED + f"    [ERR] Upload failed: {res}")
        return _cors_resp(jsonify({"error": res}), 500)
        
    newId = res.get("assetId")
    if not newId:
        return _cors_resp(jsonify({"error": "No assetId returned"}), 500)
        
    print_success(newId, oldId, name)
    # ส่งข้อมูลกลับไปให้ Plugin เพื่อทำการแทนที่ (Replace)
    return _cors_resp(jsonify({"status": "ok", "newId": newId, "oldId": oldId}))

def _cors_resp(resp=None, code=200):
    if resp is None: resp = jsonify({"status":"ok"})
    resp.headers.add("Access-Control-Allow-Origin", "*")
    resp.headers.add("Access-Control-Allow-Headers", "*")
    return resp, code

if __name__ == "__main__":
    cli_setup()
    print("="*40)
    print(Fore.GREEN + f"✅ V4.1 Server (Keyframe Mode) Ready!")
    print(f"📡 Port: {cfg['port']}")
    print("="*40)
    app.run(host="0.0.0.0", port=cfg['port'])
