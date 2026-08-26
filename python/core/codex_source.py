import os
import json
import re
import shutil
import subprocess
import sys
import ctypes
import ctypes.wintypes
import time
import uuid
from pathlib import Path

from core.constants import PORTABLE_APP_DIR_NAME, SOURCE_VERSION_FILE_NAME
from core.path_utils import get_directory_size, normalize_path_for_match, remove_readonly_path


def read_running_codex_commands():
    """读取当前所有 Codex 相关进程的命令行。"""
    return normalize_path_for_match(
        "\n".join(process["command_line"] for process in read_running_codex_processes())
    )


def read_running_codex_processes():
    """读取当前所有 Codex 客户端主进程。"""
    script = r"""
$processes = Get-CimInstance Win32_Process -Filter "Name = 'ChatGPT.exe' OR Name = 'Codex.exe'"
@($processes | Select-Object Name, ProcessId, ExecutablePath, CommandLine) | ConvertTo-Json -Compress
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    items = payload if isinstance(payload, list) else [payload]
    candidates = [
        {
            "name": str(item.get("Name") or ""),
            "pid": int(item.get("ProcessId") or 0),
            "executable_path": str(item.get("ExecutablePath") or ""),
            "command_line": str(item.get("CommandLine") or ""),
        }
        for item in items
        if isinstance(item, dict) and item.get("ProcessId") and item.get("CommandLine")
    ]
    return [process for process in candidates if _is_client_main_process(process)]


def read_processes_in_directory(target_dir):
    """读取主程序或辅助程序位于指定目录内的进程，仅用于客户端副本更新。"""
    if os.name != "nt":
        return []
    env = os.environ.copy()
    env["CODEX_FORGE_PROCESS_ROOT"] = os.path.abspath(target_dir)
    script = r"""
$root = [IO.Path]::GetFullPath($env:CODEX_FORGE_PROCESS_ROOT).TrimEnd('\') + '\'
$processes = Get-CimInstance Win32_Process | Where-Object {
  $_.ExecutablePath -and $_.ExecutablePath.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)
}
@($processes | Select-Object Name, ProcessId, ParentProcessId, ExecutablePath, CommandLine) | ConvertTo-Json -Compress
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=env,
        )
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    items = payload if isinstance(payload, list) else [payload]
    return [
        {
            "name": str(item.get("Name") or ""),
            "pid": int(item.get("ProcessId") or 0),
            "parent_pid": int(item.get("ParentProcessId") or 0),
            "executable_path": str(item.get("ExecutablePath") or ""),
            "command_line": str(item.get("CommandLine") or ""),
        }
        for item in items
        if isinstance(item, dict) and item.get("ProcessId")
    ]


def _is_client_main_process(process):
    """排除 Chromium 子进程和新版内置 codex app-server。"""
    name = str(process.get("name") or "").lower()
    command_line = str(process.get("command_line") or "").lower()
    executable_path = normalize_path_for_match(process.get("executable_path") or "")
    if name not in ("chatgpt.exe", "codex.exe"):
        return False
    if "--type=" in command_line or " app-server" in command_line:
        return False
    return not (name == "codex.exe" and "\\resources\\codex.exe" in executable_path)


def find_windowsapps_codex_path():
    """自动查找微软商店版 Codex 主程序路径。"""
    running_path = find_running_codex_path()
    if running_path and is_windowsapps_codex_path(running_path):
        return running_path
    return find_windowsapps_codex_path_by_package() or find_windowsapps_codex_path_by_scan()


def find_windowsapps_codex_path_by_package():
    """按新版商店包结构优先定位 ChatGPT.exe。"""
    return _find_appx_client_path() or _find_windowsapps_client_path(("OpenAI.Codex_", "OpenAI.ChatGPT_"))


