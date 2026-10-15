"""OTLP log export: the `MIRES_OTLP_*` settings as a stdlib logging handler (#293).

`settings.LOGGING` adds the handler to the root logger when `MIRES_OTLP_ENABLED` is set, so
every log record (the viewer first-render beacon among them) goes to the collector with its
`extra` fields as attributes. OTLP/HTTP (protobuf) only.
"""
import logging


def otlp_handler(endpoint: str, service_name: str) -> logging.Handler:
    """A logging handler exporting records in batches to the OTLP/HTTP logs `endpoint`."""
    # Imported here: settings imports this module, and OTel is only needed when enabled.
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource

    provider = LoggerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint)))
    return LoggingHandler(logger_provider=provider)


def otlp_logging_config(*, enabled: bool, endpoint: str, service_name: str) -> dict:
    """The `LOGGING["handlers"]` entry for OTLP export, or nothing when disabled."""
    if not enabled:
        return {}
    return {
        "otlp": {
            "()": "MiqaResearch.telemetry.otlp_handler",
            "endpoint": endpoint,
            "service_name": service_name,
        }
    }
