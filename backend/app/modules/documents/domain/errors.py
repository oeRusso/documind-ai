"""Errors of the documents module. Each one maps to an HTTP status via its base class."""

from uuid import UUID

from app.shared.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    ValidationError,
)


class DocumentNotFoundError(NotFoundError):
    """Also for documents of another organization and deleted ones: they do not exist here."""

    code = "document_not_found"
    message = "Documento no encontrado"


class DocumentVersionNotFoundError(NotFoundError):
    code = "document_version_not_found"
    message = "Versión no encontrada"


class CannotDeleteDocumentError(ForbiddenError):
    code = "cannot_delete_document"
    message = "Solo podés borrar los documentos que subiste vos"


class FileTooLargeError(PayloadTooLargeError):
    code = "file_too_large"

    def __init__(self, max_mb: int) -> None:
        super().__init__(f"El archivo supera el máximo de {max_mb} MB")


class UnsupportedFileTypeError(UnsupportedMediaTypeError):
    code = "unsupported_file_type"
    message = "Tipo de archivo no permitido. Se aceptan PDF, DOCX, TXT y Markdown"


class FileTypeMismatchError(UnsupportedMediaTypeError):
    """The extension says one thing and the content another (e.g. an .exe renamed to .pdf)."""

    code = "file_type_mismatch"
    message = "El contenido del archivo no coincide con su extensión"


class EmptyFileError(ValidationError):
    code = "empty_file"
    message = "El archivo está vacío"


class CorruptFileError(ValidationError):
    code = "corrupt_file"
    message = "El archivo está dañado o no se puede leer"


class EncryptedFileError(ValidationError):
    code = "encrypted_file"
    message = "El archivo está protegido con contraseña. Subí una versión sin contraseña"


class TooManyPagesError(ValidationError):
    code = "too_many_pages"

    def __init__(self, max_pages: int) -> None:
        super().__init__(f"El documento supera el máximo de {max_pages} páginas")


class DuplicateDocumentError(ConflictError):
    """The same bytes (same SHA-256) are already in this organization."""

    code = "duplicate_document"

    def __init__(self, existing_document_id: UUID, existing_title: str) -> None:
        super().__init__(
            f"Este archivo ya está cargado en «{existing_title}»",
            details=[{"document_id": str(existing_document_id)}],
        )
