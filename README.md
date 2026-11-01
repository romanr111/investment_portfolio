# Investment Portfolio

Personal portfolio automation: live IB Gateway data, dividend income estimates, Google Sheets updates, historical snapshots, Dalio-style risk analysis і concentration safeguards.

## Main Command

```bash
python -m src.portfolio_sync
```

Bootstraps `.venv`, ставить requirements, підвантажує `data/ib_flex_env.sh` і запускає пайплайн:

- живі позиції з Interactive Brokers Gateway (`ib_insync`)
- алокація та дивідендний дохід
- датований снапшот `combined_data` у `data/snapshots/`
- оновлення налаштованої Google Sheet
- історія та Dalio-аналіз вимкнені за замовчуванням

## Local Setup

Приватні дані лишаються локально: git трекає тільки `data/README.md`. Токени, акаунти, снапшоти й env-файли — в `.gitignore`.

- `data/credentials.json` — сервісний акаунт Google Sheets
- `data/ib_flex_env.sh` — налаштування IB/Flex: `IB_GATEWAY_HOST`, `IB_GATEWAY_PORT`, `IB_ACCOUNT_ID`, `IB_FLEX_TOKEN`, `IB_FLEX_QUERY_ID_YTD_PERFORMANCE`

Реальні креденшели й акаунт-файли ніколи не коміться.

## Common Runs

```bash
python -m src.portfolio_sync --skip-sheet-update    # без запису в Sheets
python -m src.portfolio_sync --force-refresh        # всі джерела наново
python -m src.portfolio_sync --run-history-sync     # місячна історія зі Sheets
python -m src.portfolio_sync --run-history-sync --run-dalio-analysis
```

Історія за замовчуванням: місячні рядки, дати month-end, порожній `return_pct` (поповнення й виводи — не доходності). Оверрайди: `--history-return-source pct-change`, `--history-frequency raw`.

## Concentration Safeguards

Бал диверсифікації **не бачить** концентрацію за емітентами. Поруч з ним у Sheets і квартальному HTML працюють захисти:

- **Look-through**: SPY, VOO, VTI, VT, ACWI, EFA розкладаються на холдінги; холдінги датовані й не старші 90 днів — файли з майбутніми датами не є доказом.
- **Канонічні issuer-ключі**: прямі акції та холдінги ETF агрегуються під одним ключем (`GOOG` + SPY `alphabet` → `alphabet`); у таблиці — зручно відформатовані назви.
- **Ліміти**: емітент 5% акцій / 2% NAV, Топ-4 ≤ 20%, core (акції) ≥ 50%, Китай ≤ 10%.
- **Рішення прив'язані до суб'єкта**: accept/reduce/exit діє на конкретного емітента, потребує причини і горизонту ≤ 120 днів; зіпсовані або прострочені записи позначаються `invalid_decision_record` і не знімають порушень.
- **What-if**: симуляція угоди порівнює before/after на замороженій конфігурації запису — прогін без змін відтворює збережений запис точно; сторона v2-балу рахується в проді і позначена відповідно.
- **Ownership у writer**: блок ідемпотентний — той самий рендер дає ті самі запити; після скорочення рендер прибирає свої застарілі рядки; чужий вміст або метадані зупиняють запис замість перезапису.

Збережені записи живуть у `DIVERSIFICATION_DATA` / `concentration_v1`; Sheets і HTML читають збережений view — не перекачують ціни й не рахують ризик. Пошкоджений блок позначається попередженням, а не підмінюється старим числом.

Деталі: [docs/diversification-methodology.md](docs/diversification-methodology.md).

## Diversification Score

`capital_diversification_v2` дає **0-100** для інвестованої частини: десять рівновагових перевірок політики (діапазон — межі нерозглянутих перевірок, не ймовірність). 4 пройдено, 3 провалено, 3 нерозглянуто → **40-70**; всі нерозглянуті → «Недостатньо даних». Cash поза оцінкою, показується окремо.

Опційний `capital_diversification_v3` (сусідній запис `allocation_score_v3`) замінює припущення 0,25 для автобізнесу кореляцією з публічним індексом цін вживаних авто (Manheim, США; сценарій цінового каналу при R=1, не вимір вашого бізнесу і не межа для нього). Він з'являється, лише якщо є заморожений блок `data/car_category/block_latest.json` (`just car-category build`); без блока лишається чистий v2. Деталі: `docs/diversification-methodology.md`.

