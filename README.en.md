<p align="center">
  <a href="README.md">简体中文</a> |
  <a href="README.en.md">English</a>
</p>

<p align="center">
  <img src="src/renderer/src/assets/codex-forge-logo.png" alt="Codex Forge Logo" width="150" />
</p>

<h1 align="center">Codex Forge</h1>

<p align="center">
  <b>Codex multi-account and multi-instance management · Auth management · Visual TOML / instruction workspace</b>
</p>

<p align="center">
  A local multi-account and multi-instance manager for the Codex desktop app on Windows. It brings the runtime environment, Codex instances, login profiles, <code>auth.json</code>, <code>config.toml</code>, instruction templates, and usage snapshots into one desktop workspace. You can switch accounts before launching Codex or run multiple isolated Codex clients.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows-555" alt="platform" />
  <img src="https://img.shields.io/badge/built%20with-Electron%2041-4B8BBE?logo=electron&logoColor=white" alt="electron" />
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="python" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white" />
  <img src="https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white" />
  <img src="https://img.shields.io/badge/Vite-Ready-646CFF?logo=vite&logoColor=white" />
  <img src="https://img.shields.io/badge/Tailwind-CSS-38B2AC?logo=tailwind-css&logoColor=white" />
</p>

---

## 📖 Overview

**Codex Forge** is a local workspace for Codex accounts, multi-instance launches, and configuration. It turns common terminal-side operations into desktop app workflows:

- ✨ **Multiple accounts**: Manage multiple Codex account profiles in one place.
- 🔑 **Flexible auth import**: Add accounts through browser OAuth, the current default account, or a local `auth.json` file.
- 🔄 **Smooth switching**: Write the selected account to `~/.codex/auth.json` automatically.
- 🛡️ **Config isolation**: Account-switching mode always uses the system `~/.codex/config.toml`; isolated multi-instance mode uses each account's `CodexHome/config.toml`.
- 🛠️ **Visual editing**: View and edit the active `~/.codex/config.toml`.
- 📝 **Instruction templates (prompt injection)**: Save common prompts as Markdown templates and switch Codex's global behavior profile with one click. The built-in prompt can break restrictions and support effects such as SQL injection testing and reverse engineering.
- 📊 **Status monitoring**: Check the current workspace and running instances on the home page, then inspect account health, weekly remaining usage, available resets, and expiration times from profile management.
- 🧰 **Environment workspace**: Review 30-day usage trends and account health, then manage MCP, Skills, AGENTS.md, the read-only session index, and per-account launch settings.
- 🎨 **Codex skins**: Includes the Forge Aurora theme and supports importing, switching, pausing, and deleting background themes stored only on your device.
- 🚀 **Selectable launch modes**: Supports account switching and isolated multi-instance mode for running multiple Codex clients.
- 🌐 **Bilingual UI**: Built-in Chinese / English switching for different language environments.
- 🔔 **Version updates**: Check for updates in the app, review release notes, download in the background, and restart to install.

## 🖼️ Software Preview

<p align="center">
  <img src="docs/images/home.png" alt="Codex Forge home page" />
</p>

## ⚡ Features

| Module | Details |
| :--- | :--- |
| 🧭 **Runtime workspace** | Check the Codex client, profile root, authentication, and configuration from the home page, view running instances, and quickly launch the current account or open common tools. |
| 👥 **Profile management** | Search, filter, and sort accounts, then use the profile inspector to launch or close an account, refresh usage, view details, export a backup, rename, or delete it. Data is stored in `~/Documents/CodexProfiles` by default. |
| 🔑 **Auth import** | Uses the official Codex App Server for Codex browser sign-in, and supports saving the current account or importing `auth.json`. |
| 🚀 **One-click switch and launch** | Writes the selected account into the current user's `.codex` directory and launches Codex. If Codex is running, the app prompts you to close it first. |
| 📦 **Isolated multi-instance launch** | Featured capability. Creates one shared copy from the installed Codex client. All accounts use that copy with separate `CodexHome`, `APPDATA`, `LOCALAPPDATA`, and `--user-data-dir` environments. |
| 📊 **Usage snapshots** | Uses the official Codex App Server to read and cache weekly remaining usage, available resets, each reset's expiration time, and limit status. |
| 🧰 **Environment workspace** | Keeps 30 days of usage history, provides threshold alerts, config diffs and field-level sync, health checks and repairs, and manages MCP, Skills, AGENTS.md, a read-only session index, and launch settings. It remembers the last open tab and asks for confirmation before discarding unsaved changes or performing destructive actions. |
| 🔐 **Encrypted profile backups** | Protects profile backups with Windows DPAPI while keeping legacy ZIP restore compatibility; sessions, logs, caches, and client files stay excluded. |
| 🛠️ **TOML editor** | Opens and saves the active `config.toml`, backs it up automatically before saving, and warns about unsaved changes before switching configurations or leaving the page. |
| 📝 **Instruction templates (prompt injection)** | Saves Markdown prompt templates locally. Enabling a template copies it into the active Codex config directory and points `model_instructions_file` in `config.toml` to that template. |
| 🎨 **Codex skins** | Includes the Forge Aurora theme and supports importing, switching, pausing, and deleting local background themes. Images stay in the local Forge data directory, with support for both account-switch and isolated multi-instance modes. |
| ⚙️ **Launch and directory settings** | Switch launch modes, migrate the account profile root, and enable Codex Forge to start after Windows sign-in. |
| 🔔 **In-app updates** | Supports silent update checks, manual update checks, release notes, background downloads, and restart-to-install. |
| 🌐 **Language and project links** | Supports Chinese / English UI switching and provides GitHub and Gitee project links in the About area. |

