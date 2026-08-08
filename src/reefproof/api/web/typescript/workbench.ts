import type { components } from "./workbench-contracts.js";

const API_ROOT = "/v1/workbench";
const PROJECT_ID =
  document.documentElement?.dataset.projectId ?? "primary-reef-system";
const PROJECT_ROOT = `/v1/projects/${PROJECT_ID}`;
const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
const AUTHENTICATED_SESSION_SENTINEL = "authenticated-session";
const SESSION_INVALIDATED_MESSAGE =
  "Session is no longer valid. Authenticate again to continue.";

type ReturnFlowPolicyTemplate = components["schemas"]["ReturnFlowPolicyTemplate"];
type FlowInputs = components["schemas"]["ReturnFlowPolicyInputs"];
type FlowFieldName = keyof FlowInputs;
type ReturnFlowPolicyRevision = components["schemas"]["ReturnFlowPolicyRevision"];
type LogicalTreeNode = components["schemas"]["LogicalTreeNode"];
type InvariantTemplate = components["schemas"]["InvariantTemplate"];
type InvariantCatalog = components["schemas"]["InvariantCatalog"];
type PhysicalTwin = components["schemas"]["PhysicalTwin"];
type ProjectBrief = components["schemas"]["ProjectBrief"];
type InterviewSession = components["schemas"]["InterviewSession"];
type StoredCandidate = components["schemas"]["StoredCandidate"];
type CandidateReviewResponse = components["schemas"]["CandidateReviewResponse"];
type DatabaseSchema = components["schemas"]["DatabaseSchema"];
type DatabaseTableSchema = components["schemas"]["TableSchema"];
type DatabaseTablePage = components["schemas"]["TablePage"];
type DatabaseCell = components["schemas"]["DatabaseCell"];
type ElectricalPosture = components["schemas"]["ElectricalPostureResponse"];
type OperatorSession = {
  principal_id: string;
  principal_display_name: string;
};
type TrustEventView = {
  trust_event_id: string;
  event_type: "revoked" | "restored";
  scope_kind: "evidence" | "subsystem";
  scope_id: string;
  rationale: string;
  occurred_at: string;
};
type TrustStateView = {
  events: TrustEventView[];
  active_revocations: TrustEventView[];
  last_sequence: number;
};

type FieldPresentation = {
  label: string;
  hint: string;
  unit: string;
  min: number;
  max: number;
  step: string;
  placeholder: string;
};

const FIELD_PRESENTATION: Readonly<Record<FlowFieldName, FieldPresentation>> = {
  tank_volume_gallons: {
    label: "Main-tank volume",
    hint: "Authored system volume used for turnover.",
    unit: "gal",
    min: 0.001,
    max: 1_000_000,
    step: "any",
    placeholder: "120",
  },
  pump_rated_flow_gph: {
    label: "Pump-rated return flow",
    hint: "Manufacturer-rated flow before system losses.",
    unit: "GPH",
    min: 0.001,
    max: 10_000_000,
    step: "any",
    placeholder: "800",
  },
  delivered_flow_gph: {
    label: "Delivered return flow",
    hint: "Your measured or estimated delivered flow.",
    unit: "GPH",
    min: 0.001,
    max: 10_000_000,
    step: "any",
    placeholder: "650",
  },
  minimum_turnover_per_hour: {
    label: "Minimum acceptable turnover",
    hint: "Your authored target—not a universal recommendation.",
    unit: "× / hr",
    min: 0.001,
    max: 1_000,
    step: "any",
    placeholder: "5",
  },
};

let authenticatedPrincipalId: string | null = null;

const updateLogoutControl = (): void => {
  const button = document.querySelector<HTMLButtonElement>("#workbench-logout");
  if (button === null) {
    return;
  }
  button.hidden = authenticatedPrincipalId === null;
};

const requiredElement = <T extends Element>(selector: string): T => {
  const element = document.querySelector<T>(selector);
  if (element === null) {
    throw new Error(`Required element is missing: ${selector}`);
  }
  return element;
};

type JsonRecord = Record<string, unknown>;
type Validator<T> = (value: unknown) => value is T;
type StatusKind = "ready" | "empty" | "error";

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isString = (value: unknown): value is string => typeof value === "string";
const isBoolean = (value: unknown): value is boolean => typeof value === "boolean";
const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(isString);
const isTrustEventView = (value: unknown): value is TrustEventView =>
  isRecord(value) &&
  isString(value.trust_event_id) &&
  ["revoked", "restored"].includes(String(value.event_type)) &&
  ["evidence", "subsystem"].includes(String(value.scope_kind)) &&
  isString(value.scope_id) &&
  isString(value.rationale) &&
  isString(value.occurred_at);
const isTrustStateView: Validator<TrustStateView> = (
  value,
): value is TrustStateView =>
  isRecord(value) &&
  Array.isArray(value.events) &&
  value.events.every(isTrustEventView) &&
  Array.isArray(value.active_revocations) &&
  value.active_revocations.every(isTrustEventView) &&
  isFiniteNumber(value.last_sequence);

const hasManualBoundary = (value: JsonRecord): boolean =>
  value.schema_version === "0.1" &&
  value.collective_name === "Mock Collective" &&
  value.provenance_label === "MANUAL / NOT LIVE" &&
  value.live_observation === false;

const isReturnFlowPolicyTemplate: Validator<ReturnFlowPolicyTemplate> = (value): value is ReturnFlowPolicyTemplate =>
  isRecord(value) &&
  hasManualBoundary(value) &&
  value.policy_template_id === "RP-POLICY-FLOW-001" &&
  value.provenance === "MANUAL" &&
  value.units === "gallons/hour" &&
  isStringArray(value.fields);

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

const isInvariantCatalog: Validator<InvariantCatalog> = (
  value,
): value is InvariantCatalog =>
  isRecord(value) &&
  hasManualBoundary(value) &&
  Array.isArray(value.templates) &&
  value.templates.every(isInvariantTemplate);

const isPhysicalEntity = (value: unknown): boolean =>
  isRecord(value) &&
  isString(value.entity_id) &&
  ["display_tank", "sump", "return_pump"].includes(String(value.physical_type)) &&
  isString(value.label) &&
  isFiniteNumber(value.quantity) &&
  isFiniteNumber(value.elevation_inches) &&
  isRecord(value.size) &&
  isFiniteNumber(value.size.width_inches) &&
  isFiniteNumber(value.size.height_inches) &&
  isFiniteNumber(value.size.depth_inches) &&
  isRecord(value.geometry) &&
  isFiniteNumber(value.geometry.x) &&
  isFiniteNumber(value.geometry.y) &&
  isFiniteNumber(value.geometry.width) &&
  isFiniteNumber(value.geometry.height);

const isPhysicalRelationship = (value: unknown): boolean =>
  isRecord(value) &&
  ["down", "left", "up_and_right"].includes(String(value.direction)) &&
  isString(value.dependency) &&
  isString(value.label) &&
  isString(value.svg_path);

const isMockFinding = (value: unknown): boolean =>
  isRecord(value) &&
  ["critical", "high", "warning", "info"].includes(String(value.severity)) &&
  ["⚠", "▲", "●"].includes(String(value.icon)) &&
  ["CRITICAL", "WARNING", "INFO"].includes(String(value.state_text)) &&
  isString(value.summary);

const isPhysicalTwin: Validator<PhysicalTwin> = (value): value is PhysicalTwin =>
  isRecord(value) &&
  hasManualBoundary(value) &&
  Array.isArray(value.entities) &&
  value.entities.every(isPhysicalEntity) &&
  Array.isArray(value.relationships) &&
  value.relationships.every(isPhysicalRelationship) &&
  Array.isArray(value.findings) &&
  value.findings.every(isMockFinding);

const isFlowInputs = (value: unknown): value is FlowInputs =>
  isRecord(value) &&
  isFiniteNumber(value.tank_volume_gallons) &&
  isFiniteNumber(value.pump_rated_flow_gph) &&
  isFiniteNumber(value.delivered_flow_gph) &&
  isFiniteNumber(value.minimum_turnover_per_hour);

