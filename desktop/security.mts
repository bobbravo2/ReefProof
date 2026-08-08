export const SECURE_WEB_PREFERENCES = Object.freeze({
  nodeIntegration: false,
  contextIsolation: true,
  sandbox: true,
});

type NavigationEvent = { preventDefault(): void };
type WindowOpenDetails = { url: string };
type WebContentsLike = {
  on(event: "will-navigate" | "will-redirect", listener: (event: NavigationEvent, url: string) => void): void;
  setWindowOpenHandler(handler: (details: WindowOpenDetails) => { action: "deny" }): void;
};

export function isAllowedNavigation(candidate: string, applicationOrigin: string): boolean {
  try {
    return new URL(candidate).origin === applicationOrigin;
  } catch {
    return false;
  }
}

function isApprovedExternal(candidate: string, applicationOrigin: string): boolean {
  try {
    const url = new URL(candidate);
    return url.origin !== applicationOrigin && (url.protocol === "https:" || url.protocol === "http:");
  } catch {
    return false;
  }
}

export function applySecurityPolicy(
  contents: WebContentsLike,
  applicationOrigin: string,
  openExternal: (url: string) => Promise<void>,
): void {
  const denyUnexpectedNavigation = (event: NavigationEvent, url: string): void => {
    if (!isAllowedNavigation(url, applicationOrigin)) event.preventDefault();
  };
  contents.on("will-navigate", denyUnexpectedNavigation);
  contents.on("will-redirect", denyUnexpectedNavigation);
  contents.setWindowOpenHandler(({ url }) => {
    if (isApprovedExternal(url, applicationOrigin)) void openExternal(url);
    return { action: "deny" };
  });
}
