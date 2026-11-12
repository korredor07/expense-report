#!/usr/bin/env bash
# No secrets in the change: keys, tokens or passwords written as literals in added lines.
bad="$(git diff "$FACTORY_BASE" -- . | grep -E '^\+' | grep -v '^+++' \
  | grep -iE "(api[_-]?key|secret|token|passw(or)?d)[\"']?[[:space:]]*[:=][[:space:]]*[\"'][A-Za-z0-9_\-]{16,}[\"']" || true)"
if [ -n "$bad" ]; then echo "The change adds what looks like a secret:"; echo "$bad"; exit 1; fi
