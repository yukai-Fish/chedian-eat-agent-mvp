import NextAuth from "next-auth";
import EmailProvider from "next-auth/providers/nodemailer";
import { PrismaAdapter } from "@auth/prisma-adapter";

import { prisma } from "@/lib/prisma";

const from = process.env.AUTH_EMAIL_FROM || "noreply@chedian.local";
const smtpServer = process.env.AUTH_EMAIL_SERVER;

const provider = EmailProvider({
  server: smtpServer || "smtp://127.0.0.1:2525",
  from,
  async sendVerificationRequest(params) {
    const { identifier, url, provider } = params;
    try {
      if (!smtpServer) {
        // eslint-disable-next-line no-console
        console.info(`[AUTH_DEV_MAGIC_LINK] email=${identifier} url=${url}`);
        return;
      }

      const nodemailer = await import("nodemailer");
      const transport = nodemailer.createTransport(provider.server);
      await transport.sendMail({
        to: identifier,
        from: provider.from,
        subject: "成电吃什么 登录链接",
        text: `点击登录：${url}`,
        html: `<p>点击下方链接登录成电吃什么：</p><p><a href="${url}">${url}</a></p>`,
      });
    } catch (error) {
      // Dev-safe fallback: do not break sign-in if local SMTP is unavailable.
      // eslint-disable-next-line no-console
      console.warn("[AUTH_EMAIL_FALLBACK]", error);
      // eslint-disable-next-line no-console
      console.info(`[AUTH_DEV_MAGIC_LINK] email=${identifier} url=${url}`);
    }
  },
});

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: PrismaAdapter(prisma),
  session: {
    strategy: "database",
  },
  providers: [provider],
  pages: {
    verifyRequest: "/?auth=verify",
  },
  callbacks: {
    async session({ session, user }) {
      if (session.user) {
        session.user.id = user.id;
      }
      return session;
    },
  },
});
