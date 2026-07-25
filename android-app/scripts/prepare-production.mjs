import { createHash } from "node:crypto";
import {
  createReadStream,
  createWriteStream,
  existsSync,
  promises as fs,
} from "node:fs";
import { get as httpsGet } from "node:https";
import path from "node:path";
import { Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";
import { createGunzip } from "node:zlib";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const lockPath = path.join(projectRoot, "packaging", "model-lock.json");
const vendorRoot = path.join(projectRoot, "android", "app", "src", "main", "cpp", "vendor");
const modelRoot = path.join(
  projectRoot,
  "android",
  "models-pack",
  "src",
  "main",
  "assets",
  "models",
);
const downloadRoot = path.join(projectRoot, "android", ".production-downloads");
const args = new Set(process.argv.slice(2));
const REQUIRED_NATIVE_SOURCES = new Set(["whisper.cpp", "llama.cpp"]);
const REQUIRED_MODEL_ARTIFACTS = new Set(["whisper", "llama", "minilm", "tokenizer"]);
const REQUIRED_MODEL_DIRECTORIES = new Set(["whisper", "llama", "minilm"]);
const DOWNLOAD_HOSTS = new Set([
  "codeload.github.com",
  "huggingface.co",
  "cdn-lfs.huggingface.co",
  "cas-bridge.xethub.hf.co",
]);

function isTrustedDownloadHost(hostname) {
  const host = hostname.toLowerCase();
  return DOWNLOAD_HOSTS.has(host) || /^[a-z0-9-]+\.aws\.cdn\.hf\.co$/.test(host);
}
const MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024;
const MAX_SOURCE_DOWNLOAD_BYTES = 512 * 1024 * 1024;
const verifyOnly = args.has("--verify");
const prepareSources = !args.has("--models-only");
const prepareModels = !args.has("--sources-only");

if ([...args].some((arg) => !["--verify", "--sources-only", "--models-only"].includes(arg))) {
  throw new Error("Usage: node scripts/prepare-production.mjs [--verify|--sources-only|--models-only]");
}
if (args.has("--sources-only") && args.has("--models-only")) {
  throw new Error("--sources-only and --models-only cannot be combined.");
}

const lock = JSON.parse(await fs.readFile(lockPath, "utf8"));
if (lock.schemaVersion !== 1) throw new Error("Unsupported production lock schema.");
validateLock(lock);
if (!verifyOnly) await fs.mkdir(downloadRoot, { recursive: true });

if (prepareSources) {
  for (const [name, source] of Object.entries(lock.nativeSources)) {
    await prepareNativeSource(name, source);
  }
}

if (prepareModels) {
  const manifestModels = {};
  for (const [name, model] of Object.entries(lock.models)) {
    const destination = safeJoin(modelRoot, model.file);
    const expected = { sha256: model.sha256, size: model.size, blob: model.blob };
    let actual = await inspectFile(destination);
    if (!actual || !matches(actual, expected)) {
      if (verifyOnly) throw new Error(`${name} is missing or does not match the production lock.`);
      await downloadVerified(model.url, destination, expected);
      actual = await inspectFile(destination);
    }
    if (!actual) throw new Error(`${name} was not prepared.`);
    if (model.size != null && actual.size !== model.size) {
      throw new Error(`${name} failed locked size verification.`);
    }
    if (!matches(actual, expected)) {
      throw new Error(`${name} failed checksum or size verification.`);
    }
    manifestModels[name] = {
      file: model.file,
      sha256: actual.sha256,
      size: actual.size,
      source: model.source,
      revision: model.revision,
      ...(model.blob ? { blob: model.blob } : {}),
    };
    console.log(`verified model ${name} (${actual.size} bytes)`);
  }

  await rejectUnexpectedModelFiles(new Set(Object.values(lock.models).map((model) => model.file)));
  if (!verifyOnly) {
    const manifest = `${JSON.stringify({ version: 2, models: manifestModels }, null, 2)}\n`;
    await atomicWrite(path.join(modelRoot, "model-manifest.json"), manifest);
  }
}

console.log(verifyOnly ? "production artifacts verified" : "production artifacts prepared");

async function rejectUnexpectedModelFiles(lockedFiles) {
  const allowed = new Set([
    ...lockedFiles,
    "model-manifest.json",
    "README.md",
    ".gitkeep",
  ]);
  for (const file of await listFiles(modelRoot)) {
    const relative = path.relative(modelRoot, file).split(path.sep).join("/");
    if (!allowed.has(relative)) {
      throw new Error(`Unexpected model asset '${relative}'; remove it before packaging.`);
    }
  }
}

async function listFiles(directory) {
  const files = [];
  let entries;
  try {
    entries = await fs.readdir(directory, { withFileTypes: true });
  } catch (error) {
    if (error.code === "ENOENT") return files;
    throw error;
  }
  for (const entry of entries) {
    const child = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await listFiles(child));
    else if (entry.isFile()) files.push(child);
    else throw new Error(`Unsupported filesystem entry in model assets: ${child}`);
  }
  return files;
}

