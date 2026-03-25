from __future__ import annotations


class NoQuestionsError(Exception):
    pass


class NoEligibleQuestionsError(Exception):
    """No never-attempted questions remain for this user (all answered at least once)."""

    pass


class StateVersionConflict(Exception):
    pass


class NotCurrentQuestion(Exception):
    pass


class QuestionNotFound(Exception):
    pass


class UserNotFound(Exception):
    pass


class QuestionAlreadyMastered(Exception):
    """User already has an answer_log row for this question; no re-scoring or re-answering."""

    pass

