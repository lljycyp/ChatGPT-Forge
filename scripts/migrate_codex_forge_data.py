import argparse
import ctypes
import io
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from ctypes import wintypes
from pathlib import Path


OLD_MAGIC = b"CHATGPT-FORGE-DPAPI\x00"
NEW_MAGIC = b"CODEX-FORGE-DPAPI\x00"
OLD_META_NAME = "chatgpt-forge-profile.json"
NEW_META_NAME = "codex-forge-profile.json"
REPLACEMENTS = (
    ("ChatGPT Forge", "Codex Forge"),
    ("ChatGPTPortableApp", "CodexPortableApp"),
    ("ChatGPTForge", "CodexForge"),
    ("chatgptForge", "codexForge"),
    ("chatgpt-forge", "codex-forge"),
    ("chatgpt_forge", "codex_forge"),
    ("CHATGPT_FORGE", "CODEX_FORGE"),
)


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _to_blob(value: bytes):
    buffer = ctypes.create_string_buffer(value)
    blob = _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _unprotect(value: bytes) -> bytes:
    if os.name != "nt" or not value.startswith(OLD_MAGIC):
        raise ValueError("不是可迁移的旧版 Codex Forge 加密备份")
    source, source_buffer = _to_blob(value[len(OLD_MAGIC) :])
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(target)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def _protect(value: bytes) -> bytes:
    source, source_buffer = _to_blob(value)
    target = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source),
        "Codex Forge backup",
        None,
        None,
        None,
        0x1,
        ctypes.byref(target),
    ):
        raise ctypes.WinError()
    try:
        return NEW_MAGIC + ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def _replace_text(value: str) -> str:
    for old, new in REPLACEMENTS:
        value = value.replace(old, new)
    return value


def migrate_database(path: Path) -> dict:
    connection = sqlite3.connect(path)
    try:
        integrity_before = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity_before != "ok":
            raise RuntimeError(f"迁移前数据库校验失败: {integrity_before}")

        changed_rows = 0
        table_counts = {}
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        with connection:
            for (table_name,) in tables:
                quoted_table = '"' + table_name.replace('"', '""') + '"'
                table_counts[table_name] = connection.execute(
                    f"SELECT COUNT(*) FROM {quoted_table}"
                ).fetchone()[0]
                columns = connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()
                text_columns = [row[1] for row in columns if "TEXT" in str(row[2]).upper()]
                for column_name in text_columns:
                    quoted_column = '"' + column_name.replace('"', '""') + '"'
                    rows = connection.execute(
                        f"SELECT rowid, {quoted_column} FROM {quoted_table} WHERE {quoted_column} IS NOT NULL"
                    ).fetchall()
                    for rowid, value in rows:
                        migrated = _replace_text(value)
                        if migrated != value:
                            connection.execute(
                                f"UPDATE {quoted_table} SET {quoted_column} = ? WHERE rowid = ?",
                                (migrated, rowid),
                            )
                            changed_rows += 1

        integrity_after = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity_after != "ok":
            raise RuntimeError(f"迁移后数据库校验失败: {integrity_after}")
        return {"integrity": integrity_after, "changedRows": changed_rows, "tableCounts": table_counts}
    finally:
        connection.close()


def _rewrite_zip(raw: bytes) -> tuple[bytes, bool]:
    source = io.BytesIO(raw)
    target = io.BytesIO()
    changed = False
    with zipfile.ZipFile(source, "r") as input_archive, zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED
    ) as output_archive:
        for info in input_archive.infolist():
            name = info.filename
            data = input_archive.read(info)
            if name == OLD_META_NAME:
                name = NEW_META_NAME
                data = _replace_text(data.decode("utf-8")).encode("utf-8")
                changed = True
            output_archive.writestr(name, data)
    return target.getvalue(), changed


def migrate_backup(path: Path) -> bool:
    raw = path.read_bytes()
    secure = raw.startswith(OLD_MAGIC)
    payload = _unprotect(raw) if secure else raw
    try:
        migrated, changed = _rewrite_zip(payload)
    except zipfile.BadZipFile:
        return False
    if not changed and not secure:
        return False

    backup_path = path.with_name(f"{path.name}.pre-codex-forge-migration")
    if not backup_path.exists():
        shutil.copy2(path, backup_path)
    output = _protect(migrated) if secure else migrated
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp_file:
        temp_file.write(output)
        temp_path = Path(temp_file.name)
    temp_path.replace(path)
    return True


def migrate_backup_roots(roots: list[Path]) -> list[str]:
    migrated = []
    for root in roots:
        if not root.exists():
            continue
        candidates = list(root.rglob("*.forgebackup")) + list(root.rglob("*.zip"))
        for path in candidates:
            if migrate_backup(path):
                migrated.append(str(path))
    return migrated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--backup-root", action="append", type=Path, default=[])
    args = parser.parse_args()
    result = {
        "database": migrate_database(args.database),
        "migratedBackups": migrate_backup_roots(args.backup_root),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
