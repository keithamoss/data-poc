#!/usr/bin/env bash
# ONE DATABASE PER ASSET, supply_<data_asset_id> (REQ-PIPE-343 criterion 7;
# Keith, 2026-11-15: a compose init script). docker-compose.yml mounts this
# repository's assets/ read-only into the database container and this file
# into /docker-entrypoint-initdb.d/, so the official postgres image runs it
# once, when the data volume is first initialised - an existing volume keeps
# whatever databases it already has. An asset is a folder under assets/ that
# holds a data-asset.yaml; its database is named by that file's
# data_asset_id, which is what each command opens (qa_tools/common/supply_db.py)
# and what each database is marked with (post-create.sh).
#
# `--list` prints the names and touches no database (tests/test_devcontainer.py).
# Deliberately no `set -u`: the image's entrypoint may source a script that is
# not executable, and that would change its own shell's options.
set -eo pipefail

assets_dir="${MOTHMAN_ASSETS_DIR:-/mothman-assets}"

asset_databases() {
  local folder id
  for folder in "$assets_dir"/*/; do
    [ -f "${folder}data-asset.yaml" ] || continue
    id=$(sed -n 's/^data_asset_id:[[:space:]]*\([^[:space:]#]*\).*/\1/p' "${folder}data-asset.yaml" | head -n 1)
    [ -n "$id" ] && echo "supply_${id}"
  done
}

if [ "${1:-}" = "--list" ]; then
  asset_databases
else
  for db in $(asset_databases); do
    echo "Creating database ${db}"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
      -c "CREATE DATABASE \"${db}\" OWNER \"${POSTGRES_USER}\""
  done
fi