const isReturnFlowPolicyRevision: Validator<ReturnFlowPolicyRevision> = (
  value,
): value is ReturnFlowPolicyRevision =>
  isRecord(value) &&
  hasManualBoundary(value) &&
  isString(value.revision_id) &&
  value.policy_template_id === "RP-POLICY-FLOW-001" &&
  isFiniteNumber(value.revision_number) &&
  isString(value.created_at) &&
  isString(value.authoring_operator_session_id) &&
  isFlowInputs(value.inputs) &&
  isRecord(value.preview) &&
  ["PASS", "FAIL"].includes(String(value.preview.state)) &&
  isFiniteNumber(value.preview.actual_turnover_per_hour) &&
  isFiniteNumber(value.preview.minimum_delivered_flow_gph) &&
  isFiniteNumber(value.preview.delivery_difference_gph) &&
  isFiniteNumber(value.preview.delivery_efficiency_percent) &&
  isString(value.preview.explanation);

const isOperatorSession: Validator<OperatorSession> = (
  value,
): value is OperatorSession =>
  isRecord(value) &&
  isString(value.principal_id) &&
  value.principal_id.length > 0 &&
  isString(value.principal_display_name) &&
  value.principal_display_name.length > 0;

const isProjectBrief: Validator<ProjectBrief> = (value): value is ProjectBrief =>
  isRecord(value) &&
  value.project_id === PROJECT_ID &&
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

const isInterviewSessions: Validator<InterviewSession[]> = (
  value,
): value is InterviewSession[] =>
  Array.isArray(value) &&
  value.every(
    (session) =>
      isRecord(session) &&
      isString(session.session_id) &&
      isString(session.initiated_by_actor_id) &&
      isString(session.initiated_at) &&
      isString(session.purpose),
  );

const isStoredCandidates: Validator<StoredCandidate[]> = (
  value,
): value is StoredCandidate[] =>
  Array.isArray(value) &&
  value.every(
    (record) =>
      isRecord(record) &&
      isString(record.session_id) &&
      isRecord(record.candidate) &&
      isString(record.candidate.candidate_fact_id) &&
      isString(record.candidate.subject_id) &&
      isString(record.candidate.attribute) &&
      (record.decision === null || isRecord(record.decision)),
  );

const isCandidateReviewResponse: Validator<CandidateReviewResponse> = (
  value,
): value is CandidateReviewResponse =>
  isRecord(value) &&
  isRecord(value.candidate) &&
  isRecord(value.decision) &&
  ["accepted", "rejected"].includes(String(value.decision.decision)) &&
  isRecord(value.canonical_state);

const isElectricalPosture: Validator<ElectricalPosture> = (
  value,
): value is ElectricalPosture =>
  isRecord(value) &&
  value.project_id === PROJECT_ID &&
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

const isDatabaseColumn = (value: unknown): boolean =>
  isRecord(value) &&
  isFiniteNumber(value.position) &&
  isString(value.name) &&
  isString(value.declared_type) &&
  isBoolean(value.nullable) &&
  (value.default_value === null || isString(value.default_value)) &&
  isFiniteNumber(value.primary_key_position);

const isDatabaseTableSchema = (value: unknown): value is DatabaseTableSchema =>
  isRecord(value) &&
  isString(value.name) &&
  isFiniteNumber(value.row_count) &&
  Array.isArray(value.columns) &&
  value.columns.length > 0 &&
  value.columns.every(isDatabaseColumn) &&
  Array.isArray(value.foreign_keys) &&
  value.foreign_keys.every(
    (foreignKey) =>
      isRecord(foreignKey) &&
      isFiniteNumber(foreignKey.identifier) &&
      isFiniteNumber(foreignKey.sequence) &&
      isString(foreignKey.from_column) &&
      isString(foreignKey.target_table) &&
      (foreignKey.target_column === null || isString(foreignKey.target_column)) &&
      isString(foreignKey.on_update) &&
      isString(foreignKey.on_delete),
  ) &&
  Array.isArray(value.indexes) &&
  value.indexes.every(
    (index) =>
      isRecord(index) &&
      isString(index.name) &&
      isBoolean(index.unique) &&
      isStringArray(index.columns),
  );

const isDatabaseSchema: Validator<DatabaseSchema> = (
  value,
): value is DatabaseSchema =>
  isRecord(value) &&
  isString(value.alembic_revision) &&
  isString(value.integrity) &&
  Array.isArray(value.tables) &&
  value.tables.every(isDatabaseTableSchema);

const isDatabaseCell = (value: unknown): value is DatabaseCell =>
  isRecord(value) &&
  ["null", "integer", "real", "text", "blob"].includes(String(value.kind)) &&
  (value.value === null || isString(value.value) || isFiniteNumber(value.value)) &&
  isBoolean(value.truncated);

const isDatabaseTablePage: Validator<DatabaseTablePage> = (
  value,
): value is DatabaseTablePage => {
  if (
    !isRecord(value) ||
    !isString(value.table_name) ||
    !isFiniteNumber(value.offset) ||
    !isFiniteNumber(value.limit) ||
    !isFiniteNumber(value.total_rows) ||
    !isStringArray(value.columns) ||
    value.columns.length === 0 ||
    !Array.isArray(value.rows) ||
    (value.next_offset !== null && !isFiniteNumber(value.next_offset))
  ) {
    return false;
  }
  const columns = value.columns;
  return value.rows.every(
    (row) =>
      Array.isArray(row) &&
      row.length === columns.length &&
      row.every(isDatabaseCell),
  );
};

const toErrorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

const requestJsonFrom = async <T>(
  basePath: string,
  path: string,
  validator: Validator<T>,
  options?: RequestInit,
): Promise<T> => {
  const response = await fetch(`${basePath}${path}`, {
    ...options,
    headers: { Accept: "application/json", ...options?.headers },
  });
  if (response.status === 401) {
    invalidateSession();
    throw new Error(SESSION_INVALIDATED_MESSAGE);
  }
  if (!response.ok) {
    throw new Error(`${path || "/"} failed: ${response.status}`);
  }
  const value: unknown = await response.json();
  if (!validator(value)) {
    throw new Error(`${path || "/"} returned data outside the committed UI boundary.`);
  }
  return value;
};

const requestJson = async <T>(
  path: string,
  validator: Validator<T>,
  options?: RequestInit,
): Promise<T> => {
  return requestJsonFrom(API_ROOT, path, validator, options);
};

const requestProjectJson = async <T>(
  path: string,
  _principalId: string,
  validator: Validator<T>,
  options?: RequestInit,
): Promise<T> => {
  return requestJsonFrom(PROJECT_ROOT, path, validator, options);
};

const requestDatabaseJson = async <T>(
  path: string,
  validator: Validator<T>,
): Promise<T> => {
  return requestJsonFrom("/v1/database", path, validator);
};

const markSessionGate = (authenticated: boolean): void => {
  if (document.body != null) {
    document.body.dataset.sessionGated = authenticated ? "false" : "true";
  }
  const gate = document.querySelector<HTMLElement>("#session-auth-gate");
  if (gate !== null) {
    gate.hidden = authenticated;
  }
  const content = document.querySelector<HTMLElement>("#page-content");
  if (content !== null) {
    content.hidden = !authenticated;
  }
  updateLogoutControl();
};

const invalidateSession = (message = SESSION_INVALIDATED_MESSAGE): void => {
  authenticatedPrincipalId = null;
  markSessionGate(false);
  if (document.querySelector("#startup-auth-status") !== null) {
    setStatus("#startup-auth-status", message, "error");
  }
};

const probeAuthenticatedSession = async (): Promise<boolean> => {
  const response = await fetch(`${API_ROOT}/totp`, {
    headers: { Accept: "application/json" },
  });
  if (response.status === 401) {
    return false;
  }
  if (!response.ok) {
    throw new Error(`Session check failed: ${response.status}`);
  }
  return true;
};

const updateSystemStatus = async (): Promise<void> => {
  try {
    const response = await fetch("/v1/system/status");
    if (response.ok) {
      const status = (await response.json()) as {
        operating_mode: string;
        hydros_connection: string;
      };
      const badge = document.querySelector<HTMLElement>("#system-mode-badge");
      if (badge !== null) {
        const mode = status.operating_mode.toUpperCase();
        const live = status.hydros_connection === "connected" ? "LIVE" : "NOT LIVE";
        badge.textContent = `${mode} · ${live}`;
      }
    }
  } catch (error: unknown) {
    // System status is non-critical; fail silently
    console.debug("Could not fetch system status:", error);
  }
};

