#!/bin/sh
# card-secrets: makes a card's internal and human secrets on the device, at first start.
#
#   generate        (the default) make each secret in CARD_SECRETS that does not exist yet
#   show <NAME>     print one secret, for a person on the machine (human secrets)
#
# CARD_SECRETS has one line per secret, NAME=command, the command from the card's secrets:
# make. Each secret becomes the file $DIR/NAME (default /run/card-secrets), one value per file.
# A secret that exists is never changed: a database set its password at its first start.
# It also writes $DIR/.load, the wrapper an app's container runs as its entrypoint: it loads
# every secret into the environment and then runs the app's own command. So a remote deploy
# needs nothing but the Compose file, and no value is in it.
set -eu
DIR=${CARD_SECRETS_DIR:-/run/card-secrets}

case "${1:-generate}" in
generate)
  mkdir -p "$DIR"
  made=0
  printf '%s\n' "${CARD_SECRETS:-}" | while IFS= read -r line; do
    case "$line" in ''|'#'*) continue ;; esac
    name=${line%%=*}; cmd=${line#*=}
    case "$name" in *[!A-Z0-9_]*|'') echo "card-secrets: bad name in line: $name" >&2; exit 1 ;; esac
    [ -s "$DIR/$name" ] && continue
    value=$(sh -c "$cmd")
    [ -n "$value" ] || { echo "card-secrets: the command for $name printed nothing" >&2; exit 1; }
    umask 077
    printf '%s' "$value" > "$DIR/.$name.new" && mv "$DIR/.$name.new" "$DIR/$name"
    chmod 0444 "$DIR/$name"
    echo "card-secrets: made $name"
  done
  cat > "$DIR/.load" <<'LOAD'
#!/bin/sh
# Loads the card's secrets into the environment, then runs the app's own command.
for f in /run/card-secrets/*; do [ -f "$f" ] && export "$(basename "$f")=$(cat "$f")"; done
exec "$@"
LOAD
  chmod 0555 "$DIR/.load"
  echo "card-secrets: ready ($(ls "$DIR" | wc -l | tr -d ' ') secrets)"
  ;;
show)
  name=${2:?usage: card-secrets show NAME}
  [ -s "$DIR/$name" ] || { echo "card-secrets: no secret $name" >&2; exit 1; }
  cat "$DIR/$name"; echo
  ;;
*) echo "usage: card-secrets [generate | show NAME]" >&2; exit 2 ;;
esac
