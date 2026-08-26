import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Layout, Modal, Progress, message } from "antd";
import { Boxes, Code2, FileText, Home, Palette, Settings, ShieldCheck } from "lucide-react";
import { AppLayout } from "./components/AppLayout";
import { getViewMeta } from "./constants/views";
import { invokeLauncher } from "./api/launcher";
import { useI18n } from "./i18n";
import { HomePage } from "./pages/HomePage";
import { Profiles } from "./pages/Profiles";
import { InstructionsPage } from "./pages/InstructionsPage";
import { TomlConfigPage } from "./pages/TomlConfigPage";
import { CodexSkinPage } from "./pages/CodexSkinPage";
import { SettingsPage } from "./pages/SettingsPage";
import { WorkspacePage } from "./pages/WorkspacePage";
import codexForgeLogo from "./assets/codex-forge-logo.png";
import type { AppState, ProfileSummary, ProfileUsage, RunCommand, RuntimeStatus, UpdateEvent, ViewKey } from "./types";

const { Content } = Layout;
const runtimeStatusPollMs = 3 * 1000;
const usageAutoRefreshMs = 5 * 60 * 1000;
const privacyModeStorageKey = "codexForgePrivacyMode";
type UpdateModalEvent = Exclude<UpdateEvent, { status: "error" } | { status: "not-available" }>;
type ShellSnapshot = { appState: AppState; profiles: ProfileSummary[] };

const emptyState: AppState = {
  codexCommandAvailable: false,
  activeAuthPath: "",
  activeAuthExists: false,
  activeConfigPath: "",
  activeConfigExists: false,
  activeProfile: "",
  shareSystemConfig: true,
  launchMode: "switch",
  codexSkinEnabled: false,
  profileRoot: "",
  profileRootExists: false,
  profileCount: 0,
  runningCount: 0,
  authCredentialStore: "file"
};