async function prepareNativeSource(name, source) {
  const destination = safeJoin(vendorRoot, source.destination);
  const receiptPath = path.join(destination, ".wearableai-source.json");
  const receipt = await readJson(receiptPath);
  const receiptMatchesSource =
    receipt?.revision === source.revision &&
    receipt?.commit === source.commit &&
    receipt?.url === source.url &&
    (!source.archiveSha256 || receipt?.archiveSha256 === source.archiveSha256) &&
    existsSync(path.join(destination, "CMakeLists.txt"));
  if (receiptMatchesSource) {
    const tree = await hashTree(destination);
    if (receipt.treeSha256 === tree.sha256 && receipt.treeFileCount === tree.fileCount) {
      console.log(`verified native source ${name} (${source.revision})`);
      return;
    }
  }
  if (verifyOnly) throw new Error(`${name} ${source.revision} is not prepared.`);

  const archive = path.join(downloadRoot, `${source.destination}-${source.revision}.tar.gz`);
  let archiveInfo = await inspectFile(archive);
  if (!archiveInfo) {
    await downloadVerified(source.url, archive, null);
    archiveInfo = await inspectFile(archive);
  }
  if (!archiveInfo) throw new Error(`Could not download ${name}.`);
  if (source.archiveSha256 && archiveInfo.sha256 !== source.archiveSha256) {
    throw new Error(`${name} source archive checksum does not match the lock.`);
  }

  const repository = name.replace(/\.cpp$/, ".cpp");
  await extractTarGzAtomic(archive, destination, `${repository}-${source.commit}`);
  if (!existsSync(path.join(destination, "CMakeLists.txt"))) {
    throw new Error(`${name} archive did not contain CMakeLists.txt.`);
  }
  const tree = await hashTree(destination);
  await atomicWrite(
    receiptPath,
    `${JSON.stringify({
      name,
      revision: source.revision,
      commit: source.commit,
      url: source.url,
      archiveSha256: archiveInfo.sha256,
      archiveSize: archiveInfo.size,
      treeSha256: tree.sha256,
      treeFileCount: tree.fileCount,
    }, null, 2)}\n`,
  );
  console.log(`prepared native source ${name} (${source.revision})`);
}

async function hashTree(directory) {
  const files = (await listFiles(directory))
    .filter((file) => path.basename(file) !== ".wearableai-source.json")
    .map((file) => ({
      file,
      relative: path.relative(directory, file).split(path.sep).join("/"),
    }))
    .sort((left, right) =>
      left.relative < right.relative ? -1 : left.relative > right.relative ? 1 : 0);
  const hash = createHash("sha256");
  for (const { file, relative } of files) {
    hash.update(relative, "utf8");
    hash.update("\0");
    await new Promise((resolve, reject) => {
      const input = createReadStream(file);
      input.on("data", (chunk) => hash.update(chunk));
      input.on("error", reject);
      input.on("end", resolve);
    });
    hash.update("\0");
  }
  return { sha256: hash.digest("hex"), fileCount: files.length };
}

function safeJoin(root, relative) {
  if (
    typeof relative !== "string" ||
    !relative ||
    path.isAbsolute(relative) ||
    relative.includes("\\") ||
    relative.split("/").some((part) => part === ".." || part === "")
  ) {
    throw new Error(`Unsafe relative path: ${relative}`);
  }
  const resolved = path.resolve(root, ...relative.split("/"));
  const prefix = `${path.resolve(root)}${path.sep}`;
  if (!resolved.startsWith(prefix)) throw new Error(`Path escapes destination: ${relative}`);
  return resolved;
}

