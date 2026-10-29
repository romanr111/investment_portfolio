"""Public whitelist for the frozen indicator. No fetching or financial calculation."""
from analytics.holy_grail_indicator import validate_saved_indicator

REASONS = {
 'partial_or_cached_valuations':'Частина оцінок збережена або неповна; це попередня модельна оцінка.',
 'short_common_history':'Менше 60 спільних місячних спостережень.',
 'history_lags_positions':'Історії закінчуються раніше за дату позицій.',
 'uncovered_positions':'Частина позицій не має придатної історії.',
 'hedge_driven_count':'Хеджування підвищує еквівалент; це не буквальна кількість незалежних бізнесів.',
 'incomplete_recent_window':'Порівняння за останні 36 календарних місяців недоступне через пропуски.',
 'reserve_confirmation_expired_or_invalid':'Підтвердження резерву потребує оновлення.',
 'mapping_outside_validity':'Строк підтвердженого зіставлення позиції з історією минув або ще не почався; зіставлення потребує оновлення.',
 'invalid_mapping_dates':'Некоректні дати зіставлення позиції з історією; зіставлення не застосовано.',
 'unreconciled_valuations':'Суми позицій не узгоджуються з підсумком.',
 'insufficient_common_history':'Менше 36 спільних місяців історії.',
 'degenerate_covariance':'Недостатня варіативність для розрахунку.',
 'invalid_valuation':'Некоректні оцінки позицій.',
 'invalid_cash_partition':'Компоненти Cash не узгоджуються.',
 'unsupported_risk':'Непідтримувані короткі або нелінійні позиції.',
 'invalid_monthly_history':'Некоректна місячна історія.',
 'invalid_inputs':'Некоректні вхідні дані.'}


def fmt(value, places=1):
    if value is None: return '-'
    if places == 1 and value < 15 and round(value,1) >= 15: return '<15'
    return f'{value:.{places}f}'.replace('.',',')


def indicator_view(data, expected_date=None):
    from analytics.diversification_view import _empty
    q = data['DIVERSIFICATION_DATA']['indicator']
    expected_date = expected_date or str(data.get('POSITION_DATA',{}).get('as_of_date') or data.get('DATA_METADATA',{}).get('last_updated') or '')[:10]
    def unavailable(message):
        view=_empty(message)
        stamp='.'.join(reversed(expected_date.split('-'))) if expected_date else '-'
        view.update(indicator=True,sheet_number='Дані недоступні',as_of=stamp,
                    coverage_summary='Оцінка недоступна; попереднє число не використовується.',
                    principal_constraint=message,rows=[('Статус',message),('Дата позицій',stamp)])
        return view
    if not validate_saved_indicator(q,data,expected_date):
        return unavailable('Некоректна або неузгоджена збережена оцінка')
    warnings = [REASONS.get(r,'Обмеження вхідних даних.') for r in q['warnings']]
    if q['status']=='unavailable': return unavailable(' '.join(warnings))
    count=q['effective_streams'];headline='Не застосовується' if q['status']=='not_applicable' else fmt(count)
    stamp='.'.join(reversed(q['as_of_date'].split('-')))
    coverage=q['coverage']
    pct=lambda k:f"{coverage[k]:.1f}%".replace('.',',')
    def precise_pct(value):
        return ('<0,1%' if 0<value<.1 else f'{value:.1f}%'.replace('.',','))
    rows=[('Еквівалент джерел ризику',headline),('Орієнтир','15–20'),
          ('Без проксі, ті самі місяці',fmt(q['direct_only_effective_streams'])),
          ('Останні 36 місяців',fmt(q['recent_effective_streams'])),
          ('Без проксі за 36 місяців',fmt(q['direct_only_recent_effective_streams'])),
          ('Дата позицій',stamp),('Період історій',f"{q['return_window_start'] or '-'} - {q['return_window_end'] or '-'}"),
          ('Спільних місячних спостережень',str(q['observation_count'])),
          ('Модельованих експозицій',str(q['modeled_exposure_count']))]
    for label,key in [('Прямі історії','direct'),('Моделі','model'),('Підтверджений Treasury-резерв','reserve'),('Cash поза лічильником','cash'),('Непокриті позиції','uncovered')]:
        rows.append((label,precise_pct(coverage[key])))
    for item in q['models']:
        share = f" Частка портфеля: {precise_pct(item['share_pct'])}." if 'share_pct' in item else ''
        rows.append(('Модель',item['description'] + share))
    for item in q['uncovered']: rows.append(('Без історії',f"{item['category']}: {precise_pct(item['share_pct'])}"))
    for pair in q['top_correlations']:
        rows.append(('Корельована пара',f"{pair['left']} / {pair['right']}: {pair['correlation']:.2f}".replace('.',',')))
    for warning in warnings: rows.append(('Обмеження',warning))
    rows.extend([('Інтерпретація','Модель статистичної диверсифікації; не офіційна оцінка Ray Dalio та не оцінка якості інвестицій.'),
                 ('Cash','Cash не додає джерел. Stablecoins не є безризиковим резервом.'),
                 ('Моделі','Результат без проксі є порівнянням для іншої частини портфеля, не межею похибки.')])
    view=_empty()
    view.update(indicator=True, headline=headline, effective=headline,
                sheet_number=count if count is not None and headline!='<15' else headline,
                as_of=stamp,status='Попередній метод DR². '+('Попередня модельна оцінка' if q['status']=='provisional' else 'Модельна оцінка'),
                sheet_status='Попередній метод DR²', confidence_label='Модельна оцінка', rows=rows,
                count_note='Еквівалент джерел ризику', principal_constraint=' '.join(warnings),
                coverage_text=f"{pct('direct')} / {pct('model')}",
                coverage_summary=f"Прямі історії: {pct('direct')}; моделі: {pct('model')}; резерв: {pct('reserve')}; Cash: {pct('cash')}; непокриті: {precise_pct(coverage['uncovered'])}.",
                history_end=q['return_window_end'] or '-',warnings=warnings)
    return view
