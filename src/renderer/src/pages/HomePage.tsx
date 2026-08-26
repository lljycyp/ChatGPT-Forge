import { Button, Tooltip } from "antd";
import type { ReactNode } from "react";
import {
  Check,
  ChevronRight,
  Code2,
  FileText,
  FolderOpen,
  Play,
  Settings,
  ShieldAlert,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import { useI18n } from "../i18n";
import type { AppState, ProfileSummary, ViewKey } from "../types";

type HomePageProps = {
  appState: AppState;
  profiles: ProfileSummary[];
  onOpenView: (view: ViewKey) => void;
  onLaunchProfile: (profile: ProfileSummary) => void;
};

type EnvironmentCheck = {
  label: string;
  ok: boolean;
};

const panelClass =
  "rounded-panel border border-shell-line bg-white shadow-[0_10px_28px_rgba(15,23,42,0.045)]";

export function HomePage({ appState, profiles, onOpenView, onLaunchProfile }: HomePageProps) {
  const { t } = useI18n();
  const currentProfile =
    profiles.find((profile) => profile.name === appState.activeProfile)
    ?? profiles.find((profile) => profile.active)
    ?? null;
  const environmentChecks: EnvironmentCheck[] = [
    { label: t("ChatGPT 客户端"), ok: appState.codexCommandAvailable },
    { label: t("账号资料根目录"), ok: appState.profileRootExists },
    { label: "auth.json", ok: appState.activeAuthExists },
    { label: "config.toml", ok: appState.activeConfigExists },
  ];
  const attentionCount = environmentChecks.filter((item) => !item.ok).length;
  const environmentReady = attentionCount === 0;
  const hasRunningInstance = appState.runningCount > 0;
  const heroTitle = environmentReady ? t("Codex Forge 已就绪") : t("当前工作环境存在需要处理的问题");
  const heroDescription = environmentReady
    ? t("当前工作环境可以正常使用")
    : t("请先处理环境问题后再启动 ChatGPT");
  const primaryText = hasRunningInstance
    ? t("查看运行实例")
    : currentProfile
      ? t("启动 ChatGPT")
      : t("选择账号");

  const handlePrimaryAction = () => {
    if (hasRunningInstance || !currentProfile) {
      onOpenView("profiles");
      return;
    }
    onLaunchProfile(currentProfile);
  };

  return (
    <div className="mx-auto grid w-full max-w-[1480px] gap-4">
      <section className="relative overflow-hidden rounded-panel border border-brand-100 bg-[radial-gradient(circle_at_10%_45%,rgba(13,148,136,0.12),transparent_24%),linear-gradient(115deg,#f2fcfa_0%,#fff_58%,#f6fbff_100%)] px-6 py-5 shadow-[0_12px_30px_rgba(13,148,136,0.07)] max-[960px]:px-4">
        <div className="relative z-[1] grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-5 max-[960px]:grid-cols-[auto_minmax(0,1fr)]">
          <div className={`relative grid h-[68px] w-[68px] shrink-0 place-items-center rounded-full text-white shadow-[0_14px_28px_rgba(13,148,136,0.22)] ${environmentReady ? "bg-brand-600" : "bg-amber-500"}`}>
            <span className="absolute inset-[-9px] rounded-full border border-current opacity-15" />
            <span className="absolute inset-[-17px] rounded-full border border-current opacity-10" />
            {environmentReady ? <Check size={34} strokeWidth={3} /> : <ShieldAlert size={30} />}
          </div>

          <div className="min-w-0">
            <h2 className="m-0 text-[24px] font-extrabold leading-tight tracking-[-0.025em] text-slate-950">{heroTitle}</h2>
            <p className="mb-0 mt-1 text-[13px] font-medium text-slate-500">{heroDescription}</p>
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-[12px] font-semibold text-slate-500">
              <HeroMeta tone={hasRunningInstance ? "green" : "slate"} text={hasRunningInstance ? t("运行中") : t("空闲")} />
              <span className="h-4 w-px bg-slate-200" aria-hidden />
              <HeroMeta icon={<Code2 size={13} />} text={formatLaunchMode(appState.launchMode, t)} />
              <span className="h-4 w-px bg-slate-200" aria-hidden />
              <HeroMeta icon={<UsersRound size={13} />} text={appState.activeProfile || t("未选择")} />
            </div>
          </div>

          <div className="flex items-center gap-2 max-[960px]:col-span-2 max-[960px]:ml-[88px] max-[720px]:ml-0 max-[720px]:w-full max-[720px]:flex-col">
            <Button
              className="!h-10 !min-w-[144px] !rounded-[8px] !font-bold max-[720px]:!w-full"
              type="primary"
              icon={hasRunningInstance ? <UsersRound size={15} /> : <Play size={15} />}
              disabled={!environmentReady && !hasRunningInstance}
              onClick={handlePrimaryAction}
            >
              {primaryText}
            </Button>
            <Button className="!h-10 !rounded-[8px] !font-semibold max-[720px]:!w-full" icon={<UsersRound size={15} />} onClick={() => onOpenView("profiles")}>
              {t("切换账号")}
            </Button>
          </div>
        </div>
      </section>

      <section className={`${panelClass} grid grid-cols-3 divide-x divide-slate-100 px-2 py-3 max-[720px]:grid-cols-1 max-[720px]:divide-x-0 max-[720px]:divide-y`} aria-label={t("当前状态")}>
        <StatusMetric label={t("已保存账号")} value={profiles.length || appState.profileCount} tone="green" />
        <StatusMetric label={t("运行实例")} value={appState.runningCount} tone="blue" />
        <StatusMetric label={t("需要处理")} value={attentionCount} tone={attentionCount ? "amber" : "slate"} />
      </section>

      <div className="grid grid-cols-[0.95fr_1.05fr] gap-4 max-[960px]:grid-cols-1">
        <section className={`${panelClass} flex min-h-[292px] flex-col p-5`}>
          <PanelHeading icon={<FolderOpen size={16} />} title={t("当前工作区")} />
          <div className="mt-4 divide-y divide-slate-100">
            <WorkspaceRow label={t("当前账号")} value={appState.activeProfile || t("未选择")} />
            <WorkspaceRow label={t("启动模式")} value={formatLaunchMode(appState.launchMode, t)} />
            <WorkspaceRow label={t("配置来源")} value={appState.launchMode === "multi" ? t("账号 CodexHome 配置") : t("系统 config.toml")} />
            <WorkspaceRow label={t("认证存储")} value={appState.authCredentialStore === "file" ? "auth.json" : appState.authCredentialStore} />
          </div>
          <div className="mt-auto grid grid-cols-2 gap-2 pt-4 max-[600px]:grid-cols-1">
            <Button icon={<UsersRound size={14} />} onClick={() => onOpenView("profiles")}>{t("管理账号")}</Button>
            <Button icon={<Code2 size={14} />} onClick={() => onOpenView("toml")}>{t("编辑 TOML")}</Button>
          </div>
        </section>

        <section className={`${panelClass} flex min-h-[292px] flex-col p-5`}>
          <div className="flex items-center justify-between gap-3">
            <PanelHeading icon={<ShieldCheck size={16} />} title={t("环境检查")} />
            <span className={`inline-flex h-6 items-center rounded-[7px] px-2.5 text-[11.5px] font-bold ${environmentReady ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
              {environmentReady ? t("全部正常") : t("存在问题")}
            </span>
          </div>
          <div className="mt-4 divide-y divide-slate-100 rounded-[9px] border border-slate-200 px-3">
            {environmentChecks.map((item) => <EnvironmentRow key={item.label} item={item} t={t} />)}
          </div>
          <button type="button" className="mt-auto flex w-fit appearance-none items-center gap-1 border-0 bg-transparent p-0 pt-4 text-[12px] font-semibold text-brand-600 hover:text-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500" onClick={() => onOpenView("settings")}>
            {t("查看诊断详情")}<ChevronRight size={13} />
          </button>
        </section>
      </div>

      <nav className={`${panelClass} grid grid-cols-4 divide-x divide-slate-100 overflow-hidden px-2 py-2 max-[800px]:grid-cols-2 max-[800px]:divide-x-0`} aria-label={t("快捷入口")}>
        <QuickEntry icon={<UsersRound size={19} />} label={t("账号管理")} onClick={() => onOpenView("profiles")} />
        <QuickEntry icon={<Code2 size={19} />} label={t("TOML 配置")} onClick={() => onOpenView("toml")} />
        <QuickEntry icon={<FileText size={19} />} label={t("指令模板")} onClick={() => onOpenView("instructions")} />
        <QuickEntry icon={<Settings size={19} />} label={t("应用设置")} onClick={() => onOpenView("settings")} />
      </nav>
    </div>
  );
}

function HeroMeta({ icon, text, tone = "slate" }: { icon?: ReactNode; text: string; tone?: "green" | "slate" }) {
  return (
    <span className={`inline-flex min-w-0 items-center gap-1.5 ${tone === "green" ? "text-emerald-700" : "text-slate-500"}`}>
      {tone === "green" ? <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" /> : icon}
      <span className="truncate">{text}</span>
    </span>
  );
}

function StatusMetric({ label, value, tone }: { label: string; value: number; tone: "green" | "blue" | "amber" | "slate" }) {
  const dotClass = tone === "green" ? "bg-emerald-500" : tone === "blue" ? "bg-blue-500" : tone === "amber" ? "bg-amber-500" : "bg-slate-300";
  return (
    <div className="flex min-h-[46px] items-center justify-center gap-4 px-4 max-[720px]:justify-between">
      <span className="flex items-center gap-2 text-[13px] font-semibold text-slate-500"><span className={`h-2 w-2 rounded-full ${dotClass}`} />{label}</span>
      <strong className="text-[24px] font-extrabold leading-none tracking-[-0.04em] text-slate-900 tabular-nums">{value}</strong>
    </div>
  );
}

function PanelHeading({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="grid h-8 w-8 place-items-center rounded-[8px] bg-brand-50 text-brand-600">{icon}</span>
      <h2 className="m-0 text-[16px] font-extrabold text-slate-900">{title}</h2>
    </div>
  );
}

function WorkspaceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[120px_minmax(0,1fr)] items-center gap-3 py-3 text-[13px] max-[560px]:grid-cols-1 max-[560px]:gap-1">
      <span className="font-semibold text-slate-500">{label}</span>
      <Tooltip title={value}><span className="min-w-0 truncate text-right font-semibold text-slate-700 max-[560px]:text-left">{value}</span></Tooltip>
    </div>
  );
}

function EnvironmentRow({ item, t }: { item: EnvironmentCheck; t: (text: string) => string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-3 text-[13px]">
      <span className="flex min-w-0 items-center gap-2 font-medium text-slate-600">
        <span className={`h-2 w-2 shrink-0 rounded-full ${item.ok ? "bg-emerald-500" : "bg-amber-500"}`} />
        <span className="truncate">{item.label}</span>
      </span>
      <span className={`shrink-0 text-[12px] font-bold ${item.ok ? "text-emerald-700" : "text-amber-700"}`}>{item.ok ? t("正常") : t("需处理")}</span>
    </div>
  );
}

function QuickEntry({ icon, label, onClick }: { icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <button type="button" className="group flex min-h-[54px] appearance-none items-center gap-3 border-0 bg-transparent px-5 text-left text-[13px] font-bold text-slate-700 transition-colors hover:bg-brand-50/70 hover:text-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-brand-500" onClick={onClick}>
      <span className="text-brand-600">{icon}</span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
      <ChevronRight size={14} className="shrink-0 text-slate-400 transition-transform group-hover:translate-x-0.5" />
    </button>
  );
}

function formatLaunchMode(mode: AppState["launchMode"], t: (text: string) => string) {
  return mode === "multi" ? t("多开隔离模式") : t("账号切换模式");
}
