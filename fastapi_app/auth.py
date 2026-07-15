import os
import logging
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from authlib.integrations.starlette_client import OAuth, OAuthError

from database import get_db
from models_db import User

logger = logging.getLogger(__name__)

oauth = OAuth()

OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")
OIDC_DISCOVERY_URL = os.environ.get(
    "OIDC_DISCOVERY_URL",
    "https://regapp.nfdi-aai.de/oidc/realms/nfdi/.well-known/openid-configuration",
)
OIDC_REDIRECT_URI = os.environ.get(
    "OIDC_REDIRECT_URI",
    "https://localhost:5001/auth/callback",
)

oauth.register(
    name="simaas",
    client_id=OIDC_CLIENT_ID,
    client_secret=OIDC_CLIENT_SECRET,
    server_metadata_url=OIDC_DISCOVERY_URL,
    client_kwargs={
        "scope": "openid profile email",
    },
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/login")
async def login(request: Request):
    try:
        return await oauth.simaas.authorize_redirect(request, OIDC_REDIRECT_URI)
    except Exception as exc:
        logger.exception("Failed to redirect to OIDC provider")
        return JSONResponse(
            status_code=502,
            content={
                "error": "Failed to connect to the authentication provider. "
                         "Please verify that the server has internet access and can reach the OIDC provider."
            }
        )


@router.get("/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.simaas.authorize_access_token(request)
    except OAuthError as exc:
        logger.error("OIDC callback error: %s", exc)
        return JSONResponse(
            status_code=400,
            content={"error": f"Authentication failed: {exc.description}"},
        )

    user_info = token.get("userinfo")
    if user_info is None:
        return JSONResponse(
            status_code=400,
            content={"error": "No user information received from identity provider."},
        )

    sub = user_info.get("sub")
    if not sub:
        return JSONResponse(
            status_code=400,
            content={"error": "No subject identifier (sub) in token."},
        )

    # Upsert user: find existing by `sub`, or create a new record
    user = db.query(User).filter(User.sub == sub).first()

    if user is None:
        user = User(
            sub=sub,
            email=user_info.get("email"),
            display_name=user_info.get("name"),
            issuer=user_info.get("iss", OIDC_DISCOVERY_URL),
            raw_claims=dict(user_info),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("Created new user: sub=%s email=%s", sub, user.email)
    else:
        user.email = user_info.get("email", user.email)
        user.display_name = user_info.get("name", user.display_name)
        user.raw_claims = dict(user_info)
        db.commit()
        logger.info("Updated existing user: sub=%s", sub)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    logger.info("Local session cleared. Redirecting to dashboard.")
    return RedirectResponse(url="/dashboard/")


@router.get("/me")
async def me(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_or_none(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "sub": user.sub,
    }


def get_current_user_or_none(request: Request, db: Session) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    user = get_current_user_or_none(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
