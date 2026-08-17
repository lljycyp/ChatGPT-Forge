import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Progress,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  message,
} from "antd";
import { Activity, FileText, FolderOpen, Plus, RefreshCw, Save, Server, Settings2, Trash2 } from "lucide-react";
import { invokeLauncher } from "../api/launcher";
import { useI18n } from "../i18n";
import type { AppState, ProfileSummary, ProfileUsage } from "../types";

type WorkspacePageProps = { appState: AppState; profiles: ProfileSummary[]; onDirtyChange: (dirty: boolean) => void };
type HistoryState = { items: ProfileUsage[]; pacePerDay: number | null };
type HealthCheck = { key: string; ok: boolean; message: string; severity: "ok" | "warning" | "error"; action?: string | null };
type HealthState = { name?: string; healthy: boolean; checks: HealthCheck[] };
type McpServer = { name: string; command?: string; args?: string[]; env?: Record<string, string>; enabled: boolean };
type Skill = { name: string; enabled: boolean; path: string; hasManifest: boolean };
type WorkspaceState = { codexHome: string; configError?: string; agentsPath: string; agentsContent: string; mcpServers: McpServer[]; skills: Skill[] };
type SessionItem = { id: string; title: string; projectPath: string; path: string; updatedAt: number; sizeBytes: number };
type LaunchSettings = { workingDir: string; args: string[]; env: Record<string, string> };
type WorkspaceSnapshot = {
  history?: HistoryState;
  health?: HealthState;
  workspace?: WorkspaceState;
  sessions?: { items: SessionItem[] };
  launchSettings?: LaunchSettings;
};
type WorkspaceTab = "insights" | "resources" | "sessions" | "launch";

const SYSTEM_PROFILE_NAME = "__system__";
const workspaceTabStorageKey = "chatgptForgeWorkspaceTab";
const workspaceSections: Record<WorkspaceTab, string[]> = {
  insights: ["history", "health"],
  resources: ["workspace"],
  sessions: ["sessions"],
  launch: ["launchSettings"],
};
const { TextArea } = Input;

