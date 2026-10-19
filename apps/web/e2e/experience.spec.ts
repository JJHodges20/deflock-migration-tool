import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// M6: the complete trip-planning experience, exercised in a real browser against the Compose stack.
// Public landmarks only. Coordinates avoid a geocoder dependency where the test is about the planner itself.
const UNION_STATION = "39.7530, -105.0002";
const DENVER_ZOO = "39.7503, -104.9500";
const PLAN_BODY = { origin: { lat: 39.753, lon: -105.0002 }, destination: { lat: 39.7503, lon: -104.95 }, profiles: ["standard", "balanced", "fewest_mapped"], camera_scope: "all_alpr", units: "km" };

async function confirmCoordinates(page: Page, label: "Start" | "Destination", text: string) {
  const field = page.getByLabel(label);
  await field.fill(text);
  await field.press("Enter");
  await expect(page.getByTestId(label === "Start" ? "origin-field" : "destination-field").getByText("Confirmed:")).toBeVisible();
}

async function planByCoordinates(page: Page) {
  const planResponse = page.waitForResponse((response) => response.url().includes("/api/v1/routes/plan"));
  await page.goto("/");
  await confirmCoordinates(page, "Start", UNION_STATION);
  await confirmCoordinates(page, "Destination", DENVER_ZOO);
  await page.getByTestId("plan-button").click();
  const response = await planResponse;
  expect(response.status()).toBe(200);
  await expect(page.getByTestId("route-cards")).toBeVisible();
  return response.json();
}

test("full flow: addresses through the local geocoder, compare, select another option; map, card and directions stay in sync", async ({ page }) => {
  await page.goto("/");
  const start = page.getByLabel("Start");
  await start.fill("Union Station, Denver, CO");
  await start.press("Enter");
  await page.getByTestId("origin-field").getByRole("radio").first().click(); // click, not check: the list disappears on confirmation
  await expect(page.getByTestId("origin-field").getByText("Confirmed:")).toBeVisible();
  const destination = page.getByLabel("Destination");
  await destination.fill("Denver Zoo");
  await destination.press("Enter");
  await page.getByTestId("destination-field").getByRole("radio").first().click();
  await expect(page.getByTestId("destination-field").getByText("Confirmed:")).toBeVisible();

  const planResponse = page.waitForResponse((response) => response.url().includes("/api/v1/routes/plan"));
  await page.getByTestId("plan-button").click();
  const body = await (await planResponse).json();
  await expect(page.getByTestId("route-cards")).toBeVisible();
  const cards = page.getByTestId("route-card");
  expect(await cards.count()).toBe(body.options.length);
  // The results heading receives focus so keyboard and screen-reader users land on them.
  await expect(page.locator("#route-options-heading")).toBeFocused();

  if (body.options.length > 1) {
    const second = cards.nth(1);
    await second.getByRole("button", { name: /Select/ }).click();
    await expect(second).toHaveAttribute("aria-current", "true");
    await expect(second.getByTestId("result-state")).toHaveAttribute("data-state", "better");
    const label = body.options[1].profiles.map((p: string) => ({ standard: "Standard route", balanced: "Balanced", fewest_mapped: "Fewest mapped cameras found" })[p]).join(", ");
    await expect(page.getByTestId("directions-summary")).toContainText(label);
    await expect(page.getByTestId("directions-summary")).toContainText(`${body.options[1].maneuvers.length} steps`);
    await expect(page.getByTestId("sheet-summary")).toContainText(label);
    // Print and download are offered for the selected card only.
    expect(await page.getByTestId("download-route").count()).toBe(1);
    await expect(second.getByTestId("download-route")).toBeVisible();
  }
});

test("keyboard-only operation: plan, land on the results, pick another card, walk the directions", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Start").focus();
  await page.keyboard.type(UNION_STATION);
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("origin-field").getByText("Confirmed:")).toBeVisible();
  await page.getByLabel("Destination").focus();
  await page.keyboard.type(DENVER_ZOO);
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("destination-field").getByText("Confirmed:")).toBeVisible();
  await page.getByTestId("plan-button").focus();
  const planResponse = page.waitForResponse((response) => response.url().includes("/api/v1/routes/plan"));
  await page.keyboard.press("Enter");
  const body = await (await planResponse).json();
  await expect(page.locator("#route-options-heading")).toBeFocused();
  if (body.options.length > 1) {
    // Tab from the heading through the summary to the second card's select button and activate it with the keyboard.
    const secondButton = page.getByTestId("route-card").nth(1).getByRole("button", { name: /Select/ });
    for (let i = 0; i < 25; i += 1) {
      if (await secondButton.evaluate((el) => el === document.activeElement)) break;
      await page.keyboard.press("Tab");
    }
    await expect(secondButton).toBeFocused();
    await page.keyboard.press("Space");
    await expect(page.getByTestId("route-card").nth(1)).toHaveAttribute("aria-current", "true");
  }
  const firstStep = page.getByTestId("directions").locator("li").first();
  await firstStep.focus();
  await expect(firstStep).toHaveAttribute("aria-current", "step");
  await expect(firstStep).toHaveClass(/highlighted/);
});

