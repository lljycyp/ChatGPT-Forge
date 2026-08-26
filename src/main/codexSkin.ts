type SkinLaunchSession = {
  profileName: string;
  port: number;
  processId: number;
};

type CdpTarget = {
  id: string;
  type: string;
  url: string;
  webSocketDebuggerUrl?: string;
};

type InstalledTarget = {
  scriptId: string | null;
  webSocketUrl: string;
};

type ActiveSession = {
  port: number;
  timer: NodeJS.Timeout;
  targets: Map<string, InstalledTarget>;
  stopped: boolean;
};

const sessions = new Map<string, ActiveSession>();
const pollIntervalMs = 1500;
const styleId = "codex-forge-codex-skin";
const stateKey = "__CODEX_FORGE_CODEX_SKIN__";
let activeTheme: CodexSkinThemePayload = {
  id: "builtin-aurora",
  name: "Forge Aurora",
  imageDataUrl: "",
  focusX: 50,
  focusY: 50,
  safeArea: "left",
  appearance: "auto",
};
let paused = false;

export function hasCodexSkinSessions(): boolean {
  return sessions.size > 0;
}

const skinCss = `
:root[data-codex-forge-skin="active"] {
  --forge-skin-bg: #0a0d12;
  --forge-skin-bg-rgb: 10 13 18;
  --forge-skin-panel: 18 22 28;
  --forge-skin-line: 148 163 184;
  --forge-skin-accent: 94 234 212;
  --forge-skin-art:
    radial-gradient(circle at 82% 18%, rgba(45, 212, 191, .24), transparent 32%),
    radial-gradient(circle at 64% 76%, rgba(59, 130, 246, .18), transparent 38%),
    linear-gradient(135deg, #061018 0%, #0b2029 46%, #101827 100%);
  --forge-skin-safe-scrim: linear-gradient(rgb(var(--forge-skin-bg-rgb) / .10), rgb(var(--forge-skin-bg-rgb) / .10));
  --forge-skin-task-shade: linear-gradient(180deg, rgb(var(--forge-skin-bg-rgb) / .64), rgb(var(--forge-skin-bg-rgb) / .84));
}

:root.electron-light[data-codex-forge-skin="active"] {
  --forge-skin-bg: #f2f4f6;
  --forge-skin-bg-rgb: 242 244 246;
  --forge-skin-panel: 250 251 252;
  --forge-skin-line: 100 116 139;
  --forge-skin-accent: 15 118 110;
  --forge-skin-art:
    radial-gradient(circle at 82% 18%, rgba(45, 212, 191, .22), transparent 32%),
    radial-gradient(circle at 64% 76%, rgba(96, 165, 250, .18), transparent 38%),
    linear-gradient(135deg, #eefcf9 0%, #e4f4f3 46%, #edf3fb 100%);
  --forge-skin-safe-scrim: linear-gradient(rgb(var(--forge-skin-bg-rgb) / .14), rgb(var(--forge-skin-bg-rgb) / .14));
  --forge-skin-task-shade: linear-gradient(180deg, rgb(var(--forge-skin-bg-rgb) / .68), rgb(var(--forge-skin-bg-rgb) / .88));
}

:root[data-codex-forge-skin="active"][data-forge-skin-appearance="light"] {
  color-scheme: light;
  --forge-skin-bg: #f2f4f6;
  --forge-skin-bg-rgb: 242 244 246;
  --forge-skin-panel: 250 251 252;
  --forge-skin-line: 100 116 139;
  --forge-skin-accent: 15 118 110;
}

:root[data-codex-forge-skin="active"][data-forge-skin-appearance="dark"] {
  color-scheme: dark;
  --forge-skin-bg: #0a0d12;
  --forge-skin-bg-rgb: 10 13 18;
  --forge-skin-panel: 18 22 28;
  --forge-skin-line: 148 163 184;
  --forge-skin-accent: 94 234 212;
}

html[data-codex-forge-skin="active"] body {
  background-color: var(--forge-skin-bg) !important;
  background-image: var(--forge-skin-art-source, var(--forge-skin-art)) !important;
  background-attachment: fixed !important;
  background-position: var(--forge-skin-position, center) !important;
  background-repeat: no-repeat !important;
  background-size: cover !important;
}

html[data-codex-forge-skin="active"] main.main-surface {
  position: relative;
  isolation: isolate;
  overflow: hidden;
  background: transparent !important;
}

html[data-codex-forge-skin="active"] main.main-surface::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  background: transparent;
  opacity: 0;
}

html[data-codex-forge-skin="active"][data-forge-skin-page="home"] main.main-surface::before {
  background:
    linear-gradient(180deg, transparent 52%, rgb(var(--forge-skin-bg-rgb) / .22)),
    var(--forge-skin-safe-scrim);
  opacity: 1;
}

html[data-codex-forge-skin="active"][data-forge-skin-page="task"] main.main-surface::before {
  background: var(--forge-skin-task-shade), var(--forge-skin-safe-scrim);
  opacity: 1;
  backdrop-filter: blur(2px) saturate(92%);
}

html[data-codex-forge-skin="active"][data-forge-skin-page="settings"] main.main-surface {
  background: rgb(var(--forge-skin-panel) / .96) !important;
}

html[data-codex-forge-skin="active"] [role="main"],
html[data-codex-forge-skin="active"] main.main-surface :is(div, section, aside)[class~="bg-token-main-surface-primary"] {
  background: transparent !important;
}

html[data-codex-forge-skin="active"] main.main-surface div[class~="bg-token-main-surface-primary"][class~="border-l"] {
  background: rgb(var(--forge-skin-panel) / .72) !important;
  backdrop-filter: blur(10px) saturate(106%);
}

html[data-codex-forge-skin="active"] aside.app-shell-left-panel {
  background: rgb(var(--forge-skin-panel) / .68) !important;
  border-right: 1px solid rgb(var(--forge-skin-line) / .16) !important;
  box-shadow: inset -1px 0 rgb(255 255 255 / .04);
  backdrop-filter: blur(16px) saturate(108%);
}

html[data-codex-forge-skin="active"][data-forge-skin-page="home"][data-forge-skin-wide="true"] aside.app-shell-left-panel {
  background: rgb(var(--forge-skin-panel) / .46) !important;
  backdrop-filter: blur(10px) saturate(104%);
}

html[data-codex-forge-skin="active"][data-forge-skin-page="task"] aside.app-shell-left-panel {
  background: rgb(var(--forge-skin-panel) / .78) !important;
}

html[data-codex-forge-skin="active"][data-forge-skin-page="settings"] aside.app-shell-left-panel {
  background: rgb(var(--forge-skin-panel) / .96) !important;
  backdrop-filter: none;
}

html[data-codex-forge-skin="active"] aside.app-shell-left-panel button,
html[data-codex-forge-skin="active"] aside.app-shell-left-panel a {
  transition: background-color 180ms ease, color 180ms ease, border-color 180ms ease !important;
}

html[data-codex-forge-skin="active"] aside.app-shell-left-panel button:hover,
html[data-codex-forge-skin="active"] aside.app-shell-left-panel a:hover {
  background-color: rgb(var(--forge-skin-accent) / .10) !important;
}

html[data-codex-forge-skin="active"] aside.app-shell-left-panel [aria-current="page"] {
  background-color: rgb(var(--forge-skin-accent) / .14) !important;
  box-shadow: inset 0 0 0 1px rgb(var(--forge-skin-accent) / .20);
}

html[data-codex-forge-skin="active"] header.app-header-tint {
  background: rgb(var(--forge-skin-panel) / .52) !important;
  border-bottom-color: rgb(var(--forge-skin-line) / .16) !important;
  box-shadow: inset 0 -1px rgb(255 255 255 / .04);
  backdrop-filter: blur(12px) saturate(106%);
}

html[data-codex-forge-skin="active"][data-forge-skin-page="home"][data-forge-skin-wide="true"] header.app-header-tint {
  background: rgb(var(--forge-skin-panel) / .36) !important;
}

html[data-codex-forge-skin="active"][data-forge-skin-page="task"] header.app-header-tint {
  background: rgb(var(--forge-skin-panel) / .70) !important;
}

html[data-codex-forge-skin="active"] [role="dialog"],
html[data-codex-forge-skin="active"] [role="menu"],
html[data-codex-forge-skin="active"] [data-radix-popper-content-wrapper] > * {
  background-color: rgb(var(--forge-skin-panel) / .94) !important;
  border-color: rgb(var(--forge-skin-line) / .22) !important;
  box-shadow: 0 18px 50px rgb(var(--forge-skin-bg-rgb) / .26), inset 0 1px rgb(255 255 255 / .08) !important;
  backdrop-filter: blur(18px) saturate(108%);
}

html[data-codex-forge-skin="active"] .composer-surface-chrome {
  background-color: rgb(var(--forge-skin-panel) / .72) !important;
  border-color: rgb(var(--forge-skin-line) / .18) !important;
  box-shadow:
    inset 0 0 0 1px rgb(var(--forge-skin-line) / .16),
    inset 0 1px rgb(255 255 255 / .08) !important;
  backdrop-filter: blur(14px) saturate(106%);
}

html[data-codex-forge-skin="active"][data-forge-skin-page="home"][data-forge-skin-wide="true"] .composer-surface-chrome {
  background-color: rgb(var(--forge-skin-panel) / .58) !important;
  backdrop-filter: blur(10px) saturate(103%);
}

html[data-codex-forge-skin="active"][data-forge-skin-page="task"] .composer-surface-chrome {
  background-color: rgb(var(--forge-skin-panel) / .68) !important;
}

html[data-codex-forge-skin="active"][data-forge-skin-page="task"]
  .thread-scroll-container
  div[class~="bg-gradient-to-t"][class~="from-token-main-surface-primary"][class~="via-token-main-surface-primary"] {
  background: transparent !important;
  background-image: none !important;
}

html[data-codex-forge-skin="active"] :is(.group\\/home-suggestions, .group\\/project-selector, [class*="_homeUtilityBar_"], [data-feature="game-source"]) {
  border-color: rgb(var(--forge-skin-line) / .16) !important;
  background-color: rgb(var(--forge-skin-panel) / .40) !important;
  box-shadow: inset 0 1px rgb(255 255 255 / .06);
  backdrop-filter: blur(10px) saturate(104%);
}

html[data-codex-forge-skin="active"][data-forge-skin-page="task"] main.main-surface article {
  border-color: rgb(var(--forge-skin-line) / .12) !important;
  background-color: rgb(var(--forge-skin-panel) / .52) !important;
  box-shadow: none;
  backdrop-filter: blur(6px) saturate(102%);
}
`;