export function WorkspacePage({ appState, profiles, onDirtyChange }: WorkspacePageProps) {
  const { t } = useI18n();
  const [profileName, setProfileName] = useState(appState.activeProfile || profiles[0]?.name || "");
  const [history, setHistory] = useState<HistoryState>({ items: [], pacePerDay: null });
  const [health, setHealth] = useState<HealthState>({ healthy: true, checks: [] });
  const [workspace, setWorkspace] = useState<WorkspaceState | null>(null);
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [agents, setAgents] = useState("");
  const [savedAgents, setSavedAgents] = useState("");
  const [launchSettings, setLaunchSettings] = useState<LaunchSettings>({ workingDir: "", args: [], env: {} });
  const [savedLaunchSettings, setSavedLaunchSettings] = useState<LaunchSettings>({ workingDir: "", args: [], env: {} });
  const [activeTab, setActiveTab] = useState<WorkspaceTab>(() => readWorkspaceTab());
  const [loading, setLoading] = useState(false);
  const launchDirty = useMemo(
    () => JSON.stringify(launchSettings) !== JSON.stringify(savedLaunchSettings),
    [launchSettings, savedLaunchSettings],
  );
  const dirty = agents !== savedAgents || launchDirty;

  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);

  useEffect(() => {
    if (!profileName && profiles[0]?.name) setProfileName(profiles[0].name);
  }, [profileName, profiles]);

  const workspacePayload = appState.launchMode === "multi" ? { profileName } : {};

  const refresh = useCallback(async (options?: { preserveEdits?: boolean }) => {
    if (!profileName) return;
    setLoading(true);
    try {
      const snapshot = await invokeLauncher<WorkspaceSnapshot>("get_workspace_snapshot", {
        ...workspacePayload,
        name: profileName,
        days: 30,
        limit: 300,
        sections: workspaceSections[activeTab],
      });
      if (snapshot.history) setHistory(snapshot.history);
      if (snapshot.health) setHealth(snapshot.health);
      if (snapshot.sessions) setSessions(snapshot.sessions.items);
      if (snapshot.workspace) {
        setWorkspace(snapshot.workspace);
        setSavedAgents(snapshot.workspace.agentsContent);
        if (!options?.preserveEdits) setAgents(snapshot.workspace.agentsContent);
      }
      if (snapshot.launchSettings) {
        setSavedLaunchSettings(snapshot.launchSettings);
        if (!options?.preserveEdits) setLaunchSettings(snapshot.launchSettings);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : t("读取工作台失败"));
    } finally {
      setLoading(false);
    }
  }, [activeTab, appState.launchMode, profileName, t]);

  useEffect(() => { void refresh(); }, [refresh]);

  const discardAndRun = (action: () => void) => {
    if (!dirty) {
      action();
      return;
    }
    Modal.confirm({
      title: t("有未保存的更改"),
      content: t("继续操作将丢失当前工作台中未保存的更改。"),
      okText: t("放弃更改"),
      cancelText: t("继续编辑"),
      onOk: () => {
        setAgents(savedAgents);
        setLaunchSettings(savedLaunchSettings);
        action();
      },
    });
  };

  const changeProfile = (nextProfileName: string) => {
    discardAndRun(() => setProfileName(nextProfileName));
  };

  const changeTab = (key: string) => {
    const nextTab = key as WorkspaceTab;
    localStorage.setItem(workspaceTabStorageKey, nextTab);
    setActiveTab(nextTab);
  };

  return (
    <div className="mx-auto grid w-full max-w-[1480px] gap-4 pb-8">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-panel border border-shell-line bg-white px-5 py-4 shadow-sm">
        <div>
          <div className="text-base font-bold text-slate-900">{t("Codex 环境工作台")}</div>
          <div className="mt-1 text-xs text-slate-500">{workspace?.codexHome || t("选择账号后读取环境")}</div>
        </div>
        <Space>
          <Select
            className="min-w-[260px]"
            value={profileName || undefined}
            options={profiles.map((profile) => ({ label: profile.name, value: profile.name }))}
            onChange={changeProfile}
          />
          <Button icon={<RefreshCw size={15} />} loading={loading} onClick={() => discardAndRun(() => void refresh())}>{t("刷新")}</Button>
        </Space>
      </div>
      {profiles.length === 0 ? <Empty description={t("请先添加账号")} /> : (
        <Tabs
          activeKey={activeTab}
          onChange={changeTab}
          items={[
            { key: "insights", label: t("额度与健康"), children: <InsightsPanel history={history} health={health} onRefresh={() => refresh({ preserveEdits: true })} /> },
            { key: "resources", label: t("MCP / Skills / AGENTS"), children: workspace ? <ResourcesPanel state={workspace} agents={agents} onAgentsChange={setAgents} payload={workspacePayload} onRefresh={() => refresh({ preserveEdits: true })} /> : null },
            { key: "sessions", label: t("会话索引"), children: <SessionsPanel items={sessions} /> },
            { key: "launch", label: t("启动环境"), children: <LaunchPanel name={profileName} value={launchSettings} onChange={setLaunchSettings} onSaved={(next) => { setLaunchSettings(next); setSavedLaunchSettings(next); }} /> },
          ]}
        />
      )}
    </div>
  );
}

