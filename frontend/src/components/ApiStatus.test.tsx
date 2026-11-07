import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiStatus } from "./ApiStatus";

afterEach(() => vi.unstubAllGlobals());

describe("ApiStatus", () => {
  it("shows online when the health endpoint returns ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok" }), { status: 200 })),
    );
    render(<ApiStatus />);
    expect(await screen.findByText("API online")).toBeInTheDocument();
  });

  it("shows offline when the request fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));
    render(<ApiStatus />);
    expect(await screen.findByText("API offline")).toBeInTheDocument();
  });

  it("shows offline on a server error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));
    render(<ApiStatus />);
    expect(await screen.findByText("API offline")).toBeInTheDocument();
  });
});
