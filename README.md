# Investment Portfolio

Personal portfolio automation for live IB Gateway data, dividend income estimates, Google Sheets updates, historical snapshots, and Dalio-style risk analysis.

## Main Command

```bash
python -m src.portfolio_sync
```

This bootstraps `.venv` when needed, installs `requirements.txt`, loads `data/ib_flex_env.sh` if present, then runs the portfolio pipeline.

By default it:
- fetches current portfolio data from Interactive Brokers Gateway
- calculates allocation and dividend income
- writes a dated `combined_data` snapshot under `data/snapshots`
- updates the configured Google Sheet
- skips retrospective history sync and Dalio analysis

## Local Setup

Private data stays local. Git tracks only `data/README.md`; credentials, account data, generated snapshots, and local environment files are ignored.

Expected local files:
- `data/credentials.json` for Google Sheets
- `data/ib_flex_env.sh` for IB/Flex settings

Required environment values:
- `IB_GATEWAY_HOST`
- `IB_GATEWAY_PORT`
- `IB_FLEX_TOKEN`
- `IB_FLEX_QUERY_ID_YTD_PERFORMANCE`
- `IB_ACCOUNT_ID`

Example local env file:

```bash
export IB_GATEWAY_HOST=127.0.0.1
export IB_GATEWAY_PORT=7497
export IB_ACCOUNT_ID=DU123456
export IB_FLEX_TOKEN=...
export IB_FLEX_QUERY_ID_YTD_PERFORMANCE=...
```

Do not commit real credentials or account files.

## Common Runs

Run without updating Google Sheets:

```bash
python -m src.portfolio_sync --skip-sheet-update
```

Refresh all data sources:

```bash
python -m src.portfolio_sync --force-refresh
```

Sync historical monthly data from Google Sheets:

```bash
python -m src.portfolio_sync --run-history-sync
```

Run the full pipeline plus Dalio analysis:

```bash
python -m src.portfolio_sync --run-history-sync --run-dalio-analysis
```

Примітка по `return_pct`:
- за замовчуванням уніфікована історія пишеться з порожнім `return_pct` (`--history-return-source blank`)
- це зроблено навмисно, щоб уникнути хибних “дохідностей” при поповненнях/виводах
- якщо потрібно, можна записувати `pct_change` (`--history-return-source pct-change`)

Примітка по датах історії:
- за замовчуванням `--history-frequency monthly`: береться остання вкладка в місяці,
  дата у файлі ставиться як month-end (`YYYY-MM-DD`)
- це робить ряд рівномірним для ризик-аналізу Dalio
- якщо потрібні сирі дати вкладок, використовуйте `--history-frequency raw`

## Диверсифікація та стійкість у Sheets і квартальному HTML

`DataSource.get_combined_data()` додає опційні `DIVERSIFICATION_DATA` та
`HOLY_GRAIL_DATA` до збереження і публікації. Sheets та HTML читають один
збережений результат через `saved_diversification_view()`; представлення не
завантажують ціни і не обчислюють ризик. Чотири summary cards збережені.

- **Оцінка /100**: десять рівновагових перевірок політики. Чотири пройдені,
  три провалені та три невизначені дають **40–70/100**. Це межі невирішених
  перевірок, не ймовірність. Якщо всі невизначені: «Недостатньо даних».
- **Ефективні джерела / ціль 15–20**: `DR² = (sum(w_i*sigma_i))²/(wᵀΣw)`.
  Це історичний еквівалент за ризиком, не кількість незалежних стратегій.
  Від'ємні кореляції збережені; перевищення кількості модельованих експозицій
  позначається як ефект хеджування. Новий headline не містить % до 15 чи
  автоматичного твердження «Holy Grail досягнуто».
- Версії `risk_equivalent_streams_v1` та `diversification_policy_v1`
  зберігаються окремо. Старий `HOLY_GRAIL_DATA` і legacy analyzer незмінні.
  Старі snapshots показують чітко позначений попередній метод без нової оцінки;
  невалідний новий блок не підмінюється старим. Тренди між методами не зіставні.
