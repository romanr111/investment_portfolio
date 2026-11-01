"""Public whitelist for one saved capital diversity score. No market collection."""
import math

from analytics.allocation_inputs import validate_saved_allocation
from analytics.concentration_v1 import decision_display

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
    'invalid_car_category_block':'Блок категорії авто відсутній, пошкоджений або не відповідає даті знімка: показано припущення кореляції 0,25 / 0,75.',
    'category_index_lagged':'Індекс цін вживаних авто ще не опубліковано за останній місяць знімка: кореляції рахуються без нього.',
    'category_pair_unmeasured':'Для частини груп кореляцію з індексом цін вживаних авто виміряти не вдалося: консервативно r=1.',
}


_ISSUER_ALIASES = {
    # canonical aggregation key -> display name (fund-constituent naming uses
    # underscores; canonical keys stay lowercase, only the label is pretty)
    'alphabet': 'Alphabet', 'amazon_com': 'Amazon', 'meta_platforms': 'Meta Platforms',
    'berkshire_hathaway': 'Berkshire Hathaway', 'jpmorgan_chase': 'JPMorgan Chase',
    'micron_technology': 'Micron Technology', 'eli_lilly': 'Eli Lilly',
    'exxonmobil': 'ExxonMobil', 'johnson_and_johnson': 'Johnson & Johnson',
    'nvidia': 'NVIDIA', 'amd': 'AMD', 'microsoft': 'Microsoft', 'apple': 'Apple',
    'tesla': 'Tesla', 'broadcom': 'Broadcom', 'visa': 'Visa',
    'bank_of_america': 'Bank of America', 'american_express': 'American Express',
    'coca_cola': 'Coca-Cola', 'occidental_petroleum': 'Occidental Petroleum',
    'chevron': 'Chevron', 'alibaba': 'Alibaba',
}


def _issuer_display(name):
    """Issuer label for display: canonical aliases first, then capitalize
    lowercase words while keeping acronyms verbatim.

    Aggregation keys stay lowercase; only the rendered label changes
    ('alibaba' -> 'Alibaba', 'amazon_com' -> 'Amazon', 'bank of america' ->
    'Bank of America') while tickers already holding uppercase ('GOOG', '9988')
    pass through verbatim.
    """
    out = []
    for idx, word in enumerate(name.split(' ')):
        core = word.rstrip(',')
        if core in _ISSUER_ALIASES:
            out.append(_ISSUER_ALIASES[core] + word[len(core):])
            continue
        if any(char.isupper() for char in word[1:]):
            out.append(word)  # acronym or already-formatted name, keep verbatim
        elif word[0:1].isalpha() and word[0:1].islower():
            if idx == 0 or word not in {'of', 'and', 'the', 'a'}:
                out.append(word[0].upper() + word[1:])
            else:
                out.append(word)
        else:
            out.append(word)
    return ' '.join(out)


def _pct(value):
    return '<0,1%' if 0 < value < .1 else f'{value:.1f}%'.replace('.',',')


def group_label(identifier, definitions):
    return definitions.get(identifier,{}).get('label','Непокриті позиції')


_PROXY_LABELS = {'manheim_wholesale': 'Manheim (США, гурт)', 'bls_used_retail': 'BLS CPI вживані авто (США, роздріб)',
                 'auto1_wholesale_eu': 'AUTO1 (Європа, гурт)', 'listed_remarketers': 'Акції CPRT/KMX/OPLN (кошик)'}
_RELATIONS = {'not_correlated': 'не корелює', 'moderately_correlated': 'помірно корелює', 'correlated': 'корелює'}
_EFFECTS = {'adds_diversification': 'додає диверсифікацію', 'reduces_diversification': 'знижує диверсифікацію',
            'neutral': 'не змінює диверсифікацію'}


def _floor1(value):
    """One decimal, rounded down, so a displayed count never overstates the computed one."""
    return f'{math.floor(value * 10 + 1e-9) / 10:.1f}'.replace('.', ',')


