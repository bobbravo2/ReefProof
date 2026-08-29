import type { components } from "../workbench-contracts.js";

type InterviewSession = components["schemas"]["InterviewSession"];
type StoredCandidate = components["schemas"]["StoredCandidate"];
type CandidateReviewResponse = components["schemas"]["CandidateReviewResponse"];
type JsonRecord = Record<string, unknown>;
type Validator<T> = (value: unknown) => value is T;

export type SessionsPageServices = Readonly<{
  request: <T>(path: string, validator: Validator<T>, options?: RequestInit) => Promise<T>;
  requiredElement: <T extends Element>(selector: string) => T;
  setStatus: (selector: string, message: string, state: "ready" | "error") => void;
  toErrorMessage: (error: unknown, fallback: string) => string;
}>;

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isString = (value: unknown): value is string => typeof value === "string";
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

const renderInterviewSessions = (
  services: SessionsPageServices,
  sessions: readonly InterviewSession[],
): void => {
  const container = services.requiredElement<HTMLElement>("#interview-session-list");
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
  services: SessionsPageServices,
  candidates: readonly StoredCandidate[],
): void => {
  const container = services.requiredElement<HTMLElement>("#candidate-review-list");
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
    heading.textContent = `${record.candidate.subject_id}.${record.candidate.attribute}`;
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
              services.setStatus("#project-status", "Acceptance rationale is required.", "error");
              rationale.focus();
              return;
            }
            try {
              await services.request(
                `/candidates/${record.candidate.candidate_fact_id}/review`,
                isCandidateReviewResponse,
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ decision, rationale: rationale.value.trim() }),
                },
              );
              const refreshed = await services.request("/candidates", isStoredCandidates);
              renderCandidateReviews(services, refreshed);
              services.setStatus(
                "#project-status",
                `${record.candidate.candidate_fact_id} ${decision}.`,
                "ready",
              );
            } catch (error: unknown) {
              services.setStatus(
                "#project-status",
                services.toErrorMessage(error, "Candidate review failed."),
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

export const mountSessionsPage = async (services: SessionsPageServices): Promise<void> => {
  const load = async (): Promise<void> => {
    const [sessions, candidates] = await Promise.all([
      services.request("/sessions", isInterviewSessions),
      services.request("/candidates", isStoredCandidates),
    ]);
    renderInterviewSessions(services, sessions);
    renderCandidateReviews(services, candidates);
    services.requiredElement<HTMLElement>("#project-sessions").hidden = false;
    services.setStatus("#project-status", "Durable sessions and candidates loaded.", "ready");
  };
  services.requiredElement<HTMLFormElement>("#project-session-form").addEventListener(
    "submit",
    (event) => {
      event.preventDefault();
      void load().catch((error: unknown) => {
        services.setStatus(
          "#project-status",
          services.toErrorMessage(error, "Project state failed to load."),
          "error",
        );
      });
    },
  );
  await load();
};