- Вікно: останні 60 завершених місяців, adjusted USD returns та sample
  covariance на тих самих спостереженнях. 36–59 дають попередню кількість,
  менше 36 приховують її. Ідентичні інструменти, історії та спільні проксі
  об'єднуються; перекази і зміни балансів не є доходностями.
- Кеш не додає джерел. Підтверджений USD cash і USD Treasury з залишком
  <=365 днів є аналітичними резервами без зміни фінансової класифікації.
  Stablecoins не отримують це виключення. Ідеальний хедж, short/borrowing/
  leverage не дають нескінченної диверсифікації.
- HYG lending і BLS/FRED `CUSR0000SETA02` залишаються слабкими проксі.
  Вони не моделюють platform default/depeg або прибуток car resale в Україні.
  Неповні/застарілі оцінки, слабкі проксі та невідомі ризики залишають перевірки
  невизначеними. Володіння активом не схвалює очікувану дохідність.

Повна політика, шоки та формат приватних підтверджень:
[docs/diversification-methodology.md](docs/diversification-methodology.md).
Налаштування, історії, source revisions і fingerprints залишаються в ignored
`data/holy_grail_config.json` та `data/holy_grail_history/`. Повторний запуск
використовує місячний кеш, спільний бюджет збору 60 секунд та timeout 8 секунд.
Помилки необов'язкової аналітики не переривають звичайне оновлення. Змінені
вхідні дані ніколи не використовують стару оцінку. JSON: finite або `null`.

Історичний replay створює нову похідну копію поза автоматичним вибором:

```bash
just holy-grail --snapshot VERIFIED_QUARTER_END_SNAPSHOT \
  --output data/derived_snapshots/quarter_diversification.json --offline
# За потреби: --config PATH --cache-dir PATH; без --offline дозволений bounded refresh.
venv/bin/python portfolio_yic_reports/generate_quarterly_report.py \
  --year YEAR --quarter QUARTER --before VERIFIED_BASELINE \
  --after data/derived_snapshots/quarter_diversification.json
```

Оригінали, `combined_data_latest.json` і фінансові поля зберігаються. Потрібні
позиції саме на дату оцінки, включно із закритими пізніше. Майбутні доходності
відкидаються; backfill сьогоднішніми історіями є ретроспективним. Дати
спостережень і публікацій економічних рядів не ототожнюються. Для похідного
replay завжди передавайте `--after` явно. Публічні diagnostics: лише відсотки
та загальні назви ризиків, без балансів, account IDs або приватних rationale.

## Dalio Holy Grail Analyzer

Модуль `analytics/dalio_holy_grail.py` реалізує risk-аналітику портфеля в дусі Dalio Holy Grail (фокус на незалежних джерелах ризику, а не тільки на кількості інструментів).

Що робить модуль:
- нормалізує історію в базову валюту (`--base-currency`) через `--fx` або `--fx-file`
- агрегує дублікати `(date, asset_bucket)` в один bucket на дату
- рахує ваги по датах (`weights_by_date`) та ключові leverage/netting метрики
- будує матрицю доходностей і кореляційну/коваріаційну структуру
  (`ledoit-wolf` за замовчуванням, також доступні `sample` та `ewma`)
- визначає частоту аналізу (`auto|daily|monthly`), де `auto` для щоденних рядів
  застосовує вікно коваріації `252`
- фільтрує активи для коваріації за мінімальним покриттям
  (`--min-asset-coverage-pct`, за замовчуванням `80%`)