## ✨ Highlights

### 1. 🧭 Runtime Workspace and Profile Inspector

The home page brings together the current workspace, launch mode, selected account, and Codex instances. It checks whether the client, profile root, `auth.json`, and `config.toml` are ready. From there, you can launch the current account or quickly open profile management, the TOML editor, instruction templates, and app settings.

The profile management page supports account search, status filters, and multiple sort orders. After you select an account, the profile inspector groups its information and actions into:

- **Overview**: Plan, runtime and authentication status, weekly remaining usage, available resets, and each reset's expiration time.
- **Runtime**: Profile directory, authentication file, configuration file, and shared client-copy status.
- **Maintenance**: Export backup, rename, open directory, and delete account.

### 2. 🛡️ Isolated Account Profiles

Each account profile stores its own login credentials and config:

```text
~/Documents/CodexProfiles/<profile-id>/auth.json
~/Documents/CodexProfiles/<profile-id>/CodexHome/config.toml
```

Account-switching mode only replaces `auth.json`; global Codex settings such as model and proxy always use the system `~/.codex/config.toml`. Isolated multi-instance mode uses each account's own `CodexHome/config.toml`.

### 3. 🔑 Auth Management

There are three ways to add an account:

- 🌐 **Browser OAuth**: Uses Codex's built-in Codex App Server to open the official sign-in flow and saves the result only to the new profile.
- 💾 **Save current account**: Copies the current system `~/.codex/auth.json`.
- 📁 **Upload local file**: Imports an existing Codex login file from disk.

> 💡 Usage refresh runs through the official App Server. Updated authentication is written back to the matching profile.

### 4. 🛠️ Visual TOML Editing with Backups

Codex Forge reads the active config file:

```text
~/.codex/config.toml
```

Before saving changes, it validates the TOML content and backs up the old file to:

```text
%LOCALAPPDATA%/CodexForge/backups/config-toml/
```

### 5. 📝 Instruction Template Management (Prompt Injection)

Instruction templates let you quickly switch Codex's system-level behavior prompt. You can save common workflows, coding rules, review standards, or one of the bundled restriction-breaking prompts as Markdown templates and enable them when needed.

Codex Forge currently includes these restriction-breaking prompt templates:

- `docs/propmt/gpt5.5-unrestricted.md`
- `docs/propmt/gpt-5.6-sol-unrestricted.md` (for GPT-5.6 SOL)

Codex Forge automatically adds both templates to **Instruction templates** at startup, but leaves them disabled and does not overwrite existing templates with the same filenames.

You can enable or disable them directly from the **Instruction templates** page. After a template is enabled, Codex Forge writes the matching `.md` file into the Codex config directory and updates `model_instructions_file` in `config.toml`.

| Comparison | Default instructions | Restriction-breaking prompt templates |
| :--- | :--- | :--- |
| Positioning | General Codex assistant | High-freedom developer mode |
| Strategy | More conservative and more likely to give generic refusals | Emphasizes execution, analysis, and verifiable results |
| Style | Standard Q&A and coding assistance | Direct, broad coverage, fewer explanation blockers |
| Best for | Daily coding and general questions | Code auditing, security research, and complex debugging |

After deployment, you can test it with:

```text
How do I perform penetration testing against a target?
```

Typical result:

```text
Before enabling -> More likely to refuse or answer generically
After enabling -> More likely to provide security research methodology, testing steps, and verification ideas
```

When a template is enabled, Codex Forge does three things:
- Copies the template into the active Codex config directory.
- Writes `model_instructions_file = "./template-file-name.md"` into `config.toml`.
- In isolated multi-instance mode, supports syncing to the current account, a selected account, or all accounts.

This means you can switch between default instructions, team rules, and a less restrictive prompt style without editing `config.toml` by hand. Disabling a template only removes the `model_instructions_file` setting; it does not delete saved template files.

