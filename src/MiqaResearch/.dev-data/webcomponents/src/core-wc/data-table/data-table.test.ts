import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import "./data-table";
import { DataTable } from "./data-table";
import { ApiService } from "./api-service";
import type {
  ColumnDefinition,
  DataTableWireResponse,
  PaginationMeta,
  SortDescriptor,
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

  it("should keep the header in the DOM while fetching new rows when columns are unchanged", async () => {
    const pagination = { page: 1, page_size: 50, total_items: 60, total_pages: 2, has_next: true, has_previous: false };
    let resolveSecond: (value: any) => void;
    vi.spyOn(ApiService, "getData")
      .mockResolvedValueOnce({
        success: true,
        data: { columns: [{ accessor: "machineName", label: "Machine" }], rows: [{ machineName: "CT1" }], pagination },
        message: "ok",
      })
      .mockImplementationOnce(() => new Promise((resolve) => (resolveSecond = resolve)) as any);

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);
    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    const headerBefore = el.shadowRoot?.querySelector("th");
    (el.shadowRoot?.querySelector('[data-action="next"]') as HTMLButtonElement).click();
    await el.updateComplete;

    expect(el.shadowRoot?.querySelector("th")).toBe(headerBefore);
    expect(el.shadowRoot?.querySelector("p.message")).toBeNull();

    resolveSecond!({
      success: true,
      data: {
        columns: null,
        rows: [{ machineName: "CT2" }],
        pagination: { ...pagination, page: 2, has_next: false, has_previous: true },
      },
      message: "ok",
    });
    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    expect(el.shadowRoot?.querySelector("th")).toBe(headerBefore);
    const cells = Array.from(el.shadowRoot?.querySelectorAll("tbody td") ?? []).map((td) => td.textContent);
    expect(cells).toEqual(["CT2"]);

    document.body.removeChild(el);
  });

  it("should refetch columns and rows and drop stale filters and sort when dataUrl changes", async () => {
    const pagination = { page: 1, page_size: 50, total_items: 1, total_pages: 1, has_next: false, has_previous: false };
    const spy = vi.spyOn(ApiService, "getData")
      .mockResolvedValueOnce({
        success: true,
        data: {
          columns: [{ accessor: "machineName", label: "Machine", sortable: true, filter: { kind: "text" } }],
          rows: [{ machineName: "CT1" }],
          pagination,
        },
        message: "ok",
      })
      .mockResolvedValueOnce({
        success: true,
        data: {
          columns: [
            { accessor: "pid", label: "PID" },
            { accessor: "machineName", label: "Machine" },
          ],
          rows: [{ pid: "1912", machineName: "CT1" }],
          pagination,
        },
        message: "ok",
      });

    const el = new DataTable();
    el.dataUrl = "https://api.example.com/table-data";
    document.body.appendChild(el);
    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    (el.shadowRoot?.querySelector("th.sortable") as HTMLElement).click();
    await new Promise((r) => setTimeout(r, 10));
    spy.mockClear();
    spy.mockResolvedValueOnce({
      success: true,
      data: {
        columns: [
          { accessor: "pid", label: "PID" },
          { accessor: "machineName", label: "Machine" },
        ],
        rows: [{ pid: "1912", machineName: "CT1" }],
        pagination,
      },
      message: "ok",
    });

    el.dataUrl = "https://api.example.com/table-data?include_pid=true";
    await new Promise((r) => setTimeout(r, 10));
    await el.updateComplete;

    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith(
      "https://api.example.com/table-data?include_pid=true&page=1&page_size=50&include_columns=true"
    );
    const headers = Array.from(el.shadowRoot?.querySelectorAll("th") ?? []).map((th) => th.textContent?.trim());
    expect(headers).toEqual(["PID", "Machine"]);

    document.body.removeChild(el);
  });

  describe("date and datetime cells", () => {
    beforeEach(() => {
      vi.stubEnv("TZ", "Asia/Tokyo"); // UTC+9: 23:30Z on the 1st is 08:30 on the 2nd
    });

    afterEach(() => {
      vi.unstubAllEnvs();
    });

    async function renderCells(row: Record<string, unknown>) {
      vi.spyOn(ApiService, "getData").mockResolvedValue({
        success: true,
        data: {
          columns: [
            { accessor: "signed_at", label: "Signed", data_type: "datetime" },
            { accessor: "birthday", label: "Birthday", data_type: "date" },
            { accessor: "clinic__clinic_name", label: "Clinic", data_type: "string" },
          ],
          rows: [row],
          pagination: { page: 1, page_size: 50, total_items: 1, total_pages: 1, has_next: false, has_previous: false },
        },
        message: "ok",
      });
      const el = new DataTable();
      el.dataUrl = "https://api.example.com/table-data";
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;
      const cells = Array.from(el.shadowRoot?.querySelectorAll("tbody td") ?? []).map((td) => td.textContent?.trim());
      document.body.removeChild(el);
      return cells;
    }

    it("should render a datetime as yyyy-mm-dd HH:MM:SS converted to the local timezone", async () => {
      const [signedAt] = await renderCells({ signed_at: "2026-03-01T23:30:00+00:00", birthday: "2000-01-31" });

      expect(signedAt).toBe("2026-03-02 08:30:00");
    });

    it("should render a date column as yyyy-mm-dd, with no time", async () => {
      const [, birthday] = await renderCells({ signed_at: "2026-03-01T23:30:00+00:00", birthday: "2000-01-31" });

      expect(birthday).toBe("2000-01-31");
    });

    it("should render only the date when a date column receives a value with a time", async () => {
      const [, birthday] = await renderCells({ signed_at: null, birthday: "2000-01-31T23:59:00+00:00" });

      expect(birthday).toBe("2000-01-31");
    });

    it("should leave other columns and empty date cells untouched", async () => {
      const cells = await renderCells({ signed_at: null, birthday: null, clinic__clinic_name: "Clinic A" });

      expect(cells).toEqual(["", "", "Clinic A"]);
    });
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

  describe("page input", () => {
    const columns = [{ accessor: "machineName", label: "Machine" }];
    const pageResponse = (page: number): DataTableWireResponse => ({
      columns,
      rows: [{ machineName: `CT-page${page}` }],
      pagination: {
        page,
        page_size: 50,
        total_items: 250,
        total_pages: 5,
        has_next: page < 5,
        has_previous: page > 1,
      },
    });

    async function setUpPagedTable(): Promise<DataTable> {
      vi.spyOn(ApiService, "getData").mockImplementation(async (url: string) => {
        const page = Number(new URL(url).searchParams.get("page"));
        return { success: true, data: pageResponse(page), message: "ok" };
      });
      const el = new DataTable();
      el.dataUrl = "https://api.example.com/table-data";
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;
      return el;
    }

    function pageInput(el: DataTable): HTMLInputElement {
      return el.shadowRoot?.querySelector('input[data-action="page-input"]') as HTMLInputElement;
    }

    async function submitPage(el: DataTable, value: string) {
      const input = pageInput(el);
      input.value = value;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;
    }

    it("should render the current page in a number input bounded by total pages", async () => {
      const el = await setUpPagedTable();
      const input = pageInput(el);
      expect(input.type).toBe("number");
      expect(input.value).toBe("1");
      expect(input.min).toBe("1");
      expect(input.max).toBe("5");
      document.body.removeChild(el);
    });

    it("should fetch the typed page", async () => {
      const el = await setUpPagedTable();
      await submitPage(el, "3");
      expect(ApiService.getData).toHaveBeenLastCalledWith("https://api.example.com/table-data?page=3&page_size=50");
      expect(pageInput(el).value).toBe("3");
      document.body.removeChild(el);
    });

    it("should clamp a page above the maximum to the last page", async () => {
      const el = await setUpPagedTable();
      await submitPage(el, "99");
      expect(ApiService.getData).toHaveBeenLastCalledWith("https://api.example.com/table-data?page=5&page_size=50");
      expect(pageInput(el).value).toBe("5");
      document.body.removeChild(el);
    });

    it("should clamp a page below the minimum to the first page", async () => {
      const el = await setUpPagedTable();
      await submitPage(el, "3");
      await submitPage(el, "-4");
      expect(ApiService.getData).toHaveBeenLastCalledWith("https://api.example.com/table-data?page=1&page_size=50");
      expect(pageInput(el).value).toBe("1");
      document.body.removeChild(el);
    });

    it("should not refetch and should restore the value when input is empty or the current page", async () => {
      const el = await setUpPagedTable();
      const spy = vi.mocked(ApiService.getData);
      const callsBefore = spy.mock.calls.length;

      await submitPage(el, "");
      expect(pageInput(el).value).toBe("1");
      await submitPage(el, "1");
      expect(spy.mock.calls.length).toBe(callsBefore);
      document.body.removeChild(el);
    });
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

    it("should render filter controls from server metadata (snake_case, null options for a text filter)", async () => {
      vi.spyOn(ApiService, "getData").mockResolvedValue({
        success: true,
        data: {
          columns: [
            { accessor: "clinic__clinic_name", label: "Clinic", data_type: "string", filter: { kind: "text", options: null } },
            {
              accessor: "status",
              label: "Status",
              data_type: "string",
              filter: { kind: "multi-select", options: [{ value: "signed", label: "Signed" }, { value: "revoked", label: "Revoked" }] },
            },
            { accessor: "consent_signed_date", label: "Signed", data_type: "datetime", filter: { kind: "date-range", options: null } },
          ],
          rows: [{ clinic__clinic_name: "A", status: "signed", consent_signed_date: "2026-01-01T08:00:00+00:00" }],
          pagination: { page: 1, page_size: 50, total_items: 1, total_pages: 1, has_next: false, has_previous: false },
        },
        message: "ok",
      });
      const el = new DataTable();
      el.dataUrl = "https://api.example.com/table-data";
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;

      expect(filterControl(el, "clinic__clinic_name").tagName).toBe("INPUT");
      const options = Array.from((filterControl(el, "status") as HTMLSelectElement).options).map((o) => o.textContent);
      expect(options).toEqual(["Signed", "Revoked"]);

      // and a filter typed on the double-underscore accessor is sent back as `<accessor>__icontains`, on page one
      const input = filterControl(el, "clinic__clinic_name") as HTMLInputElement;
      input.value = "alp";
      input.dispatchEvent(new Event("input"));
      await new Promise((r) => setTimeout(r, 400));
      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&clinic__clinic_name__icontains=alp"
      );
      document.body.removeChild(el);
    });

    it("should render a text input for a text-exact filter and send the bare column key", async () => {
      vi.spyOn(ApiService, "getData").mockResolvedValue({
        success: true,
        data: {
          columns: [
            {
              accessor: "study_participant__name",
              label: "Name",
              data_type: "string",
              sortable: false,
              filter: { kind: "text-exact", options: null },
            },
          ],
          rows: [{ study_participant__name: "Person A" }],
          pagination: { page: 1, page_size: 50, total_items: 1, total_pages: 1, has_next: false, has_previous: false },
        },
        message: "ok",
      });
      const el = new DataTable();
      el.dataUrl = "https://api.example.com/table-data";
      document.body.appendChild(el);
      await new Promise((r) => setTimeout(r, 10));
      await el.updateComplete;

      const input = filterControl(el, "study_participant__name") as HTMLInputElement;
      expect(input.tagName).toBe("INPUT");
      input.value = "Person A";
      input.dispatchEvent(new Event("input"));
      await new Promise((r) => setTimeout(r, 400));

      expect(ApiService.getData).toHaveBeenLastCalledWith(
        "https://api.example.com/table-data?page=1&page_size=50&study_participant__name=Person%20A"
      );
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

    describe("default sort seeding", () => {
      const pagination = { page: 1, page_size: 50, total_items: 60, total_pages: 2, has_next: true, has_previous: false };
      const columnsWithDefaults = [
        { accessor: "machineName", label: "Machine", sortable: true, default_sort: "asc", default_sort_order: 2 },
        { accessor: "numExams", label: "Exams", sortable: true, default_sort: "desc", default_sort_order: 1 },
        { accessor: "hospital", label: "Hospital", sortable: true },
      ];

      async function loadThenGoToNextPage(columns: Record<string, unknown>[], initialSort?: SortDescriptor[]) {
        vi.spyOn(ApiService, "getData")
          .mockResolvedValueOnce({
            success: true,
            data: { columns, rows: [{ machineName: "CT1" }], pagination },
            message: "ok",
          })
          .mockResolvedValueOnce({
            success: true,
            data: { columns: null, rows: [{ machineName: "CT2" }], pagination: { ...pagination, page: 2 } },
            message: "ok",
          });
        const el = new DataTable();
        el.dataUrl = "https://api.example.com/table-data";
        if (initialSort) el.initialSort = initialSort;
        document.body.appendChild(el);
        await new Promise((r) => setTimeout(r, 10));
        await el.updateComplete;
        (el.shadowRoot?.querySelector('[data-action="next"]') as HTMLButtonElement).click();
        await new Promise((r) => setTimeout(r, 10));
        await el.updateComplete;
        document.body.removeChild(el);
      }

      it("should seed the sort from the columns' default sort and order when no initialSort is given", async () => {
        await loadThenGoToNextPage(columnsWithDefaults);

        expect(ApiService.getData).toHaveBeenLastCalledWith(
          "https://api.example.com/table-data?page=2&page_size=50&sort=-numExams,machineName"
        );
      });

      it("should prefer initialSort over the columns' defaults", async () => {
        await loadThenGoToNextPage(columnsWithDefaults, [{ column: "hospital", direction: "asc" }]);

        expect(ApiService.getData).toHaveBeenLastCalledWith(
          "https://api.example.com/table-data?page=2&page_size=50&sort=hospital"
        );
      });

      it("should not send a sort param when no column declares a default", async () => {
        await loadThenGoToNextPage([{ accessor: "machineName", label: "Machine", sortable: true }]);

        expect(ApiService.getData).toHaveBeenLastCalledWith("https://api.example.com/table-data?page=2&page_size=50");
      });
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
