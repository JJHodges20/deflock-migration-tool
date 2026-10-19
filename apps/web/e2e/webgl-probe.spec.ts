import { test } from "@playwright/test";

// Diagnostic only: reports WebGL 1/2 availability, map initialisation state, and console errors
// (MapLibre 6 needs WebGL2; pin tests depend on a rendered map).
test("webgl availability probe", async ({ page }, testInfo) => {
  const messages: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" || message.type() === "warning") messages.push(`${message.type()}: ${message.text().slice(0, 300)}`);
  });
  page.on("pageerror", (error) => messages.push(`pageerror: ${String(error).slice(0, 300)}`));
  page.on("response", (response) => {
    if (response.status() >= 400) messages.push(`http ${response.status()}: ${response.url().slice(0, 300)}`);
  });
  page.on("requestfailed", (request) => messages.push(`requestfailed: ${request.url().slice(0, 300)} ${request.failure()?.errorText ?? ""}`));
  await page.goto("/");
  await page.waitForTimeout(6000);
  const info = await page.evaluate(() => {
    const describe = (kind: "webgl" | "webgl2") => {
      const canvas = document.createElement("canvas");
      const gl = canvas.getContext(kind) as WebGLRenderingContext | null;
      if (!gl) return null;
      const ext = gl.getExtension("WEBGL_debug_renderer_info");
      return ext ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : "unknown renderer";
    };
    return {
      webgl1: describe("webgl"),
      webgl2: describe("webgl2"),
      mapContainer: Boolean(document.querySelector('[data-testid="map"]')),
      canvas: Boolean(document.querySelector(".maplibregl-canvas")),
      controls: document.querySelectorAll(".maplibregl-ctrl").length,
      fallback: Boolean(document.querySelector(".map-fallback")),
      legend: Boolean(document.querySelector('[data-testid="camera-legend"]')),
      boxes: ['[data-testid="map"]', ".maplibregl-canvas-container", ".maplibregl-canvas"].map((selector) => {
        const element = document.querySelector(selector);
        if (!element) return `${selector}: missing`;
        const rect = element.getBoundingClientRect();
        return `${selector}: ${Math.round(rect.width)}x${Math.round(rect.height)} position=${getComputedStyle(element).position}`;
      }),
    };
  });
  console.log(`[${testInfo.project.name}] ${JSON.stringify(info)}`);
  for (const message of messages.slice(0, 12)) console.log(`[${testInfo.project.name}] console ${message}`);
});
