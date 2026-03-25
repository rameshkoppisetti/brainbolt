import type {
  LeaderboardResponse,
  MetricsResponse,
  NextQuestionResponse,
  SubmitAnswerRequest,
  SubmitAnswerResponse,
} from "./types";

export const API_BASE = (import.meta as any).env?.VITE_API_BASE ?? "http://localhost:8080";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${text ? `: ${text}` : ""}`);
  }
  return (await res.json()) as T;
}

export function getNext(userId: string, sessionId: string): Promise<NextQuestionResponse> {
  const qs = new URLSearchParams({ userId, sessionId });
  return jsonFetch<NextQuestionResponse>(`/v1/quiz/next?${qs.toString()}`);
}

export function submitAnswer(body: SubmitAnswerRequest): Promise<SubmitAnswerResponse> {
  return jsonFetch<SubmitAnswerResponse>(`/v1/quiz/answer`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getMetrics(userId: string): Promise<MetricsResponse> {
  const qs = new URLSearchParams({ userId });
  return jsonFetch<MetricsResponse>(`/v1/quiz/metrics?${qs.toString()}`);
}

export function getLeaderboardScore(userId: string, n = 10): Promise<LeaderboardResponse> {
  const qs = new URLSearchParams({ userId, n: String(n) });
  return jsonFetch<LeaderboardResponse>(`/v1/leaderboard/score?${qs.toString()}`);
}

export function getLeaderboardStreak(userId: string, n = 10): Promise<LeaderboardResponse> {
  const qs = new URLSearchParams({ userId, n: String(n) });
  return jsonFetch<LeaderboardResponse>(`/v1/leaderboard/streak?${qs.toString()}`);
}