- будує Layer A (статистична диверсифікація) на rolling вікнах (`12/24/36m` за замовчуванням):
  - `avg_corr`, `avg_abs_corr`, `high_corr_pair_share_pct`
  - `N_eff` (Effective Number of Bets) з власних значень кореляційної матриці
  - NumPy HAC кластеризацію (`d_ij = 1 - |corr_ij|`) і `cluster_count`
  - rolling `TRC`-декомпозицію ризику, `max_trc_share_pct`, `risk_hhi`, `n_rc`, `risk_gini`
  - `diversification_ratio = sum(|w_i|*sigma_i)/sigma_p`
- оцінює внесок кожного bucket у ризик портфеля (`risk_contribution_by_bucket`)
- агрегує експозицію по факторах (`factor_exposure`)
- виконує Layer B (economic risk-source diversification) на факторних рядах:
  - rolling OLS betas `r_i = alpha_i + beta_i^T f + eps_i` (window `36m` за замовчуванням)
  - факторний TRC, `factor_hhi`, `max_factor_trc_share_pct`, `factor_n_rc`, `factor_gini`
  - декомпозицію факторний vs residual risk (`factor_risk_share_pct`, `residual_risk_share_pct`)
  - діагностику якості моделі (condition number / VIF) і coverage
- рахує tail-risk (`VaR`, `CVaR`, drawdown) на лагованих вагах `w_{t-1}` без look-ahead bias
- виконує stress-тести по сценаріях і показує покриття bucket-ів шоками
- формує зведення правил керування ризиком (`management_rules`) для алертів по кореляції, risk contribution, drift, якості даних та leverage
- формує вердикт відповідності (`holy_grail_verdict`):
  - scorecard по `Independence`, `Balance`, `Robustness`, `Macro coverage (optional)`
  - загальний `Holy Grail score` (0–100) з прозорими фіксованими вагами `35/35/20/10`
  - список `red_flags` у форматі `code/severity/message/value/threshold/context`

### Вхідні дані

CSV з колонками:
- `date`
- `asset_bucket`
- `market_value`
- `return_pct` (опціонально; якщо порожній/відсутній, рахується як `pct_change` на рівні bucket)
- `currency` (опціонально, за замовчуванням `USD`)

### Приклад запуску

```bash
python3.10 -m analytics.dalio_holy_grail \
  --input data/portfolio_history.csv \
  --output-dir analytics/output \
  --base-currency USD \
  --corr-threshold 0.6 \
  --max-risk-contribution 0.25 \
  --drift-threshold 0.20 \
  --return-unit decimal \
  --return-type simple \
  --analysis-frequency auto \
  --covariance-method ledoit-wolf \
  --min-asset-coverage-pct 80 \
  --min-pair-overlap 24 \
  --factor-input-csv data/factor_returns.csv \
  --layer-b-window-months 36 \
  --layer-b-min-observations 24 \
  --layer-b-collinearity-cond-threshold 30 \
  --layer-b-vif-threshold 10 \
  --layer-b-max-factor-trc-share 0.35 \
  --layer-b-factor-hhi-threshold 0.35 \
  --layer-b-residual-share-threshold 0.40 \
  --layer-b-min-coverage-pct 80 \
  --layer-a-windows 12,24,36 \
  --layer-a-high-corr-threshold 0.70 \
  --layer-a-cluster-corr-cutoff 0.70 \
  --layer-a-trc-max-share 0.35 \
  --layer-a-min-n-rc 4.0 \
  --layer-a-primary-window 36
```

Run only Dalio analysis from an existing CSV:

```bash
python -m src.portfolio_sync --dalio-only --run-dalio-analysis --dalio-input-csv data/portfolio_history.csv
```

## Outputs

- `data/snapshots/combined_data_<date>_<timestamp>.json`
- `data/snapshots/combined_data_latest.json`
- `data/portfolio_history.csv`
- `data/portfolio_history.jsonl`
- `analytics/output/`

## Notes

- Interactive Brokers live positions come from IB Gateway via `ib_insync`.
- YTD performance comes from IBKR Flex Web Service.
- Dividend yields come from yfinance/Yahoo data; Yahoo forward-dividend fallback is called once per ticker to avoid duplicate retry delays.
- Historical sync defaults to monthly rows and blank `return_pct` to avoid false returns from deposits or withdrawals.

