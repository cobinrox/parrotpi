#!/bin/bash
# Back up all the pi-side config that was tuned by hand and is NOT
# reproducible from a fresh clone of this repo + install_as_service.
#
# Run as:  sudo ./sudo_backup_config_RUN_AS_SUDO.sh
# Then copy the resulting archive off the pi, e.g.:
#   scp u@parrotpi.local:~/parrotpi-config-backup-*.tgz .
#
# The archive contains wifi passwords in plaintext. Store it safely.
# Do NOT commit it to git.

set -e

OUT="$HOME/parrotpi-config-backup-$(date +%F).tgz"

FILES=(
  /etc/caddy/Caddyfile
  /etc/NetworkManager/system-connections/parrotpi-private.nmconnection
  /etc/NetworkManager/system-connections/parrotpi-dev.nmconnection
  /etc/NetworkManager/dnsmasq-shared.d/parrotpi.conf
  /var/lib/caddy/.local/share/caddy/pki
  /etc/parrotpi.env
  /etc/asound.conf
)

# Only include paths that actually exist; warn about any that don't.
TO_TAR=()
for f in "${FILES[@]}"; do
  if [ -e "$f" ]; then
    TO_TAR+=("$f")
  else
    echo "WARN: missing, skipping: $f" >&2
  fi
done

echo "Creating: $OUT"
tar czvf "$OUT" "${TO_TAR[@]}"

# Make sure the invoking user (not root) owns the archive so they can scp it.
if [ -n "$SUDO_USER" ]; then
  chown "$SUDO_USER:$SUDO_USER" "$OUT"
fi

echo
echo "Done. Archive: $OUT"
echo "Copy it off the pi with:"
echo "  scp u@parrotpi.local:$OUT ."
