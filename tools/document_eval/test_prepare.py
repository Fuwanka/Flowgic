"""Data integrity checks; isolated from Django and the application database."""
import copy
import unittest
import json
from pathlib import Path
import tempfile

from prepare import FIELDS, acquisition_rows, build, page_identity, regions, score_eligible
from verify import verify


class DatasetIntegrityTests(unittest.TestCase):
    def test_snapshot_detects_training_exposure_and_changed_images(self):
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp)/'source', Path(temp)/'snapshot'
            (source/'dataset/annotated').mkdir(parents=True)
            (source/'dataset/raw').mkdir()
            (source/'dataset/train').mkdir()
            name = 'abcd1234-waybill_0001_page_1.jpg'
            (source/'dataset/annotated'/name).write_bytes(b'image-fixture')
            (source/'dataset/train'/name).write_bytes(b'image-fixture')
            task = {'file_upload':name,'annotations':[{'result':[]}]}
            (source/'dataset/raw/train1.json').write_text(json.dumps([task]),encoding='utf-8')
            (source/'dataset/train/metadata.jsonl').write_text(json.dumps({'file_name':name})+'\n',encoding='utf-8')
            summary = build(source,output)
            self.assertEqual(summary['eligible_holdout_documents'],0)
            self.assertEqual(summary['training_exposure']['known_source_used_by_existing_training'],1)
            self.assertEqual(verify(output)['pages'],1)
            with self.assertRaises(FileExistsError):
                build(source,output)
            next((output/'images').iterdir()).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checksum'):
                verify(output)

    def test_acquisition_plan_prioritizes_construction_without_losing_other_industries(self):
        from collections import Counter
        rows = acquisition_rows()
        self.assertEqual(len(rows), 160)
        self.assertEqual(len({r['slot_id'] for r in rows}), 160)
        counts = Counter(r['industry'] for r in rows)
        self.assertEqual(counts['construction'], 96)
        for industry in ('general','food_cold_chain','industrial','not_applicable'):
            self.assertEqual(counts[industry], 16)
        self.assertTrue(all(r['status'] == 'missing' for r in rows))

    def test_pair_and_uuid_prefix_are_one_document(self):
        self.assertEqual(page_identity('abcd1234-waybill_0021_page_1.jpg'), ('waybill_0021', 1))
        self.assertEqual(page_identity('ffffffff-waybill_0021_page_2.jpg'), ('waybill_0021', 2))
        self.assertEqual(page_identity('abcd1234-ТТН_0001_page-0002.jpg'), ('ТТН_0001', 2))

    def test_conflicting_semantics_are_preserved_and_flagged(self):
        task = {'annotations':[{'result':[
            {'id':'r', 'type':'rectanglelabels', 'value':{'rectanglelabels':['recipient_name'],
             'x':10,'y':20,'width':30,'height':5}},
            {'id':'r', 'type':'choices', 'from_name':'field_id', 'value':{'choices':['F005']}},
            {'id':'r', 'type':'textarea', 'value':{'text':['12 345,67 руб.']}},
        ]}]}
        result = regions(task)[0]
        self.assertEqual(result['raw_text'], '12 345,67 руб.')
        self.assertEqual(result['candidate_field'], 'freight_amount')
        self.assertIn('label_fid_conflict', result['issues'])
        self.assertEqual(result['review_status'], 'pending')

    def test_missing_transcription_is_not_an_absent_field(self):
        task = {'annotations':[{'result':[
            {'id':'r','type':'rectanglelabels','value':{
                'rectanglelabels':['sender_name'],'x':99,'y':20,'width':5,'height':5}}
        ]}]}
        result = regions(task)[0]
        self.assertIn('missing_or_multiple_transcriptions', result['issues'])
        self.assertIn('invalid_bbox', result['issues'])

    def approved(self):
        return {'review_status':'approved', 'rights_status':'approved',
                'provenance_kind':'real', 'split':'holdout', 'training_exposure':'none_verified',
                'reviewer':'reviewer-a','second_reviewer':'reviewer-b',
                'pages':[{'review_status':'approved'}],
                'gold':{field:{'status':'absent','value':None,'evidence':[]} for field in FIELDS}}

    def test_holdout_requires_independent_review_and_known_provenance(self):
        approved = self.approved()
        self.assertTrue(score_eligible(approved))
        for key, value in [('training_exposure','unknown'), ('rights_status','pending'),
                           ('provenance_kind','synthetic'),('split','quarantine'),
                           ('second_reviewer','reviewer-a')]:
            doc = copy.deepcopy(approved)
            doc[key] = value
            self.assertFalse(score_eligible(doc), key)

    def test_present_value_requires_evidence_and_all_fields_must_be_reviewed(self):
        doc = self.approved()
        doc['gold']['document_number'] = {'status':'present','value':'001','evidence':[]}
        self.assertFalse(score_eligible(doc))
        doc['gold'].pop('document_number')
        self.assertFalse(score_eligible(doc))


if __name__ == '__main__':
    unittest.main()
