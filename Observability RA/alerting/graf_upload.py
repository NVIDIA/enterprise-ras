# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT

import requests
import yaml
import glob
import os
import json
from pathlib import Path

def load_config(filepath="config.yaml"):
    with open(filepath, "r") as f:
        return yaml.safe_load(f)

def list_json_files(cfg):
    files = set(cfg.get("json_files", []))
    if "json_folder" in cfg:
        folder = Path(cfg["json_folder"])
        files.update(str(f) for f in folder.glob("*.json"))
    return list(files)

def inject_folder_uid(data, folder_uid):
    try:
        alert_data = json.loads(data)
    except Exception as e:
        raise Exception(f"Invalid JSON: {e}")
    alert_data["folderUID"] = folder_uid
    return json.dumps(alert_data, indent=2)

def get_existing_rules(grafana_url, api_token):
    url = f"{grafana_url}/grafana/api/v1/provisioning/alert-rules"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    # Suppress SSL warnings if verify=False
    try:
        resp = requests.get(url, headers=headers, verify=False)
        items = resp.json()
        # API returns a dict with an "items" list
        if isinstance(items, dict) and "items" in items:
            return items["items"]
        if isinstance(items, list):
            return items
        return []
    except Exception:
        return []

def check_alert_exists(existing_rules, title, folderUID):
    for rule in existing_rules:
        # folderUID might be missing if rule in General folder
        if rule.get("title") == title and rule.get("folderUID") == folderUID:
            return True
    return False

def upload_alert(grafana_url, api_token, json_path, disable_prov=True, folder_uid=None):
    url = f"{grafana_url}/grafana/api/v1/provisioning/alert-rules"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    if disable_prov:
        headers["X-Disable-Provenance"] = "true"
    with open(json_path, "r") as f:
        data = f.read()
    if folder_uid:
        data = inject_folder_uid(data, folder_uid)
    r = requests.post(url, headers=headers, data=data, verify=False)
    try:
        resp = r.json()
    except Exception:
        resp = {"raw_response": r.text}
    success = r.status_code < 300 and "id" in resp
    return success, resp

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Batch upload Grafana alert rule JSON files, skipping if the rule exists."
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to YAML config file (default: config.yaml)"
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    grafana_url = cfg["grafana_url"]
    api_token = cfg["api_token"]
    disable_prov = cfg.get("disable_provenance", True)
    default_folder_uid = cfg.get("default_folder_uid", None)
    files = list_json_files(cfg)

    print(f"\nChecking existing Grafana alert rules ...")
    existing_rules = get_existing_rules(grafana_url, api_token)

    print(f"\nUploading {len(files)} alert JSON files to {grafana_url}/grafana/api/v1/provisioning/alert-rules ...\n")

    for json_path in files:
        if not os.path.exists(json_path):
            print(f"❌ File '{json_path}' not found! Skipping.")
            continue
        try:
            with open(json_path, "r") as f:
                data = f.read()
            alert_data = json.loads(data)
        except Exception as e:
            print(f"❌ Error reading '{json_path}': {e}. Skipping.")
            continue

        # Use config default_folder_uid if needed
        folder_uid = default_folder_uid
        if folder_uid:
            alert_data['folderUID'] = folder_uid
        else:
            folder_uid = alert_data.get('folderUID')

        title = alert_data.get('title', '<No Title>')
        if check_alert_exists(existing_rules, title, folder_uid):
            print(f"SKIPPED '{json_path}': Alert rule '{title}' already exists in folder '{folder_uid}'.")
            continue

        print(f"Uploading: {json_path} ... ", end="")
        try:
            # Save possibly updated folderUID before upload
            data_to_upload = json.dumps(alert_data, indent=2)
            success, resp = upload_alert(
                grafana_url,
                api_token,
                json_path,  # still pass original, since upload_alert will read and inject if needed
                disable_prov,
                folder_uid=folder_uid
            )
            if success:
                print(f"\033[92mSUCCESS\033[0m (rule id: {resp.get('id')}, uid: {resp.get('uid')})")
                # Update cache of existing rules so future files in the same run aren't re-uploaded on duplicate
                existing_rules.append({
                    'title': title,
                    'folderUID': folder_uid
                })
            else:
                msg = resp.get("message") or str(resp)
                print(f"\033[91mFAILED\033[0m: {msg}")
        except Exception as e:
            print(f"\033[91mFAILED\033[0m: {e}")

if __name__ == "__main__":
    main()

