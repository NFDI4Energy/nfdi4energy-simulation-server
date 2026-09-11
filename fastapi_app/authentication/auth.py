import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.concurrency import run_in_threadpool

from fastapi_app.persistence.database_dependencies import get_db
from fastapi_app.persistence.models_db import User

logger = logging.getLogger(__name__)
LOCAL_USER_ID = "simaas-local-development"
LOCAL_ISSUER = "urn:simaas:local-development"

def create_oauth(settings):
    if settings.auth_disabled:
        logger.warning("AUTH_DISABLED=true: sign-in grants access to a shared local development account")
        return None
    oauth = OAuth()
    oauth.register(name="simaas", client_id=settings.oidc_client_id,
                   client_secret=settings.oidc_client_secret,
                   server_metadata_url=settings.oidc_discovery_url,
                   client_kwargs={"scope": "openid profile email"})
    return oauth

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/login")
async def login(request: Request):
    if request.app.state.settings.auth_disabled:
        user_id = await run_in_threadpool(save_local_user, request.app.state.session_factory)
        request.session.clear()
        request.session.update({"user_id": user_id, "auth_mode": "local"})
        return RedirectResponse(url="/dashboard/")
    try:
        return await request.app.state.oauth.simaas.authorize_redirect(request, request.app.state.settings.oidc_redirect_uri)
    except Exception:
        logger.exception("Failed to redirect to OIDC provider")
        return JSONResponse(
            status_code=502,
            content={
                "error": "Failed to connect to the authentication provider. "
                         "Please verify that the server has internet access and can reach the OIDC provider."
            }
        )


@router.get("/callback")
async def auth_callback(request: Request):
    if request.app.state.settings.auth_disabled:
        raise HTTPException(status_code=404, detail="OIDC is disabled")
    try:
        token = await request.app.state.oauth.simaas.authorize_access_token(request)
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

    user_id = await run_in_threadpool(save_user, request.app.state.session_factory,
                                    user_info, request.app.state.settings.oidc_discovery_url)
    request.session.clear()
    request.session["user_id"] = user_id
    return RedirectResponse(url="/dashboard/")


def save_user(factory, user_info, discovery_url):
    with factory() as db:
        return upsert_user(db, user_info, discovery_url)


def save_local_user(factory):
    with factory() as db:
        user = db.query(User).filter(User.id == LOCAL_USER_ID).first()
        if user is None:
            user = User(id=LOCAL_USER_ID, sub=LOCAL_USER_ID, issuer=LOCAL_ISSUER,
                        email="dev@simaas.local", display_name="Local Development")
            db.add(user)
            db.commit()
        elif user.issuer != LOCAL_ISSUER:
            raise RuntimeError("Local development identity is already occupied")
        return user.id


def upsert_user(db, user_info, discovery_url):
    sub = user_info["sub"]
    user = db.query(User).filter(User.sub == sub).first()

    if user is None:
        user = User(
            sub=sub,
            email=user_info.get("email"),
            display_name=user_info.get("name"),
            issuer=user_info.get("iss", discovery_url),
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

    return user.id


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    logger.info("Local session cleared. Redirecting to dashboard.")
    return RedirectResponse(url="/dashboard/")


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
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
    # Re-enabling OIDC immediately invalidates development sessions.
    local_session = request.session.get("auth_mode") == "local" or user_id == LOCAL_USER_ID
    if local_session and not request.app.state.settings.auth_disabled:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_login(request: Request) -> User:
    if not request.session.get("user_id"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Return detached user data; streams must not retain a database session.
    with request.app.state.session_factory() as db:
        user = get_current_user_or_none(request, db)
        if user is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        db.expunge(user)
        return user
