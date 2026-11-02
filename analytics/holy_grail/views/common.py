"""Shared building blocks for the public views."""


def empty_view(status='Немає збереженої оцінки'):
    return dict(headline='Дані недоступні',score=None,score_cell='Дані недоступні',effective='-',as_of='-',
                status=status,sheet_status='Дані недоступні',rows=[],coverage_text='-',confidence_label='-',
                legacy=False,count_note='Еквівалент за ризиком',critical_text='',warnings=[],
                principal_constraint='',headline_warning='')