test("narrow screen: the bottom sheet collapses to a summary and state survives layout changes", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await planByCoordinates(page);
  await page.getByRole("button", { name: "Hide planner" }).click();
  await expect(page.getByTestId("sheet-summary")).toBeVisible();
  await expect(page.getByTestId("sheet-summary")).toContainText(/Standard route|Balanced/);
  await page.getByRole("button", { name: "Show planner" }).click();
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByTestId("route-cards")).toBeVisible();
  await expect(page.getByTestId("origin-field").getByText("Confirmed:")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByTestId("route-cards")).toBeVisible();
  await expect(page.getByTestId("directions")).toBeVisible();
});

test("cancelling a request is an explicit state and its late answer is discarded", async ({ page }) => {
  await page.route("**/api/v1/routes/plan", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    await route.continue();
  });
  await page.goto("/");
  await confirmCoordinates(page, "Start", UNION_STATION);
  await confirmCoordinates(page, "Destination", DENVER_ZOO);
  await page.getByTestId("plan-button").click();
  await page.getByTestId("cancel-button").click();
  await expect(page.getByTestId("plan-cancelled")).toBeVisible();
  await page.waitForTimeout(3500);
  await expect(page.getByTestId("route-cards")).toHaveCount(0);
  await expect(page.getByTestId("plan-cancelled")).toBeVisible();
  await page.unroute("**/api/v1/routes/plan");
  await page.getByTestId("plan-button").click();
  await expect(page.getByTestId("route-cards")).toBeVisible();
});

test("print view keeps the selected route and its directions and drops the map and controls", async ({ page }) => {
  await planByCoordinates(page);
  await page.emulateMedia({ media: "print" });
  await expect(page.getByTestId("print-header")).toBeVisible();
  await expect(page.getByTestId("print-header")).toContainText("Start:");
  await expect(page.getByTestId("map")).toBeHidden();
  await expect(page.getByTestId("plan-button")).toBeHidden();
  const cards = page.getByTestId("route-card");
  const count = await cards.count();
  await expect(cards.first()).toBeVisible();
  for (let i = 1; i < count; i += 1) await expect(cards.nth(i)).toBeHidden();
  await expect(page.getByTestId("directions")).toBeVisible();
  await page.emulateMedia({ media: null });
  await expect(page.getByTestId("print-header")).toBeHidden();
});

test("GeoJSON download preserves the selected geometry and carries the recalculation warning", async ({ page }) => {
  const body = await planByCoordinates(page);
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("download-route").click()]);
  expect(download.suggestedFilename()).toMatch(/^deflockmigration-standard.*\.geojson$/);
  const doc = JSON.parse(readFileSync((await download.path()) as string, "utf-8"));
  expect(doc.type).toBe("FeatureCollection");
  expect(doc.features[0].geometry.coordinates).toEqual(body.options[0].geometry.coordinates);
  expect(doc.features[0].properties.camera_snapshot_id).toBe(body.options[0].camera_snapshot_id);
  expect(doc.features[0].properties.warning).toMatch(/may recalculate a different path/);
});

test("typing an address sends nothing until Search, and every request stays on this origin", async ({ page, baseURL }) => {
  const requests: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  await page.goto("/");
  await page.getByLabel("Start").fill("Union Sta");
  await page.getByLabel("Start").type("tion, Denver", { delay: 20 });
  await page.waitForTimeout(500);
  expect(requests.filter((url) => url.includes("/api/v1/geocode"))).toEqual([]);
  await page.getByLabel("Start").press("Enter");
  await expect(page.getByTestId("origin-field").getByRole("radio").first()).toBeVisible();
  expect(requests.filter((url) => url.includes("/api/v1/geocode"))).toHaveLength(1);
  const origin = new URL(baseURL ?? "http://127.0.0.1:3000").origin;
  const external = requests.filter((url) => !url.startsWith(origin) && !url.startsWith("data:") && !url.startsWith("blob:"));
  expect(external).toEqual([]);
});

