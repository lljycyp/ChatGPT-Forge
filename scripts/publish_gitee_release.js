const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = path.join(__dirname, "..");
const apiBase = "https://gitee.com/api/v5";
const repoPath = (process.env.GITEE_REPO || "codex-forge")
  .replace(/^https?:\/\/gitee\.com\//, "")
  .replace(/\.git$/, "");
const repoParts = repoPath.split("/").filter(Boolean);
const owner = process.env.GITEE_OWNER || repoParts.at(-2) || "llj20010218";
const repo = repoParts.at(-1) || "codex-forge";
const token = process.env.GITEE_TOKEN;
const dryRun = process.env.GITEE_DRY_RUN === "1";
const uploadMaxTime = process.env.GITEE_UPLOAD_MAX_TIME || "7200";

const pkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
const version = pkg.version;
const tagName = process.env.RELEASE_TAG || process.env.GITHUB_REF_NAME || `v${version}`;
const releaseDir = path.join(root, "release");
const releaseNotesPath = path.join(releaseDir, "release-notes.md");
const requiredFiles = [
  path.join(releaseDir, `Codex-Forge-Setup-${version}.exe`),
  path.join(releaseDir, "latest.yml"),
  releaseNotesPath,
];

function requireFile(file) {
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    throw new Error(`Missing release asset: ${path.relative(root, file)}`);
  }
}

function assetSize(file) {
  return `${(fs.statSync(file).size / 1024 / 1024).toFixed(2)} MB`;
}

function releaseNotes() {
  const notes = fs.readFileSync(releaseNotesPath, "utf8").trim();
  if (!notes) {
    throw new Error(`release/release-notes.md missing notes for version ${version}`);
  }
  return notes;
}

async function api(pathname, { method = "GET", params = {}, body, headers = {} } = {}) {
  const url = new URL(`${apiBase}${pathname}`);
  if (!body) {
    url.searchParams.set("access_token", token);
  }
  for (const [key, value] of Object.entries(params)) {
    url.searchParams.set(key, value);
  }

  let response;
  try {
    response = await fetch(url, { method, body, headers });
  } catch (error) {
    const safeUrl = new URL(url);
    safeUrl.searchParams.delete("access_token");
    const cause = error.cause?.code || error.cause?.message || error.message;
    throw new Error(`${method} ${safeUrl.pathname}${safeUrl.search} failed: ${cause}`);
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(`${method} ${pathname} failed: ${response.status} ${text}`);
  }
  return data;
}

async function findRelease() {
  try {
    return await api(`/repos/${owner}/${repo}/releases/tags/${encodeURIComponent(tagName)}`);
  } catch (error) {
    if (error.message.includes("404")) {
      return null;
    }
    throw error;
  }
}

async function createRelease(notes) {
  const params = {
    access_token: token,
    tag_name: tagName,
    name: `Codex Forge ${version}`,
    body: notes,
    target_commitish: "main",
    prerelease: "false",
  };
  return api(`/repos/${owner}/${repo}/releases`, {
    method: "POST",
    body: new URLSearchParams(params),
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
}

async function updateRelease(id, notes) {
  const params = {
    access_token: token,
    tag_name: tagName,
    name: `Codex Forge ${version}`,
    body: notes,
    prerelease: "false",
  };
  return api(`/repos/${owner}/${repo}/releases/${id}`, {
    method: "PATCH",
    body: new URLSearchParams(params),
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });
}

async function listAssets(releaseId) {
  return api(`/repos/${owner}/${repo}/releases/${releaseId}/attach_files`);
}

async function deleteAsset(releaseId, assetId) {
  return api(`/repos/${owner}/${repo}/releases/${releaseId}/attach_files/${assetId}`, { method: "DELETE" });
}

async function uploadAsset(releaseId, file) {
  const pathname = `/repos/${owner}/${repo}/releases/${releaseId}/attach_files`;
  const curl = process.platform === "win32" ? "curl.exe" : "curl";
  const result = spawnSync(curl, [
    "--fail-with-body",
    "--show-error",
    "--location",
    "--retry",
    "2",
    "--retry-all-errors",
    "--connect-timeout",
    "60",
    "--max-time",
    uploadMaxTime,
    "-F",
    `access_token=${token}`,
    "-F",
    `file=@${file};filename=${path.basename(file)}`,
    `${apiBase}${pathname}`,
  ], { encoding: "utf8", maxBuffer: 10 * 1024 * 1024, stdio: ["ignore", "pipe", "inherit"] });

  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`POST ${pathname} failed: ${result.stderr || result.stdout || `curl exited ${result.status}`}`);
  }
}

async function main() {
  requiredFiles.forEach(requireFile);
  const files = requiredFiles.filter((file) => file !== releaseNotesPath);
  const notes = releaseNotes();

  if (dryRun) {
    console.log(`Gitee release dry run: ${owner}/${repo} ${tagName}`);
    files.forEach((file) => console.log(`asset: ${path.relative(root, file)}`));
    return;
  }

  if (!token) {
    throw new Error("GITEE_TOKEN is required");
  }

  console.log(`Finding Gitee release ${tagName}`);
  let release = await findRelease();
  console.log(release?.id ? `Updating Gitee release ${tagName}` : `Creating Gitee release ${tagName}`);
  release = release?.id ? await updateRelease(release.id, notes) : await createRelease(notes);

  console.log(`Listing Gitee release assets ${tagName}`);
  const assets = await listAssets(release.id).catch(() => []);
  for (const file of files) {
    const fileName = path.basename(file);
    const oldAsset = assets.find((asset) => [asset.name, asset.filename, asset.file_name].includes(fileName));
    if (oldAsset?.id) {
      console.log(`Deleting old Gitee asset ${fileName}`);
      await deleteAsset(release.id, oldAsset.id);
    }
    console.log(`Uploading ${fileName} (${assetSize(file)}) to Gitee release ${tagName}`);
    await uploadAsset(release.id, file);
    console.log(`Uploaded ${fileName} to Gitee release ${tagName}`);
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
