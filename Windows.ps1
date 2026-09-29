#requires -Version 5.1
<#
Local Foundry for Windows 11. Run from PowerShell, not an elevated shell.
Examples: .\Windows.ps1 Install; .\Windows.ps1 Start; .\Windows.ps1 Stop -Previews
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('Install', 'Start', 'Stop', 'Doctor', 'OfflineCheck', 'Paths', 'OpenFiles', 'Configure', 'Test')]
    [string]$Action = 'Start',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')]
    [string]$Distribution = 'Ubuntu-24.04',
    [switch]$Offline,
    [switch]$Previews,
    [switch]$Database,
    [string]$Model = '',
    [string]$ApiBase = 'http://127.0.0.1:11434/v1'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-FoundryWsl {
    param([string[]]$LinuxArguments, [switch]$Capture)
    $wslArguments = @('--distribution', $Distribution, '--exec') + $LinuxArguments
    if ($Capture) {
        $lines = & wsl.exe @wslArguments
        $code = $LASTEXITCODE
        $result = ($lines -join "`n") -replace "`0", ''
        if ($code -ne 0) {
            if ($result) { Write-Host $result }
            throw "WSL command returned $code. Follow the message above and WINDOWS.md."
        }
        return $result.Trim()
    }
    & wsl.exe @wslArguments
    if ($LASTEXITCODE -ne 0) { throw "WSL command returned $LASTEXITCODE. Follow the message above and WINDOWS.md." }
}

function Test-WindowsLoopback {
    param([object]$Launch)
    # No proxies, LAN binding, shell evaluation, or token-bearing query strings.
    $url = [string]$Launch.url
    if ($url -notmatch '^http://127[.]0[.]0[.]1:([0-9]{4,5})/#token=([A-Za-z0-9_-]{32,200})$') {
        throw 'The launcher returned an invalid local address.'
    }
    $port = [int]$Matches[1]
    $token = $Matches[2]
    if ($port -lt 1024 -or $port -gt 65535) { throw 'Invalid builder port.' }
    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object System.Net.Http.HttpClientHandler
    $handler.UseProxy = $false
    $client = New-Object System.Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromSeconds(3)
    $client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer', $token)
    try {
        for ($attempt = 0; $attempt -lt 12; $attempt++) {
            try {
                $response = $client.GetAsync("http://127.0.0.1:$port/api/config").GetAwaiter().GetResult()
                try {
                    if ($response.IsSuccessStatusCode) {
                        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
                        if ($body.version -and $body.providers) { return }
                    }
                } finally { $response.Dispose() }
            } catch { }
            Start-Sleep -Milliseconds 500
        }
        throw 'The builder is running in WSL, but Windows cannot reach its loopback port. Check WSL localhost forwarding/VPN settings in WINDOWS.md. Do not expose it on 0.0.0.0.'
    } finally { $client.Dispose(); $handler.Dispose() }
}

