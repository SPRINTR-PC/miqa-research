import { LitElement, html, css, nothing } from "lit";
import type { PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { unsafeHTML } from 'lit/directives/unsafe-html.js';

import { snakeToCamelDeep } from "../snake-to-camel";
import { ApiService } from "./api-service";
import { formatDate, formatDateTime } from "./data-table-format";
import type {
  ColumnDefinition,
  DataRow,
  DataTableResponse,
  DataTableWireResponse,
  HslColor,
  PaginationMeta,
  SortDescriptor,
  SortState,
} from "./data-table-interfaces";
import {globalStyles} from "../../styles.ts";


export const getPercentageTwoDecimals = (part: number, whole: number): string =>
  parseFloat(`${(part / whole) * 100}`).toFixed(2);

@customElement("data-table")
export class DataTable extends LitElement {
  static styles = [
    globalStyles,
    css`
    :host {
      --dt-background-divs: var(--clr-background, #000);
      --dt-color-divs: var(--clr-text, #fff);
      --dt-header-background: var(--table-header-background, var(--form-color-background));
      --dt-header-color: var(--table-header-color, var(--form-color-text));
      --dt-background-even: var(--table-background-even, var(--form-color-background-input-focus));
      --dt-color-text-even: var(--table-color-text-even, var(--form-color-text));
      --dt-background: var(--table-background, var(--dt-background-even));
      --dt-color-text: var(--table-color-text, var(--dt-color-text-even));
      --dt-border-radius: var(--table-border-radius, 0.3rem);
      --dt-background-odd: var(--table-background-odd, var(--form-color-background));
      --dt-color-text-odd: var(--table-color-text-odd, var(--form-color-text));
      --dt-table-background-warning: var(--table-background-warning, #ffd800);
      --dt-table-background-critical: var(--table-background-critical, #562e2e);
      --dt-table-background-critical-hover: var(--table-background-critical-hover, #502626);
      --dt-font-family: var(--font-family, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif);
      --dt-font-size: var(--font-size, 1rem);
      --mini-barchart-bar-width: 6px;
      --mini-barchart-bar-gap: 2px;
      --mini-barchart-num-bars: var(--mini-barchart-bars, 10);
    }
        
    .mini-bar-chart {
        align-items: flex-end;
        display: flex;
        flex-direction: row;
        border-bottom: var(--dt-chart-border, 1px solid var(--dt-color-divs));
        height: 2rem;
        width: calc(var(--mini-barchart-bar-width) * var(--mini-barchart-num-bars) + var(--mini-barchart-bar-gap) * (var(--mini-barchart-num-bars) - 1))
    }
    .mini-bar-chart .mini-bar {
        background: var(--dt-color-divs);
        flex-shrink: 0;
        flex-grow: 0;
        width: var(--mini-barchart-bar-width);
    }
    .mini-bar-chart .mini-bar:not(:last-child) {
        margin-right: var(--mini-barchart-bar-gap);
    }
        
    .message {
      background: var(--dt-background-divs);
      font-family: var(--dt-font-family);
      color: var(--dt-color-text, #333);
      font-size: var(--dt-font-size);
      margin: 0;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      padding: 0;
      border-radius: var(--dt-border-radius);
    }
    
    table tbody tr {
        background: var(--dt-background);
        color: var(--dt-color-text);
    }
        
    table.striped tbody tr:nth-child(even) {
        background: var(--dt-background-even);
        color: var(--dt-color-text-even);
    }
        
    table.striped tbody tr:nth-of-type(2n+1) {
        background: var(--dt-background-odd);
        color: var(--dt-color-text-odd);
    }
        
    table.striped tbody tr:nth-of-type(2n+1).qc-status-warning {
      background-color: var(--dt-table-background-warning);
    }

    table.striped tbody tr:nth-of-type(2n+1).qc-status-critical {
      background-color: var(--dt-table-background-critical);
    }

    table.striped tbody tr:nth-of-type(2n+1).deleted-row {
        background-color: var(--dt-table-background-critical);
    }

    table.striped tbody tr:nth-of-type(2n+1).deleted-row:hover {
      background-color: var(--dt-table-background-critical-hover);
    }
        
    th {
        background-color: var(--dt-header-background);
        color: var(--dt-header-color);
    }

    th,
    td {
      text-align: left;
      padding: 0.5rem 0.75rem;
    }

    th.sortable {
      cursor: pointer;
      user-select: none;
    }
        
    th.sortable .header-content {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      width: 100%;
    }
    
    th.sortable .header-content span:last-child {
      margin-left: auto;
    }
    
    td {
      align-items: center;
      justify-content: center;
    }
        
    td.number-cell { text-align: end; }
        
    td.tooltip-cell {
      position: relative;
    }
    
    td.tooltip-cell .tooltip {
      visibility: hidden;
      background-color: var(--dt-header-background);
      color: var(--dt-header-color);
      display: grid;
      grid-template-rows: auto;
      border-radius: 5px;
      box-shadow: 5px 5px 5px 5px #000000;
      padding: 1em 2em 2em;
      z-index: 10;
      position: absolute;
      top: -125%;
      left: 90%;
      width: 13rem;

    }
    td.tooltip-cell .tooltip ul {
      list-style: disc outside none;
    }
    td.tooltip-cell:hover .tooltip { visibility: visible; }
        

    .pager {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      margin-top: 0.75rem;
    }

    .filter-row input,
    .filter-row select {
      width: 100%;
      box-sizing: border-box;
    }

    .range-filter {
      display: flex;
      gap: 0.25rem;
    }

    .range-filter input {
      min-width: 0;
    }
  `];

  @property({ type: String })
  dataUrl: string = "";

  @property({ type: String })
  noDataMessage: string = "No data available";

  @property({ type: String })
  loadingMessage: string = "Loading data...";

  @property({ type: String })
  errorMessage: string = "Something went wrong loading data.";

  @property({ type: Array })
  initialSort?: SortDescriptor[];

  @property({ type: Number })
  pageSize?: number;

  @property({ type: Boolean })
  striped: boolean = false;

  @state()
  private _columns: ColumnDefinition[] | undefined = undefined;

  @state()
  private _rows: DataRow[] | undefined = undefined;

  @state()
  private _isLoading: boolean = false;

  @state()
  private _hasError: boolean = false;

  @state()
  private _errorDetail: string | undefined = undefined;

  @state()
  private _pagination: PaginationMeta | undefined = undefined;

  @state()
  private _page: number = 1;

  @state()
  private _sortState: SortState = [];

  @state()
  private _filterValues: Record<string, string> = {};

  @state()
  private _rangeFilterValues: Record<string, { min?: string; max?: string }> = {};

  @state()
  private _multiSelectValues: Record<string, string[]> = {};

  private _filterDebounceTimers: Record<string, ReturnType<typeof setTimeout>> = {};

  connectedCallback() {
    super.connectedCallback();
    if (this.initialSort && this.initialSort.length > 0) {
      this._sortState = this.initialSort;
    }
    if (this.dataUrl) {
      void this._loadData();
    }
  }

  protected updated(changedProperties: PropertyValues) {
    super.updated(changedProperties);

    if (changedProperties.has("dataUrl") && changedProperties.get("dataUrl") !== undefined) {
      if (this.dataUrl) {
        this._page = 1;
        void this._loadData();
      } else {
        this._rows = undefined;
        this._columns = undefined;
        this._hasError = false;
        this._pagination = undefined;
      }
    }
  }

  private async _loadData() {
    this._isLoading = true;
    this._hasError = false;
    this._errorDetail = undefined;
    try {
      const response = await ApiService.getData<DataTableWireResponse>(this._buildRequestUrl());
      if (response.success && response.data) {
        // Row keys are column accessors (e.g. `clinic__clinic_name`) that are sent back for sort/filter, so only the
        // envelope is converted from snake_case.
        const { columns, pagination } = snakeToCamelDeep<Pick<DataTableResponse, "columns" | "pagination">>({
          columns: response.data.columns,
          pagination: response.data.pagination,
        });
        if (columns && !this._columns && this._sortState.length === 0) {
          this._sortState = this._defaultSortFrom(columns);
        }
        this._rows = response.data.rows;
        this._columns = columns ?? this._columns ?? this._deriveColumnsFromRows(response.data.rows);
        this._pagination = pagination;
        this._page = pagination.page;
      } else {
        this._rows = undefined;
        this._columns = undefined;
        this._pagination = undefined;
        this._hasError = true;
      }
    } catch (error) {
      this._rows = undefined;
      this._columns = undefined;
      this._pagination = undefined;
      this._hasError = true;
      this._errorDetail = error instanceof Error ? error.message : String(error);
    } finally {
      this._isLoading = false;
    }
  }

  private _renderErrorMessage(): string {
    if (this.errorMessage.includes("{message}")) {
      return this.errorMessage.replace("{message}", this._errorDetail ?? "");
    }
    return this.errorMessage;
  }

  private _renderMiniBarChart(values: number[], color: HslColor, maxNumberOfBars: number = 10, withTdTag: boolean = true) {
    const trimmedValues = values.slice(-maxNumberOfBars);
    const largestValue = Math.max(...trimmedValues);
    return html`
      ${withTdTag ? html`<td class="tooltip-cell">` : ""}
        <div class="mini-bar-chart">
          ${trimmedValues.map(
            (value, i) => html`
              <div
                class="mini-bar"
                key="${i}_${value}/${largestValue}"
                style="
                  height: ${getPercentageTwoDecimals(value, largestValue)}%;
                  background: hsl(${color.hue}, ${color.saturation}%, ${color.lightness}%);
                "
                data-bar-value=${value}
                data-testid="mini-bar"
              />
            `
          )}
        </div>
        <div class="tooltip">
            <ul>
              ${trimmedValues.map((value, i) => html`<li>${i + 1}: ${value}</li>`)}
            </ul>
        </div>
      ${withTdTag ? html`</td>` : ""}
    `;
  }

  private _buildRequestUrl(): string {
    const pageSize = this._pagination?.pageSize ?? this.pageSize ?? 50;
    const separator = this.dataUrl.includes("?") ? "&" : "?";
    let url = `${this.dataUrl}${separator}page=${this._page}&page_size=${pageSize}`;
    if (!this._columns) {
      url += "&include_columns=true";
    }
    if (this._sortState.length > 0) {
      const sortParam = this._sortState
        .map((descriptor) => (descriptor.direction === "desc" ? `-${descriptor.column}` : descriptor.column))
        .join(",");
      url += `&sort=${sortParam}`;
    }
    url += this._buildFilterQueryString();
    return url;
  }

  private _buildFilterQueryString(): string {
    if (!this._columns) return "";
    const parts: string[] = [];
    for (const column of this._columns) {
      const filter = column.filter;
      if (!filter) continue;

      if (filter.kind === "numeric-range" || filter.kind === "date-range") {
        const range = this._rangeFilterValues[column.accessor];
        if (range?.min) parts.push(`${column.accessor}__gte=${encodeURIComponent(range.min)}`);
        if (range?.max) parts.push(`${column.accessor}__lte=${encodeURIComponent(range.max)}`);
        continue;
      }

      if (filter.kind === "multi-select") {
        const selected = this._multiSelectValues[column.accessor];
        if (selected && selected.length > 0) {
          parts.push(`${column.accessor}__in=${encodeURIComponent(selected.join(","))}`);
        }
        continue;
      }

      const value = this._filterValues[column.accessor];
      if (value === undefined || value === "") continue;
      const key = filter.kind === "text" ? `${column.accessor}__icontains` : column.accessor;
      parts.push(`${key}=${encodeURIComponent(value)}`);
    }
    return parts.length > 0 ? `&${parts.join("&")}` : "";
  }

  private _goToPage(page: number) {
    this._page = page;
    void this._loadData();
  }

  private _handleHeaderClick(column: ColumnDefinition, shiftKey: boolean) {
    if (!column.sortable) return;

    const existingIndex = this._sortState.findIndex((descriptor) => descriptor.column === column.accessor);

    if (shiftKey) {
      if (existingIndex >= 0) {
        const next = [...this._sortState];
        next[existingIndex] = {
          ...next[existingIndex],
          direction: next[existingIndex].direction === "asc" ? "desc" : "asc",
        };
        this._sortState = next;
      } else {
        this._sortState = [...this._sortState, { column: column.accessor, direction: "asc" }];
      }
    } else {
      const isSoleActiveSort = this._sortState.length === 1 && existingIndex === 0;
      if (isSoleActiveSort) {
        this._sortState = [
          { column: column.accessor, direction: this._sortState[0].direction === "asc" ? "desc" : "asc" },
        ];
      } else {
        this._sortState = [{ column: column.accessor, direction: "asc" }];
      }
    }

    this._page = 1;
    void this._loadData();
  }

  private _handleFilterInput(column: ColumnDefinition, value: string, debounceMs: number) {
    this._filterValues = { ...this._filterValues, [column.accessor]: value };

    clearTimeout(this._filterDebounceTimers[column.accessor]);
    if (debounceMs > 0) {
      this._filterDebounceTimers[column.accessor] = setTimeout(() => this._applyFilters(), debounceMs);
    } else {
      this._applyFilters();
    }
  }

  private _handleRangeFilterInput(column: ColumnDefinition, bound: "min" | "max", value: string, debounceMs: number) {
    const current = this._rangeFilterValues[column.accessor] ?? {};
    this._rangeFilterValues = { ...this._rangeFilterValues, [column.accessor]: { ...current, [bound]: value } };

    const timerKey = `${column.accessor}:${bound}`;
    clearTimeout(this._filterDebounceTimers[timerKey]);
    if (debounceMs > 0) {
      this._filterDebounceTimers[timerKey] = setTimeout(() => this._applyFilters(), debounceMs);
    } else {
      this._applyFilters();
    }
  }

  private _handleMultiSelectInput(column: ColumnDefinition, values: string[]) {
    this._multiSelectValues = { ...this._multiSelectValues, [column.accessor]: values };
    this._applyFilters();
  }

  private _applyFilters() {
    this._page = 1;
    void this._loadData();
  }

  // The server already applies the declared default when no sort is sent; seeding keeps the sort indicators and later
  // requests consistent with it.
  private _defaultSortFrom(columns: ColumnDefinition[]): SortState {
    return columns
      .flatMap((column) => (column.defaultSort ? [{ column, direction: column.defaultSort }] : []))
      .sort((a, b) => (a.column.defaultSortOrder ?? columns.length) - (b.column.defaultSortOrder ?? columns.length))
      .map(({ column, direction }) => ({ column: column.accessor, direction }));
  }

  private _deriveColumnsFromRows(rows: DataRow[]): ColumnDefinition[] | undefined {
    const firstRow = rows[0];
    if (!firstRow) return undefined;
    return Object.keys(firstRow).map((key) => ({ accessor: key, label: key }));
  }

  render() {
    if (this._isLoading) {
      return html`<p class="message">${this.loadingMessage}</p>`;
    }

    if (this._hasError) {
      return html`<p class="message">${this._renderErrorMessage()}</p>`;
    }

    if (!this._rows || this._rows.length === 0 || !this._columns) {
      return html`<p class="message">${this.noDataMessage}</p>`;
    }

    const columns = this._columns;
    const rows = this._rows;

    return html`
      <table class="${this.striped ? "striped" : ""}">
        <thead>
          <tr>
            ${columns.map((column) => this._renderHeader(column))}
          </tr>
          ${columns.some((column) => column.filter)
            ? html`<tr class="filter-row">
                ${columns.map((column) => html`<th>${this._renderFilterControl(column)}</th>`)}
              </tr>`
            : nothing}
        </thead>
        <tbody>
          ${rows.map(
            (row) => html`
              <tr>
                ${columns.map((column) => {
                    return column.dataType === "mini-barchart" 
                            ? this._renderMiniBarChart(
                               Array.isArray(this._resolveAccessor(row, column.accessor))
                                ? (this._resolveAccessor(row, column.accessor) as number[])
                                : [],
                              column.hslColor ?? { hue: 200, saturation: 100, lightness: 50 })
                            : html`<td>${this._formatCellValue(column, this._resolveAccessor(row, column.accessor))}</td>`;
                })}
              </tr>
            `
          )}
        </tbody>
      </table>
      ${this._renderPager()}
    `;
  }

  private _formatCellValue(column: ColumnDefinition, value: unknown) {
    switch (column.dataType) {
      case "date":
        return formatDate(value);
      case "datetime":
        return formatDateTime(value);
      default:
        return value ?? nothing;
    }
  }

  private _renderHeader(column: ColumnDefinition) {
    if (!column.sortable) {
      if (column.htmlLabel) {
        return html`<th >${unsafeHTML(column.label)}</th>`;
      }
      return html`<th>${column.label}</th>`;
    }

    const sortIndex = this._sortState.findIndex((descriptor) => descriptor.column === column.accessor);
    const sortDescriptor = sortIndex >= 0 ? this._sortState[sortIndex] : undefined;
    const sortOrderNumber = sortIndex >= 0 && this._sortState.length > 1 ? sortIndex + 1 : undefined;
    const indicator = sortDescriptor ? (sortDescriptor.direction === "asc" ? "▲ " : "▼ ") : "▶ ";

    return html`<th
      class="sortable"
      @click=${(event: MouseEvent) => this._handleHeaderClick(column, event.shiftKey)}
      ><div class="header-content"><span>${indicator}${column.htmlLabel ? unsafeHTML(column.label) : column.label}</span><span>${sortOrderNumber}</span></div></th
    >`;
  }

  private _renderFilterControl(column: ColumnDefinition) {
    const filter = column.filter;
    if (!filter) return nothing;
    const currentValue = this._filterValues[column.accessor] ?? "";

    switch (filter.kind) {
      case "text":
      case "text-exact": // sent as `<accessor>=<value>`, see _buildFilterQueryString
        return html`<input
          type="text"
          data-filter-accessor=${column.accessor}
          .value=${currentValue}
          @input=${(event: Event) => this._handleFilterInput(column, (event.target as HTMLInputElement).value, 300)}
        />`;
      case "numeric":
        return html`<input
          type="number"
          data-filter-accessor=${column.accessor}
          .value=${currentValue}
          @input=${(event: Event) => this._handleFilterInput(column, (event.target as HTMLInputElement).value, 300)}
        />`;
      case "dropdown":
        return html`<select
          data-filter-accessor=${column.accessor}
          .value=${currentValue}
          @change=${(event: Event) => this._handleFilterInput(column, (event.target as HTMLSelectElement).value, 0)}
        >
          <option value="">Any</option>
          ${(filter.options ?? []).map((option) => html`<option value=${option.value}>${option.label}</option>`)}
        </select>`;
      case "boolean":
        return html`<select
          data-filter-accessor=${column.accessor}
          .value=${currentValue}
          @change=${(event: Event) => this._handleFilterInput(column, (event.target as HTMLSelectElement).value, 0)}
        >
          <option value="">Either</option>
          <option value="true">${filter.trueLabel ?? "Yes"}</option>
          <option value="false">${filter.falseLabel ?? "No"}</option>
        </select>`;
      case "numeric-range": {
        const range = this._rangeFilterValues[column.accessor] ?? {};
        return html`<div class="range-filter" data-filter-accessor=${column.accessor}>
          <input
            type="number"
            placeholder="Min"
            data-filter-bound="min"
            .value=${range.min ?? ""}
            @input=${(event: Event) =>
              this._handleRangeFilterInput(column, "min", (event.target as HTMLInputElement).value, 300)}
          />
          <input
            type="number"
            placeholder="Max"
            data-filter-bound="max"
            .value=${range.max ?? ""}
            @input=${(event: Event) =>
              this._handleRangeFilterInput(column, "max", (event.target as HTMLInputElement).value, 300)}
          />
        </div>`;
      }
      case "date-range": {
        const range = this._rangeFilterValues[column.accessor] ?? {};
        return html`<div class="range-filter" data-filter-accessor=${column.accessor}>
          <input
            type="date"
            data-filter-bound="min"
            .value=${range.min ?? ""}
            @change=${(event: Event) =>
              this._handleRangeFilterInput(column, "min", (event.target as HTMLInputElement).value, 0)}
          />
          <input
            type="date"
            data-filter-bound="max"
            .value=${range.max ?? ""}
            @change=${(event: Event) =>
              this._handleRangeFilterInput(column, "max", (event.target as HTMLInputElement).value, 0)}
          />
        </div>`;
      }
      case "multi-select": {
        const selected = this._multiSelectValues[column.accessor] ?? [];
        return html`<select
          multiple
          data-filter-accessor=${column.accessor}
          @change=${(event: Event) =>
            this._handleMultiSelectInput(
              column,
              Array.from((event.target as HTMLSelectElement).selectedOptions).map((option) => option.value)
            )}
        >
          ${(filter.options ?? []).map(
            (option) =>
              html`<option value=${option.value} ?selected=${selected.includes(option.value)}>${option.label}</option>`
          )}
        </select>`;
      }
      default:
        return nothing;
    }
  }

  private _renderPager() {
    const pagination = this._pagination;
    if (!pagination || pagination.totalItems <= pagination.pageSize) return nothing;

    return html`
      <div class="pager">
        <button
          type="button"
          data-action="previous"
          ?disabled=${!pagination.hasPrevious}
          @click=${() => this._goToPage(pagination.page - 1)}
        >
          Previous
        </button>
        <span>Page ${pagination.page} of ${pagination.totalPages}</span>
        <button
          type="button"
          data-action="next"
          ?disabled=${!pagination.hasNext}
          @click=${() => this._goToPage(pagination.page + 1)}
        >
          Next
        </button>
      </div>
    `;
  }

  private _resolveAccessor(row: DataRow, accessor: string): unknown {
    return accessor.split(".").reduce<unknown>((value, segment) => {
      if (value === null || value === undefined || typeof value !== "object") return undefined;
      return (value as DataRow)[segment];
    }, row);
  }
}
