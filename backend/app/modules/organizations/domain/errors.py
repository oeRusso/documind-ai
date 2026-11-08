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


class InvitationNotFoundError(NotFoundError):
    code = "invitation_not_found"
    message = "La invitación no existe, ya se usó o fue revocada"


class InvitationExpiredError(ConflictError):
    code = "invitation_expired"
    message = "La invitación venció: pedí una nueva"


class InvitationAlreadyPendingError(ConflictError):
    code = "invitation_already_pending"
    message = "Ya hay una invitación pendiente para ese email"


class AlreadyMemberError(ConflictError):
    code = "already_member"
    message = "Esa persona ya es miembro de la organización"


class InvitationEmailMismatchError(ForbiddenError):
    code = "invitation_email_mismatch"
    message = "Esta invitación es para otro email"
