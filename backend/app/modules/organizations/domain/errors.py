from app.shared.errors import ConflictError, NotFoundError, ValidationError


class OrganizationNotFoundError(NotFoundError):
    code = "organization_not_found"
    message = "Organización no encontrada"


class OrganizationSlugTakenError(ConflictError):
    code = "organization_slug_taken"
    message = "Ya existe una organización con ese slug"


class InvalidOrganizationError(ValidationError):
    code = "invalid_organization"
    message = "Los datos de la organización no son válidos"
