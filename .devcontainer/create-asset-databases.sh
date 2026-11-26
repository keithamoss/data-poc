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

# AN ASSET'S ID IS HELD TO THE ASSET-NAME PATTERN (asset_model/assets.py's
# NAME_PATTERN) before it goes into SQL: a bad one, or an asset with none,
# fails the whole script, naming the folder - never a database silently
# skipped or a name quoted into something else.
asset_databases() {
  local folder id
  for folder in "$assets_dir"/*/; do
    [ -f "${folder}data-asset.yaml" ] || continue
    id=$(sed -n 's/^data_asset_id:[[:space:]]*\([^[:space:]#]*\).*/\1/p' "${folder}data-asset.yaml" \
      | head -n 1 | tr -d "\"'")
    if ! printf '%s' "$id" | grep -Eqx '[a-z0-9]+(-[a-z0-9]+)*'; then
      echo "create-asset-databases: ${folder}data-asset.yaml's data_asset_id '${id}' is" \
        "missing or not lowercase letters, digits and single hyphens - no database made." >&2
      return 1
    fi
    echo "supply_${id}"
  done
  return 0
}

names=$(asset_databases) || exit 1
if [ "${1:-}" = "--list" ]; then
  [ -z "$names" ] || printf '%s\n' $names
else
  for db in $names; do
    echo "Creating database ${db}"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
      -c "CREATE DATABASE \"${db}\" OWNER \"${POSTGRES_USER}\""
  done
fi
