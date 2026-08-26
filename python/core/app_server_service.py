import ctypes
import ctypes.wintypes
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import webbrowser
from collections import deque
from contextlib import contextmanager
from pathlib import Path

from core.constants import PORTABLE_APP_DIR_NAME
from core.path_utils import remove_readonly_path
from core.profile_service import sanitize_profile_config_text, write_profile_auth_json


APP_SERVER_REQUEST_TIMEOUT_SECONDS = 30
APP_SERVER_LOGIN_TIMEOUT_SECONDS = 300
TEMP_DIRECTORY_CLEANUP_ATTEMPTS = 20
CLIENT_INFO = {
    "name": "codex_forge",
    "title": "Codex Forge",
    "version": "0.2.0",
}


def read_account_and_rate_limits(profile_dir, auth_path, config_path):
    """通过官方 App Server 读取账号状态和 Codex 额度。"""
    auth_path = Path(auth_path)
    lock_path = auth_path.with_name(f".{auth_path.name}.app-server.lock")
    with _exclusive_file_lock(lock_path):
        with temporary_app_server_home(auth_path, config_path) as codex_home:
            try:
                with AppServerClient(codex_home, find_codex_cli_path(profile_dir)) as client:
                    account_result = client.request("account/read", {"refreshToken": False})
                    account = account_result.get("account") if isinstance(account_result, dict) else None
                    account = account if isinstance(account, dict) else {}
                    if account.get("type") != "chatgpt":
                        raise ValueError("API Key 账号不提供 Codex 套餐额度")
                    rate_limits = client.request("account/rateLimits/read")
            finally:
                _sync_temporary_auth(codex_home / "auth.json", auth_path)
    return account, rate_limits


def login_with_chatgpt_browser():
    """使用官方 App Server 完成 Codex 浏览器登录并返回 auth.json。"""
    with _managed_temporary_directory(prefix="codex-forge-login-") as codex_home:
        (codex_home / "config.toml").write_text(
            'cli_auth_credentials_store = "file"\n',
            encoding="utf-8",
        )
        with AppServerClient(codex_home, find_codex_cli_path()) as client:
            login = client.request(
                "account/login/start",
                {
                    "type": "chatgpt",
                    "useHostedLoginSuccessPage": True,
                    "appBrand": "chatgpt",
                },
            )
            auth_url = str(login.get("authUrl") or "")
            login_id = str(login.get("loginId") or "")
            if not auth_url or not login_id:
                raise RuntimeError("Codex 登录未返回有效授权地址")
            if not webbrowser.open(auth_url):
                raise RuntimeError(f"无法自动打开浏览器，请手动访问：{auth_url}")
            completed = client.wait_notification(
                "account/login/completed",
                lambda params: params.get("loginId") == login_id,
                APP_SERVER_LOGIN_TIMEOUT_SECONDS,
            )
            if not completed.get("success"):
                raise RuntimeError(str(completed.get("error") or "Codex 登录失败"))
            account_result = client.request("account/read", {"refreshToken": False})
            account = account_result.get("account") if isinstance(account_result, dict) else None
            if not isinstance(account, dict) or account.get("type") != "chatgpt":
                raise RuntimeError("Codex 登录完成，但 App Server 未返回有效账号")

        auth_path = codex_home / "auth.json"
        if not auth_path.exists():
            raise RuntimeError("Codex 登录成功，但未生成 auth.json")
        try:
            auth_json = json.loads(auth_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"读取 Codex 登录信息失败：{exc}") from exc
        if not isinstance(auth_json, dict):
            raise RuntimeError("Codex 登录信息格式无效")
        return auth_json


def find_codex_cli_path(profile_dir=None):
    """定位新版 Codex 内置的可执行 Codex App Server。"""
    candidates = []
    env_path = str(os.environ.get("CODEX_CLI_PATH") or "").strip()
    if env_path:
        candidates.append(Path(env_path))

    local_appdata = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    runtime_root = local_appdata / "OpenAI" / "Codex" / "bin"
    if runtime_root.exists():
        try:
            candidates.extend(
                sorted(runtime_root.glob("*/codex.exe"), key=lambda path: path.stat().st_mtime_ns, reverse=True)
            )
        except OSError:
            pass

    if profile_dir:
        profile_dir = Path(profile_dir)
        candidates.append(profile_dir.parent / ".shared" / PORTABLE_APP_DIR_NAME / "resources" / "codex.exe")

    command_path = shutil.which("codex")
    if command_path:
        candidates.append(Path(command_path))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("未找到 Codex 内置 Codex App Server，请更新或重新安装 Codex 桌面应用")


@contextmanager
def temporary_app_server_home(auth_path, config_path):
    """为一次账号查询创建最小、隔离且可自动清理的 CODEX_HOME。"""
    with _managed_temporary_directory(prefix="codex-forge-account-") as codex_home:
        shutil.copy2(auth_path, codex_home / "auth.json")
        config_text = ""
        if config_path and Path(config_path).exists():
            config_text = Path(config_path).read_text(encoding="utf-8")
        (codex_home / "config.toml").write_text(
            sanitize_profile_config_text(config_text),
            encoding="utf-8",
        )
        yield codex_home


