import { API_BASE_URL, ApiError } from "./client";

export interface AskEntity {
  kind: string;
  id: string;
  name: string;
}

export interface AskAnswer {
  contract_version: string;
  intent: string;
  entities: AskEntity[];
  season: number | null;
  requested_metric: string | null;
  status: string;
  data_version: string;
  model_version: string | null;
  metrics: Record<string, unknown>[];
  uncertainty: Record<string, unknown>[];
  limitations: string[];
  source_artifacts: {
    artifact: string;
    data_version: string;
    sha256: string;
  }[];
  candidates: AskEntity[];
  reason: string | null;
  available_alternative: string | null;
  explanation: string;
}

export async function askQuestion(question: string): Promise<AskAnswer> {
  const response = await fetch(`${API_BASE_URL}/ask`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      detail?: unknown;
    };
    throw new ApiError(
      typeof body.detail === "string"
        ? body.detail
        : `Request failed (${response.status})`,
      response.status,
    );
  }
  return response.json() as Promise<AskAnswer>;
}
