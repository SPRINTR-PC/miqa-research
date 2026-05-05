import logging
import os

try:
    from opentelemetry.sdk._logs import LoggingHandler
except ImportError:
    # Fallback to a no-op handler if OpenTelemetry is not installed
    class LoggingHandler(logging.Handler):
        def emit(self, record):
            pass

class OTelElasticsearchHandler(LoggingHandler):
    """
    A logging handler that sends logs in OpenTelemetry format to an OTLP-compatible backend 
    (like Elasticsearch with OTLP support).
    """
    _provider_initialized = False

    def __init__(self, *args, **kwargs):
        if not OTelElasticsearchHandler._provider_initialized:
            self._setup_otel_sdk()
            OTelElasticsearchHandler._provider_initialized = True
        
        # Get the global logger provider
        try:
            from opentelemetry import _logs
            provider = _logs.get_logger_provider()
            kwargs['logger_provider'] = provider
        except ImportError:
            pass
        super().__init__(*args, **kwargs)

    def _setup_otel_sdk(self):
        # Read settings (defaulting to environment variables if not in settings)
        try:
            from django.conf import settings
            endpoint = getattr(settings, 'OTLP_ENDPOINT', os.getenv('MIRES_OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318/v1/logs'))
            protocol = getattr(settings, 'OTLP_PROTOCOL', os.getenv('MIRES_OTEL_EXPORTER_OTLP_PROTOCOL', 'http'))
            service_name = getattr(settings, 'OTLP_SERVICE_NAME', 'miqa-research')
            insecure = getattr(settings, 'OTLP_INSECURE', True)
        except Exception:
            endpoint = os.getenv('MIRES_OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318/v1/logs')
            protocol = os.getenv('MIRES_OTEL_EXPORTER_OTLP_PROTOCOL', 'http')
            service_name = os.getenv('MIRES_OTEL_SERVICE_NAME', 'miqa-research')
            insecure = os.getenv('MIRES_OTEL_EXPORTER_OTLP_INSECURE', 'True').lower() == 'true'

        try:
            from opentelemetry.sdk.resources import Resource
            resource = Resource.create({
                "service.name": service_name,
            })

            from opentelemetry.sdk._logs import LoggerProvider
            provider = LoggerProvider(resource=resource)
            from opentelemetry import _logs
            _logs.set_logger_provider(provider)

            if protocol == 'grpc':
                from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
            else:
                from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

            exporter = OTLPLogExporter(endpoint=endpoint, insecure=insecure)
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
            provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
        except ImportError:
            # OpenTelemetry packages not installed, fall back or ignore
            pass
