import { css, html, LitElement } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { MiqaMonitorColumn, MiqaMonitorFilter, MiqaMonitorTableData } from "./miqa-monitor-interfaces.ts";
import { globalStyles } from "./styles.ts";

@customElement('miqa-monitor')
export class MiqaMonitor extends LitElement {
    @property({ type: String })
    public apiUri: string = '';
    
    @property({ type: String })
    public columnListApiUri: string = '';
    
    @property({ type: String })
    public bookmarkApiUri: string = '';

    @property({ type: String })
    public bookmarkId: string = '';

    @property({ type: String })
    public monitorTitle: string = 'Monitor';

    @state()
    private monitorFilter: MiqaMonitorFilter = {
        gender: [],
        age: {
            min: 0,
            max: 200,
            selected_min: 0,
            selected_max: 200,
            include_null: true
        },
        studyDescription: [],
        seriesDescription: [],
    };

    @state()
    private _tableData: MiqaMonitorTableData = {
        columns: []
    };

    @state()
    private _availableColumns: MiqaMonitorColumn[] = [
        {
            id: 'patientName',
            title: 'Patient Name',
            dataType: 'string'
        },
        {
            id: 'patientAge',
            title: 'Patient Age',
            dataType: 'number'
        },
        {
            id: 'modality',
            title: 'Modality',
            dataType: 'string'
        },
        {
            id: 'studyDate',
            title: 'Study Date',
            dataType: 'date'
        },
        {
            id: 'studyTime',
            title: 'Study Time',
            dataType: 'time'
        }
    ];

    @state()
    private _selectedColumns: MiqaMonitorColumn[] = [];

    async connectedCallback() {
        super.connectedCallback();
        await this.fetchAvailableColumns();
    }

    private async fetchAvailableColumns() {
        if (!this.columnListApiUri) {
            return;
        }

        try {
            const response = await fetch(this.columnListApiUri);
            if (response.ok) {
                this._availableColumns = await response.json();
            } else {
                console.error('Failed to fetch columns:', response.statusText);
            }
        } catch (error) {
            console.error('Error fetching columns:', error);
        }
    }

    static styles = [
        globalStyles,
        css`
        #monitor-container {
            display: flex;
            flex-direction: column;
            gap: 1rem;
            position: relative;
        }
        
        miqa-monitor-filter {
            position: relative;
            z-index: 10;
            display: block;
            margin-bottom: 1rem;
            padding: 0;
        }
        
        miqa-monitor-table {
            padding: 0;
            position: relative;
            z-index: 1;
        }
        `
    ];

    render() {
      return html`
        <div id="monitor-container">
          <h1>${this.monitorTitle}</h1>
          <miqa-monitor-columns
            .availableColumns=${this._availableColumns}
            .selectedColumns=${this._selectedColumns}
            @column-selection-changed="${(e: CustomEvent) => this._selectedColumns = e.detail.selectedColumns}"
          ></miqa-monitor-columns>
          <miqa-monitor-filter
            .monitorFilter=${this.monitorFilter}
          ></miqa-monitor-filter>
          <miqa-monitor-table
            .selectedColumns=${this._selectedColumns}
            .tableData=${this._tableData}
          ></miqa-monitor-table>
        </div>
      `;
    }
}