"""Public view of one saved risk_progress_v3 record: the individual-investor headline. No collection.

Every number and text comes from the replayed record and the replayed v2 record it was derived from; nothing is
fetched and no configuration is read. Private streams are shown by class and country with a numbered location: no
USD amounts and no location names. A record that does not replay shows "Недоступно" and never falls back to another
method. The sheet summary keeps the labels and order of the risk_progress_v2 view, so a tab written by v2 can be
rewritten in place.
"""
from analytics.holy_grail.risk_progress import EPS
from analytics.holy_grail.risk_progress_v3 import PRIVATE_PREFIX, PROXY_PREFIX, TARGET_V3
from analytics.holy_grail.views.allocation import _concentration_section_for, _pct, risk_fact_rows
from analytics.holy_grail.views.risk_progress_v2 import (
    QUALITY, REASONS, _V2_CAR_WARNINGS, _comparison_rows, _detail, _disp, _headline, _input_rows, _label, _num,
    _older_rows, _share, _shrinkage_rows, _signed, _stamp, _streams, _v2_reason, _volatility_rows, _worst_rows,
    _writeoff_rows)

METHOD = 'risk_progress_v3'
SCALE = f'100 = ефект {TARGET_V3} однакових незалежних потоків'
CLASSES = {'residential_re': 'житлова нерухомість', 'commercial_re': 'комерційна нерухомість',
           'farmland': 'сільгоспземля', 'development_land': 'земля під забудову',
           'ovdp_deposits_uah': 'гривневі ОВДП і депозити', 'ua_sovereign_usd': 'валютні ОВДП і єврооблігації України',
           'p2p_loans': 'P2P-позики'}
PROXIES = {'infrastructure': 'інфраструктура', 'private_equity': 'приватний капітал',
           'private_credit_funds': 'фонди приватного кредиту', 'timberland': 'лісові угіддя'}
COUNTRIES = {'UA': 'Україна', 'US': 'США', 'PL': 'Польща', 'DE': 'Німеччина', 'ES': 'Іспанія', 'PT': 'Португалія',
             'AE': 'ОАЕ', 'GE': 'Грузія', 'other': 'без країни'}
SOURCES = {'listed': 'біржові групи', 'car_business': 'автобізнес', 'proxy': 'біржові проксі приватних активів'}
QUALITY_V3 = dict(QUALITY, **{
    'stale_private_valuation': 'оцінка вартості приватного активу старша за 12 місяців',
    'private_valuation_after_snapshot': 'оцінка вартості приватного активу пізніша за дату знімка',
    'ua_link_unreviewed': 'географію автобізнесу не підтверджено: зв’язок з Україною враховано лише в несприятливому сценарії',
})
# Shown as the assumption line, not as data-quality reasons.
ASSUMPTIONS = {'car_proxy_assumption', 'modeled_private_assumptions', 'listed_proxy_assumption'}
REASONS_V3 = dict(REASONS, **{
    'no_history': 'для частини потоків (груп, факторів або проксі) немає ряду дохідностей',
    'private_model_invalid': 'файл параметрів приватних потоків відсутній або некоректний',
    'invalid_private_streams': 'декларація приватних потоків некоректна',
    'class_not_in_model': 'клас або країна приватного активу відсутні в моделі',
    'unsupported_leverage': 'приватний актив із боргом: плече не підтримується',
    'cash_entries_exceed_cash': 'депозити, задекларовані з Cash, перевищують Cash знімка',
    'invalid_reclassify': 'перекласифікація позиції некоректна',
})


def _reason(code):
    return REASONS_V3.get(str(code).split(':')[0], 'недостатньо придатних даних для оцінки')


def _streams7(value):
    """Equivalent streams, one decimal; never shown as the target before it is reached."""
    text = f'{value:.1f}'
    if value < TARGET_V3 - EPS and float(text) >= TARGET_V3:
        text = f'{TARGET_V3 - .1:.1f}'
    return text.replace('.', ',')


def _country(code):
    return COUNTRIES.get(code, code)


def _labeler(record, definitions):
    """Generic stream labels: class and country, a numbered location (never its name), proxy tickers."""
    rows = {row['id']: row for row in (record.get('coverage') or {}).get('streams') or []}
    places = {}
    for row in rows.values():
        if row.get('location'):
            places.setdefault(row['country'], set()).add(row['location'])
    numbers = {(country, name): (i + 1, len(names)) for country, names in places.items()
               for i, name in enumerate(sorted(names))}
    proxies = (record.get('model') or {}).get('proxies') or {}

    def label(identifier):
        if identifier.startswith(PROXY_PREFIX):
            cls = identifier[len(PROXY_PREFIX):]
            return f"{PROXIES.get(cls, cls)} (проксі {'/'.join((proxies.get(cls) or {}).get('symbols') or [])})"
        if identifier.startswith(PRIVATE_PREFIX):
            row = rows[identifier]
            text = f"{CLASSES.get(row['cls'], row['cls'])} · {_country(row['country'])}"
            if row.get('location'):
                number, count = numbers[(row['country'], row['location'])]
                text += f' · локація {number} з {count}'
            return text
        return _label(identifier, definitions)
    return label


