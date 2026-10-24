"""Evidence bounds for the versioned diversification checklist."""
import math


def bound_check(identifier, lower, upper, threshold, *, blocked=False, reasons=()):
    state = 'unknown' if blocked else 'pass' if upper <= threshold + 1e-10 else 'fail' if lower > threshold + 1e-10 else 'unknown'
    return dict(id=identifier,state=state,value=lower,upper_bound=upper,threshold=threshold,reasons=list(reasons))


def _nonnegative(value):
    try:
        number=float(value)
        return number if not isinstance(value,bool) and math.isfinite(number) and number>=0 else None
    except (ValueError,TypeError,OverflowError):
        return None


def stress_return(record, index, shocks, yield_shocks):
    kind=record.get('stress_class')
    if kind in shocks:
        return shocks[kind][index]
    rate=_nonnegative(record.get('rate_duration'))
    if kind in {'treasury_reserve','nominal_government','inflation_linked','corporate_credit'} and rate is not None and rate <= 100:
        nominal,real,spread=yield_shocks[index]
        change=-rate*(real if kind=='inflation_linked' else nominal)
        if kind=='corporate_credit':
            credit=_nonnegative(record.get('spread_duration'))
            if credit is None or credit > 100: return None
            change-=credit*spread
        return max(-1.,change)
    return None


def _fraction_map(record,key,*,maximum_sum=None):
    fractions=record.get(key)
    if not isinstance(fractions,dict): return None
    if any(not isinstance(k,str) or not k.strip() or _nonnegative(v) is None or float(v)>1 for k,v in fractions.items()):
        return None
    if maximum_sum is not None and sum(float(v) for v in fractions.values())>maximum_sum+1e-10:
        return None
    return {k:float(v) for k,v in fractions.items()}


def value_checks(rows,records,total,thresholds,shocks,yield_shocks,scenario_names):
    """Every missing fact remains a bounded unknown, with no fabricated offsetting gains."""
    issuer,dependencies={},{}
    issuer_unknown=dependency_unknown=illiquid=liquidity_unknown=0.
    scenario_values={name:dict(loss_min_pct=0.,loss_max_pct=0.,unknown_pct=0.) for name in scenario_names}
    local=dict(loss_min_pct=0.,loss_max_pct=0.,unknown_pct=0.)
    stale=sum(e['value_usd'] for e in rows if e.get('valuation_stale'))/total*100>=thresholds['material']
    for e in rows:
        share=100*e['value_usd']/total
        record=records[e['id']]
        # An explicit, sourced exemption is necessary; a category label alone is insufficient.
        if record.get('corporate_issuer_applicable') is False:
            portions={}
        else:
            portions=_fraction_map(record,'issuer_weights',maximum_sum=1)
        if portions is None:
            issuer_unknown+=share
        else:
            for name,fraction in portions.items(): issuer[name]=issuer.get(name,0.)+share*fraction
            if record.get('corporate_issuer_applicable') is not False:
                issuer_unknown+=share*max(0.,1-sum(portions.values()))
        groups=_fraction_map(record,'counterparty_groups') if record.get('counterparty_complete') is True else None
        if groups is None:
            dependency_unknown+=share
        else:
            for name,fraction in groups.items(): dependencies[name]=dependencies.get(name,0.)+share*fraction
        days=_nonnegative(record.get('liquidation_days'))
        if days is None: liquidity_unknown+=share
        elif days>thresholds['liquid_days']: illiquid+=share
        for index,name in enumerate(scenario_names):
            change=stress_return(record,index,shocks,yield_shocks)
            target=scenario_values[name]
            if change is None:
                target['loss_max_pct']+=share
                target['unknown_pct']+=share
            else:
                target['loss_min_pct']-=share*change
                target['loss_max_pct']-=share*change
        changes=[]
        if record.get('stress_class')=='car_inventory': changes.append(.30)
        if record.get('fx_monetary') is True: changes.append(.20)
        if changes:
            loss=share*max(changes)
            local['loss_min_pct']+=loss;local['loss_max_pct']+=loss
        elif record.get('fx_monetary') is False and record.get('stress_class'):
            pass
        else:
            local['loss_max_pct']+=share;local['unknown_pct']+=share
    lower=max(issuer.values(),default=0.)
    counterparty_lower=max(dependencies.values(),default=0.)
    scenario_values['local_fx']=local
    checks={
        'issuer_concentration':bound_check('issuer_concentration',lower,min(100.,lower+issuer_unknown),thresholds['issuer_concentration'],blocked=stale),
        'counterparty':bound_check('counterparty',counterparty_lower,min(100.,counterparty_lower+dependency_unknown),thresholds['counterparty'],blocked=stale),
        'illiquidity':bound_check('illiquidity',illiquid,min(100.,illiquid+liquidity_unknown),thresholds['illiquidity'],blocked=stale),
    }
    for identifier in ('recession','inflation','local_fx'):
        bounds=scenario_values[identifier]
        checks[identifier]=bound_check(identifier,bounds['loss_min_pct'],bounds['loss_max_pct'],thresholds[identifier],blocked=stale)
    liquidity=scenario_values['market_liquidity'];crypto=scenario_values['crypto_crash']
    checks['liquidity_crypto']=bound_check('liquidity_crypto',max(liquidity['loss_min_pct'],crypto['loss_min_pct']),
                                         max(liquidity['loss_max_pct'],crypto['loss_max_pct']),thresholds['liquidity_crypto'],blocked=stale)
    for check in checks.values():
        if check['state']=='unknown': check['reasons']=['stale_valuations' if stale else 'incomplete_exposure_evidence']
    return checks,scenario_values