test("the four result states are unmistakable: no route at all, unknown data, no better route, no mapped encounters", async ({ page }) => {
  const real = await (await page.request.post("/api/v1/routes/plan", { data: PLAN_BODY })).json();
  const standard = real.options[0];

  const show = async (body: unknown, status = 200) => {
    await page.route("**/api/v1/routes/plan", (route) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }));
    await page.getByTestId("plan-button").click();
  };
  await page.goto("/");
  await confirmCoordinates(page, "Start", UNION_STATION);
  await confirmCoordinates(page, "Destination", DENVER_ZOO);

  await show({ error: { code: "NO_DRIVABLE_ROUTE", message: "No drivable route was found between these points.", details: {} }, request_id: "r" }, 422);
  await expect(page.getByTestId("state-no-route")).toContainText("No route at all");
  await expect(page.getByTestId("route-cards")).toHaveCount(0);

  const unknown = { ...real, search_status: "not_run", assessment_coverage_status: "not_assessed", options: [{ ...standard, assessment: null, matched_camera_record_count: null, uncertain_nearby_camera_count: null, exposure_count: null, assessment_coverage_status: "not_assessed", camera_snapshot_id: null }], search: { ...real.search, status: "not_run", profile_outcomes: [{ profile: "balanced", outcome: "not_assessed", message: "Camera assessment is unavailable, so this preference could not be evaluated.", max_extra_seconds: 600, max_relative_factor: 1.5, bound_seconds: 900, best_exposure_count: null, route_id: null }] } };
  await show(unknown);
  await expect(page.getByTestId("result-state")).toHaveAttribute("data-state", "unknown");
  await expect(page.getByTestId("result-state")).toContainText("Unknown data");
  await expect(page.getByTestId("profile-outcome")).toContainText("could not be evaluated");

  const noBetter = { ...real, options: [{ ...standard, profiles: ["standard", "balanced", "fewest_mapped"], exposure_count: 4, matched_camera_record_count: 0, uncertain_nearby_camera_count: 4, assessment: { ...standard.assessment, status: "complete", matched_record_count: 0, uncertain_record_count: 4 }, assessment_coverage_status: "complete" }], search: { ...real.search, status: "completed", profile_outcomes: [{ profile: "balanced", outcome: "same_as_standard", message: "No lower-exposure route found within your detour limit; 5 candidate(s) were assessed. Increase the limit to search further.", max_extra_seconds: 600, max_relative_factor: 1.5, bound_seconds: 900, best_exposure_count: 4, route_id: standard.route_id }] } };
  await show(noBetter);
  await expect(page.getByTestId("result-state")).toHaveAttribute("data-state", "no-better");
  await expect(page.getByTestId("result-state")).toContainText("No better route within your limit");
  await expect(page.getByTestId("raise-limit")).toBeVisible();

  const none = { ...real, options: [{ ...standard, profiles: ["standard", "balanced", "fewest_mapped"], exposure_count: 0, matched_camera_record_count: 0, uncertain_nearby_camera_count: 0, assessment: { ...standard.assessment, status: "complete", matched_record_count: 0, uncertain_record_count: 0, encounters: [] }, assessment_coverage_status: "complete" }], search: { ...real.search, status: "completed", profile_outcomes: [] } };
  await show(none);
  await expect(page.getByTestId("result-state")).toHaveAttribute("data-state", "none");
  await expect(page.getByTestId("result-state")).toContainText("Unmapped or mislocated cameras may still be present.");
});

test("one-shot device location fills the start only after the button is pressed", async ({ page, context }) => {
  await context.grantPermissions(["geolocation"]);
  await context.setGeolocation({ latitude: 39.753, longitude: -105.0002 });
  await page.goto("/");
  await expect(page.getByTestId("origin-field").getByText("Confirmed:")).toHaveCount(0);
  await page.getByTestId("origin-use-location").click();
  await expect(page.getByTestId("origin-field").getByText(/My location/)).toBeVisible();
});

test("accessibility scan: no serious or critical violations before and after planning", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Routes compared")).toBeVisible();
  const before = await new AxeBuilder({ page }).analyze();
  const seriousBefore = before.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(seriousBefore.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
  await planByCoordinates(page);
  const after = await new AxeBuilder({ page }).analyze();
  const seriousAfter = after.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(seriousAfter.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
});

test("data-age badges and the stale flag are visible without opening a terminal", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("camera-age")).toContainText(/old/);
  await expect(page.getByTestId("road-age")).toContainText(/old/);
  await planByCoordinates(page);
  await expect(page.getByTestId("card-camera-age").first()).toContainText(/old/);
});
