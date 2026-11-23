"""Single-admin login: bcrypt-checked credentials from env, JWT in an httpOnly cookie."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.config import Settings, get_settings

COOKIE_NAME = "optiserve_session"
JWT_ALGORITHM = "HS256"
# Compared against when the email is wrong, so a bad email and a bad password take the same time.
_DUMMY_HASH = bcrypt.hashpw(b"optiserve-dummy", bcrypt.gensalt()).decode()

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """Login form body."""

    email: str
    password: str


class UserResponse(BaseModel):
    """The signed-in admin."""

    email: str


class OkResponse(BaseModel):
    """Generic success response."""

    ok: bool = True


def hash_password(password: str) -> str:
    """Return a bcrypt hash suitable for ADMIN_PASSWORD_HASH."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against a bcrypt hash; False for a missing or malformed hash."""
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(email: str, settings: Settings) -> str:
    """Create a signed JWT for the admin."""
    now = datetime.now(timezone.utc)
    payload = {"sub": email, "iat": now, "exp": now + timedelta(hours=settings.jwt_expiry_hours)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def require_admin(request: Request, settings: Settings = Depends(get_settings)) -> str:
    """Dependency: return the admin email from a valid session cookie, else 401."""
    token = request.cookies.get(COOKIE_NAME)
    if not token or not settings.jwt_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has ended. Please sign in again.")
    email = payload.get("sub")
    if email != settings.admin_email:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    return email


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response, settings: Settings = Depends(get_settings)) -> UserResponse:
    """Check the admin credentials and set the session cookie."""
    if not (settings.admin_email and settings.admin_password_hash and settings.jwt_secret):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Login is not set up. Set ADMIN_EMAIL, ADMIN_PASSWORD_HASH and JWT_SECRET in backend/.env.",
        )
    email_ok = body.email.strip().lower() == settings.admin_email.strip().lower()
    password_ok = verify_password(body.password, settings.admin_password_hash if email_ok else _DUMMY_HASH)
    if not (email_ok and password_ok):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password.")
    response.set_cookie(
        COOKIE_NAME,
        create_token(settings.admin_email, settings),
        max_age=settings.jwt_expiry_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return UserResponse(email=settings.admin_email)


@router.post("/logout", response_model=OkResponse)
def logout(response: Response, settings: Settings = Depends(get_settings)) -> OkResponse:
    """Clear the session cookie."""
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax")
    return OkResponse()


@router.get("/me", response_model=UserResponse)
def me(email: str = Depends(require_admin)) -> UserResponse:
    """Return the signed-in admin, or 401."""
    return UserResponse(email=email)
