// Define a generic response type (adjust based on your actual backend)
export interface ApiResponse<T = any> {
  success: boolean;
  data?: T;
  message?: string;
}

export class ApiService {
  static async getData<T = unknown>(url: string): Promise<ApiResponse<T>> {
    return this.getJson<T>(url, "Data fetched successfully", "Error fetching data");
  }

  private static async getJson<T>(url: string, successMessage: string, errorLogMessage: string): Promise<ApiResponse<T>> {
    const headers: HeadersInit = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };

    try {
      const response = await fetch(url, {
        method: "GET",
        headers: headers,
        credentials: "include",
      });

      if (!response.ok) {
        if (response.status === 401) {
          throw new Error("Your session has ended. Please login again");
        }

        const errorBody = await response.text();
        throw new Error(`API Error (${response.status}): ${response.statusText} - ${errorBody}`);
      }

      const responseData = await response.json();

      return {
        success: true,
        data: responseData,
        message: successMessage,
      };
    } catch (error) {
      console.error(errorLogMessage, error);

      throw error;
    }
  }
}