$foundryOriginalEncoding = [Console]::OutputEncoding
try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'Run Windows.ps1 from Windows PowerShell or PowerShell on Windows 11.' }
    $windowsBuild = [int](Get-CimInstance Win32_OperatingSystem).BuildNumber
    if ($windowsBuild -lt 22000) { throw 'Windows 11 is required for this launcher.' }
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $OutputEncoding = [Console]::OutputEncoding
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
        throw 'Install WSL2 first: wsl --install -d Ubuntu-24.04. See WINDOWS.md.'
    }
    $distributions = (& wsl.exe --list --verbose | Out-String) -replace "`0", ''
    if ($LASTEXITCODE -ne 0) { throw 'WSL could not list distributions. See WINDOWS.md.' }
    $distroPattern = '(?m)^\s*\*?\s*' + [regex]::Escape($Distribution) + '\s+.+\s+2\s*$'
    if ($distributions -notmatch $distroPattern) {
        throw "Install or convert $Distribution to WSL2, then enable its Docker Desktop WSL integration. See WINDOWS.md."
    }
    if ($Offline -and $Action -ne 'Start') { throw '-Offline applies only to Start. Install downloads dependencies; OfflineCheck verifies cached readiness.' }
    if (($Previews -or $Database) -and $Action -ne 'Stop') { throw '-Previews and -Database apply only to Stop.' }
    $linuxHome = Invoke-FoundryWsl -LinuxArguments @('printenv', 'HOME') -Capture
    if (-not $linuxHome.StartsWith('/') -or $linuxHome.Contains("`n")) { throw 'WSL returned an invalid home directory.' }
    $manager = "$linuxHome/.local/share/local-foundry/current/scripts/windows/wsl.py"
    if ($Action -eq 'Install') {
        $source = Invoke-FoundryWsl -LinuxArguments @('wslpath', '-u', '--', $PSScriptRoot) -Capture
        Invoke-FoundryWsl -LinuxArguments @('python3', "$source/scripts/windows/wsl.py", 'install', '--source', $source)
    } elseif ($Action -eq 'Start') {
        $arguments = @('python3', $manager, 'start')
        if ($Offline) { $arguments += '--offline' }
        $launch = Invoke-FoundryWsl -LinuxArguments $arguments -Capture | ConvertFrom-Json
        Test-WindowsLoopback -Launch $launch
        Start-Process -FilePath ([string]$launch.url)
        Write-Host "Local Foundry is ready at http://127.0.0.1:$($launch.port). The browser received your private launch token."
        Write-Host 'It runs in the background. Stop it with: .\Windows.ps1 Stop'
    } elseif ($Action -eq 'Stop') {
        $arguments = @('python3', $manager, 'stop')
        if ($Previews) { $arguments += '--previews' }
        if ($Database) { $arguments += '--database' }
        Invoke-FoundryWsl -LinuxArguments $arguments
    } elseif ($Action -eq 'Configure') {
        if (-not $Model) { throw 'Supply -Model with the exact downloaded model ID. The server must run inside this WSL distro.' }
        Invoke-FoundryWsl -LinuxArguments @('python3', $manager, 'configure', '--model', $Model, '--api-base', $ApiBase)
    } elseif ($Action -in @('Paths', 'OpenFiles')) {
        $paths = Invoke-FoundryWsl -LinuxArguments @('python3', $manager, 'paths') -Capture | ConvertFrom-Json
        $windowsPaths = [ordered]@{}
        foreach ($property in $paths.PSObject.Properties) {
            $windowsPaths[$property.Name] = "\\wsl.localhost\$Distribution" + $property.Value.Replace('/', '\')
        }
        if ($Action -eq 'OpenFiles') { Start-Process -FilePath explorer.exe -ArgumentList ('"' + $windowsPaths['files'] + '"') }
        else { [PSCustomObject]$windowsPaths | Format-List }
    } elseif ($Action -in @('Doctor', 'OfflineCheck')) {
        $command = if ($Action -eq 'OfflineCheck') { 'offline-check' } else { 'doctor' }
        $diagnostic = Invoke-FoundryWsl -LinuxArguments @('python3', $manager, $command) -Capture | ConvertFrom-Json
        $diagnostic | ConvertTo-Json -Depth 20 | Write-Output
        if ($diagnostic.checks.builder_http.status -eq 'passed') {
            $launch = Invoke-FoundryWsl -LinuxArguments @('python3', $manager, 'status') -Capture | ConvertFrom-Json
            Test-WindowsLoopback -Launch $launch
            Write-Host 'Windows-to-WSL authenticated localhost check passed.'
        } elseif ($Action -eq 'OfflineCheck') {
            throw 'Offline preflight requires the builder to be running. Start it, then rerun OfflineCheck.'
        } else {
            Write-Host 'Builder is not running; localhost access check was skipped. Start it and rerun Doctor.'
        }
    } elseif ($Action -eq 'Test') {
        $launch = Invoke-FoundryWsl -LinuxArguments @('python3', $manager, 'status') -Capture | ConvertFrom-Json
        Test-WindowsLoopback -Launch $launch
        Write-Host 'Windows-to-WSL authenticated localhost check passed.'
        Invoke-FoundryWsl -LinuxArguments @('python3', $manager, 'test')
    }
} catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
} finally {
    [Console]::OutputEncoding = $foundryOriginalEncoding
}