async function inspectFile(file) {
  try {
    const stat = await fs.stat(file);
    if (!stat.isFile()) return null;
    const hash = createHash("sha256");
    const blobHash = createHash("sha1");
    blobHash.update(`blob ${stat.size}\0`, "utf8");
    await new Promise((resolve, reject) => {
      const input = createReadStream(file);
      input.on("data", (chunk) => {
        hash.update(chunk);
        blobHash.update(chunk);
      });
      input.on("error", reject);
      input.on("end", resolve);
    });
    return { sha256: hash.digest("hex"), gitBlob: blobHash.digest("hex"), size: stat.size };
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

function matches(actual, expected) {
  return actual.size === expected.size &&
    (!expected.sha256 || actual.sha256 === expected.sha256.toLowerCase()) &&
    (!expected.blob || expected.blob === `git:${actual.gitBlob}`);
}

async function downloadVerified(url, destination, expected) {
  await fs.mkdir(path.dirname(destination), { recursive: true });
  const temporary = `${destination}.part-${process.pid}`;
  await fs.rm(temporary, { force: true });
  const hash = createHash("sha256");
  const blobHash = expected?.size != null ? createHash("sha1") : null;
  blobHash?.update(`blob ${expected.size}\0`, "utf8");
  let size = 0;
  try {
    await new Promise((resolve, reject) => {
      request(url, 0, async (response) => {
        const output = createWriteStream(temporary, { flags: "wx" });
        const meter = new Transform({
          transform(chunk, _encoding, callback) {
            hash.update(chunk);
            blobHash?.update(chunk);
            size += chunk.length;
            const maximum = expected?.size ?? MAX_SOURCE_DOWNLOAD_BYTES;
            if (size > maximum) {
              callback(new Error(`Download exceeds the size limit for ${path.basename(destination)}.`));
              return;
            }
            callback(null, chunk);
          },
        });
        try {
          await pipeline(response, meter, output);
          resolve();
        } catch (error) {
          reject(error);
        }
      }, reject);
    });
    const actual = {
      sha256: hash.digest("hex"),
      gitBlob: blobHash?.digest("hex"),
      size,
    };
    if (expected && !matches(actual, expected)) {
      throw new Error(
        `Downloaded ${path.basename(destination)} does not match: ` +
        `${actual.sha256}, ${actual.size} bytes.`,
      );
    }
    await replaceFile(temporary, destination);
  } catch (error) {
    await fs.rm(temporary, { force: true });
    throw error;
  }
}

function request(urlText, redirects, accept, reject) {
  if (redirects > 10) return reject(new Error(`Too many redirects for ${urlText}`));
  const url = new URL(urlText);
  if (url.protocol !== "https:") return reject(new Error(`Refusing non-HTTPS URL: ${urlText}`));
  if (url.username || url.password || !isTrustedDownloadHost(url.hostname)) {
    return reject(new Error(`Refusing untrusted download URL: ${urlText}`));
  }
  const requestHandle = httpsGet(
    url,
    { headers: { "User-Agent": "WearableAI-production-preparer/1" } },
    (response) => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode)) {
        const location = response.headers.location;
        response.resume();
        if (!location) return reject(new Error(`Redirect from ${urlText} has no location.`));
        return request(new URL(location, url).href, redirects + 1, accept, reject);
      }
      if (response.statusCode !== 200) {
        response.resume();
        return reject(new Error(`Download failed (${response.statusCode}) for ${urlText}`));
      }
      accept(response);
    },
  );
  requestHandle.setTimeout(120_000, () => requestHandle.destroy(new Error("Download timed out.")));
  requestHandle.on("error", reject);
}

async function atomicWrite(destination, contents) {
  await fs.mkdir(path.dirname(destination), { recursive: true });
  const temporary = `${destination}.part-${process.pid}`;
  await fs.rm(temporary, { force: true });
  await fs.writeFile(temporary, contents, { flag: "wx" });
  await replaceFile(temporary, destination);
}

async function replaceFile(temporary, destination) {
  try {
    await fs.rename(temporary, destination);
    return;
  } catch (error) {
    if (!["EEXIST", "EPERM", "ENOTEMPTY"].includes(error.code)) throw error;
  }
  const backup = `${destination}.replace-${process.pid}`;
  await fs.rm(backup, { force: true });
  await fs.rename(destination, backup);
  try {
    await fs.rename(temporary, destination);
    await fs.rm(backup, { force: true });
  } catch (error) {
    if (existsSync(backup)) await fs.rename(backup, destination);
    throw error;
  }
}

async function extractTarGzAtomic(archive, destination, expectedRoot) {
  const temporary = `${destination}.extract-${process.pid}`;
  const backup = `${destination}.backup-${process.pid}`;
  await fs.rm(temporary, { recursive: true, force: true });
  await fs.rm(backup, { recursive: true, force: true });
  await fs.mkdir(temporary, { recursive: true });
  try {
    const compressed = await fs.readFile(archive);
    const tar = await gunzip(compressed);
    await extractTar(tar, temporary, expectedRoot);
    if (existsSync(destination)) await fs.rename(destination, backup);
    try {
      await fs.rename(temporary, destination);
    } catch (error) {
      if (existsSync(backup)) await fs.rename(backup, destination);
      throw error;
    }
    await fs.rm(backup, { recursive: true, force: true });
  } catch (error) {
    await fs.rm(temporary, { recursive: true, force: true });
    throw error;
  }
}

