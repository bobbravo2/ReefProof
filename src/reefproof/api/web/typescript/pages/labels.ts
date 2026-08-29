import type { components } from "../workbench-contracts.js";

type LabelManifest = components["schemas"]["LabelManifest"];
type CommissioningVerification = components["schemas"]["CommissioningVerification"];
type JsonRecord = Record<string, unknown>;
type Validator<T> = (value: unknown) => value is T;

export type LabelsPageServices = Readonly<{
  request: <T>(path: string, validator: Validator<T>, options?: RequestInit) => Promise<T>;
  requiredElement: <T extends Element>(selector: string) => T;
  toErrorMessage: (error: unknown, fallback: string) => string;
}>;

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isString = (value: unknown): value is string => typeof value === "string";
const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const isLabelRecord = (value: unknown): boolean =>
  isRecord(value) &&
  ["DEVICE", "PORT", "CABLE", "POWER SUPPLY"].includes(String(value.label_kind)) &&
  isString(value.label_id) &&
  isString(value.display_id) &&
  isString(value.primary_text) &&
  isFiniteNumber(value.copies);
const isLabelManifest: Validator<LabelManifest> = (value): value is LabelManifest =>
  isRecord(value) &&
  isString(value.manifest_id) &&
  isString(value.project_id) &&
  isString(value.project_name) &&
  isFiniteNumber(value.source_project_sequence) &&
  Array.isArray(value.records) &&
  value.records.every(isLabelRecord);
const isCommissioningVerification: Validator<CommissioningVerification> = (
  value,
): value is CommissioningVerification =>
  isRecord(value) &&
  isString(value.verification_id) &&
  isString(value.device_id) &&
  ["POWER", "COMMUNICATIONS", "FAULT_TEST", "LABEL"].includes(String(value.kind)) &&
  ["PASS", "FAIL", "NOT_APPLICABLE"].includes(String(value.outcome));

export const mountLabelsPage = async (services: LabelsPageServices): Promise<void> => {
  const { request, requiredElement, toErrorMessage } = services;
  const manifest = await request("/labels", isLabelManifest);
  requiredElement<HTMLElement>("#labels-status").textContent =
    `${manifest.project_name} · ${manifest.records.length} labels · sequence ${manifest.source_project_sequence}`;
  requiredElement<HTMLElement>("#label-records").replaceChildren(
    ...manifest.records.map((record) => {
      const article = document.createElement("article");
      const heading = document.createElement("strong");
      heading.textContent =
        `${record.label_kind} · ${record.display_id} · ${record.copies} ` +
        `cop${record.copies === 1 ? "y" : "ies"}`;
      const body = document.createElement("pre");
      body.textContent = [record.primary_text, record.secondary_text]
        .filter(Boolean)
        .join("\n");
      article.append(heading, body);
      return article;
    }),
  );
  requiredElement<HTMLInputElement>(
    "#label-verification-form input[name='manifest_id']",
  ).value = manifest.manifest_id;
  const form = requiredElement<HTMLFormElement>("#label-verification-form");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void (async () => {
      const data = new FormData(form);
      try {
        const verification = await request(
          "/commissioning/label-verifications",
          isCommissioningVerification,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              device_id: String(data.get("device_id") ?? ""),
              kind: "LABEL",
              outcome: String(data.get("outcome") ?? ""),
              rationale: String(data.get("rationale") ?? ""),
              evidence_reference: String(data.get("evidence_reference") ?? ""),
              manifest_id: String(data.get("manifest_id") ?? ""),
              label_id: String(data.get("label_id") ?? ""),
              label_endpoint: String(data.get("label_endpoint") ?? ""),
              totp_code: String(data.get("totp_code") ?? ""),
            }),
          },
        );
        requiredElement<HTMLElement>("#label-verification-status").textContent =
          `Recorded ${verification.outcome} for ${verification.label_id ?? "label"}.`;
      } catch (error: unknown) {
        requiredElement<HTMLElement>("#label-verification-status").textContent =
          toErrorMessage(error, "Label verification failed.");
      }
    })();
  });
};
