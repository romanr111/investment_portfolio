"""Adapt canonical holdings to private, dated risk evidence without changing balances."""
from copy import deepcopy
from datetime import date

import pandas as pd

from analytics.holy_grail import fingerprint, holdings_fingerprint, qualification_reviewed
from analytics.diversification_quality import COUNT_VERSION, POLICY_VERSION, calculate_quality


def quality_inputs_fingerprint(data):
    def normalize(value):
        if isinstance(value,dict): return {k:normalize(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)): return [normalize(v) for v in value]
        if isinstance(value,(int,float)) and not isinstance(value,bool): return float(value)
        # Enhanced broker fields may use Decimal in the existing serializer.
        from decimal import Decimal
        if isinstance(value,Decimal): return float(value)
        return value
    return fingerprint(dict(holdings=holdings_fingerprint(data),
                            metadata=normalize(data.get('DATA_METADATA')),
                            enhanced=normalize(data.get('ENHANCED_STOCKS'))))


def prepare_quality_exposures(data,positions,cash,settings,as_of_date):
    """Cash children partition the canonical parent; they never add extra NAV."""
    configuration=settings.get('diversification',{})
    records=configuration.get('exposures',{})
    rows=deepcopy(positions)
    contract=data.get('POSITION_DATA',{})
    for e in rows:
        e['risk_record']=deepcopy(records.get(e['id'],records.get('category:'+e['category'],{})))
        e['valuation_stale']=False
        if e['category']=='Short Selling': e['unsupported_risk']=True
        if e['risk_record'].get('nonlinear_risk') or e['risk_record'].get('leveraged'): e['unsupported_risk']=True
        if e['id'].startswith('crypto:'):
            e['valuation_stale']=data.get('DATA_QUALITY',{}).get('crypto',{}).get('freshness') in {'stale','partial','snapshot_fallback'}
            matches=[r for r in contract.get('crypto',[]) if r.get('asset')==e['id'].split(':',1)[1]]
            if any(float(r.get('quantity',0))<0 for r in matches): e['unsupported_risk']=True
        for group in ('crypto_lending','p2p','other_assets'):
            prefix=group+':'
            if e['id'].startswith(prefix):
                index=int(e['id'][len(prefix):]);source=contract.get(group,[])
                if index<len(source):
                    source=source[index]
                    e['valuation_stale']=source.get('status')=='legacy' or source.get('coverage') in {'partial','legacy'} or (source.get('as_of_date') and str(source['as_of_date'])[:10]!=as_of_date)
    cash_data=data.get('CASH_DATA',{})
    children=[]
    def child(identifier,value):
        children.append(dict(id=identifier,category='Cash',value_usd=float(value),series=None,
                             is_cash=True,kind='unmodeled',weak_proxy=False,
                             risk_record=deepcopy(records.get(identifier,{})),
                             valuation_stale=data.get('DATA_QUALITY',{}).get('cash',{}).get('freshness') in {'stale','partial','snapshot_fallback'}))
    for asset,value in (cash_data.get('Cash_Equivalents') or {}).items():
        child('cash_equivalent:'+asset,value)
    seen=set()
    for component in configuration.get('cash_components',[]):
        key=component['breakdown_key']
        if key in seen or component.get('excludes_cash_equivalents') is not True:
            raise ValueError('Cash partition requires disjoint canonical source keys')
        seen.add(key)
        child('cash_breakdown:'+key,cash_data.get('Breakdown',{})[key])
    remaining=float(cash)-sum(e['value_usd'] for e in children)
    if remaining < -max(.02,abs(float(cash))*1e-6):
        raise ValueError('Cash children exceed canonical cash total')
    if remaining>0: child('cash:unclassified',remaining)
    return rows+children


def enrich_quality(data,positions,cash,returns,settings,as_of_date,flags,provenance):
    """Failure is confined to the optional quality block, not the legacy result."""
    try:
        if set(flags)&{'invalid_valuation','invalid_cash_valuation','unreconciled_positions','unreconciled_valuations'}:
            raise ValueError('Canonical valuation inputs are incomplete')
        rows=prepare_quality_exposures(data,positions,cash,settings,as_of_date)
        # Source dates are necessary for resolving checks, independently of the envelope date.
        if set(flags)&{'valuation_date_mismatch','valuation_date_unverified'}:
            for e in rows: e['valuation_stale']=True
        result=calculate_quality(rows,returns,as_of_date=as_of_date,total_assets=data['TOTAL_ASSETS'],
                                 policy=settings.get('diversification',{}).get('policy'),input_flags=flags)
        result.update(holdings_fingerprint=quality_inputs_fingerprint(data),
                      configuration_fingerprint=fingerprint(settings.get('diversification',{})),
                      history_fingerprint=fingerprint(returns.to_json(date_format='iso')),
                      retrospective=as_of_date<date.today().isoformat(),source_provenance=provenance,
                      cash_share_pct=100*float(cash)/float(data['TOTAL_ASSETS']),
                      qualification_status='reviewed' if all(qualification_reviewed(e.get('qualification')) for e in positions) else 'pending')
        return result
    except Exception as error:
        return dict(count_version=COUNT_VERSION,policy_version=POLICY_VERSION,as_of_date=as_of_date,
                    status='unavailable',effective_streams=None,score=None,score_min=None,score_max=None,
                    confidence='low',constraints=['quality_analysis_failed',type(error).__name__])
