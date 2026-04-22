#!/bin/bash
# Restore a parrotpi config backup produced by sudo_backup_config_RUN_AS_SUDO.sh
# onto a fresh pi.
#
# Usage (pick one):
#   sudo ./sudo_restore_config_RUN_AS_SUDO.sh parrotpi-config-backup-2026-04-22.tgz
#   sudo ./sudo_restore_config_RUN_AS_SUDO.sh parrotpi-config-backup-2026-04-22.tgz.gpg
#
# If you pass a .gpg file, you will be prompted for the GPG passphrase.
#
# What this does:
#   1. (If .gpg) decrypts to a temp file
#   2. Lists the archive contents as a sanity check
#   3. Extracts at / (absolute paths are preserved in the archive)
#   4. Re-asserts root ownership and 600 mode on the NetworkManager files
#      (belt-and-suspenders; tar usually preserves these already)
#   5. Reloads NetworkManager and restarts caddy / avahi-daemon so the
#      restored configs take effect immediately
#
# Does NOT do:
#   - apt install packages (do that first per README)
#   - git clone the repo (do that first)
#   - run install_as_service_RUN_AS_SUDO.sh (do that after this script)

set -e

if [ "$EUID" -ne 0 ]; then
  echo "ERROR: must run as root (use sudo)"
  exit 1
fi

if [ -z "$1" ]; then
  echo "Usage: sudo $0 <backup-archive.tgz[.gpg]>"
  exit 1
fi

INPUT="$1"
if [ ! -f "$INPUT" ]; then
  echo "ERROR: file not found: $INPUT"
  exit 1
fi

# ---- step 1: decrypt if needed ----
TMP_ARCHIVE=""
cleanup() {
  if [ -n "$TMP_ARCHIVE" ] && [ -f "$TMP_ARCHIVE" ]; then
    shred -u "$TMP_ARCHIVE" 2>/dev/null || rm -f "$TMP_ARCHIVE"
  fi
}
trap cleanup EXIT

case "$INPUT" in
  *.gpg)
    TMP_ARCHIVE="$(mktemp /tmp/parrotpi-restore.XXXXXX.tgz)"
    echo "Decrypting $INPUT (you will be prompted for the passphrase)..."
    gpg --output "$TMP_ARCHIVE" --decrypt "$INPUT"
    ARCHIVE="$TMP_ARCHIVE"
    ;;
  *.tgz|*.tar.gz)
    ARCHIVE="$INPUT"
    ;;
  *)
    echo "ERROR: expected .tgz, .tar.gz, or .gpg file"
    exit 1
    ;;
esac

# ---- step 2: show what's in the archive before splattering it over / ----
echo
echo "===== Archive contents ====="
tar tzvf "$ARCHIVE"
echo "============================"
echo
read -r -p "Extract these files at / ? [y/N] " ans
if [ "$ans" != "y" ] && [ "$ans" != "Y" ]; then
  echo "Aborted."
  exit 1
fi

# ---- step 3: extract ----
echo "Extracting..."
tar xzvf "$ARCHIVE" -C /

# ---- step 4: fix perms on NM connection files (defense in depth) ----
echo "Fixing NetworkManager file ownership/perms..."
for f in /etc/NetworkManager/system-connections/parrotpi-private.nmconnection \
         /etc/NetworkManager/system-connections/parrotpi-dev.nmconnection; do
  if [ -f "$f" ]; then
    chown root:root "$f"
    chmod 600       "$f"
  fi
done

# ---- step 5: fix perms on caddy pki (owned by caddy user) ----
if [ -d /var/lib/caddy/.local/share/caddy/pki ]; then
  echo "Fixing Caddy PKI ownership..."
  chown -R caddy:caddy /var/lib/caddy/.local 2>/dev/null || true
fi

# ---- step 6: reload services ----
echo "Reloading NetworkManager..."
nmcli connection reload || true

echo "Restarting caddy..."
systemctl restart caddy || true

echo "Restarting avahi-daemon..."
systemctl restart avahi-daemon || true

# ---- step 7: re-apply autoconnect preferences (harmless if already set) ----
echo "Ensuring parrotpi-private is the default at boot..."
nmcli connection modify parrotpi-private connection.autoconnect yes \
                                         connection.autoconnect-priority 100 2>/dev/null || true
nmcli connection modify parrotpi-dev     connection.autoconnect no 2>/dev/null || true

echo
echo "Restore complete."
echo "Next steps:"
echo "  1. sudo ./install_as_service_RUN_AS_SUDO.sh   (recreates systemd service, logrotate, sudoers)"
echo "  2. sudo reboot                                 (verify it boots into parrotpi AP mode)"