function InsightsPanel({ history, health, onRefresh }: { history: HistoryState; health: HealthState; onRefresh: () => Promise<void> }) {
  const { t } = useI18n();
  const latest = history.items.at(-1)?.oneWeek;
  return (
    <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
      <Card title={t("30 天额度趋势")} extra={history.pacePerDay === null ? null : `${t("日均消耗")} ${history.pacePerDay}%`}>
        {latest ? (
          <div className="grid gap-5">
            <div><div className="mb-2 flex justify-between text-sm"><span>{t("一周剩余额度")}</span><b>{latest.remainingPercent}%</b></div><Progress percent={latest.remainingPercent} showInfo={false} strokeColor="#0f766e" /></div>
            <UsageSparkline items={history.items} />
            <div className="text-xs text-slate-500">{history.items.length} {t("个历史快照，自动保留 30 天")}</div>
          </div>
        ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t("刷新额度后开始积累历史数据")} />}
      </Card>
      <Card title={t("账号健康检查")} extra={<Tag color={health.healthy ? "green" : "red"}>{health.healthy ? t("可用") : t("需要处理")}</Tag>}>
        <List
          dataSource={health.checks}
          locale={{ emptyText: t("暂无检查结果") }}
          renderItem={(item) => <List.Item actions={item.action ? [<Button key="repair" size="small" onClick={async () => { await invokeLauncher("repair_profile", { name: health.name, action: item.action }); message.success(t("修复操作已完成")); await onRefresh(); }}>{item.action === "refresh-usage" ? t("重新检测") : t("修复")}</Button>] : []}><div className="flex items-start gap-3"><Tag color={item.ok ? "green" : item.severity === "warning" ? "orange" : "red"}>{item.ok ? "OK" : item.severity.toUpperCase()}</Tag><span className="text-sm text-slate-700">{item.message}</span></div></List.Item>}
        />
      </Card>
    </div>
  );
}

function UsageSparkline({ items }: { items: ProfileUsage[] }) {
  const points = items.flatMap((item) => item.oneWeek ? [{ x: item.fetchedAt, y: item.oneWeek.remainingPercent }] : []);
  if (points.length < 2) return null;
  const minX = points[0].x;
  const widthX = Math.max(1, points.at(-1)!.x - minX);
  const path = points.map((point, index) => `${index ? "L" : "M"}${((point.x - minX) / widthX) * 100},${100 - point.y}`).join(" ");
  return <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-44 w-full rounded-lg bg-slate-50 p-2"><path d={path} fill="none" stroke="#0f766e" strokeWidth="2" vectorEffect="non-scaling-stroke" /></svg>;
}

