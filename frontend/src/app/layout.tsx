import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'VisuSync AI — Edit with intent', description: 'AI-assisted video editing studio' };
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en"><body>{children}</body></html>; }
