import { existsSync, readFileSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const androidRoot = path.join(projectRoot, "android");
const unsignedApk = path.join(
  androidRoot,
  "app/build/outputs/apk/sideload/release/app-sideload-release-unsigned.apk",
);
const signedApk = path.join(
  androidRoot,
  "app/build/outputs/apk/sideload/release/app-sideload-release-debugsigned.apk",
);
const applicationId = "com.wearableai.local";
const launchActivity = `${applicationId}/.MainActivity`;
const skipBuild = process.argv.includes("--install-only");

if (!skipBuild) {
  await run("npm", ["run", "release"], projectRoot);
}

if (!existsSync(unsignedApk)) {
  fail(`Missing unsigned APK at ${unsignedApk}. Run without --install-only first.`);
}

const sdkRoot = resolveAndroidSdk();
const apksigner = resolveApksigner(sdkRoot);
const keystore = path.join(homedir(), ".android", "debug.keystore");
if (!existsSync(keystore)) {
  fail(`Missing debug keystore at ${keystore}. Open Android Studio once to create it.`);
}

console.log("Signing sideload release with debug keystore…");
await run(apksigner, [
  "sign",
  "--ks",
  keystore,
  "--ks-pass",
  "pass:android",
  "--key-pass",
  "pass:android",
  "--ks-key-alias",
  "androiddebugkey",
  "--out",
  signedApk,
  unsignedApk,
]);

console.log("Installing on device…");
await run("adb", ["install", "-r", signedApk]);

console.log("Launching app…");
await run("adb", ["shell", "am", "start", "-n", launchActivity]);
console.log("Done.");

function resolveAndroidSdk() {
  for (const candidate of [
    process.env.ANDROID_HOME,
    process.env.ANDROID_SDK_ROOT,
    sdkFromLocalProperties(),
    process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, "Android", "Sdk")
      : null,
    path.join(homedir(), "AppData", "Local", "Android", "Sdk"),
    path.join(homedir(), "Android", "Sdk"),
  ]) {
    if (candidate && existsSync(candidate)) return candidate;
  }
  fail("Android SDK not found. Set ANDROID_HOME or create android/local.properties.");
}

function sdkFromLocalProperties() {
  const localProperties = path.join(androidRoot, "local.properties");
  if (!existsSync(localProperties)) return null;
  const match = readFileSync(localProperties, "utf8").match(/^\s*sdk\.dir\s*=\s*(.+)\s*$/m);
  if (!match) return null;
  return match[1]
    .trim()
    .replace(/\\\\/g, "\\")
    .replace(/^([A-Za-z]):\\\\/, "$1:\\");
}

function resolveApksigner(sdkRoot) {
  const buildTools = path.join(sdkRoot, "build-tools");
  if (!existsSync(buildTools)) fail(`No build-tools under ${sdkRoot}`);
  const versions = readdirSync(buildTools)
    .filter((name) =>
      existsSync(
        path.join(
          buildTools,
          name,
          process.platform === "win32" ? "apksigner.bat" : "apksigner",
        ),
      ),
    )
    .sort();
  const latest = versions.at(-1);
  if (!latest) fail(`apksigner not found under ${buildTools}`);
  return path.join(
    buildTools,
    latest,
    process.platform === "win32" ? "apksigner.bat" : "apksigner",
  );
}

function run(command, args, cwd = projectRoot) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      stdio: "inherit",
      shell: process.platform === "win32",
      env: process.env,
    });
    child.on("error", reject);
    child.on("exit", (code, signal) => {
      if (signal) reject(new Error(`${command} killed by ${signal}`));
      else if (code) reject(new Error(`${command} exited with ${code}`));
      else resolve();
    });
  });
}

function fail(message) {
  console.error(message);
  process.exit(1);
}
