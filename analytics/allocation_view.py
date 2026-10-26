"""Public whitelist for one saved capital diversity score. No market collection."""
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
                               f"; кореляція {top['correlation']:.2f}.".replace('.',','))
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