function gunzip(buffer) {
  return new Promise((resolve, reject) => {
    const gunzipper = createGunzip();
    const chunks = [];
    let total = 0;
    gunzipper.on("data", (chunk) => {
      total += chunk.length;
      if (total > MAX_ARCHIVE_BYTES) {
        gunzipper.destroy(new Error("Expanded source archive exceeds the safety limit."));
        return;
      }
      chunks.push(chunk);
    });
    gunzipper.on("error", reject);
    gunzipper.on("end", () => resolve(Buffer.concat(chunks)));
    gunzipper.end(buffer);
  });
}

async function extractTar(tar, destination, expectedRoot) {
  let offset = 0;
  let rootComponent = null;
  let pendingLongName = null;
  let pendingPax = null;
  const links = [];
  const outputs = new Set();
  let terminated = false;
  while (offset + 512 <= tar.length) {
    const header = tar.subarray(offset, offset + 512);
    if (header.every((byte) => byte === 0)) {
      terminated = true;
      break;
    }
    verifyTarHeader(header);
    const size = parseTarNumber(header.subarray(124, 136));
    const type = String.fromCharCode(header[156] || 48);
    const prefix = tarText(header.subarray(345, 500));
    const headerName = tarText(header.subarray(0, 100));
    const name = pendingLongName ?? pendingPax?.path ??
      (prefix ? `${prefix}/${headerName}` : headerName);
    pendingLongName = null;
    const dataStart = offset + 512;
    const dataEnd = dataStart + size;
    if (dataEnd > tar.length) throw new Error("Truncated tar entry.");
    const data = tar.subarray(dataStart, dataEnd);
    offset = dataStart + Math.ceil(size / 512) * 512;

    if (type === "L") {
      pendingLongName = tarText(data);
      continue;
    }
    if (type === "x") {
      pendingPax = parsePax(data);
      continue;
    }
    if (type === "g") continue;
    const entryPax = pendingPax;
    pendingPax = null;

    const normalized = normalizeTarPath(name);
    const parts = normalized.split("/");
    rootComponent ??= parts[0];
    if (parts[0] !== rootComponent) throw new Error("Tar archive has multiple root directories.");
    if (rootComponent !== expectedRoot) {
      throw new Error(`Tar root '${rootComponent}' does not match pinned commit.`);
    }
    const relative = parts.slice(1).join("/");
    if (!relative) continue;
    const output = safeJoin(destination, relative);
    if (outputs.has(relative)) throw new Error(`Duplicate tar entry: ${relative}`);
    outputs.add(relative);

    if (type === "5") {
      await fs.mkdir(output, { recursive: true });
    } else if (type === "0" || type === "\0") {
      await fs.mkdir(path.dirname(output), { recursive: true });
      await fs.writeFile(output, data, { mode: parseTarNumber(header.subarray(100, 108)) & 0o777 });
    } else if (type === "2" || type === "1") {
      links.push({
        output,
        relative,
        target: entryPax?.linkpath ?? tarText(header.subarray(157, 257)),
        hard: type === "1",
      });
    } else {
      throw new Error(`Unsupported tar entry type '${type}' for ${name}`);
    }
  }
  if (!terminated || tar.subarray(offset).some((byte) => byte !== 0)) {
    throw new Error("Tar archive has missing or malformed end blocks.");
  }
  if (!rootComponent) throw new Error("Tar archive is empty.");

  for (const link of links) {
    let targetRelative;
    if (link.hard) {
      const targetParts = normalizeTarPath(link.target).split("/");
      if (targetParts[0] !== expectedRoot) {
        throw new Error(`Hard link target is outside the pinned tar root: ${link.target}`);
      }
      targetRelative = targetParts.slice(1).join("/");
    } else {
      if (
        link.target.startsWith("/") ||
        link.target.includes("\\") ||
        /^[A-Za-z]:/.test(link.target)
      ) {
        throw new Error(`Unsafe symbolic link target: ${link.target}`);
      }
      targetRelative = path.posix.normalize(
        path.posix.join(path.posix.dirname(link.relative), link.target),
      );
    }
    const target = safeJoin(destination, targetRelative);
    const stat = await fs.stat(target);
    await fs.mkdir(path.dirname(link.output), { recursive: true });
    if (stat.isDirectory()) {
      await fs.cp(target, link.output, { recursive: true });
    } else {
      await fs.copyFile(target, link.output);
    }
  }
}

