"""Public used-vehicle datasets for the car-category tracker (parsers, manifest, refresh).

The parsers read local files only. `fetch_raw` and `long_group_returns` are the only
network entry points and are called explicitly; every raw file is recorded with its
SHA-256 so a later run can prove which vintage it used (Manheim revises history).
"""
import hashlib
import json
import re
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

MANHEIM_INDEX = 'Index (1/97 = 100)'
BLS_URL = 'https://download.bls.gov/pub/time.series/cu/cu.data.14.USTransportation'
AUTO1_URL = 'https://auto1-group.com/index'
EUROSTAT_URL = ('https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_midx'
                '?format=JSON&coicop=CP07112&unit=I15&geo=FR')
BEA_URL = 'https://api.db.nomics.world/v22/series/BEA/NIUnderlyingDetail-U70205S/{}?observations=1'
BEA_SERIES = ('SAART-M', 'TEMF-M', 'TEMG-M', 'NSAT-M', 'T2-M', 'T3-M')
BLS_SERIES = ('CUSR0000SETA02', 'CUUR0000SETA02', 'CUUR0000SETC', 'CUUR0000SETD01',
              'CUSR0000SETD03', 'CUUR0000SETD03')
USER_AGENT = 'investment-portfolio-car-category/1.0'
_NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def _month_end(index):
    return pd.DatetimeIndex(index) + pd.offsets.MonthEnd(0)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def manifest(raw_dir):
    """Name, size and SHA-256 of every raw file, so a run can name its data vintage."""
    return {p.name: dict(bytes=p.stat().st_size, sha256=sha256(p))
            for p in sorted(Path(raw_dir).iterdir()) if p.is_file()}


def _column_number(ref):
    number = 0
    for char in re.match(r'[A-Z]+', ref).group(0):
        number = number * 26 + ord(char) - 64
    return number - 1


def manheim_frame(path):
    """Monthly Manheim Used Vehicle Value Index sheet 'DATA' (stdlib xlsx parsing)."""
    archive = zipfile.ZipFile(path)
    strings = [''.join(t.text or '' for t in si.iter(_NS + 't'))
               for si in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
    header, rows = None, []
    for row in ET.fromstring(archive.read('xl/worksheets/sheet1.xml')).iter(_NS + 'row'):
        cells = {}
        for cell in row.findall(_NS + 'c'):
            value = cell.find(_NS + 'v')
            if value is not None:
                cells[_column_number(cell.get('r'))] = (
                    strings[int(value.text)] if cell.get('t') == 's' else value.text)
        if header is None:
            if MANHEIM_INDEX in cells.values():
                header = cells
            continue
        try:
            stamp = date(1899, 12, 30) + timedelta(days=int(float(cells[0])))
        except (KeyError, ValueError):
            continue
        record = {'date': pd.Timestamp(stamp)}
        for position, name in header.items():
            if position and position in cells:
                try:
                    record[str(name)] = float(cells[position])
                except ValueError:
                    pass
        rows.append(record)
    if not rows:
        raise ValueError('Manheim workbook has no data rows')
    frame = pd.DataFrame(rows).set_index('date').sort_index()
    frame.index = _month_end(frame.index)
    return frame


def bls_frame(path, series_ids=BLS_SERIES):
    """Monthly BLS CPI levels; unpublished months ('-') stay missing."""
    out = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[0] not in series_ids or not re.fullmatch(r'M(0[1-9]|1[0-2])', parts[2]):
            continue
        try:
            value = float(parts[3])
        except ValueError:
            continue
        out.setdefault(parts[0], {})[pd.Timestamp(int(parts[1]), int(parts[2][1:]), 1)] = value
    frame = pd.DataFrame({k: pd.Series(v).sort_index() for k, v in out.items()})
    frame.index = _month_end(frame.index)
    return frame


def dbnomics_series(path):
    doc = json.loads(Path(path).read_text(encoding='utf-8'))['series']['docs'][0]
    values = [float('nan') if v in (None, 'NA') else float(v) for v in doc['value']]
    return pd.Series(values, index=_month_end(pd.to_datetime(doc['period_start_day'])), name=doc['series_code'])


def new_vehicle_units(raw_dir):
    """Monthly NSA US new light-vehicle units (millions): autos + light trucks, from BEA via DBnomics."""
    parts = [dbnomics_series(Path(raw_dir) / f'bea_{code}.json') for code in ('NSAT-M', 'T2-M', 'T3-M')]
    return pd.concat(parts, axis=1).sum(axis=1, min_count=3)


def auto1_series(path):
    """AUTO1 Group Price Index (seasonally adjusted wholesale), scraped from the page's JS array."""
    match = re.search(r'const DATA\s*=\s*(\[.*?\])\s*;', Path(path).read_text(encoding='utf-8'), re.S)
    if not match:
        raise ValueError('AUTO1 page has no DATA array')
    data = json.loads(match.group(1))
    return pd.Series([v for _, v in data], index=_month_end(pd.to_datetime([d for d, _ in data], format='%b %Y')),
                     name='auto1')


def eurostat_series(path):
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    position = {v: k for k, v in doc['dimension']['time']['category']['index'].items()}
    values = {pd.Timestamp(position[int(i)] + '-01'): v for i, v in doc['value'].items()}
    return pd.Series(values).sort_index().rename('eurostat_fr').pipe(lambda s: s.set_axis(_month_end(s.index)))


def _curl(url, target, agent=USER_AGENT):
    result = subprocess.run(['curl', '-sSL', '--proto', '=https', '--proto-redir', '=https', '--max-time', '120', '-A', agent,
                            '-o', str(target), url],
                            capture_output=True, text=True)
    if result.returncode or not Path(target).stat().st_size:
        raise ValueError(f'download failed: {url}')


def fetch_raw(raw_dir, manheim_url, bls_contact=None):
    """Download the raw files into a new empty directory (network).

    BLS refuses requests without contact details in the User-Agent, so its file is fetched only
    when the caller supplies a contact; the tracker itself does not need it (crisis test only).
    """
    raw = Path(raw_dir)
    raw.mkdir(parents=True)
    _curl(manheim_url, raw / 'manheim.xlsx')
    if bls_contact:
        _curl(BLS_URL, raw / 'bls_cu_transport.txt', f'{USER_AGENT} ({bls_contact})')
    _curl(AUTO1_URL, raw / 'auto1_index.html')
    _curl(EUROSTAT_URL, raw / 'eurostat_fr.json')
    for code in BEA_SERIES:
        _curl(BEA_URL.format(code), raw / f'bea_{code}.json')
    return manifest(raw)


def long_group_returns(as_of_date, symbols):
    """Full-history monthly USD total returns of ETF representatives (network, Yahoo)."""
    from analytics.holy_grail import completed_month_end
    from analytics.holy_grail_data import _fetch_market
    cutoff = completed_month_end(as_of_date)
    frames = {}
    for group, symbol in symbols.items():
        prices = _fetch_market(symbol, '1990-01-01', (pd.Timestamp(cutoff) + pd.Timedelta(days=5)).date().isoformat())
        close = prices['prices']
        close.index = pd.DatetimeIndex(close.index).tz_localize(None)
        monthly = close.groupby(close.index.to_period('M')).last()
        monthly.index = _month_end(monthly.index.to_timestamp())
        frames[group] = monthly[monthly.index <= pd.Timestamp(cutoff)].pct_change()
    return pd.DataFrame(frames)
