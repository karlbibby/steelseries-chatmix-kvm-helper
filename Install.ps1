param([switch]$ReplaceGGStartup)
$ErrorActionPreference = 'Stop'

# Default installation is per-user. Replacing an HKLM startup value additionally
# requires an administrator shell; this script does not change execution policy.
$installDir = Join-Path $env:LOCALAPPDATA 'GGChatMixHelper'
$machineKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
$userKey = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
$entryName = 'SteelSeriesChatMixHelper'
$backupFile = Join-Path $installDir 'startup-backup.json'
$pythonCommand = Get-Command python.exe -ErrorAction Stop
$pythonw = (& $pythonCommand.Source -c 'import pathlib,sys; print(pathlib.Path(sys.executable).with_name("pythonw.exe"))').Trim()
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $pythonw)) {
    throw 'Install regular Windows Python 3.10+ with python.exe on PATH and pythonw.exe alongside it.'
}
$versionOk = & $pythonCommand.Source -c 'import sys; print(int(sys.version_info >= (3,10)))'
if ($versionOk -ne '1') { throw 'Python 3.10 or newer is required' }
$machineCommand = (Get-ItemProperty -LiteralPath $machineKey -Name SteelSeriesGG -ErrorAction SilentlyContinue).SteelSeriesGG
$userCommand = (Get-ItemProperty -LiteralPath $userKey -Name SteelSeriesGG -ErrorAction SilentlyContinue).SteelSeriesGG
$helperCommand = '"' + $pythonw + '" "' + (Join-Path $installDir 'gg_chatmix_helper.py') + '" --startup'
$existingHelper = (Get-ItemProperty -LiteralPath $userKey -Name $entryName -ErrorAction SilentlyContinue).$entryName
if ($existingHelper -and $existingHelper -ne $helperCommand) {
    throw 'A different ChatMix helper startup entry exists; restore/remove that installation first.'
}
if ($ReplaceGGStartup -and $machineCommand) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Replacing machine-wide GG startup needs an administrator PowerShell window. Run as your own account.'
    }
}
if ($ReplaceGGStartup) {
    foreach ($value in @($machineCommand,$userCommand)) {
        if ($value -and $value -notmatch 'SteelSeries(?:GGEZ|GG)\.exe') {
            throw 'Unexpected SteelSeriesGG startup command. Back it up and review it manually before replacing it.'
        }
    }
}
New-Item -ItemType Directory -Path $installDir -Force | Out-Null
if (Test-Path -LiteralPath $backupFile) {
    $backup = Get-Content -LiteralPath $backupFile -Raw | ConvertFrom-Json
    if ([bool]$backup.ReplacedGGStartup -ne [bool]$ReplaceGGStartup) {
        throw 'Restore startup before changing installation mode.'
    }
} else {
    [pscustomobject]@{
        ReplacedGGStartup=[bool]$ReplaceGGStartup
        MachineCommand=$machineCommand
        UserCommand=$userCommand
        PreviousHelperCommand=$existingHelper
        HelperCommand=$helperCommand
        UserSid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        SavedAt=(Get-Date -Format o)
    } | ConvertTo-Json | Set-Content -LiteralPath $backupFile -Encoding UTF8
}
foreach ($file in @('gg_chatmix_helper.py','probe_headset.py','Launch GG with ChatMix.vbs','Restore-Startup.ps1','README.md','LICENSE')) {
    $source = Join-Path $PSScriptRoot $file
    $destination = Join-Path $installDir $file
    if ([IO.Path]::GetFullPath($source) -ne [IO.Path]::GetFullPath($destination)) {
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}
[IO.File]::WriteAllText((Join-Path $installDir 'pythonw-path.txt'),$pythonw)
New-Item -Path $userKey -Force | Out-Null
New-ItemProperty -LiteralPath $userKey -Name $entryName -Value $helperCommand -PropertyType String -Force | Out-Null
if ($ReplaceGGStartup) {
    if ($machineCommand) { Remove-ItemProperty -LiteralPath $machineKey -Name SteelSeriesGG }
    if ($userCommand) { Remove-ItemProperty -LiteralPath $userKey -Name SteelSeriesGG }
}
Write-Output "Installed to $installDir"
Write-Output "Startup entry: $entryName"
Write-Output 'Double-click Launch GG with ChatMix.vbs in the installed folder to run now, or sign in again.'
