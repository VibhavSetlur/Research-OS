"""Token budget tracker for Research Copilot.

Tracks cumulative token usage across all LLM calls and fires an emergency
synthesis hook when the budget approaches exhaustion (90 % threshold).
"""

import logging

logger = logging.getLogger("research.token_budget")

_WARNING_THRESHOLD = 0.80  # fire HITL compress warning at 80 %
_EMERGENCY_THRESHOLD = 0.90  # fire force_synthesize at 90 %


class TokenBudgetTracker:
    """Tracks token usage and triggers emergency synthesis when budget is near exhaustion."""

    def __init__(self, max_tokens: int = 200_000):
        self.max_tokens = max_tokens
        self.used_tokens = 0
        self._warned = False
        self.limit_reached = False

    def add_usage(self, prompt_tokens: int, completion_tokens: int) -> None:
        total = prompt_tokens + completion_tokens
        self.used_tokens += total
        ratio = self.used_tokens / self.max_tokens

        if ratio >= _WARNING_THRESHOLD and not self._warned:
            self._warned = True
            logger.warning(
                "Token budget at %.0f%%. Consider running `rcp compress` to free context.",
                ratio * 100,
            )

        if ratio >= _EMERGENCY_THRESHOLD and not self.limit_reached:
            self.limit_reached = True
            logger.warning(
                "Token budget reached 90%%. Triggering force_synthesize interceptor."
            )
            self._trigger_force_synthesize()

    def _trigger_force_synthesize(self) -> None:
        from research_copilot.core.hooks import hook_engine

        hook_engine.trigger_sync("emergency_synthesize", {"status": "budget_exhausted"})

    def get_remaining(self) -> int:
        return max(0, self.max_tokens - self.used_tokens)

    def usage_ratio(self) -> float:
        return self.used_tokens / self.max_tokens if self.max_tokens else 0.0