Окремий запис `risk_progress_v1` («Ризиковий прогрес» у вкладці) рахує, скільки незалежних рівноризикових потоків (DR², ціль 15) відповідає покритій частині портфеля; автобізнес входить лише діапазоном сценаріїв «бізнес поводиться як публічний ряд» (припущення, не вимір вашого бізнесу). Записується лише за наявності замороженого блока `data/car_category/proxies_latest.json` (`just car-proxies build`); перегляд офлайн: `just risk-progress`. Деталі: `docs/diversification-methodology.md`.

Бал рахується в пайплайні та зберігається; HTML і Sheets читають збережений `allocation_score_v2` (і v3, якщо він є). Історичні v1/DR² діагностики лишаються доступними у своїх одиницях. Конфіг: приватна секція `allocation` у `data/holy_grail_config.json`; датовані профілі активів (публічні — в `analytics/models/`) підтверджують класифікацію.

Повна політика, шоки, формат приватних профілів:
[docs/diversification-methodology.md](docs/diversification-methodology.md).

Replay явний і offline-first:

```bash
just holy-grail --snapshot VERIFIED_QUARTER_END_SNAPSHOT \
  --output data/derived_snapshots/quarter_diversification.json --offline
venv/bin/python portfolio_yic_reports/generate_quarterly_report.py \
  --year YEAR --quarter QUARTER --before VERIFIED_BASELINE \
  --after data/derived_snapshots/quarter_diversification.json
```

Позиції мають бути саме на дату оцінки, включно з закритими пізніше. Майбутні доходності відкидаються; backfill ретроспективний і так позначений.

## Dalio Holy Grail Analyzer

`analytics/dalio_holy_grail.py` міряє незалежні джерела ризику, а не кількість інструментів:

- нормалізація історії (базова валюта, дедуплікація), опційні факторні шари
- Layer A (rolling 12/24/36m): ефективні ставки `N_eff`, HAC-кластери, TRC-декомпозиція ризику, HHI/gini
- Layer B (опційно, фактори growth/inflation/real rates/credit): rolling бети, факторний vs залишковий ризик, діагностика якості моделі
- tail-risk на лагованих вагах (без look-ahead), stress-сценарії з перевіркою покриття
- вердикт: Independence 35 / Balance 35 / Robustness 20 / Macro 10 (вага Macro перенормовується без Layer B); класи Strong ≥ 85, Good 70-84, Watch 55-69, Weak < 55

Коваріація за замовчуванням: Ledoit-Wolf на останніх 60 завершених місяцях (денні рядки агрегуються до month-end — семантика 12/24/36m зберігається).

Повний список прапорців і вихідних файлів:

```bash
python3 -m analytics.dalio_holy_grail --help
```

Запуск лише Dalio з наявного CSV:

```bash
python -m src.portfolio_sync --dalio-only --run-dalio-analysis --dalio-input-csv data/portfolio_history.csv
```

## Outputs

- `data/snapshots/combined_data_<date>_<timestamp>.json` + `combined_data_latest.json`
- `data/portfolio_history.csv` / `.jsonl`
- `analytics/output/` — метрики Dalio, `summary.json`

## Quarterly Report (`just report`)

```bash
just fetch-snapshots   # завантажити CI-снапшоти Flex
just run               # оновити combined_data (TWR, алокація, дивіденди)
just report 2026 3     # звіт Q3 2026
```

Снапшоти вантажить scheduled GitHub Actions (1-е число Jan/Apr/Jul/Oct: IB Flex відкриті позиції + квартальні угоди, артефакти 365 днів, повідомлення в Telegram, ручний `workflow_dispatch` для backfill). Потрібні секрети: `IB_FLEX_TOKEN`, `IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT`, `IB_FLEX_QUERY_ID_QUARTERLY_TRADES`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

Вхідні дані звіту: позиції матчами за XML `toDate` (±3 дні), угоди за датами кварталу, диф алокації з `data/portfolio_history.csv`, YTD/дивіденди/свобода зі снапшотів `combined_data`, Dalio з `analytics/output/summary.json`. Без відповідного снапшоту команда відмовляється з явною помилкою.

## Tests

```bash
python3 -m unittest discover -s tests
```