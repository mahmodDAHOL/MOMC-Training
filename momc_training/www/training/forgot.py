from momc_training.utils.portal import build


def get_context(context):
    build(context, "forgot", signed_in=False)
