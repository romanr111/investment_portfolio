"""Historical quality summaries remain readable."""
import unittest


class PolicyTests(unittest.TestCase):
    def test_ten_checks_define_exact_score_range(self):
        from analytics.diversification_quality import summarize_checks, CHECK_IDS
        states=['pass']*4+['fail']*3+['unknown']*3
        result=summarize_checks([dict(id=k,state=v) for k,v in zip(CHECK_IDS,states)])
        self.assertEqual((result['score_min'],result['score_max'],result['score']),(40,70,None))

    def test_missing_or_impossible_review_evidence_is_not_accepted(self):
        from analytics.diversification_quality import reviewed_record
        for field, value in [('source', None), ('source', 42), ('reviewed_at', '2999-01-01')]:
            record = {'source': 'synthetic source', 'effective_from': '2020-01-01',
                      'reviewed_at': '2026-09-30'}
            record[field] = value
            self.assertEqual(reviewed_record({'risk_record': record}, '2026-09-30'), {})
