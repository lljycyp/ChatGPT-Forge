const { app, BrowserWindow } = require("electron");
const path = require("node:path");

const userDataPath = process.argv[2];
const seedTestValues = process.argv.includes("--test-seed");
if (!userDataPath) {
  throw new Error("Missing Electron user-data path");
}

app.setPath("userData", path.resolve(userDataPath));

app.whenReady().then(async () => {
  const window = new BrowserWindow({
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  try {
    await window.loadFile(path.join(__dirname, "..", "out", "renderer", "index.html"));
    const result = await window.webContents.executeJavaScript(`(() => {
      if (${JSON.stringify(seedTestValues)}) {
        localStorage.setItem("chatgptForgeLanguage", "en-US");
        localStorage.setItem("chatgptForgePrivacyMode", "true");
        localStorage.setItem("chatgptForgeWorkspaceTab", "mcp");
      }
      const mappings = [
        ["chatgptForgeLanguage", "codexForgeLanguage"],
        ["chatgptForgePrivacyMode", "codexForgePrivacyMode"],
        ["chatgptForgeWorkspaceTab", "codexForgeWorkspaceTab"],
      ];
      const migrated = [];
      for (const [oldKey, newKey] of mappings) {
        const value = localStorage.getItem(oldKey);
        if (value !== null) {
          localStorage.setItem(newKey, value);
          if (localStorage.getItem(newKey) !== value) throw new Error("Failed to verify " + newKey);
          localStorage.removeItem(oldKey);
          migrated.push(newKey);
        }
      }
      return migrated;
    })()`);
    process.stdout.write(`${JSON.stringify({ migratedKeys: result }, null, 2)}\n`);
    app.exit(0);
  } catch (error) {
    process.stderr.write(`${error.stack || error}\n`);
    app.exit(1);
  }
});
