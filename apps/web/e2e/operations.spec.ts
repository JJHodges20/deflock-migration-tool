import { expect, test } from "@playwright/test";

// M7: operating state visible in the browser (scheduler, source policy, history, trip-free metrics) and results
// that are marked outdated when newer data appears, instead of changing underneath the user.
const UNION_STATION = "39.7530, -105.0002";
const DENVER_ZOO = "39.7503, -104.9500";

test("data health shows the scheduler, the source policy, snapshot history, and metrics without trip data", async ({ page }) => {
  await page.goto("/");
  await page.getByText("Data health").click();
  await expect(page.getByTestId("scheduler")).toContainText(/every [0-9]+ h while the stack runs/);
  await expect(page.getByTestId("scheduler")).toContainText(/on schedule|due now|overdue|as soon as the worker runs/);
  await expect(page.getByTestId("provider-policy")).toContainText("never derived from a trip");
  await expect(page.getByTestId("diff-history").locator("li").first()).toBeVisible();
  await expect(page.getByTestId("service-metrics")).toContainText(/plans?/);
  const metrics = await (await page.request.get("/api/v1/health/metrics")).json();
  const text = JSON.stringify(metrics);
  for (const forbidden of ["39.75", "-105.0", "origin", "destination", "shape"]) expect(text).not.toContain(forbidden);
  expect(metrics.storage.available).toBe(true);
  expect(metrics.process.rss_mb).toBeGreaterThan(0);
});

test("a planned result is marked outdated when a newer snapshot appears, and stays as computed", async ({ page }) => {
  await page.goto("/");
  for (const [label, text] of [["Start", UNION_STATION], ["Destination", DENVER_ZOO]] as const) {
    const field = page.getByLabel(label);
    await field.fill(text);
    await field.press("Enter");
  }
  await expect(page.getByTestId("destination-field").getByText("Confirmed:")).toBeVisible();
  const planResponse = page.waitForResponse((response) => response.url().includes("/api/v1/routes/plan"));
  await page.getByTestId("plan-button").click();
  const plan = await (await planResponse).json();
  await expect(page.getByTestId("route-cards")).toBeVisible();
  await expect(page.getByTestId("outdated-result")).toHaveCount(0);

  // Simulate a later sync: Data Health now names a different active snapshot.
  const health = await (await page.request.get("/api/v1/health/data")).json();
  const newer = { ...health, snapshot: { ...health.snapshot, snapshot_id: "ovp-denver-99991231T235959Z-ffffffff" } };
  await page.route("**/api/v1/health/data", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(newer) }));
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await expect(page.getByTestId("outdated-result")).toContainText("a newer camera snapshot (ovp-denver-99991231T235959Z-ffffffff) was published after this plan");
  // The displayed result keeps the versions it was computed with.
  await expect(page.getByTestId("route-card").first()).toContainText(plan.options[0].road_graph_version);
  await page.unroute("**/api/v1/health/data");
});
