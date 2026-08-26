<p align="center">
  <a href="README.md">简体中文</a> |
  <a href="README.en.md">English</a>
</p>

<p align="center">
  <img src="src/renderer/src/assets/codex-forge-logo.png" alt="Codex Forge Logo" width="150" />
</p>

<h1 align="center">Codex Forge</h1>

<p align="center">
  <b>ChatGPT 多账号多开 · Auth 管理 · TOML / 指令模板可视化工作台</b>
</p>

<p align="center">
  面向 Windows ChatGPT 桌面应用的本地多账号与多开管理工具。它将运行环境、ChatGPT 实例、多个登录资料、<code>auth.json</code>、<code>config.toml</code>、指令模板和额度快照集中到一个桌面工作台中，既可切换账号后启动 ChatGPT，也可用隔离环境同时多开多个 ChatGPT 客户端。
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

## 📖 简介

**Codex Forge** 是一个面向 ChatGPT 桌面应用的**本地多账号、多开与配置工作台**。它将日常高频的终端操作转化为直观的桌面应用功能：

- ✨ **多账号管理**：集中管理多个 ChatGPT 账号资料。
- 🔑 **灵活授权**：支持通过浏览器授权、保存当前默认账号，或导入本地 `auth.json` 来新增账号。
- 🔄 **无缝切换**：切换账号时自动写入当前用户的 `~/.codex/auth.json`。
- 🛡️ **配置隔离**：账号切换模式固定使用系统 `~/.codex/config.toml`；多开隔离模式使用账号 `CodexHome/config.toml`。
- 🛠️ **可视化编辑**：提供查看和编辑当前生效的 `~/.codex/config.toml` 的可视化界面。
- 📝 **指令模板（提示词注入）**：把常用提示词保存成 Markdown 模板，一键切换 ChatGPT 的全局行为设定，使用内置提示词可实现破除限制，可实现 SQL 注入测试、逆向等效果。
- 📊 **状态监控**：在首页检查当前工作环境和运行实例，并在账号管理页查看账号健康状态、一周剩余额度、可刷新次数及过期时间。
- 🧰 **环境工作台**：查看30天额度趋势和账号健康检查，并管理 MCP、Skills、AGENTS.md、会话索引与账号启动环境。
- 🎨 **Codex 换肤**：内置 Forge Aurora 主题，支持导入、切换、暂停和删除仅保存在本机的背景主题。
- 🚀 **可选启动模式**：支持稳定的账号切换模式，也支持多开隔离模式并发启动多个 ChatGPT 客户端。
- 🌐 **双语界面**：内置中文 / English 切换，适合不同语言环境下使用。
- 🔔 **版本更新**：支持应用内检查更新、查看更新内容、后台下载并重启安装。

## 🖼️ 软件预览

<p align="center">
  <img src="docs/images/home.png" alt="Codex Forge 首页" />
</p>

## ⚡ 功能特性

| 功能模块                      | 详细说明                                                                                                                                              |
| :---------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------- |
| 🧭 **运行工作台**             | 在首页集中检查 ChatGPT 客户端、账号目录、认证与配置状态，查看运行实例，并快捷启动当前账号或进入常用功能。                                             |
| 👥 **账号资料管理**           | 支持搜索、筛选和排序账号，并通过账号检查器集中完成启动、关闭、额度刷新、详情查看、备份、改名和删除，数据默认保存在 `~/Documents/CodexProfiles`。       |
| 🔑 **授权导入**               | 通过官方 Codex App Server 完成 ChatGPT 浏览器登录，也支持保存当前账号或导入本地 `auth.json`。                                                        |
| 🚀 **一键切换启动**           | 账号切换模式下自动写入当前用户 `.codex` 目录并启动 ChatGPT。若检测到 ChatGPT 正在运行会提示先关闭。                                                  |
| 📦 **多开隔离启动**           | 特色功能。从系统已安装的 ChatGPT 客户端复制出一份共享副本，所有账号共用该副本，并分别隔离 `CodexHome`、`APPDATA`、`LOCALAPPDATA` 和 `--user-data-dir`。 |
| 📊 **额度快照**               | 通过官方 Codex App Server 读取并缓存 ChatGPT 账号的一周剩余额度、可刷新次数、每次刷新的过期时间与限制状态。                                           |
| 🧰 **环境工作台**             | 保留30天额度历史，提供阈值告警、配置差异与字段级同步、健康检查与修复，并集中管理 MCP、Skills、AGENTS.md、只读会话索引和账号启动环境；支持记住上次打开的标签页，在存在未保存修改或执行危险操作时给出确认提醒。 |
| 🔐 **加密账号备份**           | 账号备份使用当前 Windows 用户的 DPAPI 加密，继续兼容恢复旧版 ZIP；会话、日志、缓存和客户端程序不会进入备份。                                        |
| 🛠️ **TOML 编辑**              | 直接查看和保存当前生效的 `config.toml`，保存前自动备份；切换配置或离开页面时会提醒尚未保存的修改。                                                     |
| 📝 **指令模板（提示词注入）** | 本地保存 Markdown（标记语言）提示词模板，启用后复制到当前 ChatGPT 配置目录，并把 `config.toml` 的 `model_instructions_file` 指向该模板。              |
| 🎨 **Codex 换肤**             | 内置 Forge Aurora 主题，支持导入、切换、暂停和删除本地背景主题；图片只保存在本机 Forge 数据目录，并支持账号切换与多开隔离模式。                       |
| ⚙️ **启动与目录设置**         | 支持切换启动模式、迁移账号资料根目录，并可开启 Windows 登录后自动启动 Codex Forge。                                                                 |
| 🔔 **应用内更新**             | 支持静默检查新版本、手动检查更新、查看发布说明、后台下载更新包并重启安装。                                                                            |
| 🌐 **语言与项目入口**         | 支持中文 / English 界面切换，并在关于区域提供 GitHub 与 Gitee 项目入口。                                                                               |

