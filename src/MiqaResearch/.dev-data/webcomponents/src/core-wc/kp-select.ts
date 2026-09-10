import { LitElement, html, css, type PropertyValueMap } from 'lit';
import { customElement, property, state, query } from 'lit/decorators.js';

/**
 * Interface for select options
 */
export interface KpOption {
  label: string;
  value: string;
}

/**
 * A custom select web component built with Lit.
 * It functions like a standard HTML select element but is highly customizable.
 * 
 * @element kp-select
 */
@customElement('kp-select')
export class KpSelect extends LitElement {
  /**
   * Current selected value of the component.
   */
  @property({ type: String, reflect: true })
  public value: string = '';

  /**
   * Name attribute for form compatibility.
   */
  @property({ type: String })
  public name: string = '';

  /**
   * Placeholder text when no option is selected.
   */
  @property({ type: String })
  public placeholder: string = 'Select an option';

  /**
   * Placeholder text for the search input.
   */
  @property({ type: String })
  public searchPlaceholder: string = 'Search...';

  /**
   * Array of options to display in the dropdown.
   */
  @property({ type: Array })
  public options: KpOption[] = [];

  /**
   * Whether the component should have a built-in search functionality.
   */
  @property({ type: Boolean })
  public searchable: boolean = false;

  /**
   * Whether the dropdown is currently open.
   */
  @state()
  private _isOpen: boolean = false;

  /**
   * Current text in the search input.
   */
  @state()
  private _searchText: string = '';

  @query('.search-input')
  private _searchInput?: HTMLInputElement;

  @query('slot')
  private _slot?: HTMLSlotElement;

  static styles = css`
    :host {
      --kp-select-width: 100%;
      --kp-select-bg: var(--color-background, #ffffff);
      --kp-select-border: var(--border-color, #e5e4e7);
      --kp-select-border-radius: var(--select-border-radius, 8px);
      --kp-select-padding: var(--select-padding, 10px 12px);
      --kp-select-font-size: var(--select-font-size, 16px);
      --kp-select-text-color: var(--color-foreground, #000000);
      --kp-select-primary: var(--color-primary, #aa3bff);
      --kp-select-hover-bg: var(--select-hover-bg, #f4f3ec);
      --kp-select-dropdown-shadow: var(--select-dropdown-shadow, 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06));
      --kp-select-dropdown-max-height: var(--select-dropdown-max-height, 250px);

      display: inline-block;
      position: relative;
      width: var(--kp-select-width);
      font-family: inherit;
      color: var(--kp-select-text-color);
      box-sizing: border-box;
    }

    /* Hide the slot that contains the option tags */
    ::slotted(option) {
      display: none;
    }

    .select-trigger {
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      padding: var(--kp-select-padding);
      background-color: var(--kp-select-bg);
      border: 1px solid var(--kp-select-border);
      border-radius: var(--kp-select-border-radius);
      cursor: pointer;
      font-size: var(--kp-select-font-size);
      box-sizing: border-box;
      user-select: none;
    }

    .select-trigger:focus {
      outline: none;
      border-color: var(--kp-select-primary);
      box-shadow: 0 0 0 2px rgba(170, 59, 255, 0.2);
    }

    .select-trigger.open {
      border-bottom-left-radius: 0;
      border-bottom-right-radius: 0;
      border-color: var(--kp-select-primary);
    }

    .arrow {
      width: 1.5em;
      height: 1.5em;
      margin-left: 0.5em;
      transition: transform 0.2s ease;
      fill: currentColor;
      opacity: 0.5;
    }

    .select-trigger.open .arrow {
      transform: rotate(180deg);
    }

    .dropdown {
      position: absolute;
      top: 100%;
      left: 0;
      right: 0;
      z-index: 1000;
      background-color: var(--kp-select-bg);
      border: 1px solid var(--kp-select-primary);
      border-top: none;
      border-bottom-left-radius: var(--kp-select-border-radius);
      border-bottom-right-radius: var(--kp-select-border-radius);
      box-shadow: var(--kp-select-dropdown-shadow);
      display: none;
      flex-direction: column;
      box-sizing: border-box;
    }

    .dropdown.open {
      display: flex;
    }

    .search-container {
      padding: 8px;
      border-bottom: 1px solid var(--kp-select-border);
    }

    .search-input {
      width: 100%;
      padding: 8px;
      border: 1px solid var(--kp-select-border);
      border-radius: 4px;
      font-size: 14px;
      box-sizing: border-box;
    }

    .search-input:focus {
      outline: none;
      border-color: var(--kp-select-primary);
    }

    .options-list {
      max-height: var(--kp-select-dropdown-max-height);
      overflow-y: auto;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    .option {
      padding: var(--kp-select-padding);
      cursor: pointer;
      transition: background-color 0.1s ease;
    }

    .option:hover {
      background-color: var(--kp-select-hover-bg);
    }

    .option.selected {
      background-color: var(--kp-select-hover-bg);
      font-weight: 600;
      color: var(--kp-select-primary);
    }

    .no-results {
      padding: var(--kp-select-padding);
      color: #999;
      text-align: center;
      font-size: 14px;
    }

    .placeholder {
      color: #999;
    }
  `;

