import { describe, expect, it } from "vitest";

import { parseInvitationHash } from "./invitation-link";

describe("parseInvitationHash", () => {
  it("reads organization and token after the #", () => {
    expect(parseInvitationHash("#organization=abc&token=x-Y_z")).toEqual({
      organizationId: "abc",
      token: "x-Y_z",
    });
  });

  it("rejects incomplete links", () => {
    expect(parseInvitationHash("")).toBeNull();
    expect(parseInvitationHash("#organization=abc")).toBeNull();
  });
});
