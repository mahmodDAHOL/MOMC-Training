app_name = "momc_training"
app_title = "MOMC Training"
app_publisher = "مديرية تقانة المعلومات والتحول الرقمي - وزارة الإعلام"
app_description = "بوابة برنامج تدريب الخريجين الجدد"
app_email = "it@momc.gov.sy"
app_license = "MIT"
required_apps = ["frappe"]

# Ministry identity on this app's desk screens (scoped by desk.js).
app_include_css = ["/assets/momc_training/css/desk.css"]
app_include_js = ["/assets/momc_training/js/desk.js"]

after_install = "momc_training.install.after_install"
after_migrate = "momc_training.install.after_migrate"

# Applicant sessions live in Redis and expire on their own; this sweeps
# exam attempts whose time ran out while the browser was closed.
scheduler_events = {
    "cron": {
        "*/5 * * * *": ["momc_training.exam.service.expire_overdue_attempts"],
    },
}

# The portal lives under /training/* (www/training). Applicants never hold a
# Frappe user: their accounts and sessions are separate (utils/session.py).
