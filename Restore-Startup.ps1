$ErrorActionPreference = 'Stop'
$backup = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'startup-backup.json') -Raw | ConvertFrom-Json
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
if ($sid -ne $backup.UserSid) { throw 'Run this as the account that installed the helper.' }
$machineKey = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
$userKey = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
$entryName = 'SteelSeriesChatMixHelper'
$currentHelper = (Get-ItemProperty -LiteralPath $userKey -Name $entryName -ErrorAction SilentlyContinue).$entryName
if ($currentHelper -and $currentHelper -ne $backup.HelperCommand) {
    throw 'The helper startup command changed; refusing to overwrite it.'
}
if ($backup.ReplacedGGStartup) {
    # Validate both scopes before making changes.
    foreach ($scope in @(@{Key=$machineKey;Expected=$backup.MachineCommand},@{Key=$userKey;Expected=$backup.UserCommand})) {
        $current = (Get-ItemProperty -LiteralPath $scope.Key -Name SteelSeriesGG -ErrorAction SilentlyContinue).SteelSeriesGG
        if ($current -and $current -ne $scope.Expected) { throw 'GG startup changed; review it before restoring.' }
    }
    if ($backup.MachineCommand) {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            throw 'Restoring machine-wide GG startup needs an administrator PowerShell window.'
        }
        New-ItemProperty -LiteralPath $machineKey -Name SteelSeriesGG -Value $backup.MachineCommand -PropertyType String -Force | Out-Null
    }
    if ($backup.UserCommand) {
        New-ItemProperty -LiteralPath $userKey -Name SteelSeriesGG -Value $backup.UserCommand -PropertyType String -Force | Out-Null
    }
}
if ($backup.PreviousHelperCommand) {
    New-ItemProperty -LiteralPath $userKey -Name $entryName -Value $backup.PreviousHelperCommand -PropertyType String -Force | Out-Null
} elseif ($currentHelper) {
    Remove-ItemProperty -LiteralPath $userKey -Name $entryName
}
Write-Output 'Startup restored. Stop the running helper separately before removing its folder.'
