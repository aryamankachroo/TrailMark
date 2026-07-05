/** Thin proxy: /api/v1/* → FastAPI /v1/*.
 * Business logic lives exclusively in apps/api; this layer only attaches the
 * firm-scoped bearer token and forwards the original client IP (attestations
 * record it as part of the FINRA 3110 evidence trail). */

import { NextRequest, NextResponse } from "next/server";

import { getApiToken } from "@/lib/server-auth";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

async function proxy(
  req: NextRequest,
  { params }: { params: { path: string[] } },
): Promise<NextResponse> {
  const token = await getApiToken();
  if (!token) {
    return NextResponse.json(
      { error: { code: "unauthenticated", message: "Sign in required." } },
      { status: 401 },
    );
  }

  const url = `${API_URL}/${params.path.join("/")}${req.nextUrl.search}`;
  const headers: Record<string, string> = {
    authorization: `Bearer ${token}`,
    "x-forwarded-for":
      req.headers.get("x-forwarded-for") ?? req.ip ?? "127.0.0.1",
  };
  const contentType = req.headers.get("content-type");
  if (contentType) headers["content-type"] = contentType;
  const userAgent = req.headers.get("user-agent");
  if (userAgent) headers["user-agent"] = userAgent;

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const resp = await fetch(url, {
    method: req.method,
    headers,
    body: hasBody ? await req.text() : undefined,
    cache: "no-store",
  });

  return new NextResponse(resp.body, {
    status: resp.status,
    headers: {
      "content-type": resp.headers.get("content-type") ?? "application/json",
    },
  });
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
};
