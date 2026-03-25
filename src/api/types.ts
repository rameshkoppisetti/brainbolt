export type NextQuestionResponse = {
  questionId: string;
  /** Question row tier (scoring); can differ from the user's adaptive band. */
  difficulty: number;
  /** Adaptive level from server state (target band); matches metrics.currentDifficulty after refresh. */
  userDifficulty: number;
  prompt: string;
  choices: string[];
  sessionId: string;
  stateVersion: number;
  currentScore: number;
  currentStreak: number;
};

export type SubmitAnswerRequest = {
  userId: string;
  sessionId: string;
  questionId: string;
  answer: string;
  stateVersion: number;
  answerIdempotencyKey: string;
};

export type SubmitAnswerResponse = {
  correct: boolean;
  newDifficulty: number;
  newStreak: number;
  scoreDelta: number;
  totalScore: number;
  stateVersion: number;
  leaderboardRankScore: number | null;
  leaderboardRankStreak: number | null;
};

export type LeaderboardEntry = { userId: string; score: number };
export type LeaderboardResponse = {
  top: LeaderboardEntry[];
  yourRank: number | null;
  yourScore: number | null;
};

export type MetricsResponse = {
  currentDifficulty: number;
  streak: number;
  maxStreak: number;
  totalScore: number;
  accuracy: number;
  difficultyHistogram: Record<string, number>;
  recentPerformance: boolean[];
};

export type LeaderboardUpdateEvent = {
  type: "leaderboard_update";
  changedUser: {
    userId: string;
    totalScore: number;
    streak: number;
    currentDifficulty: number;
    rankScore: number | null;
    rankStreak: number | null;
  };
  topScore: LeaderboardEntry[];
  topStreak: LeaderboardEntry[];
};

