#!/usr/bin/env bash
# Switch to TTY5 only after the face-recognition service is active.
set -euo pipefail

for _ in $(seq 1 30); do
    if /usr/bin/systemctl is-active --quiet face-recognition-tty5.service; then
        /usr/bin/chvt 5
        exit 0
    fi
    sleep 1
done

printf 'Face Recognition TTY5 service did not become active.\n' >&2
exit 1