const initializeLogoutControl = (): void => {
  const button = document.querySelector<HTMLButtonElement>("#workbench-logout");
  if (button === null) {
    return;
  }
  button.addEventListener("click", () => {
    void (async () => {
      try {
        const response = await fetch(`${API_ROOT}/operator-sessions/current/revocations`, {
          method: "POST",
          headers: { Accept: "application/json" },
        });
        if (!response.ok && response.status !== 401) {
          throw new Error(`Logout failed: ${response.status}`);
        }
      } catch (error: unknown) {
        if (document.querySelector("#startup-auth-status") !== null) {
          setStatus(
            "#startup-auth-status",
            toErrorMessage(error, "Logout failed."),
            "error",
          );
        }
      } finally {
        invalidateSession("Session closed. Authenticate to unlock the workbench.");
      }
    })();
  });
  updateLogoutControl();
};

const initializeSessionWatchdog = (): void => {
  if (typeof window === "undefined" || typeof window.setInterval !== "function") {
    return;
  }
  window.setInterval(() => {
    if (authenticatedPrincipalId === null) {
      return;
    }
    void (async () => {
      try {
        if (!(await probeAuthenticatedSession())) {
          invalidateSession();
        }
      } catch {
        // Keep current UI state when probe transport fails.
      }
    })();
  }, 5000);
};

const setMethodStatus = (
  method: "bootstrap" | "totp",
  message: string,
  kind: StatusKind,
  visible: boolean = true,
): void => {
  const statusId = method === "totp" ? "totp-status" : "bootstrap-status";
  const status = document.querySelector<HTMLElement>(`#${statusId}`);
  if (status === null) return;
  if (!visible || message.length === 0) {
    status.hidden = true;
  } else {
    status.hidden = false;
    status.className = `auth-method-status notice--${kind}`;
    const span = status.querySelector<HTMLSpanElement>("span:last-of-type");
    if (span !== null) {
      span.textContent = message;
    }
  }
};

const setCredentialError = (
  input: HTMLInputElement,
  statusId: "bootstrap-status" | "totp-status",
  invalid: boolean,
): void => {
  if (invalid) {
    input.setAttribute("aria-invalid", "true");
    input.setAttribute("aria-errormessage", statusId);
    return;
  }
  input.removeAttribute("aria-invalid");
  input.removeAttribute("aria-errormessage");
};

const requireAuthenticatedSession = (): Promise<void> | void => {
  const sessionForm = document.querySelector<HTMLFormElement>("#startup-session-form");
  if (sessionForm === null) {
    markSessionGate(true);
    return;
  }

  return (async () => {
    markSessionGate(false);
    setMethodStatus("bootstrap", "Checking for an active local operator session.", "empty");
    setMethodStatus("totp", "Checking for an active local operator session.", "empty");
    try {
      if (await probeAuthenticatedSession()) {
        authenticatedPrincipalId ??= AUTHENTICATED_SESSION_SENTINEL;
        setMethodStatus("bootstrap", "Session ready. Workbench unlocked.", "ready");
        setMethodStatus("totp", "Session ready. Workbench unlocked.", "ready");
        markSessionGate(true);
        return;
      }

      const authMethodResponse = await fetch(`${API_ROOT}/auth-method`);
      if (!authMethodResponse.ok) {
        throw new Error(`Authentication method check failed: ${authMethodResponse.status}`);
      }
      const authMethodData = (await authMethodResponse.json()) as { method: string };
      const methodFieldset =
        authMethodData.method === "totp"
          ? document.querySelector<HTMLFieldSetElement>("#auth-method-totp")
          : document.querySelector<HTMLFieldSetElement>("#auth-method-bootstrap");
      if (methodFieldset !== null) {
        methodFieldset.hidden = false;
        const input = methodFieldset.querySelector<HTMLInputElement>("input");
        if (input !== null) {
          if (authMethodData.method === "totp" && input.name === "totp_code") {
            setMethodStatus("totp", "Enter your authenticator code to unlock.", "empty");
            const validateTotp = (): void => {
              const code = input.value.trim();
              if (code.length === 0) {
                setCredentialError(input, "totp-status", false);
                setMethodStatus("totp", "", "empty", false);
              } else if (!/^\d{6}$/.test(code)) {
                setCredentialError(input, "totp-status", true);
                setMethodStatus("totp", "Code must be 6 digits.", "error");
              } else {
                setCredentialError(input, "totp-status", false);
                setMethodStatus("totp", "Code ready to submit.", "ready");
              }
            };
            input.addEventListener("input", validateTotp);
            input.addEventListener("change", validateTotp);
          } else {
            setMethodStatus("bootstrap", "Enter the bootstrap shared secret to unlock.", "empty");
          }
        }
      }
    } catch (error: unknown) {
      setMethodStatus("bootstrap", toErrorMessage(error, "Session check failed. Authenticate to continue."), "error");
      setMethodStatus("totp", toErrorMessage(error, "Session check failed. Authenticate to continue."), "error");
    }

    await new Promise<void>((resolve) => {
      sessionForm.addEventListener("submit", (event) => {
        event.preventDefault();
        void (async () => {
          // Validate form before submission
          const bootstrapFieldset = document.querySelector<HTMLFieldSetElement>("#auth-method-bootstrap");
          const totpFieldset = document.querySelector<HTMLFieldSetElement>("#auth-method-totp");
          
          const sharedSecretInput = sessionForm.elements.namedItem("bootstrap_secret");
          const totpCodeInput = sessionForm.elements.namedItem("totp_code");

          if (sharedSecretInput instanceof HTMLInputElement) {
            setCredentialError(sharedSecretInput, "bootstrap-status", false);
          }
          if (totpCodeInput instanceof HTMLInputElement) {
            setCredentialError(totpCodeInput, "totp-status", false);
          }
          
          let validationError: string | null = null;
          
          // Determine which method should be active
          const totpActive = totpFieldset !== null && !totpFieldset.hidden;
          const bootstrapActive = bootstrapFieldset !== null && !bootstrapFieldset.hidden;
          
          if (totpActive && totpCodeInput instanceof HTMLInputElement) {
            const code = totpCodeInput.value.trim();
            if (code.length === 0) {
              validationError = "Enter your six-digit authenticator code.";
            } else if (!/^\d{6}$/.test(code)) {
              validationError = "Authenticator code must be exactly six digits.";
            }
          } else if (bootstrapActive && sharedSecretInput instanceof HTMLInputElement) {
            const secret = sharedSecretInput.value.trim();
            if (secret.length === 0) {
              validationError = "Enter the bootstrap shared secret.";
            }
          }
          
          if (validationError !== null) {
            let invalidInput: HTMLInputElement | null = null;
            let statusId: "bootstrap-status" | "totp-status";
            if (totpActive) {
              invalidInput = totpCodeInput instanceof HTMLInputElement ? totpCodeInput : null;
              statusId = "totp-status";
              setMethodStatus("totp", validationError, "error");
            } else if (bootstrapActive) {
              invalidInput = sharedSecretInput instanceof HTMLInputElement ? sharedSecretInput : null;
              statusId = "bootstrap-status";
              setMethodStatus("bootstrap", validationError, "error");
            } else {
              return;
            }
            if (invalidInput !== null) {
              setCredentialError(invalidInput, statusId, true);
              invalidInput.focus();
            }
            return;
          }
          
          try {
            if (totpActive) {
              setMethodStatus("totp", "Authenticating...", "empty");
            } else if (bootstrapActive) {
              setMethodStatus("bootstrap", "Authenticating...", "empty");
            }
            authenticatedPrincipalId = await establishSession(sessionForm);
            markSessionGate(true);
            setMethodStatus("bootstrap", "Session ready. Workbench unlocked.", "ready");
            setMethodStatus("totp", "Session ready. Workbench unlocked.", "ready");
            resolve();
          } catch (error: unknown) {
            const errorMessage = toErrorMessage(error, "Authentication failed. Please check your credential and try again.");
            if (totpActive) {
              setMethodStatus("totp", errorMessage, "error");
            } else if (bootstrapActive) {
              setMethodStatus("bootstrap", errorMessage, "error");
            }
          }
        })();
      });
    });
  })();
};

