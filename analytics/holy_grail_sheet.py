"""Scoped, readback-verified Holy Grail updates. Never replace a worksheet."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from analytics.holy_grail import fingerprint
from analytics.diversification_view import saved_diversification_view
from analytics.allocation_view import sheet_detail_rows
from analytics.holy_grail_data import DATA_DIR

END_MARKER = 'Holy Grail - End'
MARKERS = {'Holy Grail - Details','Диверсифікація - Details'}
CELL_FIELDS = ('userEnteredValue','userEnteredFormat','dataValidation','note','textFormatRuns')


def _occupied(cell):
    return bool(cell.get('userEnteredValue') or cell.get('note') or cell.get('dataValidation'))


def _write(sheet_id, start, values):
    def cell(v):
        return {'userEnteredValue':{'numberValue':v} if isinstance(v,(float,int)) else {'stringValue':str(v)}}
    return {'updateCells':{'range':{'sheetId':sheet_id,'startRowIndex':start,'endRowIndex':start+len(values),
                                   'startColumnIndex':0,'endColumnIndex':2},
                           'rows':[{'values':[cell(v) for v in row]} for row in values],
                           'fields':'userEnteredValue'}}


def plan_requests(data, sheet_id, grid, groups, details_start, old_end):
    allowed_labels = [
        {'Диверсифікація інвестованої частини', 'Диверсифікація інвестованого капіталу',
         'Holy Grail: еквівалент джерел', 'Диверсифікація /100'},
        {'Висновок', 'Орієнтир', 'Ефективні джерела / ціль'},
        {'Найбільша група', 'Дата позицій', 'Дата оцінки'},
        {'Модель бізнесу 0,75', 'Сценарний розкид', 'Прямі історії / моделі', 'Впевненість у даних'},
        {'Дата / Cash поза оцінкою', 'Статус', 'Прямі / проксі / без історії'},
    ]
    view=saved_diversification_view(data)
    if not view.get('indicator'): raise ValueError('A valid new indicator is required')
    summary=view['sheet_summary'] if view.get('allocation') else [
        ['Holy Grail: еквівалент джерел',view['sheet_number']],['Орієнтир','15–20'],
        ['Дата позицій',view['as_of']],['Прямі історії / моделі',view['coverage_text']],
        ['Статус',view['status']]]
    # A saved concentration measurement extends the owned summary beyond 5 rows.
    extra = max(0, len(summary) - 5) if view.get('allocation') else 0
    allowed_labels.extend([{'Концентрація'}, {'Емітент', 'Концентрація'},
                           {'Топ-4 / Core', 'Концентрація'}, {'Китай', 'Концентрація'}][:extra])
    end_row = 9 + max(len(summary), 5)
    if end_row > len(grid): raise ValueError('Insufficient summary rows; extend the sheet explicitly')
    if not grid[9][0].get('userEnteredValue', {}).get('stringValue', '') and any(
            _occupied(cell) for row in grid[9:end_row] for cell in row[:2]):
        raise ValueError('Summary cells are populated without an ownership label')
    for index, labels in enumerate(allowed_labels, start=9):
        left, right = grid[index][:2]
        label = left.get('userEnteredValue', {}).get('stringValue', '')
        if (label and label not in labels) or (not label and _occupied(right)):
            raise ValueError('Summary cells belong to another section')
        for cell in (left, right):
            if (cell.get('note') or cell.get('dataValidation') or cell.get('textFormatRuns') or
                    'formulaValue' in cell.get('userEnteredValue', {})):
                raise ValueError('Summary cells contain foreign metadata or formulas')
    detail_rows = sheet_detail_rows(view['rows']) if view.get('allocation') else view['rows']
    rows=[[a,b] for a,b in detail_rows]+[[END_MARKER,'']]
    end=details_start+len(rows)
    if end>len(grid): raise ValueError('Insufficient rows; extend the test/target sheet explicitly')
    for row in grid[details_start-1:old_end]:
        for cell in row[:2]:
            if (cell.get('note') or cell.get('dataValidation') or cell.get('textFormatRuns') or
                    'formulaValue' in cell.get('userEnteredValue', {})):
                raise ValueError('Details cells contain foreign metadata or formulas')
    for row in grid[old_end:end]:
        if any(_occupied(c) for c in row[:2]): raise ValueError('New details overlap existing cells')
    requests=[_write(sheet_id,9,summary),_write(sheet_id,details_start-1,[['Диверсифікація - Details','']]),
              _write(sheet_id,details_start,rows)]
    if old_end>end: requests.append(_write(sheet_id,end,[['',''] for _ in range(old_end-end)]))
    marker = grid[details_start-1][0].get('userEnteredValue', {}).get('stringValue', '')
    if marker not in MARKERS and any(g['range']['startIndex'] == details_start for g in groups):
        raise ValueError('Details insertion conflicts with an unowned row group')
    owned=[g for g in groups if marker in MARKERS and g['range']['startIndex']==details_start]
    span_end=max(end,old_end)
    if owned and any(_occupied(c) for row in grid[details_start:span_end] for c in row[2:]):
        raise ValueError('Details row group contains foreign cells')
    for g in sorted(owned,key=lambda x:-x.get('depth',1)):
        requests.append({'deleteDimensionGroup':{'range':{'sheetId':sheet_id,'dimension':'ROWS',
                        'startIndex':g['range']['startIndex'],'endIndex':g['range']['endIndex']}}})
    foreign=[g for g in groups if g not in owned and g['range']['startIndex']<span_end and g['range']['endIndex']>details_start]
    if owned:
        segments=[]
        for i in range(details_start,span_end):
            if any(g['range']['startIndex']<=i<g['range']['endIndex'] for g in foreign): continue
            if segments and segments[-1][1]==i: segments[-1][1]=i+1
            else: segments.append([i,i+1])
        for a,b in segments:
            requests.append({'updateDimensionProperties':{'range':{'sheetId':sheet_id,'dimension':'ROWS','startIndex':a,'endIndex':b},
                            'properties':{'hiddenByUser':False},'fields':'hiddenByUser'}})
    bounds={'sheetId':sheet_id,'dimension':'ROWS','startIndex':details_start,'endIndex':end}
    safe=not foreign and not any(_occupied(c) for row in grid[details_start:span_end] for c in row[2:])
    if safe:
        requests.extend([{'addDimensionGroup':{'range':bounds}},
          {'updateDimensionGroup':{'dimensionGroup':{'range':bounds,'depth':1,'collapsed':True},'fields':'collapsed'}},
          {'updateDimensionProperties':{'range':bounds,'properties':{'hiddenByUser':True},'fields':'hiddenByUser'}}])
    requests.extend([
      {'repeatCell':{'range':{'sheetId':sheet_id,'startRowIndex':9,'endRowIndex':10,'startColumnIndex':1,'endColumnIndex':2},
        'cell':{'userEnteredFormat':{'numberFormat':view.get('number_format') or ({'type':'PERCENT','pattern':'0%'} if view.get('allocation') else {'type':'NUMBER','pattern':'0.0'})}},'fields':'userEnteredFormat.numberFormat'}},
      {'repeatCell':{'range':{'sheetId':sheet_id,'startRowIndex':9,'endRowIndex':end_row,'startColumnIndex':0,'endColumnIndex':2},
        'cell':{'userEnteredFormat':{'wrapStrategy':'WRAP'}},'fields':'userEnteredFormat.wrapStrategy'}},
      {'repeatCell':{'range':{'sheetId':sheet_id,'startRowIndex':details_start-1,'endRowIndex':end,'startColumnIndex':0,'endColumnIndex':2},
        'cell':{'userEnteredFormat':{'wrapStrategy':'WRAP'}},'fields':'userEnteredFormat.wrapStrategy'}}])
    return requests,dict(summary=[9,end_row],details=[details_start-1,span_end],new_end=end,collapsed=safe)


def read_state(book, sheet_id):
    from gspread.utils import rowcol_to_a1
    metadata=book.fetch_sheet_metadata()
    sheet=next(s for s in metadata['sheets'] if s['properties']['sheetId']==sheet_id)
    props=sheet['properties'];n=props['gridProperties']['rowCount'];m=props['gridProperties']['columnCount']
    if n*m>100000: raise ValueError('Target grid exceeds bounded audit size')
    title=props['title'].replace("'","''")
    result=book.fetch_sheet_metadata(params={'includeGridData':True,'ranges':f"'{title}'!A1:{rowcol_to_a1(n,m)}"})
    sheet=next(s for s in result['sheets'] if s['properties']['sheetId']==sheet_id)
    grid=[[{} for _ in range(m)] for _ in range(n)]
    for chunk in sheet.get('data',[]):
        for i,row in enumerate(chunk.get('rowData',[]),start=chunk.get('startRow',0)):
            for j,c in enumerate(row.get('values',[]),start=chunk.get('startColumn',0)):
                grid[i][j]={k:deepcopy(c[k]) for k in CELL_FIELDS if k in c}
    return dict(properties=props,grid=grid,groups=sheet.get('rowGroups',[]),
                row_metadata=[r for chunk in sheet.get('data',[]) for r in chunk.get('rowMetadata',[])])


def _details(state):
    grid=state['grid'];matches=[i for i,row in enumerate(grid) if row and row[0].get('userEnteredValue',{}).get('stringValue') in MARKERS]
    if len(matches)>1: raise ValueError('Ambiguous details ownership')
    if matches:
        start=matches[0]+1
        group_ends=[g['range']['endIndex'] for g in state['groups'] if g['range']['startIndex']==start]
        ends=[i+1 for i,row in enumerate(grid) if i>=start and row[0].get('userEnteredValue',{}).get('stringValue')==END_MARKER]
        if len(ends)>1: raise ValueError('Ambiguous details end markers')
        if ends:
            # A row group is not permission to consume cells beyond the marker.
            if any(end!=ends[0] for end in group_ends):
                raise ValueError('Details end marker conflicts with row group')
            return start,ends[0]
        if group_ends: return start,max(group_ends)
        if any(_occupied(c) for c in grid[start][:2]):
            raise ValueError('Populated details need an owned group or explicit end marker')
        return start,start
    last=max((i for i,row in enumerate(grid) if any(_occupied(c) for c in row)),default=14)
    return last+2,last+2


def outside_fingerprint(state, owned):
    grid=deepcopy(state['grid'])
    for start,end in [owned['summary'],owned['details']]:
        for row in grid[start:end]: row[:2]=[{},{}]
    start,end=owned['details']
    foreign=[g for g in state['groups'] if g['range']['startIndex'] != start+1]
    # Only row visibility in the explicitly managed block may change.
    row_metadata=deepcopy(state['row_metadata'])
    for row in row_metadata[start:end]: row.pop('hiddenByUser',None)
    return fingerprint(dict(grid=grid,groups=foreign,properties=state['properties'],row_metadata=row_metadata))


def deliver(book, sheet_id, data, receipt_dir, *, apply=False, expected_title=None):
    before=read_state(book,sheet_id)
    if expected_title and before['properties']['title']!=expected_title: raise ValueError('Worksheet date does not match snapshot')
    start,old_end=_details(before)
    requests,owned=plan_requests(data,sheet_id,before['grid'],before['groups'],start,old_end)
    receipt_dir=Path(receipt_dir);receipt_dir.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path=receipt_dir/f'{stamp}_{sheet_id}.json'
    receipt=dict(spreadsheet_id=book.id,sheet_id=sheet_id,owned=owned,before=before,requests=requests,status='dry_run')
    path.write_text(json.dumps(receipt,ensure_ascii=False))
    if not apply:return dict(status='dry_run',receipt=str(path),requests=len(requests),owned=owned)
    if fingerprint(read_state(book,sheet_id))!=fingerprint(before): raise ValueError('Target changed after preflight')
    write_error=None
    try: book.batch_update({'requests':requests})
    except Exception as error: write_error=type(error).__name__
    after=read_state(book,sheet_id)
    expected=deepcopy(before['grid'])
    for request in requests:
        if 'updateCells' in request:
            update=request['updateCells'];offset=update['range']['startRowIndex']
            for i,row in enumerate(update['rows'],start=offset):
                for j,c in enumerate(row['values']):
                    expected[i][j]['userEnteredValue']=c['userEnteredValue']
    for a,b in [owned['summary'],owned['details']]:
        for i in range(a,b):
            for j in range(2):
                got=after['grid'][i][j].get('userEnteredValue',{})
                want=expected[i][j].get('userEnteredValue',{})
                if got.get('stringValue')=='':got={}
                if want.get('stringValue')=='':want={}
                if got!=want: raise RuntimeError('Indicator value readback mismatch; backup retained')
    if outside_fingerprint(before,owned)!=outside_fingerprint(after,owned):
        raise RuntimeError('Outside-scope state changed; backup retained')
    fmt=after['grid'][9][1].get('userEnteredFormat',{}).get('numberFormat',{})
    view=saved_diversification_view(data)
    expected_format=view.get('number_format') or ({'type':'PERCENT','pattern':'0%'} if view.get('allocation') else {'type':'NUMBER','pattern':'0.0'})
    if fmt!=expected_format: raise RuntimeError('Number format readback mismatch')
    visibility={}
    for request in requests:
        change=request.get('updateDimensionProperties',{})
        if 'hiddenByUser' in change.get('properties',{}):
            bounds=change['range']
            for i in range(bounds['startIndex'],bounds['endIndex']):
                visibility[i]=change['properties']['hiddenByUser']
    for i,want in visibility.items():
        metadata=after['row_metadata'][i] if i<len(after['row_metadata']) else {}
        if bool(metadata.get('hiddenByUser',False)) != want:
            raise RuntimeError('Row visibility readback mismatch')
    matches=[g for g in after['groups'] if g['range']['startIndex']==start]
    if owned['collapsed'] and (len(matches)!=1 or matches[0]['range']['endIndex']!=owned['new_end'] or not matches[0].get('collapsed')):
        raise RuntimeError('Group readback mismatch')
    if not owned['collapsed'] and matches: raise RuntimeError('Unsafe group remains')
    receipt.update(status='verified',after=after,write_error=write_error,outside_unchanged=True)
    path.write_text(json.dumps(receipt,ensure_ascii=False))
    return dict(status='verified',receipt=str(path),url=f'https://docs.google.com/spreadsheets/d/{book.id}/edit#gid={sheet_id}',owned=owned)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True);parser.add_argument('--spreadsheet-id',required=True)
    parser.add_argument('--sheet-id',type=int,required=True);parser.add_argument('--credentials',type=Path,default=DATA_DIR/'credentials.json')
    parser.add_argument('--receipt-dir',type=Path,default=DATA_DIR/'indicator_delivery')
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--dry-run',action='store_true');mode.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    payload=json.loads(args.snapshot.read_text());data=payload.get('data',payload)
    diversification=data['DIVERSIFICATION_DATA']
    saved=(diversification['allocation_score_v2'] if 'allocation_score_v2' in diversification else
           diversification.get('allocation_score',diversification.get('indicator',{})))
    if not isinstance(saved,dict): parser.exit(2,'Invalid saved indicator\n')
    as_of=payload.get('as_of_date') or saved['as_of_date']
    if as_of != saved.get('as_of_date'):
        parser.exit(2,'Snapshot date does not match saved indicator date\n')
    from src.google_sheets.spreadsheet_structure import GoogleSheetsClient
    book=GoogleSheetsClient(str(args.credentials)).client.open_by_key(args.spreadsheet_id)
    expected=datetime.strptime(as_of,'%Y-%m-%d').strftime('%d %b %Y')
    try: result=deliver(book,args.sheet_id,data,args.receipt_dir,apply=args.apply,expected_title=expected)
    except (ValueError,RuntimeError) as error: parser.exit(2,str(error)+'\n')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
