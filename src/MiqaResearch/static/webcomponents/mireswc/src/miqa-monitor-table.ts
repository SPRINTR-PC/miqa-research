import { css, html, LitElement, type PropertyValues } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { repeat } from 'lit/directives/repeat.js';
import type { MiqaMonitorColumn, MiqaMonitorTableData } from "./miqa-monitor-interfaces.ts";
import { globalStyles } from "./styles.ts";

@customElement('miqa-monitor-table')
export class MiqaMonitorTable extends LitElement {
    @property({ type: Object })
    public selectedColumns: MiqaMonitorColumn[] = [];

    @property({ type: Object })
    public tableData: MiqaMonitorTableData = {
        columns: []
    };
    
    @property({ type: String })
    public noDataAvailableString: string = 'No data available';   

    @state()
    private _rows: any[][] = [];

    static styles = [
        globalStyles,
        css`
          .table-container {
              overflow: auto;
          }  
          table {
              text-indent: 0;
              border-collapse: collapse;
              border-color: inherit;
              font-size: var(--mires-font-size-small, .875rem);
              line-height: var(--mires-line-height-small, 1.25rem);
          }
          thead {
              background-color: var(--color-background-darker);
          }  
          thead tr th {
            padding: .75rem 1rem;
          }
        `
    ];

    protected willUpdate(_changedProperties: PropertyValues) {
        if (_changedProperties.has('tableData')) {
            this._preCalculateRows();
        }
    }

    private _preCalculateRows() {
        this.tableData = this.tableData == null ? { columns: [] } : this.tableData;
        if (this.tableData.columns.length === 0) {
            this._rows = [];
            return;
        }

        const rowCount = this.tableData.columns[0].values.length;
        const columnCount = this.tableData.columns.length;
        const newRows = new Array(rowCount);

        for (let i = 0; i < rowCount; i++) {
            const row = new Array(columnCount);
            for (let j = 0; j < columnCount; j++) {
                row[j] = this.tableData.columns[j].values[i];
            }
            newRows[i] = row;
        }
        this._rows = newRows;
    }

    render() {
        this.selectedColumns = this.selectedColumns == null ? [] : this.selectedColumns;

        return html`
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  ${this.tableData.columns.length === 0 ?
                      (this.selectedColumns.length === 0 ?
                          html`<th></th>` :
                          this.selectedColumns.map(column => html`<th>${column.title}</th>`)
                      ) :
                      this.tableData.columns.map(column => html`<th>${column.header}</th>`)
                  }
                </tr>
              </thead>
              <tbody>
                ${this._mapTableDataToRows()}
              </tbody>
            </table>
          </div>
        `;
    }
    
    private _mapTableDataToRows() {
        if (this._rows.length === 0) return html`<tr><td colspan="${this.selectedColumns.length}">${this.noDataAvailableString}</td></tr>`;

        return html`
            ${repeat(
                this._rows,
                (_row, index) => index,
                (row) => html`
                    <tr>
                        ${row.map(value => html`<td>${value}</td>`)}
                    </tr>
                `
            )}
        `;
    }
}