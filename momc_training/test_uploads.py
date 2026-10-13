# momc_training/test_upload.py


def run():
    import frappe, os, json
    from momc_training.utils import session as app_session
    from momc_training.api import files as files_api

    path = "/home/momcerp/frappe-bench/sites/momc-erp.sy/private/files/front_ID.jpg"
    assert os.path.exists(path), f"missing {path}"

    # --- 1. dummy cookie manager ---
    class _DummyCookie:
        def __init__(self): self.cookies = {}
        def set_cookie(self, name, value, **kw): self.cookies[name] = value
        def delete_cookie(self, name, **kw): self.cookies.pop(name, None)

    frappe.local.cookie_manager = _DummyCookie()

    # --- 2. session ---
    sess = app_session.create("TA-2026-41083")
    cookie_name = next(iter(frappe.local.cookie_manager.cookies))
    sid  = frappe.local.cookie_manager.cookies[cookie_name]
    csrf = sess["csrf"]
    print("cookie:", cookie_name, "| SID:", sid, "| CSRF:", csrf)

    with open(path, "rb") as f:
        data = f.read()

    # --- 3. fake werkzeug file ---
    class _Stream:
        def __init__(self, b): self.b, self.i = b, 0
        def read(self, n=-1):
            if n < 0:
                c = self.b[self.i:]; self.i = len(self.b)
            else:
                c = self.b[self.i:self.i+n]; self.i += len(c)
            return c

    class _File:
        def __init__(self, name, b, ct):
            self.filename, self.stream, self.content_type = name, _Stream(b), ct

    # --- 4. fake HTTP request ---
    frappe.request = frappe._dict(
        cookies=frappe._dict({cookie_name: sid}),
        headers=frappe._dict({"X-TA-CSRF": csrf}),
        files=frappe._dict({"file": _File("front_ID.jpg", data, "image/jpeg")}),
        method="POST",
    )
    # >>> THE MISSING PIECE: identity for @rate_limit <<<
    frappe.local.request_ip = "127.0.0.1"
    # Optional: also give Frappe a session user so user_key fallback works
    frappe.session.user = "Administrator"   # only if your code reads it

    # --- 5. run ---
    print("require ->", app_session.require(check_csrf=True))
    result = files_api.upload(kind="id_front")
    print(frappe.as_json(result))
    return result