const isFlowFieldName = (value: string): value is FlowFieldName =>
  Object.hasOwn(FIELD_PRESENTATION, value);

const boundedFields = (template: ReturnFlowPolicyTemplate): readonly FlowFieldName[] => {
  const fields = template.fields;
  if (
    fields.length !== Object.keys(FIELD_PRESENTATION).length ||
    new Set(fields).size !== fields.length ||
    fields.some((field) => !isFlowFieldName(field))
  ) {
    throw new Error("Backend field contract is outside the bounded UI model.");
  }
  return fields as readonly FlowFieldName[];
};

const createFlowFields = (template: ReturnFlowPolicyTemplate): void => {
  const container = requiredElement<HTMLElement>("#flow-fields");
  const fields = boundedFields(template);
  container.replaceChildren();
  fields.forEach((name, index) => {
    const presentation = FIELD_PRESENTATION[name];
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
    input.name = name;
    input.type = "number";
    input.min = String(presentation.min);
    input.max = String(presentation.max);
    input.step = presentation.step;
    input.placeholder = presentation.placeholder;
    input.required = true;
    input.inputMode = "decimal";
    const unit = document.createElement("span");
    unit.textContent = presentation.unit;
    unit.setAttribute("aria-hidden", "true");
    control.append(input, unit);
    label.append(heading, hint, control);
    container.append(label);
  });
  requiredElement<HTMLElement>("#field-count").textContent =
    `${fields.length} bounded fields`;
};

const readNumber = (form: HTMLFormElement, name: FlowFieldName): number => {
  const input = form.elements.namedItem(name);
  if (!(input instanceof HTMLInputElement)) {
    throw new Error(`Required input is missing: ${name}`);
  }
  return input.valueAsNumber;
};

const writeNumber = (form: HTMLFormElement, name: FlowFieldName, value: number): void => {
  const input = form.elements.namedItem(name);
  if (!(input instanceof HTMLInputElement)) {
    throw new Error(`Required input is missing: ${name}`);
  }
  input.value = String(value);
};

const readInputs = (form: HTMLFormElement): FlowInputs => ({
  tank_volume_gallons: readNumber(form, "tank_volume_gallons"),
  pump_rated_flow_gph: readNumber(form, "pump_rated_flow_gph"),
  delivered_flow_gph: readNumber(form, "delivered_flow_gph"),
  minimum_turnover_per_hour: readNumber(form, "minimum_turnover_per_hour"),
});

const formatLogicalTree = (node: LogicalTreeNode, depth = 0): string => {
  const branch = depth === 0 ? "" : "└─ ";
  const state = node.state === null ? "" : `[${node.state}] `;
  const current = `${"  ".repeat(depth)}${branch}${state}${node.label}`;
  return [current, ...node.children.map((child) => formatLogicalTree(child, depth + 1))].join(
    "\n",
  );
};

const initializeCatalog = (catalog: InvariantCatalog): void => {
  const section = requiredElement<HTMLElement>("#rule-catalog");
  const selector = requiredElement<HTMLSelectElement>("#rule-template-selector");
  selector.replaceChildren();
  const templates = new Map<string, InvariantTemplate>();
  catalog.templates.forEach((template) => {
    if (templates.has(template.invariant_id)) {
      throw new Error(`Duplicate committed rule: ${template.invariant_id}`);
    }
    templates.set(template.invariant_id, template);
    const option = document.createElement("option");
    option.value = template.invariant_id;
    option.textContent = `${template.invariant_id} · ${template.title}`;
    selector.append(option);
  });
  if (templates.size === 0) {
    throw new Error("The committed rule catalog is empty.");
  }
  requiredElement<HTMLElement>("#catalog-summary").textContent =
    `${templates.size} backend-authored rules · schema ${catalog.schema_version}`;

  const renderSelected = (): void => {
    const template = templates.get(selector.value);
    if (template === undefined) {
      throw new Error(`Unknown committed rule: ${selector.value}`);
    }
    requiredElement<HTMLElement>("#rule-template-heading").textContent =
      `${template.invariant_id} v${template.version} — ${template.title}`;
    const severity = requiredElement<HTMLElement>("#rule-template-severity");
    severity.textContent = template.severity.toUpperCase();
    severity.dataset.severity = template.severity;
    requiredElement<HTMLElement>("#rule-tree").textContent = formatLogicalTree(
      template.logical_tree,
    );
  };
  selector.addEventListener("change", renderSelected);
  renderSelected();
  section.hidden = false;
};

const svgElement = <K extends keyof SVGElementTagNameMap>(
  name: K,
): SVGElementTagNameMap[K] => document.createElementNS(SVG_NAMESPACE, name);

const initializePhysicalTwin = (twin: PhysicalTwin): void => {
  const relationships = requiredElement<SVGGElement>("#physical-relationships");
  const entities = requiredElement<SVGGElement>("#physical-entities");
  const findings = requiredElement<HTMLElement>("#mock-findings");
  const facts = requiredElement<HTMLElement>("#physical-facts");
  relationships.replaceChildren();
  entities.replaceChildren();
  findings.replaceChildren();
  facts.replaceChildren();

  twin.relationships.forEach((relationship) => {
    const path = svgElement("path");
    path.classList.add("flow-path");
    path.setAttribute("d", relationship.svg_path);
    path.setAttribute("data-direction", relationship.direction);
    path.setAttribute("aria-label", `${relationship.label}. ${relationship.dependency}`);
    path.setAttribute("marker-end", "url(#flow-arrow)");
    relationships.append(path);
  });

  twin.entities.forEach((entity) => {
    const group = svgElement("g");
    group.classList.add("physical-entity", `physical-entity--${entity.physical_type}`);
    group.setAttribute("role", "group");
    group.setAttribute(
      "aria-label",
      `${entity.label}. Type ${entity.physical_type}. Quantity ${entity.quantity}. ` +
        `Elevation ${entity.elevation_inches} inches. Size ${entity.size.width_inches} by ` +
        `${entity.size.height_inches} by ${entity.size.depth_inches} inches.`,
    );
    const shape =
      entity.physical_type === "return_pump" ? svgElement("ellipse") : svgElement("rect");
    if (shape instanceof SVGEllipseElement) {
      shape.setAttribute("cx", String(entity.geometry.x + entity.geometry.width / 2));
      shape.setAttribute("cy", String(entity.geometry.y + entity.geometry.height / 2));
      shape.setAttribute("rx", String(entity.geometry.width / 2));
      shape.setAttribute("ry", String(entity.geometry.height / 2));
    } else {
      shape.setAttribute("x", String(entity.geometry.x));
      shape.setAttribute("y", String(entity.geometry.y));
      shape.setAttribute("width", String(entity.geometry.width));
      shape.setAttribute("height", String(entity.geometry.height));
      shape.setAttribute("rx", "12");
    }
    const label = svgElement("text");
    label.setAttribute("x", String(entity.geometry.x + entity.geometry.width / 2));
    label.setAttribute("y", String(entity.geometry.y + entity.geometry.height / 2));
    label.setAttribute("text-anchor", "middle");
    label.textContent = entity.label;
    group.append(shape, label);
    entities.append(group);

    const fact = document.createElement("p");
    fact.textContent =
      `${entity.label} · ${entity.quantity} × ${entity.physical_type.replaceAll("_", " ")} · ` +
      `${entity.size.width_inches} × ${entity.size.height_inches} × ` +
      `${entity.size.depth_inches} in · elevation ${entity.elevation_inches} in`;
    facts.append(fact);
  });

  twin.findings.forEach((finding) => {
    const article = document.createElement("article");
    article.className = `finding finding--${finding.severity}`;
    article.dataset.findingSeverity = finding.severity;
    const heading = document.createElement("h4");
    heading.textContent = `${finding.icon} ${finding.state_text}`;
    const summary = document.createElement("p");
    summary.textContent = finding.summary;
    article.append(heading, summary);
    findings.append(article);
  });

  requiredElement<HTMLElement>("#physical-twin").hidden = false;
};

