import { app, BrowserWindow, dialog, ipcMain, Notification, type OpenDialogOptions } from "electron";
import { invokeBackend } from "./python/launcherBackend";
import {
  applyCodexSkinTheme,
  hasCodexSkinSessions,
  pauseCodexSkinSessions,
  startCodexSkinSession,
  stopAllCodexSkinSessions,
  stopCodexSkinSession,
} from "./codexSkin";
import {
  deleteCodexSkinTheme,
  getActiveCodexSkinTheme,
  getCodexSkinThemeState,
  importCodexSkinTheme,
  setActiveCodexSkinTheme,
  setCodexSkinPaused,
  updateCodexSkinThemeOptions,
} from "./codexSkinStore";

type SkinLaunch = { profileName?: string; port?: number; processId?: number };

function validSkinLaunch(launch: SkinLaunch): launch is Required<SkinLaunch> {
  return Boolean(launch.profileName) && Number.isInteger(launch.port) && Number.isInteger(launch.processId);
}

async function startSkinLaunches(launches: SkinLaunch[]): Promise<void> {
  const validLaunches = launches.filter(validSkinLaunch);
  if (validLaunches.length === 0) return;
  const [theme, state] = await Promise.all([getActiveCodexSkinTheme(), getCodexSkinThemeState()]);
  await applyCodexSkinTheme(theme);
  await pauseCodexSkinSessions(state.paused);
  validLaunches.forEach((launch) => startCodexSkinSession(launch));
}

let skinRecovery: Promise<void> | null = null;

export async function recoverCodexSkinSessions(): Promise<void> {
  if (hasCodexSkinSessions()) return;
  if (skinRecovery) return skinRecovery;
  skinRecovery = (async () => {
    const result = await invokeBackend("ensure_codex_skin_sessions", {});
    if (!result.ok) return;
    const launches = Array.isArray(result.data.skinSessions) ? result.data.skinSessions : [];
    await startSkinLaunches(launches as SkinLaunch[]);
  })();
  try {
    await skinRecovery;
  } finally {
    skinRecovery = null;
  }
}

async function applySelectedCodexSkinTheme(): Promise<void> {
  await recoverCodexSkinSessions();
  await applyCodexSkinTheme(await getActiveCodexSkinTheme());
}

