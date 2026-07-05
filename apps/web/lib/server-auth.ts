/** Server-side token resolution for the API proxy.
 *
 * With Clerk configured (CLERK_SECRET_KEY set) the signed-in user's session
 * JWT is forwarded — the FastAPI side verifies it against Clerk's JWKS and
 * scopes by its firm_id claim. Without Clerk (local dev) a tmk_dev_<firm>
 * token is used, matching the API's non-production dev-auth path.
 */

const DEV_FIRM = process.env.TRAILMARK_DEV_FIRM ?? "firm_demo";

export function clerkConfigured(): boolean {
  return Boolean(process.env.CLERK_SECRET_KEY);
}

export async function getApiToken(): Promise<string | null> {
  if (clerkConfigured()) {
    const { auth } = await import("@clerk/nextjs/server");
    const { getToken } = auth();
    return getToken();
  }
  return `tmk_dev_${DEV_FIRM}`;
}
