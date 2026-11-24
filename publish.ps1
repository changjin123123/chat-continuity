param([string]$Repository = "chat-continuity")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if ($Repository -notmatch '^[A-Za-z0-9_.-]+$') { throw "Repository name must not contain an owner or path." }
foreach ($tool in @("git", "gh")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Install $tool first." }
}
gh auth status
if ($LASTEXITCODE -ne 0) { throw "Run gh auth login, then retry." }
if (Test-Path .git) {
    $remotes = git remote
    if ($remotes) { throw "A remote already exists. This helper will not overwrite it." }
} else {
    git init -b main
    if ($LASTEXITCODE -ne 0) { throw "git init failed." }
}
# Explicit allowlist: never stage the private database, user exports or environment secrets.
git add -- README.md pyproject.toml .gitignore continuity tests examples docs publish.ps1
if ($LASTEXITCODE -ne 0) { throw "git add failed." }
git diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
    git -c user.name="Chat Continuity" -c user.email="continuity@users.noreply.github.com" commit -m "Add source-grounded conversation continuity MVP"
    if ($LASTEXITCODE -ne 0) { throw "Commit failed. Inspect git status before retrying." }
} elseif ($LASTEXITCODE -ne 0) { throw "Cannot inspect staged changes." }
gh repo create $Repository --public --source . --remote origin --push --description "Lossless conversation archive and verified AI session handoff"
if ($LASTEXITCODE -ne 0) { throw "GitHub publish failed. Local code and commit are preserved; inspect gh output." }
