# Real Panorama Converter

**Create Minecraft Java Edition title-screen panorama resource packs from 360° images.**

Made by **real_eldho**.

Real Panorama Converter takes a 360-degree equirectangular image, projects it into Minecraft's six title-screen panorama textures, and creates a complete resource-pack folder and ZIP archive.

## Features

- Preview a source panorama and adjust its center by clicking the preview.
- Generate `panorama_0.png` through `panorama_5.png`.
- Select a Minecraft Java Edition target from the application's version list.
- Set the resource-pack name, description, and panorama-face resolution.
- Use a custom `pack.png` icon, validated as an exact 128 × 128 PNG.
- Automatically generate a default pack icon if no custom icon is selected.
- Export both a resource-pack folder and ZIP archive.
- Built-in tutorial and dark/light theme toggle.

## Supported target labels

The current application version lists:

`1.11`, `1.12`, `1.13`, `1.14`, `1.15`, `1.16`, `1.17`, `1.18`, `1.19`, `1.20`, `1.20.3`, `1.20.5`, `1.21`, `1.21.2`, `1.21.4`, `1.21.5`, `1.21.6`, `1.21.9`, `1.21.11`, `26.1`, `26.2`, `26.3`

The version-to-pack-metadata mapping is configured in `MINECRAFT_TARGETS` in `real_panorama_converter.py`. A major-version label does not guarantee that every minor release in that family uses the same resource-pack format. The application does not launch Minecraft or test compatibility in-game. Verify and test each exact Minecraft release before making compatibility claims.

## Source image requirements

- Use a full **360° equirectangular panorama**, not an ordinary perspective screenshot.
- Expected aspect ratio: **2:1** (width is twice the height).
- Recommended resolution: **4096 × 2048 pixels**.
- Supported formats: JPG, JPEG, PNG, WEBP, TIF, TIFF, and BMP.
- Non-2:1 images trigger a warning; results may be distorted or incomplete.

## Requirements

- Windows 10/11 for the provided EXE release.
- Python 3.12 or newer for running/building from source.
- Dependencies: NumPy and Pillow (see `requirements.txt`).

## Run from source

Create a virtual environment, install dependencies, and launch the program:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe real_panorama_converter.py
```

## Build the Windows EXE manually

Open PowerShell in the repository folder.

### 1. Create a virtual environment

```powershell
py -m venv .venv
```

If `py` is unavailable, use the full path to your Python executable:

```powershell
& "C:\Path\To\Python\python.exe" -m venv .venv
```

### 2. Install the project dependencies and PyInstaller

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --upgrade pyinstaller
```

### 3. Build the EXE

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name RealPanoramaConverter real_panorama_converter.py
```

The executable will be created at:

`dist\RealPanoramaConverter.exe`

Build the Windows executable on Windows. Test it before publishing.

## Install a generated resource pack

1. In Minecraft Java Edition, open **Options → Resource Packs → Open Pack Folder**.
2. Copy the generated ZIP (or resource-pack folder) into that directory.
3. Return to Minecraft and enable the pack.
4. Ensure the selected game version matches the target for which the pack was generated.

The ZIP contains `pack.mcmeta`, `pack.png`, and the six files under:

`assets/minecraft/textures/gui/title/background/`

## GitHub release checklist

1. Commit and push the source project to the repository.
2. Build and test `dist/RealPanoramaConverter.exe`.
3. Open the repository on GitHub and select **Releases → Draft a new release**.
4. Create a version tag (for example, `v1.1.0`).
5. Upload `RealPanoramaConverter.exe` from the `dist` folder as a release asset.
6. Add release notes and publish.

Do not commit `.venv`, `build`, `dist`, or generated panorama ZIP files. Keep the executable in GitHub Release assets.

## Project files

- `real_panorama_converter.py` — application source
- `requirements.txt` — Python dependencies
- `.gitignore` — excludes local environments and build output
- `.gitattributes` — consistent text-file handling
- `COPYRIGHT_AND_LICENSE.md` — licensing checklist

## License

This project is licensed under the **MIT License**. See the [`LICENSE`](LICENSE) file for details.