function buildInstallExpression(theme: CodexSkinThemePayload): string {
  return `(() => {
  const id = ${JSON.stringify(styleId)};
  const key = ${JSON.stringify(stateKey)};
  const css = ${JSON.stringify(skinCss)};
  const image = ${JSON.stringify(theme.imageDataUrl)};
  const focusX = ${JSON.stringify(theme.focusX)};
  const focusY = ${JSON.stringify(theme.focusY)};
  const safeArea = ${JSON.stringify(theme.safeArea)};
  const appearance = ${JSON.stringify(theme.appearance)};
  const previous = window[key];
  if (previous && typeof previous.remove === "function") previous.remove();
  const style = document.getElementById(id) || document.createElement("style");
  style.id = id;
  style.textContent = css;
  (document.head || document.documentElement).appendChild(style);
  const root = document.documentElement;
  root.setAttribute("data-codex-forge-skin", "active");
  root.setAttribute("data-forge-skin-appearance", appearance);
  const token = {};
  let frame = 0;
  let sampledPalette = null;
  let composition = {
    focusX,
    focusY,
    safeArea: image ? "none" : safeArea,
    wide: false,
  };
  let artObjectUrl = "";
  const clamp = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));
  const mix = (source, target, targetWeight) => source.map((value, index) =>
    Math.round(value * (1 - targetWeight) + target[index] * targetWeight));
  const isLight = () => appearance === "light" || (appearance === "auto" && root.classList.contains("electron-light"));
  const applyComposition = () => {
    const area = composition.safeArea;
    const light = isLight();
    const directionalStrength = light ? .68 : .58;
    const direction = area === "right" ? "270deg" : "90deg";
    const scrim = area === "left" || area === "right"
      ? "linear-gradient(" + direction + ", rgb(var(--forge-skin-bg-rgb) / " + directionalStrength + ") 0%, rgb(var(--forge-skin-bg-rgb) / .16) 36%, transparent 64%)"
      : "linear-gradient(rgb(var(--forge-skin-bg-rgb) / " + (light ? .14 : .10) + "), rgb(var(--forge-skin-bg-rgb) / " + (light ? .14 : .10) + "))";
    root.setAttribute("data-forge-skin-wide", composition.wide ? "true" : "false");
    root.setAttribute("data-forge-skin-safe-area", area);
    root.style.setProperty("--forge-skin-position", composition.focusX + "% " + composition.focusY + "%");
    root.style.setProperty("--forge-skin-safe-scrim", scrim);
    root.style.setProperty(
      "--forge-skin-task-shade",
      light
        ? "linear-gradient(180deg, rgb(var(--forge-skin-bg-rgb) / .68), rgb(var(--forge-skin-bg-rgb) / .88))"
        : "linear-gradient(180deg, rgb(var(--forge-skin-bg-rgb) / .64), rgb(var(--forge-skin-bg-rgb) / .84))",
    );
  };
  const applyPalette = () => {
    if (!sampledPalette) return;
    const light = isLight();
    const background = mix(sampledPalette.average, light ? [244, 246, 248] : [8, 11, 16], light ? .88 : .82);
    const panel = mix(sampledPalette.average, light ? [251, 252, 253] : [18, 21, 27], light ? .91 : .76);
    const accent = mix(sampledPalette.accent, light ? [45, 55, 72] : [225, 231, 238], light ? .16 : .12);
    root.style.setProperty("--forge-skin-bg", "rgb(" + background.join(" ") + ")");
    root.style.setProperty("--forge-skin-bg-rgb", background.join(" "));
    root.style.setProperty("--forge-skin-panel", panel.join(" "));
    root.style.setProperty("--forge-skin-line", accent.join(" "));
    root.style.setProperty("--forge-skin-accent", accent.join(" "));
  };
  const updatePageState = () => {
    const settings = Boolean(document.querySelector('input[name="appearance-theme"]'));
    const home = !settings && (Boolean(document.querySelector('[data-testid="home-icon"]'))
      || Boolean(document.querySelector('main.main-surface [role="main"]')));
    root.setAttribute("data-forge-skin-page", settings ? "settings" : home ? "home" : "task");
    applyPalette();
    applyComposition();
  };
  const queuePageUpdate = () => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      updatePageState();
    });
  };
  if (image) {
    try {
      const separator = image.indexOf(",");
      const mimeEnd = image.indexOf(";");
      const mimeType = image.startsWith("data:") && mimeEnd > 5 ? image.slice(5, mimeEnd) : "image/png";
      const binary = atob(image.slice(separator + 1));
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      artObjectUrl = URL.createObjectURL(new Blob([bytes], { type: mimeType }));
    } catch {}
    const artSource = artObjectUrl || image;
    root.style.setProperty("--forge-skin-art-source", 'url("' + artSource + '")');
    const paletteImage = new Image();
    paletteImage.onload = () => {
      if (!window[key] || window[key].token !== token) return;
      try {
        const canvas = document.createElement("canvas");
        const width = 64;
        const height = 36;
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) return;
        context.drawImage(paletteImage, 0, 0, width, height);
        const pixels = context.getImageData(0, 0, width, height).data;
        const total = [0, 0, 0];
        const luminance = new Float32Array(width * height);
        const saturation = new Float32Array(width * height);
        let count = 0;
        let best = [148, 163, 184];
        let bestScore = -1;
        for (let pixelIndex = 0; pixelIndex < width * height; pixelIndex += 1) {
          const index = pixelIndex * 4;
          if (pixels[index + 3] < 180) continue;
          const color = [pixels[index], pixels[index + 1], pixels[index + 2]];
          const high = Math.max(...color);
          const low = Math.min(...color);
          const pixelLuminance = (color[0] * .2126 + color[1] * .7152 + color[2] * .0722) / 255;
          const pixelSaturation = high === 0 ? 0 : (high - low) / high;
          luminance[pixelIndex] = pixelLuminance;
          saturation[pixelIndex] = pixelSaturation;
          total[0] += color[0];
          total[1] += color[1];
          total[2] += color[2];
          count += 1;
          const colorScore = pixelSaturation * (1 - Math.abs(pixelLuminance - .55));
          if (pixelLuminance > .08 && pixelLuminance < .94 && colorScore > bestScore) {
            bestScore = colorScore;
            best = color;
          }
        }
        if (count) {
          sampledPalette = {
            average: total.map((value) => Math.round(value / count)),
            accent: best,
          };
          let leftInformation = 0;
          let rightInformation = 0;
          let saliencyTotal = 0;
          let saliencyX = 0;
          let saliencyY = 0;
          for (let y = 0; y < height; y += 1) {
            for (let x = 0; x < width; x += 1) {
              const pixelIndex = y * width + x;
              const current = luminance[pixelIndex];
              const horizontal = x > 0 ? Math.abs(current - luminance[pixelIndex - 1]) : 0;
              const vertical = y > 0 ? Math.abs(current - luminance[pixelIndex - width]) : 0;
              const edge = horizontal + vertical;
              const information = edge * 1.8 + saturation[pixelIndex] * .18 + .01;
              if (x < width / 3) leftInformation += information;
              if (x >= width * 2 / 3) rightInformation += information;
              const saliency = edge * 1.6 + saturation[pixelIndex] * .28 + .01;
              saliencyTotal += saliency;
              saliencyX += saliency * ((x + .5) / width);
              saliencyY += saliency * ((y + .5) / height);
            }
          }
          let inferredSafeArea = "center";
          if (leftInformation < rightInformation * .82) inferredSafeArea = "left";
          else if (rightInformation < leftInformation * .82) inferredSafeArea = "right";
          let inferredFocusX = saliencyTotal ? saliencyX / saliencyTotal : .5;
          let inferredFocusY = saliencyTotal ? saliencyY / saliencyTotal : .5;
          if (inferredSafeArea === "left") inferredFocusX = Math.max(.62, inferredFocusX);
          if (inferredSafeArea === "right") inferredFocusX = Math.min(.38, inferredFocusX);
          inferredFocusX = clamp(inferredFocusX, .14, .86);
          inferredFocusY = clamp(inferredFocusY, .20, .80);
          const ratio = paletteImage.naturalWidth / paletteImage.naturalHeight;
          composition = {
            focusX: Math.round(inferredFocusX * 100),
            focusY: Math.round(inferredFocusY * 100),
            safeArea: inferredSafeArea,
            wide: Number.isFinite(ratio) && ratio >= 1.55,
          };
          applyPalette();
          applyComposition();
        }
      } catch {}
    };
    paletteImage.src = artSource;
  } else {
    root.style.removeProperty("--forge-skin-art-source");
  }
  const observer = new MutationObserver(queuePageUpdate);
  observer.observe(root, { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
  window.addEventListener("hashchange", queuePageUpdate);
  window.addEventListener("popstate", queuePageUpdate);
  updatePageState();
  window[key] = {
    token,
    remove() {
      observer.disconnect();
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener("hashchange", queuePageUpdate);
      window.removeEventListener("popstate", queuePageUpdate);
      document.getElementById(id)?.remove();
      root.removeAttribute("data-codex-forge-skin");
      root.removeAttribute("data-forge-skin-appearance");
      root.removeAttribute("data-forge-skin-page");
      root.removeAttribute("data-forge-skin-wide");
      root.removeAttribute("data-forge-skin-safe-area");
      root.style.removeProperty("--forge-skin-art-source");
      root.style.removeProperty("--forge-skin-safe-scrim");
      root.style.removeProperty("--forge-skin-task-shade");
      root.style.removeProperty("--forge-skin-position");
      root.style.removeProperty("--forge-skin-bg");
      root.style.removeProperty("--forge-skin-bg-rgb");
      root.style.removeProperty("--forge-skin-panel");
      root.style.removeProperty("--forge-skin-line");
      root.style.removeProperty("--forge-skin-accent");
      if (artObjectUrl) URL.revokeObjectURL(artObjectUrl);
      delete window[key];
    }
  };
})()`;
}

