import { app } from "electron";
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

type BackendResult = {
  ok: boolean;
  data: Record<string, unknown>;
  error: string;
};

export type BackendProgress = {
  operation: string;
  profileName?: string;
  percent: number;
  copiedBytes?: number;
  totalBytes?: number;
};

type BackendCommand = {
  command: string;
  args: string[];
  mode: "packaged" | "development";
};

const progressPrefix = "CODEX_FORGE_PROGRESS:";

function getProjectRoot(): string {
  return app.isPackaged ? process.resourcesPath : join(__dirname, "../..");
}

function getPythonRoot(projectRoot: string): string {
  return join(projectRoot, "python");
}

function getBackendCommand(): BackendCommand {
  const packagedBackend = join(process.resourcesPath, "main.exe");
  if (app.isPackaged && existsSync(packagedBackend)) {
    return { command: packagedBackend, args: [], mode: "packaged" };
  }
  const projectRoot = getProjectRoot();
  const pythonCommand = process.platform === "win32"
    ? join(projectRoot, "python", ".venv", "Scripts", "python.exe")
    : join(projectRoot, "python", ".venv", "bin", "python");
  return { command: pythonCommand, args: ["-m", "bridge.cli"], mode: "development" };
}

export function invokeBackend(
  commandName: string,
  payload: unknown,
  onProgress?: (progress: BackendProgress) => void,
): Promise<BackendResult> {
  const backend = getBackendCommand();
  const args = [...backend.args, commandName, JSON.stringify(payload ?? {})];
  const projectRoot = getProjectRoot();
  const cwd = backend.mode === "development" ? getPythonRoot(projectRoot) : projectRoot;

  return new Promise((resolve) => {
    const child = spawn(backend.command, args, { cwd, windowsHide: true });
    let stdout = "";
    let stderr = "";
    let stderrBuffer = "";
    let settled = false;

    const finish = (result: BackendResult) => {
      if (!settled) {
        settled = true;
        resolve(result);
      }
    };

    const consumeStderrLine = (line: string) => {
      if (!line.startsWith(progressPrefix)) {
        if (line.trim()) {
          stderr += `${line}\n`;
        }
        return;
      }
      try {
        const progress = JSON.parse(line.slice(progressPrefix.length)) as BackendProgress;
        onProgress?.(progress);
      } catch {
        stderr += `${line}\n`;
      }
    };

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk: string) => {
      stderrBuffer += chunk;
      const lines = stderrBuffer.split(/\r?\n/);
      stderrBuffer = lines.pop() ?? "";
      lines.forEach(consumeStderrLine);
    });
    child.on("error", (error) => {
      finish({
        ok: false,
        data: {},
        error: [error.message, `命令：${backend.command}`, `目录：${cwd}`, `模式：${backend.mode}`].join("\n"),
      });
    });
    child.on("close", () => {
      if (stderrBuffer) {
        consumeStderrLine(stderrBuffer);
      }
      const output = stdout.trim();
      if (output) {
        try {
          finish(JSON.parse(output) as BackendResult);
          return;
        } catch {
          finish({ ok: false, data: {}, error: output });
          return;
        }
      }
      finish({
        ok: false,
        data: {},
        error: [
          stderr.trim() || "后端无响应",
          `命令：${backend.command}`,
          `目录：${cwd}`,
          `模式：${backend.mode}`,
        ].join("\n"),
      });
    });
  });
}
