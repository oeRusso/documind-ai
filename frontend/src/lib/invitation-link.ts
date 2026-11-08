/** The invitation link: /invitations/accept#organization=<id>&token=<token>. */

export type InvitationLink = { organizationId: string; token: string };

export function parseInvitationHash(hash: string): InvitationLink | null {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const organizationId = params.get("organization");
  const token = params.get("token");
  if (!organizationId || !token) return null;
  return { organizationId, token };
}
