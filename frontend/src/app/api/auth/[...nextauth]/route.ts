import { handlers } from "@/lib/auth";
import { ensureAuthSchema } from "@/lib/ensureAuthSchema";

export const runtime = "nodejs";

export async function GET(req: Request, ctx: unknown) {
  await ensureAuthSchema();
  // @ts-expect-error next-auth handler signature
  return handlers.GET(req, ctx);
}

export async function POST(req: Request, ctx: unknown) {
  await ensureAuthSchema();
  // @ts-expect-error next-auth handler signature
  return handlers.POST(req, ctx);
}
