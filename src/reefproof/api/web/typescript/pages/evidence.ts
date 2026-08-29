import type { components } from "../workbench-contracts.js";

type ReturnFlowPolicyRevision = components["schemas"]["ReturnFlowPolicyRevision"];
type FlowInputs = components["schemas"]["ReturnFlowPolicyInputs"];
type LogicalTreeNode = components["schemas"]["LogicalTreeNode"];
type InvariantTemplate = components["schemas"]["InvariantTemplate"];
type InvariantCatalog = components["schemas"]["InvariantCatalog"];
type JsonRecord = Record<string, unknown>;
type Validator<T> = (value: unknown) => value is T;

export type EvidencePageServices = Readonly<{
  request: <T>(path: string, validator: Validator<T>) => Promise<T>;
  requestOptional: <T>(path: string, validator: Validator<T>) => Promise<T | null>;
  requiredElement: <T extends Element>(selector: string) => T;
  setStatus: (selector: string, message: string, state: "ready" | "error") => void;
  toErrorMessage: (error: unknown, fallback: string) => string;
  mountTrust: () => void;
}>;

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
const isLogicalTreeNode: Validator<LogicalTreeNode> = (
  value,
): value is LogicalTreeNode =>
  isRecord(value) &&
  ["rule", "all", "evidence", "outcome"].includes(String(value.kind)) &&
  isString(value.label) &&
  (value.state === null || ["PASS", "FAIL", "UNKNOWN"].includes(String(value.state))) &&
  Array.isArray(value.children) &&
  value.children.every(isLogicalTreeNode);
const isInvariantTemplate: Validator<InvariantTemplate> = (
  value,
): value is InvariantTemplate =>
  isRecord(value) &&
  isString(value.invariant_id) &&
  isString(value.version) &&
  isString(value.title) &&
  ["info", "warning", "high", "critical"].includes(String(value.severity)) &&
  isStringArray(value.evidence_requirements) &&
  isLogicalTreeNode(value.logical_tree);
const isCatalog: Validator<InvariantCatalog> = (value): value is InvariantCatalog =>
  isRecord(value) &&
  hasManualBoundary(value) &&
  Array.isArray(value.templates) &&
  value.templates.every(isInvariantTemplate);
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

const formatTree = (node: LogicalTreeNode, depth = 0): string => {
  const branch = depth === 0 ? "" : "└─ ";
  const state = node.state === null ? "" : `[${node.state}] `;
  const current = `${"  ".repeat(depth)}${branch}${state}${node.label}`;
  return [current, ...node.children.map((child) => formatTree(child, depth + 1))].join("\n");
};
const renderCatalog = (services: EvidencePageServices, catalog: InvariantCatalog): void => {
  const selector = services.requiredElement<HTMLSelectElement>("#rule-template-selector");
  selector.replaceChildren();
  const templates = new Map<string, InvariantTemplate>();
  catalog.templates.forEach((template) => {
    if (templates.has(template.invariant_id)) throw new Error(`Duplicate committed rule: ${template.invariant_id}`);
    templates.set(template.invariant_id, template);
    const option = document.createElement("option");
    option.value = template.invariant_id;
    option.textContent = `${template.invariant_id} · ${template.title}`;
    selector.append(option);
  });
  if (templates.size === 0) throw new Error("The committed rule catalog is empty.");
  services.requiredElement<HTMLElement>("#catalog-summary").textContent =
    `${templates.size} backend-authored rules · schema ${catalog.schema_version}`;
  const renderSelected = (): void => {
    const template = templates.get(selector.value);
    if (template === undefined) throw new Error(`Unknown committed rule: ${selector.value}`);
    services.requiredElement<HTMLElement>("#rule-template-heading").textContent =
      `${template.invariant_id} v${template.version} — ${template.title}`;
    const severity = services.requiredElement<HTMLElement>("#rule-template-severity");
    severity.textContent = template.severity.toUpperCase();
    severity.dataset.severity = template.severity;
    services.requiredElement<HTMLElement>("#rule-tree").textContent = formatTree(template.logical_tree);
  };
  selector.addEventListener("change", renderSelected);
  renderSelected();
  services.requiredElement<HTMLElement>("#rule-catalog").hidden = false;
};
const renderRevision = (services: EvidencePageServices, revision: ReturnFlowPolicyRevision): void => {
  const set = (name: string, value: string): void => {
    services.requiredElement<HTMLElement>(`[data-evidence="${name}"]`).textContent = value;
  };
  set("state", revision.preview.state);
  set("revision", `Revision ${revision.revision_number}`);
  set("created", revision.created_at);
  set("author-session", revision.authoring_operator_session_id);
  set("template", revision.policy_template_id);
  set("provenance", revision.provenance_label);
  set("revision-id", revision.revision_id);
  set("tank-volume", `${revision.inputs.tank_volume_gallons} gal`);
  set("pump-flow", `${revision.inputs.pump_rated_flow_gph} GPH`);
  set("delivered-flow", `${revision.inputs.delivered_flow_gph} GPH`);
  set("minimum-turnover", `${revision.inputs.minimum_turnover_per_hour}× / hr`);
  set("explanation", revision.preview.explanation);
  services.requiredElement<HTMLElement>("#evidence-revision-empty").hidden = true;
  services.requiredElement<HTMLElement>("#evidence-revision").hidden = false;
};

export const mountEvidencePage = async (services: EvidencePageServices): Promise<void> => {
  services.mountTrust();
  try {
    const [catalog, latest] = await Promise.all([
      services.request("/invariant-catalog", isCatalog),
      services.requestOptional("/policy-revisions/latest", isRevision),
    ]);
    renderCatalog(services, catalog);
    services.requiredElement<HTMLElement>("#evidence-invariant-count").textContent = String(catalog.templates.length);
    if (latest === null) {
      services.requiredElement<HTMLElement>("#evidence-revision-empty").hidden = false;
      services.requiredElement<HTMLElement>("#evidence-revision").hidden = true;
      services.setStatus("#evidence-status", "Ready · No authored policy evidence exists yet.", "ready");
    } else {
      renderRevision(services, latest);
      services.setStatus("#evidence-status", `Loaded immutable revision ${latest.revision_number}.`, "ready");
    }
  } catch (error: unknown) {
    services.setStatus("#evidence-status", services.toErrorMessage(error, "Evidence failed to load."), "error");
  }
};
