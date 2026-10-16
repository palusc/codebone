# Windows publisher signing

The existing 2.0 release is unsigned. Enabling this pipeline does not change its
downloaded binaries. Publish a new patch version after configuring and validating
the real publisher; do not silently replace existing release files or checksums.

## Microsoft Artifact Signing setup

This integration uses Microsoft's Artifact Signing service and GitHub OIDC. No
certificate private key, PFX password or Azure client secret is stored in this
repository. The service requires an Azure subscription, applicable service fees
and Microsoft's publisher identity verification. Check current eligibility and
pricing before creating resources. This repository does not create paid resources.

1. Follow Microsoft's [Artifact Signing setup](https://learn.microsoft.com/azure/artifact-signing/quickstart).
   Complete identity validation and create a **Public Trust** certificate profile.
   A private-trust or self-signed certificate does not establish public trust.
2. Create an Entra application/service principal. Grant its
   **Artifact Signing Certificate Profile Signer** role at the certificate profile
   scope. Configure GitHub OIDC credentials with audience `api://AzureADTokenExchange`:
   `repo:palusc/codebone:ref:refs/heads/main` for manual validation, and the exact
   next release tag, for example `repo:palusc/codebone:ref:refs/tags/v2.0.1`.
   Do not authorize pull requests or untrusted branches to sign.
3. In GitHub **Settings → Secrets and variables → Actions → Variables**, set:

   | Variable | Value |
   | --- | --- |
   | `AZURE_CLIENT_ID` | Entra application/client ID |
   | `AZURE_TENANT_ID` | Entra directory/tenant ID |
   | `AZURE_SUBSCRIPTION_ID` | Subscription containing the signing account |
   | `WINDOWS_SIGNING_ENDPOINT` | The account's regional HTTPS endpoint |
   | `WINDOWS_SIGNING_ACCOUNT` | Artifact Signing account name |
   | `WINDOWS_SIGNING_PROFILE` | Public Trust certificate profile name |
   | `WINDOWS_SIGNING_SUBJECT` | Exact X.509 subject of the verified publisher certificate |

   Obtain the subject from the service certificate/profile; do not substitute the
   application name or relax signature verification to accept another publisher.
4. Run **Windows build and validation** on `main`, selecting `sign-windows`.
   The runner authenticates with OIDC, installs pinned `ArtifactSigning` 0.1.20
   from PSGallery, signs both bundled entry points, and lets Inno Setup sign the
   generated uninstaller and installer. Every signature must be trusted, match
   the configured subject, and carry a timestamp. ZIP/checksums are generated
   after signing. The installed copies are verified again before uninstall tests.
5. Inspect the signed artifact and native smoke-test results before publishing
   the next version tag. Public release workflows require signing; missing
   configuration or any signing failure stops the Windows release.

Unsigned development builds remain available with `sign-windows` unchecked. They
do not publish a GitHub release. These builds and the current 2.0 release can
trigger Windows SmartScreen. A trusted signature identifies the publisher;
SmartScreen also uses reputation, so a new signed application can still receive
warnings. Do not promise that signing immediately eliminates every warning.

For another signing provider, adapt the signing helper only after its genuine
publisher credentials and supported signing method are available.
