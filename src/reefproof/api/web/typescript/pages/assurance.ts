import type { components } from "../workbench-contracts.js";

type ReturnFlowPolicyTemplate = components["schemas"]["ReturnFlowPolicyTemplate"];
type FlowInputs = components["schemas"]["ReturnFlowPolicyInputs"];
type FlowFieldName = keyof FlowInputs;
type ReturnFlowPolicyRevision = components["schemas"]["ReturnFlowPolicyRevision"];
type JsonRecord = Record<string, unknown>;
type Validator<T> = (value: unknown) => value is T;
type StatusKind = "ready" | "empty" | "error";

export type AssurancePageServices = Readonly<{
  request: <T>(path: string, validator: Validator<T>, options?: RequestInit) => Promise<T>;
  requestOptional: <T>(path: string, validator: Validator<T>) => Promise<T | null>;
  requiredElement: <T extends Element>(selector: string) => T;
  setStatus: (selector: string, message: string, state: StatusKind) => void;
  toErrorMessage: (error: unknown, fallback: string) => string;
}>;

type FieldPresentation = Readonly<{
  label: string;
  hint: string;
  unit: string;
  min: number;
  max: number;
  step: string;
  placeholder: string;
}>;
const fields: Readonly<Record<FlowFieldName, FieldPresentation>> = {
  tank_volume_gallons: { label: "Main-tank volume", hint: "Authored system volume used for turnover.", unit: "gal", min: 0.001, max: 1_000_000, step: "any", placeholder: "120" },
  pump_rated_flow_gph: { label: "Pump-rated return flow", hint: "Manufacturer-rated flow before system losses.", unit: "GPH", min: 0.001, max: 10_000_000, step: "any", placeholder: "800" },
  delivered_flow_gph: { label: "Delivered return flow", hint: "Your measured or estimated delivered flow.", unit: "GPH", min: 0.001, max: 10_000_000, step: "any", placeholder: "650" },
  minimum_turnover_per_hour: { label: "Minimum acceptable turnover", hint: "Your authored target—not a universal recommendation.", unit: "× / hr", min: 0.001, max: 1_000, step: "any", placeholder: "5" },
};

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isString = (value: unknown): value is string => typeof value === "string";
const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(isString);
const hasManualBoundary = (value: JsonRecord): boolean =>
  value.schema_version === "0.1" &&
  value.provenance_label === "MANUAL / NOT LIVE" &&
  value.live_observation === false;
const isTemplate: Validator<ReturnFlowPolicyTemplate> = (
  value,
): value is ReturnFlowPolicyTemplate =>
  isRecord(value) &&
  hasManualBoundary(value) &&
  value.policy_template_id === "RP-POLICY-FLOW-001" &&
  value.provenance === "MANUAL" &&
  value.units === "gallons/hour" &&
  isStringArray(value.fields);
const isInputs = (value: unknown): value is FlowInputs =>
  isRecord(value) &&
  isFiniteNumber(value.tank_volume_gallons) &&
  isFiniteNumber(value.pump_rated_flow_gph) &&
  isFiniteNumber(value.delivered_flow_gph) &&
  isFiniteNumber(value.minimum_turnover_per_hour);
const isRevision: Validator<ReturnFlowPolicyRevision> = (
  value,
): value is ReturnFlowPolicyRevision =>
  isRecord(value) &&
  hasManualBoundary(value) &&
  isString(value.revision_id) &&
  value.policy_template_id === "RP-POLICY-FLOW-001" &&
  isFiniteNumber(value.revision_number) &&
  isString(value.created_at) &&
  isString(value.authoring_operator_session_id) &&
  isInputs(value.inputs) &&
  isRecord(value.preview) &&
  ["PASS", "FAIL"].includes(String(value.preview.state)) &&
  isFiniteNumber(value.preview.actual_turnover_per_hour) &&
  isFiniteNumber(value.preview.minimum_delivered_flow_gph) &&
  isFiniteNumber(value.preview.delivery_difference_gph) &&
  isFiniteNumber(value.preview.delivery_efficiency_percent) &&
  isString(value.preview.explanation);

