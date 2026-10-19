import { mkdirSync } from "node:fs";
import { expect, test } from "@playwright/test";

// Review aid, not a check: saves full-page screenshots of the planner before and after a plan so a person can look at the
// rendered result for each viewport (test-results/screens/). The planned trip uses public landmarks only.
const UNION_STATION = "39.7530, -105.0002";
const DENVER_ZOO = "39.7503, -104.9500";

test("capture review screenshots", async ({ page }, testInfo) => {
  const dir = "test-results/screens"; // test-results is cleared at the start of a run, so these survive until the next run
  mkdirSync(dir, { recursive: true });
  await page.goto("/");
  await expect(page.getByText("Routes compared")).toBeVisible();
  await page.screenshot({ path: `${dir}/${testInfo.project.name}-1-start.png`, fullPage: true });
  for (const [label, text] of [["Start", UNION_STATION], ["Destination", DENVER_ZOO]] as const) {
    const field = page.getByLabel(label);
    await field.fill(text);
    await field.press("Enter");
  }
  await expect(page.getByTestId("destination-field").getByText("Confirmed:")).toBeVisible();
  const planResponse = page.waitForResponse((response) => response.url().includes("/api/v1/routes/plan"));
  await page.getByTestId("plan-button").click();
  await planResponse;
  await expect(page.getByTestId("route-cards")).toBeVisible();
  await page.waitForTimeout(1500); // let the map settle
  await page.screenshot({ path: `${dir}/${testInfo.project.name}-2-planned.png`, fullPage: true });
  const cards = page.getByTestId("route-card");
  if ((await cards.count()) > 1) {
    await cards.nth(1).getByRole("button", { name: /Select/ }).click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${dir}/${testInfo.project.name}-3-alternative.png`, fullPage: true });
  }
  await page.getByTestId("encounter-list").first().locator("summary").click();
  await page.screenshot({ path: `${dir}/${testInfo.project.name}-4-evidence.png`, fullPage: true });
  await page.emulateMedia({ media: "print" });
  await page.screenshot({ path: `${dir}/${testInfo.project.name}-5-print.png`, fullPage: true });
});
