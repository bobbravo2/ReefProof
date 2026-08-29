import {
  defaultBrowserDependencies,
  type BrowserDependencies,
} from "./shared/browser-dependencies.js";
import {
  mountRegisteredPage,
  type PageController,
} from "./shared/page-registry.js";
import { mountSourcePage } from "./pages/source.js";
import { mountLabelsPage } from "./pages/labels.js";
import { mountCommissioningPage } from "./pages/commissioning.js";
import { mountOverviewPage } from "./pages/overview.js";
import { mountSessionsPage } from "./pages/sessions.js";
import { mountDatabasePage } from "./pages/database.js";
import { mountSystemMapPage } from "./pages/system-map.js";
import { mountAssurancePage } from "./pages/assurance.js";
import { mountEvidencePage } from "./pages/evidence.js";

const API_ROOT = "/v1/workbench";
const PROJECT_ID =
  document.documentElement?.dataset.projectId ?? "primary-reef-system";
const PROJECT_ROOT = `/v1/projects/${PROJECT_ID}`;
const AUTHENTICATED_SESSION_SENTINEL = "authenticated-session";
const SESSION_INVALIDATED_MESSAGE =
  "Session is no longer valid. Authenticate again to continue.";

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

let authenticatedPrincipalId: string | null = null;
let browserDependencies = defaultBrowserDependencies();

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

const isOperatorSession: Validator<OperatorSession> = (
  value,
): value is OperatorSession =>
  isRecord(value) &&
  isString(value.principal_id) &&
  value.principal_id.length > 0 &&
  isString(value.principal_display_name) &&
  value.principal_display_name.length > 0;

const toErrorMessage = (error: unknown, fallback: string): string =>
  error instanceof Error ? error.message : fallback;

const requestJsonFrom = async <T>(
  basePath: string,
  path: string,
  validator: Validator<T>,
  options?: RequestInit,
): Promise<T> => {
  const response = await browserDependencies.request(`${basePath}${path}`, {
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
  const response = await browserDependencies.request(`${API_ROOT}/totp`, {
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
    const response = await browserDependencies.request("/v1/system/status");
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
        const response = await browserDependencies.request(`${API_ROOT}/operator-sessions/current/revocations`, {
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

      const authMethodResponse = await browserDependencies.request(`${API_ROOT}/auth-method`);
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
          const response = await browserDependencies.request(`${API_ROOT}/totp/enrollment/confirm`, {
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

const initialize = async (): Promise<void> => {
  initializeLogoutControl();
  initializeSessionWatchdog();
  
  // Update system status badge (non-blocking)
  void updateSystemStatus();

  const authentication = requireAuthenticatedSession();
  if (authentication !== undefined) {
    await authentication;
  }

  const controllers: readonly PageController[] = [
    {
      page: "overview",
      mount: () =>
        mountOverviewPage({
          projectId: PROJECT_ID,
          requestWorkbench: requestJson,
          requestProject: <T>(path: string, validator: Validator<T>, options?: RequestInit) =>
            requestProjectJson(
              path,
              authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL,
              validator,
              options,
            ),
          requiredElement,
          setStatus,
          toErrorMessage,
        }),
    },
    {
      page: "assurance",
      mount: () =>
        mountAssurancePage({
          request: requestJson,
          requestOptional: <T>(path: string, validator: Validator<T>) =>
            requestJson(
              path,
              (value): value is T | null => value === null || validator(value),
            ),
          requiredElement,
          setStatus,
          toErrorMessage,
        }),
    },
    {
      page: "evidence",
      mount: () =>
        mountEvidencePage({
          request: requestJson,
          requestOptional: <T>(path: string, validator: Validator<T>) =>
            requestJson(
              path,
              (value): value is T | null => value === null || validator(value),
            ),
          requiredElement,
          setStatus,
          toErrorMessage,
          mountTrust: initializeTrust,
        }),
    },
    {
      page: "system-map",
      mount: () =>
        mountSystemMapPage({
          request: <T>(path: string, validator: Validator<T>, options?: RequestInit) =>
            requestProjectJson(
              path,
              authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL,
              validator,
              options,
            ),
          toErrorMessage,
        }),
    },
    {
      page: "source",
      mount: () =>
        mountSourcePage({
          request: <T>(path: string, validator: Validator<T>, options?: RequestInit) =>
            requestProjectJson(
              path,
              authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL,
              validator,
              options,
            ),
          requiredElement,
          toErrorMessage,
        }),
    },
    {
      page: "commissioning",
      mount: () =>
        mountCommissioningPage({
          request: <T>(path: string, validator: Validator<T>, options?: RequestInit) =>
            requestProjectJson(
              path,
              authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL,
              validator,
              options,
            ),
          requiredElement,
          toErrorMessage,
        }),
    },
    {
      page: "labels",
      mount: () =>
        mountLabelsPage({
          request: <T>(path: string, validator: Validator<T>, options?: RequestInit) =>
            requestProjectJson(
              path,
              authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL,
              validator,
              options,
            ),
          requiredElement,
          toErrorMessage,
        }),
    },
    {
      page: "sessions",
      mount: () =>
        mountSessionsPage({
          request: <T>(path: string, validator: Validator<T>, options?: RequestInit) =>
            requestProjectJson(
              path,
              authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL,
              validator,
              options,
            ),
          requiredElement,
          setStatus,
          toErrorMessage,
        }),
    },
    {
      page: "database",
      mount: () =>
        mountDatabasePage({
          request: requestDatabaseJson,
          requiredElement,
          setStatus,
          toErrorMessage,
        }),
    },
  ];
  const page = document.body?.dataset.workbenchPage;
  if (page !== undefined) {
    await mountRegisteredPage(page, controllers);
    return;
  }
  throw new Error("Workbench page identity is missing.");
};

export const mountWorkbench = async (
  dependencies: BrowserDependencies = defaultBrowserDependencies(),
): Promise<void> => {
  browserDependencies = dependencies;
  await initialize();
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
  void mountWorkbench();
}
