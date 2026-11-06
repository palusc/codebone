# Releasing codebone 2.0

codebone supports macOS Apple Silicon. Existing
1.8 releases stay archived. App release `2.0a` maps to npm package `igotaboner@2.0.0-a` through
`scripts/npm_version.py`. Nothing is published by a local version bump.

The npm packages are `igotaboner` and `gotaboner`; the desktop app is `codebone`.
Both packages provide the `codebone`, `cb`, `igotaboner` and `gotaboner` commands.
After igotaboner is published, mark the old
`codebone-mcp` package as moved using npm deprecation metadata.

1. Review the changes and validate the macOS build.
2. Configure the npm package's trusted GitHub publisher for repository
   `palusc/codebone`, workflow `npm-release.yml`. No npm token is saved in source.
   A newly named npm package may require its first publication through an npm
   account before trusted publishing can be configured. Alternatively configure
   the GitHub repository secret `NPM_TOKEN` with package-publishing permissions
   for the initial release; enter its value only in GitHub Secrets, never in chat.
   Publishing `igotaboner` and marking the old package as moved each require
   authorization for the respective package. The old package move notice is a
   one-time `npm deprecate codebone-mcp "Renamed to igotaboner. Use npx -y igotaboner instead."`
   operation, performed after the first successful igotaboner publication.
3. Push a tag matching the checked-in version (such as `v2.0a`) at the reviewed source commit. The release workflow verifies the
   versions, builds and validates macOS before publishing its artifacts.
4. The npm publication workflow runs after the native release and marks the matching npm version as
   `latest`. An identical version already published directly from the cloud is
   verified and reused, allowing release retries without republishing. Verify the package and dist-tag on npm, then check Socket.dev after
   it indexes the new version.
5. Update the Homebrew formula URL and SHA-256 together using the generated macOS
   ZIP. Until then it intentionally references the last verified 1.8 archive.

Publication requires Git write access, enabled GitHub Actions and an authorized
npm publisher. Network access to `api.github.com` is required to observe workflow
runs from the cloud environment. A pushed tag is not evidence of a successful
build or published release.