def _risk_progress_text(record, definitions):
    """Sheet row text and hover-note lines for a replayed risk_progress_v1 record (whitelisted fields)."""
    if record['status'] == 'unavailable':
        return 'Недоступно', []
    main, coverage = record['windows']['m60'], record['coverage']
    target = record['method']['target_streams']
    points = f"{record['progress_display']:.1f}".replace('.', ',')
    parts = [f'{points} зі 100', f"{_floor1(main['effective_streams'])} з {target} потоків",
             f"покрито {_pct(coverage['covered_pct_invested'])}"]
    if record['status'] == 'provisional':
        parts.append('попередньо')
    excluded = ', '.join(f"{group_label(row['id'], definitions)} {_pct(row['weight_pct_invested'])}"
                         for row in coverage['excluded']) or 'немає'
    lines = [f"Ризиковий прогрес: {points} зі 100 = {_floor1(main['effective_streams'])} ефективних незалежних потоків "
             f"ризику з цільових {target} (лінійна шкала 0-100 за політикою, не відсоток ризику). Рахується за покритою "
             f"частиною: {_pct(coverage['covered_pct_invested'])} інвестованого; поза нею: {excluded}; Cash поза оцінкою."]
    scenarios = record.get('car_scenarios')
    if scenarios is None:
        return ' · '.join(parts), lines
    if scenarios['status'] == 'unavailable':
        parts.append('автобізнес не оцінено')
        lines.append('Сценарії автобізнесу недоступні: ' + str(scenarios['reason']))
        return ' · '.join(parts), lines
    span = scenarios['range']
    parts.append(f"з автобізнесом {span['low_display']:.1f}-{span['high_display']:.1f} (припущення"
                 f"{', попередньо' if scenarios['status'] == 'provisional' else ''})".replace('.', ','))
    lines.append(f"Автобізнес ({_pct(scenarios['car_weight_pct_invested'])} інвестованого) у сценаріях \"бізнес поводиться як "
                 f"ряд\", а не вимірювання вашого бізнесу; потоки покритої частини {_floor1(main['effective_streams'])}:")
    for name, item in scenarios['items'].items():
        label = _PROXY_LABELS.get(name, item['label'])
        if item['effective_streams'] is None:
            lines.append(f"{label}: недоступно ({item['reason']})")
            continue
        lines.append((f"{label}: {item['progress_display']:.1f} зі 100, потоків {item['effective_streams']:.2f} "
                      f"({item['delta_streams']:+.2f}); r з покритою частиною {item['correlation_covered']:+.2f} - "
                      f"{_RELATIONS[item['relation']]}, {_EFFECTS[item['effect']]}").replace('.', ','))
    lines.append('Ціновий індекс і біржовий кошик дають різний результат; хто з них ближчий до вашого бізнесу, '
                 'публічні дані не кажуть. Заголовок рахує лише покриту частину.')
    return ' · '.join(parts), lines


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
    'unprofiled_positions': 'Позиції не розпізнані профілями',
    'business_assumption_material': 'Бізнес-допущення суттєве для оцінки',
    'concentration_block_invalid': 'введені дані не пройшли перевірку цілісності',
}
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
        raw_id = largest['id'] if isinstance(largest['id'], str) else 'Немає'
        issuer_id = raw_id.split(':', 1)[1] if raw_id.startswith('ib:') else raw_id
        over_limit = []
        for entry in facts.get('issuers_over_limit') or []:
            if (not isinstance(entry, dict) or not isinstance(entry.get('id'), str)
                    or not _num(entry.get('pct_equities')) or not _num(entry.get('pct_nav'))):
                return None
            over_limit.append(dict(id=entry['id'], pct_equities=entry['pct_equities'],
                                   pct_nav=entry['pct_nav']))
        shares = dict(issuer_id=issuer_id, issuer_pct_equities=largest['pct_equities'],
                      issuer_pct_nav=largest['pct_nav'], top4_pct_equities=top4['pct_equities'],
                      top4_ids=[str(i) for i in top4.get('ids') or []],
                      core_pct_equities=facts['core_pct_equities'], china_pct_equities=country_share(facts),
                      unknown_lookthrough_pct_equities=facts.get('unknown_lookthrough_pct_equities'),
                      business_pct_invested=facts.get('business_pct_invested'),
                      score_excluding_car=facts.get('score_excluding_car'),
                      thesis_pct_equities={str(k): v for k, v in (facts.get(THESIS_KEY) or {}).items()},
                      issuers_over_limit=over_limit)
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
    from analytics.concentration_v1 import ISSUER_EQ_PREFIX, ISSUER_NAV_PREFIX
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
        # Delegation: the display text is the shared one from concentration_v1
        # (no catch-all text for an unreadable record any more).
        record = (decisions or {}).get(item.get('decision_id')) if item.get('decision_id') else None
        return decision_display(record, item, as_of_date) or 'нерозглянуто'

    def resolved(item):
        return decision_text(item) != 'нерозглянуто'

    def limit_for(key):
        if key in limits and key != THESIS_KEY:
            return limits[key], LIMIT_LABELS.get(key, key)
        for prefix, plain, suffix in ((ISSUER_EQ_PREFIX, 'issuer_pct_equities', ''),
                                      (ISSUER_NAV_PREFIX, 'issuer_pct_nav', ' / NAV')):
            if key.startswith(prefix):
                return limits.get(plain), 'Емітент ' + _issuer_display(key[len(prefix):]) + suffix
        name = key.split(':', 1)[1] if ':' in key else key.split('.', 1)[1] if '.' in key else None
        theses = limits.get(THESIS_KEY) or {}
        if name and name in theses:
            return theses[name], 'Теза ' + name
        return limits.get(key), LIMIT_LABELS.get(key, key)

    breach_rows, breach_facts, breach_summary_items = [], [], []
    sorted_items = sorted(block['breaches'], key=lambda item: 0 if not resolved(item) else 1)

    def subject_of(item):
        limit = item['limit']
        if limit.startswith(ISSUER_EQ_PREFIX):
            return ('issuer', limit[len(ISSUER_EQ_PREFIX):])
        if limit.startswith(ISSUER_NAV_PREFIX):
            return ('issuer', limit[len(ISSUER_NAV_PREFIX):])
        return (None, limit)

    groups, by_subject = [], {}
    for item in sorted_items:
        key = subject_of(item)
        if key not in by_subject:
            by_subject[key] = []
            groups.append(key)
        by_subject[key].append(item)
    for subject_key in groups:
        items = by_subject[subject_key]
        if subject_key[0] is None:
            item = items[0]
            limit, label = limit_for(item['limit'])
            minimal = limit is not None and item.get('limit') == 'core_min_pct_equities'
            nav = item.get('limit') == 'issuer_pct_nav'
            against = _pct(limit) if limit is not None else ''
            suffix = ' NAV' if nav else ''
            value_text = (_pct(item['value']) + suffix + ' нижче цілі ' + against if minimal
                          else _pct(item['value']) + suffix + ' понад ліміт ' + against + suffix)
            text = value_text + ' · ' + decision_text(item)
            row_value = item.get('value')
            value_compact = (_pct(item['value']) + suffix
                             + (' (ціль ≥' + against + ')' if against and minimal
                                else (' (ліміт ' + against + ')' if against else '')))
        else:
            # One row per issuer: both denominators (equities and NAV) share it,
            # subject in the row label, unresolved-first ordering preserved.
            eq = next((i for i in items if i['limit'].startswith(ISSUER_EQ_PREFIX)), None)
            nav_item = next((i for i in items if i['limit'].startswith(ISSUER_NAV_PREFIX)), None)
            primary = eq or nav_item
            limit, label = limit_for(primary['limit'])
            value_text = ''
            against_text = ''
            if eq is not None:
                eq_limit = limit_for(eq['limit'])[0]
                value_text = _pct(eq['value']) + ' акцій'
                against_text = _pct(eq_limit) if eq_limit is not None else ''
            if nav_item is not None:
                nav_limit = limit_for(nav_item['limit'])[0]
                nav_value = _pct(nav_item['value']) + ' NAV'
                nav_against = (_pct(nav_limit) + ' NAV') if nav_limit is not None else ' NAV'
                if value_text:
                    value_text += ' / ' + nav_value
                    against_text += ' / ' + nav_against
                else:
                    value_text = nav_value
                    against_text = nav_against
            text = value_text + ' понад ліміт ' + against_text + ' · ' + decision_text(primary)
            row_value = (eq or nav_item).get('value')
            value_compact = (_pct(eq['value']) + ' / ' + _pct(nav_item['value']) + ' NAV'
                             if eq is not None and nav_item is not None else
                             _pct(eq['value']) + ' акцій' if eq is not None else
                             _pct(nav_item['value']) + ' NAV')
            if against_text:
                value_compact += ' (ліміт ' + against_text + ')'
        breach_rows.append(('Порушення: ' + label, text))
        breach_facts.append('Порушення ліміту: ' + label + ' ' + text)
        breach_summary_items.append(('Порушення: ' + label, value_compact, row_value,
                                     item if subject_key[0] is None else primary))

    rows = list(breach_rows)
    issuer = f"{_issuer_display(shares['issuer_id'])}: {_pct(shares['issuer_pct_equities'])} акцій"
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
                     _pct(limits.get('top4_pct_equities', 20)) + ' (' +
                     _issuer_display(', '.join(shares['top4_ids'][:4])) + ')'))
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
    unresolved = sum(1 for item in block['breaches'] if not resolved(item))
    summary = [('Концентрація',
                'Ліміти дотримані' if not block['breaches'] else
                str(len(block['breaches'])) + ' порушень · ' + str(unresolved) + ' нерозглянутих'),
               ('Емітент', (_issuer_display(shares['issuer_id']) + ' ' + _pct(shares['issuer_pct_equities'])
                            + (' / ' + _pct(shares['issuer_pct_nav']) + ' NAV'
                               if shares['issuer_pct_nav'] is not None else ''))),
               ('Топ-4 / Core (stocks)', _pct(shares['top4_pct_equities']) + ' / ' + _pct(shares['core_pct_equities'])),
               ('Китай', _pct(shares['china_pct_equities']) if shares['china_pct_equities'] is not None else '-')]
    def _decision_suffix(item):
        text = decision_text(item)
        if text == 'нерозглянуто':
            return ' · нерозглянуто'
        verb = text.split(';')[0].replace('рішення: ', '')
        return ' · ✓ ' + verb + ((' до ' + text.split('розгляд ')[-1]) if 'розгляд ' in text else '')
    # The counter needs its evidence in place: compact breach explanations ride
    # in the sheet summary, largest impact first (owner 2026-10-29: sorted by
    # the primary denominator's value, alphabetical label breaking ties).
    # A blank row and the band header come from view data, so the writer (and
    # every render) sees the same layout - no hand-placed separator rows.)
    summary.extend([('', ''),
                    ('Порушення: за впливом, найбільші зверху', '#')])
    summary += [(row[0], row[1] + _decision_suffix(row[3])) for row in sorted(
        breach_summary_items, key=lambda row: (-(row[2] if _num(row[2]) else 0.), row[0]))]
    return dict(unavailable=None, rows=rows, summary=summary, breach_facts=breach_facts)


