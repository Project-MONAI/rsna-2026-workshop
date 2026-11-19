import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from html.parser import HTMLParser

import nibabel as nib
import numpy as np

import publish_nv_inference as publisher


class LinkParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs)['href']


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'data'
        self.image = self.data / 'ImageCAS/case 90/image.nii.gz'
        self.image.parent.mkdir(parents=True)
        self.run = self.root / 'inference_tmp/run one'
        self.run.mkdir(parents=True)
        self.mask = self.run / 'raw_prediction.nii.gz'
        nib.save(nib.Nifti1Image(np.zeros((3, 4, 5), dtype=np.int16), np.eye(4)), self.image)
        labels = np.zeros((3, 4, 5), dtype=np.uint16)
        labels[0] = 3
        nib.save(nib.Nifti1Image(labels, np.eye(4)), self.mask)
        self.result = {'skill':'nv_segment_ct', 'output': {
            'path':str(self.mask), 'any_label_present':True, 'label_set_valid':True,
            'geometry':{'shape_match':True, 'spacing_match':True, 'affine_match':True}}}
        (self.run / 'result.json').write_text(json.dumps(self.result))

    def publish(self, *extra, image=True):
        args = ['publish', '--run-dir', str(self.run), '--data-root', str(self.data)]
        if image:
            args += ['--image', str(self.image)]
        with patch('sys.argv', args + list(extra)), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(publisher.main(), 0)
        return json.loads((self.run / 'manifest.json').read_text())

    def test_external_image_is_referenced_and_full_labels_preserved(self):
        original = self.image.read_bytes()
        manifest = self.publish()
        self.assertEqual(self.image.read_bytes(), original)
        self.assertFalse((self.run / 'image.nii.gz').exists())
        self.assertFalse((self.run / 'prediction_heart.nii.gz').exists())
        self.assertFalse(manifest['image_copied'])
        self.assertEqual(manifest['prediction_viewer'], 'prediction_global.nii.gz')
        self.assertEqual(manifest['foreground_voxels'], {'3':20})
        np.testing.assert_array_equal(nib.load(self.mask).get_fdata(),
                                      nib.load(self.run / 'prediction_global.nii.gz').get_fdata())
        parser = LinkParser()
        parser.feed((self.run / 'result_viewer.html').read_text())
        url = urljoin('https://lab.example/miagent/files/inference_tmp/run%20one/result_viewer.html', parser.href)
        self.assertEqual(urlparse(url).path, '/miagent/nii')
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query['huOffset'], ['0'])
        source = urljoin(url, query['images'][0])
        self.assertEqual(unquote(urlparse(source).path), '/miagent/data-files/ImageCAS/case 90/image.nii.gz')
        self.assertNotIn('palette', query)

    def test_image_symlink_uses_data_route(self):
        (self.run / 'image.nii.gz').symlink_to(self.image)
        manifest = self.publish(image=False)
        self.assertTrue(manifest['input_url'].startswith('data-files/'))
        self.assertTrue((self.run / 'image.nii.gz').is_symlink())

    def test_actual_geometry_checked_despite_result_claims(self):
        affine = np.eye(4)
        affine[0, 3] = 100
        nib.save(nib.Nifti1Image(np.ones((3, 4, 5), dtype=np.uint8), affine), self.mask)
        with self.assertRaisesRegex(SystemExit, 'actual image and mask affines differ'):
            self.publish()
        self.assertFalse((self.run / 'result_viewer.html').exists())

    def test_image_outside_served_roots_rejected(self):
        other = self.root / 'private.nii.gz'
        other.write_bytes(self.image.read_bytes())
        self.image = other
        with self.assertRaisesRegex(SystemExit, 'input image must be under'):
            self.publish()

    def test_optional_heart_view(self):
        mask = np.full((3, 4, 5), 115, dtype=np.uint16)
        nib.save(nib.Nifti1Image(mask, np.eye(4)), self.mask)
        manifest = self.publish('--overlay', 'heart', '--hu-offset', '1024')
        self.assertEqual(manifest['prediction_viewer'], 'prediction_heart.nii.gz')
        self.assertEqual(manifest['hu_display_offset'], 1024)
        np.testing.assert_array_equal(nib.load(self.run / 'prediction_heart.nii.gz').get_fdata(), np.ones(mask.shape))

    def test_prepared_image_inside_run(self):
        local = self.run / 'prepared.nii.gz'
        local.write_bytes(self.image.read_bytes())
        self.image = local
        self.assertTrue(self.publish()['input_url'].startswith('files/inference_tmp/'))


if __name__ == '__main__':
    unittest.main()
