import { NextResponse } from "next/server";

import { auth } from "@/lib/auth";
import { ensureAuthSchema } from "@/lib/ensureAuthSchema";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";

export async function POST(req: Request) {
  await ensureAuthSchema();
  const session = await auth();
  const userId = session?.user?.id;
  if (!userId) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  const body = (await req.json().catch(() => ({}))) as { anonymousId?: string };
  const anonymousId = String(body.anonymousId || "").trim();
  if (!anonymousId) {
    return NextResponse.json({ ok: false, error: "anonymousId is required" }, { status: 400 });
  }

  await prisma.anonymousIdentityLink.upsert({
    where: {
      anonymousId_userId: {
        anonymousId,
        userId,
      },
    },
    update: {},
    create: {
      anonymousId,
      userId,
    },
  });

  return NextResponse.json({ ok: true });
}
