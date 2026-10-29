"""Public whitelist for one saved capital diversity score. No market collection."""
import math

from analytics.allocation_inputs import validate_saved_allocation

LABELS = ('Концентрований','Частково диверсифікований','Добре диверсифікований у межах моделі')
WARNINGS = {
    'cash_liabilities_outside_scope':'Особистий борг та облікова корекція у Cash перебувають поза оцінкою інвестованої частини. Від’ємний брокерський або інвестиційний cash блокує оцінку.',
    'partial_or_cached_valuations':'Частина збережених балансів неповна, застаріла або має іншу дату.',
    'partial_pair_history':'Для окремих пар доступні 36-59 місяців або історія відстає від дати портфеля.',
    'unknown_profiles':'Нерозпізнані позиції залишені у вагах і не отримують бонусу незалежності.',
    'unknown_correlations':'Невідомі кореляції консервативно прийняті рівними 1.',
    'unknown_sectors':'Невідома секторна частка додана до найбільшого відомого сектора.',
    'confirmed_ai_theme':'Є підтверджена AI-тема: різні сектори можуть мати спільний тематичний ризик.',
    'invalid_calibration':'Калібрування пошкоджене або не відповідає контрольним сценаріям.',
    'insufficient_coverage':'Непокрита частка перевищує 5% або вплив невідомих кореляцій перевищує 5 пунктів.',
    'unsupported_risk':'Короткі, нелінійні або позикові позиції не підтримуються цією моделлю.',
    'unsupported_borrowing':'Виявлено позиковий залишок; ця модель не підтримує кредитне плече.',
    'unreconciled_valuations':'Суми збережених позицій не узгоджуються з NAV.',
    'unreconciled_positions':'Частина фінансового підсумку не розкладена на позиції.',
    'invalid_valuation':'Некоректні вартості позицій.',
    'invalid_inputs':'Некоректні або неповні входи індикатора.',
}


def _pct(value):
    return '<0,1%' if 0 < value < .1 else f'{value:.1f}%'.replace('.',',')


def group_label(identifier, definitions):
    return definitions.get(identifier,{}).get('label','Непокриті позиції')