const initializeSeverityFilters = (): void => {
  document
    .querySelectorAll<HTMLInputElement>("[data-severity-filter]")
    .forEach((filter) => {
      filter.addEventListener("change", () => {
        document
          .querySelectorAll<HTMLElement>("[data-finding-severity]")
          .forEach((finding) => {
            if (finding.dataset.findingSeverity === filter.dataset.severityFilter) {
              finding.hidden = !filter.checked;
            }
          });
      });
    });
};

const loadLatestRevision = async (): Promise<ReturnFlowPolicyRevision | null> => {
  const response = await fetch(`${API_ROOT}/policy-revisions/latest`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Latest saved revision failed: ${response.status}`);
  }
  const value: unknown = await response.json();
  if (value === null) {
    return null;
  }
  if (!isReturnFlowPolicyRevision(value)) {
    throw new Error(
      "Latest saved revision returned data outside the committed UI boundary.",
    );
  }
  return value;
};

const establishSession = async (form: HTMLFormElement): Promise<string> => {
  const sharedSecretInput = form.elements.namedItem("bootstrap_secret");
  const totpCodeInput = form.elements.namedItem("totp_code");
  const sharedSecret =
    sharedSecretInput instanceof HTMLInputElement ? sharedSecretInput.value.trim() : "";
  const totpCode =
    totpCodeInput instanceof HTMLInputElement ? totpCodeInput.value.trim() : "";
  if (sharedSecret.length === 0 && totpCode.length === 0) {
    throw new Error("Provide a valid authentication credential.");
  }
  const session = await requestJson("/operator-sessions", isOperatorSession, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bootstrap_secret: sharedSecret, totp_code: totpCode }),
  });
  if (sharedSecretInput instanceof HTMLInputElement) {
    sharedSecretInput.value = "";
  }
  if (totpCodeInput instanceof HTMLInputElement) {
    totpCodeInput.value = "";
  }
  return session.principal_id;
};

const saveFlowRevision = (
  form: HTMLFormElement,
  _principalId: string,
): Promise<ReturnFlowPolicyRevision> =>
  requestJson("/policy-revisions", isReturnFlowPolicyRevision, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(readInputs(form)),
  });

const setResult = (name: string, value: string): void => {
  requiredElement<HTMLElement>(`[data-result="${name}"]`).textContent = value;
};

const renderAssuranceRevision = (
  revision: ReturnFlowPolicyRevision,
  form: HTMLFormElement,
): void => {
  (Object.entries(revision.inputs) as [FlowFieldName, number][]).forEach(([name, value]) => {
    writeNumber(form, name, value);
  });
  setResult("revision", `Revision ${revision.revision_number} · ${revision.created_at}`);
  setResult("author-session", `Author session ${revision.authoring_operator_session_id}`);
  setResult("state", revision.preview.state);
  setResult("turnover", `${revision.preview.actual_turnover_per_hour}× / hr`);
  setResult("minimum-flow", `${revision.preview.minimum_delivered_flow_gph} GPH`);
  setResult("difference", `${revision.preview.delivery_difference_gph} GPH`);
  setResult("efficiency", `${revision.preview.delivery_efficiency_percent}%`);
  setResult("explanation", revision.preview.explanation);
  const preview = requiredElement<HTMLElement>("#preview");
  preview.dataset.state = revision.preview.state.toLowerCase();
  preview.hidden = false;
};

const setStatus = (
  selector: string,
  message: string,
  kind: StatusKind,
): void => {
  const status = requiredElement<HTMLElement>(selector);
  status.hidden = false;
  status.className = `notice notice--${kind}`;
  status.lastElementChild!.textContent = message;
};

const setEvidence = (name: string, value: string): void => {
  requiredElement<HTMLElement>(`[data-evidence="${name}"]`).textContent = value;
};

const renderEvidenceRevision = (revision: ReturnFlowPolicyRevision): void => {
  setEvidence("state", revision.preview.state);
  setEvidence("revision", `Revision ${revision.revision_number}`);
  setEvidence("created", revision.created_at);
  setEvidence("author-session", revision.authoring_operator_session_id);
  setEvidence("template", revision.policy_template_id);
  setEvidence("provenance", revision.provenance_label);
  setEvidence("revision-id", revision.revision_id);
  setEvidence("tank-volume", `${revision.inputs.tank_volume_gallons} gal`);
  setEvidence("pump-flow", `${revision.inputs.pump_rated_flow_gph} GPH`);
  setEvidence("delivered-flow", `${revision.inputs.delivered_flow_gph} GPH`);
  setEvidence(
    "minimum-turnover",
    `${revision.inputs.minimum_turnover_per_hour}× / hr`,
  );
  setEvidence("explanation", revision.preview.explanation);
  requiredElement<HTMLElement>("#evidence-revision-empty").hidden = true;
  requiredElement<HTMLElement>("#evidence-revision").hidden = false;
};

const renderTrustState = (state: TrustStateView): void => {
  const history = requiredElement<HTMLElement>("#trust-history");
  history.replaceChildren();
  if (state.events.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No trust events recorded. Canonical evidence remains trusted.";
    history.append(empty);
    return;
  }
  const activeIds = new Set(
    state.active_revocations.map((event) => event.trust_event_id),
  );
  state.events
    .slice()
    .reverse()
    .forEach((event) => {
      const article = document.createElement("article");
      const heading = document.createElement("h4");
      const active = activeIds.has(event.trust_event_id);
      heading.textContent =
        `${event.event_type === "revoked" ? "⊘ REVOKED" : "✓ RESTORED"} · ` +
        `${event.scope_kind} ${event.scope_id}${active ? " · ACTIVE" : ""}`;
      const detail = document.createElement("p");
      detail.textContent = `${event.rationale} · ${event.occurred_at}`;
      article.append(heading, detail);
      history.append(article);
    });
};

const loadTrust = (principalId: string): Promise<TrustStateView> =>
  requestProjectJson("/trust", principalId, isTrustStateView);

const initializeTrust = (): void => {
  const sessionForm = requiredElement<HTMLFormElement>("#trust-session-form");
  const controls = requiredElement<HTMLElement>("#trust-controls");
  const enrollment = requiredElement<HTMLElement>("#totp-enrollment");
  const qrImage = requiredElement<HTMLImageElement>("#totp-qr");
  let principalId: string | null = authenticatedPrincipalId;
  let challengeId: string | null = null;

  const refresh = async (): Promise<boolean> => {
    if (principalId === null) {
      return false;
    }
    renderTrustState(await loadTrust(principalId));
    const totp = await requestJson(
      "/totp",
      (value): value is { enrolled: boolean } =>
        isRecord(value) && isBoolean(value.enrolled),
    );
    requiredElement<HTMLElement>("#totp-enrollment-state").textContent =
      `Phone authenticator: ${totp.enrolled ? "ENROLLED" : "NOT ENROLLED"}`;
    requiredElement<HTMLButtonElement>("#totp-enroll").hidden = totp.enrolled;
    return totp.enrolled;
  };

  const beginEnrollment = async (): Promise<void> => {
    const response = await requestJson(
      "/totp/enrollment",
      (value): value is { challenge_id: string; qr_png_base64: string } =>
        isRecord(value) &&
        isString(value.challenge_id) &&
        isString(value.qr_png_base64),
      { method: "POST" },
    );
    challengeId = response.challenge_id;
    qrImage.src = `data:image/png;base64,${response.qr_png_base64}`;
    enrollment.hidden = false;
    setStatus(
      "#trust-status",
      "QR code loaded. Scan it with your authenticator app, then confirm with a six-digit code.",
      "ready",
    );
  };

  sessionForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void (async () => {
      try {
        principalId = authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL;
        controls.hidden = false;
        const totpEnrolled = await refresh();
        setStatus(
          "#trust-status",
          totpEnrolled
            ? "Trust history loaded from the backend."
            : "Trust history loaded. authenticator app is not enrolled yet; click Enroll authenticator app to reveal the QR code.",
          "ready",
        );
      } catch (error: unknown) {
        setStatus("#trust-status", toErrorMessage(error, "Trust history failed to load."), "error");
      }
    })();
  });

  if (principalId !== null) {
    controls.hidden = false;
    void (async () => {
      try {
        const totpEnrolled = await refresh();
        setStatus(
          "#trust-status",
          totpEnrolled
            ? "Trust history loaded from the backend."
            : "Trust history loaded. authenticator app is not enrolled yet; click Enroll authenticator app to reveal the QR code.",
          "ready",
        );
      } catch (error: unknown) {
        setStatus("#trust-status", toErrorMessage(error, "Trust history failed to load."), "error");
      }
    })();
  }

  requiredElement<HTMLButtonElement>("#totp-enroll").addEventListener("click", () => {
    void (async () => {
      try {
        await beginEnrollment();
      } catch (error: unknown) {
        setStatus("#trust-status", toErrorMessage(error, "authenticator app enrollment failed."), "error");
      }
    })();
  });

  requiredElement<HTMLFormElement>("#totp-confirm-form").addEventListener(
    "submit",
    (event) => {
      event.preventDefault();
      void (async () => {
        try {
          if (challengeId === null) {
            throw new Error("Start enrollment before confirming a authenticator code.");
          }
          const form = event.currentTarget as HTMLFormElement;
          const code = form.elements.namedItem("totp_code");
          const response = await fetch(`${API_ROOT}/totp/enrollment/confirm`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              challenge_id: challengeId,
              totp_code: code instanceof HTMLInputElement ? code.value : "",
            }),
          });
          if (!response.ok) {
            throw new Error(`authenticator app confirmation failed: ${response.status}`);
          }
          challengeId = null;
          qrImage.src = "";
          enrollment.hidden = true;
          await refresh();
          setStatus(
            "#trust-status",
            "Phone authenticator enrolled. Use a fresh six-digit code for revocations and restorations.",
            "ready",
          );
        } catch (error: unknown) {
          setStatus("#trust-status", toErrorMessage(error, "authenticator app confirmation failed."), "error");
        }
      })();
    },
  );

  requiredElement<HTMLFormElement>("#trust-revocation-form").addEventListener(
    "submit",
    (event) => {
      event.preventDefault();
      void (async () => {
        try {
          if (principalId === null) {
            return;
          }
          const form = event.currentTarget as HTMLFormElement;
          const data = new FormData(form);
          const state = await requestProjectJson(
            "/trust/revocations",
            principalId,
            isTrustStateView,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                scope_kind: data.get("scope_kind"),
                scope_id: data.get("scope_id"),
                rationale: data.get("rationale"),
                totp_code: data.get("totp_code"),
              }),
            },
          );
          renderTrustState(state);
          setStatus(
            "#trust-status",
            "Trust revoked. Affected projections are UNKNOWN and REVOKED.",
            "ready",
          );
          form.reset();
        } catch (error: unknown) {
          setStatus("#trust-status", toErrorMessage(error, "Trust revocation failed."), "error");
        }
      })();
    },
  );

  requiredElement<HTMLFormElement>("#trust-restoration-form").addEventListener(
    "submit",
    (event) => {
      event.preventDefault();
      void (async () => {
        try {
          if (principalId === null) {
            return;
          }
          const form = event.currentTarget as HTMLFormElement;
          const data = new FormData(form);
          const candidates = String(data.get("replacement_candidate_fact_ids") ?? "")
            .split(",")
            .map((value) => value.trim())
            .filter((value) => value.length > 0);
          const state = await requestProjectJson(
            "/trust/restorations",
            principalId,
            isTrustStateView,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                revocation_id: data.get("revocation_id"),
                rationale: data.get("rationale"),
                replacement_candidate_fact_ids: candidates,
                totp_code: data.get("totp_code"),
              }),
            },
          );
          renderTrustState(state);
          setStatus(
            "#trust-status",
            "Trust restored from complete fresh evidence and a new authenticator code.",
            "ready",
          );
          form.reset();
        } catch (error: unknown) {
          setStatus("#trust-status", toErrorMessage(error, "Trust restoration failed."), "error");
        }
      })();
    },
  );
};

const initializeAssurance = async (): Promise<void> => {
  const form = requiredElement<HTMLFormElement>("#flow-form");
  let sessionId: string | null = authenticatedPrincipalId;
  try {
    const template = await requestJson("/policy-template", isReturnFlowPolicyTemplate);
    createFlowFields(template);
    requiredElement<HTMLElement>("#policy-inputs").hidden = false;

    const latest = await loadLatestRevision();
    if (latest === null) {
      setStatus(
        "#loading-status",
        "Ready · No authored policy has been saved yet.",
        "empty",
      );
    } else {
      renderAssuranceRevision(latest, form);
      setStatus(
        "#loading-status",
        `Loaded saved revision ${latest.revision_number} from the backend.`,
        "ready",
      );
    }

    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void (async () => {
        try {
          sessionId ??= AUTHENTICATED_SESSION_SENTINEL;
          const revision = await saveFlowRevision(form, sessionId);
          renderAssuranceRevision(revision, form);
          setStatus(
            "#loading-status",
            `Saved revision ${revision.revision_number}.`,
            "ready",
          );
          requiredElement<HTMLElement>("#preview").scrollIntoView({
            behavior: "smooth",
            block: "start",
          });
        } catch (error: unknown) {
          setStatus(
            "#loading-status",
            error instanceof Error ? error.message : "Policy save failed.",
            "error",
          );
        }
      })();
    });
  } catch (error: unknown) {
    setStatus("#loading-status", toErrorMessage(error, "Assurance failed to load."), "error");
  }
};

const initializeEvidence = async (): Promise<void> => {
  try {
    const catalog = await requestJson("/invariant-catalog", isInvariantCatalog);
    initializeCatalog(catalog);
    const count = document.querySelector<HTMLElement>("#evidence-invariant-count");
    if (count !== null) {
      count.textContent = String(catalog.templates.length);
    }

    if (document.querySelector("#evidence-revision") !== null) {
      const latest = await loadLatestRevision();
      if (latest === null) {
        setStatus(
          "#evidence-status",
          "Catalog ready · No authored policy revision exists yet.",
          "empty",
        );
      } else {
        renderEvidenceRevision(latest);
        setStatus(
          "#evidence-status",
          `Evidence loaded · Revision ${latest.revision_number} and ` +
            `${catalog.templates.length} committed invariants.`,
          "ready",
        );
      }
    }
  } catch (error: unknown) {
    const status = document.querySelector("#evidence-status");
    if (status !== null) {
      setStatus("#evidence-status", toErrorMessage(error, "Evidence failed to load."), "error");
    }
  }
};

const initializeSystemMap = async (): Promise<void> => {
  try {
    const twin = await requestJson("/physical-twin", isPhysicalTwin);
    initializePhysicalTwin(twin);
    initializeSeverityFilters();
    if (document.querySelector("#system-map-status") !== null) {
      setStatus(
        "#system-map-status",
        `Model ready · ${twin.entities.length} authored physical entities.`,
        "ready",
      );
    }
  } catch (error: unknown) {
    if (document.querySelector("#system-map-status") !== null) {
      setStatus("#system-map-status", toErrorMessage(error, "System map failed to load."), "error");
    }
  }
};

const projectText = (name: string, value: string): void => {
  requiredElement<HTMLElement>(`[data-project="${name}"]`).textContent = value;
};

const renderProjectList = (name: string, values: readonly string[]): void => {
  const list = requiredElement<HTMLElement>(`[data-project-list="${name}"]`);
  list.replaceChildren();
  if (values.length === 0) {
    const item = document.createElement("li");
    item.textContent = "UNKNOWN · no structured records are available.";
    list.append(item);
    return;
  }
  values.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    list.append(item);
  });
};

const renderProjectBrief = (brief: ProjectBrief): void => {
  const recommendation = brief.recommended_next_action;
  projectText(
    "recommendation",
    recommendation.action === null
      ? "UNKNOWN · no deterministic action is currently selected."
      : `${recommendation.action.action_type.replaceAll("_", " ")} · ${recommendation.action.action_id}`,
  );
  projectText(
    "recommendation-reasons",
    `Reason codes: ${recommendation.reason_codes.join(", ")}`,
  );
  projectText(
    "posture",
    brief.current_posture.trust_status === "REVOKED"
      ? `⊘ UNKNOWN · REVOKED (evaluated ${brief.current_posture.evaluated_posture})`
      : brief.current_posture.posture,
  );
  projectText(
    "posture-reasons",
    `Reason codes: ${brief.current_posture.reason_codes.join(", ")} · ` +
      `Trust events: ${brief.current_posture.contributing_trust_event_ids.join(", ") || "none"}`,
  );
  renderProjectList(
    "risks",
    brief.highest_consequence_risks.map(
      (risk) => `${risk.risk_id} · severity ${risk.severity} · ${risk.reason_codes.join(", ")}`,
    ),
  );
  renderProjectList(
    "unknowns",
    brief.important_unknowns.map(
      (unknown) =>
        `${unknown.unknown_id} · impact ${unknown.impact} · ${unknown.reason_codes.join(", ")}`,
    ),
  );
  renderProjectList(
    "decisions",
    brief.recent_accepted_decisions.map(
      (decision) =>
        `${decision.subject_id}.${decision.attribute} = ${String(decision.accepted_value)} · ` +
        `${decision.accepted_at} · source ${decision.source_candidate_fact_id}`,
    ),
  );
  projectText(
    "continue-interview",
    brief.continue_interview.based_on_unknown_ids.length === 0
      ? "No structured unknown currently blocks the interview."
      : `${brief.continue_interview.based_on_unknown_ids.length} structured unknown(s) are ready.`,
  );
  requiredElement<HTMLElement>("#project-overview").hidden = false;
};

const electricalText = (name: string, value: string): void => {
  requiredElement<HTMLElement>(`[data-electrical="${name}"]`).textContent = value;
};

const renderElectricalPosture = (posture: ElectricalPosture): void => {
  electricalText("import-state", posture.import_state.toUpperCase());
  electricalText("headline", posture.headline);
  electricalText(
    "action",
    `${posture.recommended_action.label}. ${posture.recommended_action.description}`,
  );
  const action = requiredElement<HTMLAnchorElement>("[data-electrical-action]");
  action.href = posture.recommended_action.href;
  action.textContent = `${posture.recommended_action.label} →`;
  const counts = Object.entries(posture.entity_counts ?? {})
    .map(([name, count]) => `${count} ${name}`)
    .join(" · ");
  electricalText(
    "coverage",
    `${posture.observed_entity_count} imported entities${counts === "" ? "" : ` · ${counts}`}`,
  );
  electricalText(
    "freshness",
    posture.captured_at === null || posture.captured_at === undefined
      ? "No captured configuration timestamp."
      : `Captured ${posture.captured_at}`,
  );
  electricalText(
    "unknowns",
    `${posture.unknown_entity_count} unknown-confidence entities · ` +
      `${posture.unproven_domains.join(", ") || "no unproven domains reported"}`,
  );
  const categories = Object.entries(posture.redaction_categories ?? {})
    .map(([name, count]) => `${count} ${name.replaceAll("_", " ")}`)
    .join(" · ");
  electricalText(
    "redactions",
    `${posture.redacted_field_count} fields omitted${categories === "" ? "" : ` · ${categories}`}`,
  );
  requiredElement<HTMLElement>("#electrical-posture").hidden = false;
};

const initializeElectricalPosture = async (): Promise<void> => {
  const posture = await requestJson(
    "/electrical-posture",
    isElectricalPosture,
  );
  renderElectricalPosture(posture);
};

const renderInterviewSessions = (sessions: readonly InterviewSession[]): void => {
  const container = requiredElement<HTMLElement>("#interview-session-list");
  container.replaceChildren();
  if (sessions.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No durable interview sessions have been recorded.";
    container.append(empty);
    return;
  }
  sessions.forEach((session) => {
    const article = document.createElement("article");
    const heading = document.createElement("h3");
    heading.textContent = session.purpose;
    const summary = document.createElement("p");
    summary.textContent =
      `${session.initiated_at} · initiated by ${session.initiated_by_actor_id} · ` +
      `${session.candidate_facts.length} candidate(s) · ${session.decisions.length} decision(s)`;
    article.append(heading, summary);
    container.append(article);
  });
};

const renderCandidateReviews = (
  candidates: readonly StoredCandidate[],
  sessionId: string,
): void => {
  const container = requiredElement<HTMLElement>("#candidate-review-list");
  container.replaceChildren();
  if (candidates.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No candidate facts are waiting for review.";
    container.append(empty);
    return;
  }
  candidates.forEach((record) => {
    const article = document.createElement("article");
    article.dataset.candidateId = record.candidate.candidate_fact_id;
    const heading = document.createElement("h3");
    heading.textContent =
      `${record.candidate.subject_id}.${record.candidate.attribute}`;
    const value = document.createElement("p");
    value.textContent =
      `${String(record.candidate.proposed_value)} · proposed by ` +
      `${record.candidate.proposed_by_actor_id} · ${record.candidate.proposed_at}`;
    const status = document.createElement("p");
    status.textContent =
      record.decision == null
        ? "CANDIDATE · not canonical"
        : `${record.decision.decision.toUpperCase()} · ${record.decision.decided_at}`;
    article.append(heading, value, status);
    if (record.decision == null) {
      const rationale = document.createElement("textarea");
      rationale.rows = 3;
      rationale.placeholder = "Acceptance rationale";
      rationale.setAttribute("aria-label", `Rationale for ${record.candidate.candidate_fact_id}`);
      const actions = document.createElement("div");
      actions.className = "form-actions";
      (["accepted", "rejected"] as const).forEach((decision) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = decision === "accepted" ? "Accept fact" : "Reject candidate";
        button.addEventListener("click", () => {
          void (async () => {
            if (rationale.value.trim() === "") {
              setStatus("#project-status", "Acceptance rationale is required.", "error");
              rationale.focus();
              return;
            }
            try {
              await requestProjectJson(
                `/candidates/${record.candidate.candidate_fact_id}/review`,
                sessionId,
                isCandidateReviewResponse,
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ decision, rationale: rationale.value.trim() }),
                },
              );
              const refreshed = await requestProjectJson(
                "/candidates",
                sessionId,
                isStoredCandidates,
              );
              renderCandidateReviews(refreshed, sessionId);
              setStatus(
                "#project-status",
                `${record.candidate.candidate_fact_id} ${decision}.`,
                "ready",
              );
            } catch (error: unknown) {
              setStatus(
                "#project-status",
                toErrorMessage(error, "Candidate review failed."),
                "error",
              );
            }
          })();
        });
        actions.append(button);
      });
      article.append(rationale, actions);
    }
    container.append(article);
  });
};

const renderDatabaseColumns = (table: DatabaseTableSchema): void => {
  requiredElement<HTMLElement>("#database-table-heading").textContent = table.name;
  requiredElement<HTMLElement>("#database-table-summary").textContent =
    `${table.row_count} stored row(s) · ${table.columns.length} column(s) · ` +
    `${table.foreign_keys.length} foreign key(s) · ${table.indexes.length} index(es)`;
  const body = requiredElement<HTMLTableSectionElement>("#database-column-table tbody");
  body.replaceChildren();
  table.columns.forEach((column) => {
    const row = document.createElement("tr");
    const name = document.createElement("th");
    name.scope = "row";
    name.textContent = column.name;
    const declaredType = document.createElement("td");
    declaredType.textContent = column.declared_type || "UNDECLARED";
    const nullable = document.createElement("td");
    nullable.textContent = column.nullable ? "YES" : "NO";
    const defaultValue = document.createElement("td");
    defaultValue.textContent = column.default_value ?? "—";
    const key = document.createElement("td");
    key.textContent =
      column.primary_key_position > 0
        ? `PRIMARY ${column.primary_key_position}`
        : "—";
    row.append(name, declaredType, nullable, defaultValue, key);
    body.append(row);
  });

  const foreignKeys = requiredElement<HTMLElement>("#database-foreign-key-list");
  foreignKeys.replaceChildren();
  if (table.foreign_keys.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "No foreign keys";
    foreignKeys.append(empty);
  } else {
    table.foreign_keys.forEach((foreignKey) => {
      const item = document.createElement("li");
      item.textContent =
        `${foreignKey.from_column} → ${foreignKey.target_table}.` +
        `${foreignKey.target_column ?? "(rowid)"} · update ${foreignKey.on_update} · ` +
        `delete ${foreignKey.on_delete}`;
      foreignKeys.append(item);
    });
  }

  const indexes = requiredElement<HTMLElement>("#database-index-list");
  indexes.replaceChildren();
  if (table.indexes.length === 0) {
    const empty = document.createElement("li");
    empty.textContent = "No indexes";
    indexes.append(empty);
  } else {
    table.indexes.forEach((index) => {
      const item = document.createElement("li");
      item.textContent =
        `${index.name} · ${index.unique ? "UNIQUE" : "NON-UNIQUE"} · ` +
        `${index.columns.join(", ") || "(expression)"}`;
      indexes.append(item);
    });
  }
};

const renderDatabasePage = (page: DatabaseTablePage): void => {
  const head = requiredElement<HTMLTableSectionElement>("#database-row-table thead");
  const body = requiredElement<HTMLTableSectionElement>("#database-row-table tbody");
  head.replaceChildren();
  body.replaceChildren();

  const headingRow = document.createElement("tr");
  page.columns.forEach((column) => {
    const heading = document.createElement("th");
    heading.scope = "col";
    heading.textContent = column;
    headingRow.append(heading);
  });
  head.append(headingRow);

  page.rows.forEach((cells) => {
    const row = document.createElement("tr");
    cells.forEach((cell) => {
      const value = document.createElement("td");
      value.dataset.cellKind = cell.kind;
      if (cell.kind === "null") {
        value.textContent = "NULL";
      } else {
        value.textContent = `${String(cell.value)}${cell.truncated ? "…" : ""}`;
      }
      row.append(value);
    });
    body.append(row);
  });

  const caption = requiredElement<HTMLElement>("#database-row-caption");
  const first = page.total_rows === 0 ? 0 : page.offset + 1;
  const last = page.offset + page.rows.length;
  caption.textContent =
    `${page.table_name}: approved columns only, rows ${first}–${last} of ${page.total_rows}.`;
  requiredElement<HTMLElement>("#database-page-status").textContent =
    `${first}–${last} of ${page.total_rows}`;
  requiredElement<HTMLButtonElement>("#database-previous").disabled = page.offset === 0;
  requiredElement<HTMLButtonElement>("#database-next").disabled =
    page.next_offset === null;
};

const initializeDatabase = (): void => {
  const form = requiredElement<HTMLFormElement>("#database-session-form");
  let selectedTable: DatabaseTableSchema | null = null;
  let currentPage: DatabaseTablePage | null = null;

  const selectTable = async (
    table: DatabaseTableSchema,
    offset = 0,
  ): Promise<void> => {
    selectedTable = table;
    document.querySelectorAll<HTMLButtonElement>("[data-database-table]").forEach((button) => {
      button.setAttribute(
        "aria-current",
        String(button.dataset.databaseTable === table.name),
      );
    });
    renderDatabaseColumns(table);
    currentPage = await requestDatabaseJson(
      `/tables/${encodeURIComponent(table.name)}?offset=${offset}&limit=50`,
      isDatabaseTablePage,
    );
    renderDatabasePage(currentPage);
    setStatus(
      "#database-status",
      `${table.name} loaded through the query-only boundary.`,
      "ready",
    );
  };

  const loadExplorer = async (): Promise<void> => {
    const schema = await requestDatabaseJson("/schema", isDatabaseSchema);
    requiredElement<HTMLElement>("#database-revision").textContent =
      schema.alembic_revision;
    requiredElement<HTMLElement>("#database-integrity").textContent =
      schema.integrity.toUpperCase();
    const tableList = requiredElement<HTMLElement>("#database-table-list");
    tableList.replaceChildren();
    schema.tables.forEach((table) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.databaseTable = table.name;
      button.setAttribute("aria-current", "false");
      button.textContent = `${table.name} (${table.row_count})`;
      button.addEventListener("click", () => {
        void selectTable(table);
      });
      tableList.append(button);
    });
    requiredElement<HTMLElement>("#database-explorer").hidden = false;
    if (schema.tables.length === 0) {
      setStatus("#database-status", "No approved tables are present.", "empty");
      return;
    }
    const firstTable = schema.tables[0];
    if (firstTable !== undefined) {
      await selectTable(firstTable);
    }
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void (async () => {
      try {
        await loadExplorer();
      } catch (error: unknown) {
        setStatus("#database-status", toErrorMessage(error, "Database inspection failed."), "error");
      }
    })();
  });

  if (authenticatedPrincipalId !== null) {
    void (async () => {
      try {
        await loadExplorer();
      } catch (error: unknown) {
        setStatus("#database-status", toErrorMessage(error, "Database inspection failed."), "error");
      }
    })();
  }

  requiredElement<HTMLButtonElement>("#database-previous").addEventListener(
    "click",
    () => {
      if (selectedTable !== null && currentPage !== null) {
        void selectTable(
          selectedTable,
          Math.max(0, currentPage.offset - currentPage.limit),
        );
      }
    },
  );
  requiredElement<HTMLButtonElement>("#database-next").addEventListener(
    "click",
    () => {
      if (
        selectedTable !== null &&
        currentPage !== null &&
        currentPage.next_offset !== null
      ) {
        void selectTable(selectedTable, currentPage.next_offset);
      }
    },
  );
};

const initializeProjectSurface = (): void => {
  const form = requiredElement<HTMLFormElement>("#project-session-form");

  const loadProjectState = async (): Promise<void> => {
    const principalId = authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL;
    const page = document.body.dataset.workbenchPage;
    if (page === "overview") {
      const brief = await requestProjectJson("/brief", principalId, isProjectBrief);
      renderProjectBrief(brief);
      setStatus("#project-status", "Durable project brief loaded.", "ready");
    } else if (page === "sessions") {
      const [sessions, candidates] = await Promise.all([
        requestProjectJson("/sessions", principalId, isInterviewSessions),
        requestProjectJson("/candidates", principalId, isStoredCandidates),
      ]);
      renderInterviewSessions(sessions);
      renderCandidateReviews(candidates, principalId);
      requiredElement<HTMLElement>("#project-sessions").hidden = false;
      setStatus("#project-status", "Durable sessions and candidates loaded.", "ready");
    }
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void (async () => {
      try {
        await loadProjectState();
      } catch (error: unknown) {
        setStatus("#project-status", toErrorMessage(error, "Project state failed to load."), "error");
      }
    })();
  });

  if (authenticatedPrincipalId !== null) {
    void (async () => {
      try {
        await loadProjectState();
      } catch (error: unknown) {
        setStatus("#project-status", toErrorMessage(error, "Project state failed to load."), "error");
      }
    })();
  }
};

const initialize = async (): Promise<void> => {
  initializeLogoutControl();
  initializeSessionWatchdog();
  
  // Update system status badge (non-blocking)
  void updateSystemStatus();

  const authentication = requireAuthenticatedSession();
  if (authentication !== undefined) {
    await authentication;
  }

  // One registry keeps page wiring explicit and easy to extend.
  const initializersBySelector: readonly {
    selector: string;
    initialize: () => Promise<void> | void;
  }[] = [
    { selector: "#flow-form", initialize: initializeAssurance },
    { selector: "#rule-catalog", initialize: initializeEvidence },
    { selector: "#trust-session-form", initialize: initializeTrust },
    { selector: "#physical-twin", initialize: initializeSystemMap },
    { selector: "#electrical-posture", initialize: initializeElectricalPosture },
    { selector: "#project-session-form", initialize: initializeProjectSurface },
    { selector: "#database-session-form", initialize: initializeDatabase },
  ];

  const initializers: Promise<void>[] = [];
  for (const item of initializersBySelector) {
    if (document.querySelector(item.selector) === null) {
      continue;
    }
    const initialized = item.initialize();
    if (initialized instanceof Promise) {
      initializers.push(initialized);
    }
  }
  await Promise.all(initializers);
};

const redirectLegacyWorkbenchFragment = (): boolean => {
  if (typeof window === "undefined" || typeof window.location?.hash !== "string") {
    return false;
  }
  const route = new Map<string, string>([
    ["#policy-inputs", "/workbench/assurance"],
    ["#preview", "/workbench/assurance"],
    ["#evidence-heading", "/workbench/evidence"],
  ]).get(window.location.hash);
  if (
    route !== undefined &&
    document.body?.dataset.workbenchPage === "overview"
  ) {
    window.location.replace(route);
    return true;
  }
  return false;
};

if (!redirectLegacyWorkbenchFragment()) {
  void initialize();
}