function ResourcesPanel({ state, agents, onAgentsChange, payload, onRefresh }: { state: WorkspaceState; agents: string; onAgentsChange: (value: string) => void; payload: object; onRefresh: () => Promise<void> }) {
  const { t } = useI18n();
  const [mcpOpen, setMcpOpen] = useState(false);
  const [editingMcp, setEditingMcp] = useState<McpServer | null>(null);
  const [mcpForm] = Form.useForm();

  const saveAgents = async () => {
    await invokeLauncher("save_agents", { ...payload, content: agents });
    message.success(t("AGENTS.md 已保存"));
    await onRefresh();
  };
  const editMcp = (server?: McpServer) => {
    setEditingMcp(server || null);
    mcpForm.setFieldsValue({
      name: server?.name || "",
      command: server?.command || "",
      args: (server?.args || []).join("\n"),
      env: Object.entries(server?.env || {}).map(([key, value]) => `${key}=${value}`).join("\n"),
    });
    setMcpOpen(true);
  };
  const saveMcp = async () => {
    const values = await mcpForm.validateFields();
    await invokeLauncher("save_mcp_server", {
      ...payload,
      server: {
        name: values.name,
        command: values.command,
        args: lines(values.args),
        env: envLines(values.env),
        enabled: editingMcp?.enabled ?? true,
      },
    });
    message.success(t("MCP 服务已保存"));
    setMcpOpen(false);
    setEditingMcp(null);
    await onRefresh();
  };
  const confirmDeleteMcp = (server: McpServer) => {
    Modal.confirm({
      title: t("确认删除 MCP 服务"),
      content: `${t("将从当前配置中删除")}「${server.name}」。`,
      okText: t("删除"),
      okButtonProps: { danger: true },
      cancelText: t("取消"),
      onOk: async () => {
        await invokeLauncher("delete_mcp_server", { ...payload, name: server.name });
        await onRefresh();
      },
    });
  };
  const confirmRemoveSkill = (skill: Skill) => {
    Modal.confirm({
      title: t("确认移除 Skill"),
      content: `${t("Skill 将移入备份目录")}：「${skill.name}」。`,
      okText: t("移除"),
      okButtonProps: { danger: true },
      cancelText: t("取消"),
      onOk: async () => {
        await invokeLauncher("remove_skill", { ...payload, name: skill.name });
        message.success(t("Skill 已移入备份目录"));
        await onRefresh();
      },
    });
  };

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {state.configError ? <Alert className="xl:col-span-2" type="error" showIcon message={state.configError} /> : null}
      <Card title={<span className="flex items-center gap-2"><Server size={16} />MCP</span>} extra={<Button size="small" icon={<Plus size={14} />} onClick={() => editMcp()}>{t("添加")}</Button>}>
        <Table
          size="small"
          pagination={false}
          rowKey="name"
          dataSource={state.mcpServers}
          columns={[
            { title: t("名称"), dataIndex: "name" },
            { title: t("命令"), dataIndex: "command", ellipsis: true },
            {
              title: "",
              width: 160,
              render: (_, server) => <Space>
                <Switch
                  aria-label={`${t("切换 MCP 状态")} ${server.name}`}
                  size="small"
                  checked={server.enabled}
                  onChange={async (enabled) => {
                    await invokeLauncher("set_mcp_enabled", { ...payload, name: server.name, enabled });
                    message.success(t("MCP 状态已更新，重启 Codex 后生效"));
                    await onRefresh();
                  }}
                />
                <Button size="small" onClick={() => editMcp(server)}>{t("编辑")}</Button>
                <Button aria-label={`${t("删除 MCP 服务")} ${server.name}`} size="small" danger icon={<Trash2 size={13} />} onClick={() => confirmDeleteMcp(server)} />
              </Space>,
            },
          ]}
        />
      </Card>
      <Card title={t("Skills")} extra={<Button size="small" icon={<Plus size={14} />} onClick={async () => { const sourcePath = await window.launcherApi.selectDirectory(); if (sourcePath) { await invokeLauncher("install_skill", { ...payload, sourcePath }); message.success(t("Skill 已安装")); await onRefresh(); } }}>{t("从目录安装")}</Button>}>
        <List dataSource={state.skills} locale={{ emptyText: t("当前环境没有 Skills") }} renderItem={(skill) => <List.Item actions={[<Switch key="enabled" aria-label={`${t("切换 Skill 状态")} ${skill.name}`} size="small" checked={skill.enabled} onChange={async (enabled) => { await invokeLauncher("set_skill_enabled", { ...payload, name: skill.name, enabled }); await onRefresh(); }} />, <Button key="remove" aria-label={`${t("移除 Skill")} ${skill.name}`} size="small" danger icon={<Trash2 size={13} />} onClick={() => confirmRemoveSkill(skill)} />]}><List.Item.Meta title={<Space>{skill.name}{!skill.hasManifest ? <Tag color="orange">{t("缺少 SKILL.md")}</Tag> : null}</Space>} description={skill.path} /></List.Item>} />
      </Card>
      <Card className="xl:col-span-2" title={<span className="flex items-center gap-2"><FileText size={16} />AGENTS.md</span>} extra={<Button type="primary" icon={<Save size={14} />} onClick={saveAgents}>{t("保存")}</Button>}>
        <TextArea className="!h-[320px] !font-mono !text-sm" value={agents} onChange={(event) => onAgentsChange(event.target.value)} />
      </Card>
      <Modal title={t("MCP 服务")} open={mcpOpen} onCancel={() => { setMcpOpen(false); setEditingMcp(null); }} onOk={saveMcp} okText={t("保存")}>
        <Form form={mcpForm} layout="vertical">
          <Form.Item name="name" label={t("名称")} rules={[{ required: true }]}><Input placeholder="playwright" /></Form.Item>
          <Form.Item name="command" label={t("命令")} rules={[{ required: true }]}><Input placeholder="npx" /></Form.Item>
          <Form.Item name="args" label={t("参数，每行一个")}><TextArea rows={4} /></Form.Item>
          <Form.Item name="env" label={t("环境变量，每行 KEY=VALUE")}><TextArea rows={4} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function SessionsPanel({ items }: { items: SessionItem[] }) {
  const { t } = useI18n();
  const [search, setSearch] = useState("");
  const filtered = useMemo(() => items.filter((item) => `${item.title} ${item.projectPath}`.toLowerCase().includes(search.toLowerCase())), [items, search]);
  return (
    <Card title={t("本地会话只读索引")} extra={<Input.Search allowClear className="w-[300px]" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("搜索标题或项目路径")} />}>
      <Alert className="mb-4" type="info" showIcon message={t("这里只读取会话元数据，不修改、迁移或恢复 Codex 内部文件。")}/>
      <Table rowKey="path" dataSource={filtered} pagination={{ pageSize: 20 }} columns={[
        { title: t("标题"), dataIndex: "title", ellipsis: true },
        { title: t("项目"), dataIndex: "projectPath", ellipsis: true },
        { title: t("最后活动"), dataIndex: "updatedAt", width: 180, render: (value) => new Date(value * 1000).toLocaleString() },
        { title: "", width: 60, render: (_, item) => <Button aria-label={`${t("打开会话文件")} ${item.title}`} icon={<FolderOpen size={14} />} onClick={() => void invokeLauncher("open_path", { path: item.path, reveal: true })} /> },
      ]} />
    </Card>
  );
}

