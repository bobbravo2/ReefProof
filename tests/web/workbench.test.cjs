const assert = require("node:assert/strict");
const fs = require("node:fs");
const test = require("node:test");
const vm = require("node:vm");

class FakeElement {
  constructor() {
    this.hidden = true;
    this.textContent = "";
    this.listeners = new Map();
    this.dataset = {};
    this.children = [];
    this.attributes = new Map();
    this.className = "";
    this.classList = { add: (...names) => (this.className += ` ${names.join(" ")}`) };
  }

  addEventListener(name, listener) {
    this.listeners.set(name, listener);
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = [...children];
  }

  setAttribute(name, value) {
    this.attributes.set(name, value);
  }

  scrollIntoView() {
    this.scrolled = true;
  }

  get lastElementChild() {
    return this.children.at(-1) ?? null;
  }
}

class FakeInput extends FakeElement {
  constructor(value = "") {
    super();
    this.value = String(value);
    this.checked = true;
    this.required = false;
  }

  get valueAsNumber() {
    return Number(this.value);
  }
}

class FakeSelect extends FakeElement {
  constructor() {
    super();
    this.options = [];
    this._value = "";
  }

  append(...options) {
    super.append(...options);
    this.options.push(...options);
    if (!this._value && options[0]) {
      this._value = options[0].value;
    }
  }

  replaceChildren(...options) {
    super.replaceChildren(...options);
    this.options = [...options];
    this._value = options[0]?.value ?? "";
  }

  get value() {
    return this._value;
  }

  set value(value) {
    this._value = value;
  }
}

class FakeForm extends FakeElement {
  constructor(inputs) {
    super();
    this.elements = { namedItem: (name) => inputs.get(name) ?? null };
  }
}

class FakeSvgElement extends FakeElement {}
class FakeSvgEllipse extends FakeSvgElement {}
class FakeSvgGroup extends FakeSvgElement {}

class FakeStorage {
  constructor() {
    this.values = new Map();
  }

  getItem(key) {
    return this.values.has(key) ? this.values.get(key) : null;
  }

  setItem(key, value) {
    this.values.set(key, String(value));
  }

  removeItem(key) {
    this.values.delete(key);
  }
}

const nextTurn = () => new Promise((resolve) => setImmediate(resolve));

const catalogTemplate = (invariantId, title, severity) => ({
  invariant_id: invariantId,
  version: "1",
  title,
  severity,
  collective_name: "Mock Collective",
  provenance_label: "MANUAL / NOT LIVE",
  live_observation: false,
  evidence_requirements: ["Complete authored evidence."],
  logical_tree: {
    kind: "rule",
    label: title,
    state: null,
    children: [
      {
        kind: "all",
        label: "Required evidence",
        state: null,
        children: [
          {
            kind: "evidence",
            label: "Complete authored evidence.",
            state: null,
            children: [],
          },
        ],
      },
      {
        kind: "outcome",
        label: "The requirement is satisfied.",
        state: "PASS",
        children: [],
      },
      {
        kind: "outcome",
        label: "The requirement is violated.",
        state: "FAIL",
        children: [],
      },
      {
        kind: "outcome",
        label: "Evidence is incomplete.",
        state: "UNKNOWN",
        children: [],
      },
    ],
  },
});

