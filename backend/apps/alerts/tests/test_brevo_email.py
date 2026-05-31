from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.alerts.services.brevo_email import BREVO_API_URL, send_transactional_email


class BrevoEmailTests(TestCase):
    @override_settings(BREVO_API_KEY="", DEFAULT_FROM_EMAIL="sender@example.com")
    def test_missing_api_key_raises(self):
        with self.assertRaises(ValueError):
            send_transactional_email(
                recipient="to@example.com",
                subject="Test",
                body="Hello",
            )

    @override_settings(BREVO_API_KEY="test-key", DEFAULT_FROM_EMAIL="")
    def test_missing_from_email_raises(self):
        with self.assertRaises(ValueError):
            send_transactional_email(
                recipient="to@example.com",
                subject="Test",
                body="Hello",
            )

    @override_settings(BREVO_API_KEY="test-key", DEFAULT_FROM_EMAIL="sender@example.com")
    @patch("apps.alerts.services.brevo_email.requests.post")
    def test_successful_send(self, mock_post):
        mock_response = MagicMock()
        mock_response.content = b'{"messageId":"abc123"}'
        mock_response.json.return_value = {"messageId": "abc123"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = send_transactional_email(
            recipient="to@example.com",
            subject="Job alert: python",
            body="Matching jobs:\n- Job 1",
        )

        self.assertEqual(result["messageId"], "abc123")
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        self.assertEqual(call_kwargs["json"]["sender"]["email"], "sender@example.com")
        self.assertEqual(call_kwargs["json"]["to"], [{"email": "to@example.com"}])
        self.assertEqual(call_kwargs["json"]["subject"], "Job alert: python")
        self.assertEqual(call_kwargs["headers"]["api-key"], "test-key")
        self.assertEqual(mock_post.call_args.args[0], BREVO_API_URL)

    @override_settings(BREVO_API_KEY="test-key", DEFAULT_FROM_EMAIL="sender@example.com")
    @patch("apps.alerts.services.brevo_email.requests.post")
    def test_html_content_included_when_provided(self, mock_post):
        mock_response = MagicMock()
        mock_response.content = b'{"messageId":"abc123"}'
        mock_response.json.return_value = {"messageId": "abc123"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        send_transactional_email(
            recipient="to@example.com",
            subject="JobSense AI Alert: python — 3 relevant matches",
            body="Plain text body",
            html_body="<html><body>HTML body</body></html>",
        )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["textContent"], "Plain text body")
        self.assertEqual(payload["htmlContent"], "<html><body>HTML body</body></html>")