def _find_appx_client_path():
    """通过当前用户 AppX Manifest 获取真实主程序路径。"""
    if os.name != "nt":
        return ""
    script = r"""
$result = @()
foreach ($packageName in @('OpenAI.Codex', 'OpenAI.ChatGPT')) {
  $package = Get-AppxPackage -Name $packageName | Sort-Object Version -Descending | Select-Object -First 1
  if ($null -eq $package) { continue }
  $manifest = $package | Get-AppxPackageManifest
  foreach ($application in @($manifest.Package.Applications.Application)) {
    if ($null -eq $application -or -not $application.Executable) { continue }
    $path = Join-Path $package.InstallLocation $application.Executable
    if (Test-Path -LiteralPath $path) {
      $result += [pscustomobject]@{ Path = $path; Version = $package.Version.ToString() }
    }
  }
}
@($result) | ConvertTo-Json -Compress
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        return ""
    if result.returncode != 0 or not result.stdout.strip():
        return ""
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ""
    items = payload if isinstance(payload, list) else [payload]
    for item in items:
        path = Path(str(item.get("Path") or "")) if isinstance(item, dict) else Path()
        if path.is_file() and path.name.lower() in ("chatgpt.exe", "codex.exe"):
            return str(path)
    return ""


def find_windowsapps_codex_path_by_scan():
    """在 WindowsApps 目录里兜底查找已知客户端入口。"""
    return _find_windowsapps_client_path(("codex", "chatgpt", "openai"))


def _find_windowsapps_client_path(package_markers):
    windows_apps_dir = get_windowsapps_dir()
    if not windows_apps_dir.exists():
        return ""

    candidates = []
    try:
        children = list(windows_apps_dir.iterdir())
    except Exception:
        return ""

    for child in children:
        if not child.is_dir():
            continue
        lowered_name = child.name.lower()
        if not any(marker.lower() in lowered_name for marker in package_markers):
            continue
        for relative_path in ("app/ChatGPT.exe", "app/Codex.exe", "ChatGPT.exe", "Codex.exe"):
            candidate = child / relative_path
            if candidate.exists():
                candidates.append(candidate)
                break

    if not candidates:
        return ""
    candidates.sort(
        key=lambda path: (path.name.lower() == "chatgpt.exe", path.stat().st_mtime_ns),
        reverse=True,
    )
    return str(candidates[0])


def get_windowsapps_dir():
    """获取系统微软商店应用安装目录。"""
    program_files = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files"
    return Path(program_files) / "WindowsApps"


def is_windowsapps_codex_path(path):
    """判断路径是否为微软商店应用目录里的客户端主程序。"""
    path = Path(path)
    return (
        path.exists()
        and path.name.lower() in ("chatgpt.exe", "codex.exe")
        and "windowsapps" in normalize_path_for_match(path)
    )


def find_running_codex_path():
    """从正在运行的客户端主进程读取真实程序路径。"""
    for process in read_running_codex_processes():
        path = process.get("executable_path") or ""
        if path and Path(path).exists():
            return path
    return ""


def get_source_signature(codex_path):
    """读取源程序关键特征，用于判断账号副本是否需要更新。"""
    codex_path = Path(codex_path)
    try:
        stat = codex_path.stat()
    except OSError:
        return {}
    return {
        "source_path": str(codex_path),
        "source_dir": str(codex_path.parent),
        "package_version": _get_appx_package_version(codex_path),
        "file_version": get_file_version(codex_path),
        "size": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


def _get_appx_package_version(path):
    """从 WindowsApps 包目录名提取应用版本。"""
    normalized_parts = Path(path).parts
    for part in normalized_parts:
        match = re.match(r"OpenAI\.(?:Codex|ChatGPT)_([^_]+)_", part, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def get_file_version(path):
    """读取可执行文件版本号；读取失败时返回空文本。"""
    try:
        return read_windows_file_version(Path(path))
    except Exception:
        return ""


def read_source_signature(target_app_dir):
    """读取共享客户端副本记录的安装源版本信息。"""
    version_path = Path(target_app_dir) / SOURCE_VERSION_FILE_NAME
    if not version_path.exists():
        return {}
    try:
        return json.loads(version_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_source_signature(target_app_dir, signature):
    """写入共享客户端副本对应的安装源版本信息。"""
    version_path = Path(target_app_dir) / SOURCE_VERSION_FILE_NAME
    version_path.write_text(json.dumps(signature, ensure_ascii=False, indent=2), encoding="utf-8")


def portable_app_needs_update(source_codex_path, target_app_dir):
    """判断共享客户端副本是否缺失或落后于安装源。"""
    source_codex_path = Path(source_codex_path)
    target_app_dir = Path(target_app_dir)
    target_codex_path = target_app_dir / source_codex_path.name
    if not target_codex_path.exists():
        return True
    current_signature = get_source_signature(source_codex_path)
    saved_signature = read_source_signature(target_app_dir)
    if not saved_signature:
        return True
    if "package_version" not in saved_signature and all(
        saved_signature.get(key) == current_signature.get(key)
        for key in ("source_path", "file_version", "size", "modified_ns")
    ):
        saved_signature["package_version"] = current_signature.get("package_version", "")
        write_source_signature(target_app_dir, saved_signature)
        return False
    return any(
        saved_signature.get(key) != current_signature.get(key)
        for key in ("source_path", "package_version", "file_version", "size", "modified_ns")
    )


def prepare_portable_codex_path(source_codex_path, profile_dir, allow_update=True, progress_callback=None):
    """从安装源原子复制多开账号共用的 Codex 客户端副本。"""
    source_codex_path = Path(source_codex_path)
    source_app_dir = source_codex_path.parent
    profile_dir = Path(profile_dir)
    target_app_dir = profile_dir / PORTABLE_APP_DIR_NAME
    target_codex_path = target_app_dir / source_codex_path.name
    _recover_portable_copy(profile_dir, target_app_dir)
    if target_codex_path.exists() and not portable_app_needs_update(source_codex_path, target_app_dir):
        return str(target_codex_path)
    if target_codex_path.exists() and not allow_update:
        return str(target_codex_path)

    profile_dir.mkdir(parents=True, exist_ok=True)
    source_size = get_directory_size(source_app_dir)
    required_bytes = source_size + 128 * 1024 * 1024
    free_bytes = shutil.disk_usage(profile_dir).free
    if free_bytes < required_bytes:
        raise OSError(
            "磁盘空间不足：复制 Codex 客户端需要至少 "
            f"{required_bytes / 1024 ** 3:.2f} GB，当前可用 {free_bytes / 1024 ** 3:.2f} GB"
        )

    staging_dir = profile_dir / f".{PORTABLE_APP_DIR_NAME}.new-{uuid.uuid4().hex}"
    backup_dir = profile_dir / f".{PORTABLE_APP_DIR_NAME}.old-{uuid.uuid4().hex}"
    try:
        _copy_app_directory(source_app_dir, staging_dir, source_size, progress_callback)
        staging_codex_path = staging_dir / source_codex_path.name
        if not staging_codex_path.is_file():
            raise FileNotFoundError("Codex 客户端复制不完整，未找到主程序")
        signature = get_source_signature(source_codex_path)
        signature["directory_size"] = get_directory_size(staging_dir)
        write_source_signature(staging_dir, signature)
        if target_app_dir.exists():
            _replace_directory_with_retry(target_app_dir, backup_dir)
        try:
            _replace_directory_with_retry(staging_dir, target_app_dir)
        except Exception:
            if backup_dir.exists() and not target_app_dir.exists():
                _replace_directory_with_retry(backup_dir, target_app_dir)
            raise
        if backup_dir.exists():
            shutil.rmtree(backup_dir, onerror=remove_readonly_path)
    finally:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, onerror=remove_readonly_path)
        if backup_dir.exists() and target_app_dir.exists():
            shutil.rmtree(backup_dir, onerror=remove_readonly_path)

    return str(target_codex_path)


def _replace_directory_with_retry(source_dir, target_dir, timeout_seconds=3):
    """短暂重试 Windows 目录交换，并把持续占用转换为可操作的错误。"""
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            os.replace(source_dir, target_dir)
            return
        except PermissionError as exc:
            if getattr(exc, "winerror", None) not in (5, 32) or time.monotonic() >= deadline:
                raise RuntimeError("Codex 客户端副本仍被后台进程占用，请完全退出 Codex 后重试") from exc
            time.sleep(0.25)


def _recover_portable_copy(profile_dir, target_app_dir):
    """恢复上次异常中断留下的副本交换目录。"""
    old_dirs = sorted(profile_dir.glob(f".{PORTABLE_APP_DIR_NAME}.old-*"))
    if not target_app_dir.exists() and old_dirs:
        os.replace(old_dirs[-1], target_app_dir)
        old_dirs = old_dirs[:-1]
    for directory in old_dirs:
        if directory.is_dir():
            shutil.rmtree(directory, onerror=remove_readonly_path)
    for directory in profile_dir.glob(f".{PORTABLE_APP_DIR_NAME}.new-*"):
        if directory.is_dir():
            shutil.rmtree(directory, onerror=remove_readonly_path)


def _copy_app_directory(source_dir, target_dir, total_bytes, progress_callback=None):
    """复制客户端目录并按文件字节报告进度。"""
    copied_bytes = 0
    last_percent = 0
    if progress_callback:
        progress_callback(0, 0, total_bytes)
    for root, dirs, files in os.walk(source_dir):
        root_path = Path(root)
        relative = root_path.relative_to(source_dir)
        target_root = target_dir / relative
        target_root.mkdir(parents=True, exist_ok=True)
        dirs[:] = [name for name in dirs if not (root_path / name).is_symlink()]
        for file_name in files:
            source_file = root_path / file_name
            if source_file.is_symlink():
                continue
            target_file = target_root / file_name
            shutil.copy2(source_file, target_file)
            try:
                copied_bytes += source_file.stat().st_size
            except OSError:
                pass
            percent = 100 if total_bytes <= 0 else min(100, int(copied_bytes * 100 / total_bytes))
            if progress_callback and percent != last_percent:
                progress_callback(percent, copied_bytes, total_bytes)
                last_percent = percent
    if progress_callback and last_percent < 100:
        progress_callback(100, copied_bytes, total_bytes)


def request_process_close(pid):
    """向指定进程拥有的顶层窗口发送 WM_CLOSE。"""
    if sys.platform != "win32":
        return 0
    user32 = ctypes.windll.user32
    wm_close = 0x0010
    matched = 0
    callback_type = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    def callback(hwnd, _lparam):
        nonlocal matched
        process_id = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value == int(pid):
            user32.PostMessageW(hwnd, wm_close, 0, 0)
            matched += 1
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return matched


class VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", ctypes.wintypes.DWORD),
        ("dwStrucVersion", ctypes.wintypes.DWORD),
        ("dwFileVersionMS", ctypes.wintypes.DWORD),
        ("dwFileVersionLS", ctypes.wintypes.DWORD),
        ("dwProductVersionMS", ctypes.wintypes.DWORD),
        ("dwProductVersionLS", ctypes.wintypes.DWORD),
        ("dwFileFlagsMask", ctypes.wintypes.DWORD),
        ("dwFileFlags", ctypes.wintypes.DWORD),
        ("dwFileOS", ctypes.wintypes.DWORD),
        ("dwFileType", ctypes.wintypes.DWORD),
        ("dwFileSubtype", ctypes.wintypes.DWORD),
        ("dwFileDateMS", ctypes.wintypes.DWORD),
        ("dwFileDateLS", ctypes.wintypes.DWORD),
    ]


def read_windows_file_version(path):
    """通过 Windows Version API 读取文件版本号。"""
    if sys.platform != "win32":
        return ""
    version = ctypes.windll.version
    file_path = str(path)
    handle = ctypes.wintypes.DWORD()
    size = version.GetFileVersionInfoSizeW(file_path, ctypes.byref(handle))
    if not size:
        return ""

    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(file_path, 0, size, buffer):
        return ""

    value = ctypes.wintypes.LPVOID()
    value_size = ctypes.wintypes.UINT()
    if not version.VerQueryValueW(buffer, "\\", ctypes.byref(value), ctypes.byref(value_size)):
        return ""
    if value_size.value < ctypes.sizeof(VS_FIXEDFILEINFO):
        return ""

    info = ctypes.cast(value, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    return ".".join(
        str(part)
        for part in (
            info.dwFileVersionMS >> 16,
            info.dwFileVersionMS & 0xFFFF,
            info.dwFileVersionLS >> 16,
            info.dwFileVersionLS & 0xFFFF,
        )
    )
