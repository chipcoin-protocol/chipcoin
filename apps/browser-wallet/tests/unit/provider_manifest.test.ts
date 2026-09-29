import { describe, expect, it } from "vitest";

import chromeManifest from "../../manifest/chrome.json";
import firefoxManifest from "../../manifest/firefox.json";

describe("provider manifest injection", () => {
  for (const [name, manifest] of Object.entries({ chrome: chromeManifest, firefox: firefoxManifest })) {
    it(`${name} declares content script and page provider resources for chipcoinprotocol.com`, () => {
      expect(manifest.content_scripts).toEqual([
        expect.objectContaining({
          matches: ["https://chipcoinprotocol.com/*"],
          js: ["assets/content_script.js"],
          run_at: "document_start",
          all_frames: false,
        }),
      ]);
      expect(manifest.web_accessible_resources).toEqual([
        expect.objectContaining({
          resources: ["assets/page_provider.js"],
          matches: ["https://chipcoinprotocol.com/*"],
        }),
      ]);
    });

    it(`${name} declares Chipcoin extension and toolbar icons`, () => {
      expect(manifest.icons).toEqual({
        "16": "icons/chipcoin-16.png",
        "32": "icons/chipcoin-32.png",
        "48": "icons/chipcoin-48.png",
        "128": "icons/chipcoin-128.png",
      });
      expect(manifest.action.default_icon).toEqual({
        "16": "icons/chipcoin-16.png",
        "32": "icons/chipcoin-32.png",
      });
    });
  }
});
