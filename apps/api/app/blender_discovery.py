from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _windows_registry_paths() -> list[Path]:
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []

    paths: list[Path] = []
    locations = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    for hive, key_path in locations:
        try:
            with winreg.OpenKey(hive, key_path) as uninstall:
                for index in range(winreg.QueryInfoKey(uninstall)[0]):
                    try:
                        subkey_name = winreg.EnumKey(uninstall, index)
                        with winreg.OpenKey(uninstall, subkey_name) as app_key:
                            install_location = str(winreg.QueryValueEx(app_key, "InstallLocation")[0]).strip()
                            display_icon = str(winreg.QueryValueEx(app_key, "DisplayIcon")[0]).strip()
                    except (OSError, TypeError):
                        continue
                    if install_location:
                        paths.append(Path(install_location) / "blender.exe")
                    if display_icon:
                        icon_path = Path(display_icon.split(",", 1)[0].strip('"'))
                        paths.append(icon_path if icon_path.name.lower() == "blender.exe" else icon_path.parent / "blender.exe")
        except OSError:
            continue
    return paths


def blender_path() -> str | None:
    configured = os.getenv("BLENDER_PATH") or os.getenv("BLENDER_EXECUTABLE")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    for command in ("blender", "blender.exe"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))
    if sys.platform == "win32":
        candidates.extend(
            Path(path) / "blender.exe"
            for path in (
                r"C:\\Program Files\\Blender Foundation\\Blender 5.0",
                r"C:\\Program Files\\Blender Foundation\\Blender 4.5",
                r"C:\\Program Files\\Blender Foundation\\Blender 4.4",
                r"C:\\Program Files\\Blender Foundation\\Blender 4.3",
                r"C:\\Program Files\\Blender Foundation\\Blender 4.2",
                r"C:\\Program Files\\Blender Foundation\\Blender 4.1",
                r"C:\\Program Files\\Blender Foundation\\Blender 4.0",
            )
        )
        candidates.extend(_windows_registry_paths())
    seen: set[str] = set()
    for candidate in candidates:
        resolved = str(candidate.expanduser())
        if resolved.lower() in seen:
            continue
        seen.add(resolved.lower())
        if Path(resolved).is_file():
            return resolved
    return None
