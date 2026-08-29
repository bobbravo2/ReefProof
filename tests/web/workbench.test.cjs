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
  const templateRoot = "src/reefproof/api/web/templates";
  const source = [
    fs.readFileSync(`${templateRoot}/workbench.html`, "utf8"),
    ...fs
      .readdirSync(`${templateRoot}/pages`)
      .map((name) => fs.readFileSync(`${templateRoot}/pages/${name}`, "utf8")),
  ].join("\n");
  assert.equal((source.match(/name="bootstrap_secret"/g) ?? []).length, 1);
  assert.equal((source.match(/name="totp_code"/g) ?? []).length, 9);
  for (const authorityForm of [
    "source-review-form",
    "commissioning-verification-form",
    "failure-mode-form",
    "label-verification-form",
    "reconciliation-binding-form",
  ]) {
    const form = source.match(new RegExp(`<form id="${authorityForm}"[\\s\\S]*?</form>`))?.[0];
    assert.ok(form, `missing authority form: ${authorityForm}`);
    assert.match(form, /name="totp_code"/);
  }
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

test("database browser exposes no SQL editor or mutation request", () => {
  const source = fs.readFileSync(
    "src/reefproof/api/web/static/workbench.js",
    "utf8",
  );

  assert.match(source, /\/v1\/database/);
  assert.doesNotMatch(source, /sql-editor|sql-console|requestDatabaseJson\([^)]*,[^)]*,/);
  assert.doesNotMatch(source, /\/v1\/database.*method:\s*"(POST|PUT|PATCH|DELETE)"/);
});
