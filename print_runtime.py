from __future__ import annotations

from pathlib import Path

from portable_temp import get_portable_temp_dir
import threading

from print_layout import resolve_layout_options
from printing.documents import DocumentPipeline
from printing.domain import PrintOptions, PrintRequest
from printing.service import IppPrintService


_PIPELINE_LOCK = threading.Lock()
_PIPELINE: DocumentPipeline | None = None
_PIPELINE_KEY: tuple[str, str] | None = None


def build_document_pipeline(config_repo, logger) -> DocumentPipeline:
    global _PIPELINE, _PIPELINE_KEY
    settings = config_repo.get_full_config().get("settings", {})
    root = Path(get_portable_temp_dir()) / "ipp-printing"
    libreoffice_path = str(settings.get("libreoffice_path") or "")
    key = (str(root.resolve()), libreoffice_path.lower())
    with _PIPELINE_LOCK:
        if _PIPELINE is None or _PIPELINE_KEY != key:
            if _PIPELINE is not None:
                _PIPELINE.stop()
            pipeline = DocumentPipeline(
                libreoffice_path,
                root / "document-cache",
                root / "jobs",
                root / "libreoffice-profile",
                logger,
            )
            pipeline.start()
            _PIPELINE = pipeline
            _PIPELINE_KEY = key
        return _PIPELINE


def stop_document_pipelines() -> None:
    global _PIPELINE, _PIPELINE_KEY
    with _PIPELINE_LOCK:
        pipeline = _PIPELINE
        _PIPELINE = None
        _PIPELINE_KEY = None
    if pipeline:
        pipeline.stop()


def resolve_print_options(config_repo, print_options) -> PrintOptions:
    """Resolve explicit options and Edge defaults into one local print policy."""
    raw_options = dict(print_options or {})
    full_config = config_repo.get_full_config() if config_repo else {}
    settings = full_config.get("settings", {}) if isinstance(full_config, dict) else {}
    raw_options.update(resolve_layout_options(raw_options, settings))
    return PrintOptions.from_mapping(raw_options)


def build_print_service(config_repo, logger) -> IppPrintService:
    return IppPrintService(
        build_document_pipeline(config_repo, logger),
        logger,
    )


def build_print_request(
    config_repo,
    *,
    job_id,
    printer_id,
    file_path,
    source_name,
    print_options,
    content_hash=None,
    source_kind="",
    source_supplier=None,
    delete_source_after_standardize=False,
) -> PrintRequest:
    printer = config_repo.get_printer_by_id(printer_id) if printer_id else None
    if not printer:
        raise ValueError(f"managed printer not found: {printer_id!r}")
    return PrintRequest(
        job_id=str(job_id),
        printer_id=str(printer.get("id") or printer_id or "") or None,
        printer_name=str(printer.get("name") or ""),
        printer_uuid=str(printer.get("printer_uuid") or ""),
        ipp_uri=str(printer.get("ipp_uri") or ""),
        source_path=Path(file_path) if file_path else None,
        source_name=source_name or (Path(file_path).name if file_path else ""),
        options=resolve_print_options(config_repo, print_options),
        content_hash=content_hash,
        source_kind=source_kind,
        source_supplier=source_supplier,
        delete_source_after_standardize=delete_source_after_standardize,
    )