Dalio analyzer details:

`factor_returns.csv` (Layer B) має бути wide-формату:
- `date`
- `growth`
- `inflation`
- `real_rates`
- `credit_liquidity`

За замовчуванням stress-сценарії мають покривати 100% bucket-ів шоками.
Щоб дозволити часткове покриття, додайте `--allow-partial-scenario-coverage`.

### Що зберігається у результатах

У `analytics/output` пишуться:
- `normalized_data.csv`
- `weights_by_date.csv`
- `correlation_matrix.csv`
- `rolling_correlation.csv` (вікна `12m` і `36m`)
- `layer_a_metrics_rolling.csv` (`12/24/36m` за замовчуванням)
- `layer_a_trc_rolling.csv`
- `layer_a_cluster_membership_rolling.csv`
- `covariance_matrix.csv`
- `risk_contribution_by_bucket.csv`
- `factor_exposure.csv`
- `factor_returns_aligned.csv`
- `factor_betas_by_bucket_rolling.csv`
- `factor_model_quality_rolling.csv`
- `factor_risk_contribution_rolling.csv`
- `factor_residual_risk_rolling.csv`
- `stress_test_results.csv`
- `quality_checks.csv`
- `high_correlation_pairs.csv`
- `pairwise_confidence.csv` (overlap, coverage, `HIGH/LOW`)
- `asset_coverage.csv` (coverage per asset + inclusion flag for covariance)
- `tail_risk_metrics.csv`
- `weight_drift.csv`
- `holy_grail_scorecard.csv`
- `holy_grail_robustness.csv`
- `holy_grail_red_flags.csv`
- `summary.json` з `diversification_metrics`, `management_rules`, `holy_grail_verdict`

### Важливі правила/прапорці

- `--return-unit decimal|percent`: формат `return_pct` задається явно (auto-detect не використовується)
- `--return-type simple|log`: тип доходностей для ризик-розрахунків
- `--analysis-frequency auto|daily|monthly`: частота core-risk, де `auto` обирає `daily`
  при медіанному кроці дат `<= 3` дні
- `--covariance-method ledoit-wolf|sample|ewma`: дефолт `ledoit-wolf`
- `--covariance-window`: trailing window для covariance; за замовчуванням
  `252` для daily та весь доступний ряд для monthly
- `--min-asset-coverage-pct`: мінімальна частка непорожніх спостережень активу
  для включення в covariance/risk contribution
- `--allow-unmapped-factors`: без цього прапорця bucket-и без `factor_map` викликають помилку
- `--allow-shorts`, `--max-gross-leverage`, `--min-net-to-gross`: контроль short/netting ризику
- `--min-pair-overlap`: поріг, нижче якого парні метрики позначаються як `LOW` confidence
- Layer B (phase 1 deprecation policy):
  - за замовчуванням `factor_input_csv` опційний; без нього Layer B вимикається і повертає deprecation notice у `management_rules`
  - `--layer-b-require-data` (або `--dalio-layer-b-require-data` у `main.py`) робить факторні дані обов'язковими вже зараз
  - у майбутньому major version факторні дані стануть обов'язковими за замовчуванням
- Layer A defaults (Balanced):
  - `high_corr_pair_share_pct > 30` при `|corr| > 0.70` → high-corr alert
  - `max_trc_share_pct > 35` → concentration alert
  - `n_rc < 4` або `neff < 4` → low-independent-bets alert

Migration note:
- Починаючи з поточної версії дефолт `--covariance-method` змінено з `sample`
  на `ledoit-wolf` для стабільнішої оцінки ризику на шумних даних.
- Для daily-входу Layer A/B не переводяться в денні вікна:
  вони рахуються на month-end агрегації, щоб зберегти семантику `12/24/36m`.

### Holy Grail verdict (scorecard)

