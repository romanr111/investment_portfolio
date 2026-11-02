"""Public view of one saved risk_progress_v2 record: the single headline score. No collection.

Every number and text comes from the replayed record (and the replayed v2 record it was derived
from); nothing is fetched and no configuration is read. A record that does not replay shows
"Недоступно" and never falls back to another method.
"""
from analytics.holy_grail.views.allocation import (WARNINGS, _PROXY_LABELS, _concentration_section_for, _floor1, _pct,
                                                    _risk_progress_text, group_label, risk_fact_rows)

CAR_ID = 'car_business'
SCALE = '100 = ефект 15 однакових незалежних потоків'
ASSUMPTION = ('автобізнес через кошик CPRT/KMX/OPLN; фактична прибутковість бізнесу ще не перевірена, '
              'ризик оцінено через проксі')
NO_CAR_ASSUMPTION = 'усі інвестовані групи оцінені за історіями їхніх представників; автобізнесу в портфелі немає'
# Warnings of the saved v2 that concern its own car correlation, not this score.
_V2_CAR_WARNINGS = {'invalid_car_category_block', 'category_index_lagged', 'category_pair_unmeasured'}
QUALITY = {
    'lagged_one_month': 'останній спільний місяць відстає від дати знімка на місяць',
    'short_history': 'історія 36-59 місяців замість 60',
    'source_v2_provisional': 'вхідна оцінка капіталу попередня',
    'hedge_driven_count': 'хеджування підвищує еквівалент: це не кількість незалежних бізнесів',
}
REASONS = {
    'car_proxies_missing': 'немає блока кошика CPRT/KMX/OPLN для автобізнесу',
    'invalid_car_proxies_block': 'блок кошика CPRT/KMX/OPLN пошкоджений або не відповідає даті знімка',
    'insufficient_common_history': 'менше 36 спільних місяців історії',
    'car_basket_unavailable': 'ряд кошика CPRT/KMX/OPLN для автобізнесу відсутній, короткий або застарілий',
    'stale_series': 'є ряд, що завершується надто давно',
    'no_history': 'для частини інвестованих груп немає ряду дохідностей',
    'invalid_weights': 'ваги груп некоректні',
    'no_streams': 'немає груп для оцінки',
    'main_unavailable': 'головне вікно недоступне',
    'stale_common_history': 'останній спільний місяць надто давній',
    'degenerate_covariance': 'історія не дає придатної матриці коваріації',
    'not_positive_semidefinite': 'матриця коваріації некоректна',
    'no_invested_assets': 'немає інвестованої частини',
    'source_v2_unavailable': 'вхідна оцінка капіталу недоступна',
    'invalid_inputs': 'некоректні або неповні входи',
    'missing': 'ряд відсутній', 'stale': 'ряд застарів', 'insufficient_history': 'ряд закороткий', 'unusable': 'ряд непридатний',
}
# Qualitative reference only (All Weather style): which growth/inflation environments a class usually favours.
# No numbers; part of the owner's judgment, not a measurement of any reaction.
ENVIRONMENTS = {('+', '-'): 'зростання↑, інфляція↓', ('+', '+'): 'зростання↑, інфляція↑',
                ('-', '-'): 'зростання↓, інфляція↓', ('-', '+'): 'зростання↓, інфляція↑'}
_EQUITY = ('зростання↑, інфляція↓', {('+', '-')})
_NOMINAL = ('зростання↓, інфляція↓', {('-', '-')})
_HY = ('зростання↑', {('+', '-'), ('+', '+')})
_REAL = ('зростання↑, інфляція↑', {('+', '+')})
ENVIRONMENT_MAP = {
    'equity_us': _EQUITY, 'equity_developed': _EQUITY, 'equity_china': _EQUITY, 'equity_emerging': _EQUITY,
    'treasury_medium': _NOMINAL, 'treasury_long': _NOMINAL, 'credit_ig_usd': _NOMINAL,
    'credit_hy_usd': _HY, 'credit_hy_eur': _HY, 'commodities': _REAL, 'silver': _REAL,
    'gold': ('інфляція↑', {('+', '+'), ('-', '+')}),
    'treasury_short': ('- (резерв)', set()),
    'crypto': ('зростання↑ (рішення власника)', {('+', '-'), ('+', '+')}),
    CAR_ID: ('не визначено: фактична прибутковість ще не перевірена, ризик оцінено через проксі', set()),
}


def _num(value, places=1):
    return f'{value:.{places}f}'.replace('.', ',')


def _signed(value, places=1):
    return f'{value:+.{places}f}'.replace('.', ',')


