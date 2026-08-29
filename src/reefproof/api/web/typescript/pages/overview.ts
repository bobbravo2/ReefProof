import type { components } from "../workbench-contracts.js";
import { mountReconciliation } from "../shared/reconciliation.js";

type ElectricalPosture = components["schemas"]["ElectricalPostureResponse"];
type ProjectBrief = components["schemas"]["ProjectBrief"];
type JsonRecord = Record<string, unknown>;
type Validator<T> = (value: unknown) => value is T;

export type OverviewPageServices = Readonly<{
  projectId: string;
  requestWorkbench: <T>(path: string, validator: Validator<T>) => Promise<T>;
  requestProject: <T>(path: string, validator: Validator<T>, options?: RequestInit) => Promise<T>;
  requiredElement: <T extends Element>(selector: string) => T;
  setStatus: (selector: string, message: string, state: "ready" | "error") => void;
  toErrorMessage: (error: unknown, fallback: string) => string;
}>;

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isString = (value: unknown): value is string => typeof value === "string";
const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(isString);

const projectBriefValidator = (projectId: string): Validator<ProjectBrief> =>
  (value): value is ProjectBrief =>
    isRecord(value) &&
    value.project_id === projectId &&
    isRecord(value.recommended_next_action) &&
    ["SELECTED", "UNKNOWN"].includes(String(value.recommended_next_action.status)) &&
    isRecord(value.current_posture) &&
    ["commissioning", "operational", "UNKNOWN"].includes(
      String(value.current_posture.posture),
    ) &&
    ["commissioning", "operational", "UNKNOWN"].includes(
      String(value.current_posture.evaluated_posture),
    ) &&
    ["TRUSTED", "REVOKED"].includes(String(value.current_posture.trust_status)) &&
    isStringArray(value.current_posture.contributing_trust_event_ids) &&
    Array.isArray(value.highest_consequence_risks) &&
    Array.isArray(value.important_unknowns) &&
    Array.isArray(value.recent_accepted_decisions) &&
    isRecord(value.continue_interview);

const electricalPostureValidator = (projectId: string): Validator<ElectricalPosture> =>
  (value): value is ElectricalPosture =>
    isRecord(value) &&
    value.project_id === projectId &&
    ["empty", "partial"].includes(String(value.import_state)) &&
    isString(value.headline) &&
    isRecord(value.recommended_action) &&
    isString(value.recommended_action.id) &&
    isString(value.recommended_action.label) &&
    isString(value.recommended_action.description) &&
    isString(value.recommended_action.href) &&
    isFiniteNumber(value.observed_entity_count) &&
    isRecord(value.entity_counts) &&
    Object.values(value.entity_counts).every(isFiniteNumber) &&
    isFiniteNumber(value.unknown_entity_count) &&
    isFiniteNumber(value.redacted_field_count) &&
    isRecord(value.redaction_categories) &&
    Object.values(value.redaction_categories).every(isFiniteNumber) &&
    isStringArray(value.unproven_domains);

const renderProjectList = (
  services: OverviewPageServices,
  name: string,
  values: readonly string[],
): void => {
  const list = services.requiredElement<HTMLElement>(`[data-project-list="${name}"]`);
  list.replaceChildren();
  const rendered = values.length === 0
    ? ["UNKNOWN · no structured records are available."]
    : values;
  rendered.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    list.append(item);
  });
};

