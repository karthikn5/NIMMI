import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** Class joiner for the marketing site (server components can't use the client-only one in ui.tsx). */
export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
