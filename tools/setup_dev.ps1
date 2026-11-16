# SYSTEM MIND X — Local Development Setup Wrapper (Windows PowerShell)
# Strictly unprivileged. Do not run as Administrator.

[CmdletBinding()]
param (
    [string]$Command = "bootstrap",
    [switch]$DryRun,
    [switch]$SkipTests,
    [switch]$SkipCargo,
    [switch]$SkipNpm,
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir

# Safety check: warn if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    Write-Warning "Running as Administrator is not recommended. SYSTEM MIND X should be installed in user space."
}

# Ensure Python is available
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "python is not found in PATH. Please install Python 3.10+ from python.org or via winget install Python.Python.3.12"
    exit 1
}

$devSetupScript = Join-Path $rootDir "tools\dev_setup.py"

$extraArgs = @()
if ($DryRun) { $extraArgs += "--dry-run" }
if ($SkipTests) { $extraArgs += "--skip-tests" }
if ($SkipCargo) { $extraArgs += "--skip-cargo" }
if ($SkipNpm) { $extraArgs += "--skip-npm" }
if ($Json) { $extraArgs += "--json" }

python $devSetupScript $Command @extraArgs
