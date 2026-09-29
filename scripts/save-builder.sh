#!/usr/bin/env bash
# Run from the downloaded starter to save the builder itself to a new private repo.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
repository_name="${1:-local-foundry}"
if [[ ! "$repository_name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$ ]]; then
  echo "Supply a simple GitHub repository name."
  exit 1
fi
if [[ -d .git ]]; then
  echo "This folder is already a Git repository. Use your normal Git workflow."
  exit 1
fi
gh auth status
git init -b main
git add .gitignore .gitattributes .env.example README.md WINDOWS.md Windows.ps1 MOBILE.md ruff.toml CHANGELOG.md VALIDATION.md PROVIDER-ACCEPTANCE.md backend frontend template kits browser protected mobile release-template scripts tests screenshots
git -c core.hooksPath=/dev/null diff --cached --check
git -c core.hooksPath=/dev/null -c commit.gpgsign=false commit -m "Add local app builder"
gh repo create "$repository_name" --private --source . --remote origin --push