def _quality_reasons(record):
    reasons = []
    for code in record.get('warnings') or []:
        if code in ASSUMPTIONS or code in _V2_CAR_WARNINGS:
            continue
        reasons.append(QUALITY_V3.get(code) or _v2_reason(code) or 'інші обмеження входів моделі')
    return list(dict.fromkeys(reasons))


def _assumption(record, car_proxy):
    warnings = set(record.get('warnings') or [])
    parts = []
    if 'modeled_private_assumptions' in warnings:
        parts.append('приватні активи змодельовано за публічними параметрами, не вимірювання ваших об’єктів')
    if 'listed_proxy_assumption' in warnings:
        parts.append('частина приватних активів через біржові проксі')
    if car_proxy:
        parts.append('автобізнес через кошик CPRT/KMX/OPLN; фактична прибутковість бізнесу ще не перевірена')
    return '; '.join(parts) or 'усі потоки оцінені за історіями їхніх представників'


def _risk_rows(main, label):
    weights, shares, vols = main['capital_weights'], main['risk_share'], main['annual_volatility_pct']
    order = sorted((s for s in weights if weights[s] > 0), key=lambda s: (-shares[s], s))
    rows = [('Потік', 'Частка капіталу (інвестоване + приватне) → модельний внесок у ризик · річна волатильність')]
    rows.extend((label(s), f'{_share(weights[s])} → {_share(shares[s])} · {_num(vols[s])}%') for s in order)
    rows.append(('Модельна річна волатильність портфеля',
                 _num(main['annual_portfolio_volatility_pct']) + '% (за місячною вибіркою; не прогноз збитку)'))
    return order, rows


def _scenario_rows(block):
    title = 'Діапазон за припущеннями'
    if not block or block.get('status') == 'not_applicable':
        return [(title, 'Не застосовується: модельованих приватних потоків немає')]
    if block.get('status') not in {'modeled', 'provisional'}:
        return [(title, 'Недоступно')]
    items, vol = block['items'], block['volatility']
    low, high = items['adverse'], items['favorable']
    return [(title, f"несприятливі {_disp(low['progress_display'])} - сприятливі {_disp(high['progress_display'])} зі 100 "
                    f"(еквівалент {_streams7(low['effective_streams'])}-{_streams7(high['effective_streams'])}); змінюються лише "
                    'кореляції з ринком, частки спільного ризику країни, класу й локації та зв’язок з автобізнесом; це набір '
                    'припущень, не довірчий інтервал'),
            ('Чутливість до волатильності приватних потоків',
             f"×0,5: {_disp(vol['0.5']['progress_display'])} зі 100; ×2: {_disp(vol['2.0']['progress_display'])} зі 100; "
             'ефект диверсифікації не змінюється монотонно з волатильністю')]


def _gain_rows(gain):
    title = 'Внесок приватних потоків'
    if not gain or gain.get('status') == 'not_applicable':
        return [(title, 'Не застосовується: приватних потоків не задекларовано')]
    if gain.get('status') not in {'modeled', 'provisional'}:
        return [(title, 'Недоступно' + (': ' + _reason(gain['reason']) if gain.get('reason') else ''))]
    base = gain['items']['base']
    return [(title, f"{_signed(gain['total_points'])} балу: модельовані {_signed(gain['modeled_points'])}, біржові проксі "
                    f"{_signed(gain['proxy_points'])}; без них {_disp(base['progress_display'])} зі 100 на тій самій вибірці")]


def _source_rows(record):
    sources = record.get('sources') or {}
    capital, risk = sources.get('capital_pct') or {}, sources.get('risk_pct') or {}
    if not risk:
        return []
    def name(key):
        return SOURCES.get(key) or 'приватні: ' + _country(key.split(':', 1)[1])
    text = '; '.join(f'{name(k)} {_share(capital[k] / 100)} капіталу → {_share(risk[k] / 100)} ризику'
                     for k in sorted(risk, key=lambda k: (-risk[k], k)))
    locations = record.get('locations') or {}
    rows = [('Ризик за джерелами', text)]
    if locations:
        rows.append(('Локації приватних потоків', '; '.join(f'{_country(c)}: {n}' for c, n in sorted(locations.items()))))
    return rows


