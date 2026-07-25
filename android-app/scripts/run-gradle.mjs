import { createWriteStream, existsSync, promises as fs } from "node:fs";
import { get as httpsGet } from "node:https";
import path from "node:path";
import { pipeline } from "node:stream/promises";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const androidRoot = path.join(projectRoot, "android");
const wrapperJar = path.join(androidRoot, "gradle", "wrapper", "gradle-wrapper.jar");
const localProperties = path.join(androidRoot, "local.properties");
const WRAPPER_JAR_URL =
  "https://raw.githubusercontent.com/gradle/gradle/v8.13.0/gradle/wrapper/gradle-wrapper.jar";

await ensureAndroidSdk();
await ensureWrapperJar();
const javaHome = resolveJavaHome();

const launcher = process.platform === "win32" ? "gradlew.bat" : "./gradlew";
const child = spawn(launcher, process.argv.slice(2), {
  cwd: androidRoot,
  stdio: "inherit",
  shell: process.platform === "win32",
  env: {
    ...process.env,
    ...(javaHome
      ? {
          JAVA_HOME: javaHome,
          PATH: `${path.join(javaHome, "bin")}${path.delimiter}${process.env.PATH ?? ""}`,
        }
      : {}),
  },
});

child.on("error", (error) => {
  console.error(`Could not start Gradle: ${error.message}`);
  process.exitCode = 1;
});
child.on("exit", (code, signal) => {
  process.exitCode = signal ? 1 : (code ?? 1);
});

function resolveJavaHome() {
  const candidates = [
    process.env.JAVA_HOME,
    "C:\\Program Files\\Android\\Android Studio\\jbr",
    "C:\\Program Files\\Eclipse Adoptium\\jdk-21.0.8+9",
    process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, "Programs", "Android", "Android Studio", "jbr")
      : null,
  ].filter(Boolean);
  for (const candidate of candidates) {
    const javaBin = path.join(
      candidate,
      "bin",
      process.platform === "win32" ? "java.exe" : "java",
    );
    if (existsSync(javaBin)) {
      if (candidate !== process.env.JAVA_HOME) {
        console.log(`Using JAVA_HOME=${candidate}`);
      }
      return candidate;
    }
  }
  return null;
}

async function ensureAndroidSdk() {
  if (existsSync(localProperties)) return;
  const candidates = [
    process.env.ANDROID_HOME,
    process.env.ANDROID_SDK_ROOT,
    process.env.LOCALAPPDATA
      ? path.join(process.env.LOCALAPPDATA, "Android", "Sdk")
      : null,
    process.env.HOME
      ? path.join(process.env.HOME, "AppData", "Local", "Android", "Sdk")
      : null,
    process.env.HOME ? path.join(process.env.HOME, "Android", "Sdk") : null,
    "/usr/lib/android-sdk",
  ].filter(Boolean);
  const sdkDir = candidates.find((candidate) => existsSync(candidate));
  if (!sdkDir) {
    throw new Error(
      "Android SDK not found. Set ANDROID_HOME or create android/local.properties with sdk.dir=...",
    );
  }
  const escaped = sdkDir.replace(/\\/g, "\\\\").replace(/:/g, "\\:");
  await fs.writeFile(localProperties, `sdk.dir=${escaped}\n`, "utf8");
  console.log(`Wrote local.properties -> ${sdkDir}`);
}

async function ensureWrapperJar() {
  if (existsSync(wrapperJar)) return;
  console.log("Downloading gradle-wrapper.jar…");
  await fs.mkdir(path.dirname(wrapperJar), { recursive: true });
  const temporary = `${wrapperJar}.part`;
  await fs.rm(temporary, { force: true });
  await download(WRAPPER_JAR_URL, temporary);
  await fs.rename(temporary, wrapperJar);
  console.log("gradle-wrapper.jar ready");
}

function download(urlText, destination, redirects = 0) {
  return new Promise((resolve, reject) => {
    if (redirects > 8) return reject(new Error(`Too many redirects for ${urlText}`));
    const url = new URL(urlText);
    if (url.protocol !== "https:") return reject(new Error(`Refusing non-HTTPS URL: ${urlText}`));
    const request = httpsGet(url, (response) => {
      if ([301, 302, 303, 307, 308].includes(response.statusCode ?? 0)) {
        const location = response.headers.location;
        response.resume();
        if (!location) return reject(new Error(`Redirect from ${urlText} has no location.`));
        return resolve(download(new URL(location, url).href, destination, redirects + 1));
      }
      if (response.statusCode !== 200) {
        response.resume();
        return reject(new Error(`Download failed (${response.statusCode}) for ${urlText}`));
      }
      pipeline(response, createWriteStream(destination)).then(resolve).catch(reject);
    });
    request.on("error", reject);
  });
}