function LaunchPanel({ name, value, onChange, onSaved }: { name: string; value: LaunchSettings; onChange: (value: LaunchSettings) => void; onSaved: (value: LaunchSettings) => void }) {
  const { t } = useI18n();
  const save = async () => {
    const next = await invokeLauncher<LaunchSettings>("save_profile_launch_settings", { name, ...value });
    onSaved(next);
    message.success(t("账号启动环境已保存"));
  };
  return (
    <Card title={<span className="flex items-center gap-2"><Settings2 size={16} />{t("账号级启动环境")}</span>} extra={<Button type="primary" icon={<Save size={14} />} onClick={save}>{t("保存")}</Button>}>
      <Descriptions column={1} bordered size="small">
        <Descriptions.Item label={t("默认项目目录")}><Input value={value.workingDir} onChange={(event) => onChange({ ...value, workingDir: event.target.value })} placeholder="D:\\Projects\\example" /></Descriptions.Item>
        <Descriptions.Item label={t("启动参数")}><TextArea rows={5} value={value.args.join("\n")} onChange={(event) => onChange({ ...value, args: lines(event.target.value) })} placeholder={t("每行一个参数")} /></Descriptions.Item>
        <Descriptions.Item label={t("环境变量")}><TextArea rows={8} value={Object.entries(value.env).map(([key, entry]) => `${key}=${entry}`).join("\n")} onChange={(event) => onChange({ ...value, env: envLines(event.target.value) })} placeholder="HTTP_PROXY=http://127.0.0.1:7890" /></Descriptions.Item>
      </Descriptions>
    </Card>
  );
}

function lines(value: string) { return String(value || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean); }
function envLines(value: string) {
  return Object.fromEntries(lines(value).map((line) => { const index = line.indexOf("="); return index > 0 ? [line.slice(0, index).trim(), line.slice(index + 1)] : [line, ""]; }));
}

function readWorkspaceTab(): WorkspaceTab {
  const value = localStorage.getItem(workspaceTabStorageKey);
  return value === "resources" || value === "sessions" || value === "launch" ? value : "insights";
}