def _window36_rows(record):
    window = (record.get('windows') or {}).get('m36') or {}
    if window.get('effective_streams') is None:
        reason = _reason(window.get('reason')) if window.get('reason') else None
        rows = [('Вікно 36 місяців (діагностика)', 'Недоступно' + (f': {reason}' if reason else ''))]
    else:
        rows = [('Вікно 36 місяців (діагностика)',
                 f"{_stamp(window['window_start'])} - {_stamp(window['window_end'])}: бал {_disp(window['progress_display'])} зі 100; "
                 f"еквівалент потоків {_streams7(window['effective_streams'])}; "
                 f"волатильність портфеля {_num(window['annual_portfolio_volatility_pct'])}%")]
    return rows + [('Про вікна', 'Різниця між вікнами - це зміна історії ринку, а не портфеля.')]


def _market_rows(data, v2, expected, definitions):
    """The replayed risk_progress_v2 of the same snapshot: its number and its invested-assets details."""
    previous = data['DIVERSIFICATION_DATA'].get('risk_progress_v2')
    if previous is None:
        return [], []
    try:
        from analytics.holy_grail.risk_progress import validate_saved_risk_progress_v2
        valid = bool(validate_saved_risk_progress_v2(previous, data, v2, expected, v2_validated=True))
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        valid = False
    shown = valid and previous.get('status') in {'modeled', 'provisional'}
    title = 'Ризиковий прогрес v2 (risk_progress_v2: лише інвестовані активи, 100 = 15 потоків)'
    if not shown:
        return [(title, 'Недоступно')], []
    number = [(title, f"{_headline(previous)} зі 100; еквівалент {_streams(previous['windows']['m60']['effective_streams'])}")]
    details = [('Ринкова частина', 'Рядки нижче - з risk_progress_v2 того самого знімка: лише інвестовані активи, без приватних потоків.')]
    details += _worst_rows(previous.get('stress'), definitions) + _writeoff_rows(previous.get('stress'))
    details += _volatility_rows(previous.get('sensitivity')) + _comparison_rows(previous.get('sensitivity'))
    return number, details