const removeExpression = `(() => {
  const key = ${JSON.stringify(stateKey)};
  if (window[key] && typeof window[key].remove === "function") window[key].remove();
  document.getElementById(${JSON.stringify(styleId)})?.remove();
  document.documentElement.removeAttribute("data-codex-forge-skin");
  document.documentElement.removeAttribute("data-forge-skin-appearance");
  document.documentElement.removeAttribute("data-forge-skin-page");
  document.documentElement.removeAttribute("data-forge-skin-wide");
  document.documentElement.removeAttribute("data-forge-skin-safe-area");
  document.documentElement.style.removeProperty("--forge-skin-art-source");
  document.documentElement.style.removeProperty("--forge-skin-safe-scrim");
  document.documentElement.style.removeProperty("--forge-skin-task-shade");
  document.documentElement.style.removeProperty("--forge-skin-position");
  document.documentElement.style.removeProperty("--forge-skin-bg");
  document.documentElement.style.removeProperty("--forge-skin-bg-rgb");
  document.documentElement.style.removeProperty("--forge-skin-panel");
  document.documentElement.style.removeProperty("--forge-skin-line");
  document.documentElement.style.removeProperty("--forge-skin-accent");
})()`;

function validWebSocketUrl(value: string, port: number): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "ws:"
      && (url.hostname === "127.0.0.1" || url.hostname === "localhost")
      && Number(url.port) === port
      && /^\/devtools\/page\/[A-Za-z0-9._-]+$/.test(url.pathname)
      && !url.username
      && !url.password
      && !url.search
      && !url.hash;
  } catch {
    return false;
  }
}

