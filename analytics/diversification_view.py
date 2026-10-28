"""Privacy-safe presentation of saved analytics. No collection or risk calculation."""
from datetime import datetime
import math

from analytics.holy_grail import saved_progress_view
from analytics.diversification_inputs import quality_inputs_fingerprint
from analytics.diversification_quality import COUNT_VERSION, POLICY_VERSION, CHECK_IDS, summarize_checks

CHECK_LABELS = dict(family_concentration='Концентрація сімей ризику',issuer_concentration='Концентрація емітента',
                    breadth='Статистична широта',stability='Стійкість за 36 місяців',recession='Рецесія',
                    inflation='Інфляція та ставки',liquidity_crypto='Ліквідність / криптострес',
                    counterparty='Контрагент / depeg',local_fx='Бізнес / валютний шок',illiquidity='Неліквідні активи')
STATES={'pass':'Пройдено','fail':'Не пройдено','unknown':'Невизначено'}
CONFIDENCE={'low':'Низька','medium':'Середня','high':'Висока'}


def _number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)


def _fmt(value,places=1):
    return '-' if not _number(value) else f'{value:.{places}f}'.replace('.',',')


def _empty(status='Немає збереженої оцінки'):
    return dict(headline='Дані недоступні',score=None,score_cell='Дані недоступні',effective='-',as_of='-',
                status=status,sheet_status='Дані недоступні',rows=[],coverage_text='-',confidence_label='-',
                legacy=False,count_note='Еквівалент за ризиком',critical_text='',warnings=[],
                principal_constraint='',headline_warning='')


def _legacy(data,expected_date):
    old=saved_progress_view(data,expected_date)
    if old['as_of']=='-': return _empty(old['status'])
    view=_empty('Попередній метод; нова оцінка відсутня')
    view.update(headline='Нова оцінка відсутня',score_cell='Нова оцінка відсутня',effective=old['effective'],
                as_of=old['as_of'],legacy=True,count_note='Попередній метод holy_grail_progress_v1',
                coverage_text=old['coverage_text'],sheet_status='Попередній метод',
                rows=[row for row in old['rows'] if row[0] not in {'Статистична оцінка прогресу','Статус оцінки'}])
    return view