const refreshDelayCommands = new Set(["launch_profile", "stop_profile"]);

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function releaseNotesForLanguage(releaseNotes: string, language: string) {
  const lines = releaseNotes.split(/\r?\n/);
  const start = lines.findIndex((line) => line.trim().toLowerCase() === `### ${language}`.toLowerCase());
  if (start === -1) {
    return releaseNotes;
  }
  const end = lines.findIndex((line, index) => index > start && /^###\s+/.test(line.trim()));
  return lines.slice(start + 1, end === -1 ? undefined : end).join("\n").trim();
}

function updateNotes(event: UpdateEvent | null, language: string) {
  if (!event || !("releaseNotes" in event) || !event.releaseNotes) {
    return [];
  }
  const notes = releaseNotesForLanguage(event.releaseNotes, language)
    .split(/\r?\n/)
    .map((line) => line.replace(/^[-*]\s*/, "").trim())
    .filter((line) => line && !/^#{1,6}\s+/.test(line))
    .slice(0, 5);
  return notes;
}

async function notifyLowUsage(profiles: ProfileSummary[], t: (text: string) => string) {
  if (localStorage.getItem("quotaAlertsEnabled") === "false" || !window.launcherApi.showNotification) {
    return;
  }
  const configured = Number(localStorage.getItem("quotaAlertThreshold") || "20");
  const threshold = Number.isFinite(configured) ? Math.max(1, Math.min(configured, 90)) : 20;
  for (const profile of profiles) {
    for (const [label, usage] of [[t("一周剩余额度"), profile.usage?.oneWeek]] as const) {
      if (!usage || profile.usage?.error) continue;
      const resetKey = `quotaWindowReset:${profile.id}:${usage.windowSeconds}`;
      const previousReset = Number(localStorage.getItem(resetKey) || "0");
      if (usage.resetAt) localStorage.setItem(resetKey, String(usage.resetAt));
      const previousWindowEnded = previousReset > 0 && previousReset <= Date.now() / 1000;
      if (previousWindowEnded && usage.resetAt && usage.resetAt > previousReset && usage.remainingPercent > threshold) {
        await window.launcherApi.showNotification(t("Codex 额度已重置"), `${profile.name} ${label} ${Math.round(usage.remainingPercent)}%`);
      }
      if (usage.remainingPercent > threshold) continue;
      const key = `quotaAlert:${profile.id}:${usage.windowSeconds}:${usage.resetAt ?? "unknown"}:${threshold}`;
      if (localStorage.getItem(key)) continue;
      localStorage.setItem(key, String(Date.now()));
      await window.launcherApi.showNotification(t("Codex 额度提醒"), `${profile.name} ${label} ${Math.round(usage.remainingPercent)}%`);
    }
  }
}

export default function App() {
  const { language, t } = useI18n();
  const [activeView, setActiveView] = useState<ViewKey>("home");
  const [appState, setAppState] = useState<AppState>(emptyState);
  const [profiles, setProfiles] = useState<ProfileSummary[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshingView, setRefreshingView] = useState<ViewKey | null>(null);
  const [commandingView, setCommandingView] = useState<ViewKey | null>(null);
  const [taskText, setTaskText] = useState(t("就绪"));
  const contentRef = useRef<HTMLDivElement | null>(null);
  const activeViewRef = useRef<ViewKey>("home");
  const profilesRef = useRef<ProfileSummary[]>([]);
  const dirtyViewsRef = useRef(new Set<ViewKey>());
  const refreshTokenRef = useRef(0);
  const commandTokenRef = useRef(0);
  const autoUsageRefreshingRef = useRef(false);
  const runtimeStatusRefreshingRef = useRef(false);
  const showUpdateProgressRef = useRef(false);
  const [updateEvent, setUpdateEvent] = useState<UpdateModalEvent | null>(null);
  const [updateModalOpen, setUpdateModalOpen] = useState(false);
  const [showUpdateProgress, setShowUpdateProgress] = useState(false);
  const [privacyMode, setPrivacyModeState] = useState(() => localStorage.getItem(privacyModeStorageKey) === "1");

  const setPrivacyMode = useCallback((enabled: boolean) => {
    localStorage.setItem(privacyModeStorageKey, enabled ? "1" : "0");
    setPrivacyModeState(enabled);
  }, []);

  useEffect(() => {
    activeViewRef.current = activeView;
  }, [activeView]);

  useEffect(() => {
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (dirtyViewsRef.current.size === 0) {
        return;
      }
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, []);

  useEffect(() => {
    setTaskText(t("就绪"));
  }, [t]);

  useEffect(() => {
    if (!window.launcherApi.onBackendProgress) {
      return undefined;
    }
    return window.launcherApi.onBackendProgress((progress) => {
      if (progress.operation !== "portable-client-copy") {
        return;
      }
      const sizeText = progress.totalBytes
        ? ` · ${formatBytes(progress.copiedBytes ?? 0)} / ${formatBytes(progress.totalBytes)}`
        : "";
      setTaskText(`${t("正在复制 Codex 客户端")} ${progress.percent}%${sizeText}`);
    });
  }, [t]);

  const loadShellState = useCallback(async () => {
    const snapshot = await invokeLauncher<ShellSnapshot>("get_shell_snapshot");
    profilesRef.current = snapshot.profiles;
    setAppState(snapshot.appState);
    setProfiles(snapshot.profiles);
    return snapshot.profiles;
  }, []);

  const refresh = useCallback(async (view?: ViewKey | null) => {
    const refreshToken = view ? ++refreshTokenRef.current : refreshTokenRef.current;
    if (view) {
      setRefreshingView(view);
    }
    try {
      await loadShellState();
      setTaskText(t("状态已刷新"));
    } catch (error) {
      message.error(error instanceof Error ? error.message : t("刷新失败"));
    } finally {
      if (view && refreshTokenRef.current === refreshToken) {
        setRefreshingView(null);
      }
      if (view === "home") {
        setInitialLoading(false);
      }
    }
  }, [loadShellState, t]);

  useEffect(() => {
    refresh("home");
  }, [refresh]);

  useEffect(() => {
    if (!window.launcherApi.onUpdateEvent) {
      return undefined;
    }
    return window.launcherApi.onUpdateEvent((event) => {
      if (event.status === "error") {
        showUpdateProgressRef.current = false;
        setShowUpdateProgress(false);
        setUpdateModalOpen(false);
        message.error(event.message || t("更新失败"));
        return;
      }
      if (event.status === "not-available") {
        showUpdateProgressRef.current = false;
        setShowUpdateProgress(false);
        setUpdateModalOpen(false);
        if (event.manual) {
          message.success(t("当前已是最新版本"));
        }
        return;
      }
      setUpdateEvent(event);
      if (event.status === "available") {
        showUpdateProgressRef.current = false;
        setShowUpdateProgress(false);
        setUpdateModalOpen(true);
        return;
      }
      if (event.status === "downloaded") {
        showUpdateProgressRef.current = false;
        setShowUpdateProgress(false);
        setUpdateModalOpen(true);
        return;
      }
      setUpdateModalOpen(showUpdateProgressRef.current);
    });
  }, [t]);

  useEffect(() => {
    if (initialLoading) {
      return undefined;
    }
    const refreshUsageSilently = async () => {
      if (autoUsageRefreshingRef.current) {
        return;
      }
      autoUsageRefreshingRef.current = true;
      try {
        const result = await invokeLauncher<{ profiles: Record<string, ProfileUsage | null> }>("refresh_all_profile_usage");
        const nextProfiles = profilesRef.current.map((profile) => (
          Object.prototype.hasOwnProperty.call(result.profiles, profile.name)
            ? { ...profile, usage: result.profiles[profile.name] }
            : profile
        ));
        profilesRef.current = nextProfiles;
        setProfiles(nextProfiles);
        await notifyLowUsage(nextProfiles, t);
      } catch {
        // 静默自动刷新不打扰用户，手动刷新仍会展示具体错误。
      } finally {
        autoUsageRefreshingRef.current = false;
      }
    };

    const timer = window.setInterval(() => {
      void refreshUsageSilently();
    }, usageAutoRefreshMs);
    void refreshUsageSilently();
    return () => window.clearInterval(timer);
  }, [initialLoading, t]);

  useEffect(() => {
    if (initialLoading || activeView !== "profiles") {
      return undefined;
    }

    const refreshRuntimeStatus = async () => {
      if (document.hidden || runtimeStatusRefreshingRef.current) {
        return;
      }
      runtimeStatusRefreshingRef.current = true;
      try {
        const runtimeStatus = await invokeLauncher<RuntimeStatus>("get_runtime_status");
        setAppState((current) => (
          current.runningCount === runtimeStatus.runningCount
            ? current
            : { ...current, runningCount: runtimeStatus.runningCount }
        ));
        const runningChanged = profilesRef.current.some(
          (profile) => profile.running !== (runtimeStatus.profiles[profile.name] ?? false),
        );
        if (runningChanged) {
          const nextProfiles = profilesRef.current.map((profile) => ({
            ...profile,
            running: runtimeStatus.profiles[profile.name] ?? false,
          }));
          profilesRef.current = nextProfiles;
          setProfiles(nextProfiles);
        }
      } catch {
        // 后台状态检查失败时保持现有界面状态，避免打扰用户。
      } finally {
        runtimeStatusRefreshingRef.current = false;
      }
    };

    const handleFocus = () => {
      void refreshRuntimeStatus();
    };
    const timer = window.setInterval(() => {
      void refreshRuntimeStatus();
    }, runtimeStatusPollMs);
    window.addEventListener("focus", handleFocus);
    void refreshRuntimeStatus();
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", handleFocus);
    };
  }, [activeView, initialLoading]);

  const runCommand = useCallback<RunCommand>(
    async (command, payload, successText = t("操作完成"), options) => {
      const commandToken = ++commandTokenRef.current;
      const sourceView = activeViewRef.current;
      const shouldBlockView = options?.blocking !== false;
      const shouldRefreshAfter = options?.refreshAfter !== false;
      if (shouldBlockView) {
        setCommandingView(sourceView);
      }
      setTaskText(t("正在执行..."));
      try {
        await invokeLauncher(command, payload);
        if (refreshDelayCommands.has(command)) {
          await new Promise((resolve) => setTimeout(resolve, 800));
        }
        message.success(successText);
        setTaskText(successText);
        if (shouldRefreshAfter) {
          await refresh(null);
        }
      } catch (error) {
        const text = error instanceof Error ? error.message : t("操作失败");
        setTaskText(text);
        message.error(text);
      } finally {
        if (shouldBlockView && commandTokenRef.current === commandToken) {
          setCommandingView(null);
        }
      }
    },
    [refresh, t]
  );

  const menuItems = useMemo(
    () => [
      { key: "home" as const, label: t("首页"), icon: <Home size={18} /> },
      { key: "profiles" as const, label: t("账号"), icon: <ShieldCheck size={18} /> },
      { key: "workspace" as const, label: t("环境"), icon: <Boxes size={18} /> },
      { key: "instructions" as const, label: t("指令模板"), icon: <FileText size={18} /> },
      { key: "toml" as const, label: "TOML", icon: <Code2 size={18} /> },
      { key: "skin" as const, label: t("换肤"), icon: <Palette size={18} /> },
      { key: "settings" as const, label: t("设置"), icon: <Settings size={18} /> }
    ],
    [t]
  );
  const currentView = useMemo(() => getViewMeta(t), [t])[activeView];

  useEffect(() => {
    document.title = `${currentView.title} - Codex Forge`;
  }, [currentView.title]);

  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0 });
  }, [activeView]);

  const changeView = useCallback(
    (view: ViewKey) => {
      const currentView = activeViewRef.current;
      if (view === currentView) {
        return;
      }
      if (dirtyViewsRef.current.has(currentView)) {
        Modal.confirm({
          title: t("有未保存的更改"),
          content: t("离开当前页面将丢失未保存的更改。"),
          okText: t("放弃更改并离开"),
          cancelText: t("继续编辑"),
          onOk: () => {
            dirtyViewsRef.current.delete(currentView);
            setActiveView(view);
          },
        });
        return;
      }
      setActiveView(view);
    },
    [t]
  );

  const setViewDirty = useCallback((view: ViewKey, dirty: boolean) => {
    if (dirty) {
      dirtyViewsRef.current.add(view);
    } else {
      dirtyViewsRef.current.delete(view);
    }
  }, []);
  const setWorkspaceDirty = useCallback((dirty: boolean) => setViewDirty("workspace", dirty), [setViewDirty]);
  const setTomlDirty = useCallback((dirty: boolean) => setViewDirty("toml", dirty), [setViewDirty]);

  const launchProfileFromHome = useCallback(
    (profile: ProfileSummary) => {
      void runCommand(
        "launch_profile",
        { name: profile.name },
        t("已启动"),
        { blocking: false },
      );
    },
    [runCommand, t],
  );

  const hideUpdateModal = useCallback(() => {
    showUpdateProgressRef.current = false;
    setShowUpdateProgress(false);
    setUpdateModalOpen(false);
  }, []);

  const startUpdateDownload = useCallback((showProgress: boolean) => {
    if (!window.launcherApi.downloadUpdate) {
      message.error(t("当前版本不支持下载更新，请重启后再试"));
      return;
    }
    showUpdateProgressRef.current = showProgress;
    setShowUpdateProgress(showProgress);
    setUpdateModalOpen(showProgress);
    if (!showProgress) {
      message.info(t("更新将在后台下载，完成后会提示安装"));
    }
    void window.launcherApi.downloadUpdate().catch((error) => {
      showUpdateProgressRef.current = false;
      setShowUpdateProgress(false);
      setUpdateModalOpen(false);
      message.error(error instanceof Error ? error.message : t("下载更新失败"));
    });
  }, [t]);

  const installUpdate = useCallback(() => {
    if (!window.launcherApi.installUpdate) {
      message.error(t("当前版本不支持安装更新，请重启后再试"));
      return;
    }
    void window.launcherApi.installUpdate();
  }, [t]);

  const notes = updateNotes(updateEvent, language);
  const updateModalTitle =
    updateEvent?.status === "downloaded"
      ? t("更新已下载")
      : updateEvent?.status === "downloading" && showUpdateProgress
        ? t("正在下载更新")
        : t("发现新版本");

  return (
    <>
      <AppLayout
        activeView={activeView}
        launchMode={appState.launchMode}
        menuItems={menuItems}
        taskText={taskText}
        onChangeView={changeView}
      >
        <Content
          ref={contentRef}
          className={
            activeView === "toml"
              ? "m-0 min-h-0 flex-auto overflow-hidden rounded-none border-0 bg-white px-[30px] py-[22px] shadow-none"
              : "m-0 min-h-0 flex-auto overflow-auto rounded-none border-0 bg-white px-[30px] py-[22px] shadow-none"
          }
        >
          {activeView === "home" ? (
            <HomePage
              appState={appState}
              profiles={profiles}
              onOpenView={changeView}
              onLaunchProfile={launchProfileFromHome}
            />
          ) : null}
          {activeView === "profiles" ? (
            <Profiles
              profiles={profiles}
              runningCount={appState.runningCount}
              launchMode={appState.launchMode}
              privacyMode={privacyMode}
              runCommand={runCommand}
              loading={commandingView === "profiles" || refreshingView === "profiles"}
            />
          ) : null}
          {activeView === "workspace" ? (
            <WorkspacePage appState={appState} profiles={profiles} onDirtyChange={setWorkspaceDirty} />
          ) : null}
          {activeView === "instructions" ? (
            <InstructionsPage appState={appState} profiles={profiles} />
          ) : null}
          {activeView === "toml" ? (
            <TomlConfigPage appState={appState} profiles={profiles} onDirtyChange={setTomlDirty} />
          ) : null}
          {activeView === "skin" ? (
            <CodexSkinPage appState={appState} runCommand={runCommand} />
          ) : null}
          {activeView === "settings" ? (
            <SettingsPage
              appState={appState}
              privacyMode={privacyMode}
              runCommand={runCommand}
              onPrivacyModeChange={setPrivacyMode}
            />
          ) : null}
        </Content>
      </AppLayout>
      {initialLoading ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-white/80 backdrop-blur-md">
          <div className="grid place-items-center gap-4 text-center">
            <div className="forge-splash-logo-wrap">
              <div className="forge-splash-ring" />
              <div className="grid h-[76px] w-[76px] place-items-center rounded-[20px] bg-white shadow-[0_18px_46px_rgba(15,118,110,0.22)]">
                <img
                  src={codexForgeLogo}
                  alt=""
                  className="h-[54px] w-[54px] object-contain"
                  draggable={false}
                />
              </div>
            </div>
            <div className="grid gap-1">
              <div className="text-xl font-extrabold text-slate-900">Codex Forge</div>
              <div className="text-sm font-semibold text-slate-500">{t("正在加载账号数据...")}</div>
            </div>
            <div className="h-1.5 w-[210px] overflow-hidden rounded-full bg-slate-200">
              <div className="forge-splash-progress h-full rounded-full bg-brand-gradient" />
            </div>
          </div>
        </div>
      ) : null}
      <Modal
        centered
        width={520}
        title={updateModalTitle}
        open={updateModalOpen && updateEvent !== null}
        onCancel={hideUpdateModal}
        footer={
          updateEvent?.status === "downloaded" ? (
            <>
              <Button onClick={hideUpdateModal}>{t("稍后")}</Button>
              <Button type="primary" onClick={installUpdate}>
                {t("立即重启安装")}
              </Button>
            </>
          ) : updateEvent?.status === "downloading" && showUpdateProgress ? (
            <Button onClick={hideUpdateModal}>{t("稍后隐藏")}</Button>
          ) : (
            <>
              <Button onClick={hideUpdateModal}>{t("稍后")}</Button>
              <Button onClick={() => startUpdateDownload(false)}>{t("后台下载")}</Button>
              <Button type="primary" onClick={() => startUpdateDownload(true)}>
                {t("立即下载")}
              </Button>
            </>
          )
        }
      >
        {updateEvent ? (
          <div className="grid gap-5">
            <div className="flex items-center gap-4 rounded-xl bg-slate-50 p-4">
              <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-white shadow-sm ring-1 ring-slate-900/5">
                <img src={codexForgeLogo} alt="" className="h-8 w-8 object-contain" draggable={false} />
              </div>
              <div className="grid gap-1">
                <div className="text-[15px] font-semibold text-slate-900">
                  {t("当前版本")} <span className="text-slate-500 font-normal">{updateEvent.currentVersion}</span> <span className="mx-1 text-slate-300">→</span> {t("最新版本")} <span className="text-brand-600">{updateEvent.version}</span>
                </div>
                <div className="text-sm text-slate-500 leading-relaxed">
                  {updateEvent.status === "downloaded"
                    ? t("更新包已下载完成，重启后将自动安装。")
                    : updateEvent.status === "downloading"
                      ? t("更新包正在下载，下载期间可以继续使用 Codex Forge。")
                      : t("新版本已可用。你可以立即下载并查看进度，也可以让它在后台下载。")}
                </div>
              </div>
            </div>
            {updateEvent.status === "downloading" && showUpdateProgress ? (
              <div className="grid gap-2 px-1">
                <Progress percent={Math.round(updateEvent.percent)} strokeColor="#0f766e" />
                <div className="text-xs font-medium text-slate-500">
                  {formatBytes(updateEvent.transferred)} / {formatBytes(updateEvent.total)} ·{" "}
                  {formatBytes(updateEvent.bytesPerSecond)}/s
                </div>
              </div>
            ) : null}
            {updateEvent.status !== "downloading" ? (
              <div className="grid gap-3 px-1">
                <div className="flex items-center gap-2">
                  <div className="h-3.5 w-1 rounded-full bg-brand-600" />
                  <div className="text-[15px] font-bold text-slate-900">{t("更新内容")}</div>
                </div>
                {notes.length > 0 ? (
                  <ul className="m-0 grid gap-2.5 pl-1 text-[14px] text-slate-600 list-none">
                    {notes.map((note) => (
                      <li key={note} className="relative pl-4 leading-relaxed">
                        <span className="absolute left-0 top-[9px] h-1.5 w-1.5 rounded-full bg-slate-300" />
                        {note}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-[14px] text-slate-500">{t("暂无更新说明")}</div>
                )}
              </div>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </>
  );
}
