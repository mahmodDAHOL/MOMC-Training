import frappe

from momc_training.utils.portal import build
from momc_training.utils.security import normalise_email


def get_context(context):
    build(context, "verify", signed_in=False)
    context.email = normalise_email(frappe.form_dict.get("email") or "")
