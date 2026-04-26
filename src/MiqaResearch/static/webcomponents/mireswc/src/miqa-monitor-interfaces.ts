export interface WildCardFilterOption {
    value: string;
    wildcard: boolean;
}

export interface MiqaMonitorFilterCategoryOption {
    id: string;
    title: string;
    wildcard: boolean;
    icon: string | undefined;
    selected: boolean;
}

export interface MiqaMonitorFilterRange {
    min: number;
    max: number;
    selected_min: number;
    selected_max: number;
    include_null: boolean;
}

export interface MiqaMonitorFilter {
    gender: MiqaMonitorFilterCategoryOption[];
    age: MiqaMonitorFilterRange;
    studyDescription: MiqaMonitorFilterCategoryOption[];
    seriesDescription: MiqaMonitorFilterCategoryOption[];
}

export interface MiqaMonitorColumn {
    title: string;
    id: string;
    dataType: string;
}

export interface MiqaMonitorTableColumn {
    header: string;
    dataType: string;
    width: number | undefined;
    values: any[];
}

export interface MiqaMonitorTableData {
    columns: MiqaMonitorTableColumn[];
}