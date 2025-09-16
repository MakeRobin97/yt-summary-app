import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000'),
  title: {
    default: '유튜브 요약 프로그램 - 자막 기반 자동 요약',
    template: '%s | 유튜브 요약 프로그램',
  },
  description: '유튜브 링크만 붙여넣으면 요약을 자동으로 생성해줍니다.',
  keywords: [
    '유튜브 요약',
    '유튜브 자막',
    '유튜브 요약프로그램',
    'youtube summary',
    'youtube transcript',
  ],
  alternates: {
    canonical: '/',
  },
  openGraph: {
    type: 'website',
    locale: 'ko_KR',
    url: '/',
    siteName: '유튜브 요약 프로그램',
    title: '유튜브 요약 프로그램 - 자막 기반 자동 요약',
    description:
      '유튜브 링크만 붙여넣으면 자막을 분석해 핵심 요약을 제공합니다. 유튜브 요약, 유튜브 자막 요약 프로그램.',
  },
  twitter: {
    card: 'summary_large_image',
    title: '유튜브 요약 프로그램 - 자막 기반 자동 요약',
    description:
      '유튜브 링크만 붙여넣으면 자막을 분석해 핵심 요약을 제공합니다. 유튜브 요약, 유튜브 자막 요약 프로그램.',
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        {children}
      </body>
    </html>
  );
}
