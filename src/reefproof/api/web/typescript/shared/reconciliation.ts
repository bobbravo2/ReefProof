import type { components } from "../workbench-contracts.js";

type ReconciliationProjection = components["schemas"]["ReconciliationProjection"];
type JsonRecord = Record<string, unknown>;
type Validator<T> = (value: unknown) => value is T;

export type ReconciliationServices = Readonly<{
  request: <T>(path: string, validator: Validator<T>, options?: RequestInit) => Promise<T>;
  toErrorMessage: (error: unknown, fallback: string) => string;
}>;

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isString = (value: unknown): value is string => typeof value === "string";
const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const isReconciliationItem = (value: unknown): boolean =>
  isRecord(value) &&
  isString(value.reconciliation_id) &&
  ["MATCHED", "AUTHORED_ONLY", "OBSERVED_ONLY", "CONFLICT"].includes(
    String(value.state),
  ) &&
  (value.canonical_subject_id === null || isString(value.canonical_subject_id)) &&
  (value.authored_display_id === null || isString(value.authored_display_id)) &&
  (value.observed_entity_id === null || isString(value.observed_entity_id)) &&
  (value.observed_vendor_id === null || isString(value.observed_vendor_id)) &&
  (value.observed_display_name === null || isString(value.observed_display_name)) &&
  isString(value.detail);
const isReconciliationProjection: Validator<ReconciliationProjection> = (
  value,
): value is ReconciliationProjection =>
  isRecord(value) &&
  isString(value.project_id) &&
  (value.observed_snapshot_hash === null || isString(value.observed_snapshot_hash)) &&
  (value.observed_captured_at === null || isString(value.observed_captured_at)) &&
  Array.isArray(value.items) &&
  value.items.every(isReconciliationItem) &&
  isFiniteNumber(value.matched_count) &&
  isFiniteNumber(value.authored_only_count) &&
  isFiniteNumber(value.observed_only_count) &&
  isFiniteNumber(value.conflict_count);

const renderReconciliation = (projection: ReconciliationProjection): void => {
  const status = document.querySelector<HTMLElement>("#reconciliation-status");
  const items = document.querySelector<HTMLElement>("#reconciliation-items");
  if (status === null || items === null) return;
  status.textContent =
    `${projection.matched_count} matched · ` +
    `${projection.authored_only_count} authored only · ` +
    `${projection.observed_only_count} observed only · ` +
    `${projection.conflict_count} conflicts`;
  status.className = `notice notice--${projection.conflict_count > 0 ? "error" : "ready"}`;
  items.replaceChildren();
  if (projection.items.length === 0) {
    const empty = document.createElement("p");
    empty.textContent =
      "No accepted authored devices or observed configuration evidence are available.";
    items.append(empty);
    return;
  }
  items.append(
    ...projection.items.map((item) => {
      const article = document.createElement("article");
      const heading = document.createElement("strong");
      heading.textContent =
        `${item.state} · ` +
        `${item.authored_display_id ?? item.observed_display_name ?? item.observed_entity_id ?? "unknown"}`;
      const identity = document.createElement("code");
      identity.textContent = [item.canonical_subject_id, item.observed_entity_id]
        .filter(Boolean)
        .join(" ↔ ");
      const detail = document.createElement("p");
      detail.textContent = item.detail;
      article.append(heading, identity, detail);
      return article;
    }),
  );
};

export const mountReconciliation = async (
  services: ReconciliationServices,
): Promise<void> => {
  const projection = await services.request("/reconciliation", isReconciliationProjection);
  renderReconciliation(projection);
  const form = document.querySelector<HTMLFormElement>("#reconciliation-binding-form");
  if (form === null) return;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void (async () => {
      const data = new FormData(form);
      const status = document.querySelector<HTMLElement>("#reconciliation-binding-status");
      try {
        const updated = await services.request(
          "/reconciliation/bindings",
          isReconciliationProjection,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              canonical_device_id: String(data.get("canonical_device_id") ?? ""),
              observed_entity_id: String(data.get("observed_entity_id") ?? ""),
              evidence_reference: String(data.get("evidence_reference") ?? ""),
              rationale: String(data.get("rationale") ?? ""),
              totp_code: String(data.get("totp_code") ?? ""),
            }),
          },
        );
        renderReconciliation(updated);
        if (status !== null) status.textContent = "Explicit observed identity binding recorded.";
      } catch (error: unknown) {
        if (status !== null) {
          status.textContent = services.toErrorMessage(
            error,
            "Observed identity binding failed.",
          );
        }
      }
    })();
  });
};
