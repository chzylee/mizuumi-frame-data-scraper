/** The local app's DataSource: the Express API, proxied by Vite at /api. */
import { SaveRefused, type DataSource, type SaveRequest, type SaveResult, type Snapshot } from "../shared/api";

const NOT_RUNNING =
  "Can't reach the viewer's local server. Is `npm start` still running in viewer/? Start it again, " +
  "then retry. Nothing was written.";

async function errorFrom(res: Response): Promise<SaveRefused> {
  // Vite answers for the API with a 5xx gateway error when the Express half has stopped.
  if (res.status === 502 || res.status === 503 || res.status === 504) return new SaveRefused(NOT_RUNNING, []);
  try {
    const body = (await res.json()) as { error?: string; problems?: string[] };
    return new SaveRefused(body.error ?? `HTTP ${res.status}`, body.problems ?? []);
  } catch {
    return new SaveRefused(`HTTP ${res.status} ${res.statusText}`, []);
  }
}

/** fetch, with "the local server is gone" reported plainly instead of the browser's NetworkError. */
async function call(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch {
    throw new SaveRefused(NOT_RUNNING, []);
  }
}

export const httpSource: DataSource = {
  async load(): Promise<Snapshot> {
    const res = await call("/api/snapshot");
    if (!res.ok) throw await errorFrom(res);
    return (await res.json()) as Snapshot;
  },
  async save(request: SaveRequest): Promise<SaveResult> {
    const res = await call("/api/save", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!res.ok) throw await errorFrom(res);
    return (await res.json()) as SaveResult;
  },
};