LIMIT_LABELS = {'issuer_pct_equities': 'Емітент', 'issuer_pct_nav': 'Емітент / NAV', 'top4_pct_equities': 'Топ-4',
                'core_min_pct_equities': 'Core', 'country_pct_equities_china': 'Китай'}


def _concentration_section_for(data, result, decisions):
    """The saved safeguard block behind the integrity gate, rendered for `result`.

    Single source of both v2 branches (scored and unavailable/not_applicable):
    a stale or tampered sibling degrades to an explicit unavailable block
    (`concentration_section` then renders its one row), an absent or malformed
    block returns None - safeguards never show verdicts the record cannot prove.
    """
    from analytics.concentration_v1 import (unavailable_block, validate_saved_concentration,
                                            VERSION as CONCENTRATION_VERSION)
    section = data['DIVERSIFICATION_DATA']
    block = section.get('concentration_v1')
    if (isinstance(block, dict) and block.get('version') == CONCENTRATION_VERSION
            and 'status' not in block
            and not validate_saved_concentration(block, data, result)):
        # A stale or tampered sibling must not render its verdicts with the
        # valid v2 score; degrade the safeguards, keep the score.
        section = dict(section, concentration_v1=unavailable_block(
            result['as_of_date'], ['concentration_block_invalid']))
    return concentration_section(section, decisions, result['as_of_date'])


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


