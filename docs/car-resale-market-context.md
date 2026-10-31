# Car resale market context

The diversification score uses its existing business-correlation scenarios. Public car-market data is separate context, not a business return, profit forecast, or measured correlation.

`analytics.car_resale_market.build_context(cutoff, observations)` freezes a manually collected one-time dataset. Add the returned object as `CAR_RESALE_MARKET_CONTEXT` in the `data` object of a separate derived combined-data snapshot; do not modify the original snapshot or its sealed `allocation_score_v2`. The cutoff is the source snapshot's timezone-aware `saved_at_utc`, not the time of enrichment. Private snapshots stay under ignored `data/`.

Each observation needs `id`, `label`, `value` (a number or null), `unit`, `period`, ISO `period_end`, ISO `published`, an HTTPS `url`, and `limitation`. A range may include numeric `upper`. For a comparison in the same series, add `previous`, `previous_period`, `previous_published`, and HTTPS `previous_url`; the builder derives `change_pct`. A publication date without time must be earlier than the snapshot date. Include precise timezone-aware publication timestamps for sources published on the cutoff date. Record unavailable data with a null value and explain the limitation.

The frozen block includes a version, cutoff, observations and fingerprint. The view validates and replays it before rendering the source-dated note. Missing, altered or invalid context is shown as unavailable. Rendering also requires the source snapshot envelope’s timezone-aware `saved_at_utc`; context later than that timestamp, or context without a reliable source timestamp, is unavailable while the score and scenario explanation remain visible. Collection is manual; no automatic updates or assumptions about the next snapshot are made.

Generated notes end with the portfolio note marker. The Sheets writer only replaces or clears notes bearing that marker within its recorded owned range; a different note at the target is a conflict. It also recognizes notes from the earlier marker-first format. Existing full-sheet writes remain subject to their usual preflight, and a separate live refresh is required to validate the entire production flow.

## Історичний публічний контекст: 29 жовтня 2026

Ці дані були доступні до часу збереження історичного знімка 29.10.2026. Це разовий контекст, а не поточні котирування, прибуток бізнесу чи вимір його кореляції з портфелем.

| Показник і період | Значення | Опубліковано, джерело та обмеження |
| --- | --- | --- |
| Індекс оптових цін Manheim, вересень 2026 | 205,9 пункту; -1,1% до 208,2 у серпні | [7 жовтня](https://www.coxautoinc.com/insights/manheim-used-vehicle-value-index-september-2026-trends/), [серпневий індекс: 8 вересня](https://www.coxautoinc.com/insights/manheim-used-vehicle-value-index-august-2026-trends/). Загальний ринок, не ціни пошкоджених лотів. |
| Медіана українських оголошень, вересень 2026 | $9 500 проти $9 300 у серпні, +2,2% | [2 жовтня](https://eauto.org.ua/news/101200-vzhivani-avto-podorozhchali-shcho-naspravdi-oznachayut-200-do-cin-u-veresni). Ціни пропозиції; змінився склад оголошень, це не ціни угод. |
| Авто зі США в українських оголошеннях, вересень 2026 | Медіана $17 999 | [13 жовтня](https://eauto.org.ua/news/101218-u-ssha-deshevshayut-zvichayni-avto-ale-ne-elektromobili-shcho-ce-oznachaye-dlya-importu). Не ціна продажу чи конкретної моделі. |
| Офіційний курс USD/UAH, 28 жовтня 2026 | 45,6008 грн/USD проти 44,8624 на 30 вересня, +1,6% | [НБУ, 28 жовтня](https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&date=20261028&json), [30 вересня](https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&date=20260930&json). Офіційний курс не обов’язково збігається з курсом угоди. |
| Заміна та фарбування бампера в Києві, квітень 2026 | 15 000-30 000 грн | [8 квітня](https://site.express-insurance.com.ua/news/332). Приклад страховика, не повна вартість відновлення автомобіля. |
| Морський фрахт у консолідованому контейнері, червень 2026 | $1 300-1 700 | [24 червня](https://yes-auto.com.ua/blog/morska-dostavka-avto-etapy-terminy-vartist). Орієнтир одного перевізника США-Балтія, не вся доставка до України. |

Контекст не розраховує маржу, дохідність чи нову бізнесову кореляцію. Для окремої угоди потрібні ціна лота, комісії, логістика, митні платежі, ремонт і підтверджена ціна продажу.