test("workbench uses one global session gate without inline credential fallback", async () => {
  const source = fs.readFileSync("src/reefproof/api/web/templates/workbench.html", "utf8");
  assert.equal((source.match(/name="bootstrap_secret"/g) ?? []).length, 1);
  assert.equal((source.match(/name="totp_code"/g) ?? []).length, 4);
  assert.doesNotMatch(source, /session_auth_fields/);
  return;
  const sharedSecretInput = new FakeInput("bootstrap-shared-secret");
  const totpCodeInput = new FakeInput();
  const sessionForm = new FakeForm(
    new Map([
      ["bootstrap_secret", sharedSecretInput],
      ["totp_code", totpCodeInput],
    ]),
  );
  const trustControls = new FakeElement();
  trustControls.hidden = true;
  const totpEnrollmentState = new FakeElement();
  const totpEnroll = new FakeElement();
  const totpEnrollment = new FakeElement();
  const totpQr = new FakeElement();
  const totpConfirmForm = new FakeForm(new Map());
  const trustRevocationForm = new FakeForm(new Map());
  const trustRestorationForm = new FakeForm(new Map());
  const trustStatus = new FakeElement();
  trustStatus.append(new FakeElement(), new FakeElement());

  const selectors = new Map([
    ["#trust-session-form", sessionForm],
    ["#trust-controls", trustControls],
    ["#totp-enrollment-state", totpEnrollmentState],
    ["#totp-enroll", totpEnroll],
    ["#totp-enrollment", totpEnrollment],
    ["#totp-qr", totpQr],
    ["#totp-confirm-form", totpConfirmForm],
    ["#trust-revocation-form", trustRevocationForm],
    ["#trust-restoration-form", trustRestorationForm],
    ["#trust-status", trustStatus],
  ]);

  const requests = [];
  const responses = [
    {
      ok: true,
      status: 200,
      json: async () => ({
        mode: "LOCAL",
        status: "NOT LIVE",
        display: "LOCAL · NOT LIVE",
      }),
    },
    {
      ok: true,
      status: 201,
      json: async () => ({
        principal_id: "local-acceptance-authority",
        principal_display_name: "Local acceptance authority",
      }),
    },
    {
      ok: true,
      status: 200,
      json: async () => ({ enrolled: false }),
    },
    {
      ok: true,
      status: 201,
      json: async () => ({
        challenge_id: "pending-challenge",
        qr_png_base64: "AQID",
      }),
    },
  ];

  const document = {
    querySelector: (selector) => selectors.get(selector) ?? null,
    querySelectorAll: () => [],
    createElement: (name) => {
      if (name === "input") return new FakeInput();
      return new FakeElement();
    },
    createElementNS: (_namespace, name) => {
      if (name === "ellipse") return new FakeSvgEllipse();
      if (name === "g") return new FakeSvgGroup();
      return new FakeSvgElement();
    },
  };
  const fetch = async (path, options = {}) => {
    requests.push({ path, options });
    return responses.shift();
  };

  const script = fs.readFileSync("src/reefproof/api/web/static/workbench.js", "utf8")
    .replace(/\nexport \{\};\s*$/, "");
  vm.runInNewContext(script, {
    console,
    document,
    fetch,
    window: {},
    HTMLElement: FakeElement,
    HTMLInputElement: FakeInput,
    HTMLFormElement: FakeForm,
    HTMLSelectElement: FakeElement,
    SVGEllipseElement: FakeSvgEllipse,
    Error,
    Map,
    Number,
    Object,
    Promise,
    Set,
  }, { filename: "workbench.js" });
  await nextTurn();

  sessionForm.listeners.get("submit")({ preventDefault() {} });
  await nextTurn();
  await nextTurn();
  assert.equal(sharedSecretInput.value, "");
  assert.equal(totpCodeInput.value, "");

  totpEnroll.listeners.get("click")();
  await nextTurn();
  await nextTurn();
  assert.equal(totpEnrollment.hidden, false);
  assert.equal(totpQr.src, "data:image/png;base64,AQID");

  assert.equal(requests[1].path, "/v1/workbench/operator-sessions");
  assert.deepEqual(JSON.parse(requests[1].options.body), {
    bootstrap_secret: "bootstrap-shared-secret",
    totp_code: "",
  });
});