  constructor() {
    super();
    this._handleClickOutside = this._handleClickOutside.bind(this);
  }

  connectedCallback() {
    super.connectedCallback();
    document.addEventListener('click', this._handleClickOutside);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    document.removeEventListener('click', this._handleClickOutside);
  }

  protected updated(changedProperties: PropertyValueMap<any> | Map<PropertyKey, unknown>): void {
      if (changedProperties.has('_isOpen') && this._isOpen && this.searchable) {
          // Focus search input when dropdown opens
          setTimeout(() => {
              this._searchInput?.focus();
          }, 0);
      }
  }

  private _handleClickOutside(event: MouseEvent) {
    if (this._isOpen && !event.composedPath().includes(this)) {
      this._isOpen = false;
    }
  }

  private _toggleDropdown() {
    this._isOpen = !this._isOpen;
    if (this._isOpen) {
      this._searchText = '';
    }
  }

  private _handleSearch(event: Event) {
    const target = event.target as HTMLInputElement;
    this._searchText = target.value;
  }

  private _handleSlotChange() {
    this._syncOptionsFromSlot();
  }

  private _syncOptionsFromSlot() {
    if (!this._slot) return;
    
    const slottedNodes = this._slot.assignedNodes({ flatten: true });
    const newOptions: KpOption[] = [];
    
    slottedNodes.forEach(node => {
      if (node instanceof HTMLOptionElement) {
        newOptions.push({
          label: node.text,
          value: node.value
        });
      }
    });
    
    if (newOptions.length > 0) {
      this.options = newOptions;
    }
  }

  private _selectOption(option: KpOption) {
    this.value = option.value;
    this._isOpen = false;
    this._dispatchEvent();
  }

  private _dispatchEvent() {
    this.dispatchEvent(new CustomEvent('change', {
      detail: { value: this.value },
      bubbles: true,
      composed: true
    }));
    
    // Also dispatch 'input' event for form compatibility
    this.dispatchEvent(new CustomEvent('input', {
      detail: { value: this.value },
      bubbles: true,
      composed: true
    }));
  }

  private get _filteredOptions() {
    if (!this._searchText) {
      return this.options;
    }
    const searchLower = this._searchText.toLowerCase();
    return this.options.filter(opt => 
      opt.label.toLowerCase().includes(searchLower) || 
      opt.value.toLowerCase().includes(searchLower)
    );
  }

  private get _selectedOptionLabel() {
    const selected = this.options.find(opt => opt.value === this.value);
    return selected ? selected.label : null;
  }

  render() {
    const filteredOptions = this._filteredOptions;
    const selectedLabel = this._selectedOptionLabel;

    return html`
      <div 
        class="select-trigger ${this._isOpen ? 'open' : ''}" 
        @click="${this._toggleDropdown}"
        tabindex="0"
        role="combobox"
        aria-expanded="${this._isOpen}"
        aria-haspopup="listbox"
      >
        <span class="${!selectedLabel ? 'placeholder' : ''}">
          ${selectedLabel || this.placeholder}
        </span>
        <svg class="arrow" viewBox="0 0 20 20">
          <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" />
        </svg>
      </div>

      <div class="dropdown ${this._isOpen ? 'open' : ''}">
        ${this.searchable ? html`
          <div class="search-container">
            <input 
              type="text" 
              class="search-input" 
              placeholder=${this.searchPlaceholder} 
              .value="${this._searchText}"
              @input="${this._handleSearch}"
              @click="${(e: Event) => e.stopPropagation()}"
            >
          </div>
        ` : ''}
        
        <ul class="options-list" role="listbox">
          ${filteredOptions.map(option => html`
            <li 
              class="option ${this.value === option.value ? 'selected' : ''}"
              role="option"
              aria-selected="${this.value === option.value}"
              @click="${() => this._selectOption(option)}"
            >
              ${option.label}
            </li>
          `)}
          
          ${filteredOptions.length === 0 ? html`
            <li class="no-results">No options found</li>
          ` : ''}
        </ul>
      </div>

      <slot @slotchange="${this._handleSlotChange}" style="display: none;"></slot>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'kp-select': KpSelect;
  }
}