def _share(value):
    """A share of capital or risk in percent; a hedge can make it negative, and the sign is kept."""
    return _pct(value * 100) if value >= 0 else f'{value * 100:.1f}%'.replace('.', ',')


def _stamp(iso):
    return '.'.join(reversed(iso.split('-')))


def _label(identifier, definitions):
    return 'Автобізнес' if identifier == CAR_ID else group_label(identifier, definitions)


def _reason(code):
    return REASONS.get(str(code).split(':')[0], 'недостатньо придатних даних для оцінки')


def _headline(record):
    display = record['progress_display']
    return display['headline'] if isinstance(display, dict) else display


def _detail(record):
    display = record['progress_display']
    return display['detail'] if isinstance(display, dict) else display


SHORT_V2 = {
    'partial_or_cached_valuations': 'частина балансів неповна, застаріла або має іншу дату',
    'cash_liabilities_outside_scope': 'особистий борг і облікова корекція Cash поза оцінкою',
    'partial_pair_history': 'для частини пар лише 36-59 місяців історії',
    'unknown_profiles': 'є нерозпізнані позиції',
    'unreconciled_valuations': 'суми позицій не узгоджуються з NAV',
    'unreconciled_positions': 'частина підсумку не розкладена на позиції',
}


def _v2_reason(code):
    if code in SHORT_V2:
        return SHORT_V2[code]
    text = WARNINGS.get(code)
    return text[0].lower() + text[1:].rstrip('.') if text else None


def _streams(value):
    """Equivalent count for the anchor: rounded to one decimal, never shown as 15 before the target is reached."""
    text = f'{value:.1f}'
    if value < 15 - 1e-10 and float(text) >= 15:
        text = '14.9'
    return text.replace('.', ',')


def _quality_reasons(record):
    """Concrete reasons for a provisional or limited result, from the record's own warnings (v2 warnings included)."""
    reasons = []
    for code in record.get('warnings') or []:
        if code == 'car_proxy_assumption' or code in _V2_CAR_WARNINGS:
            continue  # shown as the assumption line / belongs to the older car-correlation scenarios of v2
        reasons.append(QUALITY.get(code) or _v2_reason(code) or 'інші обмеження входів моделі')
    return list(dict.fromkeys(reasons))


def _disp(value):
    """One decimal, rounded down, from a stored display value ({'headline','detail'} or a number)."""
    detail = value['detail'] if isinstance(value, dict) else value
    return _floor1(detail)


def _risk_rows(main, definitions):
    weights, shares, vols = main['capital_weights'], main['risk_share'], main['annual_volatility_pct']
    order = sorted((g for g in weights if weights[g] > 0), key=lambda g: (-shares[g], g))
    rows = [('Група', 'Частка інвестованого капіталу → модельний внесок у ризик · річна волатильність ряду')]
    rows.extend((_label(g, definitions), f'{_share(weights[g])} → {_share(shares[g])} · {_num(vols[g])}%') for g in order)
    rows.append(('Модельна річна волатильність портфеля',
                 _num(main['annual_portfolio_volatility_pct']) + '% (за місячною вибіркою; не прогноз збитку)'))
    return order, rows


def _worst_rows(stress, definitions):
    worst = (stress or {}).get('worst_months')
    if (stress or {}).get('status') not in {'modeled', 'provisional'} or not worst:
        return [('Найгірші модельні місяці доступного вікна', 'Недоступно')]
    months = '; '.join(f"{item['date'][:7]} ({_signed(item['portfolio_return'] * 100)}%)" for item in worst['months'])
    contributions = sorted(worst['contributions'].items(), key=lambda item: (item[1], item[0]))
    return [('Найгірші модельні місяці доступного вікна',
             f"{_stamp(worst['window_start'])} - {_stamp(worst['window_end'])}: {worst['count']} місяців: {months}; "
             f"середня дохідність модельного портфеля {_signed(worst['mean_portfolio_return'] * 100)}%"),
            ('Середній внесок у ці місяці, п.п.',
             '; '.join(f'{_label(g, definitions)} {_signed(v * 100, 2)}' for g, v in contributions)),
            ('Примітка', 'Модель на представниках активів і поточних вагах; не фактичні збитки.')]