function validateLock(value) {
  if (!value || typeof value !== "object") throw new Error("Production lock must be an object.");
  if (!sameSet(Object.keys(value.nativeSources ?? {}), REQUIRED_NATIVE_SOURCES)) {
    throw new Error("Production lock must pin exactly whisper.cpp and llama.cpp.");
  }
  if (!sameSet(Object.keys(value.models ?? {}), REQUIRED_MODEL_ARTIFACTS)) {
    throw new Error("Production lock must contain exactly three models and the MiniLM tokenizer.");
  }
  for (const [name, source] of Object.entries(value.nativeSources)) {
    if (
      !source ||
      source.destination !== name ||
      !/^[0-9a-f]{40}$/.test(source.commit ?? "") ||
      typeof source.revision !== "string" ||
      !/^[A-Za-z0-9._-]+$/.test(source.revision) ||
      (source.archiveSha256 != null &&
        !/^[0-9a-fA-F]{64}$/.test(source.archiveSha256))
    ) {
      throw new Error(`Invalid native source lock for ${name}.`);
    }
    assertTrustedUrl(source.url);
  }
  const directories = new Set();
  for (const [name, model] of Object.entries(value.models)) {
    safeJoin(modelRoot, model.file);
    directories.add(model.file.split("/")[0]);
    if (
      !Number.isSafeInteger(model.size) ||
      model.size <= 0 ||
      typeof model.source !== "string" ||
      !model.source ||
      !/^[0-9a-f]{40}$/.test(model.revision ?? "") ||
      (
        !(typeof model.sha256 === "string" && /^[0-9a-fA-F]{64}$/.test(model.sha256)) &&
        !(typeof model.blob === "string" && /^git:[0-9a-f]{40}$/.test(model.blob))
      )
    ) {
      throw new Error(`Model ${name} needs an exact size and SHA-256 or Git blob hash.`);
    }
    assertTrustedUrl(model.url);
  }
  if (!sameSet(directories, REQUIRED_MODEL_DIRECTORIES)) {
    throw new Error("Production artifacts must use exactly three model directories.");
  }
}

function assertTrustedUrl(value) {
  const url = new URL(value);
  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    !isTrustedDownloadHost(url.hostname)
  ) {
    throw new Error(`Untrusted production URL: ${value}`);
  }
}

function sameSet(left, right) {
  const values = [...left];
  return values.length === right.size && values.every((item) => right.has(item));
}

function parsePax(buffer) {
  const values = {};
  let offset = 0;
  while (offset < buffer.length) {
    const space = buffer.indexOf(32, offset);
    if (space < 0) throw new Error("Malformed PAX record.");
    const length = Number.parseInt(buffer.subarray(offset, space).toString("ascii"), 10);
    if (!Number.isSafeInteger(length) || length <= 0 || offset + length > buffer.length) {
      throw new Error("Invalid PAX record length.");
    }
    if (buffer[offset + length - 1] !== 10) throw new Error("PAX record is not newline terminated.");
    const record = buffer.subarray(space + 1, offset + length - 1).toString("utf8");
    const equals = record.indexOf("=");
    if (equals > 0) values[record.slice(0, equals)] = record.slice(equals + 1);
    offset += length;
  }
  return values;
}

function verifyTarHeader(header) {
  const expected = parseTarNumber(header.subarray(148, 156));
  let actual = 0;
  for (let index = 0; index < header.length; index += 1) {
    actual += index >= 148 && index < 156 ? 32 : header[index];
  }
  if (actual !== expected) throw new Error("Tar header checksum mismatch.");
}

function normalizeTarPath(value) {
  const cleaned = value.replace(/^\.\//, "").replace(/\/+$/, "");
  if (
    !cleaned ||
    cleaned.includes("\\") ||
    cleaned.startsWith("/") ||
    /^[A-Za-z]:/.test(cleaned) ||
    cleaned.split("/").some((part) => part === ".." || part === "")
  ) {
    throw new Error(`Unsafe tar path: ${value}`);
  }
  return cleaned;
}

function tarText(buffer) {
  const zero = buffer.indexOf(0);
  return buffer.subarray(0, zero < 0 ? buffer.length : zero).toString("utf8").trim();
}

function parseTarNumber(buffer) {
  const text = tarText(buffer).trim();
  if (!text) return 0;
  const value = Number.parseInt(text, 8);
  if (!Number.isSafeInteger(value) || value < 0) throw new Error(`Invalid tar number: ${text}`);
  return value;
}

async function readJson(file) {
  try {
    return JSON.parse(await fs.readFile(file, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT" || error instanceof SyntaxError) return null;
    throw error;
  }
}
