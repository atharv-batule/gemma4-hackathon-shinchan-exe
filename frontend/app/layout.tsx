import type { Metadata } from "next";
import "./styles.css";
export const metadata: Metadata = { title: "DrugDiscover AI", description: "Evidence-grounded drug repurposing research" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