const renderProjectBrief = (services: OverviewPageServices, brief: ProjectBrief): void => {
  const text = (name: string, value: string): void => {
    services.requiredElement<HTMLElement>(`[data-project="${name}"]`).textContent = value;
  };
  const recommendation = brief.recommended_next_action;
  text(
    "recommendation",
    recommendation.action === null
      ? "UNKNOWN · no deterministic action is currently selected."
      : `${recommendation.action.action_type.replaceAll("_", " ")} · ${recommendation.action.action_id}`,
  );
  text("recommendation-reasons", `Reason codes: ${recommendation.reason_codes.join(", ")}`);
  text(
    "posture",
    brief.current_posture.trust_status === "REVOKED"
      ? `⊘ UNKNOWN · REVOKED (evaluated ${brief.current_posture.evaluated_posture})`
      : brief.current_posture.posture,
  );
  text(
    "posture-reasons",
    `Reason codes: ${brief.current_posture.reason_codes.join(", ")} · ` +
      `Trust events: ${brief.current_posture.contributing_trust_event_ids.join(", ") || "none"}`,
  );
  renderProjectList(
    services,
    "risks",
    brief.highest_consequence_risks.map(
      (risk) => `${risk.risk_id} · severity ${risk.severity} · ${risk.reason_codes.join(", ")}`,
    ),
  );
  renderProjectList(
    services,
    "unknowns",
    brief.important_unknowns.map(
      (unknown) =>
        `${unknown.unknown_id} · impact ${unknown.impact} · ${unknown.reason_codes.join(", ")}`,
    ),
  );
  renderProjectList(
    services,
    "decisions",
    brief.recent_accepted_decisions.map(
      (decision) =>
        `${decision.subject_id}.${decision.attribute} = ${String(decision.accepted_value)} · ` +
        `${decision.accepted_at} · source ${decision.source_candidate_fact_id}`,
    ),
  );
  text(
    "continue-interview",
    brief.continue_interview.based_on_unknown_ids.length === 0
      ? "No structured unknown currently blocks the interview."
      : `${brief.continue_interview.based_on_unknown_ids.length} structured unknown(s) are ready.`,
  );
  services.requiredElement<HTMLElement>("#project-overview").hidden = false;
};

const renderElectricalPosture = (
  services: OverviewPageServices,
  posture: ElectricalPosture,
): void => {
  const text = (name: string, value: string): void => {
    services.requiredElement<HTMLElement>(`[data-electrical="${name}"]`).textContent = value;
  };
  text("import-state", posture.import_state.toUpperCase());
  text("headline", posture.headline);
  text(
    "action",
    `${posture.recommended_action.label}. ${posture.recommended_action.description}`,
  );
  const action = services.requiredElement<HTMLAnchorElement>("[data-electrical-action]");
  action.href = posture.recommended_action.href;
  action.textContent = `${posture.recommended_action.label} →`;
  const counts = Object.entries(posture.entity_counts ?? {})
    .map(([name, count]) => `${count} ${name}`)
    .join(" · ");
  text(
    "coverage",
    `${posture.observed_entity_count} imported entities${counts === "" ? "" : ` · ${counts}`}`,
  );
  text(
    "freshness",
    posture.captured_at === null || posture.captured_at === undefined
      ? "No captured configuration timestamp."
      : `Captured ${posture.captured_at}`,
  );
  text(
    "unknowns",
    `${posture.unknown_entity_count} unknown-confidence entities · ` +
      `${posture.unproven_domains.join(", ") || "no unproven domains reported"}`,
  );
  const categories = Object.entries(posture.redaction_categories ?? {})
    .map(([name, count]) => `${count} ${name.replaceAll("_", " ")}`)
    .join(" · ");
  text(
    "redactions",
    `${posture.redacted_field_count} fields omitted${categories === "" ? "" : ` · ${categories}`}`,
  );
  services.requiredElement<HTMLElement>("#electrical-posture").hidden = false;
};

export const mountOverviewPage = async (services: OverviewPageServices): Promise<void> => {
  const loadProjectBrief = async (): Promise<void> => {
    const brief = await services.requestProject("/brief", projectBriefValidator(services.projectId));
    renderProjectBrief(services, brief);
    services.setStatus("#project-status", "Durable project brief loaded.", "ready");
  };
  services.requiredElement<HTMLFormElement>("#project-session-form").addEventListener(
    "submit",
    (event) => {
      event.preventDefault();
      void loadProjectBrief().catch((error: unknown) => {
        services.setStatus(
          "#project-status",
          services.toErrorMessage(error, "Project state failed to load."),
          "error",
        );
      });
    },
  );
  const [electrical, brief] = await Promise.all([
    services.requestWorkbench(
      "/electrical-posture",
      electricalPostureValidator(services.projectId),
    ),
    services.requestProject("/brief", projectBriefValidator(services.projectId)),
    mountReconciliation({
      request: services.requestProject,
      toErrorMessage: services.toErrorMessage,
    }),
  ]);
  renderElectricalPosture(services, electrical);
  renderProjectBrief(services, brief);
  services.setStatus("#project-status", "Durable project brief loaded.", "ready");
};
