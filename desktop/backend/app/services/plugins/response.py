from app.utils.response import ResponseWrapper


class PluginResponse:
    """Plugin API boundary preserving the product {code,msg,data} envelope."""

    success = staticmethod(ResponseWrapper.success)
    error = staticmethod(ResponseWrapper.error)
