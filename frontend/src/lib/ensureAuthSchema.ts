import { prisma } from "@/lib/prisma";

let initialized = false;
let inflight: Promise<void> | null = null;

export async function ensureAuthSchema(): Promise<void> {
  if (initialized) return;
  if (inflight) return inflight;

  inflight = (async () => {
    await prisma.$executeRawUnsafe(`
      CREATE TABLE IF NOT EXISTS "User" (
        "id" TEXT NOT NULL PRIMARY KEY,
        "name" TEXT,
        "email" TEXT,
        "emailVerified" DATETIME,
        "image" TEXT,
        "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        "updatedAt" DATETIME NOT NULL
      )
    `);
    await prisma.$executeRawUnsafe(`CREATE UNIQUE INDEX IF NOT EXISTS "User_email_key" ON "User"("email")`);

    await prisma.$executeRawUnsafe(`
      CREATE TABLE IF NOT EXISTS "Account" (
        "userId" TEXT NOT NULL,
        "type" TEXT NOT NULL,
        "provider" TEXT NOT NULL,
        "providerAccountId" TEXT NOT NULL,
        "refresh_token" TEXT,
        "access_token" TEXT,
        "expires_at" INTEGER,
        "token_type" TEXT,
        "scope" TEXT,
        "id_token" TEXT,
        "session_state" TEXT,
        PRIMARY KEY ("provider","providerAccountId")
      )
    `);
    await prisma.$executeRawUnsafe(`CREATE INDEX IF NOT EXISTS "Account_userId_idx" ON "Account"("userId")`);

    await prisma.$executeRawUnsafe(`
      CREATE TABLE IF NOT EXISTS "Session" (
        "id" TEXT NOT NULL PRIMARY KEY,
        "sessionToken" TEXT NOT NULL,
        "userId" TEXT NOT NULL,
        "expires" DATETIME NOT NULL
      )
    `);
    await prisma.$executeRawUnsafe(`CREATE UNIQUE INDEX IF NOT EXISTS "Session_sessionToken_key" ON "Session"("sessionToken")`);
    await prisma.$executeRawUnsafe(`CREATE INDEX IF NOT EXISTS "Session_userId_idx" ON "Session"("userId")`);

    await prisma.$executeRawUnsafe(`
      CREATE TABLE IF NOT EXISTS "VerificationToken" (
        "identifier" TEXT NOT NULL,
        "token" TEXT NOT NULL,
        "expires" DATETIME NOT NULL,
        PRIMARY KEY ("identifier","token")
      )
    `);
    await prisma.$executeRawUnsafe(`CREATE UNIQUE INDEX IF NOT EXISTS "VerificationToken_token_key" ON "VerificationToken"("token")`);

    await prisma.$executeRawUnsafe(`
      CREATE TABLE IF NOT EXISTS "AnonymousIdentityLink" (
        "id" TEXT NOT NULL PRIMARY KEY,
        "anonymousId" TEXT NOT NULL,
        "userId" TEXT NOT NULL,
        "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        "updatedAt" DATETIME NOT NULL
      )
    `);
    await prisma.$executeRawUnsafe(`CREATE UNIQUE INDEX IF NOT EXISTS "AnonymousIdentityLink_anonymousId_userId_key" ON "AnonymousIdentityLink"("anonymousId","userId")`);
    await prisma.$executeRawUnsafe(`CREATE INDEX IF NOT EXISTS "AnonymousIdentityLink_anonymousId_idx" ON "AnonymousIdentityLink"("anonymousId")`);

    await prisma.$executeRawUnsafe(`
      CREATE TABLE IF NOT EXISTS "Favorite" (
        "id" TEXT NOT NULL PRIMARY KEY,
        "userId" TEXT NOT NULL,
        "shopId" TEXT NOT NULL,
        "shopName" TEXT,
        "anonymousId" TEXT,
        "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        "updatedAt" DATETIME NOT NULL
      )
    `);
    await prisma.$executeRawUnsafe(`CREATE UNIQUE INDEX IF NOT EXISTS "Favorite_userId_shopId_key" ON "Favorite"("userId","shopId")`);
    await prisma.$executeRawUnsafe(`CREATE INDEX IF NOT EXISTS "Favorite_userId_idx" ON "Favorite"("userId")`);

    initialized = true;
    inflight = null;
  })().catch((err) => {
    inflight = null;
    throw err;
  });

  return inflight;
}