def allocation_view_v2(data, expected_date=None, saved_at_utc=None):
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
    valid = validate_saved_allocation_v2(result, data, expected, replay=True)
    # v3 lives beside v2. A valid v3 supplies the scenarios; one that cannot be computed shows the
    # v2 assumption numbers with an explicit warning; a present but invalid one never falls back.
    shown, extra_warnings = result, []
    category_record = data['DIVERSIFICATION_DATA'].get('allocation_score_v3')
    if valid and category_record is not None:
        from analytics.allocation_score_v3 import validate_saved_allocation_v3
        if not validate_saved_allocation_v3(category_record, data, result, expected, v2_validated=True):
            valid = False
        elif category_record['status'] == 'unavailable':
            extra_warnings = category_record['warnings']
        else:
            shown = dict(result, **{key: category_record[key] for key in (
                'version', 'method', 'status', 'score', 'display_score', 'category', 'scenarios', 'assessment')},
                warnings=category_record['warnings'])
    # Risk progress lives beside v2 as well. Absent: the view is unchanged. Present: replayed against this
    # very v2; one that does not replay shows "Недоступно" and never a number.
    progress_row, progress_lines = None, []
    progress_record = data['DIVERSIFICATION_DATA'].get('risk_progress_v1')
    if valid and progress_record is not None:
        from analytics.holy_grail_risk_progress import validate_saved_risk_progress_v1
        if validate_saved_risk_progress_v1(progress_record, data, result, expected, v2_validated=True):
            progress_row, progress_lines = _risk_progress_text(progress_record, result['configuration']['group_definitions'])
        else:
            progress_row = 'Недоступно'
    if not valid:
        view['rows'] = [('Статус', view['status'])]
    else:
        stamp = '.'.join(reversed(result['as_of_date'].split('-')))
        cash = result['coverage'].get('cash_pct_nav')
        coverage = 'Cash поза оцінкою: ' + (_pct(cash) if cash is not None else '-') + ' повного портфеля.'
        warnings = [WARNINGS.get(w, 'Некоректні або неповні входи індикатора.') for w in shown['warnings'] + extra_warnings]
        view.update(as_of=stamp, warnings=warnings, principal_constraint=' '.join(warnings), coverage_summary=coverage,
                    cash_cell=_pct(cash) if cash is not None else '-')
        if result['status'] in {'unavailable', 'not_applicable'}:
            headline = 'Не застосовується' if result['status'] == 'not_applicable' else 'Дані недоступні'
            # The concentration block is measured beside the score and stays
            # replayable without it: render the safeguards here too. An
            # explicitly unavailable block shows its single row; the section is
            # hidden only when no block is saved (None) or the whole v2 record
            # fails the replay gate above.
            safeguards = _concentration_section_for(
                data, result, result['configuration'].get('concentration_decisions'))
            rows = [('Статус', headline), ('Обмеження', ' '.join(warnings)), ('Дата позиций', stamp)]
            if safeguards:
                rows.extend(safeguards['rows'])
            view.update(headline=headline, sheet_number=headline, status=headline, rows=rows,
                        safeguard_summary=(safeguards or {}).get('summary') or [])
        else:
            assessment = shown['assessment']
            label = {'concentrated': 'Концентрований',
                     'partly_diversified': 'Часткова диверсифікація',
                     'well_diversified': 'Добра диверсифікація'}[shown['category']]
            if assessment['business_dependent']:
                label += ' · Чутлива до автобізнесу'
            if assessment['window_dependent']:
                label += ' · Залежить від періоду'
            if assessment['combined_dependent']:
                label += ' · Залежить від сценарію'
            if assessment['available'] != assessment['expected']:
                label += ' · Не всі сценарії доступні'
            if shown['status'] == 'provisional': label += ' · Попередньо'
            if extra_warnings:  # the tab shows this label and note only, so the v2 fallback must be named here
                label += ' · Припущення v2: блок категорії авто недоступний'
            from analytics.car_resale_market import conclusion_note
            view['conclusion_note'] = conclusion_note(shown, data.get('CAR_RESALE_MARKET_CONTEXT'), saved_at_utc,
                                                      progress_lines)
            groups = sorted(result['groups'], key=lambda item: (-item['weight'], item['id']))
            definitions = result['configuration']['group_definitions']
            largest = group_label(groups[0]['id'], definitions) + ': ' + _pct(groups[0]['weight'] * 100)
            scenario_range = f"{assessment['min_display']}-{assessment['max_display']} зі 100"
            if assessment['available'] != assessment['expected']:
                scenario_range += f" ({assessment['available']}/{assessment['expected']} доступні)"
            rows = [('Метод', shown['version']), ('Оцінка', str(shown['display_score']) + ' зі 100'),
                    ('Висновок', label), ('Сценарний розкид', scenario_range),
                    ('Cash від повного портфеля', _pct(cash)),
                    ('Непокрита інвестована частка', _pct(result['coverage']['unknown_pct_invested']))]
            safeguards = _concentration_section_for(
                data, result, result['configuration'].get('concentration_decisions'))
            if safeguards:
                rows.extend(safeguards['rows'])
            for key, scenario in shown['scenarios'].items():
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
            main = shown['scenarios'][shown['method']['headline_scenario'] if 'method' in shown else
                                      'm60_r025' if 'm60_r025' in shown['scenarios'] else 'm60']
            for pair in main['pairs']:
                names = group_label(pair['left'], definitions) + ' / ' + group_label(pair['right'], definitions)
                if pair['kind'] == 'measured':
                    detail = f"{pair['observations']} місяців; останній {pair['last_month']}; r={pair['correlation']:.2f}".replace('.', ',')
                elif pair['kind'] == 'modeled':
                    detail = 'Модельна кореляція ' + str(pair['correlation']).replace('.', ',')
                elif pair['kind'] == 'category':
                    sample = {'monthly': 'місячна, вікно', 'lagged_1m': 'ціна з лагом 1 міс., вікно',
                              'stress_quintile': 'стрес-місяці акцій США з 1997'}.get(pair.get('sample'), 'вибірку не вказано')
                    detail = (f"Індекс цін вживаних авто (США), ціновий канал, R=1; {pair['observations']} спостережень "
                              f"({sample}); r={pair['correlation']:.2f}").replace('.', ',')
                else:
                    detail = 'Немає придатної пари; консервативно r=1'
                rows.append(('Історія пар', names + ': ' + detail))
            if 'method' in shown:
                rows.append(('Модель', 'Пари активів: 60 і 36 календарних місяців; автобізнес: кореляція з індексом цін '
                                       'вживаних авто (категорія і ціновий канал R=1, не ваш бізнес). Точка - найбільша з трьох '
                                       'оцінок (вікно, лаг ціни 1 міс., стрес-місяці акцій США з 1997; вибірки різні); обережний '
                                       'сценарій - найбільша верхня межа Фішера 90% на кожну оцінку, не довірчий інтервал бала; '
                                       'стрес 0,75; невідомі пари: r=1.'))
            else:
                rows.append(('Модель', '60 і 36 календарних місяців; бізнес: 0,25 / 0,75; невідомі пари: r=1.'))
            comparison = result['comparison']
            if comparison['status'] == 'available':
                rows.append(('Порівняння' + (' v2 (кореляція авто 0,25)' if 'method' in shown else ''), 'Ринки: {:+.2f}; позиції: {:+.2f}; разом: {:+.2f} пункту'.format(
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
            # The Details group no longer renders in the tab (owner 2026-10-29)
            view.update(headline=str(shown['display_score']) + ' зі 100', score_cell=shown['display_score'],
                        sheet_number=shown['display_score'], status=label, sheet_status=label,
                        largest_text=largest, sensitivity_text=scenario_range, rows=rows,
                        drivers=['Найбільша група: ' + largest],
                        risk_facts=((safeguards or {}).get('breach_facts') or []) + public_facts[:3],
                        safeguard_summary=(safeguards or {}).get('summary') or [],
                        model_status='Попередня оцінка' if shown['status'] == 'provisional' else 'Модельна оцінка')
    view['sheet_summary'] = [('Диверсифікація інвестованого капіталу', view['sheet_number']),
                             ('Висновок', view['status']), ('Найбільша група', view['largest_text']),
                             ('Сценарний розкид', view['sensitivity_text'])] + \
                            ([('Ризиковий прогрес', progress_row)] if progress_row is not None else []) + \
                            [('Cash поза оцінкою', view.get('cash_cell') or '-')] + \
                            list(view.get('safeguard_summary') or [])
    return view
