# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: MIT
"""
`status_page_enabled: false` means the dashboard and reports are not served
(ADR-0091, MR !314 review), checked over HTTP against a real nginx.

The shipped nginx-ztp.conf.j2 is rendered by Ansible's template module, its
absolute paths and port are pointed at a temp dir, and nginx serves it as the
current user. Requests come from 127.0.0.3 (an allowed provisioning subnet)
and 127.0.0.2 (not allowed). Covers a fresh disabled install, a disabled
install that still holds an earlier enabled install's dashboard/reports, and
an enabled install. The cleanup tasks of both deployment paths
(`setup-status-page.yml`, which also runs for NOZTP=1, and the ZTP-server
role) are executed with ansible-playbook.
"""
import base64
import http.client
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "roles" / "ztp-server" / "templates" / "nginx-ztp.conf.j2"
ROLE_TASKS = REPO / "roles" / "ztp-server" / "tasks" / "main.yml"
PLAYBOOK = REPO / "playbooks" / "setup-status-page.yml"
CLEANUP = "Remove the dashboard and status-page credentials when the status page is disabled (ADR-0091)"
RENDER = {PLAYBOOK: "Render status page", ROLE_TASKS: "Create ZTP status page"}
USER = "era"
PASSWORD = "St@tus-Pag3-Dedicated"  # pragma: allowlist secret
ALLOWED, OTHER = "127.0.0.3", "127.0.0.2"
OPERATOR_PATHS = ["/", "/index.html", "/reports/", "/reports/ztp-report.txt",
                  "/licenses/", "/licenses/license.txt", "/images/", "/images/fw.bin", "/topology/"]
ZTP_PATHS = ["/scripts/ztp.sh", "/configs/leaf01-config.sh", "/authorized_keys"]


def _nginx():
    found = shutil.which("nginx") or next(
        (p for p in ("/usr/sbin/nginx", "/usr/local/sbin/nginx") if os.access(p, os.X_OK)), None)
    if found and shutil.which("ansible-playbook"):
        return found
    if os.environ.get("CI"):
        pytest.fail("nginx / ansible-playbook missing in CI -- the HTTP check would silently no-op")
    pytest.skip("nginx and ansible-playbook required")


def _ansible(tmp_path, tasks, play_vars):
    play = [{"hosts": "localhost", "gather_facts": False, "connection": "local",
             "vars": play_vars, "tasks": tasks}]
    pb = tmp_path / f"play-{time.monotonic_ns()}.yml"
    pb.write_text(yaml.safe_dump(play, sort_keys=False))
    r = subprocess.run(["ansible-playbook", "-i", "localhost,", str(pb)],
                       capture_output=True, text=True, cwd=tmp_path)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    return r