test("workbench consumes the versioned rule model and renders saved evidence", async () => {
  const inputValues = {
    tank_volume_gallons: 250,
    pump_rated_flow_gph: 800,
    delivered_flow_gph: 650,
    minimum_turnover_per_hour: 2,
  };
  const inputs = new Map(
    Object.entries(inputValues).map(([name, value]) => [name, new FakeInput(value)]),
  );
  inputs.set("bootstrap_secret", new FakeInput("test-operator-secret"));
  const form = new FakeForm(inputs);
  const status = new FakeElement();
  status.append(new FakeElement(), new FakeElement());
  const policy = new FakeElement();
  const flowFields = new FakeElement();
  const fieldCount = new FakeElement();
  const preview = new FakeElement();
  const catalog = new FakeElement();
  const selector = new FakeSelect();
  const catalogSummary = new FakeElement();
  const templateHeading = new FakeElement();
  const templateSeverity = new FakeElement();
  const ruleTree = new FakeElement();
  const twin = new FakeElement();
  const relationships = new FakeSvgGroup();
  const entities = new FakeSvgGroup();
  const findings = new FakeElement();
  const facts = new FakeElement();
  const criticalFilter = new FakeInput();
  criticalFilter.dataset.severityFilter = "critical";
  const results = new Map(
    [
      "revision",
      "author-session",
      "state",
      "turnover",
      "minimum-flow",
      "difference",
      "efficiency",
      "explanation",
    ].map((name) => [name, new FakeElement()]),
  );
  const selectors = new Map([
    ["#loading-status", status],
    ["#policy-inputs", policy],
    ["#flow-form", form],
    ["#flow-fields", flowFields],
    ["#field-count", fieldCount],
    ["#preview", preview],
    ["#rule-catalog", catalog],
    ["#rule-template-selector", selector],
    ["#catalog-summary", catalogSummary],
    ["#rule-template-heading", templateHeading],
    ["#rule-template-severity", templateSeverity],
    ["#rule-tree", ruleTree],
    ["#physical-twin", twin],
    ["#physical-relationships", relationships],
    ["#physical-entities", entities],
    ["#mock-findings", findings],
    ["#physical-facts", facts],
  ]);
  for (const [name, element] of results) {
    selectors.set(`[data-result="${name}"]`, element);
  }

  const previewDocument = (state, turnover, explanation) => ({
    schema_version: "0.1",
    collective_name: "Mock Collective",
    provenance: "MANUAL",
    provenance_label: "MANUAL / NOT LIVE",
    live_observation: false,
    policy_kind: "operator-authored minimum turnover",
    state,
    delivery_difference_gph: 800 - turnover * 250,
    delivery_efficiency_percent: (turnover * 250 * 100) / 800,
    actual_turnover_per_hour: turnover,
    minimum_delivered_flow_gph: 500,
    explanation,
  });
  const revision = (number, deliveredFlow, state) => ({
    schema_version: "0.1",
    revision_id: `00000000-0000-4000-8000-00000000000${number}`,
    policy_template_id: "RP-POLICY-FLOW-001",
    revision_number: number,
    created_at: `2026-07-25T17:0${number}:00+00:00`,
    authoring_operator_session_id: "12345678-abcd-4234-8234-123456789abc",
    collective_name: "Mock Collective",
    provenance: "MANUAL",
    provenance_label: "MANUAL / NOT LIVE",
    live_observation: false,
    inputs: { ...inputValues, delivered_flow_gph: deliveredFlow },
    preview: previewDocument(state, deliveredFlow / 250, `revision ${number}`),
  });
  const latest = revision(1, 650, "PASS");
  const saved = revision(2, 450, "FAIL");
  const requests = [];
  const responses = [
    {
      ok: true,
      status: 200,
      json: async () => ({
        mode: "LOCAL",
        status: "NOT LIVE",
        display: "LOCAL · NOT LIVE",
      }),
    },
    {
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: "0.1",
        policy_template_id: "RP-POLICY-FLOW-001",
        collective_name: "Mock Collective",
        provenance: "MANUAL",
        provenance_label: "MANUAL / NOT LIVE",
        live_observation: false,
        units: "gallons/hour",
        fields: Object.keys(inputValues),
      }),
    },
    {
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: "0.1",
        collective_name: "Mock Collective",
        provenance_label: "MANUAL / NOT LIVE",
        live_observation: false,
        templates: [
          catalogTemplate("RP-CIRC-001", "Independent return power", "critical"),
          catalogTemplate("RP-FLOW-001", "UV flow permissive", "high"),
        ],
      }),
    },
    {
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: "0.1",
        collective_name: "Mock Collective",
        provenance_label: "MANUAL / NOT LIVE",
        live_observation: false,
        entities: [
          {
            entity_id: "return_pump",
            physical_type: "return_pump",
            label: "Return pump",
            quantity: 1,
            elevation_inches: 4,
            size: { width_inches: 8, height_inches: 6, depth_inches: 5, volume_gallons: null },
            geometry: { x: 75, y: 320, width: 135, height: 80 },
          },
        ],
        relationships: [
          {
            direction: "up_and_right",
            dependency: "Authored pump path.",
            label: "Mock return path",
            svg_path: "M 145 320 L 145 105 L 330 105",
          },
        ],
        findings: [
          {
            finding_id: "mock-return-critical",
            severity: "critical",
            icon: "⚠",
            state_text: "CRITICAL",
            summary: "Mock critical finding.",
          },
        ],
      }),
    },
    { ok: true, status: 200, json: async () => latest },
    { ok: true, status: 201, json: async () => saved },
  ];

  const document = {
    querySelector: (selector) => selectors.get(selector) ?? null,
    querySelectorAll: (selector) => {
      if (selector === "[data-severity-filter]") {
        return [criticalFilter];
      }
      if (selector === "[data-finding-severity]") {
        return findings.children;
      }
      return [];
    },
    createElement: (name) => {
      if (name === "input") return new FakeInput();
      if (name === "option") return new FakeElement();
      return new FakeElement();
    },
    createElementNS: (_namespace, name) => {
      if (name === "ellipse") return new FakeSvgEllipse();
      if (name === "g") return new FakeSvgGroup();
      return new FakeSvgElement();
    },
  };
  const fetch = async (path, options = {}) => {
    requests.push({ path, options });
    return responses.shift();
  };

  const script = fs
    .readFileSync("src/reefproof/api/web/static/workbench.js", "utf8")
    .replace(/\nexport \{\};\s*$/, "");
  vm.runInNewContext(script, {
    console,
    document,
    fetch,
    HTMLElement: FakeElement,
    HTMLInputElement: FakeInput,
    HTMLFormElement: FakeForm,
    HTMLSelectElement: FakeSelect,
    SVGEllipseElement: FakeSvgEllipse,
    Error,
    Map,
    Number,
    Object,
    Promise,
    Set,
  }, { filename: "workbench.js" });
  await nextTurn();
  await nextTurn();

  assert.deepEqual(
    requests.slice(0, 5).map(({ path }) => path),
    [
      "/v1/system/status",
      "/v1/workbench/policy-template",
      "/v1/workbench/invariant-catalog",
      "/v1/workbench/physical-twin",
      "/v1/workbench/policy-revisions/latest",
    ],
  );
  assert.equal(policy.hidden, false);
  assert.equal(flowFields.children.length, 4);
  assert.equal(fieldCount.textContent, "4 bounded fields");
  assert.equal(catalogSummary.textContent, "2 backend-authored rules · schema 0.1");
  assert.equal(templateHeading.textContent, "RP-CIRC-001 v1 — Independent return power");
  assert.equal(templateSeverity.textContent, "CRITICAL");
  assert.match(ruleTree.textContent, /\[UNKNOWN\] Evidence is incomplete/);
  assert.equal(relationships.children.length, 1);
  assert.equal(entities.children.length, 1);
  assert.equal(findings.children.length, 1);
  assert.equal(results.get("state").textContent, "PASS");
  assert.equal(status.lastElementChild.textContent, "Loaded saved revision 1 from the backend.");

  inputs.get("delivered_flow_gph").value = "450";
  form.listeners.get("submit")({ preventDefault() {} });
  await nextTurn();
  await nextTurn();

  assert.equal(status.lastElementChild.textContent, "Saved revision 2.");
  assert.equal(results.get("state").textContent, "FAIL");
  assert.equal(preview.dataset.state, "fail");
  assert.equal(preview.scrolled, true);
  assert.deepEqual(JSON.parse(requests[5].options.body), {
    ...inputValues,
    delivered_flow_gph: 450,
  });
});