def _saved_diversification_view(data,expected_date=None):
    data=data.get('data',data)
    if 'DIVERSIFICATION_DATA' not in data: return _legacy(data,expected_date)
    q=data['DIVERSIFICATION_DATA']
    if isinstance(q,dict) and 'allocation_score_v2' in q:
        from analytics.allocation_view import allocation_view_v2
        return allocation_view_v2(data,expected_date)
    if isinstance(q,dict) and 'allocation_score' in q:
        from analytics.allocation_view import allocation_view
        view = allocation_view(data,expected_date)
        view['model_status'] = 'Попередня методика capital_diversification_v1'
        view['rows'].insert(0, ('Метод', view['model_status']))
        return view
    if isinstance(q,dict) and 'indicator' in q:
        from analytics.holy_grail_indicator_view import indicator_view
        return indicator_view(data,expected_date)
    try:
        if not isinstance(q,dict) or q.get('count_version')!=COUNT_VERSION or q.get('policy_version')!=POLICY_VERSION:
            return _empty('Непідтримувана версія оцінки')
        expected=expected_date or str(data.get('DATA_METADATA',{}).get('last_updated') or data.get('POSITION_DATA',{}).get('as_of_date') or '')[:10]
        if expected and q.get('as_of_date')!=expected: return _empty('Оцінка не відповідає даті портфеля')
        if q.get('status')=='unavailable': return _empty('Недостатньо узгоджених даних для оцінки')
        if q.get('holdings_fingerprint')!=quality_inputs_fingerprint(data): return _empty('Оцінка не відповідає збереженим вхідним даним')
        stamp=datetime.fromisoformat(q['as_of_date']).strftime('%d.%m.%Y')
        count=q.get('effective_streams')
        if count is not None and (not _number(count) or count<0): return _empty('Некоректна збережена оцінка')
        for key in ('cash_share_pct','reserve_share_pct'):
            if not _number(q.get(key)) or not 0<=q[key]<=100+1e-8: return _empty('Некоректні частки портфеля')
        if not isinstance(q.get('constraints'),list) or not all(isinstance(x,str) for x in q['constraints']):
            return _empty('Некоректні обмеження оцінки')
        if not isinstance(q.get('scenarios'),dict): return _empty('Некоректні сценарії')
        checks=q['checks']
        if any(not _number(c.get('threshold')) or any(c.get(k) is not None and not _number(c[k]) for k in ('value','upper_bound')) for c in checks):
            return _empty('Некоректні значення перевірок')
        summary=summarize_checks(checks)
        reserve_only=q['status']=='not_applicable'
        if not reserve_only and any(q.get(k)!=summary[k] for k in ('score','score_min','score_max','check_counts')):
            return _empty('Неузгоджені результати перевірок')
        if q.get('confidence') not in CONFIDENCE: return _empty('Некоректна впевненість у даних')
        coverage=q['coverage']
        if any(not _number(coverage[k]) or not 0<=coverage[k]<=100+1e-8 for k in ('direct_pct','proxy_pct','uncovered_pct','reserve_pct')):
            return _empty('Некоректне покриття')
        if abs(sum(coverage.values())-100)>1e-6: return _empty('Неузгоджене покриття')
    except (ValueError,TypeError,KeyError,AttributeError):
        return _empty('Некоректний формат збереженої оцінки')
    if reserve_only:
        headline='Не застосовується';cell=headline
    elif summary['check_counts']['unknown']==10:
        headline='Недостатньо даних';cell=headline
    else:
        headline=f"{q['score']}/100" if q['score'] is not None else f"{q['score_min']}–{q['score_max']}/100"
        cell=q['score'] if q['score'] is not None else headline
    effective='<15' if count is not None and count<15 and round(count,2)>=15 else _fmt(count,2)
    scope='лише покрита частина портфеля' if q.get('scope')=='covered_subset' else 'портфель у межах моделі'
    status=('Попередня оцінка' if q['status']!='assessed' else 'Оцінка за політикою')+' - '+scope
    if q.get('retrospective'): status+=' - ретроспективно'
    critical=[CHECK_LABELS[c['id']] for c in checks if c['state']=='fail' and c['id'] in {'family_concentration','issuer_concentration','breadth','counterparty'}]
    critical_text='; '.join(critical)
    warnings=[]
    if 'hedge_driven_count' in q.get('constraints',[]): warnings.append('Хеджування підвищує еквівалент: це не кількість незалежних бізнесів або стратегій.')
    if q.get('cash_share_pct',0)>0: warnings.append('Кеш може зменшувати втрати, але не додає незалежних джерел дохідності.')
    if q.get('status')=='not_applicable': warnings.append('Портфель складається з підтверджених резервів; оцінка диверсифікації не застосовується.')
    principal_constraint = ('Неповні або застарілі оцінки активів' if set(q['constraints']) & {'stale_valuations','partial_valuations'}
                            else 'Неповне моделювання ризиків або слабкі проксі' if 'material_proxy_or_valuation_limit' in q['constraints']
                            else 'Неповне покриття історіями' if 'uncovered_exposures' in q['constraints']
                            else 'Недостатньо підтверджених даних' if summary['check_counts']['unknown'] else '')
    headline_warning = warnings[0] if 'hedge_driven_count' in q['constraints'] else ''
    coverage_text=' / '.join(_fmt(coverage[k])+'%' for k in ('direct_pct','proxy_pct','uncovered_pct'))
    rows=[('Оцінка /100',headline),('Межі за невизначеними перевірками','-' if reserve_only else f"{q['score_min']}–{q['score_max']}/100"),
          ('Ефективні джерела / ціль',effective+' / 15–20'),('Метод кількості',COUNT_VERSION),('Політика',POLICY_VERSION),
          ('Дата оцінки',stamp),('Статус',status),('Впевненість у вхідних даних',CONFIDENCE[q['confidence']]),
          ('Прямі дані / проксі / без історії',coverage_text),('Частка резервів',_fmt(q.get('reserve_share_pct'))+'%'),
          ('Частка кешу',_fmt(q.get('cash_share_pct'))+'%'),('Модельованих експозицій',str(q.get('modeled_exposure_count',0))),
          ('Місячних спостережень',str(q.get('observation_count',0))),
          ('Період дохідностей',f"{q.get('return_window_start') or '-'} - {q.get('return_window_end') or '-'}"),
          ('Зниження модельованої волатильності',_fmt(q.get('volatility_reduction_pct'))+'%'),
          ('Обґрунтування очікуваної дохідності','Перевірені' if q.get('qualification_status')=='reviewed' else 'Потребують окремої перевірки')]
    if principal_constraint: rows.append(('Основне обмеження',principal_constraint))
    for check in checks:
        value=check.get('value');upper=check.get('upper_bound');threshold=check.get('threshold')
        if check['id']=='stability':
            display=_fmt(value*100 if _number(value) else None);limit=_fmt(threshold*100 if _number(threshold) else None)+'%'
            value_text=display+'%'
        else:
            suffix='' if check['id']=='breadth' else '%'
            value_text=_fmt(value)+(('–'+_fmt(upper)) if _number(upper) and upper!=value else '')+suffix
            limit=_fmt(threshold)+suffix
        reason_labels={'stale_valuations':'неповні або застарілі оцінки',
                       'incomplete_exposure_evidence':'неповні підтвердження ризиків',
                       'insufficient_evidence':'недостатньо придатних історій або підтверджень ризиків'}
        explanation='; '.join(reason_labels.get(reason,'недостатньо підтверджених даних') for reason in check.get('reasons',[]))
        rows.append((CHECK_LABELS[check['id']],f"{STATES[check['state']]}: {value_text}; поріг {'≥' if check['id'] in {'breadth','stability'} else '≤'} {limit}"+('; '+explanation if explanation else '')))
    for name,label in [('recession','Рецесія'),('inflation','Інфляція / ставки'),('market_liquidity','Ринкова ліквідність'),('crypto_crash','Криптошок'),('local_fx','Бізнес / FX')]:
        scenario=q.get('scenarios',{}).get(name,{})
        rows.append(('Сценарій: '+label,_fmt(scenario.get('loss_min_pct'))+'–'+_fmt(scenario.get('loss_max_pct'))+'% втрати'))
    rows.extend([('Інтерпретація','10 балів за пройдену перевірку. Діапазон відображає невизначені перевірки, не ймовірність.'),
                 ('Сценарії','Гіпотетичні шоки. Оцінка облігацій за duration є наближеною, особливо за великих змін ставок.'),
                 ('Обмеження','Минулі кореляції та оцінка /100 не доводять майбутньої незалежності або привабливості інвестицій.')])
    if critical_text: rows.append(('Не пройдені ключові перевірки',critical_text))
    rows.extend(('Увага',warning) for warning in warnings)
    return dict(headline=headline,score=q.get('score'),score_cell=cell,effective=effective,as_of=stamp,status=status,
                sheet_status=CONFIDENCE[q['confidence']]+(' · Не пройдено: '+critical_text if critical_text else ' · '+principal_constraint if principal_constraint else ''),confidence_label=CONFIDENCE[q['confidence']],
                rows=rows,coverage_text=coverage_text,legacy=False,count_note='Еквівалент за ризиком',
                critical_text=critical_text,warnings=warnings,principal_constraint=principal_constraint,headline_warning=headline_warning)


def saved_diversification_view(data,expected_date=None):
    """Malformed optional data must never break ordinary Sheets/report rendering."""
    try:
        return _saved_diversification_view(data,expected_date)
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return _empty('Некоректний формат збереженої оцінки')
