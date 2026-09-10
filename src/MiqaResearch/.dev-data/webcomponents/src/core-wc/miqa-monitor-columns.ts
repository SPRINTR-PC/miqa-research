import { customElement, property, state } from "lit/decorators.js";
import {LitElement, html, css, type PropertyValues} from "lit";
import type { MiqaMonitorColumn } from "./miqa-monitor-interfaces.ts";
import { globalStyles } from "../styles.ts";
import { PanelRightOpen } from "../../icons.ts";


@customElement('miqa-monitor-columns')
export class MiqaMonitorColumns extends LitElement {
    @property({ type: Object })
    public availableColumns: MiqaMonitorColumn[] = [];

    @property({ type: Object })
    public selectedColumns: MiqaMonitorColumn[] = [];

    @state()
    private _collapsed: boolean = true;

    @state()
    private _showContent: boolean = false;

    @state()
    private _draggedColumnId: string | null = null;

    @state()
    private _dragOverColumnId: string | null = null;

    @state()
    private _visibleAvailableColumns: MiqaMonitorColumn[] = [];

    @state()
    private _visibleSelectedColumns: MiqaMonitorColumn[] = [];

    static styles = [
        globalStyles,
        css`
        :host {
            position: fixed;
            top: 0;
            right: 0;
            bottom: 0;
            z-index: 1000;
            pointer-events: none;
            padding: 0;
            border: none;
        }

        .drawer {
            position: absolute;
            top: 0;
            right: 0;
            bottom: 0;
            width: 30rem;
            background-color: var(--mires-color-background-darker);
            box-shadow: -2px 0 5px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s ease-in-out;
            display: flex;
            flex-direction: column;
            pointer-events: auto;
        }
            
        input {
            width: calc(100% - 0.8rem);
            padding: 0.5rem;
            box-sizing: border-box;
        }

        .drawer.collapsed {
            transform: translateX(100%);
            box-shadow: none;
        }
            
        .drawer button svg {
            fill: none;
            stroke: currentColor;
        }
            
        .drawer.expanded button svg {
            transform: rotate(180deg);
        }
            
        .toggle-button {
            position: absolute;
            left: -2.5em;
            top: 50%;
            transform: translateY(-50%);
            width: 2.5em;
            height: 3.75em;
            background-color: var(--mires-color-background-darker);
            border: 1px solid #ccc;
            border-right: none;
            border-radius: 1rem 0 0 1rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: -2px 0 5px rgba(0, 0, 0, 0.1);
        }

        .toggle-button:hover {
            background-color: hsl(from hsl(var(--mires-color-primary-parts)) h s calc(l / .5));
        }

        .drawer-content {
            padding: 16px;
            overflow-y: auto;
            flex-grow: 1;
        }
            
        .column-lists-container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.8rem;
        }
            
        .btn-list-container  {
            margin-top: 0.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.1rem;
        }
        
        .selected-columns-col {
            border-right: 1px solid var(--color-border, #ffff);
        }

        .column-btn {
            background-color: var(--mires-form-input-background);
            display: block;
            width: 95%;
            padding: 0.5rem 1rem;
            margin-bottom: 4px;
            text-align: left;
            cursor: pointer;
            border: 1px solid #ccc;
            box-sizing: border-box;
            border-radius: 1rem;
        }

        .selected-column-btn {
            cursor: grab;
            background-color: var(--color-primary);
        }

        .selected-column-btn:active {
            cursor: grabbing;
        }

        .selected-column-btn.dragging {
            opacity: 0.5;
        }

        .selected-column-btn.drag-over {
            border-top: 2px solid #007bff;
        }

        h3, h4 {
            margin-top: 0;
        }
    `];

    protected willUpdate(_changedProperties: PropertyValues) {
        if (_changedProperties.has('availableColumns') || _changedProperties.has('selectedColumns') || _changedProperties.has('columnsOrder')) {
            this._filterAvailableColumns(new Event('input'));
        }
    }