@contextmanager
def _managed_temporary_directory(prefix):
    """等待 App Server 的 marketplace 子进程释放文件后再清理目录。"""
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield path
    finally:
        _remove_temporary_directory(path)


def _remove_temporary_directory(path):
    path = Path(path)
    for attempt in range(TEMP_DIRECTORY_CLEANUP_ATTEMPTS):
        try:
            shutil.rmtree(path, onerror=remove_readonly_path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt + 1 >= TEMP_DIRECTORY_CLEANUP_ATTEMPTS:
                raise
            time.sleep(min(0.1 * (attempt + 1), 0.5))


def _sync_temporary_auth(source_path, target_path):
    if not source_path.exists():
        return
    try:
        auth_json = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(auth_json, dict):
        write_profile_auth_json(target_path, auth_json)


@contextmanager
def _exclusive_file_lock(lock_path, timeout_seconds=60):
    """避免同一账号同时启动多个 App Server 刷新同一认证。"""
    lock_path = Path(lock_path)
    deadline = time.time() + timeout_seconds
    file_handle = None
    while True:
        try:
            file_handle = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(file_handle, str(os.getpid()).encode("utf-8"))
            break
        except FileExistsError:
            if _remove_stale_process_lock(lock_path):
                continue
            if time.time() >= deadline:
                raise TimeoutError(f"等待账号 App Server 锁超时：{lock_path}")
            time.sleep(0.08)
    try:
        yield
    finally:
        if file_handle is not None:
            os.close(file_handle)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _remove_stale_process_lock(lock_path):
    """锁内进程已退出时清理残留锁。"""
    try:
        owner_pid = int(lock_path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, OSError, TypeError, ValueError):
        return False
    if _is_process_running(owner_pid):
        return False
    try:
        if lock_path.read_text(encoding="utf-8").strip() != str(owner_pid):
            return False
        lock_path.unlink()
        return True
    except (FileNotFoundError, OSError):
        return False


def _is_process_running(pid):
    if pid <= 0:
        return False
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
        kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        kernel32.CloseHandle.restype = ctypes.wintypes.BOOL
        handle = kernel32.OpenProcess(0x00100000, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return ctypes.get_last_error() != 87
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


class AppServerClient:
    """Codex App Server 的最小 JSONL 客户端。"""

    def __init__(self, codex_home, executable):
        self.codex_home = Path(codex_home)
        self.executable = Path(executable)
        self.process = None
        self.messages = queue.Queue()
        self.stderr_lines = deque(maxlen=20)
        self.next_id = 1

    def __enter__(self):
        env = os.environ.copy()
        env["CODEX_HOME"] = str(self.codex_home)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            [str(self.executable), "app-server", "--listen", "stdio://"],
            cwd=str(self.executable.parent),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self._send({"method": "initialize", "id": 0, "params": {"clientInfo": CLIENT_INFO}})
        initialized = self._wait_for(
            lambda message: message.get("id") == 0,
            APP_SERVER_REQUEST_TIMEOUT_SECONDS,
        )
        if initialized.get("error"):
            raise RuntimeError(f"Codex App Server 初始化失败：{initialized['error']}")
        self._send({"method": "initialized", "params": {}})
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        process = self.process
        if process is None:
            return
        if os.name == "nt" and process.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if process.stdin:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is None:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)

    def request(self, method, params=None, timeout=APP_SERVER_REQUEST_TIMEOUT_SECONDS):
        request_id = self.next_id
        self.next_id += 1
        message = {"method": method, "id": request_id}
        if params is not None:
            message["params"] = params
        self._send(message)
        response = self._wait_for(lambda item: item.get("id") == request_id, timeout)
        if response.get("error"):
            error = response["error"]
            if isinstance(error, dict):
                error = error.get("message") or json.dumps(error, ensure_ascii=False)
            raise RuntimeError(str(error))
        result = response.get("result")
        return result if isinstance(result, dict) else {}

    def wait_notification(self, method, predicate, timeout):
        message = self._wait_for(
            lambda item: item.get("method") == method
            and isinstance(item.get("params"), dict)
            and predicate(item["params"]),
            timeout,
        )
        return message["params"]

    def _send(self, message):
        process = self.process
        if process is None or process.stdin is None:
            raise RuntimeError("Codex App Server 未启动")
        process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        process.stdin.flush()

    def _wait_for(self, predicate, timeout):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("等待 Codex App Server 响应超时")
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError("等待 Codex App Server 响应超时") from exc
            if message is None:
                detail = "\n".join(self.stderr_lines).strip()
                raise RuntimeError(detail or "Codex App Server 已退出")
            if predicate(message):
                return message

    def _read_stdout(self):
        process = self.process
        if process is None or process.stdout is None:
            self.messages.put(None)
            return
        for line in process.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self.messages.put(message)
        self.messages.put(None)

    def _read_stderr(self):
        process = self.process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            self.stderr_lines.append(line.rstrip())
