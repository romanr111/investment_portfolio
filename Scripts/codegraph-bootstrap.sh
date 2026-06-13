#!/bin/bash
set -euo pipefail

fail() {
  echo "codegraph-bootstrap: $*" >&2
  exit 1
}

command -v git >/dev/null 2>&1 || fail "git is not available"
command -v codegraph >/dev/null 2>&1 || fail "codegraph is not available on PATH"

git_root="$(git rev-parse --show-toplevel 2>/dev/null)" || fail "not inside a git worktree"
git_root_real="$(cd "$git_root" && pwd -P)"
current_dir_real="$(pwd -P)"

if [[ "$current_dir_real" != "$git_root_real" ]]; then
  fail "Run from the git worktree root: $git_root_real"
fi

mkdir -p "$git_root_real/.codegraph"

owner_marker="$git_root_real/.codegraph/worktree-root"

if [[ ! -f "$git_root_real/.codegraph/codegraph.db" ]]; then
  echo "codegraph-bootstrap: initializing CodeGraph index for $git_root_real"
  codegraph init -i
  printf '%s\n' "$git_root_real" > "$owner_marker"
elif [[ ! -f "$owner_marker" ]]; then
  fail "existing CodeGraph DB is missing worktree owner marker: $owner_marker"
else
  owner_root="$(sed -n '1p' "$owner_marker")"
  owner_root_real="$(cd "$owner_root" 2>/dev/null && pwd -P)" || fail "CodeGraph DB belongs to unreadable worktree: $owner_root"

  if [[ "$owner_root_real" != "$git_root_real" ]]; then
    fail "CodeGraph DB belongs to another worktree '$owner_root_real', not '$git_root_real'"
  fi
fi

status_output="$(codegraph status 2>&1)"
status_clean="$(printf '%s\n' "$status_output" | perl -pe 's/\e\[[0-9;?]*[ -\/]*[@-~]//g')"
project_line="$(printf '%s\n' "$status_clean" | awk '/Project:/ { print; exit }')"

if [[ -z "$project_line" ]]; then
  printf '%s\n' "$status_output" >&2
  fail "could not find CodeGraph project path in status output"
fi

project_path="$(printf '%s\n' "${project_line#*Project:}" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"

if [[ -z "$project_path" || ! -d "$project_path" ]]; then
  printf '%s\n' "$status_output" >&2
  fail "CodeGraph reported an invalid project path: ${project_path:-<empty>}"
fi

project_path_real="$(cd "$project_path" && pwd -P)"

if [[ "$project_path_real" != "$git_root_real" ]]; then
  printf '%s\n' "$status_output" >&2
  fail "CodeGraph project '$project_path_real' does not match this worktree '$git_root_real'"
fi

printf '%s\n' "$status_output"