const boundedFields = (template: ReturnFlowPolicyTemplate): readonly FlowFieldName[] => {
  if (
    template.fields.length !== Object.keys(fields).length ||
    new Set(template.fields).size !== template.fields.length ||
    template.fields.some((field) => !Object.hasOwn(fields, field))
  ) throw new Error("Backend field contract is outside the bounded UI model.");
  return template.fields as readonly FlowFieldName[];
};
const createFields = (services: AssurancePageServices, template: ReturnFlowPolicyTemplate): void => {
  const container = services.requiredElement<HTMLElement>("#flow-fields");
  const names = boundedFields(template);
  container.replaceChildren();
  names.forEach((name, index) => {
    const presentation = fields[name];
    const label = document.createElement("label");
    label.className = "field";
    const heading = document.createElement("span");
    heading.className = "field__label";
    heading.textContent = `${index + 1}. ${presentation.label}`;
    const hint = document.createElement("span");
    hint.className = "field__hint";
    hint.textContent = presentation.hint;
    const control = document.createElement("span");
    control.className = "input-shell";
    const input = document.createElement("input");
    Object.assign(input, {
      name,
      type: "number",
      min: String(presentation.min),
      max: String(presentation.max),
      step: presentation.step,
      placeholder: presentation.placeholder,
      required: true,
      inputMode: "decimal",
    });
    const unit = document.createElement("span");
    unit.textContent = presentation.unit;
    unit.setAttribute("aria-hidden", "true");
    control.append(input, unit);
    label.append(heading, hint, control);
    container.append(label);
  });
  services.requiredElement<HTMLElement>("#field-count").textContent = `${names.length} bounded fields`;
};
const input = (form: HTMLFormElement, name: FlowFieldName): HTMLInputElement => {
  const element = form.elements.namedItem(name);
  if (!(element instanceof HTMLInputElement)) throw new Error(`Required input is missing: ${name}`);
  return element;
};
const readInputs = (form: HTMLFormElement): FlowInputs => ({
  tank_volume_gallons: input(form, "tank_volume_gallons").valueAsNumber,
  pump_rated_flow_gph: input(form, "pump_rated_flow_gph").valueAsNumber,
  delivered_flow_gph: input(form, "delivered_flow_gph").valueAsNumber,
  minimum_turnover_per_hour: input(form, "minimum_turnover_per_hour").valueAsNumber,
});
const render = (
  services: AssurancePageServices,
  revision: ReturnFlowPolicyRevision,
  form: HTMLFormElement,
): void => {
  (Object.entries(revision.inputs) as [FlowFieldName, number][]).forEach(([name, value]) => {
    input(form, name).value = String(value);
  });
  const set = (name: string, value: string): void => {
    services.requiredElement<HTMLElement>(`[data-result="${name}"]`).textContent = value;
  };
  set("revision", `Revision ${revision.revision_number} · ${revision.created_at}`);
  set("author-session", `Author session ${revision.authoring_operator_session_id}`);
  set("state", revision.preview.state);
  set("turnover", `${revision.preview.actual_turnover_per_hour}× / hr`);
  set("minimum-flow", `${revision.preview.minimum_delivered_flow_gph} GPH`);
  set("difference", `${revision.preview.delivery_difference_gph} GPH`);
  set("efficiency", `${revision.preview.delivery_efficiency_percent}%`);
  set("explanation", revision.preview.explanation);
  const preview = services.requiredElement<HTMLElement>("#preview");
  preview.dataset.state = revision.preview.state.toLowerCase();
  preview.hidden = false;
};

export const mountAssurancePage = async (services: AssurancePageServices): Promise<void> => {
  const form = services.requiredElement<HTMLFormElement>("#flow-form");
  try {
    const template = await services.request("/policy-template", isTemplate);
    createFields(services, template);
    services.requiredElement<HTMLElement>("#policy-inputs").hidden = false;
    const latest = await services.requestOptional("/policy-revisions/latest", isRevision);
    if (latest === null) {
      services.setStatus("#loading-status", "Ready · No authored policy has been saved yet.", "empty");
    } else {
      render(services, latest, form);
      services.setStatus("#loading-status", `Loaded saved revision ${latest.revision_number} from the backend.`, "ready");
    }
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void (async () => {
        try {
          const revision = await services.request("/policy-revisions", isRevision, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(readInputs(form)),
          });
          render(services, revision, form);
          services.setStatus("#loading-status", `Saved revision ${revision.revision_number}.`, "ready");
          services.requiredElement<HTMLElement>("#preview").scrollIntoView({ behavior: "smooth", block: "start" });
        } catch (error: unknown) {
          services.setStatus("#loading-status", services.toErrorMessage(error, "Policy save failed."), "error");
        }
      })();
    });
  } catch (error: unknown) {
    services.setStatus("#loading-status", services.toErrorMessage(error, "Assurance failed to load."), "error");
  }
};
