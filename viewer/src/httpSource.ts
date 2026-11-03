/** The local app's DataSource: the Express API, proxied by Vite at /api. */
import { SaveRefused, type DataSource, type SaveRequest, type SaveResult, type Snapshot } from "../shared/api";

async function errorFrom(res: Response): Promise<SaveRefused> {
  try {
    const body = (await res.json()) as { error?: string; problems?: string[] };
    return new SaveRefused(body.error ?? `HTTP ${res.status}`, body.problems ?? []);
  } catch {
    return new SaveRefused(`HTTP ${res.status} ${res.statusText}`, []);
  }
}

export const httpSource: DataSource = {
  async load(): Promise<Snapshot> {
    const res = await fetch("/api/snapshot");
    if (!res.ok) throw await errorFrom(res);
    return (await res.json()) as Snapshot;
  },
  async save(request: SaveRequest): Promise<SaveResult> {
    const res = await fetch("/api/save", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!res.ok) throw await errorFrom(res);
    return (await res.json()) as SaveResult;
  },
};
