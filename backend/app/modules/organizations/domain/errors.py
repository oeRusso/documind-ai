from app.shared.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError


class OrganizationNotFoundError(NotFoundError):
    code = "organization_not_found"
    message = "Organización no encontrada"


class OrganizationSlugTakenError(ConflictError):
    code = "organization_slug_taken"
    message = "Ya existe una organización con ese slug"


class InvalidOrganizationError(ValidationError):
    code = "invalid_organization"
    message = "Los datos de la organización no son válidos"


class PermissionDeniedError(ForbiddenError):
    code = "forbidden"
    message = "Tu rol en esta organización no permite esta acción"


class LastOwnerError(ConflictError):
    code = "last_owner"
    message = "La organización tiene que conservar al menos un owner"


class MembershipNotFoundError(NotFoundError):
    code = "membership_not_found"
    message = "Miembro no encontrado"