async function listTargets(port: number): Promise<CdpTarget[]> {
  const response = await fetch(`http://127.0.0.1:${port}/json/list`, { signal: AbortSignal.timeout(1200) });
  if (!response.ok) {
    throw new Error(`CDP target request failed: ${response.status}`);
  }
  const targets = await response.json() as CdpTarget[];
  return targets.filter((target) =>
    target.type === "page"
    && Boolean(target.webSocketDebuggerUrl)
    && validWebSocketUrl(target.webSocketDebuggerUrl as string, port)
  );
}

async function withCdp<T>(webSocketUrl: string, action: (send: (method: string, params?: object) => Promise<Record<string, unknown>>) => Promise<T>): Promise<T> {
  const socket = new WebSocket(webSocketUrl);
  const pending = new Map<number, { resolve: (value: Record<string, unknown>) => void; reject: (error: Error) => void }>();
  let nextId = 1;

  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("CDP WebSocket open timed out")), 3000);
    socket.addEventListener("open", () => {
      clearTimeout(timeout);
      resolve();
    }, { once: true });
    socket.addEventListener("error", () => {
      clearTimeout(timeout);
      reject(new Error("CDP WebSocket open failed"));
    }, { once: true });
  });

  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data)) as { id?: number; result?: Record<string, unknown>; error?: { message?: string } };
    if (!message.id) return;
    const request = pending.get(message.id);
    if (!request) return;
    pending.delete(message.id);
    if (message.error) {
      request.reject(new Error(message.error.message || "CDP request failed"));
    } else {
      request.resolve(message.result || {});
    }
  });

  const send = (method: string, params: object = {}) => new Promise<Record<string, unknown>>((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });

  try {
    return await action(send);
  } finally {
    socket.close();
  }
}

