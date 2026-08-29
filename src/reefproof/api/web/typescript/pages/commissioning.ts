import type { components } from "../workbench-contracts.js";

type CommissioningProjection = components["schemas"]["CommissioningProjection"];
type CommissioningVerification = components["schemas"]["CommissioningVerification"];
type FailureModeDisposition = components["schemas"]["FailureModeDisposition"];
type JsonRecord = Record<string, unknown>;
type Validator<T> = (value: unknown) => value is T;

export type CommissioningPageServices = Readonly<{
  request: <T>(path: string, validator: Validator<T>, options?: RequestInit) => Promise<T>;
  requiredElement: <T extends Element>(selector: string) => T;
  toErrorMessage: (error: unknown, fallback: string) => string;
}>;

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isString = (value: unknown): value is string => typeof value === "string";
const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(isString);
const isCommissioningRequirement = (value: unknown): boolean =>
  isRecord(value) &&
  isString(value.requirement_id) &&
  isString(value.label) &&
  ["PASS", "FAIL", "UNKNOWN"].includes(String(value.state)) &&
  isString(value.detail) &&
  isStringArray(value.evidence_ids);
const isCommissioningDevice = (value: unknown): boolean =>
  isRecord(value) &&
  isString(value.device_id) &&
  isString(value.canonical_device_id) &&
  isString(value.display_name) &&
  ["NOT_STARTED", "IN_PROGRESS", "BLOCKED", "COMMISSIONED", "REVOKED"].includes(
    String(value.state),
  ) &&
  Array.isArray(value.requirements) &&
  value.requirements.every(isCommissioningRequirement);
const isCommissioningProjection: Validator<CommissioningProjection> = (
  value,
): value is CommissioningProjection =>
  isRecord(value) &&
  isString(value.project_id) &&
  Array.isArray(value.devices) &&
  value.devices.every(isCommissioningDevice) &&
  isFiniteNumber(value.commissioned_count) &&
  isFiniteNumber(value.blocked_count) &&
  isFiniteNumber(value.unknown_requirement_count);
const isCommissioningVerification: Validator<CommissioningVerification> = (
  value,
): value is CommissioningVerification =>
  isRecord(value) &&
  isString(value.verification_id) &&
  isString(value.device_id) &&
  ["CONNECTION", "POWER", "COMMUNICATIONS", "FAULT_TEST", "LABEL"].includes(
    String(value.kind),
  ) &&
  ["PASS", "FAIL", "NOT_APPLICABLE"].includes(String(value.outcome));
const isFailureModeDisposition: Validator<FailureModeDisposition> = (
  value,
): value is FailureModeDisposition =>
  isRecord(value) &&
  isString(value.disposition_id) &&
  isString(value.device_id) &&
  isString(value.failure_mode_id) &&
  ["ACCEPTED_RISK", "ALERTED_DETECTED", "AUTOMATED_MITIGATION"].includes(
    String(value.disposition),
  );

export const mountCommissioningPage = async (
  services: CommissioningPageServices,
): Promise<void> => {
  const { request, requiredElement, toErrorMessage } = services;
  const loadProjection = async (): Promise<void> => {
    const projection = await request("/commissioning", isCommissioningProjection);
    requiredElement<HTMLElement>("#commissioning-status").textContent =
      `${projection.commissioned_count} commissioned · ${projection.blocked_count} blocked · ` +
      `${projection.unknown_requirement_count} unknown requirements`;
    requiredElement<HTMLElement>("#commissioning-devices").replaceChildren(
      ...projection.devices.map((device) => {
        const article = document.createElement("article");
        const heading = document.createElement("h3");
        heading.textContent = `${device.state} · ${device.display_name}`;
        const identity = document.createElement("code");
        identity.textContent = device.canonical_device_id;
        const list = document.createElement("ul");
        list.append(
          ...device.requirements.map((requirement) => {
            const item = document.createElement("li");
            item.textContent =
              `${requirement.state} · ${requirement.label}: ${requirement.detail}`;
            return item;
          }),
        );
        article.append(heading, identity, list);
        return article;
      }),
    );
  };
  await loadProjection();
  const verificationForm = requiredElement<HTMLFormElement>(
    "#commissioning-verification-form",
  );
  verificationForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void (async () => {
      const data = new FormData(verificationForm);
      const connection = String(data.get("connection_id") ?? "").trim();
      const controlSurface = String(data.get("control_surface_id") ?? "").trim();
      try {
        const verification = await request(
          "/commissioning/verifications",
          isCommissioningVerification,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              device_id: String(data.get("device_id") ?? ""),
              kind: String(data.get("kind") ?? ""),
              outcome: String(data.get("outcome") ?? ""),
              rationale: String(data.get("rationale") ?? ""),
              evidence_reference: String(data.get("evidence_reference") ?? ""),
              connection_id: connection || null,
              control_surface_id: controlSurface || null,
              totp_code: String(data.get("totp_code") ?? ""),
            }),
          },
        );
        requiredElement<HTMLElement>("#commissioning-action-status").textContent =
          `Recorded ${verification.kind} ${verification.outcome}.`;
        await loadProjection();
      } catch (error: unknown) {
        requiredElement<HTMLElement>("#commissioning-action-status").textContent =
          toErrorMessage(error, "Commissioning verification failed.");
      }
    })();
  });
  const dispositionForm = requiredElement<HTMLFormElement>("#failure-mode-form");
  dispositionForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void (async () => {
      const data = new FormData(dispositionForm);
      try {
        const disposition = await request(
          "/commissioning/failure-mode-dispositions",
          isFailureModeDisposition,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              device_id: String(data.get("device_id") ?? ""),
              failure_mode_id: String(data.get("failure_mode_id") ?? ""),
              disposition: String(data.get("disposition") ?? ""),
              rationale: String(data.get("rationale") ?? ""),
              evidence_reference: String(data.get("evidence_reference") ?? ""),
              totp_code: String(data.get("totp_code") ?? ""),
            }),
          },
        );
        requiredElement<HTMLElement>("#failure-mode-status").textContent =
          `Recorded ${disposition.failure_mode_id}: ${disposition.disposition}.`;
        await loadProjection();
      } catch (error: unknown) {
        requiredElement<HTMLElement>("#failure-mode-status").textContent =
          toErrorMessage(error, "Failure-mode disposition failed.");
      }
    })();
  });
};
