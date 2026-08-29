import { mountReconciliation } from "../shared/reconciliation.js";

type Validator<T> = (value: unknown) => value is T;

export type SystemMapPageServices = Readonly<{
  request: <T>(path: string, validator: Validator<T>, options?: RequestInit) => Promise<T>;
  toErrorMessage: (error: unknown, fallback: string) => string;
}>;

export const mountSystemMapPage = async (
  services: SystemMapPageServices,
): Promise<void> => {
  await mountReconciliation(services);
  const status = document.querySelector<HTMLElement>("#system-map-status");
  if (status !== null) {
    status.textContent = "Canonical authored identities and explicit observed bindings loaded.";
    status.className = "notice notice--ready";
  }
};
