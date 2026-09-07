import { beforeEach, describe, expect, it } from "vitest";
import { GATEWAY_STATUSES, useConnectivity } from "./connectivity";

beforeEach(() => useConnectivity.setState({ browserOnline: true, serverDown: false, serverDownSince: null }));

describe("connectivity store", () => {
  it("marks the server down once, keeping the first sighting, and clears it on the next good answer", () => {
    const s = useConnectivity.getState();
    s.reportServerFailure();
    const since = useConnectivity.getState().serverDownSince;
    expect(useConnectivity.getState().serverDown).toBe(true);
    expect(since).not.toBeNull();
    s.reportServerFailure(); // a second failure does not move the clock
    expect(useConnectivity.getState().serverDownSince).toBe(since);
    s.reportServerOk();
    expect(useConnectivity.getState().serverDown).toBe(false);
    expect(useConnectivity.getState().serverDownSince).toBeNull();
  });

  it("tracks the browser's own network separately from the server", () => {
    useConnectivity.getState().setBrowserOnline(false);
    expect(useConnectivity.getState().browserOnline).toBe(false);
    expect(useConnectivity.getState().serverDown).toBe(false);
  });

  it("treats gateway answers as the server being down", () => {
    expect([502, 503, 504].every((c) => GATEWAY_STATUSES.has(c))).toBe(true);
    expect(GATEWAY_STATUSES.has(500)).toBe(false);
  });
});
