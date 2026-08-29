import type { components } from "../workbench-contracts.js";

type AuthoredSourceConfiguration = components["schemas"]["AuthoredSourceConfiguration"];
type AuthoredSourceStatus = components["schemas"]["AuthoredSourceStatus"];
type AuthoredImportSummary = components["schemas"]["AuthoredImportSummary"];
type AuthoredImportReview = components["schemas"]["AuthoredImportReview"];
type AuthoredImportReviewResponse = components["schemas"]["AuthoredImportReviewResponse"];
type JsonRecord = Record<string, unknown>;
type Validator<T> = (value: unknown) => value is T;

export type SourcePageServices = Readonly<{
  request: <T>(path: string, validator: Validator<T>, options?: RequestInit) => Promise<T>;
  requiredElement: <T extends Element>(selector: string) => T;
  toErrorMessage: (error: unknown, fallback: string) => string;
}>;

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isString = (value: unknown): value is string => typeof value === "string";
const isBoolean = (value: unknown): value is boolean => typeof value === "boolean";
const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const isStringNumberRecord = (value: unknown): value is Record<string, number> =>
  isRecord(value) && Object.values(value).every(isFiniteNumber);
const isAuthoredSourceConfiguration = (
  value: unknown,
): value is AuthoredSourceConfiguration =>
  isRecord(value) &&
  isString(value.source_configuration_id) &&
  isString(value.project_id) &&
  isString(value.source_alias) &&
  isString(value.spreadsheet_id) &&
  isString(value.configured_at) &&
  isFiniteNumber(value.freshness_seconds);
const isAuthoredSourceConfigurations: Validator<AuthoredSourceConfiguration[]> = (
  value,
): value is AuthoredSourceConfiguration[] =>
  Array.isArray(value) && value.every(isAuthoredSourceConfiguration);
const isAuthoredSourceStatus: Validator<AuthoredSourceStatus> = (
  value,
): value is AuthoredSourceStatus =>
  isRecord(value) &&
  ["NOT_CONFIGURED", "CURRENT", "STALE", "UNAVAILABLE", "CHANGED"].includes(
    String(value.health),
  ) &&
  isString(value.detail) &&
  (value.last_successful_fetch_at === undefined ||
    value.last_successful_fetch_at === null ||
    isString(value.last_successful_fetch_at)) &&
  (value.latest_snapshot_hash === undefined ||
    value.latest_snapshot_hash === null ||
    isString(value.latest_snapshot_hash));
const isAuthoredImportSummary = (value: unknown): value is AuthoredImportSummary =>
  isRecord(value) &&
  isString(value.import_batch_id) &&
  isString(value.fetched_at) &&
  isString(value.source_snapshot_hash) &&
  isString(value.normalized_content_hash) &&
  isBoolean(value.valid) &&
  isStringNumberRecord(value.record_counts) &&
  isFiniteNumber(value.diagnostic_count) &&
  ["INVALID", "PENDING_REVIEW", "ACCEPTED", "REJECTED"].includes(
    String(value.review_status),
  );
const isAuthoredImportSummaries: Validator<AuthoredImportSummary[]> = (
  value,
): value is AuthoredImportSummary[] =>
  Array.isArray(value) && value.every(isAuthoredImportSummary);
const isImportFactChange = (value: unknown): boolean =>
  isRecord(value) &&
  isString(value.attribute) &&
  (value.proposed_value === null || isString(value.proposed_value)) &&
  ["NEW", "CHANGED", "UNCHANGED", "CONFLICT", "INVALID", "REMOVED_FROM_SOURCE"].includes(
    String(value.state),
  );
const isImportObjectReview = (value: unknown): boolean =>
  isRecord(value) &&
  isString(value.canonical_subject_id) &&
  isString(value.external_namespace) &&
  isString(value.external_id) &&
  isString(value.tab) &&
  (value.source_range === null || isString(value.source_range)) &&
  Array.isArray(value.changes) &&
  value.changes.every(isImportFactChange);
const isAuthoredImportReview: Validator<AuthoredImportReview> = (
  value,
): value is AuthoredImportReview =>
  isRecord(value) &&
  isString(value.import_batch_id) &&
  isString(value.source_snapshot_hash) &&
  isBoolean(value.valid) &&
  isStringNumberRecord(value.state_counts) &&
  Array.isArray(value.objects) &&
  value.objects.every(isImportObjectReview);
const isAuthoredImportReviewResponse: Validator<AuthoredImportReviewResponse> = (
  value,
): value is AuthoredImportReviewResponse =>
  isRecord(value) &&
  isString(value.import_batch_id) &&
  ["ACCEPTED", "REJECTED"].includes(String(value.decision)) &&
  isFiniteNumber(value.reviewed_candidate_count) &&
  isFiniteNumber(value.project_sequence);

