#!/bin/bash
# Warns when `git worktree add` is run inside a kubeyard-managed repository,
# where a bare worktree still shares one namespace, database and broker with
# every other checkout. Detached worktrees are the supported way to rewrite
# history in a repository with uncommitted changes, so they pass silently.
#
# To make this block instead of warn, replace the additionalContext line with:
#     permissionDecision: "deny",
#     permissionDecisionReason: $message
set -u

input=$(cat)
command=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')
cwd=$(printf '%s' "$input" | jq -r '.cwd // ""')

case "$command" in
    *'git worktree add'*) ;;
    *) exit 0 ;;
esac

case "$command" in
    *--detach*) exit 0 ;;
esac

project=$cwd
while [ -n "$project" ] && [ "$project" != "/" ] && [ ! -f "$project/config/kubeyard.yml" ]; do
    project=$(dirname "$project")
done
[ -f "$project/config/kubeyard.yml" ] || exit 0

jq -n --arg project "$project" '{
    hookSpecificOutput: {
        hookEventName: "PreToolUse",
        additionalContext: (
            $project + " is a kubeyard project, where a bare worktree gives you an isolated "
            + "checkout but still shares one namespace, database and message broker with every "
            + "other checkout. Prefer `kubeyard workspace create <name>`, which creates the "
            + "worktree and an isolated ws-<name> environment; `--print-path` prints the "
            + "directory to cd into. For work spanning several repositories, run it once per "
            + "repository with the same name. Load the kubeyard:workspaces skill for the full flow. If you "
            + "want a throwaway worktree to rewrite history, use --detach."
        )
    }
}'