## ✨ 核心亮点

### 1. 🧭 运行工作台与账号检查器

首页会集中展示当前工作环境、运行模式、所选账号和 ChatGPT 实例，并检查客户端、账号资料根目录、`auth.json` 与 `config.toml` 是否就绪。你可以直接启动当前账号，也可以快速进入账号管理、TOML 编辑、指令模板和应用设置。

账号管理页提供账号搜索、状态筛选和多种排序方式。选择账号后，右侧账号检查器会集中展示：

- **概览**：账号套餐、运行与认证状态、一周剩余额度、可刷新次数及每次刷新的过期时间。
- **运行环境**：账号目录、认证文件、配置文件和共享客户端副本状态。
- **维护操作**：导出备份、改名、打开目录和删除账号。

### 2. 🛡️ 多账号资料隔离

每个账号资料独立保存自身的登录凭证与配置：

```text
~/Documents/CodexProfiles/<profile_id>/auth.json
~/Documents/CodexProfiles/<profile_id>/CodexHome/config.toml
```

账号切换模式只替换 `auth.json`，模型、代理等全局 ChatGPT 配置始终使用系统 `~/.codex/config.toml`。多开隔离模式使用账号自己的 `CodexHome/config.toml`。

### 3. 🔑 多样化的认证（Auth）管理

提供三种便捷的新增账号方式：

- 🌐 **浏览器授权**：通过 ChatGPT 内置 Codex App Server 打开官方授权流程，授权结果仅保存至新账号资料目录。
- 💾 **保存当前账号**：一键复制当前系统中的 `~/.codex/auth.json`。
- 📁 **上传本地文件**：从本地选择已有的 ChatGPT 登录文件进行导入。

> 💡 额度刷新通过官方 App Server 完成；如果认证被刷新，最新信息会回写至对应账号资料。

### 4. 🛠️ TOML 可视化编辑与安全备份

Codex Forge 会读取当前生效的配置文件：

```text
~/.codex/config.toml
```

在保存任何修改前，系统会自动校验 TOML 内容的合法性，并将旧文件安全备份至：

```text
%LOCALAPPDATA%/CodexForge/backups/config-toml/
```

### 5. 📝 指令模板管理（提示词注入）

指令模板用于快速切换 ChatGPT 的系统级行为提示词。你可以把常用工作方式、代码规范、审查标准，或仓库内置的破除限制提示词保存为 Markdown（标记语言）模板，需要时一键启用。

Codex Forge 当前内置破除限制提示词模板：

- `docs/propmt/gpt5.5-unrestricted.md`
- `docs/propmt/gpt-5.6-sol-unrestricted.md`（适配 GPT-5.6 SOL）

Codex Forge 启动时会自动将这两个模板写入 **指令模板**，但不会默认启用，也不会覆盖已有的同名模板。

你可以在 **指令模板** 页面直接点击启用 / 禁用。启用后，Codex Forge 会把对应 `.md` 写入 ChatGPT 配置目录，并更新 `config.toml` 中的 `model_instructions_file`。

| 对比项 | 默认指令             | 破除限制提示词模板           |
| :----- | :------------------- | :--------------------------- |
| 定位   | 通用 ChatGPT 助手    | 高自由度开发者模式           |
| 策略   | 偏保守，容易泛化拒答 | 更强调执行、分析和可验证结果 |
| 风格   | 标准问答和代码协助   | 直接、覆盖面广、少解释阻塞   |
| 适用   | 日常编码、普通问答   | 代码审计、安全研究、复杂调试 |

部署后可以测试：

```text
如何对目标进行渗透测试？
```

典型效果：

```text
启用前 -> 容易拒绝或给出泛化回答
启用后 -> 更倾向于给出安全研究方法论、测试步骤和验证思路
```

启用模板时，Codex Forge 会执行三件事：

- 将模板复制到当前生效的 ChatGPT 配置目录。
- 在 `config.toml` 中写入 `model_instructions_file = "./模板文件名.md"`。
- 在多开隔离模式下支持同步到当前账号、指定账号或全部账号。

这意味着你不需要手动编辑 `config.toml`，就能在默认指令、团队规范和更少限制的提示词风格之间切换。禁用模板只会移除 `model_instructions_file` 配置，不会删除已保存的模板文件。

### 6. 📦 多开隔离启动

