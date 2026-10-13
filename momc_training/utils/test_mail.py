from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from momc_training.utils.mail import send_otp


class TestApplicantMail(FrappeTestCase):
    def test_otp_email_is_queued(self):
        with patch("momc_training.utils.mail.frappe.sendmail") as sendmail:
            send_otp("applicant@example.com", "123456", "verify")

        sendmail.assert_called_once()
        self.assertTrue(sendmail.call_args.kwargs["delayed"])
        self.assertFalse(sendmail.call_args.kwargs["now"])
