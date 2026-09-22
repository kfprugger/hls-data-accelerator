//-----------------------------------------------------------------------
// Typed Rayfin data/auth client for the app database.
//-----------------------------------------------------------------------

import RayfinClient from "@microsoft/rayfin-client";

import type { AppSchema } from "../../rayfin/data/schema";

/** The app's Rayfin client, typed against the entities in rayfin/data. */
export type AppRayfinClient = RayfinClient<AppSchema>;

let _client: AppRayfinClient | undefined;

/**
 * Returns the singleton RayfinClient bound to AppSchema.
 *
 * `rayfin env` projects rayfin/.env into VITE_RAYFIN_API_URL; the older
 * VITE_RAYFIN_BASE_URL name is still accepted so a hand-written .env.local
 * keeps working. Throws when neither is present — callers surface that as a
 * user-visible error rather than crashing during render.
 */
export function getRayfinClient(): AppRayfinClient {
    if (_client) return _client;

    const baseUrl = import.meta.env.VITE_RAYFIN_API_URL ?? import.meta.env.VITE_RAYFIN_BASE_URL;
    const publishableKey = import.meta.env.VITE_RAYFIN_PUBLISHABLE_KEY;

    if (!baseUrl || !publishableKey) {
        throw new Error(
            "RayfinClient requires VITE_RAYFIN_API_URL (or VITE_RAYFIN_BASE_URL) and VITE_RAYFIN_PUBLISHABLE_KEY to be set.",
        );
    }

    _client = new RayfinClient<AppSchema>({
        baseUrl,
        publishableKey,
        authStorage: true,
    });

    return _client;
}