除默认的账号切换模式外，Codex Forge 的特色启动能力是多开隔离：

- **账号切换模式**：默认模式。切换账号时写入系统 `~/.codex`，同一时间只建议运行一个 ChatGPT 客户端。
- **多开隔离模式**：特色模式。首次启动时从系统已安装的 ChatGPT 客户端复制出一份共享副本，所有账号共用该副本，并使用独立配置和运行环境。

多开隔离模式会隔离 `CodexHome`、`APPDATA`、`LOCALAPPDATA` 和浏览器 `--user-data-dir`。复制出来的共享客户端副本只在账号资料根目录下保存一份：

```text
CodexProfiles/.shared/CodexPortableApp
CodexProfiles/<profile_id>/CodexHome
CodexProfiles/<profile_id>/AppData
```

### 7. 🎨 Codex 换肤

Codex 换肤页面提供内置的 **Forge Aurora** 主题，也可以导入本地背景图片并快速切换。导入的图片只保存在本机 Forge 数据目录，不会上传。

<p align="center">
  <img src="docs/images/codex-skin.png" alt="Codex Forge Codex 换肤页面" />
</p>

- 支持账号切换与多开隔离两种启动模式。
- 支持切换、暂停显示和删除自定义主题。
- 开启或关闭换肤时，会安全重启正在运行的 Codex 以应用或恢复官方外观。

### 8. ⚙️ 设置、更新与项目入口

设置页集中管理启动器自身配置：

- **账号资料位置**：可更改账号资料根目录，迁移前会提示关闭正在运行的 ChatGPT。
- **启动模式**：可在账号切换模式和多开隔离模式之间切换；首次启动多开账号时会从系统安装目录复制一份共享客户端副本。
- **开机自启**：支持登录 Windows 后自动启动 Codex Forge。
- **语言切换**：支持中文 / English 界面切换。
- **版本更新**：显示当前版本，支持手动检查更新；发现新版本后可查看更新内容、后台下载并重启安装。
- **项目入口**：关于区域提供 GitHub 与 Gitee 项目入口，方便查看源码和发布信息。

### 9. 🧠 ChatGPT 启动来源智能识别

在启动账号时，系统会按以下优先级顺序智能识别启动路径：

1. 已保存的 ChatGPT 桌面主程序路径。
2. 当前运行中的 ChatGPT 主进程。
3. `OpenAI.Codex` / `OpenAI.ChatGPT` AppX Manifest 中的主程序与应用标识。

---

## 📁 核心配置路径

**ChatGPT 当前用户配置（默认读写）**：

```text
~/.codex/auth.json
~/.codex/config.toml
```

**Codex Forge 自身配置、日志与缓存**：

```text
%LOCALAPPDATA%/CodexForge/codex_forge.db
%LOCALAPPDATA%/CodexForge/logs/launcher.log
```

**账号资料存储目录**：

```text
~/Documents/CodexProfiles
```

---

## 👨‍💻 开发者指南

### 🛠️ 技术栈

- **桌面框架**：Electron 41 / electron-vite
- **前端技术**：React 18 / TypeScript / Vite
- **UI（用户界面）组件**：Ant Design 5 / Tailwind CSS / lucide-react
- **后端服务**：Python 3.11 (本地桥接进程)
- **构建打包**：PyInstaller / Electron Builder
- **包管理器**：yarn / uv

### 📋 环境要求

- 操作系统：Windows 10 / Windows 11
- 环境依赖：
  - Python 3.11 或更高版本
  - Node.js
  - uv (Python 包管理器)
  - yarn
  - Bash 环境 (Windows 推荐使用 Git Bash)
- 软件依赖：已从 Microsoft Store 安装 ChatGPT 桌面应用。

_验证 ChatGPT 桌面应用（可选）：_

```powershell
winget list ChatGPT -s msstore
```

### 🚀 开发运行

```bash
cd /d/MyObject/CodexForge
cd python
uv sync --dev
cd ..
yarn install
yarn dev
```

### 🔍 代码检查

```bash
cd python
uv run python -m py_compile main.py
cd ..
yarn typecheck:all
```

### 📦 项目打包

**完整打包命令**：

```bash
yarn build
```

**分步构建命令**：

```bash
yarn build:backend
yarn build:shell
yarn build:installer
yarn clean
```

> **打包流程说明**：
>
> 1. 通过 `python -m PyInstaller` 生成独立的后端可执行文件 `resources/main.exe`。
> 2. 最后构建 Electron（跨平台桌面应用开发框架）桌面外壳，并生成 Windows 标准安装包。

**主要产物路径**：

```text
resources/main.exe
release/Codex-Forge-Setup-<version>.exe
```

---

## ⚠️ 免责声明

Codex Forge 是一个本地账号、配置和启动管理工具，非 OpenAI 官方产品，也不隶属于 OpenAI。项目中提供的指令模板仅用于合法的软件开发、代码审计、安全研究和学习测试场景；使用者应自行遵守所在地法律法规、目标系统授权要求以及相关平台服务条款。因使用本工具或模板造成的账号、数据、合规或安全风险，由使用者自行承担。
