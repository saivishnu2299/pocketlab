#!/bin/sh
# Stock launcher. Recovery changes only recorded PocketLAB runtime files.
APPDIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
cd "$APPDIR" || exit 1
mkdir -p "$APPDIR/data" "$APPDIR/apps" || exit 1
PENDING="$APPDIR/data/pending-shell-update"
if [ -d /tmp/pocketlab-shell-install.lock ]; then
    printf 'PocketLAB update is in progress; reopen after installation finishes.\n' >> "$APPDIR/data/pocketlab.log"
    exit 1
fi
if [ -f "$APPDIR/data/pocketlab.log" ]; then
    mv -f "$APPDIR/data/pocketlab.log" "$APPDIR/data/pocketlab.previous.log"
fi
export LD_LIBRARY_PATH="$APPDIR/lib:/usr/trimui/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
recover() {
    read -r token phase < "$PENDING" || return 1
    case "$token" in ''|*[!a-f0-9]*) return 1;; esac
    [ "${#token}" -eq 32 ] || return 1
    printf 'Recovering previous PocketLAB runtime\n'
    sh "$APPDIR/data/updates/$token/restore.sh"
}
{
    date
    uname -a
    printf 'PocketLAB launcher: %s\n' "$APPDIR"
    while :; do
        checking=0
        if [ -f "$PENDING" ]; then
            read -r token phase < "$PENDING" || exit 1
            if [ "$phase" != ready ]; then
                recover || exit 1
            else
                printf '%s attempted\n' "$token" > "$PENDING.incoming"
                sync
                mv "$PENDING.incoming" "$PENDING"
                sync
                rm -f "$APPDIR/data/control/status.json"
                checking=1
            fi
        fi
        "$APPDIR/pocketlab" --root "$APPDIR" &
        child=$!
        if [ "$checking" -eq 1 ]; then
            tries=0
            while [ "$tries" -lt 100 ] && kill -0 "$child" 2>/dev/null; do
                status="$APPDIR/data/control/status.json"
                if [ -f "$status" ] && grep -q '"shell_pid":'"$child"',' "$status" &&
                   grep -Eq '"state":"(library|builtin|app)"' "$status"; then
                    rm -f "$PENDING"
                    printf 'Updated shell acknowledged startup\n'
                    break
                fi
                sleep 0.1
                tries=$((tries + 1))
            done
            if [ -f "$PENDING" ]; then
                kill -TERM "$child" 2>/dev/null
                sleep 1
                kill -KILL "$child" 2>/dev/null
                wait "$child" 2>/dev/null
                recover || exit 1
                continue
            fi
        fi
        wait "$child"
        RESULT=$?
        [ "$RESULT" -eq 75 ] || break
        printf 'Restarting updated PocketLAB\n'
        sleep 1
    done
    printf 'PocketLAB exit code: %s\n' "$RESULT"
    exit "$RESULT"
} >> "$APPDIR/data/pocketlab.log" 2>&1
