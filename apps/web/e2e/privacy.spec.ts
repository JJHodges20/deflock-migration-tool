import { expect, test } from "@playwright/test";

// M8 privacy audit in the browser (roadmap section 13): during a complete session, every request stays on this origin,
// no trip detail appears in a URL except the camera viewport box (documented, never logged), nothing is written to
// browser storage, no cookie is set, no service worker is registered, and the page URL never carries coordinates.
const UNION_STATION = "39.7530, -105.0002";
const DENVER_ZOO = "39.7503, -104.9500";

test("a full session leaves no trip data in requests, storage, cookies, or the address bar", async ({ page, baseURL }) => {
  const origin = new URL(baseURL ?? "http://127.0.0.1:3000").origin;
  const requests: { url: string; method: string; body: string | null }[] = [];
  page.on("request", (request) => requests.push({ url: request.url(), method: request.method(), body: request.postData() }));

  await page.goto("/");
  await expect(page.getByText("Routes compared")).toBeVisible();
  // Address search through the local geocoder, then a plan, then the camera overlay at a zoomed-in view.
  const start = page.getByLabel("Start");
  await start.fill("Union Station, Denver, CO");
  await start.press("Enter");
  await page.getByTestId("origin-field").locator("input[type=radio]").first().click();
  await expect(page.getByTestId("origin-field").getByText("Confirmed:")).toBeVisible();
  const destination = page.getByLabel("Destination");
  await destination.fill(DENVER_ZOO);
  await destination.press("Enter");
  await expect(page.getByTestId("destination-field").getByText("Confirmed:")).toBeVisible();
  const planResponse = page.waitForResponse((response) => response.url().includes("/api/v1/routes/plan"));
  await page.getByTestId("plan-button").click();
  expect((await planResponse).status()).toBe(200);
  await expect(page.getByTestId("route-cards")).toBeVisible();
  await page.getByText("Data health").click();
  await expect(page.getByTestId("scheduler")).toBeVisible();
  await page.waitForTimeout(1500);

  // 1. Every request stays on this origin (no third-party tiles, fonts, analytics, or geocoders).
  const external = requests.filter((r) => !r.url.startsWith(origin) && !r.url.startsWith("data:") && !r.url.startsWith("blob:"));
  expect(external).toEqual([]);

  // 2. Trip details travel only in POST bodies; the only query string with geometry is the camera viewport box.
  for (const r of requests) {
    const url = new URL(r.url);
    if (url.search) {
      // The camera viewport box (documented, never logged) and a plain row limit for the diff history are the only query strings.
      const allowed = url.pathname === "/api/v1/cameras" || (url.pathname === "/api/v1/cameras/diffs" && /^\?limit=\d+$/.test(url.search)) || url.pathname.startsWith("/_next/");
      expect(allowed, `unexpected query string on ${url.pathname}${url.search}`).toBe(true);
    }
    if (url.pathname.startsWith("/api/v1/routes/plan") || url.pathname.startsWith("/api/v1/geocode")) {
      expect(r.method).toBe("POST");
    }
  }
  const planRequest = requests.find((r) => r.url.includes("/api/v1/routes/plan"));
  expect(planRequest?.body).toContain("39.753"); // the trip is in the body, by design, to the local API only

  // 3. Nothing persists in the browser and no cookie or service worker exists.
  const state = await page.evaluate(async () => ({
    localStorage: Object.keys(window.localStorage),
    sessionStorage: Object.keys(window.sessionStorage),
    cookies: document.cookie,
    serviceWorkers: "serviceWorker" in navigator ? (await navigator.serviceWorker.getRegistrations()).length : 0,
    indexedDb: "databases" in indexedDB ? (await indexedDB.databases()).length : 0,
    href: window.location.href,
  }));
  expect(state.localStorage).toEqual([]);
  expect(state.sessionStorage).toEqual([]);
  expect(state.cookies).toBe("");
  expect(state.serviceWorkers).toBe(0);
  expect(state.indexedDb).toBe(0);
  expect(state.href).not.toMatch(/39\.7|-104\.|-105\./);

  // 4. Clear trip removes the result and the inputs from the page.
  await page.getByTestId("clear-trip").click();
  await expect(page.getByTestId("route-cards")).toHaveCount(0);
  await expect(page.getByLabel("Start")).toHaveValue("");
});

test("response headers do not set cookies and the API is reached only through the edge", async ({ page }) => {
  const setCookie: string[] = [];
  page.on("response", (response) => {
    const header = response.headers()["set-cookie"];
    if (header) setCookie.push(`${response.url()}: ${header}`);
  });
  await page.goto("/");
  await expect(page.getByText("Routes compared")).toBeVisible();
  const health = await page.request.get("/api/v1/health/data");
  expect(health.ok()).toBe(true);
  expect(setCookie).toEqual([]);
});
