#!/usr/bin/env bash
# Root-owned, fixed-purpose helper for the Face Recognition Pi GUI.
# Supported actions only: status, set-hostname <name>, reboot.
#
# v108: persists the hostname explicitly in /etc/hostname and prevents
# cloud-init (when installed) from overwriting the app-managed hostname at boot.

set -euo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

validate_hostname() {
    local value="$1"

    [[ -n "$value" ]] || fail "Hostname cannot be empty."
    [[ ${#value} -le 63 ]] || fail "Hostname must be 63 characters or fewer."
    [[ "$value" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$ || "$value" =~ ^[A-Za-z0-9]$ ]] \
        || fail "Hostname may contain only letters, numbers, and hyphens; it cannot start or end with a hyphen."
}

atomic_write_file() {
    local target="$1"
    local content="$2"
    local temp_file

    temp_file="$(mktemp "${target}.face-recognition.XXXXXX")"
    printf '%s\n' "$content" > "$temp_file"
    chown root:root "$temp_file"
    chmod 644 "$temp_file"
    mv -f "$temp_file" "$target"
}

write_static_hostname() {
    local new_hostname="$1"
    # /etc/hostname is the on-disk static hostname read again during boot.
    atomic_write_file "/etc/hostname" "$new_hostname"
}

update_hosts_file() {
    local new_hostname="$1"
    local temp_file

    temp_file="$(mktemp /etc/hosts.face-recognition.XXXXXX)"
    trap 'rm -f "$temp_file"' RETURN

    awk -v host="$new_hostname" '
        $1 == "127.0.1.1" {
            print "127.0.1.1\t" host
            found = 1
            next
        }
        { print }
        END {
            if (!found) {
                print "127.0.1.1\t" host
            }
        }
    ' /etc/hosts > "$temp_file"

    chown root:root "$temp_file"
    chmod 644 "$temp_file"
    mv -f "$temp_file" /etc/hosts
    trap - RETURN
}

protect_hostname_from_cloud_init() {
    # Raspberry Pi OS normally has no cloud-init. When it is installed,
    # this drop-in prevents its boot stage from restoring an old image name.
    if [[ -d /etc/cloud ]] || command -v cloud-init >/dev/null 2>&1; then
        install -d -o root -g root -m 755 /etc/cloud/cloud.cfg.d
        cat > /etc/cloud/cloud.cfg.d/99-face-recognition-preserve-hostname.cfg <<'CFG'
# Managed by Face Recognition Pi Device Control.
# The GUI owns /etc/hostname, so cloud-init must not replace it during boot.
preserve_hostname: true
CFG
        chown root:root /etc/cloud/cloud.cfg.d/99-face-recognition-preserve-hostname.cfg
        chmod 644 /etc/cloud/cloud.cfg.d/99-face-recognition-preserve-hostname.cfg
    fi
}

verify_persisted_hostname() {
    local expected="$1"
    local stored=""
    local static_name=""

    stored="$(tr -d '\r\n' < /etc/hostname 2>/dev/null || true)"
    static_name="$(hostnamectl --static 2>/dev/null || true)"

    [[ "$stored" == "$expected" ]] || fail "Could not persist hostname to /etc/hostname."
    [[ -z "$static_name" || "$static_name" == "$expected" ]] \
        || fail "Static hostname verification failed (expected ${expected}, got ${static_name})."
}

action="${1:-}"

case "$action" in
    status)
        [[ $# -eq 1 ]] || fail "Usage: status"
        echo "READY"
        ;;

    set-hostname)
        [[ $# -eq 2 ]] || fail "Usage: set-hostname <hostname>"
        new_hostname="$2"
        validate_hostname "$new_hostname"

        old_hostname="$(hostnamectl --static 2>/dev/null || hostname)"

        # Persist first, update local resolution, then update the active name.
        write_static_hostname "$new_hostname"
        update_hosts_file "$new_hostname"
        protect_hostname_from_cloud_init
        hostnamectl set-hostname "$new_hostname"
        verify_persisted_hostname "$new_hostname"

        echo "HOSTNAME_PERSISTED old=${old_hostname} new=${new_hostname}"
        ;;

    reboot)
        [[ $# -eq 1 ]] || fail "Usage: reboot"
        echo "REBOOT_REQUESTED"
        systemctl reboot
        ;;

    *)
        fail "Unsupported action."
        ;;
esac