def _writeoff_rows(stress):
    writeoff = (stress or {}).get('car_writeoff')
    if not writeoff:
        return []
    cases = '; '.join(f"списання {_num(item['loss_fraction'] * 100, 0)}% вартості: {_signed(-item['nav_loss_pct'])}% NAV"
                      for item in writeoff['scenarios'])
    return [('Окремий сценарій списання вартості автобізнесу',
             f"частка автобізнесу {_pct(writeoff['weight_pct_nav'])} NAV; {cases}"),
            ('Припущення сценарію', 'решта активів незмінна; додаткові зобов’язання, супутні збитки та податкові наслідки '
                                     'не враховані. Це арифметика частки в NAV, не ймовірність і не прогноз.')]


def _environment_rows(order, definitions):
    rows = [('Карта економічних середовищ (якісна)',
             '; '.join(f"{_label(g, definitions)}: {ENVIRONMENT_MAP.get(g, ('не визначено', set()))[0]}" for g in order))]
    covered = set()
    for g in order:
        covered |= ENVIRONMENT_MAP.get(g, ('', set()))[1]
    missing = [text for key, text in ENVIRONMENTS.items() if key not in covered]
    if missing:
        rows.append(('Середовища без відповідного класу на карті',
                     'Серед поточних груп немає класу, який карта відносить до середовища: ' + '; '.join(missing) + '.'))
    rows.append(('Про карту', 'Довідкова карта за підходом All Weather: вона не вимірює реакцію активів на зміни зростання '
                              'та інфляції відносно очікувань; частина клітинок - поширена практика або рішення власника.'))
    return rows


def _scenario_text(item, with_vol_series=False):
    parts = []
    if with_vol_series:
        parts.append(f"волатильність ряду {_num(item['car_series_annual_volatility_pct'])}%")
    parts.extend([f"бал {_floor1(item['progress_points'])} зі 100", f"еквівалент потоків {_floor1(item['effective_streams'])}",
                  f"внесок автобізнесу в ризик {_share(item['car_risk_share'])}",
                  f"волатильність портфеля {_num(item['annual_portfolio_volatility_pct'])}%"])
    return '; '.join(parts)


def _volatility_rows(sensitivity):
    block = (sensitivity or {}).get('volatility') or {}
    if block.get('status') == 'not_applicable':
        return []
    if block.get('status') not in {'modeled', 'provisional'}:
        return [('Чутливість до волатильності автобізнесу', 'Недоступно')]
    rows = [('Чутливість до волатильності автобізнесу',
             'Штучне масштабування всього ряду автобізнесу зі збереженням кореляцій на місяцях головного сценарію; '
             'не оцінка ризику бізнесу і не змінює головний бал.')]
    for key, item in block['items'].items():
        rows.append((f"Множник ×{key.replace('.', ',')}", _scenario_text(item, with_vol_series=True)))
    return rows


def _comparison_rows(sensitivity):
    block = (sensitivity or {}).get('proxy_comparison') or {}
    title = 'Чутливість до представника автобізнесу'
    if block.get('status') == 'not_applicable':
        return []
    if block.get('status') not in {'modeled', 'provisional'}:
        missing = '; '.join(f"{_PROXY_LABELS.get(name, name)}: {_reason(item.get('reason'))}"
                            for name, item in (block.get('items') or {}).items() if item.get('status') == 'unavailable')
        return [(title, 'Порівняння неповне або недоступне' + (' (' + missing + ')' if missing else '') +
                 '; діапазон не показано. Заміна кошика акцій на цінові індекси; не вимір ризику бізнесу.')]
    rows = [(title, f"Заміна кошика акцій на цінові індекси; не вимір ризику бізнесу. Спільна вибірка {block['common_observations']} "
                    f"місяців {_stamp(block['window_start'])} - {_stamp(block['window_end'])}"
                    + ('' if block.get('same_sample_as_main') else '; відрізняється від вибірки головного балу'))]
    for name, item in block['items'].items():
        label = _PROXY_LABELS.get(name, name)
        rows.append((label, 'недоступно' if item.get('progress_points') is None else _scenario_text(item)))
    span = block.get('range')
    if span:
        rows.append(('Діапазон за чотирма представниками',
                     f"{_disp(span['low_display'])}-{_disp(span['high_display'])} зі 100; це набір припущень, не довірчий інтервал"))
    return rows


def _window36_rows(record):
    window = (record.get('windows') or {}).get('m36') or {}
    if window.get('effective_streams') is None:
        rows = [('Вікно 36 місяців (діагностика)', 'Недоступно')]
    else:
        rows = [('Вікно 36 місяців (діагностика)',
                 f"{_stamp(window['window_start'])} - {_stamp(window['window_end'])}: бал {_floor1(window['progress_points'])} зі 100; "
                 f"еквівалент потоків {_floor1(window['effective_streams'])}; "
                 f"волатильність портфеля {_num(window['annual_portfolio_volatility_pct'])}%")]
    return rows + [('Про вікна', 'Різниця між вікнами - це зміна історії ринку, а не портфеля.')]


