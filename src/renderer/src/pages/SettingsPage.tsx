import { useEffect, useState } from "react";
import { Alert, Button, Form, Input, InputNumber, message, Modal, Radio, Space, Switch } from "antd";
import { Bell, ClipboardCopy, EyeOff, FolderOpen, Github, HardDrive, Info, Power, RefreshCw } from "lucide-react";
import { invokeLauncher } from "../api/launcher";
import { useI18n } from "../i18n";
import type { AppState, RunCommand } from "../types";

type SettingsPageProps = {
  appState: AppState;
  privacyMode: boolean;
  runCommand: RunCommand;
  onPrivacyModeChange: (enabled: boolean) => void;
};

function GiteeIcon({ size = 16 }: { size?: number }) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 1024 1024"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <circle cx="512" cy="512" r="448" fill="#c71d23" />
      <path
        fill="#fff"
        d="M300 512c0-117 95-212 212-212h212v120H512a92 92 0 0 0 0 184h92v-72H484V412h240v312H512c-117 0-212-95-212-212Z"
      />
    </svg>
  );
}

export function SettingsPage({ appState, privacyMode, runCommand, onPrivacyModeChange }: SettingsPageProps) {
  const { language, setLanguage, t } = useI18n();
  const [form] = Form.useForm();
  const [autoStartEnabled, setAutoStartEnabled] = useState(false);
  const [appVersion, setAppVersion] = useState("");
  const [autoStartLoading, setAutoStartLoading] = useState(false);
  const [checkUpdateLoading, setCheckUpdateLoading] = useState(false);
  const [launchModeLoading, setLaunchModeLoading] = useState(false);
  const [codexSourceLoading, setCodexSourceLoading] = useState(false);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);
  const [quotaAlertsEnabled, setQuotaAlertsEnabled] = useState(() => localStorage.getItem("quotaAlertsEnabled") !== "false");
  const [quotaAlertThreshold, setQuotaAlertThreshold] = useState(() => Number(localStorage.getItem("quotaAlertThreshold") || "20"));

  useEffect(() => {
    form.setFieldsValue({
      profileRoot: appState.profileRoot,
    });
  }, [appState, form]);

  useEffect(() => {
    let disposed = false;
    void window.launcherApi.getAppVersion?.()
      .then((version) => {
        if (!disposed) {
          setAppVersion(version);
        }
      })
      .catch(() => undefined);
    const loadAutoStartEnabled = async () => {
      if (!window.launcherApi.getAutoStartEnabled) {
        message.warning(t("请重启启动器后再使用开机自启设置"));
        return;
      }
      try {
        const enabled = await window.launcherApi.getAutoStartEnabled();
        if (!disposed) {
          setAutoStartEnabled(enabled);
        }
      } catch (error) {
        if (!disposed) {
          message.error(error instanceof Error ? error.message : t("读取开机自启状态失败"));
        }
      }
    };
    void loadAutoStartEnabled();
    return () => {
      disposed = true;
    };
  }, [t]);

  const changeAutoStartEnabled = async (enabled: boolean) => {
    if (!window.launcherApi.setAutoStartEnabled) {
      message.warning(t("请重启启动器后再使用开机自启设置"));
      return;
    }
    const previousValue = autoStartEnabled;
    setAutoStartEnabled(enabled);
    setAutoStartLoading(true);
    try {
      const savedValue = await window.launcherApi.setAutoStartEnabled(enabled);
      setAutoStartEnabled(savedValue);
      message.success(savedValue ? t("已开启开机自启") : t("已关闭开机自启"));
    } catch (error) {
      setAutoStartEnabled(previousValue);
      message.error(error instanceof Error ? error.message : t("保存开机自启设置失败"));
    } finally {
      setAutoStartLoading(false);
    }
  };

  const checkForUpdates = async () => {
    if (!window.launcherApi.checkForUpdates) {
      message.warning(t("当前版本不支持手动检查更新，请重启后再试"));
      return;
    }
    setCheckUpdateLoading(true);
    try {
      message.info(t("正在检查更新"));
      await window.launcherApi.checkForUpdates();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t("检查更新失败"));
    } finally {
      setCheckUpdateLoading(false);
    }
  };

  const chooseProfileRoot = async () => {
    const selectedPath = await window.launcherApi.selectDirectory(
      appState.profileRoot || undefined,
    );
    if (!selectedPath) {
      return;
    }
    Modal.confirm({
      title: t("更改账号资料位置"),
      content: t("将迁移整个账号资料根目录。迁移期间请先关闭正在运行的 Codex。"),
      okText: t("开始迁移"),
      cancelText: t("取消"),
      onOk: async () => {
        form.setFieldsValue({ profileRoot: selectedPath });
        await runCommand(
          "set_profile_root",
          { profileRoot: selectedPath, asStorageLocation: true },
          t("账号资料位置已更新"),
        );
      },
    });
  };

  const saveLaunchMode = async (mode: "switch" | "multi") => {
    if (mode === appState.launchMode) {
      return;
    }
    setLaunchModeLoading(true);
    try {
      await runCommand(
        "set_launch_mode",
        { mode },
        mode === "multi" ? t("已切换到多开隔离模式") : t("已切换到账号切换模式"),
        { blocking: false },
      );
    } finally {
      setLaunchModeLoading(false);
    }
  };

  const changeLaunchMode = (mode: "switch" | "multi") => {
    if (mode === "multi") {
      Modal.confirm({
        title: t("切换到多开隔离模式"),
        content: appState.runningCount > 0
          ? (language === "en-US" ? "Codex is running. Close it first if possible. Isolated multi-instance mode creates one shared copy from the installed Codex client, then keeps each account's configuration and runtime data separate." : "检测到 Codex 正在运行。建议先关闭当前 Codex；多开隔离模式会从系统已安装的 Codex 客户端复制出一份共享副本，并分别隔离每个账号的配置和运行数据。")
          : (language === "en-US" ? "Isolated multi-instance mode creates one shared copy from the installed Codex client, then keeps each account's configuration and runtime data separate." : "多开隔离模式会从系统已安装的 Codex 客户端复制出一份共享副本，并分别隔离每个账号的配置和运行数据。"),
        okText: t("切换"),
        cancelText: t("取消"),
        onOk: () => saveLaunchMode(mode),
      });
      return;
    }
    void saveLaunchMode(mode);
  };

  const refreshCodexSource = async () => {
    setCodexSourceLoading(true);
    try {
      await runCommand(
        "refresh_codex_source",
        {},
        t("已重新识别 Codex 客户端"),
      );
    } finally {
      setCodexSourceLoading(false);
    }
  };

  const saveQuotaAlertSettings = (enabled: boolean, threshold = quotaAlertThreshold) => {
    const normalized = Math.max(1, Math.min(Number(threshold) || 20, 90));
    setQuotaAlertsEnabled(enabled);
    setQuotaAlertThreshold(normalized);
    localStorage.setItem("quotaAlertsEnabled", String(enabled));
    localStorage.setItem("quotaAlertThreshold", String(normalized));
  };

  const copyDiagnostics = async () => {
    setDiagnosticsLoading(true);
    try {
      const diagnostics = await invokeLauncher("get_diagnostics");
      await navigator.clipboard.writeText(JSON.stringify(redactDiagnostics(diagnostics), null, 2));
      message.success(t("诊断报告已复制"));
    } catch (error) {
      message.error(error instanceof Error ? error.message : t("复制诊断报告失败"));
    } finally {
      setDiagnosticsLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-[800px] pb-8 pt-2">
      <Form form={form} layout="vertical">
        <div className="mb-5 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded bg-brand-50 text-brand-600">
            <HardDrive size={16} />
          </div>
          <h2 className="m-0 text-lg font-bold leading-none text-slate-800">
            {t("账号资料")}
          </h2>
        </div>

        <div className="rounded-xl border border-[#e4ebf3] bg-slate-50/50 p-6">
          <Form.Item
            label={
              <span className="font-semibold text-slate-700">
                {t("账号资料根目录")}
              </span>
            }
            className="mb-0"
            extra=""
          >
            <Space.Compact className="w-full">
              <Form.Item name="profileRoot" noStyle>
                <Input
                  className="flex-1 bg-white"
                  placeholder="D:\CodexProfiles"
                />
              </Form.Item>
              <Button
                onClick={() =>
                  runCommand(
                    "set_profile_root",
                    { profileRoot: form.getFieldValue("profileRoot") },
                    t("已保存账号资料根目录"),
                  )
                }
              >
                {t("使用当前路径")}
              </Button>
              <Button
                type="primary"
                icon={<FolderOpen size={14} />}
                onClick={chooseProfileRoot}
              >
                {t("更改位置")}
              </Button>
            </Space.Compact>
          </Form.Item>
        </div>

        <div className="mb-5 mt-8 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded bg-brand-50 text-brand-600">
            <Power size={16} />
          </div>
          <h2 className="m-0 text-lg font-bold leading-none text-slate-800">
            {t("启动设置")}
          </h2>
        </div>

        <div className="rounded-xl border border-[#e4ebf3] bg-slate-50/50 p-6">
          <div className="mb-6 border-b border-slate-200 pb-5">
            <div className="mb-3 font-semibold text-slate-700">{t("启动模式")}</div>
            <Radio.Group
              value={appState.launchMode}
              disabled={launchModeLoading}
              onChange={(event) => changeLaunchMode(event.target.value)}
            >
              <Radio.Button value="switch">{t("账号切换模式")}</Radio.Button>
              <Radio.Button value="multi">{t("多开隔离模式")}</Radio.Button>
            </Radio.Group>
            <div className="mt-3 text-sm leading-6 text-slate-500">
              {t("账号切换模式共用系统 .codex；多开隔离模式为每个账号使用独立环境，可同时运行多个 Codex 客户端。")}
            </div>
            {appState.launchMode === "multi" ? (
              <Alert
                className="mt-3"
                type="warning"
                showIcon
                message={t("多开账号共用一份 Codex 客户端副本")}
                description={t("首次启动多开账号时会从系统已安装的客户端复制一份共享副本，新增账号不会重复复制。运行中的多开实例需要先关闭，才能切回账号切换模式。")}
              />
            ) : null}
          </div>
          <div className="mb-5 flex items-center justify-between gap-6 border-b border-slate-200 pb-5">
            <div className="min-w-0">
              <div className="font-semibold text-slate-700">{t("Codex 客户端来源")}</div>
              <div className="mt-1 text-sm leading-6 text-slate-500">
                {t("重新识别系统当前安装的 Codex 客户端；共享副本会在下次启动前同步更新。")}
              </div>
            </div>
            <Button
              icon={<RefreshCw size={14} />}
              loading={codexSourceLoading}
              onClick={() => void refreshCodexSource()}
            >
              {t("重新识别")}
            </Button>
          </div>
          <div className="flex items-center justify-between gap-6">
            <div className="min-w-0">
              <div className="font-semibold text-slate-700">{t("开机自启")}</div>
              <div className="mt-1 text-sm leading-6 text-slate-500">
                {t("登录 Windows 后自动启动 Codex Forge。")}
              </div>
            </div>
            <Switch
              checked={autoStartEnabled}
              loading={autoStartLoading}
              onChange={changeAutoStartEnabled}
            />
          </div>
          <div className="mt-5 flex items-center justify-between gap-6 border-t border-slate-200 pt-5">
            <div className="min-w-0">
              <div className="flex items-center gap-2 font-semibold text-slate-700">
                <Bell size={16} />
                {t("额度告警")}
              </div>
              <div className="mt-1 text-sm leading-6 text-slate-500">
                {t("自动刷新后，一周剩余额度低于阈值时发送一次 Windows 通知。")}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <InputNumber
                min={1}
                max={90}
                addonAfter="%"
                value={quotaAlertThreshold}
                disabled={!quotaAlertsEnabled}
                onChange={(value) => saveQuotaAlertSettings(quotaAlertsEnabled, Number(value) || 20)}
              />
              <Switch checked={quotaAlertsEnabled} onChange={(value) => saveQuotaAlertSettings(value)} />
            </div>
          </div>
        </div>

        <div className="mb-5 mt-8 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded bg-brand-50 text-brand-600">
            <Info size={16} />
          </div>
          <h2 className="m-0 text-lg font-bold leading-none text-slate-800">
            {t("关于")}
          </h2>
        </div>

        <div className="mb-4 rounded-xl border border-[#e4ebf3] bg-slate-50/50 p-6">
          <div className="flex items-center justify-between gap-6">
            <div className="min-w-0">
              <div className="font-semibold text-slate-700">{t("语言")}</div>
            </div>
            <Radio.Group value={language} onChange={(event) => setLanguage(event.target.value)}>
              <Radio.Button value="zh-CN">{t("中文")}</Radio.Button>
              <Radio.Button value="en-US">{t("English")}</Radio.Button>
            </Radio.Group>
          </div>
        </div>

        <div className="mb-4 rounded-xl border border-[#e4ebf3] bg-slate-50/50 p-6">
          <div className="flex items-center justify-between gap-6">
            <div className="min-w-0">
              <div className="flex items-center gap-2 font-semibold text-slate-700">
                <EyeOff size={16} />
                {t("隐私模式")}
              </div>
              <div className="mt-1 text-sm leading-6 text-slate-500">
                {t("隐藏账号邮箱、账号编号和系统用户名，便于截图或屏幕共享。")}
              </div>
            </div>
            <Switch checked={privacyMode} onChange={onPrivacyModeChange} />
          </div>
        </div>

        <div className="rounded-xl border border-[#e4ebf3] bg-slate-50/50 p-6">
          <div className="flex items-center justify-between gap-6">
            <div className="min-w-0">
              <div className="font-semibold text-slate-700">Codex Forge</div>
              <div className="mt-1 text-sm leading-6 text-slate-500">
                {t("当前版本")}
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="shrink-0 rounded bg-white px-3 py-1.5 text-sm font-bold text-brand-700 shadow-sm ring-1 ring-slate-900/5">
                {appVersion ? `v${appVersion}` : "-"}
              </div>
              <Button
                icon={<RefreshCw size={16} />}
                loading={checkUpdateLoading}
                onClick={checkForUpdates}
              >
                {t("检查更新")}
              </Button>
              <Button
                icon={<ClipboardCopy size={16} />}
                loading={diagnosticsLoading}
                onClick={copyDiagnostics}
              >
                {t("复制诊断报告")}
              </Button>
              <Button
                aria-label={t("打开 GitHub 项目")}
                icon={<Github size={16} />}
                onClick={() => {
                  void window.launcherApi.openProjectGitHub?.();
                }}
              />
              <Button
                aria-label={t("打开 Gitee 项目")}
                icon={<GiteeIcon size={16} />}
                onClick={() => {
                  void window.launcherApi.openProjectGitee?.();
                }}
              />
            </div>
          </div>
        </div>
      </Form>
    </div>
  );
}

function redactDiagnostics(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(redactDiagnostics);
  }
  if (!value || typeof value !== "object") {
    return redactPath(value);
  }
  return Object.fromEntries(
    Object.entries(value).map(([key, entry]) => {
      const lowered = key.toLowerCase();
      if (lowered.includes("token") || lowered.includes("auth") || lowered.includes("key")) {
        return [key, typeof entry === "boolean" ? entry : redactPath(entry)];
      }
      return [key, redactDiagnostics(entry)];
    }),
  );
}

function redactPath(value: unknown) {
  if (typeof value !== "string") {
    return value;
  }
  return value.replace(/C:\\Users\\[^\\/]+/gi, "C:\\Users\\<user>");
}
