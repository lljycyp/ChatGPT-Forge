export type BackendResponse<T> = {
  ok: boolean;
  data: T;
  error: string;
};

export type AppState = {
  codexCommandAvailable: boolean;
  activeAuthPath: string;
  activeAuthExists: boolean;
  activeConfigPath: string;
  activeConfigExists: boolean;
  activeProfile: string;
  shareSystemConfig: boolean;
  launchMode: "switch" | "multi";
  codexSkinEnabled: boolean;
  profileRoot: string;
  profileRootExists: boolean;
  profileCount: number;
  runningCount: number;
  authCredentialStore: "file" | "keyring" | "auto";
};

export type ViewKey = "home" | "profiles" | "workspace" | "instructions" | "toml" | "skin" | "settings";

export type ViewMeta = {
  title: string;
  description: string;
};

export type RunCommandOptions = {
  blocking?: boolean;
  refreshAfter?: boolean;
};

export type RunCommand = (
  command: string,
  payload?: unknown,
  successText?: string,
  options?: RunCommandOptions,
) => Promise<void>;

export type ProfileSummary = {
  id: string;
  name: string;
  storageKey: string;
  running: boolean;
  active: boolean;
  profileDir: string;
  profileDirExists: boolean;
  authPath: string;
  authExists: boolean;
  configPath: string;
  configExists: boolean;
  codexHome?: string;
  codexHomeExists?: boolean;
  portableCodexPath?: string;
  portableCodexExists?: boolean;
  portableCodexSizeBytes?: number;
  portableCodexSizeText?: string;
  usage: ProfileUsage | null;
};

export type RuntimeStatus = {
  runningCount: number;
  profiles: Record<string, boolean>;
};

export type ProfileUsageWindow = {
  usedPercent: number;
  remainingPercent: number;
  windowSeconds: number;
  resetAt: number | null;
};

export type ProfileUsage = {
  fetchedAt: number;
  planType: string | null;
  oneWeek: ProfileUsageWindow | null;
  resetCredits?: number | null;
  resetCreditExpiresAt?: number[];
  hasCredits?: boolean;
  creditsUnlimited?: boolean;
  spendControlReached?: boolean;
  rateLimitReachedType?: string | null;
  error: string | null;
};

export type InstructionTemplate = {
  id: string;
  title: string;
  filename: string;
  content: string;
  enabled: boolean;
};

export type InstructionTemplateState = {
  templates: InstructionTemplate[];
  currentInstructionFile: string;
  activeConfigPath: string;
};

export type TomlConfigState = {
  path: string;
  exists: boolean;
  content: string;
  backupPath?: string;
};

export type UpdateEvent =
  | { status: "available"; currentVersion: string; version: string; releaseNotes?: string }
  | {
      status: "downloading";
      currentVersion: string;
      version: string;
      percent: number;
      transferred: number;
      total: number;
      bytesPerSecond: number;
    }
  | { status: "downloaded"; currentVersion: string; version: string; releaseNotes?: string }
  | { status: "not-available"; currentVersion: string; version: string; manual: boolean }
  | { status: "error"; message: string };

export type BackendProgress = {
  operation: string;
  profileName?: string;
  percent: number;
  copiedBytes?: number;
  totalBytes?: number;
};

export type CodexSkinTheme = {
  id: string;
  name: string;
  builtIn: boolean;
  previewDataUrl: string;
  focusX: number;
  focusY: number;
  safeArea: "left" | "right" | "center" | "none";
  appearance: "auto" | "light" | "dark";
};

export type CodexSkinThemeState = {
  activeThemeId: string;
  paused: boolean;
  themes: CodexSkinTheme[];
};

export type LauncherApi = {
  invoke: <T>(command: string, payload?: unknown) => Promise<BackendResponse<T>>;
  selectDirectory: (defaultPath?: string) => Promise<string>;
  selectAuthJsonFile: () => Promise<string>;
  selectProfileBackupFile?: () => Promise<string>;
  getCodexSkinState?: () => Promise<CodexSkinThemeState>;
  importCodexSkinTheme?: () => Promise<CodexSkinThemeState>;
  setActiveCodexSkinTheme?: (themeId: string) => Promise<CodexSkinThemeState>;
  deleteCodexSkinTheme?: (themeId: string) => Promise<CodexSkinThemeState>;
  setCodexSkinPaused?: (paused: boolean) => Promise<CodexSkinThemeState>;
  updateCodexSkinTheme?: (
    themeId: string,
    options: Pick<CodexSkinTheme, "focusX" | "focusY" | "safeArea" | "appearance">,
  ) => Promise<CodexSkinThemeState>;
  getAutoStartEnabled?: () => Promise<boolean>;
  getAppVersion?: () => Promise<string>;
  showNotification?: (title: string, body: string) => Promise<boolean>;
  openProjectGitHub?: () => Promise<void>;
  openProjectGitee?: () => Promise<void>;
  setAutoStartEnabled?: (enabled: boolean) => Promise<boolean>;
  onBackendProgress?: (callback: (progress: BackendProgress) => void) => () => void;
  onUpdateEvent?: (callback: (event: UpdateEvent) => void) => () => void;
  checkForUpdates?: () => Promise<void>;
  downloadUpdate?: () => Promise<void>;
  installUpdate?: () => Promise<void>;
  minimizeWindow: () => Promise<void>;
  isWindowMaximized: () => Promise<boolean>;
  onWindowMaximizedChanged: (callback: (maximized: boolean) => void) => () => void;
  toggleMaximizeWindow: () => Promise<void>;
  closeWindow: () => Promise<void>;
};

declare global {
  interface Window {
    launcherApi: LauncherApi;
  }
}
