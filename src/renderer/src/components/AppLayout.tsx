import { useEffect, useState, type ReactNode } from "react";
import { Layout } from "antd";
import { Copy, Minus, Square, X } from "lucide-react";
import { useI18n } from "../i18n";
import type { AppState, ViewKey } from "../types";
import codexForgeLogo from "../assets/codex-forge-logo.png";

const { Sider } = Layout;

const windowButtonClass =
  "flex h-12 w-[46px] items-center justify-center border-0 bg-transparent text-[#263647] transition-colors duration-200 hover:bg-white/30 hover:text-slate-900";

const navButtonBaseClass =
  "flex h-11 w-full items-center gap-2.5 rounded-[9px] border border-transparent bg-transparent px-2.5 text-left text-sm font-bold text-white/90 hover:border-white/20 hover:bg-white/20 hover:text-white hover:[&_svg]:text-white [&_svg]:h-[17px] [&_svg]:w-[17px] [&_svg]:shrink-0 [&_svg]:text-white/75";

type MenuItem = {
  key: ViewKey;
  label: string;
  icon: ReactNode;
};

type AppLayoutProps = {
  activeView: ViewKey;
  launchMode: AppState["launchMode"];
  menuItems: MenuItem[];
  taskText: string;
  children: ReactNode;
  onChangeView: (view: ViewKey) => void;
};

export function AppLayout({
  activeView,
  launchMode,
  menuItems,
  taskText,
  children,
  onChangeView,
}: AppLayoutProps) {
  const { t } = useI18n();
  const [isMaximized, setIsMaximized] = useState(false);

  useEffect(() => {
    void window.launcherApi.isWindowMaximized().then(setIsMaximized);
    return window.launcherApi.onWindowMaximizedChanged(setIsMaximized);
  }, []);

  return (
    <Layout className="grid h-screen grid-rows-[48px_minmax(0,1fr)] overflow-hidden bg-[#e8f4f4] bg-shell-gradient">
      <div className="grid h-12 grid-cols-[auto_minmax(0,1fr)_auto] items-center border-b-0 bg-transparent [-webkit-app-region:drag]">
        <div className="relative h-full w-[236px] max-[960px]:w-[210px]">
          <div className="absolute left-[20px] top-[14px] flex items-center z-10">
            <div className="grid h-12 w-12 place-items-center rounded-[14px] bg-white shadow-[0_8px_20px_rgba(15,118,110,0.2)]">
              <img
                src={codexForgeLogo}
                alt=""
                className="h-[36px] w-[36px] object-contain"
                draggable={false}
              />
            </div>
            <div className="ml-3.5 flex min-w-0 flex-col gap-0.5">
              <span className="whitespace-nowrap text-[16px] font-extrabold tracking-wide text-white">
                Codex Forge
              </span>
              <div className="flex items-center gap-2 text-[11px] font-medium text-white/80">
                <span>{t("多开")}</span>
                <span className="h-[3px] w-[3px] rounded-full bg-white/40" />
                <span>{t("切换")}</span>
                <span className="h-[3px] w-[3px] rounded-full bg-white/40" />
                <span>{t("指令")}</span>
              </div>
            </div>
          </div>
        </div>
        <div className="h-full" />
        <div className="grid h-12 grid-cols-3 [-webkit-app-region:no-drag]">
          <button
            className={windowButtonClass}
            title={t("最小化")}
            onClick={() => window.launcherApi.minimizeWindow()}
          >
            <Minus size={14} strokeWidth={2} />
          </button>
          <button
            className={windowButtonClass}
            title={t(isMaximized ? "还原" : "最大化")}
            onClick={() => window.launcherApi.toggleMaximizeWindow()}
          >
            {isMaximized ? <Copy size={14} strokeWidth={2} /> : <Square size={14} strokeWidth={2} />}
          </button>
          <button
            className={`${windowButtonClass} hover:bg-[#ff4d4f] hover:text-white`}
            title={t("关闭")}
            onClick={() => window.launcherApi.closeWindow()}
          >
            <X size={14} strokeWidth={2} />
          </button>
        </div>
      </div>
      <Layout className="h-full min-h-0 overflow-hidden bg-transparent">
        <Sider
          width={236}
          className="h-full !min-w-[236px] !max-w-[236px] !basis-[236px] overflow-hidden border-r-0 !bg-transparent px-3.5 pb-3.5 pt-6 max-[960px]:!min-w-[210px] max-[960px]:!max-w-[210px] max-[960px]:!basis-[210px] [&_.ant-layout-sider-children]:grid [&_.ant-layout-sider-children]:h-full [&_.ant-layout-sider-children]:min-h-0 [&_.ant-layout-sider-children]:grid-rows-[1fr_auto] [&_.ant-layout-sider-children]:gap-4"
        >
          <nav className="grid min-h-0 content-start gap-1.5 pt-1">
            {menuItems.map((item) => (
              <NavButton
                key={item.key}
                item={item}
                active={activeView === item.key}
                onChangeView={onChangeView}
              />
            ))}
          </nav>
          <LaunchModeCard launchMode={launchMode} />
        </Sider>
        <Layout className="relative mb-3.5 mr-3.5 h-[calc(100%-14px)] min-w-0 overflow-hidden rounded-panel bg-shell-surface shadow-panel">
          {children}
        </Layout>
      </Layout>
    </Layout>
  );
}
function LaunchModeCard({ launchMode }: { launchMode: AppState["launchMode"] }) {
  const { t } = useI18n();
  const isMulti = launchMode === "multi";

  return (
    <div className="rounded-[9px] bg-black/10 px-3 py-2.5">
      <div className="text-[11px] font-medium text-white/60">{t("当前模式")}</div>
      <div className="mt-0.5 truncate text-[13px] font-semibold text-white/90">
        {isMulti ? t("多开隔离模式") : t("账号切换模式")}
      </div>
    </div>
  );
}

function NavButton({
  item,
  active,
  onChangeView,
}: {
  item: MenuItem;
  active: boolean;
  onChangeView: (view: ViewKey) => void;
}) {
  return (
    <button
      className={
        active
          ? `${navButtonBaseClass} border-white/20 bg-white/20 text-white [&_svg]:text-white`
          : navButtonBaseClass
      }
      onClick={() => onChangeView(item.key)}
    >
      {item.icon}
      <span>{item.label}</span>
    </button>
  );
}
