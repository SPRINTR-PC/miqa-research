import{_ as e,a as t,c as n,d as r,f as i,g as a,h as o,l as s,m as c,n as l,o as u,p as d,r as f,s as p,t as m,u as h,v as g,y as _}from"./chunks/directive-helpers-C7Xv0qUr.js";var v=_`
    :host {
        /* TYPOGRAPHY */
        --form-font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        --form-font-size-base: var(--font-size-base, 1rem);
        --form-font-size-h1: var(--font-size-h1, 1.8rem);
        --form-font-size-h2: var(--font-size-h2, 1.4rem);
        --form-font-size-label: var(--font-size-label, 0.9rem);
        --form-font-size-description: var(--font-size-description, 0.85rem);

        /* COLOURS */
        --mires-color-primary-parts: var(--color-primary-parts, 273 74% 53%);
        --mires-color-secondary-parts: var(--color-secondary-parts, 210 100% 50%);
        --mires-color-text-parts: var(--color-text-parts, 0 0% 20%);
        --mires-color-background-parts: var(--color-background-parts, 0 0% 100%);

        --mires-color-text: var(--color-text, hsl(var(--mires-color-text-parts)));
        --mires-color-background: var(--color-background, hsl(var(--mires-color-background-parts)));
        --mires-color-background-darker: var(--color-background-darker, hsl(from hsl(var(--mires-color-background-parts)) h s calc(l / .5)));

        --mires-form-color-text: hsl(var(--mires-color-text-parts));
        --mires-form-color-input-text: var(--color-input-text, #111);
        --mires-form-color-text-secondary: var(--color-text-secondary, #555); /* För beskrivningar */
        --mires-form-color-text-label: var(--color-text-label, #111);
        --mires-form-color-background: var(--form-color-background, var(--mires-color-background, hsl(0, 0%, 100%)));
        --mires-form-color-background-input-base: var(--color-background-input-base, #ffffff);
        --mires-form-color-background-input-focus: var(--color-background-input-focus, #ffffff);
        --mires-form-color-background-input-ok: var(--color-background-input-base, #b9fb9f);
        --mires-form-color-background-input-ok-focus: var(--color-background-input-focus, #b9fb9f);
        --mires-form-color-background-section: var(--color-background-section, #f9f9f9);
        --mires-form-color-border: var(--color-border, #ccc);
        --mires-form-color-border-focus: var(--form-color-accent);

        /* ACCENT COLOUR (Buttons, active tabs, etc.) */
        --mires-color-primary: var(--color-primary, hsl(var(--mires-color-primary-parts)));
        --mires-color-primary-hover: var(--color-primary-hover, hsl(var(--color-primary-parts, 273 74% 53%) / .5)));
        --color-secondary: hsl(var(--mires-color-secondary-parts));
        --color-secondary-hover: hsl(var(--mires-color-secondary-parts) / .5);
        --form-color-success: var(--color-success, #28a745);
        --form-color-success-darker: var(--color-success-darker, #1e7e34);
        --form-color-success-text: var(--color-success-text, #ffffff);
        --form-color-warning: var(--color-warning, #fbb34e);
        --form-color-warning-darker: var(--color-warning-darker, #fea429);
        --form-color-warning-text: var(--color-warning-text, #ffffff);
        --form-color-neutral: var(--color-neutral, #6c757d);
        --form-color-neutral-darker: var(--color-neutral-darker, #5a6268);
        --form-color-neutral-text: var(--color-neutral-text, #ffffff);
        --form-color-error: var(--color-error, #dc3545);
        --form-color-error-lighter: var(--color-error-lighter, #fa5969);
        --form-color-error-text: var(--color-error-text, #721c24);

        /* STATUS COLOUR (for tolerances) */
        --form-color-required-star: var(--color-required-star, #f98989);
        --form-color-within-tolerance-border: var(--color-within-tolerance-border, #8fff8f);
        --form-color-within-tolerance-background: var(--color-within-tolerance-background, #b9fb9f);
        --form-color-within-tolerance-input-text: var(--color-within-tolerance-input-text, #214521);
        --form-color-within-tolerance-text: var(--color-within-tolerance-text, #3c763d);
        --form-color-out-of-tolerance-border: var(--color-out-of-tolerance-border, #fdf8b2);
        --form-color-out-of-tolerance-background: var(--color-background-input-base, #fff894);
        --form-color-out-of-tolerance-text: var(--color-out-of-tolerance-text, #d9534f);
        --form-color-has-error-border: var(--color-has-error-border, var(--form-color-out-of-tolerance-text));
        --form-color-has-error-background: var(--color-has-error-background, #d58d8b);
        --form-color-out-of-tolerance-warning: var(--form-color-out-of-tolerance-text, yellow);

        /* LAYOUT */
        --form-border-radius: var(--border-radius, 4px);
        --form-spacing-medium: var(--spacing-medium, 1rem);
        --form-spacing-large: var(--spacing-large, 1.5rem);
        --form-button-padding: var(--button-padding, 0.3rem 1rem);

        /* =============================================
        // 2. MAPPNING TO SHOELACE DESIGN TOKENS
        // ============================================= */

        --sl-color-primary-500: var(--form-color-accent);
        --sl-color-primary-600: var(--form-color-accent-darker);

        --sl-color-success-500: var(--form-color-success);
        --sl-color-success-600: var(--form-color-success-darker);

        --sl-color-neutral-500: var(--form-color-neutral);
        --sl-color-neutral-600: var(--form-color-neutral-darker);

        --sl-color-warning-500: var(--form-color-warning);
        --sl-color-warning-600: var(--form-color-warning-darker);

        --sl-font-sans: var(--form-font-family);

        --sl-input-border-color: var(--mires-form-color-border);
        --sl-input-border-color-focus: var(--mires-form-color-border-focus);
        --sl-input-border-radius-medium: var(--form-border-radius);

        /* =============================================
        // 3. GLOBAL STYLING FÖR DENNA KOMPONENT
        // ============================================= */

        font-family: var(--form-font-family, "sans-serif");
        font-size: var(--form-font-size-base);
        color: var(--mires-form-color-text);
        background-color: var(--mires-form-color-background);
        display: block;
        --border: 1px solid var(--mires-form-color-border);
        --border-radius: var(--form-border-radius);
        padding: var(--form-spacing-large);
    }


`;_`
    .btn {
        padding: var
    }
    .btn {
      background: var(--primary);
      color: white;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }

    .btn:hover {
      background: var(--primary-hover);
    }
`;var y=class extends o{constructor(...e){super(...e),this.apiUri=``,this.columnListApiUri=``,this.bookmarkApiUri=``,this.bookmarkId=``,this.monitorTitle=`Monitor`,this.monitorFilter={gender:[],age:{min:0,max:200,selected_min:0,selected_max:200,include_null:!0},studyDescription:[],seriesDescription:[]},this._tableData={columns:[]},this._availableColumns=[{id:`patientName`,title:`Patient Name`,dataType:`string`},{id:`patientAge`,title:`Patient Age`,dataType:`number`},{id:`modality`,title:`Modality`,dataType:`string`},{id:`studyDate`,title:`Study Date`,dataType:`date`},{id:`studyTime`,title:`Study Time`,dataType:`time`}],this._selectedColumns=[]}async connectedCallback(){super.connectedCallback(),await this.fetchAvailableColumns()}async fetchAvailableColumns(){if(this.columnListApiUri)try{let e=await fetch(this.columnListApiUri);e.ok?this._availableColumns=await e.json():console.error(`Failed to fetch columns:`,e.statusText)}catch(e){console.error(`Error fetching columns:`,e)}}static{this.styles=[v,_`
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
        `]}render(){return g`
        <div id="monitor-container">
          <h1>${this.monitorTitle}</h1>
          <miqa-monitor-columns
            .availableColumns=${this._availableColumns}
            .selectedColumns=${this._selectedColumns}
            @column-selection-changed="${e=>this._selectedColumns=e.detail.selectedColumns}"
          ></miqa-monitor-columns>
          <miqa-monitor-filter
            .monitorFilter=${this.monitorFilter}
          ></miqa-monitor-filter>
          <miqa-monitor-table
            .selectedColumns=${this._selectedColumns}
            .tableData=${this._tableData}
          ></miqa-monitor-table>
        </div>
      `}};h([d({type:String})],y.prototype,`apiUri`,void 0),h([d({type:String})],y.prototype,`columnListApiUri`,void 0),h([d({type:String})],y.prototype,`bookmarkApiUri`,void 0),h([d({type:String})],y.prototype,`bookmarkId`,void 0),h([d({type:String})],y.prototype,`monitorTitle`,void 0),h([i()],y.prototype,`monitorFilter`,void 0),h([i()],y.prototype,`_tableData`,void 0),h([i()],y.prototype,`_availableColumns`,void 0),h([i()],y.prototype,`_selectedColumns`,void 0),y=h([c(`miqa-monitor`)],y);var b=g`<svg class="MuiSvgIcon-root MuiSvgIcon-fontSizeMedium css-1phnduy" focusable="false" aria-hidden="true" viewBox="0 0 24 24"><path d="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z"></path></svg>`,x=g`<svg class="MuiSvgIcon-root MuiSvgIcon-fontSizeMedium css-1phnduy" focusable="false" aria-hidden="true" viewBox="0 0 24 24"><path d="M8.59 16.59 13.17 12 8.59 7.41 10 6l6 6-6 6z"></path></svg>`,S=g`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-panel-right-open h-3.5 w-3.5"><rect width="18" height="18" x="3" y="3" rx="2"></rect><path d="M15 3v18"></path><path d="m10 15-3-3 3-3"></path></svg>`,C=g`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-plus h-3 w-3"><path d="M5 12h14"></path><path d="M12 5v14"></path></svg>`,w=class extends o{constructor(...e){super(...e),this.availableColumns=[],this.selectedColumns=[],this._collapsed=!0,this._showContent=!1,this._draggedColumnId=null,this._dragOverColumnId=null,this._visibleAvailableColumns=[],this._visibleSelectedColumns=[]}static{this.styles=[v,_`
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
    `]}willUpdate(e){(e.has(`availableColumns`)||e.has(`selectedColumns`)||e.has(`columnsOrder`))&&this._filterAvailableColumns(new Event(`input`))}render(){return g`
            <div class="drawer ${this._collapsed?`collapsed`:`expanded`}" @transitionend="${this._handleTransitionEnd}">
                <button class="toggle-button" @click="${this._toggleCollapsed}">
                    ${S}
                </button>
                ${this._showContent?g`
                    <div class="drawer-content">
                        <div class="column-list-header">
                            <h3>Columns</h3>
                        </div>
                        <div class="column-lists-container">
                            <div class="selected-columns-col">
                                <h4>Selected</h4>
                                <input type="text" placeholder="Filter selected columns..." @input="${e=>this._filterSelectedColumns(e)}" />
                                <div class="btn-list-container">
                                ${this._visibleSelectedColumns.map(e=>g`<button 
                                            draggable="true"
                                            @dragstart="${t=>this._handleDragStart(t,e.id)}"
                                            @dragover="${t=>this._handleDragOver(t,e.id)}"
                                            @dragleave="${()=>this._handleDragLeave(e.id)}"
                                            @drop="${t=>this._handleDrop(t,e.id)}"
                                            @dragend="${this._handleDragEnd}"
                                            @click="${()=>this._handleColumnDeselected(e.id)}" 
                                            class="column-btn selected-column-btn ${this._draggedColumnId===e.id?`dragging`:``} ${this._dragOverColumnId===e.id?`drag-over`:``}"
                                         >${e.title}</button>`)}
                                </div>
                            </div>
                            <div class="available-columns-col">
                                <h4>Available</h4>
                                <input type="text" placeholder="Filter available columns..." @input="${e=>this._filterAvailableColumns(e)}" />
                                <div class="btn-list-container">
                                ${this._visibleAvailableColumns.map(e=>g`<button @click="${()=>this._handleColumnSelected(e.id)}" class="column-btn available-column-btn">${e.title}</button>`)}
                                </div>
                            </div>
                        </div>
                    </div>
                `:``}
            </div>
        `}_filterAvailableColumns(e){let t=e.target;this._visibleAvailableColumns=t==null||t.value==``?this.availableColumns.filter(e=>!this.selectedColumns.some(t=>t.id===e.id)):this.availableColumns.filter(e=>e.title.toLowerCase().includes(t.value.toLowerCase())&&!this.selectedColumns.some(t=>t.id===e.id))}_filterSelectedColumns(e){let t=e.target;this._visibleSelectedColumns=t==null||t.value==``?this.selectedColumns:this.selectedColumns.filter(e=>e.title.toLowerCase().includes(t.value.toLowerCase()))}_toggleCollapsed(){this._collapsed?(this._showContent=!0,requestAnimationFrame(()=>{this._collapsed=!1})):this._collapsed=!0}_handleTransitionEnd(){this._collapsed&&(this._showContent=!1)}_handleColumnSelected(e){let t=this.availableColumns.find(t=>t.id===e);t&&!this.selectedColumns.some(t=>t.id===e)&&(this.selectedColumns=[...this.selectedColumns,t],this._filterSelectedColumns(new Event(`input`)),this._dispatchChanged())}_handleColumnDeselected(e){this.selectedColumns=this.selectedColumns.filter(t=>t.id!==e),this._filterSelectedColumns(new Event(`input`)),this._dispatchChanged()}_handleDragStart(e,t){this._draggedColumnId=t,e.dataTransfer&&(e.dataTransfer.effectAllowed=`move`,e.dataTransfer.setData(`text/plain`,t))}_handleDragOver(e,t){e.preventDefault(),this._draggedColumnId!==t&&(this._dragOverColumnId=t,e.dataTransfer&&(e.dataTransfer.dropEffect=`move`))}_handleDragLeave(e){this._dragOverColumnId===e&&(this._dragOverColumnId=null)}_handleDrop(e,t){e.preventDefault();let n=this._draggedColumnId;if(this._draggedColumnId=null,this._dragOverColumnId=null,n&&n!==t){let e=this.selectedColumns.findIndex(e=>e.id===n),r=this.selectedColumns.findIndex(e=>e.id===t);if(e!==-1&&r!==-1){let t=[...this.selectedColumns],[n]=t.splice(e,1);t.splice(r,0,n),this.selectedColumns=t,this._dispatchChanged()}}}_handleDragEnd(){this._draggedColumnId=null,this._dragOverColumnId=null}_dispatchChanged(){this.dispatchEvent(new CustomEvent(`column-selection-changed`,{detail:{selectedColumns:this.selectedColumns},bubbles:!0,composed:!0}))}};h([d({type:Object})],w.prototype,`availableColumns`,void 0),h([d({type:Object})],w.prototype,`selectedColumns`,void 0),h([i()],w.prototype,`_collapsed`,void 0),h([i()],w.prototype,`_showContent`,void 0),h([i()],w.prototype,`_draggedColumnId`,void 0),h([i()],w.prototype,`_dragOverColumnId`,void 0),h([i()],w.prototype,`_visibleAvailableColumns`,void 0),h([i()],w.prototype,`_visibleSelectedColumns`,void 0),w=h([c(`miqa-monitor-columns`)],w);var T=class extends o{constructor(...e){super(...e),this.columns=[],this.addString=`Add`,this.advancedFilterString=`Advanced filter`,this.modalityFilterString=`Modality`,this.genderFilterString=`Gender`,this.patientAgeFilterString=`Patient Age`,this.studyDescriptionFilterString=`Study Description`,this.seriesDescriptionFilterString=`Series Description`,this.tagFilterString=`Tag`,this._collapsed=!0,this._showContent=!1}static{this.styles=[v,_`
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
        `]}render(){return g`
            <div class="filter-container">
              <div class="filter-header ${this._collapsed?``:`expanded`}" @click="${this._toggleCollapsed}">
                <div class="filter-title">
                  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-filter h-4 w-4 text-muted-foreground"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon></svg>
                  <span class="semibold text-sm">Filter</span>
                </div>
                <div class="selected-filter-summary"></div>
                <div class="toggle-button" >${this._collapsed?x:b}</div>
              </div>
              <div class="filter-content ${this._collapsed?`collapsed`:``}" @transitionend="${this._handleTransitionEnd}">
                ${this._showContent?g`
                  <div class="filter-group">
                    <div class="filter-label">${this.advancedFilterString}</div>
                    <div class="filter-input">Some content</div>
                    <button class="add-filter-button" @click=${this._handleAddAdvancedFilterClicked}>
                      ${C} ${this.addString}
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
                      ${C} ${this.addString}
                    </button>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.seriesDescriptionFilterString}</div>
                    <div class="filter-input"></div>
                    <button class="add-filter-button" @click=${this._handleAddSeriesDescriptionFilterClicked}>
                      ${C} ${this.addString}
                    </button>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.tagFilterString}</div>
                    <div class="filter-input"></div>
                    <button class="add-filter-button" @click=${this._handleAddTagFilterClicked}>
                      ${C} ${this.addString}
                    </button>
                  </div>
                `:``}
              </div>
            </div>
        `}_handleTransitionEnd(){this._collapsed&&(this._showContent=!1)}_toggleCollapsed(){this._collapsed?(this._showContent=!0,requestAnimationFrame(()=>{this._collapsed=!1})):(this._collapsed=!0,this._showContent=!1)}_handleAddAdvancedFilterClicked(){console.log(`Add advanced filter clicked`)}_handleAddStudyDescriptionFilterClicked(){console.log(`Add study description filter clicked`)}_handleAddSeriesDescriptionFilterClicked(){console.log(`Add series description filter clicked`)}_handleAddTagFilterClicked(){console.log(`Add tag filter clicked`)}};h([d({type:Object})],T.prototype,`columns`,void 0),h([d({type:String})],T.prototype,`addString`,void 0),h([d({type:String})],T.prototype,`advancedFilterString`,void 0),h([d({type:String})],T.prototype,`modalityFilterString`,void 0),h([d({type:String})],T.prototype,`genderFilterString`,void 0),h([d({type:String})],T.prototype,`patientAgeFilterString`,void 0),h([d({type:String})],T.prototype,`studyDescriptionFilterString`,void 0),h([d({type:String})],T.prototype,`seriesDescriptionFilterString`,void 0),h([d({type:String})],T.prototype,`tagFilterString`,void 0),h([i()],T.prototype,`_collapsed`,void 0),h([i()],T.prototype,`_showContent`,void 0),T=h([c(`miqa-monitor-filter`)],T);var E=(e,t,n)=>{let r=new Map;for(let i=t;i<=n;i++)r.set(e[i],i);return r},D=p(class extends n{constructor(e){if(super(e),e.type!==s.CHILD)throw Error(`repeat() can only be used in text expressions`)}dt(e,t,n){let r;n===void 0?n=t:t!==void 0&&(r=t);let i=[],a=[],o=0;for(let t of e)i[o]=r?r(t,o):o,a[o]=n(t,o),o++;return{values:a,keys:i}}render(e,t,n){return this.dt(e,t,n).values}update(n,[r,i,a]){let o=m(n),{values:s,keys:c}=this.dt(r,i,a);if(!Array.isArray(o))return this.ut=c,s;let d=this.ut??=[],p=[],h,g,_=0,v=o.length-1,y=0,b=s.length-1;for(;_<=v&&y<=b;)if(o[_]===null)_++;else if(o[v]===null)v--;else if(d[_]===c[y])p[y]=t(o[_],s[y]),_++,y++;else if(d[v]===c[b])p[b]=t(o[v],s[b]),v--,b--;else if(d[_]===c[b])p[b]=t(o[_],s[b]),u(n,p[b+1],o[_]),_++,b--;else if(d[v]===c[y])p[y]=t(o[v],s[y]),u(n,o[_],o[v]),v--,y++;else if(h===void 0&&(h=E(c,y,b),g=E(d,_,v)),h.has(d[_])){if(h.has(d[v])){let e=g.get(c[y]),r=e===void 0?null:o[e];if(r===null){let e=u(n,o[_]);t(e,s[y]),p[y]=e}else p[y]=t(r,s[y]),u(n,o[_],r),o[e]=null;y++}else l(o[v]),v--}else l(o[_]),_++;for(;y<=b;){let e=u(n,p[b+1]);t(e,s[y]),p[y++]=e}for(;_<=v;){let e=o[_++];e!==null&&l(e)}return this.ut=c,f(n,p),e}}),O=class extends o{constructor(...e){super(...e),this.selectedColumns=[],this.tableData={columns:[]},this.noDataAvailableString=`No data available`,this._rows=[]}static{this.styles=[v,_`
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
        `]}willUpdate(e){e.has(`tableData`)&&this._preCalculateRows()}_preCalculateRows(){if(this.tableData=this.tableData==null?{columns:[]}:this.tableData,this.tableData.columns.length===0){this._rows=[];return}let e=this.tableData.columns[0].values.length,t=this.tableData.columns.length,n=Array(e);for(let r=0;r<e;r++){let e=Array(t);for(let n=0;n<t;n++)e[n]=this.tableData.columns[n].values[r];n[r]=e}this._rows=n}render(){return this.selectedColumns=this.selectedColumns==null?[]:this.selectedColumns,g`
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  ${this.tableData.columns.length===0?this.selectedColumns.length===0?g`<th></th>`:this.selectedColumns.map(e=>g`<th>${e.title}</th>`):this.tableData.columns.map(e=>g`<th>${e.header}</th>`)}
                </tr>
              </thead>
              <tbody>
                ${this._mapTableDataToRows()}
              </tbody>
            </table>
          </div>
        `}_mapTableDataToRows(){return this._rows.length===0?g`<tr><td colspan="${this.selectedColumns.length}">${this.noDataAvailableString}</td></tr>`:g`
            ${D(this._rows,(e,t)=>t,e=>g`
                    <tr>
                        ${e.map(e=>g`<td>${e}</td>`)}
                    </tr>
                `)}
        `}};h([d({type:Object})],O.prototype,`selectedColumns`,void 0),h([d({type:Object})],O.prototype,`tableData`,void 0),h([d({type:String})],O.prototype,`noDataAvailableString`,void 0),h([i()],O.prototype,`_rows`,void 0),O=h([c(`miqa-monitor-table`)],O);var k=class extends o{constructor(...e){super(...e),this.language=`en`,this.uploadUrl=``,this.projectId=``,this.files=[],this.isDragging=!1,this.globalProgress=0}static{this.styles=_`
    :host {
      --primary: var(--color-primary, #aa3bff);
      --primary-hover: hsl(var(--color-primary-parts, 273 74% 53%) / .5);
      --bg: var(--color-background, #ffffff);
      --text: hsl(var(--color-muted-foreground-parts, 267 8% 42%));
      --text-h: var(--color-muted-foreground, hsl(257, 37%, 4%));
      --border: var(--border-color, #e5e4e7);
      --error: var(--color-chart-error, hsl(0, 84%, 60%));
      --success: var(--color-chart-success, #22c55e);
      --progress-bg: #f4f3ec;

      display: block;
      font-family: system-ui, 'Segoe UI', Roboto, sans-serif;
      color: var(--text);
      margin: 0 auto;
      box-sizing: border-box;
    }

    .drop-zone {
      border: 2px dashed var(--border);
      border-radius: 8px;
      padding: 40px;
      text-align: center;
      cursor: pointer;
      transition: all 0.2s ease;
      background: var(--bg);
      margin-bottom: 24px;
    }
    
    .drop-zone:hover {
      border-color: var(--primary);
    }

    .drop-zone.dragging {
      border-color: var(--primary);
      background: rgba(170, 59, 255, 0.05);
    }

    .drop-zone p {
      margin: 0;
      font-size: 16px;
    }

    .card {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      background: var(--bg);
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }

    .card-title {
      font-size: 20px;
      font-weight: 600;
      color: var(--text-h);
      margin: 0;
    }

    .btn-upload {
      background: var(--primary);
      color: white;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }

    .btn-upload:hover {
      background: var(--primary-hover);
    }

    .btn-upload:disabled {
      background: var(--border);
      cursor: not-allowed;
    }

    .progress-container {
      height: 8px;
      background: var(--progress-bg);
      border-radius: 4px;
      overflow: hidden;
      margin-bottom: 20px;
    }

    .progress-bar {
      height: 100%;
      background: var(--primary);
      transition: width 0.3s ease;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }

    th {
      text-align: left;
      padding: 12px 8px;
      border-bottom: 1px solid var(--border);
      color: var(--text-h);
    }

    td {
      padding: 12px 8px;
      border-bottom: 1px solid var(--border);
    }

    .status-icon {
      width: 20px;
      height: 20px;
      display: inline-block;
      vertical-align: middle;
    }

    .icon-pending {
      color: var(--text);
    }

    .icon-success {
      color: var(--success);
    }

    .icon-error {
      color: var(--error);
    }

    .btn-remove {
      background: none;
      border: none;
      color: var(--text);
      cursor: pointer;
      padding: 4px;
      border-radius: 4px;
      transition: background 0.2s;
    }

    .btn-remove:hover {
      background: #fef2f2;
      color: var(--error);
    }

    .hidden {
      display: none;
    }
  `}handleDragOver(e){e.preventDefault(),e.stopPropagation(),this.isDragging=!0}handleDragLeave(e){e.preventDefault(),e.stopPropagation(),this.isDragging=!1}handleDrop(e){e.preventDefault(),e.stopPropagation(),this.isDragging=!1,e.dataTransfer?.files&&this.addFiles(e.dataTransfer.files)}openFilePicker(){this.fileInput.click()}handleFileChange(e){let t=e.target;t.files&&this.addFiles(t.files)}addFiles(e){let t=[];for(let n=0;n<e.length;n++){let r=e[n];(r.type===`application/pdf`||r.type.startsWith(`image/`))&&t.push({file:r,status:`pending`,progress:0})}this.files=[...this.files,...t],this.fileInput.value=``}removeFile(e){this.files=this.files.filter((t,n)=>n!==e)}getCsrfToken(){let e=null;if(document.cookie&&document.cookie!==``){let t=document.cookie.split(`;`);for(let n=0;n<t.length;n++){let r=t[n].trim();if(r.substring(0,10)===`csrftoken=`){e=decodeURIComponent(r.substring(10));break}}}return e}async uploadFiles(){if(this.files.length===0||!this.uploadUrl)return;let e=this.files.map((e,t)=>({f:e,index:t})).filter(({f:e})=>e.status===`pending`||e.status===`error`);if(e.length===0)return;this.globalProgress=0;let t=0,n=this.getCsrfToken();for(let{f:r,index:i}of e){this.updateFileStatus(i,`uploading`,0);try{await this.performUpload(r.file,i,n),this.updateFileStatus(i,`completed`,100)}catch(e){console.error(`Upload failed for file:`,r.file.name,e),this.updateFileStatus(i,`error`,0)}t++,this.globalProgress=Math.min(t/e.length*100,100)}}performUpload(e,t,n){return new Promise((r,i)=>{let a=new XMLHttpRequest,o=new FormData;o.append(`file`,e),this.projectId&&this.projectId.trim()!==``&&o.append(`projectId`,this.projectId),a.upload.addEventListener(`progress`,e=>{if(e.lengthComputable){let n=Math.round(e.loaded/e.total*100);this.updateFileStatus(t,`uploading`,n)}}),a.addEventListener(`load`,()=>{a.status>=200&&a.status<300?r():i(Error(`HTTP Error: ${a.status}`))}),a.addEventListener(`error`,()=>i(Error(`Network error`))),a.addEventListener(`abort`,()=>i(Error(`Upload aborted`))),a.open(`POST`,this.uploadUrl),n&&a.setRequestHeader(`X-CSRFToken`,n),a.send(o)})}updateFileStatus(e,t,n){this.files=this.files.map((r,i)=>i===e?{...r,status:t,progress:n}:r)}formatSize(e){if(e===0)return`0 Bytes`;let t=1024,n=[`Bytes`,`KB`,`MB`,`GB`],r=Math.floor(Math.log(e)/Math.log(t));return parseFloat((e/t**r).toFixed(2))+` `+n[r]}renderStatusIcon(e){switch(e){case`completed`:return g`
          <svg class="status-icon icon-success" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
            <polyline points="22 4 12 14.01 9 11.01"></polyline>
          </svg>
        `;case`error`:return g`
          <svg class="status-icon icon-error" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="15" y2="15" x1="9" y1="9"></line>
            <line x1="9" y2="15" x1="15" y1="9"></line>
          </svg>
        `;case`uploading`:return g`
          <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 1 1-6.21-8.58"></path>
          </svg>
        `;default:return g`
          <svg class="status-icon icon-pending" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"></circle>
            <polyline points="12 6 12 12 16 14"></polyline>
          </svg>
        `}}render(){this.language=this.language.toLowerCase().split(`-`)[0];let e=[];switch(this.language){case`sv`:e=[`Dra och släpp PROM formulär här eller klicka för att välja filer`,`Stöd för PDF, JPG, PNG`,`PROM Formulär`,`Ladda upp filer`,`Filnamn`,`Storlek`,`Status`];break;default:this.language!==`en`&&console.log(`Unknown/-implemented language set. Defaulting to english`),e=[`Drag and drop PROM forms here, or click to select files`,`Supports PDF, JPG, PNG`,`PROM Forms`,`Upload Files`,`File Name`,`Size`,`Status`]}return g`
      <div 
        class="drop-zone ${this.isDragging?`dragging`:``}"
        @dragover=${this.handleDragOver}
        @dragleave=${this.handleDragLeave}
        @drop=${this.handleDrop}
        @click=${this.openFilePicker}
      >
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--primary); margin-bottom: 12px;">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
          <polyline points="17 8 12 3 7 8"></polyline>
          <line x1="12" x2="12" y1="3" y2="15"></line>
        </svg>
        <p>${e[0]}</p>
        <p style="font-size: 12px; color: var(--text); margin-top: 8px;">${e[1]}</p>
        <input 
          type="file" 
          id="fileInput" 
          class="hidden" 
          multiple 
          accept="application/pdf,image/*"
          @change=${this.handleFileChange}
        >
      </div>
      ${this.files.length===0?g``:g`
      <div class="card">
        <div class="card-header">
          <h2 class="card-title">${e[2]} (${this.files.length})</h2>
          <button
              class="btn-upload"
              ?disabled=${this.files.length===0}
              @click=${this.uploadFiles}
          >
            ${e[3]}
          </button>
        </div>

        <div class="progress-container">
          <div class="progress-bar" style="width: ${this.globalProgress}%"></div>
        </div>

        <table>
          <thead>
          <tr>
            <th style="width: 40px;"></th>
            <th>${e[4]}</th>
            <th>${e[5]}</th>
            <th>${e[6]}</th>
            <th style="width: 40px;"></th>
          </tr>
          </thead>
          <tbody>
          ${this.files.map((e,t)=>g`
            <tr>
              <td>${this.renderStatusIcon(e.status)}</td>
              <td>${e.file.name}</td>
              <td>${this.formatSize(e.file.size)}</td>
              <td>${e.status.charAt(0).toUpperCase()+e.status.slice(1)}</td>
              <td>
                <button class="btn-remove" @click=${e=>{e.stopPropagation(),this.removeFile(t)}}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                       stroke-linecap="round" stroke-linejoin="round">
                    <path d="M3 6h18"></path>
                    <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>
                    <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
                    <line x1="10" x2="10" y1="11" y2="17"></line>
                    <line x1="14" x2="14" y1="11" y2="17"></line>
                  </svg>
                </button>
              </td>
            </tr>
          `)}
          </tbody>
        </table>
      </div>
    `}
    `}};h([d({type:String})],k.prototype,`language`,void 0),h([d({type:String})],k.prototype,`uploadUrl`,void 0),h([d({type:String})],k.prototype,`projectId`,void 0),h([i()],k.prototype,`files`,void 0),h([i()],k.prototype,`isDragging`,void 0),h([i()],k.prototype,`globalProgress`,void 0),h([r(`#fileInput`)],k.prototype,`fileInput`,void 0),k=h([c(`prom-upload`)],k);var A=class extends n{constructor(e){if(super(e),this.it=a,e.type!==s.CHILD)throw Error(this.constructor.directiveName+`() can only be used in child bindings`)}render(t){if(t===a||t==null)return this._t=void 0,this.it=t;if(t===e)return t;if(typeof t!=`string`)throw Error(this.constructor.directiveName+`() called with a non-string value`);if(t===this.it)return this._t;this.it=t;let n=[t];return n.raw=n,this._t={_$litType$:this.constructor.resultType,strings:n,values:[]}}};A.directiveName=`unsafeHTML`,A.resultType=1;var j=p(A),M=class{static async getData(e){return this.getJson(e,`Data fetched successfully`,`Error fetching data`)}static async getJson(e,t,n){let r={"Content-Type":`application/json`,Accept:`application/json`};try{let n=await fetch(e,{method:`GET`,headers:r,credentials:`include`});if(!n.ok){if(n.status===401)throw Error(`Your session has ended. Please login again`);let e=await n.text();throw Error(`API Error (${n.status}): ${n.statusText} - ${e}`)}return{success:!0,data:await n.json(),message:t}}catch(e){throw console.error(n,e),e}}},N=(e,t)=>parseFloat(`${e/t*100}`).toFixed(2),P=class extends o{constructor(...e){super(...e),this.dataUrl=``,this.noDataMessage=`No data available`,this.loadingMessage=`Loading data...`,this.errorMessage=`Something went wrong loading data.`,this.striped=!1,this._columns=void 0,this._rows=void 0,this._isLoading=!1,this._hasError=!1,this._errorDetail=void 0,this._pagination=void 0,this._page=1,this._sortState=[],this._filterValues={},this._rangeFilterValues={},this._multiSelectValues={},this._filterDebounceTimers={}}static{this.styles=[v,_`
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
  `]}connectedCallback(){super.connectedCallback(),this.initialSort&&this.initialSort.length>0&&(this._sortState=this.initialSort),this.dataUrl&&this._loadData()}updated(e){super.updated(e),e.has(`dataUrl`)&&e.get(`dataUrl`)!==void 0&&(this.dataUrl?(this._page=1,this._loadData()):(this._rows=void 0,this._columns=void 0,this._hasError=!1,this._pagination=void 0))}async _loadData(){this._isLoading=!0,this._hasError=!1,this._errorDetail=void 0;try{let e=await M.getData(this._buildRequestUrl());e.success&&e.data?(this._rows=e.data.rows,this._columns=e.data.columns??this._deriveColumnsFromRows(e.data.rows),this._pagination=e.data.pagination,this._page=e.data.pagination.page):(this._rows=void 0,this._columns=void 0,this._pagination=void 0,this._hasError=!0)}catch(e){this._rows=void 0,this._columns=void 0,this._pagination=void 0,this._hasError=!0,this._errorDetail=e instanceof Error?e.message:String(e)}finally{this._isLoading=!1}}_renderErrorMessage(){return this.errorMessage.includes(`{message}`)?this.errorMessage.replace(`{message}`,this._errorDetail??``):this.errorMessage}_renderMiniBarChart(e,t,n=10,r=!0){let i=e.slice(-n),a=Math.max(...i);return g`
      ${r?g`<td class="tooltip-cell">`:``}
        <div class="mini-bar-chart">
          ${i.map((e,n)=>g`
              <div
                class="mini-bar"
                key="${n}_${e}/${a}"
                style="
                  height: ${N(e,a)}%;
                  background: hsl(${t.hue}, ${t.saturation}%, ${t.lightness}%);
                "
                data-bar-value=${e}
                data-testid="mini-bar"
              />
            `)}
        </div>
        <div class="tooltip">
            <ul>
              ${i.map((e,t)=>g`<li>${t+1}: ${e}</li>`)}
            </ul>
        </div>
      ${r?g`</td>`:``}
    `}_buildRequestUrl(){let e=this._pagination?.pageSize??this.pageSize??50,t=this.dataUrl.includes(`?`)?`&`:`?`,n=`${this.dataUrl}${t}page=${this._page}&pageSize=${e}`;if(this._sortState.length>0){let e=this._sortState.map(e=>e.direction===`desc`?`-${e.column}`:e.column).join(`,`);n+=`&sort=${e}`}return n+=this._buildFilterQueryString(),n}_buildFilterQueryString(){if(!this._columns)return``;let e=[];for(let t of this._columns){let n=t.filter;if(!n)continue;if(n.kind===`numeric-range`||n.kind===`date-range`){let n=this._rangeFilterValues[t.accessor];n?.min&&e.push(`${t.accessor}__gte=${encodeURIComponent(n.min)}`),n?.max&&e.push(`${t.accessor}__lte=${encodeURIComponent(n.max)}`);continue}if(n.kind===`multi-select`){let n=this._multiSelectValues[t.accessor];n&&n.length>0&&e.push(`${t.accessor}__in=${encodeURIComponent(n.join(`,`))}`);continue}let r=this._filterValues[t.accessor];if(r===void 0||r===``)continue;let i=n.kind===`text`?`${t.accessor}__icontains`:t.accessor;e.push(`${i}=${encodeURIComponent(r)}`)}return e.length>0?`&${e.join(`&`)}`:``}_goToPage(e){this._page=e,this._loadData()}_handleHeaderClick(e,t){if(!e.sortable)return;let n=this._sortState.findIndex(t=>t.column===e.accessor);if(t){if(n>=0){let e=[...this._sortState];e[n]={...e[n],direction:e[n].direction===`asc`?`desc`:`asc`},this._sortState=e}else this._sortState=[...this._sortState,{column:e.accessor,direction:`asc`}]}else this._sortState=this._sortState.length===1&&n===0?[{column:e.accessor,direction:this._sortState[0].direction===`asc`?`desc`:`asc`}]:[{column:e.accessor,direction:`asc`}];this._page=1,this._loadData()}_handleFilterInput(e,t,n){this._filterValues={...this._filterValues,[e.accessor]:t},clearTimeout(this._filterDebounceTimers[e.accessor]),n>0?this._filterDebounceTimers[e.accessor]=setTimeout(()=>this._applyFilters(),n):this._applyFilters()}_handleRangeFilterInput(e,t,n,r){let i=this._rangeFilterValues[e.accessor]??{};this._rangeFilterValues={...this._rangeFilterValues,[e.accessor]:{...i,[t]:n}};let a=`${e.accessor}:${t}`;clearTimeout(this._filterDebounceTimers[a]),r>0?this._filterDebounceTimers[a]=setTimeout(()=>this._applyFilters(),r):this._applyFilters()}_handleMultiSelectInput(e,t){this._multiSelectValues={...this._multiSelectValues,[e.accessor]:t},this._applyFilters()}_applyFilters(){this._page=1,this._loadData()}_deriveColumnsFromRows(e){let t=e[0];if(t)return Object.keys(t).map(e=>({accessor:e,label:e}))}render(){if(this._isLoading)return g`<p class="message">${this.loadingMessage}</p>`;if(this._hasError)return g`<p class="message">${this._renderErrorMessage()}</p>`;if(!this._rows||this._rows.length===0||!this._columns)return g`<p class="message">${this.noDataMessage}</p>`;let e=this._columns,t=this._rows;return g`
      <table class="${this.striped?`striped`:``}">
        <thead>
          <tr>
            ${e.map(e=>this._renderHeader(e))}
          </tr>
          ${e.some(e=>e.filter)?g`<tr class="filter-row">
                ${e.map(e=>g`<th>${this._renderFilterControl(e)}</th>`)}
              </tr>`:a}
        </thead>
        <tbody>
          ${t.map(t=>g`
              <tr>
                ${e.map(e=>e.dataType===`mini-barchart`?this._renderMiniBarChart(Array.isArray(this._resolveAccessor(t,e.accessor))?this._resolveAccessor(t,e.accessor):[],e.hslColor??{hue:200,saturation:100,lightness:50}):g`<td>${this._resolveAccessor(t,e.accessor)??a}</td>`)}
              </tr>
            `)}
        </tbody>
      </table>
      ${this._renderPager()}
    `}_renderHeader(e){if(!e.sortable)return e.htmlLabel?g`<th >${j(e.label)}</th>`:g`<th>${e.label}</th>`;let t=this._sortState.findIndex(t=>t.column===e.accessor),n=t>=0?this._sortState[t]:void 0,r=t>=0&&this._sortState.length>1?t+1:void 0,i=n?n.direction===`asc`?`▲ `:`▼ `:`▶ `;return g`<th
      class="sortable"
      @click=${t=>this._handleHeaderClick(e,t.shiftKey)}
      ><div class="header-content"><span>${i}${e.htmlLabel?j(e.label):e.label}</span><span>${r}</span></div></th
    >`}_renderFilterControl(e){let t=e.filter;if(!t)return a;let n=this._filterValues[e.accessor]??``;switch(t.kind){case`text`:return g`<input
          type="text"
          data-filter-accessor=${e.accessor}
          .value=${n}
          @input=${t=>this._handleFilterInput(e,t.target.value,300)}
        />`;case`numeric`:return g`<input
          type="number"
          data-filter-accessor=${e.accessor}
          .value=${n}
          @input=${t=>this._handleFilterInput(e,t.target.value,300)}
        />`;case`dropdown`:return g`<select
          data-filter-accessor=${e.accessor}
          .value=${n}
          @change=${t=>this._handleFilterInput(e,t.target.value,0)}
        >
          <option value="">Any</option>
          ${(t.options??[]).map(e=>g`<option value=${e.value}>${e.label}</option>`)}
        </select>`;case`boolean`:return g`<select
          data-filter-accessor=${e.accessor}
          .value=${n}
          @change=${t=>this._handleFilterInput(e,t.target.value,0)}
        >
          <option value="">Either</option>
          <option value="true">${t.trueLabel??`Yes`}</option>
          <option value="false">${t.falseLabel??`No`}</option>
        </select>`;case`numeric-range`:{let t=this._rangeFilterValues[e.accessor]??{};return g`<div class="range-filter" data-filter-accessor=${e.accessor}>
          <input
            type="number"
            placeholder="Min"
            data-filter-bound="min"
            .value=${t.min??``}
            @input=${t=>this._handleRangeFilterInput(e,`min`,t.target.value,300)}
          />
          <input
            type="number"
            placeholder="Max"
            data-filter-bound="max"
            .value=${t.max??``}
            @input=${t=>this._handleRangeFilterInput(e,`max`,t.target.value,300)}
          />
        </div>`}case`date-range`:{let t=this._rangeFilterValues[e.accessor]??{};return g`<div class="range-filter" data-filter-accessor=${e.accessor}>
          <input
            type="date"
            data-filter-bound="min"
            .value=${t.min??``}
            @change=${t=>this._handleRangeFilterInput(e,`min`,t.target.value,0)}
          />
          <input
            type="date"
            data-filter-bound="max"
            .value=${t.max??``}
            @change=${t=>this._handleRangeFilterInput(e,`max`,t.target.value,0)}
          />
        </div>`}case`multi-select`:{let n=this._multiSelectValues[e.accessor]??[];return g`<select
          multiple
          data-filter-accessor=${e.accessor}
          @change=${t=>this._handleMultiSelectInput(e,Array.from(t.target.selectedOptions).map(e=>e.value))}
        >
          ${(t.options??[]).map(e=>g`<option value=${e.value} ?selected=${n.includes(e.value)}>${e.label}</option>`)}
        </select>`}default:return a}}_renderPager(){let e=this._pagination;return!e||e.count<=e.pageSize?a:g`
      <div class="pager">
        <button
          type="button"
          data-action="previous"
          ?disabled=${!e.hasPrevious}
          @click=${()=>this._goToPage(e.page-1)}
        >
          Previous
        </button>
        <span>Page ${e.page} of ${e.totalPages}</span>
        <button
          type="button"
          data-action="next"
          ?disabled=${!e.hasNext}
          @click=${()=>this._goToPage(e.page+1)}
        >
          Next
        </button>
      </div>
    `}_resolveAccessor(e,t){return t.split(`.`).reduce((e,t)=>{if(typeof e==`object`&&e)return e[t]},e)}};h([d({type:String})],P.prototype,`dataUrl`,void 0),h([d({type:String})],P.prototype,`noDataMessage`,void 0),h([d({type:String})],P.prototype,`loadingMessage`,void 0),h([d({type:String})],P.prototype,`errorMessage`,void 0),h([d({type:Array})],P.prototype,`initialSort`,void 0),h([d({type:Number})],P.prototype,`pageSize`,void 0),h([d({type:Boolean})],P.prototype,`striped`,void 0),h([i()],P.prototype,`_columns`,void 0),h([i()],P.prototype,`_rows`,void 0),h([i()],P.prototype,`_isLoading`,void 0),h([i()],P.prototype,`_hasError`,void 0),h([i()],P.prototype,`_errorDetail`,void 0),h([i()],P.prototype,`_pagination`,void 0),h([i()],P.prototype,`_page`,void 0),h([i()],P.prototype,`_sortState`,void 0),h([i()],P.prototype,`_filterValues`,void 0),h([i()],P.prototype,`_rangeFilterValues`,void 0),h([i()],P.prototype,`_multiSelectValues`,void 0),P=h([c(`data-table`)],P);