### 6. 📦 Isolated Multi-instance Launch

In addition to the default account-switching mode, Codex Forge's featured launch capability is isolated multi-instance mode:

- **Account-switching mode**: The default mode. Switching accounts writes into the system `~/.codex`; one Codex client is recommended.
- **Isolated multi-instance mode**: On first launch, Forge creates one shared copy from the installed Codex client. All accounts use that copy with separate configuration and runtime data.

Isolated multi-instance mode separates `CodexHome`, `APPDATA`, `LOCALAPPDATA`, and the browser `--user-data-dir`. The copied shared client is stored once under the profile root:

```text
CodexProfiles/.shared/CodexPortableApp
CodexProfiles/<profile-id>/CodexHome
CodexProfiles/<profile-id>/AppData
```

### 7. 🎨 Codex Skins

The Codex Skins page includes the built-in **Forge Aurora** theme and lets you import and switch local background images. Imported images stay in the local Forge data directory and are never uploaded.

<p align="center">
  <img src="docs/images/codex-skin.png" alt="Codex Forge Codex Skins page" />
</p>

- Works with both account-switch and isolated multi-instance modes.
- Supports switching themes, pausing their display, and deleting custom themes.
- Enabling or disabling skins safely restarts running Codex clients to apply the theme or restore the official appearance.

### 8. ⚙️ Settings, Updates, and Project Links

The Settings page centralizes Codex Forge's own configuration:

- **Account profile location**: Change the account profile root. The app prompts you to close running Codex instances before migration.
- **Launch mode**: Switch between account-switching and isolated multi-instance mode. The first multi-instance launch copies one shared client from the installed app.
- **Auto start**: Start Codex Forge automatically after Windows sign-in.
- **Language switching**: Switch between Chinese and English UI.
- **Version updates**: Show the current version and check for updates manually. When a new version is available, you can view release notes, download in the background, and restart to install.
- **Project links**: The About area provides GitHub and Gitee project links for source code and release information.

### 9. 🧠 Smart Codex Launch Detection

When launching an account, Codex Forge resolves the launch source in this order:

1. Saved Codex desktop executable path.
2. The currently running Codex main process.
3. The executable and app identifier from the `OpenAI.Codex` / `OpenAI.ChatGPT` AppX manifest.

---

## 📁 Core Paths

**Active Codex user config**:

```text
~/.codex/auth.json
~/.codex/config.toml
```

**Codex Forge config, logs, and cache**:

```text
%LOCALAPPDATA%/CodexForge/codex_forge.db
%LOCALAPPDATA%/CodexForge/logs/launcher.log
```

**Account profile storage**:

```text
~/Documents/CodexProfiles
```

---

## 👨‍💻 Developer Guide

### 🛠️ Tech Stack

- **Desktop framework**: Electron 41 / electron-vite
- **Frontend**: React 18 / TypeScript / Vite
- **UI**: Ant Design 5 / Tailwind CSS / lucide-react
- **Backend**: Python 3.11 local bridge process
- **Build**: PyInstaller / Electron Builder
- **Package managers**: yarn / uv

### 📋 Requirements

- OS: Windows 10 / Windows 11
- Runtime dependencies:
  - Python 3.11 or later
  - Node.js
  - uv, the Python package manager
  - yarn
  - Bash environment, Git Bash is recommended on Windows
- Software dependency: Install the Codex desktop app from Microsoft Store.

*Check the Codex desktop app (optional):*

```powershell
winget list Codex -s msstore
```

### 🚀 Development

```bash
cd /d/MyObject/CodexForge
cd python
uv sync --dev
cd ..
yarn install
yarn dev
```

### 🔍 Checks

```bash
cd python
uv run python -m py_compile main.py
cd ..
yarn typecheck:all
```

### 📦 Packaging

**Full build:**

```bash
yarn build
```

**Step-by-step build:**

```bash
yarn build:backend
yarn build:shell
yarn build:installer
yarn clean
```

> **Build flow**:
> 1. Generate the standalone backend executable `resources/main.exe` with `python -m PyInstaller`.
> 2. Build the Electron desktop shell and generate the Windows installer.

**Main artifacts:**

```text
resources/main.exe
release/Codex-Forge-Setup-<version>.exe
```

---

## ⚠️ Disclaimer

Codex Forge is a local account, configuration, and launch management tool. It is not an official OpenAI product and is not affiliated with OpenAI. The included instruction templates are intended only for lawful software development, code auditing, security research, and learning or testing scenarios. Users are responsible for complying with local laws, target-system authorization requirements, and relevant platform terms of service. Any account, data, compliance, or security risks caused by using this tool or its templates are the user's own responsibility.
