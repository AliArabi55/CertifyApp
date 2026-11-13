"""Public account registration, email verification, sessions, and password recovery."""
from __future__ import annotations

import os
import sqlite3
import time
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from . import auth_mail, auth_store
from .auth_security import hash_password, normalize_email, valid_email, verify_password

router = APIRouter(prefix="/api/auth", tags=["authentication"])
SESSION_COOKIE = "certify_session"
SESSION_SECONDS = 7 * 24 * 60 * 60
VERIFY_SECONDS = 30 * 60
RESET_SECONDS = 30 * 60


class EmailPassword(BaseModel):
    email: str
    password: str


class TokenBody(BaseModel):
    token: str


class EmailOnly(BaseModel):
    email: str


class PasswordReset(TokenBody):
    password: str


def _new_action_token(user_id: str, purpose: str, lifetime: int) -> str:
    return auth_store.create_action_token(user_id, purpose, int(time.time()) + lifetime)


def _send_action(email: str, subject: str, action: str, token: str) -> None:
    try:
        auth_mail.send_action_email(email, subject, action, token)
    except Exception as exc:
        raise HTTPException(503, "Account email could not be sent. Please try again later.") from exc


@router.post("/register", status_code=202)
def register(payload: EmailPassword):
    if not auth_mail.is_configured():
        raise HTTPException(503, "Account registration is temporarily unavailable.")
    email = normalize_email(payload.email)
    if not valid_email(email):
        raise HTTPException(400, "Enter a valid email address.")
    password_hash = hash_password(payload.password)
    user = auth_store.get_user_by_email(email)
    if user and user["verified"]:
        return {"message": "If this address can be registered, check your inbox for a verification link."}
    user_id = user["id"] if user else uuid.uuid4().hex
    if not user:
        owner_email = normalize_email(os.environ.get("CERTIFY_OWNER_EMAIL", ""))
        try:
            auth_store.create_user(
                user_id,
                email,
                password_hash,
                email == owner_email,
                int(time.time()),
            )
        except sqlite3.IntegrityError:
            return {"message": "If this address can be registered, check your inbox for a verification link."}
    else:
        auth_store.update_password(user_id, password_hash)
    token = _new_action_token(user_id, "verify", VERIFY_SECONDS)
    _send_action(email, "Verify your Certify account", "verify", token)
    return {"message": "Check your email for a verification link."}


@router.post("/verify")
def verify_account(payload: TokenBody):
    user = auth_store.verify_action_token(payload.token, "verify", int(time.time()))
    if not user:
        raise HTTPException(400, "This verification link is invalid or has expired.")
    if user["is_admin"]:
        auth_store.claim_legacy_projects(user["id"])
    return {"verified": True, "message": "Email verified. You can now sign in."}


@router.post("/login")
def login(payload: EmailPassword, response: Response):
    email = normalize_email(payload.email)
    user = auth_store.get_user_by_email(email) if valid_email(email) else None
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "Email or password is incorrect.")
    if not user["verified"]:
        raise HTTPException(403, "Verify your email before signing in.")
    session_token, csrf_token = auth_store.create_session(
        user["id"], int(time.time()) + SESSION_SECONDS
    )
    secure = os.environ.get("CERTIFY_COOKIE_SECURE", "1" if os.environ.get("WEBSITE_HOSTNAME") else "0") == "1"
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    return {"email": user["email"], "is_admin": bool(user["is_admin"]), "csrf_token": csrf_token}


@router.get("/me")
def current_user(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "Sign in to continue.")
    session_token = request.cookies.get(SESSION_COOKIE, "")
    csrf_token = auth_store.rotate_session_csrf(session_token)
    return {"email": user["email"], "is_admin": bool(user["is_admin"]), "csrf_token": csrf_token}


@router.post("/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        auth_store.delete_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")
    return {"signed_out": True}


@router.post("/password-reset-request", status_code=202)
def request_password_reset(payload: EmailOnly):
    email = normalize_email(payload.email)
    user = auth_store.get_user_by_email(email) if valid_email(email) else None
    if user and user["verified"] and auth_mail.is_configured():
        token = _new_action_token(user["id"], "reset", RESET_SECONDS)
        _send_action(email, "Reset your Certify password", "reset", token)
    return {"message": "If a verified account exists, a password reset link will arrive by email."}


@router.post("/password-reset")
def reset_password(payload: PasswordReset):
    if not 12 <= len(payload.password) <= 256:
        raise HTTPException(400, "Password must contain 12 to 256 characters.")
    user = auth_store.verify_action_token(payload.token, "reset", int(time.time()))
    if not user:
        raise HTTPException(400, "This password reset link is invalid or has expired.")
    auth_store.update_password(user["id"], hash_password(payload.password))
    return {"reset": True, "message": "Password updated. Sign in with your new password."}