def _older_rows(data, v2, expected, definitions):
    section = data['DIVERSIFICATION_DATA']
    rows = []
    score = v2.get('display_score')
    rows.append(('Капітальна диверсифікація v2 (capital_diversification_v2)',
                 'Недоступно' if score is None else f'{score} зі 100'))
    category = section.get('allocation_score_v3')
    if category is not None:
        try:
            from analytics.holy_grail.allocation_score_v3 import validate_saved_allocation_v3
            good = validate_saved_allocation_v3(category, data, v2, expected, v2_validated=True)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            good = False
        rows.append(('Капітальна диверсифікація v3 (capital_diversification_v3)',
                     f"{category['display_score']} зі 100" if good and category.get('display_score') is not None else 'Недоступно'))
    older = section.get('risk_progress_v1')
    if older is not None:
        try:
            from analytics.holy_grail.risk_progress import validate_saved_risk_progress_v1
            good = validate_saved_risk_progress_v1(older, data, v2, expected, v2_validated=True)
            text = _risk_progress_text(older, definitions)[0] if good else 'Недоступно'
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            text = 'Недоступно'
        rows.append(('Ризиковий прогрес v1 (risk_progress_v1, без автобізнесу в заголовку)', text))
    rows.append(('Порівняння методик', 'Бал порівнюють лише в межах тієї самої методики (risk_progress_v2); на межі методик '
                                       'показується «Змінено методику», а не динаміка.'))
    return rows


def _input_rows(v2, definitions, order):
    """Representatives, equity sectors and confirmed risk facts: the inputs of the saved v2 record, unchanged."""
    rows = []
    for group in order:
        representative = 'кошик CPRT/KMX/OPLN (проксі автобізнесу)' if group == CAR_ID else definitions.get(group, {}).get('representative')
        if representative:
            rows.append(('Представник: ' + _label(group, definitions), representative))
    for group, sectors in sorted(v2['sectors'].items()):
        rows.append(('Сектори: ' + _label(group, definitions),
                     '; '.join(name + ': ' + _pct(share * 100) for name, share in sorted(sectors.items())) or 'Не підтверджено'))
    return rows + risk_fact_rows(v2)[0]


