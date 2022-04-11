# -*- coding: utf-8 -*-
import logging
import time

HAS_SENTRY_SDK = True
try:
    import sentry_sdk
except ImportError:  # pragma: no cover
    HAS_SENTRY_SDK = False  # pragma: no cover


from odoo import models
from odoo.http import request
from odoo.service import wsgi_server

_logger = logging.getLogger(__name__)

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    # def _register_hook(self):
    #     """🐒-patch XML-RPC controller to know remote address."""
    #     super()._register_hook()
    #     original_fn = wsgi_server.application_unproxied

    #     def _patch(environ, start_response):
    #         current_thread().environ = environ
    #         return original_fn(environ, start_response)

    #     wsgi_server.application_unproxied = _patch

    @classmethod
    def _serve_page(cls):
        wsgi_server_init = wsgi_server
        response = super(IrHttp, cls)._serve_page()
        if response and HAS_SENTRY_SDK and response.headers:
            with sentry_sdk.start_span() as span:
            # Header sentry-trace
            # The header is used for trace propagation. SDKs use the header to continue traces from upstream services (incoming HTTP requests), and to propagate tracing information to downstream services (outgoing HTTP requests).
            # sentry-trace = traceid-spanid-sampled
            # sampled is optional. So at a minimum, it's expected:
            # sentry-trace = traceid-spanid
            # To offer a minimal compatibility with the W3C traceparent header (without the version prefix) and Zipkin's b3 headers (which consider both 64 and 128 bits for traceId valid)
            # , the sentry-trace header should have a traceId of 128 bits encoded in 32 hex chars and a spanId of 64 bits encoded in 16 hex chars.
            # To avoid confusion with the W3C traceparent header (to which our header is similar but not identical), we call it simply sentry-trace. No version is being defined in the header.

                response.headers.set('sentry-trace', span.span_id ) #Transaction.

        return response
