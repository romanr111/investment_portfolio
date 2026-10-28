"""Fingerprints for saved diversification inputs."""
from analytics.holy_grail import fingerprint, holdings_fingerprint


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