async function installTarget(webSocketUrl: string, expression: string): Promise<string | null> {
  return withCdp(webSocketUrl, async (send) => {
    const registered = await send("Page.addScriptToEvaluateOnNewDocument", { source: expression });
    await send("Runtime.evaluate", { expression, awaitPromise: true });
    return typeof registered.identifier === "string" ? registered.identifier : null;
  });
}

async function removeTarget(target: InstalledTarget): Promise<void> {
  await withCdp(target.webSocketUrl, async (send) => {
    if (target.scriptId) {
      try {
        await send("Page.removeScriptToEvaluateOnNewDocument", { identifier: target.scriptId });
      } catch {
        // The page may have reloaded and invalidated the registered script ID.
        // Current-page cleanup must still run.
      }
    }
    await send("Runtime.evaluate", { expression: removeExpression, awaitPromise: true });
  });
}

async function removeSessionSkin(session: ActiveSession): Promise<void> {
  await Promise.allSettled([...session.targets.values()].map(removeTarget));

  try {
    const targets = await listTargets(session.port);
    await Promise.allSettled(
      targets.map((target) => removeTarget({
        scriptId: null,
        webSocketUrl: target.webSocketDebuggerUrl as string,
      })),
    );
  } catch {
    // The Codex process may be closing; there is no live page left to clean.
  }
}

