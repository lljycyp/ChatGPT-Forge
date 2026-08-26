const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const apiBase = "https://api.github.com";
const uploadsBase = "https://uploads.github.com";
const owner = process.env.GITHUB_OWNER || "lljycyp";
const repo = process.env.GITHUB_REPO || "Codex-Forge";
const token = process.env.GITHUB_TOKEN;
const dryRun = process.env.GITHUB_DRY_RUN === "1";
const uploadTimeout = Number(process.env.GITHUB_UPLOAD_TIMEOUT_MS || 7_200_000);

const pkg = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));
const version = pkg.version;
const tagName = process.env.RELEASE_TAG || `v${version}`;
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

async function readResponse(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function api(pathname, { method = "GET", body } = {}) {
  const response = await fetch(`${apiBase}${pathname}`, {
    method,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await readResponse(response);
  if (!response.ok) {
    const detail = typeof data === "string" ? data : data?.message || JSON.stringify(data);
    throw new Error(`${method} ${pathname} failed: ${response.status} ${detail}`);
  }
  return data;
}

async function findRelease() {
  try {
    return await api(`/repos/${owner}/${repo}/releases/tags/${encodeURIComponent(tagName)}`);
  } catch (error) {
    if (error.message.includes("failed: 404 ")) {
      return null;
    }
    throw error;
  }
}

async function createRelease(notes) {
  return api(`/repos/${owner}/${repo}/releases`, {
    method: "POST",
    body: {
      tag_name: tagName,
      target_commitish: "main",
      name: `Codex Forge ${version}`,
      body: notes,
      draft: false,
      prerelease: false,
    },
  });
}

async function updateRelease(id, notes) {
  return api(`/repos/${owner}/${repo}/releases/${id}`, {
    method: "PATCH",
    body: {
      tag_name: tagName,
      name: `Codex Forge ${version}`,
      body: notes,
      draft: false,
      prerelease: false,
    },
  });
}

async function listAssets(releaseId) {
  return api(`/repos/${owner}/${repo}/releases/${releaseId}/assets?per_page=100`);
}

async function deleteAsset(assetId) {
  return api(`/repos/${owner}/${repo}/releases/assets/${assetId}`, { method: "DELETE" });
}

async function uploadAsset(releaseId, file) {
  const fileName = path.basename(file);
  const response = await fetch(
    `${uploadsBase}/repos/${owner}/${repo}/releases/${releaseId}/assets?name=${encodeURIComponent(fileName)}`,
    {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/octet-stream",
        "Content-Length": String(fs.statSync(file).size),
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: fs.createReadStream(file),
      duplex: "half",
      signal: AbortSignal.timeout(uploadTimeout),
    },
  );
  const data = await readResponse(response);
  if (!response.ok) {
    const detail = typeof data === "string" ? data : data?.message || JSON.stringify(data);
    throw new Error(`Upload ${fileName} failed: ${response.status} ${detail}`);
  }
}

async function main() {
  requiredFiles.forEach(requireFile);
  const files = requiredFiles.filter((file) => file !== releaseNotesPath);
  const notes = releaseNotes();

  if (dryRun) {
    console.log(`GitHub release dry run: ${owner}/${repo} ${tagName}`);
    files.forEach((file) => console.log(`asset: ${path.relative(root, file)} (${assetSize(file)})`));
    return;
  }

  if (!token) {
    throw new Error("GITHUB_TOKEN is required on the Windows build host");
  }

  console.log(`Finding GitHub release ${tagName}`);
  let release = await findRelease();
  console.log(release?.id ? `Updating GitHub release ${tagName}` : `Creating GitHub release ${tagName}`);
  release = release?.id ? await updateRelease(release.id, notes) : await createRelease(notes);

  const assets = await listAssets(release.id);
  for (const file of files) {
    const fileName = path.basename(file);
    const oldAsset = assets.find((asset) => asset.name === fileName);
    if (oldAsset?.id) {
      console.log(`Deleting old GitHub asset ${fileName}`);
      await deleteAsset(oldAsset.id);
    }
    console.log(`Uploading ${fileName} (${assetSize(file)}) to GitHub release ${tagName}`);
    await uploadAsset(release.id, file);
    console.log(`Uploaded ${fileName} to GitHub release ${tagName}`);
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
