from momc_training.utils.portal import build, home_for, redirect


def get_context(context):
    build(context, "home")
    if context.applicant:
        redirect(home_for(context.applicant.status))
    redirect("/training/register")
