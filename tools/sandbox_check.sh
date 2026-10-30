#!/usr/bin/env bash
# tools/sandbox_check.sh — run the full platform smoke suite INSIDE the lp.dev sandbox (s tool)
#   -OTS no secrets leave the machine: ships server.py only, runs B44_DISABLE_AI=1 (template agent)
#   -OTS requires: /usr/local/bin/s wrapper + network to lp.dev (control plane, rate-limited ~1 call/20s)
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(mktemp -d /tmp/sbx.XXXXXX)

# ─ 1. lean payload: no .git, no data/ (fresh db on remote), no vendor (2.9MB babel not needed for smoke)
TAR="$ROOT/b44.tar.gz"
tar -czf "$TAR" server.py README.md Dockerfile docker-compose.yml release.sh www/runtime.html
B64=$(base64 -w0 "$TAR")
echo "payload: $(du -h "$TAR" | cut -f1) tar → $(echo -n "$B64" | wc -c) b64"

# ─ 2. remote python envelope (payload embedded)
cat > "$ROOT/env.py" <<PYEOF
import base64, io, json, os, subprocess, sys, tarfile, time, urllib.request
B64 = "__PAYLOAD__"
work = "/tmp/b44app"
subprocess.run(["rm", "-rf", work], check=False)
os.makedirs(work, exist_ok=True)
tarfile.open(fileobj=io.BytesIO(base64.b64decode(B64)), mode="r:gz").extractall(work)
check = subprocess.run([sys.executable, "-m", "py_compile", work + "/server.py"], capture_output=True, text=True)
print("py_compile:", "OK" if check.returncode == 0 else check.stderr[:800])
if check.returncode != 0:
    sys.exit(1)

env = dict(os.environ, B44_DISABLE_AI="1")
port = 8510
logf = open("/tmp/srv.log", "w")
proc = subprocess.Popen([sys.executable, work + "/server.py"], env=env, cwd=work,
                        stdout=logf, stderr=subprocess.STDOUT)
B = f"http://localhost:{port}"
def req(path, method="GET", body=None, token=None):
    h = {"Authorization": "Bearer " + token} if token else {}
    if body: h["Content-Type"] = "application/json"
    r = urllib.request.Request(B + path, data=(json.dumps(body).encode() if body else None),
                               method=method, headers=h)
    return urllib.request.urlopen(r, timeout=30)

ok, fail = [], []
for _ in range(40):                       # wait for boot
    try:
        req("/"); break
    except Exception:
        time.sleep(0.5)
else:
    print("SMOKE FAIL: server did not boot — server log:")
    logf.flush()
    print(open("/tmp/srv.log").read()[:2000])
    proc.kill(); sys.exit(1)
def step(name, fn):
    try:
        fn(); ok.append(name); print("✓", name)
    except Exception as e:
        fail.append(name); print("✗", name, "—", str(e)[:300])

def s_root():
    assert req("/").status == 200
def s_static():
    r = urllib.request.Request(B + "/api/definitely_unknown", method="GET")
    try:
        u2 = urllib.request.urlopen(r, timeout=10)
        assert u2.status == 200, "unknown returned 200?!"
    except urllib.error.HTTPError as e:
        assert e.code == 404 and b"unknown_endpoint" in e.read()
def s_login():
    global tok
    tok = json.loads(req("/api/auth/login", "POST", {"email": "sbx@x.io", "password": "p"}).read())["access_token"]
def s_unknown():
    try:
        u2 = req("/api/definitely_unknown", token=tok)
        assert False, "unknown returned " + str(u2.status)
    except urllib.error.HTTPError as e:
        assert e.code == 404 and b"unknown_endpoint" in e.read()
def s_apps():
    global app
    app = json.loads(req("/api/apps", "POST", {"prompt": "A CRM to track my clients and deals"}, token=tok).read())
    assert app["spec"]["entities"], "template agent produced no entities"
def s_detail():
    d = json.loads(req(f"/api/apps/{app['id']}", token=tok).read())
    assert d["files"], "no code files"
def s_publish():
    pub = json.loads(req(f"/api/apps/{app['id']}/publish", "POST", token=tok).read())
    assert pub["state"] == "published"
    slug = pub["sub_domain"]
    assert json.loads(req(f"/api/published/{slug}").read())["spec"]["entities"]
    assert req(f"/p/{slug}").status == 200

step("1. GET / 200", s_root)
step("2. login", s_login)
step("3. API 404 handling", s_unknown)
step("4. template create → entities", s_apps)
step("5. app detail → code files", s_detail)
step("6. publish → public /p + /api/published", s_publish)
proc.kill()
print(json.dumps({"pass": len(ok), "fail": len(fail)}))
sys.exit(1 if fail else 0)
PYEOF

python3 - "$B64" "$ROOT/env.py" <<'INJ'
import sys
b64, path = sys.argv[1], sys.argv[2]
src = open(path).read()
assert "__PAYLOAD__" in src
open(path, "w").write(src.replace("__PAYLOAD__", b64, 1))
INJ

# ─ 3. ship → run (envelope includes the script itself → ONE s call, payload inline)
rc=0
sleep 18                                   # lp.dev control-plane rate limit
s -l python -f "$ROOT/env.py" -k -E || rc=$?
rm -rf "$ROOT"
exit "$rc"