def risk_progress_v2_view(view, data, v2, expected, saved_at_utc=None):
    """Fill `view` from the saved risk_progress_v2 record; `v2` is the already replayed capital record."""
    record = data['DIVERSIFICATION_DATA']['risk_progress_v2']
    try:
        from analytics.holy_grail.risk_progress import validate_saved_risk_progress_v2
        valid = bool(validate_saved_risk_progress_v2(record, data, v2, expected, v2_validated=True))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        valid = False
    definitions = v2['configuration']['group_definitions']
    stamp = _stamp(v2['as_of_date'])
    cash = v2['coverage'].get('cash_pct_nav')
    cash_text = _pct(cash) if cash is not None else '-'
    safeguards = _concentration_section_for(data, v2, v2['configuration'].get('concentration_decisions'))
    safeguard_rows = list((safeguards or {}).get('rows') or [])
    view.update(title='Диверсифікація портфеля', as_of=stamp, cash_cell=cash_text, warnings=[], principal_constraint='',
                coverage_summary='Cash поза оцінкою: ' + cash_text + ' повного портфеля.', risk_facts=[],
                safeguard_summary=(safeguards or {}).get('summary') or [])
    ok = valid and record['status'] in {'modeled', 'provisional'}
    if not ok:
        if not valid:
            headline, reason = 'Недоступно', 'збережений запис risk_progress_v2 не відтворюється зі збережених входів'
        elif record['status'] == 'not_applicable':
            headline, reason = 'Не застосовується', 'немає інвестованої частини'
        else:
            headline, reason = 'Недоступно', _reason(record.get('reason'))
        rows = [('Метод', 'risk_progress_v2'), ('Статус', headline + ': ' + reason), ('Дата позицій', stamp)] + safeguard_rows
        view.update(headline=headline, sheet_number=headline, score_cell=headline, status=headline, sheet_status=headline,
                    model_status=headline, rows=rows, largest_text='-', sensitivity_text='-', drivers=[],
                    sheet_summary=[('Диверсифікація портфеля', headline), ('Висновок', headline + ': ' + reason),
                                   ('Cash поза оцінкою', cash_text)] + list(view['safeguard_summary']))
        return view

    main = record['windows']['m60']
    streams = main['effective_streams']
    car_proxy = (record.get('coverage') or {}).get('car_proxy')
    order, risk_rows = _risk_rows(main, definitions)
    top = [g for g in order if main['risk_share'][g] > 0][:2]
    contributions = ' · '.join(f"{_label(g, definitions)} {_share(main['capital_weights'][g])} капіталу → "
                               f"{_share(main['risk_share'][g])} ризику" for g in top)
    provisional = record['status'] == 'provisional'
    reasons = _quality_reasons(record)
    parts = ['до ' + _stamp(main['window_end'])] + (['ретроспективний розрахунок'] if record.get('retrospective') else [])
    parts.append('Якість даних: ' + ('; '.join(reasons) if reasons else 'без додаткових застережень'))
    data_line = ' · '.join(parts)
    score_text = f"≈{_headline(record)}/100 · {SCALE}; зараз еквівалент ≈{_streams(streams)}"
    lead = [('Диверсифікація портфеля', score_text), ('Найбільший модельний внесок у ризик', contributions),
            ('Припущення', ASSUMPTION if car_proxy else NO_CAR_ASSUMPTION)]
    model = 'Попередня модельна оцінка' if provisional else 'Модельна оцінка'
    label = model + (' · автобізнес через проксі' if car_proxy else '')
    summary = lead[:1] + [('Висновок', label)] + lead[1:] + [('Дані', data_line), ('Кеш поза оцінкою', cash_text)] \
        + list(view['safeguard_summary'])
    stress = record.get('stress')
    sensitivity = record.get('sensitivity')
    reduction = main.get('volatility_reduction_pct')
    rows = [('Метод', 'risk_progress_v2'), ('Оцінка', f"≈{_headline(record)} зі 100 ({_num(_detail(record))} у деталях)"),
            ('Модель', 'Автобізнес оцінений через проксі: місячна дохідність рівновагового кошика CPRT/KMX/OPLN (не ваш бізнес); '
                       'решта груп - за історіями їхніх представників; ваги поточного знімка застосовано до всього вікна.'
                       if car_proxy else 'Усі групи оцінені за історіями їхніх представників; ваги поточного знімка застосовано до всього вікна.'),
            ('Якість даних', '; '.join(reasons) if reasons else 'без додаткових застережень'),
            ('Вікно 60 місяців', f"{_stamp(main['window_start'])} - {_stamp(main['window_end'])}; {main['observations']} спостережень"),
            ('Інтерпретація', f"Модельний ефект диверсифікації еквівалентний приблизно {_streams(streams)} однакового "
                              f"незалежного потоку. Модельне зниження волатильності відносно тих самих активів із повною "
                              f"позитивною кореляцією: {_num(reduction)}%. Це політика шкали, не гарантія меншого майбутнього "
                              f"ризику і не прибутковість." if reduction is not None else 'Недоступно'),
            ('Cash від повного портфеля', _pct(cash))] + safeguard_rows
    if 'hedge_driven_count' in (main.get('flags') or []):
        rows.append(('Хеджування', QUALITY['hedge_driven_count']))
    rows.extend(risk_rows)
    rows.extend(_worst_rows(stress, definitions))
    rows.extend(_writeoff_rows(stress))
    rows.extend(_environment_rows(order, definitions))
    rows.extend(_volatility_rows(sensitivity))
    rows.extend(_comparison_rows(sensitivity))
    rows.extend(_window36_rows(record))
    rows.extend(_older_rows(data, v2, expected, definitions))
    rows.extend(_input_rows(v2, definitions, order))
    rows.append(('Метод', 'Історичні кореляції та модельні припущення не гарантують майбутньої стійкості або прибутку.'))
    from analytics.holy_grail.car.resale_market import conclusion_note
    view.update(headline=f'≈{_headline(record)}/100', sheet_number=score_text, score_cell=_headline(record), status=label,
                sheet_status=label, model_status=model, rows=rows, largest_text=contributions, sensitivity_text=ASSUMPTION,
                drivers=[f'{name}: {value}' for name, value in lead] + [f'Дані: {data_line}'], sheet_summary=summary,
                risk_facts=list((safeguards or {}).get('breach_facts') or []) + risk_fact_rows(v2)[1][:3],
                warnings=reasons, principal_constraint=' '.join(reasons),
                conclusion_note=conclusion_note(record, data.get('CAR_RESALE_MARKET_CONTEXT'), saved_at_utc,
                                                [f'{name}: {value}' for name, value in lead] + ['Дані: ' + data_line]))
    return view
