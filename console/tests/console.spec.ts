import { expect, test } from "@playwright/test";

test("inspect a recorded run and compare the current ledger", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Ledger Parallax" }),
  ).toBeVisible();
  const scale = page.getByLabel("Recorded row count");
  await scale.focus();
  await page.keyboard.press("1"); // Native select type-ahead: 10,000 rows.
  await expect(scale).toHaveValue("0");
  await page.getByLabel("Query").selectOption("lookup");
  await expect(
    page.getByText("WHERE id = 42", { exact: false }).first(),
  ).toBeVisible();
  await page.getByRole("button", { name: "Compare live databases" }).click();
  await expect(
    page.getByText("Live results match", { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("table", { name: "Live PostgreSQL rows" })
      .getByText("42", { exact: true }),
  ).toBeVisible();
});

test("failed comparison preserves recorded evidence and allows retry", async ({
  page,
}) => {
  await page.route("**/api/compare/*", (r) =>
    r.fulfill({ status: 503, body: "{}" }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Compare live databases" }).click();
  await expect(page.getByRole("alert")).toContainText("Could not compare");
  await expect(
    page.getByRole("table", { name: "Recorded result rows" }),
  ).toBeVisible();
  await page.unroute("**/api/compare/*");
  await page.getByRole("button", { name: "Compare live databases" }).click();
  await expect(
    page.getByText("Live results match", { exact: true }),
  ).toBeVisible();
});

test("missing receipt gives a recovery action", async ({ page }) => {
  await page.route("**/api/report", (r) =>
    r.fulfill({ status: 503, body: "{}" }),
  );
  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText("Could not load");
  await page.unroute("**/api/report");
  await page.getByRole("button", { name: "Reload receipt" }).click();
  await expect(page.getByLabel("Recorded row count")).toBeVisible();
});