    render() {
        return html`
            <div class="drawer ${this._collapsed ? 'collapsed' : 'expanded'}" @transitionend="${this._handleTransitionEnd}">
                <button class="toggle-button" @click="${this._toggleCollapsed}">
                    ${PanelRightOpen}
                </button>
                ${this._showContent ? html`
                    <div class="drawer-content">
                        <div class="column-list-header">
                            <h3>Columns</h3>
                        </div>
                        <div class="column-lists-container">
                            <div class="selected-columns-col">
                                <h4>Selected</h4>
                                <input type="text" placeholder="Filter selected columns..." @input="${(e: Event) => this._filterSelectedColumns(e)}" />
                                <div class="btn-list-container">
                                ${this._visibleSelectedColumns.map(column =>
                                    html`<button 
                                            draggable="true"
                                            @dragstart="${(e: DragEvent) => this._handleDragStart(e, column.id)}"
                                            @dragover="${(e: DragEvent) => this._handleDragOver(e, column.id)}"
                                            @dragleave="${() => this._handleDragLeave(column.id)}"
                                            @drop="${(e: DragEvent) => this._handleDrop(e, column.id)}"
                                            @dragend="${this._handleDragEnd}"
                                            @click="${() => this._handleColumnDeselected(column.id)}" 
                                            class="column-btn selected-column-btn ${this._draggedColumnId === column.id ? 'dragging' : ''} ${this._dragOverColumnId === column.id ? 'drag-over' : ''}"
                                         >${column.title}</button>`)}
                                </div>
                            </div>
                            <div class="available-columns-col">
                                <h4>Available</h4>
                                <input type="text" placeholder="Filter available columns..." @input="${(e: Event) => this._filterAvailableColumns(e)}" />
                                <div class="btn-list-container">
                                ${this._visibleAvailableColumns.map(column =>
                                    html`<button @click="${() => this._handleColumnSelected(column.id)}" class="column-btn available-column-btn">${column.title}</button>`)}
                                </div>
                            </div>
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    private _filterAvailableColumns(event: Event) {
        const input = event.target as HTMLInputElement;
        this._visibleAvailableColumns = input == null || input.value == '' ?
            this.availableColumns.filter(column => !this.selectedColumns.some(c => c.id === column.id)) :
            this.availableColumns.filter(column =>
                column.title.toLowerCase().includes(input.value.toLowerCase()) &&
                !this.selectedColumns.some(c => c.id === column.id)
        );
    }

    private _filterSelectedColumns(event: Event) {
        const input = event.target as HTMLInputElement;
        this._visibleSelectedColumns = input == null || input.value == '' ?
            this.selectedColumns :
            this.selectedColumns.filter(column =>
            column.title.toLowerCase().includes(input.value.toLowerCase())
        );
    }

    private _toggleCollapsed() {
        if (this._collapsed) {
            this._showContent = true;
            // Use requestAnimationFrame to ensure _showContent is rendered before starting animation
            requestAnimationFrame(() => {
                this._collapsed = false;
            });
        } else {
            this._collapsed = true;
        }
    }

    private _handleTransitionEnd() {
        if (this._collapsed) {
            this._showContent = false;
        }
    }

    private _handleColumnSelected(columnId: string) {
        const column = this.availableColumns.find(c => c.id === columnId);
        if (column && !this.selectedColumns.some(c => c.id === columnId)) {
            this.selectedColumns = [...this.selectedColumns, column];
            this._filterSelectedColumns(new Event('input'));
            this._dispatchChanged();
        }
    }

    private _handleColumnDeselected(columnId: string) {
        this.selectedColumns = this.selectedColumns.filter(c => c.id !== columnId);
        this._filterSelectedColumns(new Event('input'));
        this._dispatchChanged();
    }

    private _handleDragStart(e: DragEvent, columnId: string) {
        this._draggedColumnId = columnId;
        if (e.dataTransfer) {
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', columnId);
        }
    }

    private _handleDragOver(e: DragEvent, columnId: string) {
        e.preventDefault();
        if (this._draggedColumnId !== columnId) {
            this._dragOverColumnId = columnId;
            if (e.dataTransfer) {
                e.dataTransfer.dropEffect = 'move';
            }
        }
    }

    private _handleDragLeave(columnId: string) {
        if (this._dragOverColumnId === columnId) {
            this._dragOverColumnId = null;
        }
    }

    private _handleDrop(e: DragEvent, targetColumnId: string) {
        e.preventDefault();
        const draggedColumnId = this._draggedColumnId;
        this._draggedColumnId = null;
        this._dragOverColumnId = null;

        if (draggedColumnId && draggedColumnId !== targetColumnId) {
            const oldIndex = this.selectedColumns.findIndex(c => c.id === draggedColumnId);
            const newIndex = this.selectedColumns.findIndex(c => c.id === targetColumnId);

            if (oldIndex !== -1 && newIndex !== -1) {
                const newSelectedColumns = [...this.selectedColumns];
                const [movedColumn] = newSelectedColumns.splice(oldIndex, 1);
                newSelectedColumns.splice(newIndex, 0, movedColumn);
                this.selectedColumns = newSelectedColumns;
                this._dispatchChanged();
            }
        }
    }

    private _handleDragEnd() {
        this._draggedColumnId = null;
        this._dragOverColumnId = null;
    }

    private _dispatchChanged() {
        this.dispatchEvent(new CustomEvent('column-selection-changed', {
            detail: { selectedColumns: this.selectedColumns },
            bubbles: true,
            composed: true
        }));
    }
}