async function refreshSession(session: ActiveSession): Promise<void> {
  if (session.stopped || paused) return;
  let targets: CdpTarget[];
  try {
    targets = await listTargets(session.port);
  } catch {
    return;
  }
  const expression = buildInstallExpression(activeTheme);
  for (const target of targets) {
    if (session.targets.has(target.id) || !target.webSocketDebuggerUrl) continue;
    try {
      const scriptId = await installTarget(target.webSocketDebuggerUrl, expression);
      session.targets.set(target.id, { scriptId, webSocketUrl: target.webSocketDebuggerUrl });
    } catch {
      // Renderer targets can disappear during startup or navigation; the next poll retries them.
    }
  }
}

export function startCodexSkinSession(launch: SkinLaunchSession): void {
  void stopCodexSkinSession(launch.profileName);
  const session: ActiveSession = {
    port: launch.port,
    timer: setInterval(() => void refreshSession(session), pollIntervalMs),
    targets: new Map(),
    stopped: false,
  };
  sessions.set(launch.profileName, session);
  void refreshSession(session);
}

export async function stopCodexSkinSession(profileName: string): Promise<void> {
  const session = sessions.get(profileName);
  if (!session) return;
  session.stopped = true;
  clearInterval(session.timer);
  sessions.delete(profileName);
  await Promise.allSettled([...session.targets.values()].map(removeTarget));
}

export async function stopAllCodexSkinSessions(): Promise<void> {
  await Promise.allSettled([...sessions.keys()].map(stopCodexSkinSession));
}

export async function applyCodexSkinTheme(theme: CodexSkinThemePayload): Promise<void> {
  activeTheme = theme;
  paused = false;
  for (const session of sessions.values()) {
    await Promise.allSettled([...session.targets.values()].map(removeTarget));
    session.targets.clear();
    void refreshSession(session);
  }
}

export async function pauseCodexSkinSessions(nextPaused: boolean): Promise<void> {
  paused = nextPaused;
  if (paused) {
    for (const session of sessions.values()) {
      await removeSessionSkin(session);
      session.targets.clear();
    }
    return;
  }
  for (const session of sessions.values()) {
    void refreshSession(session);
  }
}
import type { CodexSkinThemePayload } from "./codexSkinStore";
