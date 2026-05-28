#!/bin/bash
# Build a .deb for parakeet-ptt.
# Run from the repo root: bash packaging/build_deb.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="parakeet-ptt"
VERSION="1.0.0"
ARCH="amd64"
DEB_NAME="${PKG}_${VERSION}_${ARCH}.deb"
BUILD_DIR="/tmp/${PKG}-build"

echo "Building ${DEB_NAME} …"
rm -rf "$BUILD_DIR"

# ── Debian metadata ────────────────────────────────────────────────────────────
mkdir -p "${BUILD_DIR}/DEBIAN"
cp "${REPO_ROOT}/packaging/debian/control"  "${BUILD_DIR}/DEBIAN/control"
cp "${REPO_ROOT}/packaging/debian/postinst" "${BUILD_DIR}/DEBIAN/postinst"
cp "${REPO_ROOT}/packaging/debian/prerm"    "${BUILD_DIR}/DEBIAN/prerm"
chmod 755 "${BUILD_DIR}/DEBIAN/postinst" "${BUILD_DIR}/DEBIAN/prerm"

# ── Application files ──────────────────────────────────────────────────────────
SHARE="${BUILD_DIR}/usr/share/${PKG}"
mkdir -p "$SHARE"
cp -r "${REPO_ROOT}/parakeet_ptt" "$SHARE/"

# ── Launcher ──────────────────────────────────────────────────────────────────
BIN="${BUILD_DIR}/usr/bin"
mkdir -p "$BIN"
cat > "${BIN}/parakeet-ptt" <<'LAUNCHER'
#!/bin/bash
# Parakeet PTT launcher
export PYTHONPATH="/usr/share/parakeet-ptt${PYTHONPATH:+:$PYTHONPATH}"
exec python3 /usr/share/parakeet-ptt/parakeet_ptt/main.py "$@"
LAUNCHER
chmod 755 "${BIN}/parakeet-ptt"

# ── Desktop entry ──────────────────────────────────────────────────────────────
APPS="${BUILD_DIR}/usr/share/applications"
mkdir -p "$APPS"
cp "${REPO_ROOT}/data/parakeet-ptt.desktop" "$APPS/"

# ── Build ──────────────────────────────────────────────────────────────────────
dpkg-deb --build "$BUILD_DIR" "${REPO_ROOT}/${DEB_NAME}"
echo ""
echo "Done: ${REPO_ROOT}/${DEB_NAME}"
echo ""
echo "Install with:"
echo "  sudo dpkg -i ${REPO_ROOT}/${DEB_NAME}"
echo "  sudo apt-get install -f   # fix any missing deps"
