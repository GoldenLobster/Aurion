# GitHub Actions Release Pipeline

This project uses GitHub Actions to automatically build and release executables for Windows, macOS, and Linux.

## How It Works

1. **Automatic Triggers**: Every push to the `main` or `master` branch triggers the build pipeline
2. **Version Numbering**: Versions are automatically calculated based on commit count:
   - First version: 1.0
   - Second version: 1.1
   - Third version: 1.2
   - And so on...

3. **Multi-Platform Builds**:
   - Windows: Builds `Aurion.exe` using PyInstaller
   - macOS: Builds a `.app` bundle
   - Linux: Builds a standalone executable

4. **Automatic Releases**: After successful builds, the following happens:
   - A GitHub release is created with tag `v1.0`, `v1.1`, etc.
   - All platform-specific executables are packaged and attached as release assets:
     - `Aurion-1.0-windows.zip`
     - `Aurion-1.0-macos.zip`
     - `Aurion-1.0-linux.tar.gz`

## Setup Requirements

The workflow uses the following GitHub secrets (automatically available):
- `GITHUB_TOKEN`: Already configured by GitHub Actions

## For Users

Users can download pre-built executables from the [Releases](../../releases) page without needing to build from source.

## For Developers

To trigger a new release, simply commit and push to `main` or `master`:

```bash
git add .
git commit -m "Your changes"
git push origin main
```

The CI/CD pipeline will automatically:
1. Build executables for all three platforms
2. Create a new release
3. Upload the executables for download

## Build Configuration

The builds are configured in `.github/workflows/build-release.yml` and include:
- PyInstaller with windowed mode
- Icon bundling from `src/Icons/logo.ico`
- Data bundling of the entire `src/` folder
