import { describe, it, expect, vi, beforeEach } from "vitest";

// We need to mock fetch before importing the module
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

import { api, ApiError } from "@/lib/api-client";

function jsonResponse(body: unknown, status = 200, statusText = "OK") {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText,
    json: () => Promise.resolve(body),
  };
}

function errorResponse(status: number, statusText: string, body: unknown = null) {
  return {
    ok: false,
    status,
    statusText,
    json: () => Promise.resolve(body),
  };
}

describe("ApiError", () => {
  it("has correct properties", () => {
    const err = new ApiError(404, "Not Found", { detail: "missing" });
    expect(err.status).toBe(404);
    expect(err.statusText).toBe("Not Found");
    expect(err.body).toEqual({ detail: "missing" });
    expect(err.name).toBe("ApiError");
    expect(err.message).toBe("API Error 404: Not Found");
  });

  it("is an instance of Error", () => {
    const err = new ApiError(500, "Internal Server Error", null);
    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(ApiError);
  });
});

describe("api.get", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns parsed JSON on successful GET", async () => {
    const data = { id: "123", name: "test" };
    mockFetch.mockResolvedValueOnce(jsonResponse(data));

    const result = await api.get("/sessions/123");

    expect(result).toEqual(data);
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/sessions/123",
      expect.objectContaining({
        method: "GET",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      })
    );
  });

  it("does not send a body for GET requests", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse([]));

    await api.get("/sessions");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ body: undefined })
    );
  });
});

describe("api.post", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sends JSON body on POST", async () => {
    const payload = { company_name: "Acme", industry: "SaaS" };
    const responseData = { id: "new-id", ...payload };
    mockFetch.mockResolvedValueOnce(jsonResponse(responseData, 201, "Created"));

    const result = await api.post("/sessions", payload);

    expect(result).toEqual(responseData);
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/sessions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify(payload),
      })
    );
  });

  it("sends POST without body when no payload given", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ status: "ok" }));

    await api.post("/sessions/123/rerun/eda");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        method: "POST",
        body: undefined,
      })
    );
  });
});

describe("api.patch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sends PATCH with body", async () => {
    const patch = { current_step: "eda" };
    mockFetch.mockResolvedValueOnce(jsonResponse({ id: "1", ...patch }));

    const result = await api.patch("/sessions/1", patch);

    expect(result).toEqual({ id: "1", current_step: "eda" });
    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/sessions/1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify(patch),
      })
    );
  });
});

describe("api.delete", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sends DELETE request", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse(null));

    await api.delete("/sessions/1");

    expect(mockFetch).toHaveBeenCalledWith(
      "http://localhost:8000/sessions/1",
      expect.objectContaining({ method: "DELETE" })
    );
  });
});

describe("error handling", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("throws ApiError on non-OK response", async () => {
    const errorBody = { detail: "Session not found" };
    mockFetch.mockResolvedValueOnce(errorResponse(404, "Not Found", errorBody));

    try {
      await api.get("/sessions/missing");
      expect.fail("Expected ApiError to be thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.statusText).toBe("Not Found");
      expect(apiErr.body).toEqual(errorBody);
    }
  });

  it("throws ApiError with null body when response JSON parsing fails", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("Invalid JSON")),
    });

    try {
      await api.get("/broken");
      expect.fail("Expected ApiError to be thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(500);
      expect(apiErr.body).toBeNull();
    }
  });

  it("returns undefined for 204 No Content response", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 204,
      statusText: "No Content",
      json: () => Promise.reject(new Error("No body")),
    });

    const result = await api.delete("/sessions/1");

    expect(result).toBeUndefined();
  });
});
