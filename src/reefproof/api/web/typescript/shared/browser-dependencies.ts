export type BrowserDependencies = Readonly<{
  request: typeof globalThis.fetch;
}>;

export const defaultBrowserDependencies = (): BrowserDependencies => ({
  request: (input, init) => globalThis.fetch(input, init),
});
