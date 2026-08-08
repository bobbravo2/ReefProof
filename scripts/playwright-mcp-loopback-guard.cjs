"use strict";

const ALLOWED_ORIGIN = "http://127.0.0.1:8787";

function isAllowedRequest(requestUrl) {
  let url;
  try {
    url = new URL(requestUrl);
  } catch {
    return false;
  }
  return url.origin === ALLOWED_ORIGIN;
}

async function installLoopbackGuard({ page }) {
  await page.route("**/*", async (route) => {
    if (isAllowedRequest(route.request().url())) {
      await route.continue();
      return;
    }
    await route.abort("blockedbyclient");
  });
}

exports.ALLOWED_ORIGIN = ALLOWED_ORIGIN;
exports.isAllowedRequest = isAllowedRequest;
exports.default = installLoopbackGuard;
