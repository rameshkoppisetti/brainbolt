import { io, type Socket } from "socket.io-client";
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE,
  getLeaderboardScore,
  getLeaderboardStreak,
  getMetrics,
  getNext,
  submitAnswer,
} from "../api/client";
import type {
  LeaderboardEntry,
  LeaderboardUpdateEvent,
  MetricsResponse,
  NextQuestionResponse,
  SubmitAnswerResponse,
} from "../api/types";

function newIdemKey(): string {
  return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function App() {
  const [userId, setUserId] = useState("u-alice");
  const sessionId = "single";

  const [question, setQuestion] = useState<NextQuestionResponse | null>(null);
  const [lastAnswer, setLastAnswer] = useState<SubmitAnswerResponse | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [topScore, setTopScore] = useState<LeaderboardEntry[]>([]);
  const [topStreak, setTopStreak] = useState<LeaderboardEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const socketRef = useRef<Socket | null>(null);
  /** Prevents double-submit before React re-renders `busy` (same-tick double clicks). */
  const answerInFlightRef = useRef(false);

  const apiBase = useMemo(() => API_BASE, []);

  async function refreshAll() {
    setErr(null);
    setBusy(true);
    try {
      // /next may bump current_difficulty (streak/availability) after the last answer snapshot;
      // run it before /metrics so the metrics read matches the card tier.
      const q = await getNext(userId, sessionId);
      const [m, ls, lt] = await Promise.all([
        getMetrics(userId),
        getLeaderboardScore(userId, 10),
        getLeaderboardStreak(userId, 10),
      ]);
      setQuestion(q);
      setMetrics(m);
      setTopScore(ls.top);
      setTopStreak(lt.top);
      setLastAnswer(null);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onAnswer(choice: string) {
    if (!question || answerInFlightRef.current) return;
    answerInFlightRef.current = true;
    setErr(null);
    setBusy(true);
    const snapshot = question;
    try {
      const res = await submitAnswer({
        userId,
        sessionId,
        questionId: snapshot.questionId,
        answer: choice,
        stateVersion: snapshot.stateVersion,
        answerIdempotencyKey: newIdemKey(),
      });
      setLastAnswer(res);
      const q2 = await getNext(userId, sessionId);
      setQuestion(q2);
      setMetrics(await getMetrics(userId));
    } catch (e: any) {
      const msg = e?.message ?? String(e);
      // Often a duplicate request after a successful first submit; resync from server.
      if (msg.includes("409") && msg.includes("state_version_conflict")) {
        try {
          const q2 = await getNext(userId, sessionId);
          setQuestion(q2);
          setMetrics(await getMetrics(userId));
          setErr(null);
        } catch (e2: any) {
          setErr(e2?.message ?? String(e2));
        }
      } else {
        setErr(msg);
      }
    } finally {
      answerInFlightRef.current = false;
      setBusy(false);
    }
  }

  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  useEffect(() => {
    const s = io(apiBase, { transports: ["websocket"] });
    socketRef.current = s;
    const onConnect = () => setConnected(true);
    const onDisconnect = () => setConnected(false);
    const onUpdate = (evt: LeaderboardUpdateEvent) => {
      if (!evt || evt.type !== "leaderboard_update") return;
      setTopScore(evt.topScore);
      setTopStreak(evt.topStreak);
      // If this user is the changed user, also update metrics-ish display.
      if (evt.changedUser.userId === userId) {
        setMetrics((prev) =>
          prev
            ? {
                ...prev,
                totalScore: evt.changedUser.totalScore,
                streak: evt.changedUser.streak,
                currentDifficulty: evt.changedUser.currentDifficulty,
              }
            : prev
        );
      }
    };
    s.on("connect", onConnect);
    s.on("disconnect", onDisconnect);
    s.on("leaderboard:update", onUpdate);
    return () => {
      s.off("connect", onConnect);
      s.off("disconnect", onDisconnect);
      s.off("leaderboard:update", onUpdate);
      s.disconnect();
    };
  }, [apiBase, userId]);

  return (
    <div className="page">
      <header className="header">
        <div>
          <div className="title">BrainBolt</div>
          <div className="sub">
            API: <code>{apiBase}</code> · Socket:{" "}
            <span className={connected ? "ok" : "bad"}>{connected ? "connected" : "disconnected"}</span>
          </div>
        </div>
        <div className="userBox">
          <label className="label">
            userId
            <input
              className="input"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="u-alice"
            />
          </label>
          <button className="btn" onClick={refreshAll} disabled={busy || !userId}>
            Refresh
          </button>
        </div>
      </header>

      {err ? (
        <div className="card error">
          <div className="cardTitle">Error</div>
          <pre className="pre">{err}</pre>
        </div>
      ) : null}

      <div className="grid">
        <section className="card">
          <div className="cardTitle">Question</div>
          {question ? (
            <>
              <div className="meta">
                <span>
                  your level <b>{question.userDifficulty}</b>
                </span>
                <span>
                  card <b>{question.difficulty}</b>
                </span>
                <span>
                  stateVersion <b>{question.stateVersion}</b>
                </span>
                <span>
                  streak <b>{question.currentStreak}</b>
                </span>
                <span>
                  score <b>{question.currentScore}</b>
                </span>
              </div>
              <div className="prompt">{question.prompt}</div>
              <div className="choices">
                {question.choices.map((c) => (
                  <button key={c} className="choice" onClick={() => onAnswer(c)} disabled={busy}>
                    {c}
                  </button>
                ))}
              </div>
              {lastAnswer ? (
                <div className={`toast ${lastAnswer.correct ? "good" : "bad"}`}>
                  {lastAnswer.correct ? "Correct" : "Wrong"} · Δ {lastAnswer.scoreDelta} · level{" "}
                  {lastAnswer.newDifficulty} · total {lastAnswer.totalScore} · rank(score){" "}
                  {lastAnswer.leaderboardRankScore ?? "—"} · rank(streak) {lastAnswer.leaderboardRankStreak ?? "—"}
                </div>
              ) : null}
            </>
          ) : (
            <div className="muted">Loading…</div>
          )}
        </section>

        <section className="card">
          <div className="cardTitle">Your metrics</div>
          {metrics ? (
            <div className="kv">
              <div>
                <div className="k">your level</div>
                <div className="v">{metrics.currentDifficulty}</div>
              </div>
              <div>
                <div className="k">total score</div>
                <div className="v">{metrics.totalScore}</div>
              </div>
              <div>
                <div className="k">streak</div>
                <div className="v">{metrics.streak}</div>
              </div>
              <div>
                <div className="k">max streak</div>
                <div className="v">{metrics.maxStreak}</div>
              </div>
              <div>
                <div className="k">accuracy</div>
                <div className="v">{(metrics.accuracy * 100).toFixed(0)}%</div>
              </div>
            </div>
          ) : (
            <div className="muted">Loading…</div>
          )}
        </section>

        <section className="card">
          <div className="cardTitle">Leaderboard · Score</div>
          <ol className="list">
            {topScore.map((e) => (
              <li key={e.userId} className={e.userId === userId ? "me" : ""}>
                <span className="who">{e.userId}</span>
                <span className="num">{e.score}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="card">
          <div className="cardTitle">Leaderboard · Streak</div>
          <ol className="list">
            {topStreak.map((e) => (
              <li key={e.userId} className={e.userId === userId ? "me" : ""}>
                <span className="who">{e.userId}</span>
                <span className="num">{e.score}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <footer className="footer">
        <span className="muted">
          Tip: open two browser windows with different <code>userId</code>s to see realtime updates.
        </span>
      </footer>
    </div>
  );
}

