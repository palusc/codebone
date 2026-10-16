# Called for the application, bridge, Inno Setup uninstaller and final installer.
param([Parameter(Mandatory)][string]$FilePath)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$file = (Resolve-Path -LiteralPath $FilePath).Path
foreach ($name in @('WINDOWS_SIGNING_ENDPOINT', 'WINDOWS_SIGNING_ACCOUNT', 'WINDOWS_SIGNING_PROFILE', 'WINDOWS_SIGNING_SUBJECT')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Missing signing configuration: $name"
    }
}
Import-Module ArtifactSigning -RequiredVersion 0.1.20 -ErrorAction Stop
Invoke-ArtifactSigning -Endpoint $env:WINDOWS_SIGNING_ENDPOINT `
    -CodeSigningAccountName $env:WINDOWS_SIGNING_ACCOUNT `
    -CertificateProfileName $env:WINDOWS_SIGNING_PROFILE `
    -Files $file -FileDigest SHA256 `
    -TimestampRfc3161 'http://timestamp.acs.microsoft.com' -TimestampDigest SHA256 `
    -ExcludeEnvironmentCredential:$true -ExcludeManagedIdentityCredential:$true `
    -ExcludeWorkloadIdentityCredential:$true -ExcludeAzureCliCredential:$false `
    -ExcludeSharedTokenCacheCredential:$true -ExcludeVisualStudioCredential:$true `
    -ExcludeVisualStudioCodeCredential:$true -ExcludeAzurePowerShellCredential:$true `
    -ExcludeAzureDeveloperCliCredential:$true -ExcludeInteractiveBrowserCredential:$true
& "$PSScriptRoot/verify_windows_signature.ps1" -FilePath $file
