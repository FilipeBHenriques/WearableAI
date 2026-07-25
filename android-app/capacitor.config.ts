import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.wearableai.local",
  appName: "WearableAI",
  webDir: "dist",
  android: {
    allowMixedContent: false,
    backgroundColor: "#031008",
  },
};

export default config;
