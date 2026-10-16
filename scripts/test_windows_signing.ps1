# Exercise the verifier against an unsigned file and Microsoft's real signed host.
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
Get-ChildItem "$PSScriptRoot/*.ps1" | ForEach-Object {
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$null, [ref]$parseErrors)
    if ($parseErrors.Count -gt 0) { throw ($parseErrors | Out-String) }
}
$originalSubject = $env:WINDOWS_SIGNING_SUBJECT
$unsigned = Join-Path ([IO.Path]::GetTempPath()) ("codebone-unsigned-" + [guid]::NewGuid() + '.ps1')
try {
    Set-Content -LiteralPath $unsigned -Value '# Unsigned signature verification fixture'
    $env:WINDOWS_SIGNING_SUBJECT = ''
    $rejected = $false
    try { & "$PSScriptRoot/verify_windows_signature.ps1" -FilePath $unsigned } catch {
        if ($_.Exception.Message -notlike 'WINDOWS_SIGNING_SUBJECT*') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw 'Verifier accepted an unconfigured publisher' }

    $env:WINDOWS_SIGNING_SUBJECT = 'CN=codebone verification fixture'
    $rejected = $false
    try { & "$PSScriptRoot/verify_windows_signature.ps1" -FilePath $unsigned } catch {
        if ($_.Exception.Message -notlike 'Invalid Authenticode signature*') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw 'Verifier accepted an unsigned file' }

    $hostFile = Join-Path $PSHOME 'pwsh.exe'
    $hostSignature = Get-AuthenticodeSignature -LiteralPath $hostFile
    if ($hostSignature.Status -ne 'Valid' -or $null -eq $hostSignature.TimeStamperCertificate) {
        throw 'The Microsoft PowerShell test host must have a trusted timestamped signature'
    }
    $rejected = $false
    try { & "$PSScriptRoot/verify_windows_signature.ps1" -FilePath $hostFile } catch {
        if ($_.Exception.Message -notlike 'Unexpected signing publisher*') { throw }
        $rejected = $true
    }
    if (-not $rejected) { throw 'Verifier accepted a different publisher' }
    $env:WINDOWS_SIGNING_SUBJECT = $hostSignature.SignerCertificate.Subject
    & "$PSScriptRoot/verify_windows_signature.ps1" -FilePath $hostFile
    Write-Output 'Passed: missing publisher, unsigned file, wrong publisher, genuine trusted signature.'
} finally {
    $env:WINDOWS_SIGNING_SUBJECT = $originalSubject
    Remove-Item -LiteralPath $unsigned -Force -ErrorAction SilentlyContinue
}
