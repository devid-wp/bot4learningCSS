# Архитектура

## Слои

```
Telegram (long polling)
      │
 ┌────▼─────┐
 │ Handlers │  тонкие: принять апдейт → сервис → отрисовать
 └────┬─────┘
 ┌────▼──────┐
 │   FSM     │  маршрутизация диалога (эфемерная)
 └────┬──────┘
 ┌────▼───────────────────────────────────────┐
 │ Services                                   │
 │  learning_engine │ ai_teacher │ llm_client │
 │  course_loader   │ statistics │ scheduler  │
 └────┬───────────────────────────────────────┘
 ┌────▼─────────┐
 │ ORM (SQLA2)  │
 └────┬─────────┘
 ┌────▼─────┐
 │ SQLite   │  источник правды, переживает рестарт
 └──────────┘
```

## Два уровня состояния

| Уровень | Хранит | Где живёт | Переживает рестарт |
|---|---|---|---|
| FSM | шаг диалога | MemoryStorage | нет (пересобирается из БД) |
| DB | сессия, тема, очередь вопросов, mastery, ответы | SQLite | да |

При старте `/learn` или при пустом FSM `learning_engine.restore(user)` читает
активную `study_sessions` и `user_progress`, восстанавливая и состояние, и
текущий вопрос. Глобальных переменных нет.

## Цикл обучения

```
IDLE → /learn → выбор темы → start_session(learn)
  → EXPLANATION (кратко + примеры)
  → QUESTION (difficulty=1)
  → ANSWERING (текст; «не знаю» → HINT, повторный вопрос)
  → EVALUATION (строгий JSON от AI)
  → FEEDBACK → NEXT | REPEAT | PRACTICE | REVIEW | EXAM
  → mastered при mastery ≥ 0.85 и ≥2 сильных ответах на разных уровнях
```

## Мастерство

```
alpha = 0.5 (attempts ≤ 2), иначе 0.3
mastery = clamp(mastery + alpha * (score - mastery), 0, 1)

0.0 не изучено · 0.3 знаком · 0.5 базовое · 0.7 понимает
0.85 хорошо · 1.0 mastered
```

## AI Teacher — только structured JSON

Контекст (курс, тема, уровень, mastered/weak концепции, ошибки, вопрос, ответ)
→ строгий JSON, валидируемый Pydantic:

```python
class Evaluation(BaseModel):
    result: Literal["correct", "partially_correct", "incorrect"]
    score: float = Field(ge=0, le=1)
    feedback: str
    explanation: str
    mastered_concepts: list[str] = []
    weak_concepts: list[str] = []
    next_action: Literal["NEXT", "REPEAT", "PRACTICE", "REVIEW", "EXAM"]
    follow_up_question: str | None = None
    hint: str | None = None
```

Отказоустойчивость: `json_object` → строгий `json.loads` + Pydantic → при сбое
1 repair-запрос (передаём сырой ответ и ошибку валидации) → при повторном сбое
мягкий fallback (`REPEAT`, нейтральный фидбек, mastery не двигаем). Сеть:
timeout 30с, 3 попытки с backoff, учёт `429 Retry-After`. Regex-парсинга нет.

## Экзамен

5–10 фиксированных вопросов (`session_items`), без подсказок и объяснений до
конца → отчёт (сильные/слабые/Recommendation) → обновление mastery. Плохой
результат **не** открывает следующую тему — тема уходит в `REVIEW`.

## Напоминания

Один фоновый `asyncio`-цикл (раз в 60с), без APScheduler. Условия:
`reminders_enabled`, `next_reminder_at <= now`, есть активная тема. Антиспам:
min-интервал 30 мин, backoff после неотвеченных, отключение после `/stop`.

## Схема БД

Ядро: `users`, `courses`, `topics`, `user_progress`, `study_sessions`,
`questions`, `answers`. Плюс две поддерживающие: `concept_mastery` (повтор
слабых концепций) и `session_items` (очередь вопросов — сессия/экзамен
переживают рестарт).

Поля — см. раздел «Схема БД» в истории проекта / соответствующие модели в
`models/`. Все связи — FK, ключевые ограничения: `users.telegram_id UNIQUE`,
`topics UNIQUE(course_id, slug)`, `user_progress UNIQUE(user_id, topic_id)`,
`concept_mastery UNIQUE(user_id, topic_id, concept)`.

## План реализации

| Этап | Содержание | Статус |
|---|---|---|
| 1 | структура, config, логирование, bot, `/start` | ✅ |
| 2 | SQLite, модели, регистрация | ⏳ |
| 3 | courses/topics, `/courses`, `/progress` | ✅ |
| 4 | OpenRouter client, AI Teacher | ✅ |
| 5 | учебная сессия: вопрос/ответ/оценка | ⏳ |
| 6 | mastery, повтор слабых тем | ⏳ |
| 7 | экзамены | ⏳ |
| 8 | статистика | ⏳ |
| 9 | напоминания | ⏳ |

## Соглашения безопасности

- секреты только в `.env` (в `.gitignore`), в коде — ничего;
- логирование прогоняется через `SecretRedactingFilter`;
- ошибки API логируются без заголовков/ключей;
- SQLite-сессии закрываются через async context manager;
- ошибки Telegram и OpenRouter (timeout/rate limit) обрабатываются с retry.