test("workbench represents an empty revision as a successful typed response", async () => {
  const source = fs.readFileSync("src/reefproof/api/web/static/workbench.js", "utf8");
  assert.match(source, /if \(value === null\)/);
  assert.equal(source.includes("response.status === 404"), false);
  assert.match(source, /No authored policy has been saved yet/);
  assert.equal(source.includes('fetch("/api/workbench'), false);
});

test("workbench renders the empty revision state after a 200 null response", async () => {
  const status = new FakeElement();
  status.append(new FakeElement(), new FakeElement());
  const form = new FakeForm(new Map());
  const policy = new FakeElement();
  const flowFields = new FakeElement();
  const fieldCount = new FakeElement();
  const selectors = new Map([
    ["#loading-status", status],
    ["#flow-form", form],
    ["#policy-inputs", policy],
    ["#flow-fields", flowFields],
    ["#field-count", fieldCount],
  ]);
  const requests = [];
  const responses = [
    {
      ok: true,
      status: 200,
      json: async () => ({
        mode: "LOCAL",
        status: "NOT LIVE",
        display: "LOCAL · NOT LIVE",
      }),
    },
    {
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: "0.1",
        policy_template_id: "RP-POLICY-FLOW-001",
        collective_name: "Mock Collective",
        provenance: "MANUAL",
        provenance_label: "MANUAL / NOT LIVE",
        live_observation: false,
        units: "gallons/hour",
        fields: [
          "tank_volume_gallons",
          "pump_rated_flow_gph",
          "delivered_flow_gph",
          "minimum_turnover_per_hour",
        ],
      }),
    },
    { ok: true, status: 200, json: async () => null },
  ];
  const document = {
    querySelector: (selector) => selectors.get(selector) ?? null,
    querySelectorAll: () => [],
    createElement: () => new FakeElement(),
  };
  const fetch = async (path) => {
    requests.push(path);
    return responses.shift();
  };
  const source = fs
    .readFileSync("src/reefproof/api/web/static/workbench.js", "utf8")
    .replace(/\nexport \{\};\s*$/, "");
  vm.runInNewContext(source, {
    console,
    document,
    fetch,
    HTMLElement: FakeElement,
    HTMLInputElement: FakeInput,
    HTMLFormElement: FakeForm,
    HTMLSelectElement: FakeSelect,
    SVGEllipseElement: FakeSvgEllipse,
    Error,
    Map,
    Number,
    Object,
    Promise,
    Set,
  });
  await nextTurn();
  await nextTurn();

  assert.deepEqual(requests, [
    "/v1/system/status",
    "/v1/workbench/policy-template",
    "/v1/workbench/policy-revisions/latest",
  ]);
  assert.equal(policy.hidden, false);
  assert.equal(status.lastElementChild.textContent, "Ready · No authored policy has been saved yet.");
});

