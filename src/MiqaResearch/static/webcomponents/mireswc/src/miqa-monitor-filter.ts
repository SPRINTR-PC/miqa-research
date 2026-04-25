import { customElement, property, state } from "lit/decorators.js";
import { LitElement, html, css } from "lit";
import type { MiqaMonitorColumn } from "./miqa-monitor-interfaces.ts";
import { globalStyles } from "./styles.ts";
import {KeyboardArrowDown, KeyboardArrowRight, Plus} from "../icons.ts";

@customElement('miqa-monitor-filter')
export class MiqaMonitorFilter extends LitElement {
    @property({ type: Object })
    public columns: MiqaMonitorColumn[] = [];

    @property({ type: String })
    public addString: string = 'Add';

    @property({ type: String })
    public advancedFilterString: string = 'Advanced filter';

    @property({ type: String })
    public modalityFilterString: string = 'Modality';

    @property({ type: String })
    public genderFilterString: string = 'Gender';

    @property({ type: String })
    public patientAgeFilterString: string = 'Patient Age';

    @property({ type: String })
    public studyDescriptionFilterString: string = 'Study Description';

    @property({ type: String })
    public seriesDescriptionFilterString: string = 'Series Description';

    @property({ type: String })
    public tagFilterString: string = 'Tag';

    @state()
    private _collapsed: boolean = true;

    @state()
    private _showContent: boolean = false;

    static styles = [
        globalStyles,
        css`
            .filter-container {
                box-sizing: border-box;
                color: var(--color-text);
                background-color: var(--color-card, #ffffff);
                box-shadow: -2px 0 5px rgba(0, 0, 0, 0.2);
                transition: transform 0.3s ease-in-out;
                border-radius: calc(var(--radius, .75rem) - 2px);
                position: absolute;
                width: 100%;
                z-index: 100;
                top: 0;
                left: 0;
            }
            
            :host {
                display: block;
                position: relative;
                height: 3.5rem;
            }
            
            .filter-header {
                width: 100%;
                display: grid;
                grid-template-columns: auto 1fr auto;
                align-items: center;
                gap: 0.5rem;
                cursor: pointer;
                padding: .75rem 1rem;
                box-sizing: border-box;
                border-radius: calc(var(--radius, .75rem) - 2px);
                border: 1px solid var(--color-border);
            }
            
            .filter-header.expanded {
                border-radius: calc(var(--radius, .75rem) - 2px) calc(var(--radius, .75rem) - 2px) 0 0;
            }
            
            .filter-header:hover {
                background-color: hsl(var(--color-primary-parts) / .5);
            }
            
            .filter-title {
                display: inline-flex;
                gap: .5rem;
                align-items: center;
            }
            
            .toggle-button {
                display: flex;
            }
            
            .toggle-button svg {
                width: 1.8rem;
                fill: currentColor;
                cursor: pointer;
            }
            
            .filter-group {
                width: 100%;
                display: grid;
                align-items: center;
                gap: 0.5rem;
                grid-template-columns: 10rem 1fr auto;
                box-sizing: border-box;
                padding: 0.8rem;
            }
            
            .filter-input {
                background-color: rebeccapurple;
            }
            
            .add-filter-button {
                display: inline-flex;
                gap: .5rem;
                padding: .2rem .5rem;
            }
            
            .add-filter-button svg {
                width: 1rem;
                height: 1rem;
                stroke: currentColor;
            }
        `
    ];

    render() {
        return html`
            <div class="filter-container">
              <div class="filter-header ${this._collapsed ? "" : "expanded"}" @click="${this._toggleCollapsed}">
                <div class="filter-title">
                  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-filter h-4 w-4 text-muted-foreground"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon></svg>
                  <span class="semibold text-sm">Filter</span>
                </div>
                <div class="selected-filter-summary"></div>
                <div class="toggle-button" >${this._collapsed ? KeyboardArrowRight : KeyboardArrowDown}</div>
              </div>
              <div class="filter-content ${this._collapsed ? "collapsed" : ""}" @transitionend="${this._handleTransitionEnd}">
                ${this._showContent ? html`
                  <div class="filter-group">
                    <div class="filter-label">${this.advancedFilterString}</div>
                    <div class="filter-input">Some content</div>
                    <button class="add-filter-button" @click=${this._handleAddAdvancedFilterClicked}>
                      ${Plus} ${this.addString}
                    </button>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.modalityFilterString}</div>
                    <div class="filter-input"></div>
                    <div></div>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.genderFilterString}</div>
                    <div class="filter-input"></div>
                    <div></div>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.patientAgeFilterString}</div>
                    <div class="filter-input"></div>
                    <div></div>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.studyDescriptionFilterString}</div>
                    <div class="filter-input"></div>
                    <button class="add-filter-button" @click=${this._handleAddStudyDescriptionFilterClicked}>
                      ${Plus} ${this.addString}
                    </button>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.seriesDescriptionFilterString}</div>
                    <div class="filter-input"></div>
                    <button class="add-filter-button" @click=${this._handleAddSeriesDescriptionFilterClicked}>
                      ${Plus} ${this.addString}
                    </button>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.tagFilterString}</div>
                    <div class="filter-input"></div>
                    <button class="add-filter-button" @click=${this._handleAddTagFilterClicked}>
                      ${Plus} ${this.addString}
                    </button>
                  </div>
                ` : '' }
              </div>
            </div>
        `;
    }

    private _handleTransitionEnd() {
        if (this._collapsed) {
            this._showContent = false;
        }
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
            this._showContent = false;
        }
    }

    private _handleAddAdvancedFilterClicked() {
        console.log('Add advanced filter clicked');
    }

    private _handleAddStudyDescriptionFilterClicked() {
        console.log('Add study description filter clicked');
    }

    private _handleAddSeriesDescriptionFilterClicked() {
        console.log('Add series description filter clicked');
    }

    private _handleAddTagFilterClicked() {
        console.log('Add tag filter clicked');
    }
}