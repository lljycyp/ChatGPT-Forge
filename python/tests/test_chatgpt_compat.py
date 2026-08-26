import json
import os
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from bridge.commands import (
    _append_codex_skin_args,
    _get_legacy_system_running_profile,
    get_codex_skin_sessions,
    _is_profile_running,
    _is_same_auth_account,
    _launch_default_codex,
    _resolve_configured_codex_app_path,
    _running_multi_profile_names,
    _stop_client_processes,
    export_profile_backup,
    ensure_codex_skin_sessions,
    set_launch_mode,
    set_codex_skin_enabled,
)
from core.codex_source import (
    _get_appx_package_version,
    _is_client_main_process,
    _find_appx_client_path,
    find_windowsapps_codex_path_by_package,
    portable_app_needs_update,
    prepare_portable_codex_path,
    read_running_codex_processes,
    read_source_signature,
    write_source_signature,
)
from core.auth_service import auth_kind
from core.app_server_service import AppServerClient, _exclusive_file_lock, _remove_temporary_directory
from core.profile_service import (
    get_auth_credentials_store,
    require_file_auth_store,
    sanitize_profile_config_text,
)
from core.usage_service import _map_app_server_usage


class ChatGptCompatibilityTest(unittest.TestCase):
    def test_switch_mode_skin_launches_regular_client_directly_with_cdp(self):
        process = SimpleNamespace(pid=88)
        with (
            patch("bridge.commands.load_config", return_value={}),
            patch("bridge.commands._resolve_codex_app_source_path", return_value=Path("C:/Apps/ChatGPT.exe")),
            patch("bridge.commands.db.load_profile_launch_settings", return_value={"args": [], "env": {}}),
            patch("bridge.commands.subprocess.Popen", return_value=process) as popen,
        ):
            result = _launch_default_codex("work", skin_port=19335)

        command = popen.call_args.args[0]
        self.assertEqual(command[0], "C:\\Apps\\ChatGPT.exe")
        self.assertIn("--remote-debugging-address=127.0.0.1", command)
        self.assertIn("--remote-debugging-port=19335", command)
        skin_session = result.get("skinSession")
        self.assertIsInstance(skin_session, dict)
        assert isinstance(skin_session, dict)
        self.assertEqual(skin_session["profileName"], "work")

    def test_switch_mode_skin_uses_portable_copy_for_store_client(self):
        process = SimpleNamespace(pid=89)
        store_path = Path("C:/Program Files/WindowsApps/OpenAI.Codex_1.0_x64/app/ChatGPT.exe")
        portable_path = "D:/Profiles/.shared/ChatGPTPortable/ChatGPT.exe"
        config = {"profile_root": "D:/Profiles"}
        with (
            patch("bridge.commands.load_config", return_value=config),
            patch("bridge.commands._resolve_codex_app_source_path", return_value=store_path),
            patch("bridge.commands.prepare_portable_codex_path", return_value=portable_path) as prepare,
            patch("bridge.commands.db.load_profile_launch_settings", return_value={"args": [], "env": {}}),
            patch("bridge.commands.subprocess.Popen", return_value=process) as popen,
        ):
            result = _launch_default_codex("work", skin_port=19335)

        prepare.assert_called_once()
        command = popen.call_args.args[0]
        self.assertEqual(command[0], str(Path(portable_path)))
        self.assertIn("--remote-debugging-port=19335", command)
        skin_session = result.get("skinSession")
        self.assertIsInstance(skin_session, dict)
        assert isinstance(skin_session, dict)
        self.assertEqual(skin_session["processId"], 89)

    def test_enabling_skin_restarts_running_switch_profile(self):
        config = {"launch_mode": "switch", "active_profile": "work", "codex_skin_enabled": False}
        with (
            patch("bridge.commands.load_config", return_value=config),
            patch("bridge.commands._running_codex_count", return_value=1),
            patch("bridge.commands._sync_active_auth_to_profile") as sync_auth,
            patch("bridge.commands._stop_running_codex_processes") as stop_clients,
            patch("bridge.commands.save_config") as save_config,
            patch("bridge.commands._allocate_codex_skin_port", return_value=19335),
            patch(
                "bridge.commands._launch_default_codex",
                return_value={"skinSession": {"profileName": "work", "port": 19335, "processId": 88}},
            ) as launch_client,
        ):
            result = set_codex_skin_enabled({"enabled": True})

        sync_auth.assert_called_once_with(config, "work")
        stop_clients.assert_called_once_with()
        save_config.assert_called_once_with(config)
        launch_client.assert_called_once_with("work", skin_port=19335)
        self.assertEqual(result["skinSessions"][0]["port"], 19335)

    @patch("bridge.commands._launch_profile_multi", return_value={})
    @patch("bridge.commands._stop_profile_multi")
    @patch("bridge.commands._running_multi_profile_names", return_value=["alpha"])
    @patch("bridge.commands.save_config")
    @patch("bridge.commands.load_config", return_value={"launch_mode": "multi", "codex_skin_enabled": True})
    def test_disabling_skin_restarts_multi_profile_without_cdp(
        self,
        _load_config,
        save_config,
        _running_profiles,
        stop_profile,
        launch_profile_multi,
    ):
        result = set_codex_skin_enabled({"enabled": False})

        config = {"launch_mode": "multi", "codex_skin_enabled": False}
        save_config.assert_called_once_with(config)
        stop_profile.assert_called_once_with(config, {"name": "alpha"})
        launch_profile_multi.assert_called_once_with(config, "alpha", set())
        self.assertEqual(result["skinSessions"], [])

    def test_entering_multi_mode_syncs_the_active_system_auth(self):
        config = {"launch_mode": "switch", "active_profile": "work"}
        with (
            patch("bridge.commands.load_config", return_value=config),
            patch("bridge.commands.save_config") as save_config,
            patch("bridge.commands._sync_active_auth_to_profile") as sync_auth,
        ):
            self.assertEqual(set_launch_mode({"mode": "multi"}), {"launchMode": "multi"})

        sync_auth.assert_called_once_with(config, "work")
        save_config.assert_called_once_with(config)

    @patch("bridge.commands._launch_profile_multi")
    @patch("bridge.commands._stop_profile_multi")
    @patch("bridge.commands._running_multi_profile_names", return_value=["alpha", "beta"])
    @patch("bridge.commands.save_config")
    @patch("bridge.commands.load_config", return_value={"launch_mode": "multi", "codex_skin_enabled": False})
    def test_enabling_codex_skin_restarts_running_multi_profiles(
        self,
        _load_config,
        save_config,
        _running_profiles,
        stop_profile,
        launch_profile_multi,
    ):
        seen_reserved_ports = []

        def launch_with_reserved_port(_config, profile_name, reserved_ports):
            seen_reserved_ports.append(set(reserved_ports))
            offset = len(seen_reserved_ports) - 1
            return {
                "skinSession": {
                    "profileName": profile_name,
                    "port": 19335 + offset,
                    "processId": 101 + offset,
                }
            }

        launch_profile_multi.side_effect = launch_with_reserved_port

        result = set_codex_skin_enabled({"enabled": True})

        config = {"launch_mode": "multi", "codex_skin_enabled": True}
        save_config.assert_called_once_with(config)
        self.assertEqual(
            stop_profile.call_args_list,
            [call(config, {"name": "alpha"}), call(config, {"name": "beta"})],
        )
        self.assertEqual(seen_reserved_ports, [set(), {19335}])
        self.assertEqual(
            [session["profileName"] for session in result["skinSessions"]],
            ["alpha", "beta"],
        )

    def test_codex_skin_appends_loopback_debugging_arguments(self):
        self.assertEqual(
            _append_codex_skin_args(["--start-minimized"], 19335),
            [
                "--start-minimized",
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=19335",
            ],
        )

    def test_codex_skin_rejects_conflicting_debugging_arguments(self):
        with self.assertRaisesRegex(ValueError, "remote-debugging"):
            _append_codex_skin_args(["--remote-debugging-port=9222"], 19335)

    def test_recovers_running_switch_skin_session_from_managed_client(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            shared_root = Path(temp_dir) / ".shared"
            executable = shared_root / "CodexPortableApp" / "ChatGPT.exe"
            config = {
                "profile_root": temp_dir,
                "launch_mode": "switch",
                "active_profile": "work",
                "codex_skin_enabled": True,
            }
            process = {
                "pid": 88,
                "executable_path": str(executable),
                "command_line": (
                    f'"{executable}" --remote-debugging-address=127.0.0.1 '
                    "--remote-debugging-port=19335"
                ),
            }
            with (
                patch("bridge.commands.load_config", return_value=config),
                patch("bridge.commands.read_running_codex_processes", return_value=[process]),
            ):
                result = get_codex_skin_sessions()

        self.assertEqual(
            result["skinSessions"],
            [{"profileName": "work", "port": 19335, "processId": 88}],
        )

    def test_skin_session_recovery_rejects_unmanaged_client(self):
        config = {
            "profile_root": "D:/Profiles",
            "launch_mode": "switch",
            "active_profile": "work",
            "codex_skin_enabled": True,
        }
        process = {
            "pid": 89,
            "executable_path": "C:/Other/ChatGPT.exe",
            "command_line": (
                '"C:/Other/ChatGPT.exe" --remote-debugging-address=127.0.0.1 '
                "--remote-debugging-port=19335"
            ),
        }
        with (
            patch("bridge.commands.load_config", return_value=config),
            patch("bridge.commands.read_running_codex_processes", return_value=[process]),
        ):
            self.assertEqual(get_codex_skin_sessions(), {"skinSessions": []})

    def test_ensure_skin_session_restarts_running_switch_client_without_cdp(self):
        config = {
            "launch_mode": "switch",
            "active_profile": "work",
            "codex_skin_enabled": True,
        }
        session = {"profileName": "work", "port": 19335, "processId": 90}
        with (
            patch("bridge.commands.get_codex_skin_sessions", return_value={"skinSessions": []}),
            patch("bridge.commands.load_config", return_value=config),
            patch("bridge.commands._running_codex_count", return_value=1),
            patch("bridge.commands._sync_active_auth_to_profile") as sync_auth,
            patch("bridge.commands._stop_running_codex_processes") as stop_clients,
            patch("bridge.commands._allocate_codex_skin_port", return_value=19335),
            patch("bridge.commands._launch_default_codex", return_value={"skinSession": session}) as launch_client,
        ):
            result = ensure_codex_skin_sessions()

        sync_auth.assert_called_once_with(config, "work")
        stop_clients.assert_called_once_with()
        launch_client.assert_called_once_with("work", skin_port=19335)
        self.assertEqual(result, {"skinSessions": [session]})

    def test_stale_app_server_lock_is_recovered(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "auth.json.app-server.lock"
            lock_path.write_text("12345", encoding="utf-8")
            with patch("core.app_server_service._is_process_running", return_value=False):
                with _exclusive_file_lock(lock_path, timeout_seconds=1):
                    self.assertEqual(lock_path.read_text(encoding="utf-8"), str(os.getpid()))
            self.assertFalse(lock_path.exists())

    def test_running_app_server_lock_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "auth.json.app-server.lock"
            lock_path.write_text("12345", encoding="utf-8")
            with patch("core.app_server_service._is_process_running", return_value=True):
                with self.assertRaises(TimeoutError):
                    with _exclusive_file_lock(lock_path, timeout_seconds=0):
                        pass
            self.assertEqual(lock_path.read_text(encoding="utf-8"), "12345")

    def test_new_client_entry_processes_and_portable_copy(self):
        self.assertTrue(_is_client_main_process({
            "name": "ChatGPT.exe",
            "command_line": '"C:\\Apps\\ChatGPT.exe"',
            "executable_path": "C:\\Apps\\ChatGPT.exe",
        }))
        self.assertFalse(_is_client_main_process({
            "name": "ChatGPT.exe",
            "command_line": '"C:\\Apps\\ChatGPT.exe" --type=renderer',
            "executable_path": "C:\\Apps\\ChatGPT.exe",
        }))
        self.assertFalse(_is_client_main_process({
            "name": "Codex.exe",
            "command_line": '"C:\\Apps\\resources\\codex.exe" app-server',
            "executable_path": "C:\\Apps\\resources\\codex.exe",
        }))

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package_app = root / "OpenAI.Codex_1.0_x64" / "app"
            resources = package_app / "resources"
            resources.mkdir(parents=True)
            (package_app / "ChatGPT.exe").write_bytes(b"chatgpt")
            (package_app / "Codex.exe").write_bytes(b"legacy")
            (resources / "codex.exe").write_bytes(b"app-server")

            with (
                patch("core.codex_source._find_appx_client_path", return_value=""),
                patch("core.codex_source.get_windowsapps_dir", return_value=root),
            ):
                self.assertEqual(find_windowsapps_codex_path_by_package(), str(package_app / "ChatGPT.exe"))

            self.assertEqual(
                _resolve_configured_codex_app_path(resources / "codex.exe"),
                package_app / "ChatGPT.exe",
            )

            profile_dir = root / "profile"
            old_copy = profile_dir / "CodexPortableApp"
            old_copy.mkdir(parents=True)
            (old_copy / "Codex.exe").write_bytes(b"old")
            portable_path = Path(prepare_portable_codex_path(package_app / "ChatGPT.exe", profile_dir))
            self.assertEqual(portable_path, old_copy / "ChatGPT.exe")
            self.assertTrue(portable_path.exists())
            self.assertGreater(read_source_signature(old_copy)["directory_size"], 0)
            self.assertEqual(_get_appx_package_version(package_app / "ChatGPT.exe"), "1.0")
            legacy_signature = read_source_signature(old_copy)
            legacy_signature.pop("package_version")
            write_source_signature(old_copy, legacy_signature)
            self.assertFalse(portable_app_needs_update(package_app / "ChatGPT.exe", old_copy))
            self.assertEqual(read_source_signature(old_copy)["package_version"], "1.0")

    def test_cim_process_and_appx_manifest_payloads_are_parsed(self):
        process_payload = json.dumps([
            {
                "Name": "ChatGPT.exe",
                "ProcessId": 123,
                "ExecutablePath": "C:\\Apps\\ChatGPT.exe",
                "CommandLine": '"C:\\Apps\\ChatGPT.exe"',
            },
            {
                "Name": "ChatGPT.exe",
                "ProcessId": 124,
                "ExecutablePath": "C:\\Apps\\ChatGPT.exe",
                "CommandLine": '"C:\\Apps\\ChatGPT.exe" --type=renderer',
            },
        ])
        appx_payload = json.dumps([
            {"Path": "C:\\Apps\\ChatGPT.exe", "Version": "26.707.1.0"},
        ])
        with patch("core.codex_source.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = process_payload
            self.assertEqual(read_running_codex_processes()[0]["pid"], 123)
            run.return_value.stdout = appx_payload
            with patch("core.codex_source.Path.is_file", return_value=True):
                self.assertEqual(_find_appx_client_path(), "C:\\Apps\\ChatGPT.exe")

    def test_auth_modes_and_credential_store_are_explicit(self):
        self.assertEqual(auth_kind({"OPENAI_API_KEY": "sk-test"}), "api")
        self.assertEqual(auth_kind({"tokens": {"access_token": "token"}}), "chatgpt")

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            self.assertEqual(get_auth_credentials_store(config_path), "file")
            config_path.write_text('cli_auth_credentials_store = "keyring"\n', encoding="utf-8")
            self.assertEqual(get_auth_credentials_store(config_path), "keyring")
            with self.assertRaisesRegex(RuntimeError, "keyring"):
                require_file_auth_store(config_path)

    def test_new_usage_fields_are_mapped(self):
        usage = _map_app_server_usage(
            {"type": "chatgpt", "planType": "team"},
            {
                "rateLimits": {
                    "primary": {"windowDurationMins": 300, "usedPercent": 25},
                    "secondary": {"windowDurationMins": 10080, "usedPercent": 8},
                    "credits": {"hasCredits": True, "unlimited": False},
                    "rateLimitReachedType": "primary",
                },
                "rateLimitResetCredits": {
                    "availableCount": 3,
                    "credits": [
                        {"status": "available", "expiresAt": 2000},
                        {"status": "used", "expiresAt": 1000},
                        {"status": "available", "expiresAt": 3000},
                    ],
                },
            },
        )
        self.assertEqual(usage["resetCredits"], 3)
        self.assertEqual(usage["resetCreditExpiresAt"], [2000, 3000])
        self.assertTrue(usage["hasCredits"])
        self.assertFalse(usage["creditsUnlimited"])
        self.assertTrue(usage["spendControlReached"])
        self.assertEqual(usage["planType"], "team")
        self.assertEqual(usage["oneWeek"]["remainingPercent"], 92)

    def test_weekly_usage_is_mapped_without_legacy_window(self):
        usage = _map_app_server_usage(
            {"type": "chatgpt", "planType": "team"},
            {
                "rateLimits": {
                    "primary": {"windowDurationMins": 10080, "usedPercent": 2},
                },
            },
        )

        self.assertEqual(usage["oneWeek"]["remainingPercent"], 98)

    def test_app_server_temp_cleanup_retries_marketplace_race(self):
        path = Path(tempfile.gettempdir()) / "codex-forge-account-test"
        directory_not_empty = OSError(145, "目录不是空的", str(path / ".git"))
        with (
            patch("core.app_server_service.shutil.rmtree", side_effect=(directory_not_empty, None)) as rmtree,
            patch("core.app_server_service.time.sleep") as sleep,
        ):
            _remove_temporary_directory(path)

        self.assertEqual(rmtree.call_count, 2)
        sleep.assert_called_once()

    def test_windows_app_server_exit_kills_process_tree_before_closing_stdin(self):
        events = Mock()
        process = Mock(pid=12345)
        process.poll.side_effect = (None, 0)
        process.stdin.close.side_effect = lambda: events.stdin_closed()
        client = AppServerClient("C:\\Temp\\codex-home", "C:\\Temp\\codex.exe")
        client.process = process

        with (
            patch("core.app_server_service.os.name", "nt"),
            patch("core.app_server_service.subprocess.run", side_effect=lambda *args, **kwargs: events.tree_killed()),
        ):
            client.__exit__(None, None, None)

        self.assertEqual(events.mock_calls, [call.tree_killed(), call.stdin_closed()])
        process.wait.assert_called_once_with(timeout=3)

    def test_profile_config_removes_chatgpt_runtime_state(self):
        source = """model = "gpt-test"
notify = ["C:\\Users\\me\\AppData\\Local\\OpenAI\\Codex\\runtimes\\notify.exe"]
cli_auth_credentials_store = "auto"

[mcp_servers.node_repl]
command = "runtime.exe"

[mcp_servers.node_repl.env]
CODEX_HOME = "C:\\Users\\me\\.codex"

[marketplaces.openai-bundled]
source = "C:\\Users\\me\\.codex\\.tmp"

[mcp_servers.user_service]
command = "user-service.exe"

[hooks.state]
trusted_hash = "dynamic"
"""
        sanitized = sanitize_profile_config_text(source)
        tomllib.loads(sanitized)
        self.assertIn('cli_auth_credentials_store = "file"', sanitized)
        self.assertIn('model = "gpt-test"', sanitized)
        self.assertIn("[mcp_servers.user_service]", sanitized)
        self.assertNotIn("node_repl", sanitized)
        self.assertNotIn("openai-bundled", sanitized)
        self.assertNotIn("trusted_hash", sanitized)
        self.assertNotIn("notify =", sanitized)

    def test_portable_copy_reports_progress_and_keeps_old_copy_on_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            (source / "ChatGPT.exe").write_bytes(b"new-client")
            profile = root / "profile"
            old_copy = profile / "CodexPortableApp"
            old_copy.mkdir(parents=True)
            (old_copy / "ChatGPT.exe").write_bytes(b"old-client")
            progress = []

            result = prepare_portable_codex_path(
                source / "ChatGPT.exe",
                profile,
                progress_callback=lambda percent, _copied, _total: progress.append(percent),
            )
            self.assertEqual(Path(result).read_bytes(), b"new-client")
            self.assertEqual(progress[0], 0)
            self.assertEqual(progress[-1], 100)

            (source / "ChatGPT.exe").write_bytes(b"newer-client")
            with patch("core.codex_source._copy_app_directory", side_effect=OSError("copy failed")):
                with self.assertRaisesRegex(OSError, "copy failed"):
                    prepare_portable_codex_path(source / "ChatGPT.exe", profile)
            self.assertEqual((old_copy / "ChatGPT.exe").read_bytes(), b"new-client")

    def test_portable_copy_checks_free_disk_space_before_copying(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            (source / "ChatGPT.exe").write_bytes(b"client")
            with (
                patch("core.codex_source.get_directory_size", return_value=1024),
                patch("core.codex_source.shutil.disk_usage", return_value=SimpleNamespace(free=0)),
            ):
                with self.assertRaisesRegex(OSError, "磁盘空间不足"):
                    prepare_portable_codex_path(source / "ChatGPT.exe", root / "profile")

    def test_profile_backup_excludes_portable_client_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            profile_dir = root / "profiles" / "work"
            portable_dir = profile_dir / "CodexPortableApp"
            portable_dir.mkdir(parents=True)
            (profile_dir / "auth.json").write_text("{}", encoding="utf-8")
            (portable_dir / "ChatGPT.exe").write_bytes(b"client")
            codex_home = profile_dir / "CodexHome"
            codex_home.mkdir()
            (codex_home / "auth.json").write_text('{"runtime":true}', encoding="utf-8")
            (codex_home / "config.toml").write_text("model = 'test'", encoding="utf-8")
            (codex_home / "logs_2.sqlite").write_bytes(b"runtime-state")
            plugin_dir = codex_home / "plugins" / "cached-plugin"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "SKILL.md").write_text("runtime plugin", encoding="utf-8")
            app_data = profile_dir / "AppData" / "Roaming"
            app_data.mkdir(parents=True)
            (app_data / "Cookies").write_bytes(b"browser-state")
            config = {"profile_root": str(root / "profiles"), "profiles": ["work"]}

            with (
                patch("bridge.commands.load_config", return_value=config),
                patch("bridge.commands.db.get_profile", return_value={"dir_name": "work"}),
            ):
                result = export_profile_backup({"name": "work", "targetDir": str(root)})

            with zipfile.ZipFile(result["backupPath"]) as archive:
                self.assertNotIn("auth.json", archive.namelist())
                self.assertNotIn("CodexHome/auth.json", archive.namelist())
                self.assertIn("CodexHome/config.toml", archive.namelist())
                self.assertFalse(any(name.startswith("CodexPortableApp/") for name in archive.namelist()))
                self.assertFalse(any(name.startswith("AppData/") for name in archive.namelist()))
                self.assertNotIn("CodexHome/logs_2.sqlite", archive.namelist())
                self.assertNotIn("CodexHome/plugins/cached-plugin/SKILL.md", archive.namelist())

    def test_stop_requests_graceful_exit_before_force(self):
        with (
            patch("bridge.commands.subprocess.run") as run,
            patch("bridge.commands.request_process_close") as request_close,
            patch("bridge.commands.time.monotonic", side_effect=(0, 6)),
        ):
            self.assertEqual(_stop_client_processes([{"pid": 123}]), 1)

        request_close.assert_called_once_with(123)
        self.assertEqual(len(run.call_args_list), 1)
        self.assertIn("/F", run.call_args_list[0].args[0])

    def test_api_key_accounts_use_non_reversible_identity_comparison(self):
        first = {"OPENAI_API_KEY": "sk-first"}
        self.assertTrue(_is_same_auth_account(first, {"OPENAI_API_KEY": "sk-first"}))
        self.assertFalse(_is_same_auth_account(first, {"OPENAI_API_KEY": "sk-second"}))
        self.assertFalse(_is_same_auth_account(first, {"tokens": {"access_token": "token"}}))

    def test_switch_mode_client_remains_associated_after_entering_multi_mode(self):
        config = {"launch_mode": "multi", "profiles": ["first", "second"]}
        with (
            patch("bridge.commands.read_running_codex_commands", return_value=""),
            patch("bridge.commands._get_legacy_system_running_profile", return_value="first"),
            patch("bridge.commands.db.get_profile", side_effect=lambda name: {"dir_name": name}),
        ):
            self.assertTrue(_is_profile_running(config, "first"))
            self.assertFalse(_is_profile_running(config, "second"))
            self.assertEqual(_running_multi_profile_names(config), ["first"])

    def test_legacy_system_client_is_matched_by_its_authenticated_account(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            system_auth_path = root / "system-auth.json"
            (root / "first").mkdir()
            (root / "second").mkdir()
            system_auth_path.write_text(json.dumps({"account": "first"}), encoding="utf-8")
            (root / "first" / "auth.json").write_text(json.dumps({"account": "first"}), encoding="utf-8")
            (root / "second" / "auth.json").write_text(json.dumps({"account": "second"}), encoding="utf-8")
            config = {"launch_mode": "multi", "profile_root": str(root), "profiles": ["first", "second"]}
            with (
                patch("bridge.commands.get_active_auth_path", return_value=system_auth_path),
                patch("bridge.commands.read_running_codex_processes", return_value=[{"command_line": '"C:\\Apps\\ChatGPT.exe"'}]),
                patch("bridge.commands._is_same_auth_account", side_effect=lambda left, right: left == right),
                patch("bridge.commands.db.get_profile", side_effect=lambda name: {"dir_name": name}),
            ):
                self.assertEqual(_get_legacy_system_running_profile(config), "first")


if __name__ == "__main__":
    unittest.main()
