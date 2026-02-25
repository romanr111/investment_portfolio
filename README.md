# Інвестиційний Портфель - Аналіз

Цей скрипт аналізує зміни в інвестиційному портфелі акцій на основі XML-файлів.

## Опис

Скрипт `analyze_portfolio.py` парсить XML-файли в директорії `reporting` і аналізує зміни позицій акцій між двома періодами. Результат форматується українською мовою у вигляді таблиці і виводиться в консоль. Скрипт реалізований за допомогою об'єктно-орієнтованого підходу.

## Особливості

- Аналізує зміни в портфелі акцій (збільшення/зменшення позицій)
- Розраховує вагу кожної акції в портфелі
- Показує середню ціну акцій
- Автоматично конвертує китайські акції з HKD в USD
- Виключає певні інструменти (ETF, облігації, BILL) з розрахунку ваги портфеля
- Автоматично ігнорує активи з категорією "BILL" в звіті про зміни
- Сортує позиції за їх вагою в портфоліо (від більшої до меншої)
- Відображає загальну вартість всіх акцій в USD в кінці звіту
- Представляє результати у форматі зручної таблиці з заголовками
- Використовує ООП для інкапсуляції логіки роботи з акціями

## Структура коду

Скрипт використовує наступні класи:
- `Stock` - клас для представлення акції та її параметрів
- `Portfolio` - клас для управління колекцією акцій
- `PortfolioAnalyzer` - клас для аналізу змін між двома портфелями
- `XMLPortfolioParser` - клас для парсингу XML-файлів
- `TableFormatter` - клас для форматування результатів у вигляді таблиці

## Як використовувати

1. Розмістіть XML-файли зі звітами в директорії `reporting/`
   - Перший файл (за алфавітним порядком) буде використаний як початковий
   - Другий файл буде використаний як кінцевий

2. Запустіть скрипт:
   ```
   python3.10 analyze_portfolio.py
   ```

3. Для вибору конкретного формату виводу використовуйте аргумент `--format`:
   ```
   python3.10 analyze_portfolio.py --format text     # тільки текстовий формат
   python3.10 analyze_portfolio.py --format markdown # тільки markdown формат
   python3.10 analyze_portfolio.py --format both     # обидва формати (за замовчуванням)
   ```

4. Перегляньте результати в консолі

## Формати виводу

Скрипт підтримує два формати виводу:

### Текстовий формат
Простий текстовий формат з роздільниками для консольного виводу:
```
Акція     Остання активність    Середня ціна купівлі  Вага у портфоліо
--------  --------------------  ---------------  ----------
9988      Без змін              96.49$           18.42%    
KWEB      Без змін              32.10$           10.44%    
...
```

### Markdown формат
Формат Markdown для кращої сумісності з месенджерами та текстовими редакторами:
```
| Акція | Остання активність | Середня ціна купівлі | Вага у портфоліо |
|-------|-------------------|---------------------|-----------------|
| 9988  | Без змін          | 96.49$              | 18.42%          |
| KWEB  | Без змін          | 32.10$              | 10.44%          |
...
```
Цей формат краще зберігає вирівнювання при копіюванні в Telegram, Notes та інші програми.

Markdown-версія звіту автоматично зберігається у файл з назвою `portfolio_report_YYYY_qN.md`, де:
- YYYY - рік звіту
- N - номер кварталу

Наприклад: `portfolio_report_2025_q1.md`

Файл зберігається в тій самій директорії, де запущений скрипт.

## Приклад виводу

```
Звіт про зміни в портфелі акцій за 1-й квартал 2025 року:
--------------------------------------------------------------------------------
| Акція    | Остання активність    | Середня ціна купівлі | Вага у портфоліо   |
|----------|----------------------|---------------------|-------------------|
| 9988     | Без змін             | 96.49$              | 18.42%            |
| KWEB     | Без змін             | 32.10$              | 10.44%            |
| NKE      | Збільшив (+28%)      | 79.38$              | 8.42%             |
| CVS      | Збільшив (+11%)      | 59.57$              | 7.61%             |
...
|----------|----------------------|---------------------|-------------------|
| Підсумок: | ↑6 ↓4 =7 +2 -1      |                     | 100.00%           |

Загальна вартість всіх акцій: 44485.31$
```

## Налаштування

У файлі `analyze_portfolio.py` ви можете змінити:

- `EXCLUDED_SYMBOLS` - список символів, які будуть виключені з розрахунку ваги портфеля
- `HKD_TO_USD_RATE` - курс конвертації HKD в USD (оновлюйте його за потреби)
- `CHINESE_STOCKS` - список китайських акцій, які потребують конвертації з HKD в USD

## Фільтрація активів

Скрипт автоматично виключає з розрахунку та звіту:
- Символи зазначені в `EXCLUDED_SYMBOLS`
- Активи з атрибутом `assetCategory="BILL"` (державні облігації)

## Вимоги

- Python 3.10+ (оновлено в 2025 році)
- Стандартні бібліотеки Python (os, xml, glob, typing)

## Налаштування Python

Проект використовує Python 3.10. Файл `.python-version` вказує на використання Python 3.10.18.

Для установки залежностей:
```bash
python3.10 -m pip install -r requirements.txt
```

## Збереження snapshot + ретроспективи з Google Sheets

При запуску `main.py` тепер виконується:
- збереження `DataSource.get_combined_data()` у JSON snapshot:
  - `data/snapshots/combined_data_<date>_<timestamp>.json`
  - `data/snapshots/combined_data_latest.json`
- синхронізація історії з датованих вкладок Google Sheets (формат назви вкладки: `31 Dec 2025`)
  у уніфіковані файли:
  - `data/portfolio_history.csv`
  - `data/portfolio_history.jsonl`
- запуск Dalio Holy Grail аналізатора в кінці пайплайну, з результатом у CLI
  та збереженням таблиць у `analytics/output`

Базовий запуск:

```bash
python3.10 main.py
```

Корисні прапорці:

```bash
python3.10 main.py \
  --history-start-date 2024-01-01 \
  --history-end-date 2026-12-31 \
  --history-frequency monthly \
  --history-return-source blank \
  --history-strict-required-buckets
```

Щоб пропустити фінальний Dalio прогін:

```bash
python3.10 main.py --skip-dalio-analysis
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

## Dalio Holy Grail Analyzer

Модуль `analytics/dalio_holy_grail.py` реалізує risk-аналітику портфеля в дусі Dalio Holy Grail (фокус на незалежних джерелах ризику, а не тільки на кількості інструментів).

Що робить модуль:
- нормалізує історію в базову валюту (`--base-currency`) через `--fx` або `--fx-file`
- агрегує дублікати `(date, asset_bucket)` в один bucket на дату
- рахує ваги по датах (`weights_by_date`) та ключові leverage/netting метрики
- будує матрицю доходностей і кореляційну/коваріаційну структуру (`sample` або `ewma`)
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
  --covariance-method ewma \
  --ewma-alpha 0.06 \
  --min-pair-overlap 24 \
  --factor-input-csv data/factor_returns.csv \
  --layer-b-window-months 36 \
  --layer-b-min-observations 24 \
  --layer-b-collinearity-cond-threshold 30 \
  --layer-b-vif-threshold 10 \
  --layer-b-max-factor-trc-share 0.35 \
  --layer-b-factor-hhi-threshold 0.35 \
  --layer-b-residual-share-threshold 0.40 \
  --layer-b-min-coverage-pct 80
  --layer-a-windows 12,24,36 \
  --layer-a-high-corr-threshold 0.70 \
  --layer-a-cluster-corr-cutoff 0.70 \
  --layer-a-trc-max-share 0.35 \
  --layer-a-min-n-rc 4.0 \
  --layer-a-primary-window 36
```

Якщо потрібні фіксовані FX-курси, додайте:

```bash
--fx EUR=1.08 --fx UAH=0.024
```

Якщо потрібні історичні FX-курси по датах, використовуйте:

```bash
--fx-file data/fx_history.csv
```

`fx_history.csv` має містити:
- `date`
- `currency`
- `fx_rate_to_base`

`factor_returns.csv` (Layer B) має бути wide-формату:
- `date`
- `growth`
- `inflation`
- `real_rates`
- `credit_liquidity`

За замовчуванням stress-сценарії мають покривати 100% bucket-ів шоками.
Щоб дозволити часткове покриття, додайте:

```bash
--allow-partial-scenarios
```

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
- `tail_risk_metrics.csv`
- `weight_drift.csv`
- `summary.json` з `diversification_metrics` та `management_rules`

### Важливі правила/прапорці

- `--return-unit decimal|percent`: формат `return_pct` задається явно (auto-detect не використовується)
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
