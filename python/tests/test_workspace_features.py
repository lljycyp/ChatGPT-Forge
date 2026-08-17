import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from bridge import commands
from bridge.commands import _extract_toml_root, _remove_toml_root
from core import db
from core.secure_store import protect_bytes, unprotect_bytes
from core.workspace_service import (
    delete_mcp_server,
    install_skill,
    list_sessions,
    read_workspace,
    remove_skill,
    save_mcp_server,
    set_mcp_enabled,
)


class WorkspaceFeatureTests(unittest.TestCase):
    def test_shell_snapshot_reuses_one_process_snapshot(self):
        config = {"profiles": []}
        processes = [{"command_line": "Codex.exe --test"}]
        with (
            patch.object(commands, "load_config", return_value=config),
            patch.object(commands, "_normalize_profile_configs"),
            patch.object(commands, "ensure_builtin_instruction_templates"),
            patch.object(commands, "read_running_codex_processes", return_value=processes) as read_processes,
            patch.object(commands, "_build_app_state", return_value={"runningCount": 1}) as build_state,
            patch.object(commands, "_build_profile_summaries", return_value=[]) as build_profiles,
        ):
            result = commands.get_shell_snapshot()

        read_processes.assert_called_once_with()
        self.assertIs(build_state.call_args.args[1], processes)
        self.assertIs(build_profiles.call_args.args[2], processes)
        self.assertEqual({"appState": {"runningCount": 1}, "profiles": []}, result)

    def test_workspace_snapshot_groups_existing_reads(self):
        with (
            patch.object(commands, "get_usage_history", return_value={"items": []}) as get_history,
            patch.object(commands, "get_profile_health", return_value={"healthy": True}),
            patch.object(commands, "get_workspace", return_value={"codexHome": "home"}),
            patch.object(commands, "list_sessions", return_value={"items": []}) as list_session_items,
            patch.object(commands, "get_profile_launch_settings", return_value={"workingDir": ""}),
            patch.object(commands, "_require_profile_name", return_value="work"),
        ):
            result = commands.get_workspace_snapshot({"name": "work", "profileName": "work", "days": 7, "limit": 20})

        self.assertEqual("home", result["workspace"]["codexHome"])
        get_history.assert_called_once_with({"name": "work", "days": 7})
        list_session_items.assert_called_once_with({"profileName": "work", "limit": 20})

    def test_workspace_snapshot_reads_only_requested_sections(self):
        with (
            patch.object(commands, "get_usage_history") as get_history,
            patch.object(commands, "get_profile_health") as get_health,
            patch.object(commands, "get_workspace", return_value={"codexHome": "home"}) as get_workspace,
            patch.object(commands, "list_sessions") as list_session_items,
            patch.object(commands, "get_profile_launch_settings") as get_launch_settings,
            patch.object(commands, "_require_profile_name", return_value="work"),
        ):
            result = commands.get_workspace_snapshot(
                {"name": "work", "profileName": "work", "sections": ["workspace"]}
            )

        self.assertEqual({"workspace": {"codexHome": "home"}}, result)
        get_workspace.assert_called_once_with({"profileName": "work"})
        get_history.assert_not_called()
        get_health.assert_not_called()
        list_session_items.assert_not_called()
        get_launch_settings.assert_not_called()

    def test_profile_summaries_load_records_and_usage_once(self):
        config = {"profiles": ["work", "personal"], "launch_mode": "switch"}
        usage_cache = {"work": {"planType": "plus"}}
        with (
            patch.object(db, "list_profile_records", return_value=[
                {"display_name": "work", "id": "1", "dir_name": "1"},
                {"display_name": "personal", "id": "2", "dir_name": "2"},
            ]) as list_records,
            patch.object(db, "load_usage_cache", return_value=usage_cache) as load_usage,
            patch.object(db, "get_profile") as get_profile,
            patch.object(commands, "_get_legacy_system_running_profile", return_value=""),
            patch.object(commands, "_build_profile_summary", side_effect=[{"name": "work"}, {"name": "personal"}]) as build_summary,
        ):
            result = commands._build_profile_summaries(config, "", [])

        list_records.assert_called_once_with()
        load_usage.assert_called_once_with()
        get_profile.assert_not_called()
        self.assertIs(build_summary.call_args_list[0].kwargs["usage_cache"], usage_cache)
        self.assertEqual([{"name": "work"}, {"name": "personal"}], result)

    def test_usage_history_and_launch_settings_are_profile_scoped(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch("core.db.DB_PATH", Path(temp_dir) / "forge.db"):
            db.save_config({"profiles": ["work"]})
            now = time.time()
            db.save_usage_cache({"work": {"fetchedAt": now - 60, "oneWeek": {"remainingPercent": 80}, "error": None}})
            db.save_usage_cache({"work": {"fetchedAt": now, "oneWeek": {"remainingPercent": 70}, "error": None}})
            self.assertEqual([80, 70], [item["oneWeek"]["remainingPercent"] for item in db.load_usage_history("work", 30)])

            value = {"workingDir": temp_dir, "args": ["--test"], "env": {"HTTP_PROXY": "http://127.0.0.1:7890"}}
            db.save_profile_launch_settings("work", value)
            self.assertEqual(value, db.load_profile_launch_settings("work"))

    def test_mcp_crud_preserves_unrelated_toml(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text('model = "gpt-test"\n\n[features]\napps = true\n', encoding="utf-8")
            save_mcp_server(config_path, {"name": "demo", "command": "npx", "args": ["-y", "demo"], "env": {"TOKEN": "secret"}})
            workspace = read_workspace(temp_dir)
            self.assertEqual("demo", workspace["mcpServers"][0]["name"])
            self.assertIn('model = "gpt-test"', config_path.read_text(encoding="utf-8"))
            delete_mcp_server(config_path, "demo")
            self.assertNotIn("mcp_servers.demo", config_path.read_text(encoding="utf-8"))
            self.assertIn("[features]", config_path.read_text(encoding="utf-8"))

    def test_mcp_toggle_preserves_existing_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.toml"
            config_path.write_text(
                '[mcp_servers.demo]\ncommand = "npx"\nargs = ["-y", "demo"]\nstartup_timeout_sec = 20\n\n'
                '[mcp_servers.demo.env]\nTOKEN = "secret"\n',
                encoding="utf-8",
            )

            set_mcp_enabled(config_path, "demo", False)

            content = config_path.read_text(encoding="utf-8")
            workspace = read_workspace(temp_dir)
            self.assertIn("enabled = false", content)
            self.assertIn("startup_timeout_sec = 20", content)
            self.assertIn('TOKEN = "secret"', content)
            self.assertFalse(workspace["mcpServers"][0]["enabled"])

            save_mcp_server(
                config_path,
                {"name": "demo", "command": "npx", "args": ["-y", "demo"], "enabled": False},
            )
            self.assertFalse(read_workspace(temp_dir)["mcpServers"][0]["enabled"])

    def test_skill_remove_moves_to_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source-skill"
            source.mkdir()
            (source / "SKILL.md").write_text("# Skill", encoding="utf-8")
            codex_home = root / "codex-home"
            installed = install_skill(codex_home, source)
            self.assertTrue(Path(installed["path"]).is_dir())
            removed = remove_skill(codex_home, "source-skill")
            self.assertTrue(Path(removed["backupPath"]).is_dir())

    def test_session_index_is_read_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = Path(temp_dir) / "sessions" / "2026" / "sample.jsonl"
            session.parent.mkdir(parents=True)
            session.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "session_meta", "payload": {"id": "thread-1", "cwd": "D:\\Work"}}),
                        json.dumps({"type": "response_item", "payload": {"role": "user", "content": [{"type": "input_text", "text": "Fix startup bug"}]}}),
                    ]
                ),
                encoding="utf-8",
            )
            before = session.read_bytes()
            result = list_sessions(temp_dir)
            self.assertEqual("thread-1", result[0]["id"])
            self.assertEqual("Fix startup bug", result[0]["title"])
            self.assertEqual(before, session.read_bytes())

    def test_toml_root_selection(self):
        content = 'model = "a"\napproval = "ask"\n\n[mcp_servers.demo]\ncommand = "npx"\n\n[features]\napps = true\n'
        self.assertIn('model = "a"', _extract_toml_root(content, "model"))
        self.assertIn("[mcp_servers.demo]", _extract_toml_root(content, "mcp_servers"))
        self.assertNotIn("mcp_servers.demo", _remove_toml_root(content, "mcp_servers"))
        self.assertIn("[features]", _remove_toml_root(content, "mcp_servers"))

    @unittest.skipUnless(os.name == "nt", "DPAPI is Windows-only")
    def test_dpapi_round_trip(self):
        value = b"sensitive-backup"
        self.assertEqual(value, unprotect_bytes(protect_bytes(value)))


if __name__ == "__main__":
    unittest.main()