export function registerIpcHandlers(): void {
  ipcMain.handle("launcher:invoke", async (_event, command: string, payload: unknown) => {
    const result = await invokeBackend(command, payload, (progress) => {
      _event.sender.send("launcher:backend-progress", progress);
    });
    if (!result.ok) {
      return result;
    }
    if (command === "launch_profile") {
      const launch = result.data.skinSession as SkinLaunch | undefined;
      if (launch) await startSkinLaunches([launch]);
    } else if (command === "stop_profile") {
      const profileName = typeof payload === "object" && payload !== null
        ? String((payload as { name?: unknown }).name || "")
        : "";
      if (profileName) {
        await stopCodexSkinSession(profileName);
      } else {
        await stopAllCodexSkinSessions();
      }
    } else if (command === "set_codex_skin_enabled" && result.data.codexSkinEnabled === false) {
      await stopAllCodexSkinSessions();
    } else if (command === "set_codex_skin_enabled") {
      const launches = Array.isArray(result.data.skinSessions) ? result.data.skinSessions : [];
      await startSkinLaunches(launches as SkinLaunch[]);
    } else if (command === "set_launch_mode" && result.data.launchMode === "switch") {
      await stopAllCodexSkinSessions();
    }
    return result;
  });
  ipcMain.handle("launcher:select-directory", async (event, defaultPath?: string) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    const options: OpenDialogOptions = {
      title: "选择 CodexProfiles 的存放位置",
      defaultPath,
      properties: ["openDirectory", "createDirectory"]
    };
    const result = window ? await dialog.showOpenDialog(window, options) : await dialog.showOpenDialog(options);
    return result.canceled ? "" : result.filePaths[0] ?? "";
  });
  ipcMain.handle("launcher:select-auth-json-file", async (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    const options: OpenDialogOptions = {
      title: "选择 auth.json 文件",
      filters: [{ name: "auth.json", extensions: ["json"] }],
      properties: ["openFile"]
    };
    const result = window ? await dialog.showOpenDialog(window, options) : await dialog.showOpenDialog(options);
    return result.canceled ? "" : result.filePaths[0] ?? "";
  });
  ipcMain.handle("launcher:select-profile-backup-file", async (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    const options: OpenDialogOptions = {
      title: "选择账号备份文件",
      filters: [{ name: "Codex Forge profile backup", extensions: ["forgebackup", "zip"] }],
      properties: ["openFile"]
    };
    const result = window ? await dialog.showOpenDialog(window, options) : await dialog.showOpenDialog(options);
    return result.canceled ? "" : result.filePaths[0] ?? "";
  });
  ipcMain.handle("codex-skin:get-state", async () => {
    await recoverCodexSkinSessions();
    return getCodexSkinThemeState();
  });
  ipcMain.handle("codex-skin:import-theme", async (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    const options: OpenDialogOptions = {
      title: "选择 Codex 背景图",
      filters: [{ name: "背景图", extensions: ["png", "jpg", "jpeg", "webp"] }],
      properties: ["openFile"],
    };
    const selected = window ? await dialog.showOpenDialog(window, options) : await dialog.showOpenDialog(options);
    if (selected.canceled || !selected.filePaths[0]) return getCodexSkinThemeState();
    const state = await importCodexSkinTheme(selected.filePaths[0]);
    await applySelectedCodexSkinTheme();
    return state;
  });
  ipcMain.handle("codex-skin:set-active", async (_event, themeId: string) => {
    const state = await setActiveCodexSkinTheme(themeId);
    await applySelectedCodexSkinTheme();
    return state;
  });
  ipcMain.handle("codex-skin:delete-theme", async (_event, themeId: string) => {
    const state = await deleteCodexSkinTheme(themeId);
    await applySelectedCodexSkinTheme();
    return state;
  });
  ipcMain.handle("codex-skin:set-paused", async (_event, paused: boolean) => {
    const state = await setCodexSkinPaused(paused);
    await pauseCodexSkinSessions(state.paused);
    return state;
  });
  ipcMain.handle("codex-skin:update-theme", async (_event, themeId: string, options: object) => {
    const state = await updateCodexSkinThemeOptions(themeId, options);
    await applySelectedCodexSkinTheme();
    return state;
  });
  ipcMain.handle("app:get-auto-start-enabled", () => {
    return app.getLoginItemSettings().openAtLogin;
  });
  ipcMain.handle("app:get-version", () => app.getVersion());
  ipcMain.handle("app:show-notification", (_event, title: string, body: string) => {
    if (!Notification.isSupported()) {
      return false;
    }
    new Notification({ title, body }).show();
    return true;
  });
  ipcMain.handle("app:set-auto-start-enabled", (_event, enabled: boolean) => {
    app.setLoginItemSettings({
      openAtLogin: enabled,
      path: process.execPath
    });
    return app.getLoginItemSettings().openAtLogin;
  });
  ipcMain.handle("window:minimize", (event) => {
    BrowserWindow.fromWebContents(event.sender)?.minimize();
  });
  ipcMain.handle("window:is-maximized", (event) => {
    return BrowserWindow.fromWebContents(event.sender)?.isMaximized() ?? false;
  });
  ipcMain.handle("window:toggle-maximize", (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window) {
      return;
    }
    if (window.isMaximized()) {
      window.unmaximize();
      return;
    }
    window.maximize();
  });
  ipcMain.handle("window:close", (event) => {
    BrowserWindow.fromWebContents(event.sender)?.close();
  });
}
