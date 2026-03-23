param(
    [string]$Root = "",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$cmdPath = Join-Path $PSScriptRoot "restart_reactive_chat.cmd"
if (-not (Test-Path $cmdPath)) {
    throw "Could not find restart_reactive_chat.cmd at $cmdPath"
}

$args = @()
if ($Root) {
    $args += $Root
}
if ($NoBrowser) {
    $args += "--no-browser"
}

& $cmdPath @args
exit $LASTEXITCODE
