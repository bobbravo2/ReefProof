/* ReefProof Workbench bundle */
"use strict";
(() => {
  // src/reefproof/api/web/typescript/shared/browser-dependencies.ts
  var defaultBrowserDependencies = () => ({
    request: (input2, init) => globalThis.fetch(input2, init)
  });

  // src/reefproof/api/web/typescript/shared/page-registry.ts
  var mountRegisteredPage = async (page, controllers) => {
    const matching = controllers.filter((controller) => controller.page === page);
    if (matching.length !== 1) {
      throw new Error(`Expected one controller for Workbench page: ${page ?? "missing"}`);
    }
    await matching[0].mount();
  };

  // src/reefproof/api/web/typescript/pages/source.ts
  var isRecord = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
  var isString = (value) => typeof value === "string";
  var isBoolean = (value) => typeof value === "boolean";
  var isFiniteNumber = (value) => typeof value === "number" && Number.isFinite(value);
  var isStringNumberRecord = (value) => isRecord(value) && Object.values(value).every(isFiniteNumber);
  var isAuthoredSourceConfiguration = (value) => isRecord(value) && isString(value.source_configuration_id) && isString(value.project_id) && isString(value.source_alias) && isString(value.spreadsheet_id) && isString(value.configured_at) && isFiniteNumber(value.freshness_seconds);
  var isAuthoredSourceConfigurations = (value) => Array.isArray(value) && value.every(isAuthoredSourceConfiguration);
  var isAuthoredSourceStatus = (value) => isRecord(value) && ["NOT_CONFIGURED", "CURRENT", "STALE", "UNAVAILABLE", "CHANGED"].includes(
    String(value.health)
  ) && isString(value.detail) && (value.last_successful_fetch_at === void 0 || value.last_successful_fetch_at === null || isString(value.last_successful_fetch_at)) && (value.latest_snapshot_hash === void 0 || value.latest_snapshot_hash === null || isString(value.latest_snapshot_hash));
  var isAuthoredImportSummary = (value) => isRecord(value) && isString(value.import_batch_id) && isString(value.fetched_at) && isString(value.source_snapshot_hash) && isString(value.normalized_content_hash) && isBoolean(value.valid) && isStringNumberRecord(value.record_counts) && isFiniteNumber(value.diagnostic_count) && ["INVALID", "PENDING_REVIEW", "ACCEPTED", "REJECTED"].includes(
    String(value.review_status)
  );
  var isAuthoredImportSummaries = (value) => Array.isArray(value) && value.every(isAuthoredImportSummary);
  var isImportFactChange = (value) => isRecord(value) && isString(value.attribute) && (value.proposed_value === null || isString(value.proposed_value)) && ["NEW", "CHANGED", "UNCHANGED", "CONFLICT", "INVALID", "REMOVED_FROM_SOURCE"].includes(
    String(value.state)
  );
  var isImportObjectReview = (value) => isRecord(value) && isString(value.canonical_subject_id) && isString(value.external_namespace) && isString(value.external_id) && isString(value.tab) && (value.source_range === null || isString(value.source_range)) && Array.isArray(value.changes) && value.changes.every(isImportFactChange);
  var isAuthoredImportReview = (value) => isRecord(value) && isString(value.import_batch_id) && isString(value.source_snapshot_hash) && isBoolean(value.valid) && isStringNumberRecord(value.state_counts) && Array.isArray(value.objects) && value.objects.every(isImportObjectReview);
  var isAuthoredImportReviewResponse = (value) => isRecord(value) && isString(value.import_batch_id) && ["ACCEPTED", "REJECTED"].includes(String(value.decision)) && isFiniteNumber(value.reviewed_candidate_count) && isFiniteNumber(value.project_sequence);
  var mountSourcePage = async (services) => {
    const { request, requiredElement: requiredElement2, toErrorMessage: toErrorMessage2 } = services;
    const [configurations, status, imports] = await Promise.all([
      request("/authored-sources", isAuthoredSourceConfigurations),
      request("/authored-sources/google-sheets/status", isAuthoredSourceStatus),
      request("/imports", isAuthoredImportSummaries)
    ]);
    requiredElement2("#source-health").textContent = status.health;
    requiredElement2("#source-status").textContent = status.detail;
    requiredElement2("#source-fetched-at").textContent = status.last_successful_fetch_at ?? "Never";
    requiredElement2("#source-snapshot-hash").textContent = status.latest_snapshot_hash ?? "None";
    requiredElement2("#source-workbook").textContent = configurations.length === 0 ? "Not configured" : `${configurations[0].source_alias} \xB7 ${configurations[0].spreadsheet_id}`;
    const list = requiredElement2("#source-imports");
    list.replaceChildren();
    const openReview = async (batchId) => {
      const review = await request(
        `/imports/${encodeURIComponent(batchId)}`,
        isAuthoredImportReview
      );
      requiredElement2("#source-review").hidden = false;
      requiredElement2("#source-review-summary").textContent = Object.entries(
        review.state_counts
      ).map(([stateName, count]) => `${stateName}: ${count}`).join(" \xB7 ");
      requiredElement2("#source-review-objects").replaceChildren(
        ...review.objects.map((item) => {
          const article = document.createElement("article");
          const heading = document.createElement("strong");
          heading.textContent = `${item.state} \xB7 ${item.tab} \xB7 ${item.external_id}`;
          const detail = document.createElement("p");
          detail.textContent = `${item.canonical_subject_id} \xB7 ${item.source_range ?? "historical source"}`;
          article.append(heading, detail);
          return article;
        })
      );
      requiredElement2(
        "#source-review-form input[name='import_batch_id']"
      ).value = batchId;
    };
    if (imports.length === 0) {
      const empty = document.createElement("p");
      empty.textContent = "No source import has been loaded. Fetch the read-only source after validation.";
      list.append(empty);
    } else {
      list.append(
        ...imports.map((item) => {
          const article = document.createElement("article");
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = `${item.review_status} \xB7 ${item.import_batch_id}`;
          button.addEventListener("click", () => void openReview(item.import_batch_id));
          const detail = document.createElement("p");
          const tabCounts = Object.entries(item.record_counts).map(([tab, count]) => `${tab}: ${count}`).join(" \xB7 ");
          detail.textContent = `${tabCounts} \xB7 ${item.diagnostic_count} diagnostics \xB7 ${item.fetched_at}`;
          article.append(button, detail);
          return article;
        })
      );
    }
    requiredElement2("#source-sync").addEventListener("click", () => {
      void (async () => {
        try {
          const synced = await request(
            "/authored-sources/google-sheets/sync",
            isAuthoredImportSummary,
            { method: "POST" }
          );
          requiredElement2("#source-status").textContent = `${synced.review_status} \xB7 ${synced.import_batch_id} \xB7 reload to review.`;
        } catch (error) {
          requiredElement2("#source-status").textContent = toErrorMessage2(
            error,
            "Source fetch failed; retained accepted evidence is unchanged."
          );
        }
      })();
    });
    const form = requiredElement2("#source-review-form");
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
                totp_code: String(data.get("totp_code") ?? "")
              })
            }
          );
          requiredElement2("#source-review-status").textContent = `${response.decision}: ${response.reviewed_candidate_count} candidates reviewed at project sequence ${response.project_sequence}.`;
          form.querySelectorAll("input, select").forEach((control) => {
            control.disabled = true;
          });
        } catch (error) {
          requiredElement2("#source-review-status").textContent = toErrorMessage2(
            error,
            "Import review failed."
          );
        }
      })();
    });
  };

  // src/reefproof/api/web/typescript/pages/labels.ts
  var isRecord2 = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
  var isString2 = (value) => typeof value === "string";
  var isFiniteNumber2 = (value) => typeof value === "number" && Number.isFinite(value);
  var isLabelRecord = (value) => isRecord2(value) && ["DEVICE", "PORT", "CABLE", "POWER SUPPLY"].includes(String(value.label_kind)) && isString2(value.label_id) && isString2(value.display_id) && isString2(value.primary_text) && isFiniteNumber2(value.copies);
  var isLabelManifest = (value) => isRecord2(value) && isString2(value.manifest_id) && isString2(value.project_id) && isString2(value.project_name) && isFiniteNumber2(value.source_project_sequence) && Array.isArray(value.records) && value.records.every(isLabelRecord);
  var isCommissioningVerification = (value) => isRecord2(value) && isString2(value.verification_id) && isString2(value.device_id) && ["POWER", "COMMUNICATIONS", "FAULT_TEST", "LABEL"].includes(String(value.kind)) && ["PASS", "FAIL", "NOT_APPLICABLE"].includes(String(value.outcome));
  var mountLabelsPage = async (services) => {
    const { request, requiredElement: requiredElement2, toErrorMessage: toErrorMessage2 } = services;
    const manifest = await request("/labels", isLabelManifest);
    requiredElement2("#labels-status").textContent = `${manifest.project_name} \xB7 ${manifest.records.length} labels \xB7 sequence ${manifest.source_project_sequence}`;
    requiredElement2("#label-records").replaceChildren(
      ...manifest.records.map((record) => {
        const article = document.createElement("article");
        const heading = document.createElement("strong");
        heading.textContent = `${record.label_kind} \xB7 ${record.display_id} \xB7 ${record.copies} cop${record.copies === 1 ? "y" : "ies"}`;
        const body = document.createElement("pre");
        body.textContent = [record.primary_text, record.secondary_text].filter(Boolean).join("\n");
        article.append(heading, body);
        return article;
      })
    );
    requiredElement2(
      "#label-verification-form input[name='manifest_id']"
    ).value = manifest.manifest_id;
    const form = requiredElement2("#label-verification-form");
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
                totp_code: String(data.get("totp_code") ?? "")
              })
            }
          );
          requiredElement2("#label-verification-status").textContent = `Recorded ${verification.outcome} for ${verification.label_id ?? "label"}.`;
        } catch (error) {
          requiredElement2("#label-verification-status").textContent = toErrorMessage2(error, "Label verification failed.");
        }
      })();
    });
  };

  // src/reefproof/api/web/typescript/pages/commissioning.ts
  var isRecord3 = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
  var isString3 = (value) => typeof value === "string";
  var isFiniteNumber3 = (value) => typeof value === "number" && Number.isFinite(value);
  var isStringArray = (value) => Array.isArray(value) && value.every(isString3);
  var isCommissioningRequirement = (value) => isRecord3(value) && isString3(value.requirement_id) && isString3(value.label) && ["PASS", "FAIL", "UNKNOWN"].includes(String(value.state)) && isString3(value.detail) && isStringArray(value.evidence_ids);
  var isCommissioningDevice = (value) => isRecord3(value) && isString3(value.device_id) && isString3(value.canonical_device_id) && isString3(value.display_name) && ["NOT_STARTED", "IN_PROGRESS", "BLOCKED", "COMMISSIONED", "REVOKED"].includes(
    String(value.state)
  ) && Array.isArray(value.requirements) && value.requirements.every(isCommissioningRequirement);
  var isCommissioningProjection = (value) => isRecord3(value) && isString3(value.project_id) && Array.isArray(value.devices) && value.devices.every(isCommissioningDevice) && isFiniteNumber3(value.commissioned_count) && isFiniteNumber3(value.blocked_count) && isFiniteNumber3(value.unknown_requirement_count);
  var isCommissioningVerification2 = (value) => isRecord3(value) && isString3(value.verification_id) && isString3(value.device_id) && ["CONNECTION", "POWER", "COMMUNICATIONS", "FAULT_TEST", "LABEL"].includes(
    String(value.kind)
  ) && ["PASS", "FAIL", "NOT_APPLICABLE"].includes(String(value.outcome));
  var isFailureModeDisposition = (value) => isRecord3(value) && isString3(value.disposition_id) && isString3(value.device_id) && isString3(value.failure_mode_id) && ["ACCEPTED_RISK", "ALERTED_DETECTED", "AUTOMATED_MITIGATION"].includes(
    String(value.disposition)
  );
  var mountCommissioningPage = async (services) => {
    const { request, requiredElement: requiredElement2, toErrorMessage: toErrorMessage2 } = services;
    const loadProjection = async () => {
      const projection = await request("/commissioning", isCommissioningProjection);
      requiredElement2("#commissioning-status").textContent = `${projection.commissioned_count} commissioned \xB7 ${projection.blocked_count} blocked \xB7 ${projection.unknown_requirement_count} unknown requirements`;
      requiredElement2("#commissioning-devices").replaceChildren(
        ...projection.devices.map((device) => {
          const article = document.createElement("article");
          const heading = document.createElement("h3");
          heading.textContent = `${device.state} \xB7 ${device.display_name}`;
          const identity = document.createElement("code");
          identity.textContent = device.canonical_device_id;
          const list = document.createElement("ul");
          list.append(
            ...device.requirements.map((requirement) => {
              const item = document.createElement("li");
              item.textContent = `${requirement.state} \xB7 ${requirement.label}: ${requirement.detail}`;
              return item;
            })
          );
          article.append(heading, identity, list);
          return article;
        })
      );
    };
    await loadProjection();
    const verificationForm = requiredElement2(
      "#commissioning-verification-form"
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
            isCommissioningVerification2,
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
                totp_code: String(data.get("totp_code") ?? "")
              })
            }
          );
          requiredElement2("#commissioning-action-status").textContent = `Recorded ${verification.kind} ${verification.outcome}.`;
          await loadProjection();
        } catch (error) {
          requiredElement2("#commissioning-action-status").textContent = toErrorMessage2(error, "Commissioning verification failed.");
        }
      })();
    });
    const dispositionForm = requiredElement2("#failure-mode-form");
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
                totp_code: String(data.get("totp_code") ?? "")
              })
            }
          );
          requiredElement2("#failure-mode-status").textContent = `Recorded ${disposition.failure_mode_id}: ${disposition.disposition}.`;
          await loadProjection();
        } catch (error) {
          requiredElement2("#failure-mode-status").textContent = toErrorMessage2(error, "Failure-mode disposition failed.");
        }
      })();
    });
  };

  // src/reefproof/api/web/typescript/shared/reconciliation.ts
  var isRecord4 = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
  var isString4 = (value) => typeof value === "string";
  var isFiniteNumber4 = (value) => typeof value === "number" && Number.isFinite(value);
  var isReconciliationItem = (value) => isRecord4(value) && isString4(value.reconciliation_id) && ["MATCHED", "AUTHORED_ONLY", "OBSERVED_ONLY", "CONFLICT"].includes(
    String(value.state)
  ) && (value.canonical_subject_id === null || isString4(value.canonical_subject_id)) && (value.authored_display_id === null || isString4(value.authored_display_id)) && (value.observed_entity_id === null || isString4(value.observed_entity_id)) && (value.observed_vendor_id === null || isString4(value.observed_vendor_id)) && (value.observed_display_name === null || isString4(value.observed_display_name)) && isString4(value.detail);
  var isReconciliationProjection = (value) => isRecord4(value) && isString4(value.project_id) && (value.observed_snapshot_hash === null || isString4(value.observed_snapshot_hash)) && (value.observed_captured_at === null || isString4(value.observed_captured_at)) && Array.isArray(value.items) && value.items.every(isReconciliationItem) && isFiniteNumber4(value.matched_count) && isFiniteNumber4(value.authored_only_count) && isFiniteNumber4(value.observed_only_count) && isFiniteNumber4(value.conflict_count);
  var renderReconciliation = (projection) => {
    const status = document.querySelector("#reconciliation-status");
    const items = document.querySelector("#reconciliation-items");
    if (status === null || items === null) return;
    status.textContent = `${projection.matched_count} matched \xB7 ${projection.authored_only_count} authored only \xB7 ${projection.observed_only_count} observed only \xB7 ${projection.conflict_count} conflicts`;
    status.className = `notice notice--${projection.conflict_count > 0 ? "error" : "ready"}`;
    items.replaceChildren();
    if (projection.items.length === 0) {
      const empty = document.createElement("p");
      empty.textContent = "No accepted authored devices or observed configuration evidence are available.";
      items.append(empty);
      return;
    }
    items.append(
      ...projection.items.map((item) => {
        const article = document.createElement("article");
        const heading = document.createElement("strong");
        heading.textContent = `${item.state} \xB7 ${item.authored_display_id ?? item.observed_display_name ?? item.observed_entity_id ?? "unknown"}`;
        const identity = document.createElement("code");
        identity.textContent = [item.canonical_subject_id, item.observed_entity_id].filter(Boolean).join(" \u2194 ");
        const detail = document.createElement("p");
        detail.textContent = item.detail;
        article.append(heading, identity, detail);
        return article;
      })
    );
  };
  var mountReconciliation = async (services) => {
    const projection = await services.request("/reconciliation", isReconciliationProjection);
    renderReconciliation(projection);
    const form = document.querySelector("#reconciliation-binding-form");
    if (form === null) return;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void (async () => {
        const data = new FormData(form);
        const status = document.querySelector("#reconciliation-binding-status");
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
                totp_code: String(data.get("totp_code") ?? "")
              })
            }
          );
          renderReconciliation(updated);
          if (status !== null) status.textContent = "Explicit observed identity binding recorded.";
        } catch (error) {
          if (status !== null) {
            status.textContent = services.toErrorMessage(
              error,
              "Observed identity binding failed."
            );
          }
        }
      })();
    });
  };

  // src/reefproof/api/web/typescript/pages/overview.ts
  var isRecord5 = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
  var isString5 = (value) => typeof value === "string";
  var isFiniteNumber5 = (value) => typeof value === "number" && Number.isFinite(value);
  var isStringArray2 = (value) => Array.isArray(value) && value.every(isString5);
  var projectBriefValidator = (projectId) => (value) => isRecord5(value) && value.project_id === projectId && isRecord5(value.recommended_next_action) && ["SELECTED", "UNKNOWN"].includes(String(value.recommended_next_action.status)) && isRecord5(value.current_posture) && ["commissioning", "operational", "UNKNOWN"].includes(
    String(value.current_posture.posture)
  ) && ["commissioning", "operational", "UNKNOWN"].includes(
    String(value.current_posture.evaluated_posture)
  ) && ["TRUSTED", "REVOKED"].includes(String(value.current_posture.trust_status)) && isStringArray2(value.current_posture.contributing_trust_event_ids) && Array.isArray(value.highest_consequence_risks) && Array.isArray(value.important_unknowns) && Array.isArray(value.recent_accepted_decisions) && isRecord5(value.continue_interview);
  var electricalPostureValidator = (projectId) => (value) => isRecord5(value) && value.project_id === projectId && ["empty", "partial"].includes(String(value.import_state)) && isString5(value.headline) && isRecord5(value.recommended_action) && isString5(value.recommended_action.id) && isString5(value.recommended_action.label) && isString5(value.recommended_action.description) && isString5(value.recommended_action.href) && isFiniteNumber5(value.observed_entity_count) && isRecord5(value.entity_counts) && Object.values(value.entity_counts).every(isFiniteNumber5) && isFiniteNumber5(value.unknown_entity_count) && isFiniteNumber5(value.redacted_field_count) && isRecord5(value.redaction_categories) && Object.values(value.redaction_categories).every(isFiniteNumber5) && isStringArray2(value.unproven_domains);
  var renderProjectList = (services, name, values) => {
    const list = services.requiredElement(`[data-project-list="${name}"]`);
    list.replaceChildren();
    const rendered = values.length === 0 ? ["UNKNOWN \xB7 no structured records are available."] : values;
    rendered.forEach((value) => {
      const item = document.createElement("li");
      item.textContent = value;
      list.append(item);
    });
  };
  var renderProjectBrief = (services, brief) => {
    const text = (name, value) => {
      services.requiredElement(`[data-project="${name}"]`).textContent = value;
    };
    const recommendation = brief.recommended_next_action;
    text(
      "recommendation",
      recommendation.action === null ? "UNKNOWN \xB7 no deterministic action is currently selected." : `${recommendation.action.action_type.replaceAll("_", " ")} \xB7 ${recommendation.action.action_id}`
    );
    text("recommendation-reasons", `Reason codes: ${recommendation.reason_codes.join(", ")}`);
    text(
      "posture",
      brief.current_posture.trust_status === "REVOKED" ? `\u2298 UNKNOWN \xB7 REVOKED (evaluated ${brief.current_posture.evaluated_posture})` : brief.current_posture.posture
    );
    text(
      "posture-reasons",
      `Reason codes: ${brief.current_posture.reason_codes.join(", ")} \xB7 Trust events: ${brief.current_posture.contributing_trust_event_ids.join(", ") || "none"}`
    );
    renderProjectList(
      services,
      "risks",
      brief.highest_consequence_risks.map(
        (risk) => `${risk.risk_id} \xB7 severity ${risk.severity} \xB7 ${risk.reason_codes.join(", ")}`
      )
    );
    renderProjectList(
      services,
      "unknowns",
      brief.important_unknowns.map(
        (unknown) => `${unknown.unknown_id} \xB7 impact ${unknown.impact} \xB7 ${unknown.reason_codes.join(", ")}`
      )
    );
    renderProjectList(
      services,
      "decisions",
      brief.recent_accepted_decisions.map(
        (decision) => `${decision.subject_id}.${decision.attribute} = ${String(decision.accepted_value)} \xB7 ${decision.accepted_at} \xB7 source ${decision.source_candidate_fact_id}`
      )
    );
    text(
      "continue-interview",
      brief.continue_interview.based_on_unknown_ids.length === 0 ? "No structured unknown currently blocks the interview." : `${brief.continue_interview.based_on_unknown_ids.length} structured unknown(s) are ready.`
    );
    services.requiredElement("#project-overview").hidden = false;
  };
  var renderElectricalPosture = (services, posture) => {
    const text = (name, value) => {
      services.requiredElement(`[data-electrical="${name}"]`).textContent = value;
    };
    text("import-state", posture.import_state.toUpperCase());
    text("headline", posture.headline);
    text(
      "action",
      `${posture.recommended_action.label}. ${posture.recommended_action.description}`
    );
    const action = services.requiredElement("[data-electrical-action]");
    action.href = posture.recommended_action.href;
    action.textContent = `${posture.recommended_action.label} \u2192`;
    const counts = Object.entries(posture.entity_counts ?? {}).map(([name, count]) => `${count} ${name}`).join(" \xB7 ");
    text(
      "coverage",
      `${posture.observed_entity_count} imported entities${counts === "" ? "" : ` \xB7 ${counts}`}`
    );
    text(
      "freshness",
      posture.captured_at === null || posture.captured_at === void 0 ? "No captured configuration timestamp." : `Captured ${posture.captured_at}`
    );
    text(
      "unknowns",
      `${posture.unknown_entity_count} unknown-confidence entities \xB7 ${posture.unproven_domains.join(", ") || "no unproven domains reported"}`
    );
    const categories = Object.entries(posture.redaction_categories ?? {}).map(([name, count]) => `${count} ${name.replaceAll("_", " ")}`).join(" \xB7 ");
    text(
      "redactions",
      `${posture.redacted_field_count} fields omitted${categories === "" ? "" : ` \xB7 ${categories}`}`
    );
    services.requiredElement("#electrical-posture").hidden = false;
  };
  var mountOverviewPage = async (services) => {
    const loadProjectBrief = async () => {
      const brief2 = await services.requestProject("/brief", projectBriefValidator(services.projectId));
      renderProjectBrief(services, brief2);
      services.setStatus("#project-status", "Durable project brief loaded.", "ready");
    };
    services.requiredElement("#project-session-form").addEventListener(
      "submit",
      (event) => {
        event.preventDefault();
        void loadProjectBrief().catch((error) => {
          services.setStatus(
            "#project-status",
            services.toErrorMessage(error, "Project state failed to load."),
            "error"
          );
        });
      }
    );
    const [electrical, brief] = await Promise.all([
      services.requestWorkbench(
        "/electrical-posture",
        electricalPostureValidator(services.projectId)
      ),
      services.requestProject("/brief", projectBriefValidator(services.projectId)),
      mountReconciliation({
        request: services.requestProject,
        toErrorMessage: services.toErrorMessage
      })
    ]);
    renderElectricalPosture(services, electrical);
    renderProjectBrief(services, brief);
    services.setStatus("#project-status", "Durable project brief loaded.", "ready");
  };

  // src/reefproof/api/web/typescript/pages/sessions.ts
  var isRecord6 = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
  var isString6 = (value) => typeof value === "string";
  var isInterviewSessions = (value) => Array.isArray(value) && value.every(
    (session) => isRecord6(session) && isString6(session.session_id) && isString6(session.initiated_by_actor_id) && isString6(session.initiated_at) && isString6(session.purpose)
  );
  var isStoredCandidates = (value) => Array.isArray(value) && value.every(
    (record) => isRecord6(record) && isString6(record.session_id) && isRecord6(record.candidate) && isString6(record.candidate.candidate_fact_id) && isString6(record.candidate.subject_id) && isString6(record.candidate.attribute) && (record.decision === null || isRecord6(record.decision))
  );
  var isCandidateReviewResponse = (value) => isRecord6(value) && isRecord6(value.candidate) && isRecord6(value.decision) && ["accepted", "rejected"].includes(String(value.decision.decision)) && isRecord6(value.canonical_state);
  var renderInterviewSessions = (services, sessions) => {
    const container = services.requiredElement("#interview-session-list");
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
      summary.textContent = `${session.initiated_at} \xB7 initiated by ${session.initiated_by_actor_id} \xB7 ${session.candidate_facts.length} candidate(s) \xB7 ${session.decisions.length} decision(s)`;
      article.append(heading, summary);
      container.append(article);
    });
  };
  var renderCandidateReviews = (services, candidates) => {
    const container = services.requiredElement("#candidate-review-list");
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
      value.textContent = `${String(record.candidate.proposed_value)} \xB7 proposed by ${record.candidate.proposed_by_actor_id} \xB7 ${record.candidate.proposed_at}`;
      const status = document.createElement("p");
      status.textContent = record.decision == null ? "CANDIDATE \xB7 not canonical" : `${record.decision.decision.toUpperCase()} \xB7 ${record.decision.decided_at}`;
      article.append(heading, value, status);
      if (record.decision == null) {
        const rationale = document.createElement("textarea");
        rationale.rows = 3;
        rationale.placeholder = "Acceptance rationale";
        rationale.setAttribute("aria-label", `Rationale for ${record.candidate.candidate_fact_id}`);
        const actions = document.createElement("div");
        actions.className = "form-actions";
        ["accepted", "rejected"].forEach((decision) => {
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
                    body: JSON.stringify({ decision, rationale: rationale.value.trim() })
                  }
                );
                const refreshed = await services.request("/candidates", isStoredCandidates);
                renderCandidateReviews(services, refreshed);
                services.setStatus(
                  "#project-status",
                  `${record.candidate.candidate_fact_id} ${decision}.`,
                  "ready"
                );
              } catch (error) {
                services.setStatus(
                  "#project-status",
                  services.toErrorMessage(error, "Candidate review failed."),
                  "error"
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
  var mountSessionsPage = async (services) => {
    const load = async () => {
      const [sessions, candidates] = await Promise.all([
        services.request("/sessions", isInterviewSessions),
        services.request("/candidates", isStoredCandidates)
      ]);
      renderInterviewSessions(services, sessions);
      renderCandidateReviews(services, candidates);
      services.requiredElement("#project-sessions").hidden = false;
      services.setStatus("#project-status", "Durable sessions and candidates loaded.", "ready");
    };
    services.requiredElement("#project-session-form").addEventListener(
      "submit",
      (event) => {
        event.preventDefault();
        void load().catch((error) => {
          services.setStatus(
            "#project-status",
            services.toErrorMessage(error, "Project state failed to load."),
            "error"
          );
        });
      }
    );
    await load();
  };

  // src/reefproof/api/web/typescript/pages/database.ts
  var isRecord7 = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
  var isString7 = (value) => typeof value === "string";
  var isBoolean2 = (value) => typeof value === "boolean";
  var isFiniteNumber6 = (value) => typeof value === "number" && Number.isFinite(value);
  var isStringArray3 = (value) => Array.isArray(value) && value.every(isString7);
  var isDatabaseColumn = (value) => isRecord7(value) && isFiniteNumber6(value.position) && isString7(value.name) && isString7(value.declared_type) && isBoolean2(value.nullable) && (value.default_value === null || isString7(value.default_value)) && isFiniteNumber6(value.primary_key_position);
  var isDatabaseTableSchema = (value) => isRecord7(value) && isString7(value.name) && isFiniteNumber6(value.row_count) && Array.isArray(value.columns) && value.columns.length > 0 && value.columns.every(isDatabaseColumn) && Array.isArray(value.foreign_keys) && value.foreign_keys.every(
    (foreignKey) => isRecord7(foreignKey) && isFiniteNumber6(foreignKey.identifier) && isFiniteNumber6(foreignKey.sequence) && isString7(foreignKey.from_column) && isString7(foreignKey.target_table) && (foreignKey.target_column === null || isString7(foreignKey.target_column)) && isString7(foreignKey.on_update) && isString7(foreignKey.on_delete)
  ) && Array.isArray(value.indexes) && value.indexes.every(
    (index) => isRecord7(index) && isString7(index.name) && isBoolean2(index.unique) && isStringArray3(index.columns)
  );
  var isDatabaseSchema = (value) => isRecord7(value) && isString7(value.alembic_revision) && isString7(value.integrity) && Array.isArray(value.tables) && value.tables.every(isDatabaseTableSchema);
  var isDatabaseCell = (value) => isRecord7(value) && ["null", "integer", "real", "text", "blob"].includes(String(value.kind)) && (value.value === null || isString7(value.value) || isFiniteNumber6(value.value)) && isBoolean2(value.truncated);
  var isDatabaseTablePage = (value) => {
    if (!isRecord7(value) || !isString7(value.table_name) || !isFiniteNumber6(value.offset) || !isFiniteNumber6(value.limit) || !isFiniteNumber6(value.total_rows) || !isStringArray3(value.columns) || value.columns.length === 0 || !Array.isArray(value.rows) || value.next_offset !== null && !isFiniteNumber6(value.next_offset)) return false;
    const columns = value.columns;
    return value.rows.every(
      (row) => Array.isArray(row) && row.length === columns.length && row.every(isDatabaseCell)
    );
  };
  var renderColumns = (services, table) => {
    services.requiredElement("#database-table-heading").textContent = table.name;
    services.requiredElement("#database-table-summary").textContent = `${table.row_count} stored row(s) \xB7 ${table.columns.length} column(s) \xB7 ${table.foreign_keys.length} foreign key(s) \xB7 ${table.indexes.length} index(es)`;
    const body = services.requiredElement("#database-column-table tbody");
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
      defaultValue.textContent = column.default_value ?? "\u2014";
      const key = document.createElement("td");
      key.textContent = column.primary_key_position > 0 ? `PRIMARY ${column.primary_key_position}` : "\u2014";
      row.append(name, declaredType, nullable, defaultValue, key);
      body.append(row);
    });
    const renderList = (selector, values, empty) => {
      const list = services.requiredElement(selector);
      list.replaceChildren();
      (values.length === 0 ? [empty] : values).forEach((value) => {
        const item = document.createElement("li");
        item.textContent = value;
        list.append(item);
      });
    };
    renderList(
      "#database-foreign-key-list",
      table.foreign_keys.map(
        (foreignKey) => `${foreignKey.from_column} \u2192 ${foreignKey.target_table}.${foreignKey.target_column ?? "(rowid)"} \xB7 update ${foreignKey.on_update} \xB7 delete ${foreignKey.on_delete}`
      ),
      "No foreign keys"
    );
    renderList(
      "#database-index-list",
      table.indexes.map(
        (index) => `${index.name} \xB7 ${index.unique ? "UNIQUE" : "NON-UNIQUE"} \xB7 ${index.columns.join(", ") || "(expression)"}`
      ),
      "No indexes"
    );
  };
  var renderPage = (services, page) => {
    const head = services.requiredElement("#database-row-table thead");
    const body = services.requiredElement("#database-row-table tbody");
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
        value.textContent = cell.kind === "null" ? "NULL" : `${String(cell.value)}${cell.truncated ? "\u2026" : ""}`;
        row.append(value);
      });
      body.append(row);
    });
    const first = page.total_rows === 0 ? 0 : page.offset + 1;
    const last = page.offset + page.rows.length;
    services.requiredElement("#database-row-caption").textContent = `${page.table_name}: approved columns only, rows ${first}\u2013${last} of ${page.total_rows}.`;
    services.requiredElement("#database-page-status").textContent = `${first}\u2013${last} of ${page.total_rows}`;
    services.requiredElement("#database-previous").disabled = page.offset === 0;
    services.requiredElement("#database-next").disabled = page.next_offset === null;
  };
  var mountDatabasePage = async (services) => {
    let selectedTable = null;
    let currentPage = null;
    const selectTable = async (table, offset = 0) => {
      selectedTable = table;
      document.querySelectorAll("[data-database-table]").forEach((button) => {
        button.setAttribute("aria-current", String(button.dataset.databaseTable === table.name));
      });
      renderColumns(services, table);
      currentPage = await services.request(
        `/tables/${encodeURIComponent(table.name)}?offset=${offset}&limit=50`,
        isDatabaseTablePage
      );
      renderPage(services, currentPage);
      services.setStatus(
        "#database-status",
        `${table.name} loaded through the query-only boundary.`,
        "ready"
      );
    };
    const load = async () => {
      const schema = await services.request("/schema", isDatabaseSchema);
      services.requiredElement("#database-revision").textContent = schema.alembic_revision;
      services.requiredElement("#database-integrity").textContent = schema.integrity.toUpperCase();
      const tableList = services.requiredElement("#database-table-list");
      tableList.replaceChildren();
      schema.tables.forEach((table) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.databaseTable = table.name;
        button.setAttribute("aria-current", "false");
        button.textContent = `${table.name} (${table.row_count})`;
        button.addEventListener("click", () => void selectTable(table));
        tableList.append(button);
      });
      services.requiredElement("#database-explorer").hidden = false;
      if (schema.tables.length === 0) {
        services.setStatus("#database-status", "No approved tables are present.", "empty");
        return;
      }
      await selectTable(schema.tables[0]);
    };
    const reportFailure = (error) => {
      services.setStatus(
        "#database-status",
        services.toErrorMessage(error, "Database inspection failed."),
        "error"
      );
    };
    services.requiredElement("#database-session-form").addEventListener(
      "submit",
      (event) => {
        event.preventDefault();
        void load().catch(reportFailure);
      }
    );
    services.requiredElement("#database-previous").addEventListener(
      "click",
      () => {
        if (selectedTable !== null && currentPage !== null) {
          void selectTable(selectedTable, Math.max(0, currentPage.offset - currentPage.limit));
        }
      }
    );
    services.requiredElement("#database-next").addEventListener(
      "click",
      () => {
        if (selectedTable !== null && currentPage?.next_offset !== null) {
          void selectTable(selectedTable, currentPage.next_offset);
        }
      }
    );
    await load();
  };

  // src/reefproof/api/web/typescript/pages/system-map.ts
  var mountSystemMapPage = async (services) => {
    await mountReconciliation(services);
    const status = document.querySelector("#system-map-status");
    if (status !== null) {
      status.textContent = "Canonical authored identities and explicit observed bindings loaded.";
      status.className = "notice notice--ready";
    }
  };

  // src/reefproof/api/web/typescript/pages/assurance.ts
  var fields = {
    tank_volume_gallons: { label: "Main-tank volume", hint: "Authored system volume used for turnover.", unit: "gal", min: 1e-3, max: 1e6, step: "any", placeholder: "120" },
    pump_rated_flow_gph: { label: "Pump-rated return flow", hint: "Manufacturer-rated flow before system losses.", unit: "GPH", min: 1e-3, max: 1e7, step: "any", placeholder: "800" },
    delivered_flow_gph: { label: "Delivered return flow", hint: "Your measured or estimated delivered flow.", unit: "GPH", min: 1e-3, max: 1e7, step: "any", placeholder: "650" },
    minimum_turnover_per_hour: { label: "Minimum acceptable turnover", hint: "Your authored target\u2014not a universal recommendation.", unit: "\xD7 / hr", min: 1e-3, max: 1e3, step: "any", placeholder: "5" }
  };
  var isRecord8 = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
  var isString8 = (value) => typeof value === "string";
  var isFiniteNumber7 = (value) => typeof value === "number" && Number.isFinite(value);
  var isStringArray4 = (value) => Array.isArray(value) && value.every(isString8);
  var hasManualBoundary = (value) => value.schema_version === "0.1" && value.provenance_label === "MANUAL / NOT LIVE" && value.live_observation === false;
  var isTemplate = (value) => isRecord8(value) && hasManualBoundary(value) && value.policy_template_id === "RP-POLICY-FLOW-001" && value.provenance === "MANUAL" && value.units === "gallons/hour" && isStringArray4(value.fields);
  var isInputs = (value) => isRecord8(value) && isFiniteNumber7(value.tank_volume_gallons) && isFiniteNumber7(value.pump_rated_flow_gph) && isFiniteNumber7(value.delivered_flow_gph) && isFiniteNumber7(value.minimum_turnover_per_hour);
  var isRevision = (value) => isRecord8(value) && hasManualBoundary(value) && isString8(value.revision_id) && value.policy_template_id === "RP-POLICY-FLOW-001" && isFiniteNumber7(value.revision_number) && isString8(value.created_at) && isString8(value.authoring_operator_session_id) && isInputs(value.inputs) && isRecord8(value.preview) && ["PASS", "FAIL"].includes(String(value.preview.state)) && isFiniteNumber7(value.preview.actual_turnover_per_hour) && isFiniteNumber7(value.preview.minimum_delivered_flow_gph) && isFiniteNumber7(value.preview.delivery_difference_gph) && isFiniteNumber7(value.preview.delivery_efficiency_percent) && isString8(value.preview.explanation);
  var boundedFields = (template) => {
    if (template.fields.length !== Object.keys(fields).length || new Set(template.fields).size !== template.fields.length || template.fields.some((field) => !Object.hasOwn(fields, field))) throw new Error("Backend field contract is outside the bounded UI model.");
    return template.fields;
  };
  var createFields = (services, template) => {
    const container = services.requiredElement("#flow-fields");
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
      const input2 = document.createElement("input");
      Object.assign(input2, {
        name,
        type: "number",
        min: String(presentation.min),
        max: String(presentation.max),
        step: presentation.step,
        placeholder: presentation.placeholder,
        required: true,
        inputMode: "decimal"
      });
      const unit = document.createElement("span");
      unit.textContent = presentation.unit;
      unit.setAttribute("aria-hidden", "true");
      control.append(input2, unit);
      label.append(heading, hint, control);
      container.append(label);
    });
    services.requiredElement("#field-count").textContent = `${names.length} bounded fields`;
  };
  var input = (form, name) => {
    const element = form.elements.namedItem(name);
    if (!(element instanceof HTMLInputElement)) throw new Error(`Required input is missing: ${name}`);
    return element;
  };
  var readInputs = (form) => ({
    tank_volume_gallons: input(form, "tank_volume_gallons").valueAsNumber,
    pump_rated_flow_gph: input(form, "pump_rated_flow_gph").valueAsNumber,
    delivered_flow_gph: input(form, "delivered_flow_gph").valueAsNumber,
    minimum_turnover_per_hour: input(form, "minimum_turnover_per_hour").valueAsNumber
  });
  var render = (services, revision, form) => {
    Object.entries(revision.inputs).forEach(([name, value]) => {
      input(form, name).value = String(value);
    });
    const set = (name, value) => {
      services.requiredElement(`[data-result="${name}"]`).textContent = value;
    };
    set("revision", `Revision ${revision.revision_number} \xB7 ${revision.created_at}`);
    set("author-session", `Author session ${revision.authoring_operator_session_id}`);
    set("state", revision.preview.state);
    set("turnover", `${revision.preview.actual_turnover_per_hour}\xD7 / hr`);
    set("minimum-flow", `${revision.preview.minimum_delivered_flow_gph} GPH`);
    set("difference", `${revision.preview.delivery_difference_gph} GPH`);
    set("efficiency", `${revision.preview.delivery_efficiency_percent}%`);
    set("explanation", revision.preview.explanation);
    const preview = services.requiredElement("#preview");
    preview.dataset.state = revision.preview.state.toLowerCase();
    preview.hidden = false;
  };
  var mountAssurancePage = async (services) => {
    const form = services.requiredElement("#flow-form");
    try {
      const template = await services.request("/policy-template", isTemplate);
      createFields(services, template);
      services.requiredElement("#policy-inputs").hidden = false;
      const latest = await services.requestOptional("/policy-revisions/latest", isRevision);
      if (latest === null) {
        services.setStatus("#loading-status", "Ready \xB7 No authored policy has been saved yet.", "empty");
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
              body: JSON.stringify(readInputs(form))
            });
            render(services, revision, form);
            services.setStatus("#loading-status", `Saved revision ${revision.revision_number}.`, "ready");
            services.requiredElement("#preview").scrollIntoView({ behavior: "smooth", block: "start" });
          } catch (error) {
            services.setStatus("#loading-status", services.toErrorMessage(error, "Policy save failed."), "error");
          }
        })();
      });
    } catch (error) {
      services.setStatus("#loading-status", services.toErrorMessage(error, "Assurance failed to load."), "error");
    }
  };

  // src/reefproof/api/web/typescript/pages/evidence.ts
  var isRecord9 = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
  var isString9 = (value) => typeof value === "string";
  var isFiniteNumber8 = (value) => typeof value === "number" && Number.isFinite(value);
  var isStringArray5 = (value) => Array.isArray(value) && value.every(isString9);
  var hasManualBoundary2 = (value) => value.schema_version === "0.1" && value.provenance_label === "MANUAL / NOT LIVE" && value.live_observation === false;
  var isLogicalTreeNode = (value) => isRecord9(value) && ["rule", "all", "evidence", "outcome"].includes(String(value.kind)) && isString9(value.label) && (value.state === null || ["PASS", "FAIL", "UNKNOWN"].includes(String(value.state))) && Array.isArray(value.children) && value.children.every(isLogicalTreeNode);
  var isInvariantTemplate = (value) => isRecord9(value) && isString9(value.invariant_id) && isString9(value.version) && isString9(value.title) && ["info", "warning", "high", "critical"].includes(String(value.severity)) && isStringArray5(value.evidence_requirements) && isLogicalTreeNode(value.logical_tree);
  var isCatalog = (value) => isRecord9(value) && hasManualBoundary2(value) && Array.isArray(value.templates) && value.templates.every(isInvariantTemplate);
  var isInputs2 = (value) => isRecord9(value) && isFiniteNumber8(value.tank_volume_gallons) && isFiniteNumber8(value.pump_rated_flow_gph) && isFiniteNumber8(value.delivered_flow_gph) && isFiniteNumber8(value.minimum_turnover_per_hour);
  var isRevision2 = (value) => isRecord9(value) && hasManualBoundary2(value) && isString9(value.revision_id) && value.policy_template_id === "RP-POLICY-FLOW-001" && isFiniteNumber8(value.revision_number) && isString9(value.created_at) && isString9(value.authoring_operator_session_id) && isInputs2(value.inputs) && isRecord9(value.preview) && ["PASS", "FAIL"].includes(String(value.preview.state)) && isFiniteNumber8(value.preview.actual_turnover_per_hour) && isFiniteNumber8(value.preview.minimum_delivered_flow_gph) && isFiniteNumber8(value.preview.delivery_difference_gph) && isFiniteNumber8(value.preview.delivery_efficiency_percent) && isString9(value.preview.explanation);
  var formatTree = (node, depth = 0) => {
    const branch = depth === 0 ? "" : "\u2514\u2500 ";
    const state = node.state === null ? "" : `[${node.state}] `;
    const current = `${"  ".repeat(depth)}${branch}${state}${node.label}`;
    return [current, ...node.children.map((child) => formatTree(child, depth + 1))].join("\n");
  };
  var renderCatalog = (services, catalog) => {
    const selector = services.requiredElement("#rule-template-selector");
    selector.replaceChildren();
    const templates = /* @__PURE__ */ new Map();
    catalog.templates.forEach((template) => {
      if (templates.has(template.invariant_id)) throw new Error(`Duplicate committed rule: ${template.invariant_id}`);
      templates.set(template.invariant_id, template);
      const option = document.createElement("option");
      option.value = template.invariant_id;
      option.textContent = `${template.invariant_id} \xB7 ${template.title}`;
      selector.append(option);
    });
    if (templates.size === 0) throw new Error("The committed rule catalog is empty.");
    services.requiredElement("#catalog-summary").textContent = `${templates.size} backend-authored rules \xB7 schema ${catalog.schema_version}`;
    const renderSelected = () => {
      const template = templates.get(selector.value);
      if (template === void 0) throw new Error(`Unknown committed rule: ${selector.value}`);
      services.requiredElement("#rule-template-heading").textContent = `${template.invariant_id} v${template.version} \u2014 ${template.title}`;
      const severity = services.requiredElement("#rule-template-severity");
      severity.textContent = template.severity.toUpperCase();
      severity.dataset.severity = template.severity;
      services.requiredElement("#rule-tree").textContent = formatTree(template.logical_tree);
    };
    selector.addEventListener("change", renderSelected);
    renderSelected();
    services.requiredElement("#rule-catalog").hidden = false;
  };
  var renderRevision = (services, revision) => {
    const set = (name, value) => {
      services.requiredElement(`[data-evidence="${name}"]`).textContent = value;
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
    set("minimum-turnover", `${revision.inputs.minimum_turnover_per_hour}\xD7 / hr`);
    set("explanation", revision.preview.explanation);
    services.requiredElement("#evidence-revision-empty").hidden = true;
    services.requiredElement("#evidence-revision").hidden = false;
  };
  var mountEvidencePage = async (services) => {
    services.mountTrust();
    try {
      const [catalog, latest] = await Promise.all([
        services.request("/invariant-catalog", isCatalog),
        services.requestOptional("/policy-revisions/latest", isRevision2)
      ]);
      renderCatalog(services, catalog);
      services.requiredElement("#evidence-invariant-count").textContent = String(catalog.templates.length);
      if (latest === null) {
        services.requiredElement("#evidence-revision-empty").hidden = false;
        services.requiredElement("#evidence-revision").hidden = true;
        services.setStatus("#evidence-status", "Ready \xB7 No authored policy evidence exists yet.", "ready");
      } else {
        renderRevision(services, latest);
        services.setStatus("#evidence-status", `Loaded immutable revision ${latest.revision_number}.`, "ready");
      }
    } catch (error) {
      services.setStatus("#evidence-status", services.toErrorMessage(error, "Evidence failed to load."), "error");
    }
  };

  // src/reefproof/api/web/typescript/workbench.ts
  var API_ROOT = "/v1/workbench";
  var PROJECT_ID = document.documentElement?.dataset.projectId ?? "primary-reef-system";
  var PROJECT_ROOT = `/v1/projects/${PROJECT_ID}`;
  var AUTHENTICATED_SESSION_SENTINEL = "authenticated-session";
  var SESSION_INVALIDATED_MESSAGE = "Session is no longer valid. Authenticate again to continue.";
  var authenticatedPrincipalId = null;
  var browserDependencies = defaultBrowserDependencies();
  var updateLogoutControl = () => {
    const button = document.querySelector("#workbench-logout");
    if (button === null) {
      return;
    }
    button.hidden = authenticatedPrincipalId === null;
  };
  var requiredElement = (selector) => {
    const element = document.querySelector(selector);
    if (element === null) {
      throw new Error(`Required element is missing: ${selector}`);
    }
    return element;
  };
  var isRecord10 = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
  var isString10 = (value) => typeof value === "string";
  var isBoolean3 = (value) => typeof value === "boolean";
  var isFiniteNumber9 = (value) => typeof value === "number" && Number.isFinite(value);
  var isTrustEventView = (value) => isRecord10(value) && isString10(value.trust_event_id) && ["revoked", "restored"].includes(String(value.event_type)) && ["evidence", "subsystem"].includes(String(value.scope_kind)) && isString10(value.scope_id) && isString10(value.rationale) && isString10(value.occurred_at);
  var isTrustStateView = (value) => isRecord10(value) && Array.isArray(value.events) && value.events.every(isTrustEventView) && Array.isArray(value.active_revocations) && value.active_revocations.every(isTrustEventView) && isFiniteNumber9(value.last_sequence);
  var isOperatorSession = (value) => isRecord10(value) && isString10(value.principal_id) && value.principal_id.length > 0 && isString10(value.principal_display_name) && value.principal_display_name.length > 0;
  var toErrorMessage = (error, fallback) => error instanceof Error ? error.message : fallback;
  var requestJsonFrom = async (basePath, path, validator, options) => {
    const response = await browserDependencies.request(`${basePath}${path}`, {
      ...options,
      headers: { Accept: "application/json", ...options?.headers }
    });
    if (response.status === 401) {
      invalidateSession();
      throw new Error(SESSION_INVALIDATED_MESSAGE);
    }
    if (!response.ok) {
      throw new Error(`${path || "/"} failed: ${response.status}`);
    }
    const value = await response.json();
    if (!validator(value)) {
      throw new Error(`${path || "/"} returned data outside the committed UI boundary.`);
    }
    return value;
  };
  var requestJson = async (path, validator, options) => {
    return requestJsonFrom(API_ROOT, path, validator, options);
  };
  var requestProjectJson = async (path, _principalId, validator, options) => {
    return requestJsonFrom(PROJECT_ROOT, path, validator, options);
  };
  var requestDatabaseJson = async (path, validator) => {
    return requestJsonFrom("/v1/database", path, validator);
  };
  var markSessionGate = (authenticated) => {
    if (document.body != null) {
      document.body.dataset.sessionGated = authenticated ? "false" : "true";
    }
    const gate = document.querySelector("#session-auth-gate");
    if (gate !== null) {
      gate.hidden = authenticated;
    }
    const content = document.querySelector("#page-content");
    if (content !== null) {
      content.hidden = !authenticated;
    }
    updateLogoutControl();
  };
  var invalidateSession = (message = SESSION_INVALIDATED_MESSAGE) => {
    authenticatedPrincipalId = null;
    markSessionGate(false);
    if (document.querySelector("#startup-auth-status") !== null) {
      setStatus("#startup-auth-status", message, "error");
    }
  };
  var probeAuthenticatedSession = async () => {
    const response = await browserDependencies.request(`${API_ROOT}/totp`, {
      headers: { Accept: "application/json" }
    });
    if (response.status === 401) {
      return false;
    }
    if (!response.ok) {
      throw new Error(`Session check failed: ${response.status}`);
    }
    return true;
  };
  var updateSystemStatus = async () => {
    try {
      const response = await browserDependencies.request("/v1/system/status");
      if (response.ok) {
        const status = await response.json();
        const badge = document.querySelector("#system-mode-badge");
        if (badge !== null) {
          const mode = status.operating_mode.toUpperCase();
          const live = status.hydros_connection === "connected" ? "LIVE" : "NOT LIVE";
          badge.textContent = `${mode} \xB7 ${live}`;
        }
      }
    } catch (error) {
      console.debug("Could not fetch system status:", error);
    }
  };
  var initializeLogoutControl = () => {
    const button = document.querySelector("#workbench-logout");
    if (button === null) {
      return;
    }
    button.addEventListener("click", () => {
      void (async () => {
        try {
          const response = await browserDependencies.request(`${API_ROOT}/operator-sessions/current/revocations`, {
            method: "POST",
            headers: { Accept: "application/json" }
          });
          if (!response.ok && response.status !== 401) {
            throw new Error(`Logout failed: ${response.status}`);
          }
        } catch (error) {
          if (document.querySelector("#startup-auth-status") !== null) {
            setStatus(
              "#startup-auth-status",
              toErrorMessage(error, "Logout failed."),
              "error"
            );
          }
        } finally {
          invalidateSession("Session closed. Authenticate to unlock the workbench.");
        }
      })();
    });
    updateLogoutControl();
  };
  var initializeSessionWatchdog = () => {
    if (typeof window === "undefined" || typeof window.setInterval !== "function") {
      return;
    }
    window.setInterval(() => {
      if (authenticatedPrincipalId === null) {
        return;
      }
      void (async () => {
        try {
          if (!await probeAuthenticatedSession()) {
            invalidateSession();
          }
        } catch {
        }
      })();
    }, 5e3);
  };
  var setMethodStatus = (method, message, kind, visible = true) => {
    const statusId = method === "totp" ? "totp-status" : "bootstrap-status";
    const status = document.querySelector(`#${statusId}`);
    if (status === null) return;
    if (!visible || message.length === 0) {
      status.hidden = true;
    } else {
      status.hidden = false;
      status.className = `auth-method-status notice--${kind}`;
      const span = status.querySelector("span:last-of-type");
      if (span !== null) {
        span.textContent = message;
      }
    }
  };
  var setCredentialError = (input2, statusId, invalid) => {
    if (invalid) {
      input2.setAttribute("aria-invalid", "true");
      input2.setAttribute("aria-errormessage", statusId);
      return;
    }
    input2.removeAttribute("aria-invalid");
    input2.removeAttribute("aria-errormessage");
  };
  var requireAuthenticatedSession = () => {
    const sessionForm = document.querySelector("#startup-session-form");
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
        const authMethodData = await authMethodResponse.json();
        const methodFieldset = authMethodData.method === "totp" ? document.querySelector("#auth-method-totp") : document.querySelector("#auth-method-bootstrap");
        if (methodFieldset !== null) {
          methodFieldset.hidden = false;
          const input2 = methodFieldset.querySelector("input");
          if (input2 !== null) {
            if (authMethodData.method === "totp" && input2.name === "totp_code") {
              setMethodStatus("totp", "Enter your authenticator code to unlock.", "empty");
              const validateTotp = () => {
                const code = input2.value.trim();
                if (code.length === 0) {
                  setCredentialError(input2, "totp-status", false);
                  setMethodStatus("totp", "", "empty", false);
                } else if (!/^\d{6}$/.test(code)) {
                  setCredentialError(input2, "totp-status", true);
                  setMethodStatus("totp", "Code must be 6 digits.", "error");
                } else {
                  setCredentialError(input2, "totp-status", false);
                  setMethodStatus("totp", "Code ready to submit.", "ready");
                }
              };
              input2.addEventListener("input", validateTotp);
              input2.addEventListener("change", validateTotp);
            } else {
              setMethodStatus("bootstrap", "Enter the bootstrap shared secret to unlock.", "empty");
            }
          }
        }
      } catch (error) {
        setMethodStatus("bootstrap", toErrorMessage(error, "Session check failed. Authenticate to continue."), "error");
        setMethodStatus("totp", toErrorMessage(error, "Session check failed. Authenticate to continue."), "error");
      }
      await new Promise((resolve) => {
        sessionForm.addEventListener("submit", (event) => {
          event.preventDefault();
          void (async () => {
            const bootstrapFieldset = document.querySelector("#auth-method-bootstrap");
            const totpFieldset = document.querySelector("#auth-method-totp");
            const sharedSecretInput = sessionForm.elements.namedItem("bootstrap_secret");
            const totpCodeInput = sessionForm.elements.namedItem("totp_code");
            if (sharedSecretInput instanceof HTMLInputElement) {
              setCredentialError(sharedSecretInput, "bootstrap-status", false);
            }
            if (totpCodeInput instanceof HTMLInputElement) {
              setCredentialError(totpCodeInput, "totp-status", false);
            }
            let validationError = null;
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
              let invalidInput = null;
              let statusId;
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
            } catch (error) {
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
  var establishSession = async (form) => {
    const sharedSecretInput = form.elements.namedItem("bootstrap_secret");
    const totpCodeInput = form.elements.namedItem("totp_code");
    const sharedSecret = sharedSecretInput instanceof HTMLInputElement ? sharedSecretInput.value.trim() : "";
    const totpCode = totpCodeInput instanceof HTMLInputElement ? totpCodeInput.value.trim() : "";
    if (sharedSecret.length === 0 && totpCode.length === 0) {
      throw new Error("Provide a valid authentication credential.");
    }
    const session = await requestJson("/operator-sessions", isOperatorSession, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bootstrap_secret: sharedSecret, totp_code: totpCode })
    });
    if (sharedSecretInput instanceof HTMLInputElement) {
      sharedSecretInput.value = "";
    }
    if (totpCodeInput instanceof HTMLInputElement) {
      totpCodeInput.value = "";
    }
    return session.principal_id;
  };
  var setStatus = (selector, message, kind) => {
    const status = requiredElement(selector);
    status.hidden = false;
    status.className = `notice notice--${kind}`;
    status.lastElementChild.textContent = message;
  };
  var renderTrustState = (state) => {
    const history = requiredElement("#trust-history");
    history.replaceChildren();
    if (state.events.length === 0) {
      const empty = document.createElement("p");
      empty.textContent = "No trust events recorded. Canonical evidence remains trusted.";
      history.append(empty);
      return;
    }
    const activeIds = new Set(
      state.active_revocations.map((event) => event.trust_event_id)
    );
    state.events.slice().reverse().forEach((event) => {
      const article = document.createElement("article");
      const heading = document.createElement("h4");
      const active = activeIds.has(event.trust_event_id);
      heading.textContent = `${event.event_type === "revoked" ? "\u2298 REVOKED" : "\u2713 RESTORED"} \xB7 ${event.scope_kind} ${event.scope_id}${active ? " \xB7 ACTIVE" : ""}`;
      const detail = document.createElement("p");
      detail.textContent = `${event.rationale} \xB7 ${event.occurred_at}`;
      article.append(heading, detail);
      history.append(article);
    });
  };
  var loadTrust = (principalId) => requestProjectJson("/trust", principalId, isTrustStateView);
  var initializeTrust = () => {
    const sessionForm = requiredElement("#trust-session-form");
    const controls = requiredElement("#trust-controls");
    const enrollment = requiredElement("#totp-enrollment");
    const qrImage = requiredElement("#totp-qr");
    let principalId = authenticatedPrincipalId;
    let challengeId = null;
    const refresh = async () => {
      if (principalId === null) {
        return false;
      }
      renderTrustState(await loadTrust(principalId));
      const totp = await requestJson(
        "/totp",
        (value) => isRecord10(value) && isBoolean3(value.enrolled)
      );
      requiredElement("#totp-enrollment-state").textContent = `Phone authenticator: ${totp.enrolled ? "ENROLLED" : "NOT ENROLLED"}`;
      requiredElement("#totp-enroll").hidden = totp.enrolled;
      return totp.enrolled;
    };
    const beginEnrollment = async () => {
      const response = await requestJson(
        "/totp/enrollment",
        (value) => isRecord10(value) && isString10(value.challenge_id) && isString10(value.qr_png_base64),
        { method: "POST" }
      );
      challengeId = response.challenge_id;
      qrImage.src = `data:image/png;base64,${response.qr_png_base64}`;
      enrollment.hidden = false;
      setStatus(
        "#trust-status",
        "QR code loaded. Scan it with your authenticator app, then confirm with a six-digit code.",
        "ready"
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
            totpEnrolled ? "Trust history loaded from the backend." : "Trust history loaded. authenticator app is not enrolled yet; click Enroll authenticator app to reveal the QR code.",
            "ready"
          );
        } catch (error) {
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
            totpEnrolled ? "Trust history loaded from the backend." : "Trust history loaded. authenticator app is not enrolled yet; click Enroll authenticator app to reveal the QR code.",
            "ready"
          );
        } catch (error) {
          setStatus("#trust-status", toErrorMessage(error, "Trust history failed to load."), "error");
        }
      })();
    }
    requiredElement("#totp-enroll").addEventListener("click", () => {
      void (async () => {
        try {
          await beginEnrollment();
        } catch (error) {
          setStatus("#trust-status", toErrorMessage(error, "authenticator app enrollment failed."), "error");
        }
      })();
    });
    requiredElement("#totp-confirm-form").addEventListener(
      "submit",
      (event) => {
        event.preventDefault();
        void (async () => {
          try {
            if (challengeId === null) {
              throw new Error("Start enrollment before confirming a authenticator code.");
            }
            const form = event.currentTarget;
            const code = form.elements.namedItem("totp_code");
            const response = await browserDependencies.request(`${API_ROOT}/totp/enrollment/confirm`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                challenge_id: challengeId,
                totp_code: code instanceof HTMLInputElement ? code.value : ""
              })
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
              "ready"
            );
          } catch (error) {
            setStatus("#trust-status", toErrorMessage(error, "authenticator app confirmation failed."), "error");
          }
        })();
      }
    );
    requiredElement("#trust-revocation-form").addEventListener(
      "submit",
      (event) => {
        event.preventDefault();
        void (async () => {
          try {
            if (principalId === null) {
              return;
            }
            const form = event.currentTarget;
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
                  totp_code: data.get("totp_code")
                })
              }
            );
            renderTrustState(state);
            setStatus(
              "#trust-status",
              "Trust revoked. Affected projections are UNKNOWN and REVOKED.",
              "ready"
            );
            form.reset();
          } catch (error) {
            setStatus("#trust-status", toErrorMessage(error, "Trust revocation failed."), "error");
          }
        })();
      }
    );
    requiredElement("#trust-restoration-form").addEventListener(
      "submit",
      (event) => {
        event.preventDefault();
        void (async () => {
          try {
            if (principalId === null) {
              return;
            }
            const form = event.currentTarget;
            const data = new FormData(form);
            const candidates = String(data.get("replacement_candidate_fact_ids") ?? "").split(",").map((value) => value.trim()).filter((value) => value.length > 0);
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
                  totp_code: data.get("totp_code")
                })
              }
            );
            renderTrustState(state);
            setStatus(
              "#trust-status",
              "Trust restored from complete fresh evidence and a new authenticator code.",
              "ready"
            );
            form.reset();
          } catch (error) {
            setStatus("#trust-status", toErrorMessage(error, "Trust restoration failed."), "error");
          }
        })();
      }
    );
  };
  var initialize = async () => {
    initializeLogoutControl();
    initializeSessionWatchdog();
    void updateSystemStatus();
    const authentication = requireAuthenticatedSession();
    if (authentication !== void 0) {
      await authentication;
    }
    const controllers = [
      {
        page: "overview",
        mount: () => mountOverviewPage({
          projectId: PROJECT_ID,
          requestWorkbench: requestJson,
          requestProject: (path, validator, options) => requestProjectJson(
            path,
            authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL,
            validator,
            options
          ),
          requiredElement,
          setStatus,
          toErrorMessage
        })
      },
      {
        page: "assurance",
        mount: () => mountAssurancePage({
          request: requestJson,
          requestOptional: (path, validator) => requestJson(
            path,
            (value) => value === null || validator(value)
          ),
          requiredElement,
          setStatus,
          toErrorMessage
        })
      },
      {
        page: "evidence",
        mount: () => mountEvidencePage({
          request: requestJson,
          requestOptional: (path, validator) => requestJson(
            path,
            (value) => value === null || validator(value)
          ),
          requiredElement,
          setStatus,
          toErrorMessage,
          mountTrust: initializeTrust
        })
      },
      {
        page: "system-map",
        mount: () => mountSystemMapPage({
          request: (path, validator, options) => requestProjectJson(
            path,
            authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL,
            validator,
            options
          ),
          toErrorMessage
        })
      },
      {
        page: "source",
        mount: () => mountSourcePage({
          request: (path, validator, options) => requestProjectJson(
            path,
            authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL,
            validator,
            options
          ),
          requiredElement,
          toErrorMessage
        })
      },
      {
        page: "commissioning",
        mount: () => mountCommissioningPage({
          request: (path, validator, options) => requestProjectJson(
            path,
            authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL,
            validator,
            options
          ),
          requiredElement,
          toErrorMessage
        })
      },
      {
        page: "labels",
        mount: () => mountLabelsPage({
          request: (path, validator, options) => requestProjectJson(
            path,
            authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL,
            validator,
            options
          ),
          requiredElement,
          toErrorMessage
        })
      },
      {
        page: "sessions",
        mount: () => mountSessionsPage({
          request: (path, validator, options) => requestProjectJson(
            path,
            authenticatedPrincipalId ?? AUTHENTICATED_SESSION_SENTINEL,
            validator,
            options
          ),
          requiredElement,
          setStatus,
          toErrorMessage
        })
      },
      {
        page: "database",
        mount: () => mountDatabasePage({
          request: requestDatabaseJson,
          requiredElement,
          setStatus,
          toErrorMessage
        })
      }
    ];
    const page = document.body?.dataset.workbenchPage;
    if (page !== void 0) {
      await mountRegisteredPage(page, controllers);
      return;
    }
    throw new Error("Workbench page identity is missing.");
  };
  var mountWorkbench = async (dependencies = defaultBrowserDependencies()) => {
    browserDependencies = dependencies;
    await initialize();
  };
  var redirectLegacyWorkbenchFragment = () => {
    if (typeof window === "undefined" || typeof window.location?.hash !== "string") {
      return false;
    }
    const route = (/* @__PURE__ */ new Map([
      ["#policy-inputs", "/workbench/assurance"],
      ["#preview", "/workbench/assurance"],
      ["#evidence-heading", "/workbench/evidence"]
    ])).get(window.location.hash);
    if (route !== void 0 && document.body?.dataset.workbenchPage === "overview") {
      window.location.replace(route);
      return true;
    }
    return false;
  };
  if (!redirectLegacyWorkbenchFragment()) {
    void mountWorkbench();
  }
})();