def _num(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def country_share(facts, name='china'):
    for key, value in (facts.get('country_pct_equities') or {}).items():
        if str(key).lower() == name:
            return value
    return None


def _points(value):
    return str(int(math.floor(value + 1e-8))) if value >= 0 else str(int(math.ceil(value - 1e-8)))


SAFEGUARD_LABELS = {
    'issuer_limit_breached': 'Емітент понад ліміт',
    'core_below_target': 'Core нижче цілі',
    'country_limit_breached': 'Китай понад ліміт',
    'thesis_limit_breached': 'Теза понад ліміт',
    'unresolved_breach': 'Нерозглянуте порушення ліміту',
    'unknown_issuer_lookthrough': 'Частка емітентів у фондах не підтверджена',
    'business_assumption_material': 'Бізнес-допущення суттєве для оцінки',
    'concentration_block_invalid': 'введені дані не пройшли перевірку цілісності',
}
DECISION_TEXT = {'accept': 'рішення: прийнято', 'reduce': 'рішення: скоротити', 'exit': 'рішення: вийти'}
THESIS_KEY = 'thesis_pct_equities'


def _concentration(section):
    """Structural read of the sibling `concentration_v1` block; malformed degrades to None."""
    from analytics.concentration_v1 import VERSION
    try:
        block = section.get('concentration_v1')
        if not isinstance(block, dict) or block.get('version') != VERSION:
            return None
        if block.get('status') == 'unavailable':
            return {'unavailable': True, 'warnings': [str(w) for w in block.get('warnings') or []]}
        facts, limits = block['facts'], block['limits']
        if not isinstance(facts, dict) or not isinstance(limits, dict):
            return None
        largest, top4 = facts['largest_issuer'], facts['top4_issuers']
        raw_id = largest['id'] if isinstance(largest['id'], str) else str(largest['id'])
        issuer_id = raw_id.split(':', 1)[1] if raw_id.startswith('ib:') else raw_id
        shares = dict(issuer_id=issuer_id, issuer_pct_equities=largest['pct_equities'],
                      issuer_pct_nav=largest['pct_nav'], top4_pct_equities=top4['pct_equities'],
                      top4_ids=[str(i) for i in top4.get('ids') or []],
                      core_pct_equities=facts['core_pct_equities'], china_pct_equities=country_share(facts),
                      unknown_lookthrough_pct_equities=facts.get('unknown_lookthrough_pct_equities'),
                      business_pct_invested=facts.get('business_pct_invested'),
                      score_excluding_car=facts.get('score_excluding_car'),
                      thesis_pct_equities={str(k): v for k, v in (facts.get(THESIS_KEY) or {}).items()})
        for key in ('issuer_pct_equities','top4_pct_equities','core_pct_equities'):
            if not _num(shares[key]): return None
        for key in ('issuer_pct_nav','china_pct_equities','unknown_lookthrough_pct_equities',
                    'business_pct_invested','score_excluding_car'):
            if shares[key] is not None and not _num(shares[key]): return None
        if any(not _num(v) for v in shares['thesis_pct_equities'].values()): return None
        for key, limit in limits.items():
            if key == THESIS_KEY:
                if not isinstance(limit, dict) or any(not _num(v) for v in limit.values()): return None
            elif not _num(limit): return None
        breaches = [dict(limit=item['limit'], value=item['value'], decision_id=item.get('decision_id'))
                    for item in block.get('breaches') or []
                    if isinstance(item, dict) and isinstance(item.get('limit'), str) and _num(item.get('value'))]
        return dict(unavailable=False, limits=limits, shares=shares, breaches=breaches,
                    warnings=[str(w) for w in block.get('warnings') or []])
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def concentration_section(section, decisions=None, as_of_date=None):
    """Safeguard rows, sheet rows and uncapped breach facts from the saved block.

    Returns None when no block is saved (today's render exactly) or when the
    block is malformed; an unavailable block renders one explicit row.
    """
    block = _concentration(section)
    if block is None:
        return None
    warn_labels = dict(SAFEGUARD_LABELS)
    if block['unavailable']:
        note = 'Вимірювання концентрації недоступне'
        named = block['warnings'][:2]
        if named:
            note += ': ' + ', '.join(warn_labels.get(w, w) for w in named)
        return dict(unavailable=note, rows=[('Концентрація', note)], summary=[('Концентрація', note)], breach_facts=[])
    shares, limits = block['shares'], block['limits']
    decisions = decisions or {}

    def decision_text(item):
        record = (decisions or {}).get(item.get('decision_id')) if item.get('decision_id') else None
        if isinstance(record, dict) and str(record.get('review_by') or '') >= str(as_of_date or ''):
            text = DECISION_TEXT.get(str(record.get('decision')), 'рішення записане')
            stamp = str(record.get('review_by') or '')
            return text + ('; розгляд ' + '.'.join(reversed(stamp.split('-'))) if stamp else '')
        return 'нерозглянуто'

    def resolved(item):
        return decision_text(item) != 'нерозглянуто'

    def limit_for(key):
        if key in limits and key != THESIS_KEY:
            return limits[key], LIMIT_LABELS.get(key, key)
        name = key.split(':', 1)[1] if ':' in key else key.split('.', 1)[1] if '.' in key else None
        theses = limits.get(THESIS_KEY) or {}
        if name and name in theses:
            return theses[name], 'Теза ' + name
        return limits.get(key), LIMIT_LABELS.get(key, key)

    breach_rows, breach_facts = [], []
    for item in sorted(block['breaches'], key=lambda item: 0 if not resolved(item) else 1):
        limit, label = limit_for(item['limit'])
        minimal = limit is not None and item.get('limit') == 'core_min_pct_equities'
        nav = item.get('limit') == 'issuer_pct_nav'
        against = _pct(limit) if limit is not None else ''
        suffix = ' NAV' if nav else ''
        value_text = (_pct(item['value']) + suffix + ' нижче цілі ' + against if minimal
                      else _pct(item['value']) + suffix + ' понад ліміт ' + against + suffix)
        text = value_text + ' · ' + decision_text(item)
        breach_rows.append(('Порушення: ' + label, text))
        breach_facts.append('Порушення ліміту: ' + label + ' ' + text)

    rows = list(breach_rows)
    issuer = f"{shares['issuer_id']}: {_pct(shares['issuer_pct_equities'])} акцій"
    if shares['issuer_pct_nav'] is not None:
        issuer += ' / ' + _pct(shares['issuer_pct_nav']) + ' NAV'
    limit_issuer = limits.get('issuer_pct_equities')
    if limit_issuer is not None:
        issuer += ' · ліміт ' + _pct(limit_issuer)
        if limits.get('issuer_pct_nav') is not None:
            issuer += ' / ' + _pct(limits['issuer_pct_nav']) + ' NAV'
    rows.append(('Концентрація - емітент', issuer))
    if shares['core_pct_equities'] is not None:
        rows.append(('Концентрація - core',
                     _pct(shares['core_pct_equities']) + ' акцій · ціль ≥' + _pct(limits.get('core_min_pct_equities', 50))))
    if shares['top4_pct_equities'] is not None:
        rows.append(('Концентрація - топ-4',
                     _pct(shares['top4_pct_equities']) + ' акцій у чотирьох найбільших · ліміт ' +
                     _pct(limits.get('top4_pct_equities', 20)) + ' (' + ', '.join(shares['top4_ids'][:4]) + ')'))
    if shares['china_pct_equities'] is not None:
        rows.append(('Концентрація - Китай',
                     _pct(shares['china_pct_equities']) + ' акцій · ліміт ' + _pct(limits.get('country_pct_equities_china', 10))))
    for name, value in sorted(shares['thesis_pct_equities'].items()):
        thesis_limit = (limits.get(THESIS_KEY) or {}).get(name)
        rows.append(('Концентрація - теза ' + name,
                     _pct(value) + ' акцій · ліміт ' + _pct(thesis_limit) if thesis_limit is not None else _pct(value) + ' акцій'))
    if shares['unknown_lookthrough_pct_equities']:
        rows.append(('Look-through не підтверджено', _pct(shares['unknown_lookthrough_pct_equities']) + ' акцій у фондах'))
    if shares['business_pct_invested'] is not None:
        rows.append(('Бізнес у інвестованій частині', _pct(shares['business_pct_invested'])))
    if shares['score_excluding_car'] is not None:
        rows.append(('Бал ігноруючи бізнес-допущення', _points(shares['score_excluding_car']) + ' зі 100'))
    existing = {text for _, text in rows}
    for warning in block['warnings']:
        label = warn_labels.get(warning, warning)
        if label not in existing:
            rows.append(('Обмеження', label))
    summary = [('Концентрація',
                'Ліміти дотримані' if not block['breaches'] else
                'Порушень: ' + str(len(block['breaches'])) + '; нерозглянутих: ' +
                str(sum(1 for item in block['breaches'] if not resolved(item)))),
               ('Емітент', issuer.split(' · ліміт')[0]),
               ('Топ-4 / Core', _pct(shares['top4_pct_equities']) + ' / ' + _pct(shares['core_pct_equities']) + ' акцій'),
               ('Китай', (_pct(shares['china_pct_equities']) if shares['china_pct_equities'] is not None else '-') + ' акцій')]
    return dict(unavailable=None, rows=rows, summary=summary, breach_facts=breach_facts)


LIMIT_LABELS = {'issuer_pct_equities': 'Емітент', 'issuer_pct_nav': 'Емітент / NAV', 'top4_pct_equities': 'Топ-4',
                'core_min_pct_equities': 'Core', 'country_pct_equities_china': 'Китай'}


def allocation_view(data, expected_date=None):
    from analytics.diversification_view import _empty
    q=data['DIVERSIFICATION_DATA']['allocation_score']
    expected=expected_date or str(data.get('POSITION_DATA',{}).get('as_of_date')
        or data.get('DATA_METADATA',{}).get('last_updated') or '')[:10]
    view=_empty('Некоректна або неузгоджена збережена оцінка')
    view.update(allocation=True,indicator=True,headline='Дані недоступні',sheet_number='Дані недоступні',
                title='Диверсифікація інвестованої частини',drivers=[],coverage_summary='',
                sensitivity_text='Не застосовується',largest_text='-',rows=[])
    if not validate_saved_allocation(q,data,expected,replay=False):
        view['rows']=[('Статус',view['status'])]
    else:
        definitions=q.get('configuration',{}).get('group_definitions',{})
        label_for=lambda identifier:group_label(identifier,definitions)
        stamp='.'.join(reversed(q['as_of_date'].split('-')))
        warnings=[WARNINGS.get(w,'Некоректні або неповні входи індикатора.') for w in q['warnings']]
        cash=q['coverage'].get('cash_pct_nav')
        view.update(as_of=stamp,warnings=warnings,principal_constraint=' '.join(warnings),
                    coverage_summary='Cash поза оцінкою: '+(_pct(cash) if cash is not None else '-')+' повного портфеля.')
        if q['status'] in {'unavailable','not_applicable'}:
            headline='Не застосовується' if q['status']=='not_applicable' else 'Дані недоступні'
            view.update(headline=headline,sheet_number=headline,status=headline,
                        rows=[('Статус',headline),('Обмеження',' '.join(warnings)),('Дата позицій',stamp)])
        else:
            displayed=q['display_score'];label=LABELS[0 if displayed<50 else 1 if displayed<80 else 2]
            groups=sorted(q['groups'],key=lambda g:-g['weight'])
            largest=groups[0]
            largest_text=label_for(largest['id'])+': '+_pct(largest['weight']*100)
            drivers=['Найбільша група: '+largest_text+' інвестованої частини.']
            pairs=sorted((p for p in q['pairs'] if p['kind']=='measured' and p['correlation']>0),
                         key=lambda p:-2*next(g['weight'] for g in groups if g['id']==p['left'])*
                             next(g['weight'] for g in groups if g['id']==p['right'])*p['correlation'])
            if pairs:
                top=pairs[0]
                drivers.append('Найбільший зважений перетин: '+label_for(top['left'])+' / '+label_for(top['right'])+
                               f"; кореляція {top['correlation']:.2f}".replace('.',',')+'.')
            sensitivity='Не застосовується' if q['sensitivity_display_score'] is None else str(q['sensitivity_display_score'])+'%'
            if q['sensitivity_display_score'] is not None:
                drivers.append('Якщо кореляція Car Resale з ринками 0,75 замість 0,25: '+sensitivity+'. Обидва значення є припущеннями.')
            rows=[('Шкала','0-49%: концентрований; 50-79%: частково; 80-100%: добре диверсифікований у межах моделі.'),
                  ('Оцінювана частина','Інвестований капітал; Cash поза оцінкою.'),
                  ('Вікно історій',q['window_start']+' - '+q['window_end']),
                  ('Калібрування','Жовтень 2021 - вересень 2026; коефіцієнт зафіксований.'),
                  ('Взірець 100%','По 1/6: акції США; інші акції (EFA/MCHI); Treasury (SHV/TLT); золото; товари; Car Resale.'),
                  ('Модель бізнесу 0,75',sensitivity),('Cash від повного портфеля',_pct(cash)),
                  ('Непокрита інвестована частка',_pct(q['coverage']['unknown_pct_invested'])),
                  ('Максимальний вплив невідомих кореляцій',f"{q['coverage']['missing_pair_max_points']:.2f}".replace('.',',')+' п.п.')]
            rows.extend((label_for(g['id']),_pct(g['weight']*100)+' інвестованої частини') for g in groups)
            for g,profile in q['sectors'].items():
                rows.append(('Сектори: '+label_for(g),'; '.join(k+': '+_pct(v*100) for k,v in sorted(profile.items(),key=lambda i:-i[1])) or 'Не розкриті'))
            for p in pairs[:3]:
                rows.append(('Кореляційний перетин',label_for(p['left'])+' / '+label_for(p['right'])+
                    f": r={p['correlation']:.2f}; {p['observations']} місяців; останній {p['last_month']}".replace('.',',')))
            observed=[p for p in q['pairs'] if p['kind']=='measured']
            if observed:
                rows.append(('Спостереження для всіх виміряних пар',
                    f"{min(p['observations'] for p in observed)}-{max(p['observations'] for p in observed)} місяців; останні дати "+
                    min(p['last_month'] for p in observed)+' - '+max(p['last_month'] for p in observed)))
            profile_dates=sorted({p['definition']['as_of_date'] for p in q['profiles']})
            if profile_dates: rows.append(('Дати економічних профілів',profile_dates[0]+' - '+profile_dates[-1]))
            rows.append(('Джерела','Скориговані місячні ринкові історії в USD; датовані профілі фондів/емітентів. Приватні підтвердження залишаються у збережених входах.'))
            for g in groups:
                representative=definitions.get(g['id'],{}).get('representative')
                if representative:
                    rows.append(('Представник: '+label_for(g['id']),representative))
            rows.extend(('Обмеження',w) for w in warnings)
            rows.append(('Інтерпретація','Більше = краща диверсифікація в межах моделі. 100% - погоджений взірець, не гарантія захисту, прибутку або офіційний рейтинг Даліо.'))
            rows.append(('Моделі','Кореляції економічних груп оцінені через їхніх ринкових представників. Lending/P2P об’єднані з USD high yield; Car Resale є моделлю бізнесу.'))
            view.update(headline=str(displayed)+'%',sheet_number=displayed/100,score_cell=displayed/100,
                        status=label,sheet_status=label,model_status='Попередня модельна оцінка' if q['status']=='provisional' else 'Модельна оцінка',
                        drivers=drivers[:3],rows=rows,largest_text=largest_text,sensitivity_text=sensitivity)
    view['sheet_summary']=[('Диверсифікація інвестованої частини',view['sheet_number']),('Висновок',view['status']),
                           ('Найбільша група',view['largest_text']),('Модель бізнесу 0,75',view['sensitivity_text']),
                           ('Дата / Cash поза оцінкою',view['as_of']+' / '+view['coverage_summary'])]
    return view


def sheet_detail_rows(rows):
    """Keep pair observations together without consuming one sheet row per pair."""
    packed = []
    pairs = []
    def flush():
        if pairs:
            packed.append(('Історія пар', '\n'.join(pairs)))
            pairs.clear()
    for label, value in rows:
        if label == 'Історія пар':
            pairs.append(value)
            if len(pairs) == 6:
                flush()
        else:
            flush()
            packed.append((label, value))
    flush()
    return packed


def allocation_view_v2(data, expected_date=None):
    """Present only whitelisted fields from a fully replayed v2 record."""
    from analytics.allocation_v2_inputs import validate_saved_allocation_v2
    from analytics.diversification_view import _empty
    result = data['DIVERSIFICATION_DATA']['allocation_score_v2']
    expected = expected_date or str(data.get('POSITION_DATA', {}).get('as_of_date')
                                    or data.get('DATA_METADATA', {}).get('last_updated') or '')[:10]
    view = _empty('Некоректна або неузгоджена збережена оцінка')
    view.update(allocation=True, indicator=True, title='Диверсифікація інвестованого капіталу',
                number_kind='allocation_points', number_format={'type': 'NUMBER', 'pattern': '0" зі 100"'},
                sheet_number='Дані недоступні', drivers=[], coverage_summary='', largest_text='-',
                sensitivity_text='-', rows=[], risk_facts=[])
    if not validate_saved_allocation_v2(result, data, expected, replay=True):
        view['rows'] = [('Статус', view['status'])]
    else:
        stamp = '.'.join(reversed(result['as_of_date'].split('-')))
        cash = result['coverage'].get('cash_pct_nav')
        coverage = 'Cash поза оцінкою: ' + (_pct(cash) if cash is not None else '-') + ' повного портфеля.'
        warnings = [WARNINGS.get(w, 'Некоректні або неповні входи індикатора.') for w in result['warnings']]
        view.update(as_of=stamp, warnings=warnings, principal_constraint=' '.join(warnings), coverage_summary=coverage)
        if result['status'] in {'unavailable', 'not_applicable'}:
            headline = 'Не застосовується' if result['status'] == 'not_applicable' else 'Дані недоступні'
            view.update(headline=headline, sheet_number=headline, status=headline,
                        rows=[('Статус', headline), ('Обмеження', ' '.join(warnings)), ('Дата позицій', stamp)])
        else:
            assessment = result['assessment']
            if assessment['combined_dependent'] or (assessment['business_dependent'] and assessment['window_dependent']):
                label = 'Оцінка залежить від припущень і періоду'
            elif assessment['business_dependent']:
                label = 'Оцінка залежить від припущень'
            elif assessment['window_dependent']:
                label = 'Оцінка залежить від періоду'
            else:
                label = {'concentrated': LABELS[0], 'partly_diversified': LABELS[1],
                         'well_diversified': LABELS[2]}[result['category']]
            if assessment['combined_dependent'] or assessment['business_dependent'] or assessment['window_dependent']:
                scored = [(key, scenario) for key, scenario in result['scenarios'].items()
                          if scenario.get('display_score') is not None]
                if scored:
                    worst_key, worst = min(scored, key=lambda item: (item[1]['display_score'], item[0]))
                    when = ('при бізнесовій кореляції 0,75' if worst_key.endswith('_r075') else
                            'при бізнесовій кореляції 0,25' if worst_key.endswith('_r025') else
                            'за 36-місячним вікном' if worst_key.startswith('m36') else 'за 60-місячним вікном')
                    worst_label = {'concentrated': LABELS[0], 'partly_diversified': LABELS[1],
                                   'well_diversified': LABELS[2]}[worst['category']]
                    label = worst_label + ' ' + when + ' · ' + label
            if result['status'] == 'provisional': label += ' · Попередня оцінка'
            groups = sorted(result['groups'], key=lambda item: (-item['weight'], item['id']))
            definitions = result['configuration']['group_definitions']
            largest = group_label(groups[0]['id'], definitions) + ': ' + _pct(groups[0]['weight'] * 100)
            scenario_range = f"{assessment['min_display']}-{assessment['max_display']} зі 100"
            if assessment['available'] != assessment['expected']:
                scenario_range += f" ({assessment['available']}/{assessment['expected']} доступні)"
            rows = [('Метод', 'capital_diversification_v2'), ('Оцінка', str(result['display_score']) + ' зі 100'),
                    ('Висновок', label), ('Сценарний розкид', scenario_range),
                    ('Cash від повного портфеля', _pct(cash)),
                    ('Непокрита інвестована частка', _pct(result['coverage']['unknown_pct_invested']))]
            section = data['DIVERSIFICATION_DATA']
            block = section.get('concentration_v1')
            from analytics.concentration_v1 import (unavailable_block, validate_saved_concentration,
                                                    VERSION as CONCENTRATION_VERSION)
            if (isinstance(block, dict) and block.get('version') == CONCENTRATION_VERSION
                    and 'status' not in block
                    and not validate_saved_concentration(block, data, result)):
                # A stale or tampered sibling must not render its verdicts with the
                # valid v2 score; degrade the safeguards, keep the score.
                section = dict(section, concentration_v1=unavailable_block(
                    result['as_of_date'], ['concentration_block_invalid']))
            safeguards = concentration_section(section,
                                               result['configuration'].get('concentration_decisions'),
                                               result['as_of_date'])
            if safeguards:
                rows.extend(safeguards['rows'])
            for key, scenario in result['scenarios'].items():
                value = str(scenario['display_score']) + ' зі 100' if scenario['score'] is not None else 'Недоступно: ' + str(scenario['reason'])
                rows.append(('Сценарій ' + key, value))
            rows.extend((group_label(group['id'], definitions), _pct(group['weight'] * 100)) for group in groups)
            for group in groups:
                representative = definitions.get(group['id'], {}).get('representative')
                if representative:
                    rows.append(('Представник: ' + group_label(group['id'], definitions), representative))
            rows.append(('Формула', '100 × T + 25 × min(E × b, 1 − T); T = clip((1/C − 1)/5, 0, 1).'))
            for group, sectors in sorted(result['sectors'].items()):
                rows.append(('Сектори: ' + group_label(group, definitions),
                             '; '.join(name + ': ' + _pct(share * 100) for name, share in sorted(sectors.items())) or 'Не підтверджено'))
            main = result['scenarios']['m60_r025' if 'm60_r025' in result['scenarios'] else 'm60']
            for pair in main['pairs']:
                names = group_label(pair['left'], definitions) + ' / ' + group_label(pair['right'], definitions)
                if pair['kind'] == 'measured':
                    detail = f"{pair['observations']} місяців; останній {pair['last_month']}; r={pair['correlation']:.2f}".replace('.', ',')
                elif pair['kind'] == 'modeled':
                    detail = 'Модельна кореляція ' + str(pair['correlation']).replace('.', ',')
                else:
                    detail = 'Немає придатної пари; консервативно r=1'
                rows.append(('Історія пар', names + ': ' + detail))
            rows.append(('Модель', '60 і 36 календарних місяців; бізнес: 0,25 / 0,75; невідомі пари: r=1.'))
            comparison = result['comparison']
            if comparison['status'] == 'available':
                rows.append(('Порівняння', 'Ринки: {:+.2f}; позиції: {:+.2f}; разом: {:+.2f} пункту'.format(
                    comparison['market_relationship_change'], comparison['positions_and_profiles_change'], comparison['total_change']).replace('.', ',')))
                rows.append(('Порівняння', 'Внески відтворено зі збережених входів; відбитки джерела не підтверджені без оригіналу.'))
            else:
                rows.append(('Порівняння', 'Недоступно: ' + str(comparison.get('reason', 'невідомо'))))
            risk_labels = {'treasury_short': 'Treasury до 1 року', 'treasury_medium': 'Treasury понад 1-10 років',
                           'treasury_long': 'Treasury понад 10 років', 'credit_lending': 'Кредит та lending',
                           'business': 'Приватний бізнес', 'business_ukraine': 'Бізнес в Україні', 'economic_fx': 'Валютна експозиція',
                           'counterparty': 'Залежність від контрагентів', 'illiquidity': 'Обмежена ліквідність',
                           'confirmed_ai_theme': 'Підтверджена AI-тема'}
            facts = sorted((item for item in result.get('risk_facts', []) if item['id'] in risk_labels),
                           key=lambda item: (-item['affected_pct_nav'], item['id']))
            public_facts = [risk_labels[item['id']] + ': ' + _pct(item['affected_pct_nav']) + ' NAV' for item in facts]
            rows.extend(('Фактичний ризик', fact) for fact in public_facts)
            for detail in result.get('risk_details', []):
                duration = f"{detail['rate_duration']:.1f}".replace('.', ',')
                maturity = detail['maturity'] or 'не підтверджено'
                rows.append(('Підтверджена duration', duration + ' року; погашення: ' + maturity + '; ' + _pct(detail['affected_pct_nav']) + ' NAV'))
            for key, unknown_label in [('duration_pct_nav', 'Duration не підтверджено'),
                               ('counterparty_pct_nav', 'Контрагенти не підтверджені'),
                               ('liquidity_pct_nav', 'Ліквідність не підтверджена'),
                               ('business_geography_pct_nav', 'Географія бізнесу не підтверджена'),
                               ('economic_fx_pct_nav', 'Економічна валютна експозиція не підтверджена')]:
                if result.get('risk_unknown', {}).get(key, 0) > 0:
                    rows.append(('Невідомо', unknown_label + ': ' + _pct(result['risk_unknown'][key]) + ' NAV'))
            rows.extend(('Обмеження', warning) for warning in warnings)
            rows.append(('Метод', 'Історичні кореляції та модельні припущення не гарантують майбутньої стійкості або прибутку.'))
            label += ' · Details'
            view.update(headline=str(result['display_score']) + ' зі 100', score_cell=result['display_score'],
                        sheet_number=result['display_score'], status=label, sheet_status=label,
                        largest_text=largest, sensitivity_text=scenario_range, rows=rows,
                        drivers=['Найбільша група: ' + largest],
                        risk_facts=((safeguards or {}).get('breach_facts') or []) + public_facts[:3],
                        safeguard_summary=(safeguards or {}).get('summary') or [],
                        model_status='Попередня оцінка' if result['status'] == 'provisional' else 'Модельна оцінка')
    view['sheet_summary'] = [('Диверсифікація інвестованого капіталу', view['sheet_number']),
                             ('Висновок', view['status']), ('Найбільша група', view['largest_text']),
                             ('Сценарний розкид', view['sensitivity_text']),
                             ('Дата / Cash поза оцінкою', view['as_of'] + ' / ' + view['coverage_summary'])] + \
                            list(view.get('safeguard_summary') or [])
    return view
