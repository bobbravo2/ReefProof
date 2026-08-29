import type { components } from "../workbench-contracts.js";

type DatabaseSchema = components["schemas"]["DatabaseSchema"];
type DatabaseTableSchema = components["schemas"]["TableSchema"];
type DatabaseTablePage = components["schemas"]["TablePage"];
type DatabaseCell = components["schemas"]["DatabaseCell"];
type JsonRecord = Record<string, unknown>;
type Validator<T> = (value: unknown) => value is T;

export type DatabasePageServices = Readonly<{
  request: <T>(path: string, validator: Validator<T>) => Promise<T>;
  requiredElement: <T extends Element>(selector: string) => T;
  setStatus: (
    selector: string,
    message: string,
    state: "ready" | "error" | "empty",
  ) => void;
  toErrorMessage: (error: unknown, fallback: string) => string;
}>;

const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const isString = (value: unknown): value is string => typeof value === "string";
const isBoolean = (value: unknown): value is boolean => typeof value === "boolean";
const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);
const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(isString);
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
  ) return false;
  const columns = value.columns;
  return value.rows.every(
    (row) =>
      Array.isArray(row) &&
      row.length === columns.length &&
      row.every(isDatabaseCell),
  );
};

const renderColumns = (
  services: DatabasePageServices,
  table: DatabaseTableSchema,
): void => {
  services.requiredElement<HTMLElement>("#database-table-heading").textContent = table.name;
  services.requiredElement<HTMLElement>("#database-table-summary").textContent =
    `${table.row_count} stored row(s) · ${table.columns.length} column(s) · ` +
    `${table.foreign_keys.length} foreign key(s) · ${table.indexes.length} index(es)`;
  const body = services.requiredElement<HTMLTableSectionElement>("#database-column-table tbody");
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
    key.textContent = column.primary_key_position > 0
      ? `PRIMARY ${column.primary_key_position}`
      : "—";
    row.append(name, declaredType, nullable, defaultValue, key);
    body.append(row);
  });
  const renderList = (selector: string, values: readonly string[], empty: string): void => {
    const list = services.requiredElement<HTMLElement>(selector);
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
      (foreignKey) =>
        `${foreignKey.from_column} → ${foreignKey.target_table}.` +
        `${foreignKey.target_column ?? "(rowid)"} · update ${foreignKey.on_update} · ` +
        `delete ${foreignKey.on_delete}`,
    ),
    "No foreign keys",
  );
  renderList(
    "#database-index-list",
    table.indexes.map(
      (index) =>
        `${index.name} · ${index.unique ? "UNIQUE" : "NON-UNIQUE"} · ` +
        `${index.columns.join(", ") || "(expression)"}`,
    ),
    "No indexes",
  );
};

const renderPage = (services: DatabasePageServices, page: DatabaseTablePage): void => {
  const head = services.requiredElement<HTMLTableSectionElement>("#database-row-table thead");
  const body = services.requiredElement<HTMLTableSectionElement>("#database-row-table tbody");
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
      value.textContent = cell.kind === "null"
        ? "NULL"
        : `${String(cell.value)}${cell.truncated ? "…" : ""}`;
      row.append(value);
    });
    body.append(row);
  });
  const first = page.total_rows === 0 ? 0 : page.offset + 1;
  const last = page.offset + page.rows.length;
  services.requiredElement<HTMLElement>("#database-row-caption").textContent =
    `${page.table_name}: approved columns only, rows ${first}–${last} of ${page.total_rows}.`;
  services.requiredElement<HTMLElement>("#database-page-status").textContent =
    `${first}–${last} of ${page.total_rows}`;
  services.requiredElement<HTMLButtonElement>("#database-previous").disabled = page.offset === 0;
  services.requiredElement<HTMLButtonElement>("#database-next").disabled = page.next_offset === null;
};

export const mountDatabasePage = async (services: DatabasePageServices): Promise<void> => {
  let selectedTable: DatabaseTableSchema | null = null;
  let currentPage: DatabaseTablePage | null = null;
  const selectTable = async (table: DatabaseTableSchema, offset = 0): Promise<void> => {
    selectedTable = table;
    document.querySelectorAll<HTMLButtonElement>("[data-database-table]").forEach((button) => {
      button.setAttribute("aria-current", String(button.dataset.databaseTable === table.name));
    });
    renderColumns(services, table);
    currentPage = await services.request(
      `/tables/${encodeURIComponent(table.name)}?offset=${offset}&limit=50`,
      isDatabaseTablePage,
    );
    renderPage(services, currentPage);
    services.setStatus(
      "#database-status",
      `${table.name} loaded through the query-only boundary.`,
      "ready",
    );
  };
  const load = async (): Promise<void> => {
    const schema = await services.request("/schema", isDatabaseSchema);
    services.requiredElement<HTMLElement>("#database-revision").textContent = schema.alembic_revision;
    services.requiredElement<HTMLElement>("#database-integrity").textContent = schema.integrity.toUpperCase();
    const tableList = services.requiredElement<HTMLElement>("#database-table-list");
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
    services.requiredElement<HTMLElement>("#database-explorer").hidden = false;
    if (schema.tables.length === 0) {
      services.setStatus("#database-status", "No approved tables are present.", "empty");
      return;
    }
    await selectTable(schema.tables[0]!);
  };
  const reportFailure = (error: unknown): void => {
    services.setStatus(
      "#database-status",
      services.toErrorMessage(error, "Database inspection failed."),
      "error",
    );
  };
  services.requiredElement<HTMLFormElement>("#database-session-form").addEventListener(
    "submit",
    (event) => {
      event.preventDefault();
      void load().catch(reportFailure);
    },
  );
  services.requiredElement<HTMLButtonElement>("#database-previous").addEventListener(
    "click",
    () => {
      if (selectedTable !== null && currentPage !== null) {
        void selectTable(selectedTable, Math.max(0, currentPage.offset - currentPage.limit));
      }
    },
  );
  services.requiredElement<HTMLButtonElement>("#database-next").addEventListener(
    "click",
    () => {
      if (selectedTable !== null && currentPage?.next_offset !== null) {
        void selectTable(selectedTable, currentPage!.next_offset!);
      }
    },
  );
  await load();
};
