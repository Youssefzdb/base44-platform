#!/usr/bin/env sh
# ── release.sh — package & publish a GitHub Release for base44-platform ──
# 1. pnpm build the frontend (if ../base44-react available)
# 2. stage: server.py + www + dist + tests → tar.gz
# 3. create GitHub Release (tag v<version>) and upload the asset
#
# Usage:  GITHUB_TOKEN=ghp_xxx ./release.sh [version]
#         version defaults to YYYY.MMDD.HHMM
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
FE="$HERE/../base44-react"
REPO="Youssefzdb/base44-platform"
V="${1:-$(date +%Y.%m%d.%H%M)}"
TOKEN="${GITHUB_TOKEN:?GITHUB_TOKEN env required}"

API="https://api.github.com"

STEP() { printf '[release] %s\n' "$*"; }

# 1. rebuild frontend when we can
if [ -d "$FE/.git" ] && command -v pnpm >/dev/null 2>&1; then
  STEP "build frontend ($FE)"
  (cd "$FE" && pnpm build)
else
  STEP "no react repo/pnpm — shipping with existing dist/"
fi

# 2. stage tarball
STAGE="$HERE/.release-tmp/base44-platform-$V"
rm -rf "$HERE/.release-tmp" 2>/dev/null || true
mkdir -p "$STAGE"
cp "$HERE/server.py" "$STAGE/"
cp -r "$HERE/www"    "$STAGE/" 2>/dev/null || true
cp -r "$HERE/tests"  "$STAGE/" 2>/dev/null || true
if [ -d "$FE/dist" ]; then cp -r "$FE/dist" "$STAGE/dist"; fi
cp "$HERE/README.md" "$HERE/Dockerfile" "$HERE/docker-compose.yml" "$STAGE/" 2>/dev/null || true
TARBALL="$HERE/.release-tmp/base44-platform-$V.tar.gz"
tar -czf "$TARBALL" -C "$HERE/.release-tmp" "base44-platform-$V"
STEP "staged $(du -h "$TARBALL" | cut -f1) → $TARBALL"

# 3. create release + upload asset
TAG="v$V"
STEP "creating release $TAG on $REPO"
REL_JSON=$(cat <<EOF
{"tag_name":"$TAG","name":"Base44 platform $TAG","body":"Frontend build + mock-API backend. Unpack, run: python3 server.py, open http://localhost:8510","draft":false,"prerelease":false}
EOF
)
REL="$(
  curl -sS -X POST "$API/repos/$REPO/releases" \
    -H "Authorization: token $TOKEN" -H "Accept: application/vnd.github+json" \
    -d "$REL_JSON"
)"
UPLOAD=$(printf '%s' "$REL" | sed -n 's/.*"upload_url": *"\([^?]*\).*/\1/p')
[ -n "$UPLOAD" ] || { echo "release create failed:"; echo "$REL" | head -5; exit 1; }
ASSET="$(
  curl -sS -X POST "$UPLOAD?name=$(basename "$TARBALL")" \
    -H "Authorization: token $TOKEN" -H "Accept: application/vnd.github+json" \
    -H "Content-Type: application/gzip" --data-binary "@$TARBALL"
)"
STEP "asset: $(printf '%s' "$ASSET" | sed -n 's/.*"browser_download_url": *"\([^"]*\)".*/\1/p')"
rm -rf "$HERE/.release-tmp"
STEP "done ✅"
