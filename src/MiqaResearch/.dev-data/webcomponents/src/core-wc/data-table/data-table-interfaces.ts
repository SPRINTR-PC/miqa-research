export type ColumnDataType = "string" | "number" | "date"  | "datetime" | "boolean" | "mini-barchart";
export type SortDirection = "asc" | "desc";
export type FilterKind = "text" | "text-exact" | "numeric" | "numeric-range" | "dropdown" | "multi-select" | "date-range" | "boolean";

export interface FilterOption {
  value: string;
  label: string;
}

export interface FilterDefinition {
  kind: FilterKind;
  options?: FilterOption[]; // dropdown, multi-select
  min?: number; // numeric-range
  max?: number; // numeric-range
  minDate?: string; // date-range
  maxDate?: string; // date-range
  trueLabel?: string; // boolean, default "Yes"
  falseLabel?: string; // boolean, default "No"
}

export type HslColor = Readonly<{
  hue: number;
  saturation: number;
  lightness: number;
}>;

export interface ColumnDefinition {
  accessor: string;
  label: string;
  sortable?: boolean;
  dataType?: ColumnDataType;
  hslColor?: HslColor; // for mini-barchart
  width?: string;
  defaultSort?: SortDirection;
  defaultSortOrder?: number;
  filter?: FilterDefinition | null;
  htmlLabel?: boolean; // if true, the label is treated as HTML and rendered as such
}

export interface SortDescriptor {
  column: string;
  direction: SortDirection;
}

export type SortState = SortDescriptor[];

export interface PaginationMeta {
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
  hasNext: boolean;
  hasPrevious: boolean;
}

export type DataRow = Record<string, unknown>;

export interface DataTableResponse<TRow = DataRow> {
  columns?: ColumnDefinition[] | null; // only sent by the server when requested (include_columns)
  rows: TRow[];
  pagination: PaginationMeta;
}

// The server sends snake_case JSON. The component converts `columns` and `pagination` (never `rows`) to the camelCase
// types above.
export interface PaginationMetaWire {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

export interface DataTableWireResponse<TRow = DataRow> {
  columns?: Record<string, unknown>[] | null;
  rows: TRow[];
  pagination: PaginationMetaWire;
}
