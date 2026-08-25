import base64
import io
import unittest
from unittest.mock import MagicMock, patch

from kegal.utils import (
    _parse_s3_uri,
    _is_base64_string,
    load_images_to_base64,
    load_pdfs_to_base64,
)

PNG_BYTES = b'\x89PNG\r\n\x1a\n' + b'\x00' * 200
PDF_BYTES = b'%PDF-1.7\n' + b'0' * 200


def _fake_s3_client(body: bytes, content_type: str = ''):
    """Build a boto3-like s3 client whose get_object returns body."""
    client = MagicMock()
    client.get_object.return_value = {
        'Body': io.BytesIO(body),
        'ContentType': content_type,
    }
    return client


class TestParseS3Uri(unittest.TestCase):

    def test_bucket_and_key(self):
        self.assertEqual(
            _parse_s3_uri("s3://my-bucket/docs/report.pdf"),
            ("my-bucket", "docs/report.pdf", None),
        )

    def test_region_query_param(self):
        bucket, key, region = _parse_s3_uri("s3://my-bucket/img/a.png?region=eu-west-1")
        self.assertEqual((bucket, key), ("my-bucket", "img/a.png"))
        self.assertEqual(region, "eu-west-1")

    def test_missing_key_rejected(self):
        with self.assertRaises(ValueError):
            _parse_s3_uri("s3://my-bucket")

    def test_missing_bucket_rejected(self):
        with self.assertRaises(ValueError):
            _parse_s3_uri("s3:///just/a/key")

    def test_s3_uri_is_not_treated_as_base64(self):
        self.assertFalse(_is_base64_string("s3://my-bucket/docs/report.pdf"))


class TestLoadFromS3(unittest.TestCase):

    def test_image_uses_stored_content_type(self):
        client = _fake_s3_client(PNG_BYTES, content_type='image/png')
        with patch('boto3.client', return_value=client) as mock_client:
            content_type, b64 = load_images_to_base64("s3://bucket/img/photo.png")

        self.assertEqual(content_type, 'image/png')
        self.assertEqual(base64.b64decode(b64), PNG_BYTES)
        mock_client.assert_called_once()
        self.assertEqual(mock_client.call_args.args[0], 's3')
        client.get_object.assert_called_once_with(Bucket='bucket', Key='img/photo.png')

    def test_image_falls_back_to_key_extension(self):
        # A generic/absent ContentType must not leak into the LLM payload.
        client = _fake_s3_client(PNG_BYTES, content_type='binary/octet-stream')
        with patch('boto3.client', return_value=client):
            content_type, _ = load_images_to_base64("s3://bucket/img/photo.png")

        self.assertEqual(content_type, 'image/png')

    def test_region_from_uri_is_passed_to_boto3(self):
        client = _fake_s3_client(PNG_BYTES, content_type='image/png')
        with patch('boto3.client', return_value=client) as mock_client:
            load_images_to_base64("s3://bucket/img/photo.png?region=eu-west-1")

        self.assertEqual(mock_client.call_args.kwargs['region_name'], 'eu-west-1')

    def test_no_region_in_uri_leaves_boto3_default_chain(self):
        client = _fake_s3_client(PNG_BYTES, content_type='image/png')
        with patch('boto3.client', return_value=client) as mock_client:
            load_images_to_base64("s3://bucket/img/photo.png")

        self.assertIsNone(mock_client.call_args.kwargs['region_name'])

    def test_pdf_download(self):
        client = _fake_s3_client(PDF_BYTES, content_type='application/pdf')
        with patch('boto3.client', return_value=client):
            content_type, b64 = load_pdfs_to_base64("s3://bucket/docs/report.pdf")

        self.assertEqual(content_type, 'application/pdf')
        self.assertEqual(base64.b64decode(b64), PDF_BYTES)

    def test_pdf_validator_rejects_non_pdf_object(self):
        client = _fake_s3_client(b'not a pdf at all' * 20, content_type='application/pdf')
        with patch('boto3.client', return_value=client):
            with self.assertRaises(ValueError):
                load_pdfs_to_base64("s3://bucket/docs/report.pdf")

    def test_client_error_is_wrapped(self):
        from botocore.exceptions import ClientError

        client = MagicMock()
        client.get_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchKey', 'Message': 'Not found'}}, 'GetObject'
        )
        with patch('boto3.client', return_value=client):
            with self.assertRaises(ValueError) as ctx:
                load_images_to_base64("s3://bucket/img/missing.png")

        self.assertIn("s3://bucket/img/missing.png", str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
