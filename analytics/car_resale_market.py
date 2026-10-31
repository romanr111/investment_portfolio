"""Frozen public market context, separate from portfolio diversification scoring."""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import math
from urllib.parse import urlparse

VERSION = 'car_resale_market_context_v1'
NOTE_MARKER = '[portfolio:diversification-note:v1]'


def _instant(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timezone required')
    return dt.astimezone(timezone.utc)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def build_context(cutoff, observations):
    """Freeze dated observations; calculate changes only within the same series."""
    end = _instant(cutoff)
    rows = []
    for raw in observations:
        row = deepcopy(raw)
        required = ('id', 'label', 'period', 'period_end', 'published', 'url', 'unit', 'limitation')
        if not all(isinstance(row.get(k), str) and row[k].strip() for k in required):
            raise ValueError('Missing source metadata')
        if urlparse(row['url']).scheme != 'https':
            raise ValueError('Source must be HTTPS')
        if date.fromisoformat(row['period_end']) > end.date():
            raise ValueError('Observation period exceeds cutoff')
        publication = row['published']
        # Date-only publication must precede the snapshot day: its time is unknown.
        if len(publication) == 10:
            if date.fromisoformat(publication) >= end.date():
                raise ValueError('Publication time is unknown at snapshot cutoff')
        elif _instant(publication) > end:
            raise ValueError('Source published after cutoff')
        for key in ('value', 'previous', 'upper'):
            value = row.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError('Invalid observation')
        if row.get('previous') is not None:
            if (row.get('value') is None or row['previous'] == 0
                    or not row.get('previous_period') or not row.get('previous_url')
                    or not row.get('previous_published')
                    or not row['previous_url'].startswith('https://')):
                raise ValueError('Invalid comparison')
            previous_published = row['previous_published']
            if ((len(previous_published) == 10 and date.fromisoformat(previous_published) >= end.date())
                    or (len(previous_published) != 10 and _instant(previous_published) > end)):
                raise ValueError('Comparison source published after cutoff')
            row['change_pct'] = (row['value'] / row['previous'] - 1) * 100
        else:
            row['change_pct'] = None
        if row.get('upper') is not None and (row.get('value') is None or row['upper'] < row['value']):
            raise ValueError('Invalid range')
        rows.append(row)
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('Duplicate observations')
    result = {'version': VERSION, 'cutoff': cutoff, 'observations': rows}
    result['fingerprint'] = _digest(result)
    return result


def validated_context(context, as_of_date):
    try:
        if not isinstance(context, dict) or context.get('version') != VERSION:
            return None
        cutoff = _instant(context['cutoff'])
        if cutoff.date() > date.fromisoformat(as_of_date):
            return None
        source_rows = [{k: v for k, v in row.items() if k != 'change_pct'}
                       for row in context['observations']]
        return context if build_context(context['cutoff'], source_rows) == context else None
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return None


def conclusion_note(result, context):
    """Explain saved scenarios and optional verified context without changing the score."""
    lines = [NOTE_MARKER, 'Оцінка інвестованої частини. Бізнесова кореляція - припущення, не вимірювання.']
    scenarios = result.get('scenarios', {})
    for key, label in [('m60_r025', 'Базовий: 60 міс., кореляція 0,25'),
                       ('m60_r075', 'Стрес: 60 міс., кореляція 0,75'),
                       ('m60', 'Базовий: 60 міс.')]:
        if key in scenarios:
            score = scenarios[key].get('display_score')
            lines.append(label + ': ' + (str(score) + '/100' if score is not None else 'недоступно'))
    lines.append('Історія та припущення не гарантують майбутній результат. Кеш поза балом.')
    valid = validated_context(context, result['as_of_date'])
    if valid:
        lines.append('Ринковий контекст станом на ' + valid['cutoff'][:10] +
                     '; не прибуток і не кореляція бізнесу:')
        for row in valid['observations']:
            value = row.get('value')
            text = 'дані недоступні' if value is None else str(value).replace('.', ',')
            if value is not None:
                if row.get('upper') is not None:
                    text += '-' + str(row['upper']).replace('.', ',')
                text += ' ' + row['unit']
            if row.get('change_pct') is not None:
                text += ' (' + f"{row['change_pct']:+.1f}".replace('.', ',') + '% до ' + row['previous_period'] + ')'
            lines.append(f"{row['label']}: {text}; {row['period']}. {row['limitation']} {row['url']}")
    else:
        lines.append('Ринковий контекст: дані недоступні або не додані до цього знімка.')
    return '\n'.join(lines)