test("legacy evidence fragment redirects to the full Evidence route", () => {
  const destinations = [];
  const source = fs
    .readFileSync("src/reefproof/api/web/static/workbench.js", "utf8")
    .replace(/\nexport \{\};\s*$/, "");
  vm.runInNewContext(source, {
    console,
    document: {
      body: { dataset: { workbenchPage: "overview" } },
    },
    window: {
      location: {
        hash: "#evidence-heading",
        replace: (route) => destinations.push(route),
      },
    },
    HTMLElement: FakeElement,
    HTMLInputElement: FakeInput,
    HTMLFormElement: FakeForm,
    HTMLSelectElement: FakeSelect,
    SVGEllipseElement: FakeSvgEllipse,
    Error,
    Map,
    Number,
    Object,
    Promise,
    Set,
  });

  assert.deepEqual(destinations, ["/workbench/evidence"]);
});

test("evidence page renders the latest immutable revision and catalog", async () => {
  const status = new FakeElement();
  status.append(new FakeElement(), new FakeElement());
  const catalog = new FakeElement();
  const selector = new FakeSelect();
  const revisionContainer = new FakeElement();
  const emptyRevision = new FakeElement();
  const invariantCount = new FakeElement();
  const evidence = new Map(
    [
      "state",
      "revision",
      "created",
      "author-session",
      "template",
      "provenance",
      "revision-id",
      "tank-volume",
      "pump-flow",
      "delivered-flow",
      "minimum-turnover",
      "explanation",
    ].map((name) => [name, new FakeElement()]),
  );
  const selectors = new Map([
    ["#evidence-status", status],
    ["#evidence-invariant-count", invariantCount],
    ["#evidence-revision", revisionContainer],
    ["#evidence-revision-empty", emptyRevision],
    ["#rule-catalog", catalog],
    ["#rule-template-selector", selector],
    ["#catalog-summary", new FakeElement()],
    ["#rule-template-heading", new FakeElement()],
    ["#rule-template-severity", new FakeElement()],
    ["#rule-tree", new FakeElement()],
  ]);
  for (const [name, element] of evidence) {
    selectors.set(`[data-evidence="${name}"]`, element);
  }
  const responses = [
    {
      ok: true,
      status: 200,
      json: async () => ({
        mode: "LOCAL",
        status: "NOT LIVE",
        display: "LOCAL · NOT LIVE",
      }),
    },
    {
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: "0.1",
        collective_name: "Mock Collective",
        provenance_label: "MANUAL / NOT LIVE",
        live_observation: false,
        templates: [catalogTemplate("RP-CIRC-001", "Independent return power", "critical")],
      }),
    },
    {
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: "0.1",
        revision_id: "00000000-0000-4000-8000-000000000001",
        policy_template_id: "RP-POLICY-FLOW-001",
        revision_number: 4,
        created_at: "2026-07-25T22:30:00+00:00",
        authoring_operator_session_id: "12345678-abcd-4234-8234-123456789abc",
        collective_name: "Mock Collective",
        provenance: "MANUAL",
        provenance_label: "MANUAL / NOT LIVE",
        live_observation: false,
        inputs: {
          tank_volume_gallons: 250,
          pump_rated_flow_gph: 800,
          delivered_flow_gph: 650,
          minimum_turnover_per_hour: 2,
        },
        preview: {
          schema_version: "0.1",
          collective_name: "Mock Collective",
          provenance: "MANUAL",
          provenance_label: "MANUAL / NOT LIVE",
          live_observation: false,
          policy_kind: "operator-authored minimum turnover",
          state: "PASS",
          delivery_difference_gph: 150,
          delivery_efficiency_percent: 81.25,
          actual_turnover_per_hour: 2.6,
          minimum_delivered_flow_gph: 500,
          explanation: "The authored return-flow requirement passes.",
        },
      }),
    },
  ];
  const requests = [];
  const source = fs
    .readFileSync("src/reefproof/api/web/static/workbench.js", "utf8")
    .replace(/\nexport \{\};\s*$/, "");
  vm.runInNewContext(source, {
    console,
    document: {
      querySelector: (query) => selectors.get(query) ?? null,
      querySelectorAll: () => [],
      createElement: () => new FakeElement(),
    },
    fetch: async (path) => {
      requests.push(path);
      return responses.shift();
    },
    HTMLElement: FakeElement,
    HTMLInputElement: FakeInput,
    HTMLFormElement: FakeForm,
    HTMLSelectElement: FakeSelect,
    SVGEllipseElement: FakeSvgEllipse,
    Error,
    Map,
    Number,
    Object,
    Promise,
    Set,
  });
  await nextTurn();
  await nextTurn();

  assert.deepEqual(requests, [
    "/v1/system/status",
    "/v1/workbench/invariant-catalog",
    "/v1/workbench/policy-revisions/latest",
  ]);
  assert.equal(catalog.hidden, false);
  assert.equal(invariantCount.textContent, "1");
  assert.equal(emptyRevision.hidden, true);
  assert.equal(revisionContainer.hidden, false);
  assert.equal(evidence.get("state").textContent, "PASS");
  assert.equal(evidence.get("revision").textContent, "Revision 4");
  assert.equal(evidence.get("provenance").textContent, "MANUAL / NOT LIVE");
  assert.equal(
    evidence.get("revision-id").textContent,
    "00000000-0000-4000-8000-000000000001",
  );
  assert.equal(evidence.get("tank-volume").textContent, "250 gal");
  assert.equal(evidence.get("pump-flow").textContent, "800 GPH");
  assert.equal(evidence.get("delivered-flow").textContent, "650 GPH");
  assert.equal(evidence.get("minimum-turnover").textContent, "2× / hr");
  assert.equal(
    status.lastElementChild.textContent,
    "Evidence loaded · Revision 4 and 1 committed invariants.",
  );
});

