param([Parameter(Mandatory)][string]$FilePath)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ([string]::IsNullOrWhiteSpace($env:WINDOWS_SIGNING_SUBJECT)) {
    throw 'WINDOWS_SIGNING_SUBJECT must match the verified publisher certificate subject.'
}
$signature = Get-AuthenticodeSignature -LiteralPath $FilePath
if ($signature.Status -ne 'Valid') {
    throw "Invalid Authenticode signature for ${FilePath}: $($signature.Status)"
}
if ($null -eq $signature.SignerCertificate -or $signature.SignerCertificate.Subject -cne $env:WINDOWS_SIGNING_SUBJECT) {
    throw "Unexpected signing publisher for $FilePath"
}
if ($null -eq $signature.TimeStamperCertificate) {
    throw "Missing trusted timestamp for $FilePath"
}
Write-Output "Verified trusted, timestamped publisher signature: $FilePath"