def _web_root(tmp_path, leftovers):
    root = tmp_path / "www"
    for rel, body in {"scripts/ztp.sh": "#!/bin/bash\n# ztp\n",
                      "configs/leaf01-config.sh": "#!/bin/bash\n# leaf01\n",
                      "authorized_keys": "ssh-ed25519 AAAA synthetic\n"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(body)
    for d in ("reports", "licenses", "images", "topology"):
        (root / d).mkdir(exist_ok=True)
    if leftovers:
        (root / "index.html").write_text("<html>ERA dashboard</html>\n")
        (root / "reports" / "ztp-report.txt").write_text("report\n")
        (root / "licenses" / "license.txt").write_text("license\n")
        (root / "images" / "fw.bin").write_text("fw\n")
    return root


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _site(tmp_path, enabled, root):
    """Render the real template with Ansible, then point it at tmp_path."""
    rendered = tmp_path / "site.conf"
    _ansible(tmp_path, [{"template": {"src": str(TEMPLATE), "dest": str(rendered)}}],
             {"status_page_enabled": enabled, "ztp_allow_subnets": [f"{ALLOWED}/32"]})
    text = rendered.read_text()
    port = _free_port()
    htpasswd = tmp_path / "htpasswd"
    logs = tmp_path / "logs"
    logs.mkdir()
    for old, new in [("listen 80 default_server;", f"listen 127.0.0.1:{port} default_server;"),
                     ("listen [::]:80 default_server;", ""),
                     ("/etc/nginx/.htpasswd", str(htpasswd)),
                     ("/var/www/ztp", str(root)),
                     ("/var/log/nginx/", f"{logs}/")]:
        assert (old in text) or (old == "/etc/nginx/.htpasswd" and not enabled), old
        text = text.replace(old, new)
    assert ("auth_basic_user_file" in text) is enabled
    rendered.write_text(text)
    hashed = subprocess.run(["openssl", "passwd", "-5", "-stdin"], input=PASSWORD,
                            capture_output=True, text=True, check=True).stdout.strip()
    htpasswd.write_text(f"{USER}:{hashed}\n")
    return rendered, port


@pytest.fixture
def serve(tmp_path):
    procs = []

    def start(enabled, leftovers):
        nginx = _nginx()
        root = _web_root(tmp_path, leftovers)
        site, port = _site(tmp_path, enabled, root)
        for d in ("body", "proxy", "fastcgi", "uwsgi", "scgi"):
            (tmp_path / "temp" / d).mkdir(parents=True, exist_ok=True)
        conf = tmp_path / "nginx.conf"
        conf.write_text(
            # As root (CI containers) workers would drop to `nobody`, which cannot read tmp_path.
            ("user root;\n" if os.geteuid() == 0 else "")
            + f"worker_processes 1;\nerror_log {tmp_path}/error.log;\npid {tmp_path}/nginx.pid;\n"
            "events {}\nhttp {\n"
            + "".join(f"  {d}_temp_path {tmp_path}/temp/{d.split('_')[0]};\n"
                      for d in ("client_body", "proxy", "fastcgi", "uwsgi", "scgi"))
            + f"  include {site};\n}}\n")
        proc = subprocess.Popen([nginx, "-p", str(tmp_path), "-c", str(conf), "-g", "daemon off;"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        procs.append(proc)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
                return port
            except OSError:
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
        out = proc.stdout.read().decode() if proc.poll() is not None else ""
        pytest.fail(f"nginx did not start: {out}\n{(tmp_path / 'error.log').read_text(errors='replace')}")

    yield start
    for proc in procs:
        proc.terminate()
        proc.wait(timeout=10)


def _get(port, path, src=ALLOWED, password=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5, source_address=(src, 0))
    headers = {}
    if password is not None:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{USER}:{password}".encode()).decode()
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, body


@pytest.mark.parametrize("leftovers", [False, True], ids=["fresh", "previously-enabled"])
def test_disabled_status_page_serves_no_dashboard_or_reports(serve, leftovers):
    port = serve(enabled=False, leftovers=leftovers)
    for path in OPERATOR_PATHS:
        for password in (None, PASSWORD):
            for src in (ALLOWED, OTHER):
                status, _ = _get(port, path, src=src, password=password)
                assert status == 404, (path, src, password is not None, status)
    for path in ZTP_PATHS:
        assert _get(port, path, src=ALLOWED)[0] == 200, path
        assert _get(port, path, src=OTHER)[0] == 403, path


def test_enabled_status_page_requires_the_dedicated_password(serve):
    port = serve(enabled=True, leftovers=True)
    for path in ("/", "/reports/", "/reports/ztp-report.txt", "/licenses/license.txt", "/images/fw.bin"):
        assert _get(port, path)[0] == 401, path
        assert _get(port, path, password="wrong")[0] == 401, path  # pragma: allowlist secret
        assert _get(port, path, password=PASSWORD)[0] == 200, path
    assert b"ERA dashboard" in _get(port, "/", password=PASSWORD)[1]
    for path in ZTP_PATHS:
        assert _get(port, path, src=ALLOWED)[0] == 200, path
        assert _get(port, path, src=OTHER)[0] == 403, path


def _deploy_tasks(source):
    doc = yaml.safe_load(source.read_text())
    tasks = doc if source == ROLE_TASKS else doc[0]["tasks"]
    return [t for t in tasks if t.get("name") in (RENDER[source], CLEANUP)]


def _retarget(tasks, root, htpasswd):
    text = yaml.safe_dump(tasks, sort_keys=False)
    text = text.replace("/var/www/ztp", str(root)).replace("/etc/nginx/.htpasswd", str(htpasswd))
    out = yaml.safe_load(text)
    for t in out:
        for module in ("template", "file"):
            if isinstance(t.get(module), dict):
                t[module].pop("owner", None)
                t[module].pop("group", None)
    return out


@pytest.mark.parametrize("source", [PLAYBOOK, ROLE_TASKS], ids=lambda p: p.name)
@pytest.mark.parametrize("enabled", [False, True], ids=["disabled", "enabled"])
def test_deploy_paths_drop_an_earlier_dashboard_when_disabled(tmp_path, source, enabled):
    _nginx()
    tasks = _deploy_tasks(source)
    assert [t["name"] for t in tasks] == [RENDER[source], CLEANUP]
    root = _web_root(tmp_path, leftovers=True)
    htpasswd = tmp_path / "htpasswd"
    htpasswd.write_text("era:$5$x$y\n")
    if enabled:
        tasks = tasks[1:]  # rendering the dashboard needs the full inventory
    _ansible(tmp_path, _retarget(tasks, root, htpasswd), {"status_page_enabled": enabled})
    assert (root / "index.html").exists() is enabled
    assert htpasswd.exists() is enabled
    assert (root / "reports" / "ztp-report.txt").exists()
    assert (root / "scripts" / "ztp.sh").exists()


def test_noztp_deploy_runs_the_status_page_playbook():
    make = (REPO / "Makefile").read_text()
    step5 = make.index("STEP 5/6: Install Operator Status Page")
    noztp = make.index('@if [ "$(NOZTP)" = "1" ]', step5)
    assert "playbooks/setup-status-page.yml" in make[step5:noztp]
