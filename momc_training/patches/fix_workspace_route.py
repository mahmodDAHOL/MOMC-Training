import frappe

OLD = "Graduate Training"


def execute():
    """v1.0 shipped the workspace as name 'Graduate Training' with an Arabic
    title. Frappe routes the sidebar by title but looks pages up by name, so
    the page opened as 'not found'. The fixed workspace is synced under the
    Arabic name; remove the old record."""
    if frappe.db.exists("Workspace", OLD):
        frappe.delete_doc("Workspace", OLD, ignore_permissions=True, force=True)
