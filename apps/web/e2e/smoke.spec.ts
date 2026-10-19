import { expect, test } from "@playwright/test";

// Public landmarks only: Union Station to Denver Zoo, typed as coordinates so the test does not
// depend on the geocoder. The request travels browser -> edge -> api -> valhalla.
const UNION_STATION = "39.7530, -105.0002";
const DENVER_ZOO = "39.7503, -104.9500";

test("plans a standard route through the containers and shows directions", async ({ page }) => {
  const planResponse = page.waitForResponse((response) => response.url().includes("/api/v1/routes/plan"));
  await page.goto("/");
  await expect(page).toHaveTitle(/DeFlockMigration/);
  await expect(page.getByRole("heading", { name: "DeFlockMigration" })).toBeVisible();

  const start = page.getByLabel("Start");
  await start.fill(UNION_STATION);
  await start.press("Enter");
  await expect(page.getByTestId("origin-field").getByText("Confirmed:")).toBeVisible();

  const destination = page.getByLabel("Destination");
  await destination.fill(DENVER_ZOO);
  await destination.press("Enter");
  await expect(page.getByTestId("destination-field").getByText("Confirmed:")).toBeVisible();

  const planButton = page.getByTestId("plan-button");
  await expect(planButton).toBeEnabled();
  await planButton.click();

  const response = await planResponse;
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.options.length).toBeGreaterThanOrEqual(1);
  expect(body.options[0].matched_camera_record_count).toBeNull();

  await expect(page.getByTestId("route-cards")).toBeVisible();
  await expect(page.getByTestId("route-card").first()).toContainText("Standard route");
  await expect(page.getByTestId("route-card").first()).toContainText("Not assessed in this version");
  const directions = page.getByTestId("directions");
  await expect(directions).toBeVisible();
  await expect(directions.locator("li").first()).toContainText(/Drive|Head|Start/);
  await expect(directions.locator("li").last()).toContainText(/arrived|destination/i);
});

test("rejects a trip that starts outside the pilot area with an explicit state", async ({ page }) => {
  await page.goto("/");
  const start = page.getByLabel("Start");
  await start.fill("39.7047, -104.9339"); // Glendale enclave
  await start.press("Enter");
  await expect(page.getByTestId("origin-field").getByText(/outside the Denver pilot area/)).toBeVisible();
  const destination = page.getByLabel("Destination");
  await destination.fill(DENVER_ZOO);
  await destination.press("Enter");
  await page.getByTestId("plan-button").click();
  await expect(page.getByTestId("plan-error")).toContainText("OUTSIDE_SERVICE_AREA");
});

test("the map initialises: worker loads, controls appear, and the overlay reports its state", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.goto("/");
  const webgl2 = await page.evaluate(() => Boolean(document.createElement("canvas").getContext("webgl2")));
  test.skip(!webgl2, "this browser has no WebGL2; MapLibre cannot render here");
  await expect(page.getByTestId("map").locator("canvas.maplibregl-canvas")).toBeVisible({ timeout: 20_000 });
  // The legend only renders after MapLibre's load event, so its presence proves the style and worker loaded.
  await expect(page.getByTestId("camera-legend")).toContainText(/Zoom in|mapped records in view/, { timeout: 30_000 });
  expect(errors.filter((text) => /worker/i.test(text))).toEqual([]);
});

test("data health panel reports the published snapshot and graph", async ({ page }) => {
  await page.goto("/");
  await page.getByText("Data health").click();
  await expect(page.getByTestId("data-health")).toContainText("Camera snapshot");
  await expect(page.getByTestId("data-health")).toContainText(/ovp-denver|none loaded yet/);
  await expect(page.getByTestId("data-health")).toContainText(/Routing graph/);
});
