"""
Mock LLM client with an interface mirroring a real LLM API client.

Only this module needs to change to plug in a real provider
(e.g. OpenAI/Anthropic): classify_batch() and generate_draft().

Degradation simulation flags:
  LLMClient.available -> False triggers circuit-breaker (ConnectionError)
  LLMClient.slow       -> True simulates a timeout (TimeoutError)

Batching: classify_batch() accepts a list of texts and returns a list of
results, one LLM 'call' per batch instead of per ticket -- this is the
micro-batching idea used to control cost/latency under load (see
docs/architecture.md, degradation levels L0-L4).
"""
import time

MOCK_DRAFTS = {
    "account_access": "Здравствуйте! Для восстановления доступа воспользуйтесь сбросом пароля на странице входа. Если письмо не приходит, проверьте папку Спам.",
    "billing": "Здравствуйте! Мы рассмотрим ваше обращение по оплате и вернёмся с ответом в течение 3-5 рабочих дней.",
    "technical_issue": "Здравствуйте! Попробуйте обновить приложение и очистить кеш. Если ошибка повторится, напишите нам версию ОС и приложения.",
    "general_question": "Здравствуйте! Спасибо за ваш вопрос. {context}",
    "complaint": None,
    "abuse": None,
}


class LLMClient:
    """Singleton-style mock client. Toggle flags to simulate degradation."""

    available = True
    slow = False
    latency_sec = 0.05

    @classmethod
    def _check_health(cls):
        if not cls.available:
            raise ConnectionError("LLM API unavailable (circuit breaker open)")
        if cls.slow:
            raise TimeoutError("LLM API timeout (SLA exceeded)")

    @classmethod
    def classify_batch(cls, texts: list[str]) -> list[dict]:
        """
        Batched classification call. In a real client this would be a
        single API request containing all `texts`, reducing per-ticket
        cost/latency under load (see degradation level L1).
        """
        cls._check_health()
        time.sleep(cls.latency_sec)  # one call regardless of batch size
        results = []
        for t in texts:
            results.append({"mock": True, "note": "batched classification stub"})
        return results

    @classmethod
    def generate_draft(cls, ticket_text: str, context_snippet: str, topic: str) -> str:
        """Generate a draft reply. Raises on simulated degradation."""
        cls._check_health()
        time.sleep(cls.latency_sec)
        template = MOCK_DRAFTS.get(topic)
        if template is None:
            # risky topics never get an LLM draft - handled in pipeline.py
            return None
        return template.format(context=context_snippet)


def retrieval_only_draft(context_snippet: str) -> str:
    """
    Fallback draft generation without LLM (degradation L2/L3, or high_pii).
    Purely template-based using the retrieved KB/context snippet.
    """
    return (
        f"[автоматически подобранный черновик, требует проверки оператором] "
        f"Возможно, вам подойдёт: {context_snippet}"
    )