Вердикт використовує фіксовані ваги компонентів:
- `Independence = 35`
- `Balance = 35`
- `Robustness = 20`
- `Macro = 10`

Складові:
- `Independence`: `neff`, `avg_abs_corr`, `high_corr_pair_share_pct`
- `Balance`: `max_trc_share_pct`, `n_rc`, `risk_gini`
- `Robustness`: розподіли `p10/median/p90` по rolling-вікнах primary Layer A
- `Macro`: `max_factor_trc_share_pct`, `factor_hhi`, `factor_n_rc`, `factor_gini` (якщо Layer B доступний)

Політика без Layer B:
- якщо `Macro` недоступний, вага автоматично `renormalize` на доступні компоненти (без штрафу нулем)

Класи score:
- `>=85` → `Strong`
- `70-84` → `Good`
- `55-69` → `Watch`
- `<55` → `Weak`

## Tests

```bash
python3 -m unittest discover -s tests
```

## Quarterly Report (`just report`)

Generates `portfolio_yic_reports/portfolio_report_YYYY_qN.md` and `portfolio_report_qN_YYYY.html` - Ukrainian quarterly portfolio reports combining IB Flex portfolio snapshots, allocation diff, performance metrics, and Dalio risk analysis.

```bash
just fetch-snapshots              # download CI-fetched Flex snapshots
just run                          # update combined_data (TWR, allocation, dividends)
just report 2026 2                # generate Q2 2026 report
just report 2025 4                # generate Q4 2025 report
```

Prerequisites:
- IB Flex query `1188471` (`stocks_count_trades`) configured with Open Positions + Trades sections, Period = Last Business Day, Format = XML.
- IB Flex query `1575659` (`stocks_trades_quarterly`) configured with Trades section, Period = Last Quarter, Format = XML.
- Add to `data/ib_flex_env.sh`:
  ```bash
  export IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT=1188471
  export IB_FLEX_QUERY_ID_QUARTERLY_TRADES=1575659
  ```
- Snapshots in `data/ib_flex_snapshots/` (use `just fetch-snapshots` to download CI artifacts).

Data sources:
- Positions: IB Flex snapshots in `data/ib_flex_snapshots/` matched by XML `toDate` (+/-3 day tolerance).
- Trades: `trades_*.xml` in `data/ib_flex_snapshots/` matched by quarter date range.
- Allocation diff: `data/portfolio_history.csv` (month-end bucket values).
- YTD TWR, S&P 500/NASDAQ, dividends, freedom progress: `data/snapshots/combined_data_*.json` selected by quarter end date.
- Dalio: `analytics/output/summary.json`.

If no matching snapshot exists, the command refuses with a clear error.

### Automated Quarterly Snapshots (GitHub Actions)

A GitHub Actions cron workflow fetches IB Flex snapshots automatically on the 1st day of Jan/Apr/Jul/Oct at 06:00 UTC (before US market open), capturing the last business day of the previous quarter. Positions and quarterly trades are fetched in a single run.

Each fetch is stored as a GitHub Actions artifact (365-day retention) and a Telegram notification is sent.

To use the fetched snapshots locally:

1. Run `just fetch-snapshots` to download artifacts from the last 4 CI runs into `data/ib_flex_snapshots/`.
2. Run `just run` to update `combined_data` (YTD, allocation, dividends).
3. Run `just report YYYY Q` to generate the report.

Required GitHub secrets:

| Secret | Value |
|---|---|
| `IB_FLEX_TOKEN` | IB Flex Web Service token |
| `IB_FLEX_QUERY_ID_PORTFOLIO_SNAPSHOT` | `1188471` |
| `IB_FLEX_QUERY_ID_QUARTERLY_TRADES` | `1575659` |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (create via @BotFather) |
| `TELEGRAM_CHAT_ID` | Your chat ID (get via @userinfobot) |

The workflow can also be triggered manually via `workflow_dispatch` for backfill.