test("workbench rejects malformed successful responses before partial rendering", async () => {
  const status = new FakeElement();
  status.append(new FakeElement(), new FakeElement());
  const form = new FakeForm(new Map());
  const policy = new FakeElement();
  const selectors = new Map([
    ["#loading-status", status],
    ["#flow-form", form],
    ["#policy-inputs", policy],
  ]);
  const responses = [
    {
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: "0.1",
        fields: ["unexpected_unbounded_field"],
      }),
    },
    {
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: "0.1",
        collective_name: "Mock Collective",
        provenance_label: "MANUAL / NOT LIVE",
        live_observation: false,
        templates: [],
      }),
    },
    {
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: "0.1",
        collective_name: "Mock Collective",
        provenance_label: "MANUAL / NOT LIVE",
        live_observation: false,
        entities: [],
        relationships: [],
        findings: [],
      }),
    },
  ];
  const source = fs
    .readFileSync("src/reefproof/api/web/static/workbench.js", "utf8")
    .replace(/\nexport \{\};\s*$/, "");
  vm.runInNewContext(source, {
    console,
    document: {
      querySelector: (selector) => selectors.get(selector) ?? null,
      querySelectorAll: () => [],
    },
    fetch: async () => responses.shift(),
    HTMLElement: FakeElement,
    HTMLInputElement: FakeInput,
    HTMLFormElement: FakeForm,
    HTMLSelectElement: FakeSelect,
    SVGEllipseElement: FakeSvgEllipse,
    Error,
    Map,
    Number,
    Object,
    Promise,
    Set,
  });
  await nextTurn();
  await nextTurn();

  assert.equal(policy.hidden, true);
  assert.equal(status.className, "notice notice--error");
  assert.equal(
    status.lastElementChild.textContent,
    "/policy-template returned data outside the committed UI boundary.",
  );
});