export const mountSourcePage = async (services: SourcePageServices): Promise<void> => {
  const { request, requiredElement, toErrorMessage } = services;
  const [configurations, status, imports] = await Promise.all([
    request("/authored-sources", isAuthoredSourceConfigurations),
    request("/authored-sources/google-sheets/status", isAuthoredSourceStatus),
    request("/imports", isAuthoredImportSummaries),
  ]);
  requiredElement<HTMLElement>("#source-health").textContent = status.health;
  requiredElement<HTMLElement>("#source-status").textContent = status.detail;
  requiredElement<HTMLElement>("#source-fetched-at").textContent =
    status.last_successful_fetch_at ?? "Never";
  requiredElement<HTMLElement>("#source-snapshot-hash").textContent =
    status.latest_snapshot_hash ?? "None";
  requiredElement<HTMLElement>("#source-workbook").textContent =
    configurations.length === 0
      ? "Not configured"
      : `${configurations[0]!.source_alias} · ${configurations[0]!.spreadsheet_id}`;
  const list = requiredElement<HTMLElement>("#source-imports");
  list.replaceChildren();
  const openReview = async (batchId: string): Promise<void> => {
    const review = await request(
      `/imports/${encodeURIComponent(batchId)}`,
      isAuthoredImportReview,
    );
    requiredElement<HTMLElement>("#source-review").hidden = false;
    requiredElement<HTMLElement>("#source-review-summary").textContent = Object.entries(
      review.state_counts,
    )
      .map(([stateName, count]) => `${stateName}: ${count}`)
      .join(" · ");
    requiredElement<HTMLElement>("#source-review-objects").replaceChildren(
      ...review.objects.map((item) => {
        const article = document.createElement("article");
        const heading = document.createElement("strong");
        heading.textContent = `${item.state} · ${item.tab} · ${item.external_id}`;
        const detail = document.createElement("p");
        detail.textContent = `${item.canonical_subject_id} · ${item.source_range ?? "historical source"}`;
        article.append(heading, detail);
        return article;
      }),
    );
    requiredElement<HTMLInputElement>(
      "#source-review-form input[name='import_batch_id']",
    ).value = batchId;
  };
  if (imports.length === 0) {
    const empty = document.createElement("p");
    empty.textContent =
      "No source import has been loaded. Fetch the read-only source after validation.";
    list.append(empty);
  } else {
    list.append(
      ...imports.map((item) => {
        const article = document.createElement("article");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = `${item.review_status} · ${item.import_batch_id}`;
        button.addEventListener("click", () => void openReview(item.import_batch_id));
        const detail = document.createElement("p");
        const tabCounts = Object.entries(item.record_counts)
          .map(([tab, count]) => `${tab}: ${count}`)
          .join(" · ");
        detail.textContent = `${tabCounts} · ${item.diagnostic_count} diagnostics · ${item.fetched_at}`;
        article.append(button, detail);
        return article;
      }),
    );
  }
  requiredElement<HTMLButtonElement>("#source-sync").addEventListener("click", () => {
    void (async () => {
      try {
        const synced = await request(
          "/authored-sources/google-sheets/sync",
          isAuthoredImportSummary,
          { method: "POST" },
        );
        requiredElement<HTMLElement>("#source-status").textContent =
          `${synced.review_status} · ${synced.import_batch_id} · reload to review.`;
      } catch (error: unknown) {
        requiredElement<HTMLElement>("#source-status").textContent = toErrorMessage(
          error,
          "Source fetch failed; retained accepted evidence is unchanged.",
        );
      }
    })();
  });
  const form = requiredElement<HTMLFormElement>("#source-review-form");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void (async () => {
      const data = new FormData(form);
      const batchId = String(data.get("import_batch_id") ?? "");
      try {
        const response = await request(
          `/imports/${encodeURIComponent(batchId)}/review`,
          isAuthoredImportReviewResponse,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              decision: String(data.get("decision") ?? ""),
              rationale: String(data.get("rationale") ?? ""),
              totp_code: String(data.get("totp_code") ?? ""),
            }),
          },
        );
        requiredElement<HTMLElement>("#source-review-status").textContent =
          `${response.decision}: ${response.reviewed_candidate_count} candidates reviewed at project sequence ${response.project_sequence}.`;
        form
          .querySelectorAll<HTMLInputElement | HTMLSelectElement>("input, select")
          .forEach((control) => {
            control.disabled = true;
          });
      } catch (error: unknown) {
        requiredElement<HTMLElement>("#source-review-status").textContent = toErrorMessage(
          error,
          "Import review failed.",
        );
      }
    })();
  });
};