def risk_progress_v3_view(view, data, v2, expected, saved_at_utc=None):
    """Fill `view` from the saved risk_progress_v3 record; `v2` is the already replayed capital record."""
    record = data['DIVERSIFICATION_DATA']['risk_progress_v3']
    try:
        from analytics.holy_grail.risk_progress_v3 import validate_saved_risk_progress_v3
        valid = bool(validate_saved_risk_progress_v3(record, data, v2, expected, v2_validated=True))
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
            headline, reason = 'Недоступно', 'збережений запис risk_progress_v3 не відтворюється зі збережених входів'
        elif record['status'] == 'not_applicable':
            headline, reason = 'Не застосовується', 'немає інвестованої частини'
        else:
            headline, reason = 'Недоступно', _reason(record.get('reason'))
        rows = [('Метод', METHOD), ('Статус', headline + ': ' + reason), ('Дата позицій', stamp)] + safeguard_rows
        view.update(headline=headline, sheet_number=headline, score_cell=headline, status=headline, sheet_status=headline,
                    model_status=headline, rows=rows, largest_text='-', sensitivity_text='-', drivers=[],
                    sheet_summary=[('Диверсифікація портфеля', headline), ('Висновок', headline + ': ' + reason),
                                   ('Cash поза оцінкою', cash_text)] + list(view['safeguard_summary']))
        return view

    main = record['windows']['m60']
    streams = main['effective_streams']
    car_proxy = (record.get('coverage') or {}).get('car_proxy')
    label = _labeler(record, definitions)
    order, risk_rows = _risk_rows(main, label)
    top = [s for s in order if main['risk_share'][s] > 0][:2]
    contributions = ' · '.join(f"{label(s)} {_share(main['capital_weights'][s])} капіталу → "
                               f"{_share(main['risk_share'][s])} ризику" for s in top)
    provisional = record['status'] == 'provisional'
    reasons = _quality_reasons(record)
    parts = ['до ' + _stamp(main['window_end'])] + (['ретроспективний розрахунок'] if record.get('retrospective') else [])
    parts.append('Якість даних: ' + ('; '.join(reasons) if reasons else 'без додаткових застережень'))
    data_line = ' · '.join(parts)
    assumption = _assumption(record, car_proxy)
    score_text = f"≈{_headline(record)}/100 · {SCALE}; зараз еквівалент ≈{_streams7(streams)}"
    lead = [('Диверсифікація портфеля', score_text), ('Найбільший модельний внесок у ризик', contributions),
            ('Припущення', assumption)]
    model = 'Попередня модельна оцінка' if provisional else 'Модельна оцінка'
    status_label = model + (' · приватні потоки за моделлю' if 'modeled_private_assumptions' in record['warnings'] else '') \
        + (' · автобізнес через проксі' if car_proxy else '')
    # Same labels and order as the risk_progress_v2 summary (the sheet writer owns rows by label).
    summary = [(lead[0][0], _headline(record))] + [('Висновок', status_label)] + lead[1:] \
        + [('Дані', data_line), ('Кеш поза оцінкою', cash_text)] + list(view['safeguard_summary'])
    reduction = main.get('volatility_reduction_pct')
    number_rows, market_rows = _market_rows(data, v2, expected, definitions)
    groups = [s for s in order if not s.startswith((PROXY_PREFIX, PRIVATE_PREFIX))]
    proxies = [s for s in order if s.startswith(PROXY_PREFIX)]
    symbols = (record.get('model') or {}).get('proxies') or {}
    rows = [('Метод', METHOD), ('Оцінка', f"≈{_headline(record)} зі 100 ({_num(_detail(record))} у деталях)"),
            ('Шкала', SCALE + '; ціль для приватного інвестора без шортів, плеча і хедж-фондових стратегій'),
            ('Модель', 'Інвестовані групи - за історіями їхніх представників; приватні активи - модель за публічними '
                       'параметрами (analytics/models/private_streams_v1.json): ринкові фактори та спільний ризик країни, '
                       'класу й локації; біржові проксі - за історіями кошиків; ваги поточного знімка і задекларованих '
                       'вартостей застосовано до всього вікна.'
                       + (' Автобізнес - через рівноваговий кошик CPRT/KMX/OPLN (не ваш бізнес).' if car_proxy else '')),
            ('Якість даних', '; '.join(reasons) if reasons else 'без додаткових застережень'),
            ('Вікно 60 місяців', f"{_stamp(main['window_start'])} - {_stamp(main['window_end'])}; {main['observations']} спостережень"),
            *_shrinkage_rows(main.get('shrinkage')),
            ('Інтерпретація', f"Модельний ефект диверсифікації еквівалентний приблизно {_streams7(streams)} однакового "
                              f"незалежного потоку. Модельне зниження волатильності відносно тих самих потоків із повною "
                              f"позитивною кореляцією: {_num(reduction)}%. Це політика шкали, не гарантія меншого майбутнього "
                              f"ризику і не прибутковість." if reduction is not None else 'Недоступно'),
            *_scenario_rows(record.get('scenarios')), *_gain_rows(record.get('private_gain')), *_source_rows(record),
            ('Cash від повного портфеля', _pct(cash))] + safeguard_rows
    if 'hedge_driven_count' in (main.get('flags') or []):
        rows.append(('Хеджування', QUALITY['hedge_driven_count']))
    rows.extend(risk_rows)
    rows.extend(_window36_rows(record))
    rows.extend(market_rows)
    rows.extend(number_rows)
    rows.extend(_older_rows(data, v2, expected, definitions)[:-1])
    rows.append(('Порівняння методик', 'Бал порівнюють лише в межах тієї самої методики (risk_progress_v3); на межі методик '
                                       'показується «Змінено методику», а не динаміка.'))
    rows.extend(_input_rows(v2, definitions, groups))
    rows.extend(('Представник: ' + label(s), '/'.join((symbols.get(s[len(PROXY_PREFIX):]) or {}).get('symbols') or []))
                for s in proxies)
    rows.append(('Метод', 'Історичні кореляції та модельні припущення не гарантують майбутньої стійкості або прибутку.'))
    from analytics.holy_grail.car.resale_market import conclusion_note
    view.update(headline=f'≈{_headline(record)}/100', sheet_number=_headline(record), score_cell=_headline(record),
                status=status_label, sheet_status=status_label, model_status=model, rows=rows, largest_text=contributions,
                sensitivity_text=assumption, drivers=[f'{name}: {value}' for name, value in lead] + [f'Дані: {data_line}'],
                sheet_summary=summary,
                risk_facts=list((safeguards or {}).get('breach_facts') or []) + risk_fact_rows(v2)[1][:3],
                warnings=reasons, principal_constraint=' '.join(reasons),
                conclusion_note=conclusion_note(record, data.get('CAR_RESALE_MARKET_CONTEXT'), saved_at_utc,
                                                [f'{name}: {value}' for name, value in lead] + ['Дані: ' + data_line]))
    return view
