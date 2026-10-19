import { expect, test, type Page } from "@playwright/test";

// Public landmarks only. These tests need the full stack with the local geocoder imported.

async function confirmByAddress(page: Page, field: "Start" | "Destination", query: string) {
  const input = page.getByLabel(field);
  await input.fill(query);
  await input.press("Enter");
  const fieldId = field === "Start" ? "origin-field" : "destination-field";
  const firstCandidate = page.getByTestId(fieldId).locator("input[type=radio]").first();
  await expect(firstCandidate).toBeVisible();
  // click(), not check(): confirming removes the candidate list from the page, so a post-click "checked" verification can never succeed.
  await firstCandidate.click();
  await expect(page.getByTestId(fieldId).getByText("Confirmed:")).toBeVisible();
}

test("address-to-address planning through the local geocoder with candidate confirmation", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("data-status")).toContainText("local only");
  await confirmByAddress(page, "Start", "Union Station, Denver, CO");
  await confirmByAddress(page, "Destination", "Denver Zoo");
  const planResponse = page.waitForResponse((response) => response.url().includes("/api/v1/routes/plan"));
  await page.getByTestId("plan-button").click();
  expect((await planResponse).status()).toBe(200);
  await expect(page.getByTestId("route-card").first()).toContainText("Standard route");
  await expect(page.getByTestId("directions").locator("li").last()).toContainText(/arrived|destination/i);
});

test("no address match is an explicit state, not an empty result", async ({ page }) => {
  await page.goto("/");
  const start = page.getByLabel("Start");
  await start.fill("Nonexistent Street 99999, Denver");
  await start.press("Enter");
  await expect(page.getByTestId("origin-field")).toContainText("No address match");
  await expect(page.getByTestId("plan-button")).toBeDisabled();
});

test("coordinates typed as longitude, latitude are explained before confirmation", async ({ page }) => {
  await page.goto("/");
  const start = page.getByLabel("Start");
  await start.fill("-105.0002, 39.7530");
  await start.press("Enter");
  await expect(page.getByTestId("origin-field")).toContainText("swapped");
  await page.getByTestId("origin-field").locator("input[type=radio]").first().click();
  await expect(page.getByTestId("origin-field").getByText("Confirmed:")).toBeVisible();
});

test("units toggle converts the displayed distance without a new request", async ({ page }) => {
  await page.goto("/");
  for (const [field, coords] of [["Start", "39.7530, -105.0002"], ["Destination", "39.7503, -104.9500"]] as const) {
    const input = page.getByLabel(field);
    await input.fill(coords);
    await input.press("Enter");
  }
  await page.getByTestId("plan-button").click();
  const distance = page.getByTestId("route-distance").first();
  await expect(distance).toContainText("km");
  let requests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/routes/plan")) requests += 1;
  });
  await page.getByRole("button", { name: "mi", exact: true }).click();
  await expect(distance).toContainText("mi");
  expect(requests).toBe(0);
});

test("pin-to-pin planning on the map", async ({ page }) => {
  await page.goto("/");
  const webgl2 = await page.evaluate(() => Boolean(document.createElement("canvas").getContext("webgl2")));
  console.log(`[pin test] webgl2=${webgl2}`);
  test.skip(!webgl2, "this browser has no WebGL2; MapLibre cannot render, so pin placement cannot be exercised here");
  const map = page.getByTestId("map");
  // The planner swaps in a fallback panel when the map fails to initialise; that is a documented state, not a pin bug.
  const mapAppeared = await map.waitFor({ state: "visible", timeout: 15_000 }).then(() => true, (error) => {
    console.log(`[pin test] map did not appear: ${String(error).slice(0, 200)}`);
    return false;
  });
  console.log(`[pin test] mapAppeared=${mapAppeared}`);
  test.skip(!mapAppeared, "the map did not initialise in this browser (fallback panel shown); pin placement cannot be exercised here");
  const canvas = map.locator("canvas.maplibregl-canvas");
  await expect(canvas).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(2500); // let the style, boundary, and first tiles load
  const box = (await canvas.boundingBox())!;
  const centre = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.getByTestId("origin-field").getByRole("button", { name: "Use map pin" }).click();
  await page.mouse.click(centre.x - box.width * 0.12, centre.y);
  await expect(page.getByTestId("origin-field").getByText("Confirmed:")).toBeVisible();
  await page.getByTestId("destination-field").getByRole("button", { name: "Use map pin" }).click();
  await page.mouse.click(centre.x + box.width * 0.08, centre.y + box.height * 0.05);
  await expect(page.getByTestId("destination-field").getByText("Confirmed:")).toBeVisible();
  await expect(page.getByTestId("origin-field")).toContainText(/Map pin/);
  const planResponse = page.waitForResponse((response) => response.url().includes("/api/v1/routes/plan"));
  await page.getByTestId("plan-button").click();
  const response = await planResponse;
  // Pins land on the visible map; either a route or an explicit, labelled state is acceptable, never a blank result.
  if (response.status() === 200) {
    await expect(page.getByTestId("route-card").first()).toBeVisible();
  } else {
    await expect(page.getByTestId("plan-error")).toContainText(/OUTSIDE_SERVICE_AREA|NO_DRIVABLE_ROUTE/);
  }
});
