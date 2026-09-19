import { describe, it, expect, vi, beforeEach } from "vitest";
import "./data-table";
import { DataTable } from "./data-table";
import { ApiService } from "./api-service";
import type {
  ColumnDefinition,
  DataTableWireResponse,
  PaginationMeta,
} from "./data-table-interfaces";

describe("DataTable", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("should be registered as a custom element", () => {
    const el = document.createElement("data-table");
    expect(el).toBeInstanceOf(DataTable);
  });

  it("should have correct default properties", () => {
    const el = new DataTable();
    expect(el.dataUrl).toBe("");
    expect(el.noDataMessage).toBe("No data available");
    expect(el.loadingMessage).toBe("Loading data...");
    expect(el.errorMessage).toBe("Something went wrong loading data.");
  });

  it("should render no data message when no dataUrl is set", async () => {
    const el = new DataTable();
    document.body.appendChild(el);
    await el.updateComplete;

    const p = el.shadowRoot?.querySelector("p");
    expect(p?.textContent).toBe("No data available");
    document.body.removeChild(el);
  });

  it("should render loading message while data is loading", async () => {
    let resolvePromise: (value: any) => void;
    const pendingPromise = new Promise((resolve) => {
      resolvePromise = resolve;
    });
    vi.spyOn(ApiService, "getData").mockImplementation(() => pendingPromise as any);

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);

    await el.updateComplete;
    const p = el.shadowRoot?.querySelector("p");
    expect(p?.textContent).toBe("Loading data...");

    resolvePromise!({ success: true, data: { rows: [], columns: [], pagination: {} } });
    await new Promise((r) => setTimeout(r, 10));
    document.body.removeChild(el);
  });

  it("should fetch data from dataUrl and render columns and rows", async () => {
    const mockResponse: DataTableWireResponse = {
      columns: [
        { accessor: "machineName", label: "Machine" },
        { accessor: "numExams", label: "Exams" },
      ],
      rows: [
        { machineName: "CT1", numExams: 12 },
        { machineName: "CT2", numExams: 7 },
      ],
      pagination: { page: 1, page_size: 50, total_items: 2, total_pages: 1, has_next: false, has_previous: false },
    };
    vi.spyOn(ApiService, "getData").mockResolvedValue({ success: true, data: mockResponse, message: "ok" });

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);

    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    expect(ApiService.getData).toHaveBeenCalledWith("https://api.example.com/table-data?page=1&page_size=50&include_columns=true");

    const headers = Array.from(el.shadowRoot?.querySelectorAll("th") ?? []).map((th) => th.textContent);
    expect(headers).toEqual(["Machine", "Exams"]);

    const rows = el.shadowRoot?.querySelectorAll("tbody tr");
    expect(rows?.length).toBe(2);
    const firstRowCells = Array.from(rows?.[0].querySelectorAll("td") ?? []).map((td) => td.textContent);
    expect(firstRowCells).toEqual(["CT1", "12"]);

    document.body.removeChild(el);
  });

  it("should render error message when the fetch fails", async () => {
    vi.spyOn(ApiService, "getData").mockRejectedValue(new Error("Network Error"));

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);

    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    const p = el.shadowRoot?.querySelector("p");
    expect(p?.textContent).toBe("Something went wrong loading data.");
    document.body.removeChild(el);
  });

  it("should derive columns from the first row's keys when the response omits columns", async () => {
    const mockResponse: DataTableWireResponse = {
      rows: [
        { machineName: "CT1", numExams: 12 },
        { machineName: "CT2", numExams: 7 },
      ],
      pagination: { page: 1, page_size: 50, total_items: 2, total_pages: 1, has_next: false, has_previous: false },
    };
    vi.spyOn(ApiService, "getData").mockResolvedValue({ success: true, data: mockResponse, message: "ok" });

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);

    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    const headers = Array.from(el.shadowRoot?.querySelectorAll("th") ?? []).map((th) => th.textContent);
    expect(headers).toEqual(["machineName", "numExams"]);

    document.body.removeChild(el);
  });

  it("should render no data message when the response has an empty rows array", async () => {
    const mockResponse: DataTableWireResponse = {
      columns: [{ accessor: "machineName", label: "Machine" }],
      rows: [],
      pagination: { page: 1, page_size: 50, total_items: 0, total_pages: 1, has_next: false, has_previous: false },
    };
    vi.spyOn(ApiService, "getData").mockResolvedValue({ success: true, data: mockResponse, message: "ok" });

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);

    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    const p = el.shadowRoot?.querySelector("p");
    expect(p?.textContent).toBe("No data available");
    document.body.removeChild(el);
  });

  it("should not render pager controls when total row count fits in one page", async () => {
    const mockResponse: DataTableWireResponse = {
      columns: [{ accessor: "machineName", label: "Machine" }],
      rows: [{ machineName: "CT1" }],
      pagination: { page: 1, page_size: 50, total_items: 1, total_pages: 1, has_next: false, has_previous: false },
    };
    vi.spyOn(ApiService, "getData").mockResolvedValue({ success: true, data: mockResponse, message: "ok" });

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);

    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    expect(el.shadowRoot?.querySelector(".pager")).toBeNull();
    document.body.removeChild(el);
  });

  it("should render pager controls when total row count exceeds page size", async () => {
    const mockResponse: DataTableWireResponse = {
      columns: [{ accessor: "machineName", label: "Machine" }],
      rows: Array.from({ length: 50 }, (_, i) => ({ machineName: `CT${i}` })),
      pagination: { page: 1, page_size: 50, total_items: 60, total_pages: 2, has_next: true, has_previous: false },
    };
    vi.spyOn(ApiService, "getData").mockResolvedValue({ success: true, data: mockResponse, message: "ok" });

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);

    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    const pager = el.shadowRoot?.querySelector(".pager");
    expect(pager).not.toBeNull();
    const prevButton = pager?.querySelector('[data-action="previous"]') as HTMLButtonElement;
    const nextButton = pager?.querySelector('[data-action="next"]') as HTMLButtonElement;
    expect(prevButton.disabled).toBe(true);
    expect(nextButton.disabled).toBe(false);

    document.body.removeChild(el);
  });

  it("should convert only the response envelope from snake_case and leave row keys untouched", async () => {
    vi.spyOn(ApiService, "getData").mockResolvedValue({
      success: true,
      data: {
        columns: [{ accessor: "clinic__clinic_name", label: "Clinic Name", data_type: "string", sortable: true }],
        rows: [{ clinic__clinic_name: "Clinic A" }],
        pagination: { page: 1, page_size: 50, total_items: 1, total_pages: 1, has_next: false, has_previous: false },
      },
      message: "ok",
    });

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);
    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    const internals = el as unknown as { _columns: ColumnDefinition[]; _pagination: PaginationMeta };
    expect(internals._columns[0]).toMatchObject({ accessor: "clinic__clinic_name", dataType: "string" });
    expect(internals._pagination).toEqual({
      page: 1, pageSize: 50, totalItems: 1, totalPages: 1, hasNext: false, hasPrevious: false,
    });
    const cells = Array.from(el.shadowRoot?.querySelectorAll("tbody td") ?? []).map((td) => td.textContent);
    expect(cells).toEqual(["Clinic A"]);

    document.body.removeChild(el);
  });

  it("should keep the first-load columns when later pages omit them", async () => {
    const pagination = { page: 1, page_size: 50, total_items: 60, total_pages: 2, has_next: true, has_previous: false };
    vi.spyOn(ApiService, "getData")
      .mockResolvedValueOnce({
        success: true,
        data: { columns: [{ accessor: "machineName", label: "Machine" }], rows: [{ machineName: "CT1" }], pagination },
        message: "ok",
      })
      .mockResolvedValueOnce({
        success: true,
        data: {
          columns: null,
          rows: [{ machineName: "CT2" }],
          pagination: { ...pagination, page: 2, has_next: false, has_previous: true },
        },
        message: "ok",
      });

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);
    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    (el.shadowRoot?.querySelector('[data-action="next"]') as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    const headers = Array.from(el.shadowRoot?.querySelectorAll("th") ?? []).map((th) => th.textContent?.trim());
    expect(headers).toEqual(["Machine"]);
    const cells = Array.from(el.shadowRoot?.querySelectorAll("tbody td") ?? []).map((td) => td.textContent);
    expect(cells).toEqual(["CT2"]);

    document.body.removeChild(el);
  });

  it("should fetch the next page and re-render when the next control is clicked", async () => {
    const firstPage: DataTableWireResponse = {
      columns: [{ accessor: "machineName", label: "Machine" }],
      rows: [{ machineName: "CT-page1" }],
      pagination: { page: 1, page_size: 50, total_items: 60, total_pages: 2, has_next: true, has_previous: false },
    };
    const secondPage: DataTableWireResponse = {
      columns: [{ accessor: "machineName", label: "Machine" }],
      rows: [{ machineName: "CT-page2" }],
      pagination: { page: 2, page_size: 50, total_items: 60, total_pages: 2, has_next: false, has_previous: true },
    };
    vi.spyOn(ApiService, "getData")
      .mockResolvedValueOnce({ success: true, data: firstPage, message: "ok" })
      .mockResolvedValueOnce({ success: true, data: secondPage, message: "ok" });

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);

    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    const nextButton = el.shadowRoot?.querySelector('[data-action="next"]') as HTMLButtonElement;
    nextButton.click();

    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    expect(ApiService.getData).toHaveBeenLastCalledWith("https://api.example.com/table-data?page=2&page_size=50");
    const cells = Array.from(el.shadowRoot?.querySelectorAll("tbody td") ?? []).map((td) => td.textContent);
    expect(cells).toEqual(["CT-page2"]);

    const prevButton = el.shadowRoot?.querySelector('[data-action="previous"]') as HTMLButtonElement;
    expect(prevButton.disabled).toBe(false);
    const nextButtonAfter = el.shadowRoot?.querySelector('[data-action="next"]') as HTMLButtonElement;
    expect(nextButtonAfter.disabled).toBe(true);

    document.body.removeChild(el);
  });

  it("should fetch the previous page when the previous control is clicked", async () => {
    const firstPage: DataTableWireResponse = {
      columns: [{ accessor: "machineName", label: "Machine" }],
      rows: [{ machineName: "CT-page1" }],
      pagination: { page: 1, page_size: 50, total_items: 60, total_pages: 2, has_next: true, has_previous: false },
    };
    const secondPage: DataTableWireResponse = {
      columns: [{ accessor: "machineName", label: "Machine" }],
      rows: [{ machineName: "CT-page2" }],
      pagination: { page: 2, page_size: 50, total_items: 60, total_pages: 2, has_next: false, has_previous: true },
    };
    vi.spyOn(ApiService, "getData")
      .mockResolvedValueOnce({ success: true, data: firstPage, message: "ok" })
      .mockResolvedValueOnce({ success: true, data: secondPage, message: "ok" })
      .mockResolvedValueOnce({ success: true, data: firstPage, message: "ok" });

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);

    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;
    (el.shadowRoot?.querySelector('[data-action="next"]') as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    (el.shadowRoot?.querySelector('[data-action="previous"]') as HTMLButtonElement).click();
    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    expect(ApiService.getData).toHaveBeenLastCalledWith("https://api.example.com/table-data?page=1&page_size=50");
    const cells = Array.from(el.shadowRoot?.querySelectorAll("tbody td") ?? []).map((td) => td.textContent);
    expect(cells).toEqual(["CT-page1"]);

    document.body.removeChild(el);
  });

  describe("sort interactivity", () => {
    const twoSortableColumnsResponse: DataTableWireResponse = {
      columns: [
        { accessor: "machineName", label: "Machine", sortable: true },
        { accessor: "numExams", label: "Exams", sortable: true },
        { accessor: "hospital", label: "Hospital" },
      ],
      rows: [{ machineName: "CT1", numExams: 5, hospital: "General" }],
      pagination: { page: 1, page_size: 50, total_items: 1, total_pages: 1, has_next: false, has_previous: false },
    };

    function shiftClick(el: HTMLElement) {
      el.dispatchEvent(new MouseEvent("click", { bubbles: true, shiftKey: true }));
    }

    async function setUpTable(): Promise<DataTable> {
      vi.spyOn(ApiService, "getData").mockResolvedValue({
        success: true,
        data: twoSortableColumnsResponse,
        message: "ok",
      });
      const el = new DataTable();
      el.dataUrl = "https://api.example.com/table-data";
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;
      return el;
    }

    function headerFor(el: DataTable, label: string): HTMLElement {
      const headers = Array.from(el.shadowRoot?.querySelectorAll("th") ?? []);
      const header = headers.find((th) => th.textContent?.includes(label));
      if (!header) throw new Error(`No header found for ${label}`);
      return header as HTMLElement;
    }

    it("should sort ascending and re-fetch when a sortable header is clicked", async () => {
      const el = await setUpTable();
      headerFor(el, "Machine").click();
      await new Promise((r) => setTimeout(r, 10));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&sort=machineName"
      );
      document.body.removeChild(el);
    });

    it("should toggle to descending when the sole active sort column is clicked again", async () => {
      const el = await setUpTable();
      headerFor(el, "Machine").click();
      await new Promise((r) => setTimeout(r, 10));
      headerFor(el, "Machine").click();
      await new Promise((r) => setTimeout(r, 10));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&sort=-machineName"
      );
      document.body.removeChild(el);
    });

    it("should reset to single-column ascending when a different column is clicked without shift", async () => {
      const el = await setUpTable();
      headerFor(el, "Machine").click();
      await new Promise((r) => setTimeout(r, 10));
      headerFor(el, "Exams").click();
      await new Promise((r) => setTimeout(r, 10));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&sort=numExams"
      );
      document.body.removeChild(el);
    });

    it("should append a shift-clicked column to the current sort", async () => {
      const el = await setUpTable();
      headerFor(el, "Machine").click();
      await new Promise((r) => setTimeout(r, 10));
      shiftClick(headerFor(el, "Exams"));
      await new Promise((r) => setTimeout(r, 10));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&sort=machineName,numExams"
      );
      document.body.removeChild(el);
    });

    it("should toggle direction in place when shift-clicking a column already in the sort", async () => {
      const el = await setUpTable();
      headerFor(el, "Machine").click();
      await new Promise((r) => setTimeout(r, 10));
      shiftClick(headerFor(el, "Exams"));
      await new Promise((r) => setTimeout(r, 10));
      shiftClick(headerFor(el, "Exams"));
      await new Promise((r) => setTimeout(r, 10));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&sort=machineName,-numExams"
      );
      document.body.removeChild(el);
    });

    it("should not change sort state when a non-sortable header is clicked", async () => {
      const el = await setUpTable();
      const callsBefore = (ApiService.getData as any).mock.calls.length;
      headerFor(el, "Hospital").click();
      await new Promise((r) => setTimeout(r, 10));

      expect((ApiService.getData as any).mock.calls.length).toBe(callsBefore);
      document.body.removeChild(el);
    });

    it("should reset pagination to page 1 when sort changes", async () => {
      const manyRowsResponse: DataTableWireResponse = {
        columns: twoSortableColumnsResponse.columns,
        rows: [{ machineName: "CT1", numExams: 5, hospital: "General" }],
        pagination: { page: 2, page_size: 50, total_items: 60, total_pages: 2, has_next: false, has_previous: true },
      };
      vi.spyOn(ApiService, "getData")
        .mockResolvedValueOnce({ success: true, data: manyRowsResponse, message: "ok" })
        .mockResolvedValue({ success: true, data: twoSortableColumnsResponse, message: "ok" });

      const el = new DataTable();
      el.dataUrl = "https://api.example.com/table-data";
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;

      headerFor(el, "Machine").click();
      await new Promise((r) => setTimeout(r, 10));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&sort=machineName"
      );
      document.body.removeChild(el);
    });
  });

  describe("filter interactivity", () => {
    const filterableColumnsResponse: DataTableWireResponse = {
      columns: [
        { accessor: "machineName", label: "Machine", filter: { kind: "text" } },
        { accessor: "numExams", label: "Exams", filter: { kind: "numeric" } },
        {
          accessor: "hospital",
          label: "Hospital",
          filter: {
            kind: "dropdown",
            options: [
              { value: "gen", label: "General" },
              { value: "spec", label: "Specialist" },
            ],
          },
        },
        { accessor: "active", label: "Active", filter: { kind: "boolean", trueLabel: "Yes", falseLabel: "No" } },
        { accessor: "unfiltered", label: "Plain" },
      ],
      rows: [{ machineName: "CT1", numExams: 5, hospital: "gen", active: true, unfiltered: "x" }],
      pagination: { page: 1, page_size: 50, total_items: 1, total_pages: 1, has_next: false, has_previous: false },
    };

    async function setUpFilterableTable(): Promise<DataTable> {
      vi.spyOn(ApiService, "getData").mockResolvedValue({
        success: true,
        data: filterableColumnsResponse,
        message: "ok",
      });
      const el = new DataTable();
      el.dataUrl = "https://api.example.com/table-data";
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;
      return el;
    }

    function filterControl(el: DataTable, accessor: string): HTMLElement {
      const control = el.shadowRoot?.querySelector(`[data-filter-accessor="${accessor}"]`);
      if (!control) throw new Error(`No filter control for ${accessor}`);
      return control as HTMLElement;
    }

    it("should render a text input for a text filter column", async () => {
      const el = await setUpFilterableTable();
      const input = filterControl(el, "machineName") as HTMLInputElement;
      expect(input.tagName).toBe("INPUT");
      expect(input.type).toBe("text");
      document.body.removeChild(el);
    });

    it("should render a number input for a numeric filter column", async () => {
      const el = await setUpFilterableTable();
      const input = filterControl(el, "numExams") as HTMLInputElement;
      expect(input.tagName).toBe("INPUT");
      expect(input.type).toBe("number");
      document.body.removeChild(el);
    });

    it("should render a select with declared options for a dropdown filter column", async () => {
      const el = await setUpFilterableTable();
      const select = filterControl(el, "hospital") as HTMLSelectElement;
      expect(select.tagName).toBe("SELECT");
      const labels = Array.from(select.options).map((o) => o.textContent);
      expect(labels).toEqual(["Any", "General", "Specialist"]);
      document.body.removeChild(el);
    });

    it("should render a select with either/true/false states for a boolean filter column", async () => {
      const el = await setUpFilterableTable();
      const select = filterControl(el, "active") as HTMLSelectElement;
      const labels = Array.from(select.options).map((o) => o.textContent);
      expect(labels).toEqual(["Either", "Yes", "No"]);
      document.body.removeChild(el);
    });

    it("should render no filter control for a column without a filter", async () => {
      const el = await setUpFilterableTable();
      expect(el.shadowRoot?.querySelector('[data-filter-accessor="unfiltered"]')).toBeNull();
      document.body.removeChild(el);
    });

    it("should debounce a text filter before re-fetching", async () => {
      const el = await setUpFilterableTable();
      const input = filterControl(el, "machineName") as HTMLInputElement;

      input.value = "ct";
      input.dispatchEvent(new Event("input"));
      await new Promise((r) => setTimeout(r, 50));
      // Not yet re-fetched: still within the debounce window.
      expect(ApiService.getData).toHaveBeenCalledTimes(1);

      await new Promise((r) => setTimeout(r, 300));
      expect(ApiService.getData).toHaveBeenCalledTimes(2);
      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&machineName__icontains=ct"
      );
      document.body.removeChild(el);
    });

    it("should debounce a numeric filter and encode it as a bare exact-match param", async () => {
      const el = await setUpFilterableTable();
      const input = filterControl(el, "numExams") as HTMLInputElement;

      input.value = "5";
      input.dispatchEvent(new Event("input"));
      await new Promise((r) => setTimeout(r, 350));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&numExams=5"
      );
      document.body.removeChild(el);
    });

    it("should apply a dropdown filter immediately with no debounce delay", async () => {
      const el = await setUpFilterableTable();
      const select = filterControl(el, "hospital") as HTMLSelectElement;

      select.value = "gen";
      select.dispatchEvent(new Event("change"));
      await new Promise((r) => setTimeout(r, 10));

      expect(ApiService.getData).toHaveBeenCalledTimes(2);
      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&hospital=gen"
      );
      document.body.removeChild(el);
    });

    it("should apply a boolean filter immediately and clear it when 'either' is selected", async () => {
      const el = await setUpFilterableTable();
      const select = filterControl(el, "active") as HTMLSelectElement;

      select.value = "true";
      select.dispatchEvent(new Event("change"));
      await new Promise((r) => setTimeout(r, 10));
      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&active=true"
      );

      select.value = "";
      select.dispatchEvent(new Event("change"));
      await new Promise((r) => setTimeout(r, 10));
      expect(ApiService.getData).toHaveBeenLastCalledWith("https://api.example.com/table-data?page=1&page_size=50");

      document.body.removeChild(el);
    });

    it("should reset pagination to page 1 when a filter changes", async () => {
      const pageTwoResponse: DataTableWireResponse = {
        ...filterableColumnsResponse,
        pagination: { page: 2, page_size: 50, total_items: 60, total_pages: 2, has_next: false, has_previous: true },
      };
      vi.spyOn(ApiService, "getData")
        .mockResolvedValueOnce({ success: true, data: pageTwoResponse, message: "ok" })
        .mockResolvedValue({ success: true, data: filterableColumnsResponse, message: "ok" });

      const el = new DataTable();
      el.dataUrl = "https://api.example.com/table-data";
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;

      const select = filterControl(el, "hospital") as HTMLSelectElement;
      select.value = "gen";
      select.dispatchEvent(new Event("change"));
      await new Promise((r) => setTimeout(r, 10));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&hospital=gen"
      );
      document.body.removeChild(el);
    });
  });

  describe("range and multi-value filter interactivity", () => {
    const rangeColumnsResponse: DataTableWireResponse = {
      columns: [
        { accessor: "medianDose", label: "Median dose", filter: { kind: "numeric-range" } },
        { accessor: "firstStudy", label: "First study", filter: { kind: "date-range" } },
        {
          accessor: "hospital",
          label: "Hospital",
          filter: {
            kind: "multi-select",
            options: [
              { value: "gen", label: "General" },
              { value: "spec", label: "Specialist" },
              { value: "west", label: "West Wing" },
            ],
          },
        },
      ],
      rows: [{ medianDose: 50, firstStudy: "2024-01-01", hospital: "gen" }],
      pagination: { page: 1, page_size: 50, total_items: 1, total_pages: 1, has_next: false, has_previous: false },
    };

    async function setUpRangeTable(): Promise<DataTable> {
      vi.spyOn(ApiService, "getData").mockResolvedValue({ success: true, data: rangeColumnsResponse, message: "ok" });
      const el = new DataTable();
      el.dataUrl = "https://api.example.com/table-data";
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;
      return el;
    }

    function rangeInputs(el: DataTable, accessor: string): { min: HTMLInputElement; max: HTMLInputElement } {
      const container = el.shadowRoot?.querySelector(`[data-filter-accessor="${accessor}"]`);
      if (!container) throw new Error(`No filter container for ${accessor}`);
      return {
        min: container.querySelector('[data-filter-bound="min"]') as HTMLInputElement,
        max: container.querySelector('[data-filter-bound="max"]') as HTMLInputElement,
      };
    }

    it("should render independent min/max number inputs for a numeric-range filter", async () => {
      const el = await setUpRangeTable();
      const { min, max } = rangeInputs(el, "medianDose");
      expect(min.type).toBe("number");
      expect(max.type).toBe("number");
      document.body.removeChild(el);
    });

    it("should narrow correctly with only one numeric-range bound set, debounced", async () => {
      const el = await setUpRangeTable();
      const { min } = rangeInputs(el, "medianDose");

      min.value = "20";
      min.dispatchEvent(new Event("input"));
      await new Promise((r) => setTimeout(r, 50));
      expect(ApiService.getData).toHaveBeenCalledTimes(1);

      await new Promise((r) => setTimeout(r, 300));
      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&medianDose__gte=20"
      );
      document.body.removeChild(el);
    });

    it("should send both bounds when both numeric-range inputs are set", async () => {
      const el = await setUpRangeTable();
      const { min, max } = rangeInputs(el, "medianDose");

      min.value = "20";
      min.dispatchEvent(new Event("input"));
      max.value = "80";
      max.dispatchEvent(new Event("input"));
      await new Promise((r) => setTimeout(r, 350));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&medianDose__gte=20&medianDose__lte=80"
      );
      document.body.removeChild(el);
    });

    it("should render independent date inputs for a date-range filter and apply immediately", async () => {
      const el = await setUpRangeTable();
      const { min, max } = rangeInputs(el, "firstStudy");
      expect(min.type).toBe("date");
      expect(max.type).toBe("date");

      min.value = "2023-01-01";
      min.dispatchEvent(new Event("change"));
      await new Promise((r) => setTimeout(r, 10));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&firstStudy__gte=2023-01-01"
      );
      document.body.removeChild(el);
    });

    it("should render a multi-select control offering all declared options", async () => {
      const el = await setUpRangeTable();
      const select = el.shadowRoot?.querySelector('[data-filter-accessor="hospital"]') as HTMLSelectElement;
      expect(select.multiple).toBe(true);
      const labels = Array.from(select.options).map((o) => o.textContent);
      expect(labels).toEqual(["General", "Specialist", "West Wing"]);
      document.body.removeChild(el);
    });

    it("should apply a multi-select filter immediately with all selected values joined", async () => {
      const el = await setUpRangeTable();
      const select = el.shadowRoot?.querySelector('[data-filter-accessor="hospital"]') as HTMLSelectElement;
      select.options[0].selected = true;
      select.options[2].selected = true;
      select.dispatchEvent(new Event("change"));
      await new Promise((r) => setTimeout(r, 10));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&hospital__in=gen%2Cwest"
      );
      document.body.removeChild(el);
    });

    it("should reset pagination to page 1 when a range filter changes", async () => {
      const el = await setUpRangeTable();
      const { min } = rangeInputs(el, "firstStudy");
      min.value = "2023-01-01";
      min.dispatchEvent(new Event("change"));
      await new Promise((r) => setTimeout(r, 10));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&firstStudy__gte=2023-01-01"
      );
      document.body.removeChild(el);
    });
  });

  describe("component property overrides", () => {
    const basicResponse: DataTableWireResponse = {
      columns: [{ accessor: "machineName", label: "Machine", sortable: true }],
      rows: [{ machineName: "CT1" }],
      pagination: { page: 1, page_size: 50, total_items: 1, total_pages: 1, has_next: false, has_previous: false },
    };

    it("should send the initialSort property as the sort param on the first fetch", async () => {
      vi.spyOn(ApiService, "getData").mockResolvedValue({ success: true, data: basicResponse, message: "ok" });

      const el = new DataTable();
      el.dataUrl = "https://api.example.com/table-data";
      el.initialSort = [{ column: "machineName", direction: "desc" }];
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;

      expect(ApiService.getData).toHaveBeenCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&include_columns=true&sort=-machineName"
      );
      document.body.removeChild(el);
    });

    it("should use the pageSize property as the initial page-size request", async () => {
      vi.spyOn(ApiService, "getData").mockResolvedValue({ success: true, data: basicResponse, message: "ok" });

      const el = new DataTable();
      el.dataUrl = "https://api.example.com/table-data";
      el.pageSize = 25;
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;

      expect(ApiService.getData).toHaveBeenCalledWith("https://api.example.com/table-data?page=1&page_size=25&include_columns=true");
      document.body.removeChild(el);
    });

    it("should display a custom noDataMessage instead of the default", async () => {
      const el = new DataTable();
      el.noDataMessage = "Nothing here!";
      document.body.appendChild(el);
      await el.updateComplete;

      expect(el.shadowRoot?.querySelector("p")?.textContent).toBe("Nothing here!");
      document.body.removeChild(el);
    });

    it("should display a custom loadingMessage instead of the default", async () => {
      const pending = new Promise(() => {});
      vi.spyOn(ApiService, "getData").mockImplementation(() => pending as any);

      const el = new DataTable();
      el.loadingMessage = "Hang tight...";
      el.dataUrl = "https://api.example.com/table-data";
      document.body.appendChild(el);
      await el.updateComplete;

      expect(el.shadowRoot?.querySelector("p")?.textContent).toBe("Hang tight...");
      document.body.removeChild(el);
    });

    it("should interpolate the {message} token in errorMessage with the actual error detail", async () => {
      vi.spyOn(ApiService, "getData").mockRejectedValue(new Error("Network timeout"));

      const el = new DataTable();
      el.errorMessage = "Failed to load: {message}";
      el.dataUrl = "https://api.example.com/table-data";
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;

      expect(el.shadowRoot?.querySelector("p")?.textContent).toBe("Failed to load: Network timeout");
      document.body.removeChild(el);
    });

    it("should fall back to static errorMessage text when it has no interpolation token", async () => {
      vi.spyOn(ApiService, "getData").mockRejectedValue(new Error("Network timeout"));

      const el = new DataTable();
      el.errorMessage = "Something broke.";
      el.dataUrl = "https://api.example.com/table-data";
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;

      expect(el.shadowRoot?.querySelector("p")?.textContent).toBe("Something broke.");
      document.body.removeChild(el);
    });
  });
});
