#!/usr/bin/env python3
"""tools/sandbox_jsx_check.py — syntax-verify AI-generated site files (gen_files) in the lp.dev sandbox.

Usage:  sandbox_jsx_check.py <app_id> [base_url] [token_file]

Flow: pull gen_files from local server → base64 envelope → single `s -l python -f` remote call →
      bun parses every .jsx/.js via Bun.Transpiler → per-file verdict, exit 0 iff clean.
Rate limit: keep one `s` call per ~20s.
"""
import base64, json, os, subprocess, sys, urllib.request

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    app = sys.argv[1]
    base = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8510"
    tok = None
    if len(sys.argv) > 3:
        tok = open(sys.argv[3]).read().split()[1]
    headers = {"Authorization": "Bearer " + tok} if tok else {}
    d = json.loads(urllib.request.urlopen(
        urllib.request.Request(f"{base}/api/apps/{app}", headers=headers), timeout=30).read())
    files = {k: v for k, v in (d.get("gen_files") or {}).items() if k.endswith((".jsx", ".js"))}
    print(f"app {app} ({d['name']}) → {len(files)} JS/JSX files → remote bun parse")
    if not files:
        sys.exit("no JS payloads in gen_files — nothing to check")

    runner = (
        'const FILES = JSON.parse(await Bun.file("files.json").text());\n'
        'let bad = 0;\n'
        'for (const [p, src] of Object.entries(FILES)) {\n'
        '  try { new Bun.Transpiler({ loader: "jsx" }).transformSync(src);\n'
        '    console.log("OK   " + p); }\n'
        '  catch (e) { bad++;\n'
        '    console.log("BAD  " + p + " — " + String(e).slice(0, 220).replace(/\\n/g, " | ")); }\n'
        '}\n'
        'console.log(JSON.stringify({files: Object.keys(FILES).length, bad}));\n'
        'process.exit(bad ? 1 : 0);\n'
    )
    env = (
        "import base64, json, os, subprocess, sys\n"
        f"FILES = json.loads(base64.b64decode(\"{base64.b64encode(json.dumps(files).encode()).decode()}\"))\n"
        f"RUN = base64.b64decode(\"{base64.b64encode(runner.encode()).decode()}\").decode()\n"
        "os.makedirs('/tmp/jsxchk', exist_ok=True)\n"
        "os.chdir('/tmp/jsxchk')\n"
        "open('files.json', 'w').write(json.dumps(FILES))\n"
        "open('check.mjs', 'w').write(RUN)\n"
        "r = subprocess.run(['bun', '/tmp/jsxchk/check.mjs'], capture_output=True, text=True)\n"
        "print(r.stdout.strip())\n"
        "sys.stderr.write(r.stderr[:600])\n"
        "sys.exit(r.returncode)\n"
    )
    p = "/tmp/jsx_env.py"
    open(p, "w").write(env)
    print(f"envelope: {os.path.getsize(p)} b")
    try:
        out = subprocess.run(["s", "-l", "python", "-f", p, "-k", "-E"],
                             capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        sys.exit("`s` wrapper not found — expected /usr/local/bin/s")
    print(out.stdout.strip())
    if out.stderr.strip():
        print("stderr:", out.stderr.strip()[:400])
    sys.exit(out.returncode)

if __name__ == "__main__":
    main()