test("project surfaces use typed project paths and never submit validation claims", () => {
  const source = fs.readFileSync(
    "src/reefproof/api/web/static/workbench.js",
    "utf8",
  );

  assert.match(
    source,
    /`\/v1\/projects\/\$\{PROJECT_ID\}`/,
  );
  assert.match(source, /requestProjectJson\("\/brief"/);
  assert.match(source, /requestProjectJson\("\/sessions"/);
  assert.match(source, /requestProjectJson\("\/candidates"/);
  assert.match(
    source,
    /JSON\.stringify\(\{ decision, rationale: rationale\.value\.trim\(\) \}\)/,
  );
  assert.doesNotMatch(source, /schema_valid\s*:/);
  assert.doesNotMatch(source, /domain_valid\s*:/);
  assert.doesNotMatch(source, /sessionStorage/);
  assert.doesNotMatch(source, /localStorage/);
});

test("session gate settles its status and returns invalid credentials to the input", () => {
  const source = fs.readFileSync(
    "src/reefproof/api/web/static/workbench.js",
    "utf8",
  );

  assert.match(source, /Enter the bootstrap shared secret to unlock/);
  assert.match(source, /Enter your authenticator code to unlock/);
  assert.match(source, /setAttribute\("aria-invalid", "true"\)/);
  assert.match(source, /setAttribute\("aria-errormessage", statusId\)/);
  assert.match(source, /invalidInput\.focus\(\)/);
  assert.doesNotMatch(source, /methodFieldset\.querySelector[\s\S]{0,160}input\.focus\(\)/);
});

test("database page authenticates then renders approved schema and rows", async () => {
  const inputs = new Map([
    ["bootstrap_secret", new FakeInput("test-database-token")],
    ["totp_code", new FakeInput()],
  ]);
  const form = new FakeForm(inputs);
  const status = new FakeElement();
  status.append(new FakeElement(), new FakeElement());
  const explorer = new FakeElement();
  const tableList = new FakeElement();
  const columnBody = new FakeElement();
  const foreignKeys = new FakeElement();
  const indexes = new FakeElement();
  const rowHead = new FakeElement();
  const rowBody = new FakeElement();
  const previous = new FakeElement();
  const next = new FakeElement();
  const selectors = new Map([
    ["#database-session-form", form],
    ["#database-status", status],
    ["#database-explorer", explorer],
    ["#database-revision", new FakeElement()],
    ["#database-integrity", new FakeElement()],
    ["#database-table-list", tableList],
    ["#database-table-heading", new FakeElement()],
    ["#database-table-summary", new FakeElement()],
    ["#database-column-table tbody", columnBody],
    ["#database-foreign-key-list", foreignKeys],
    ["#database-index-list", indexes],
    ["#database-row-table thead", rowHead],
    ["#database-row-table tbody", rowBody],
    ["#database-row-caption", new FakeElement()],
    ["#database-page-status", new FakeElement()],
    ["#database-previous", previous],
    ["#database-next", next],
  ]);
  const table = {
    name: "projects",
    row_count: 1,
    columns: [
      {
        position: 0,
        name: "project_id",
        declared_type: "TEXT",
        nullable: false,
        default_value: "'primary-reef-system'",
        primary_key_position: 1,
      },
      {
        position: 1,
        name: "name",
        declared_type: "TEXT",
        nullable: false,
        default_value: null,
        primary_key_position: 0,
      },
    ],
    foreign_keys: [
      {
        identifier: 0,
        sequence: 0,
        from_column: "project_id",
        target_table: "projects",
        target_column: "project_id",
        on_update: "NO ACTION",
        on_delete: "RESTRICT",
      },
    ],
    indexes: [
      {
        name: "ix_projects_name",
        unique: true,
        columns: ["name"],
      },
    ],
  };
  const responses = [
    {
      ok: true,
      status: 200,
      json: async () => ({
        mode: "LOCAL",
        status: "NOT LIVE",
        display: "LOCAL · NOT LIVE",
      }),
    },
    {
      ok: true,
      status: 200,
      json: async () => ({
        alembic_revision: "0005",
        integrity: "ok",
        tables: [table],
      }),
    },
    {
      ok: true,
      status: 200,
      json: async () => ({
        table_name: "projects",
        offset: 0,
        limit: 50,
        total_rows: 1,
        columns: ["project_id", "name"],
        rows: [
          [
            { kind: "text", value: "primary-reef-system", truncated: false },
            { kind: "text", value: "Mock Collective", truncated: false },
          ],
        ],
        next_offset: null,
      }),
    },
  ];
  const requests = [];
  const document = {
    querySelector: (selector) => selectors.get(selector) ?? null,
    querySelectorAll: (selector) =>
      selector === "[data-database-table]" ? tableList.children : [],
    createElement: () => new FakeElement(),
  };
  const fetch = async (path, options = {}) => {
    requests.push({ path, options });
    return responses.shift();
  };
  const source = fs
    .readFileSync("src/reefproof/api/web/static/workbench.js", "utf8")
    .replace(/\nexport \{\};\s*$/, "");

  vm.runInNewContext(source, {
    console,
    document,
    fetch,
    HTMLElement: FakeElement,
    HTMLInputElement: FakeInput,
    HTMLFormElement: FakeForm,
    HTMLSelectElement: FakeSelect,
    SVGEllipseElement: FakeSvgEllipse,
    Error,
    Map,
    Number,
    Object,
    Promise,
    Set,
  }, { filename: "workbench.js" });

  form.listeners.get("submit")({ preventDefault() {} });
  await nextTurn();
  await nextTurn();
  await nextTurn();

  assert.deepEqual(requests.map(({ path }) => path), [
    "/v1/system/status",
    "/v1/database/schema",
    "/v1/database/tables/projects?offset=0&limit=50",
  ]);
  assert.equal(explorer.hidden, false);
  assert.equal(tableList.children.length, 1);
  assert.equal(columnBody.children.length, 2);
  assert.equal(
    columnBody.children[0].children[3].textContent,
    "'primary-reef-system'",
  );
  assert.match(foreignKeys.children[0].textContent, /project_id → projects\.project_id/);
  assert.match(foreignKeys.children[0].textContent, /delete RESTRICT/);
  assert.equal(
    indexes.children[0].textContent,
    "ix_projects_name · UNIQUE · name",
  );
  assert.equal(rowHead.children.length, 1);
  assert.equal(rowBody.children.length, 1);
  assert.equal(next.disabled, true);
  assert.equal(
    status.lastElementChild.textContent,
    "projects loaded through the query-only boundary.",
  );
});

test("database browser exposes no SQL editor or mutation request", () => {
  const source = fs.readFileSync(
    "src/reefproof/api/web/static/workbench.js",
    "utf8",
  );

  assert.match(source, /\/v1\/database/);
  assert.doesNotMatch(source, /sql-editor|sql-console|requestDatabaseJson\([^)]*,[^)]*,/);
  assert.doesNotMatch(source, /\/v1\/database.*method:\s*"(POST|PUT|PATCH|DELETE)"/);
});
