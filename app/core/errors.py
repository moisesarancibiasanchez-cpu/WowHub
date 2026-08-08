"""Excepciones de dominio reutilizables."""
from fastapi import HTTPException, status


class WowHubError(HTTPException):
    """Base para errores WowHub."""
    pass


class NotFoundError(WowHubError):
    def __init__(self, resource: str = "Recurso"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} no encontrado",
        )


class ConflictError(WowHubError):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=message,
        )


class ForbiddenError(WowHubError):
    def __init__(self, message: str = "Acceso denegado"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message,
        )


class UnauthorizedError(WowHubError):
    def __init__(self, message: str = "No autenticado"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=message,
            headers={"WWW-Authenticate": "Bearer"},
        )


class ValidationError(WowHubError):
    def __init__(self, message: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=message,
        )
