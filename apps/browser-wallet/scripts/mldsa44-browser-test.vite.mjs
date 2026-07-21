import { resolve } from "node:path";

import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  define: {
    __CHIPCOIN_DEFAULT_NODE_ENDPOINT__: JSON.stringify("http://127.0.0.1:28081"),
    __CHIPCOIN_DEFAULT_EXPLORER_URL__: JSON.stringify("https://explorer.chipcoinprotocol.com"),
  },
  build: {
    outDir: "dist-mldsa-browser-test",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        mldsa44_browser_harness: resolve("tests/browser/mldsa44_browser_harness.html"),
      },
    },
  },
});
