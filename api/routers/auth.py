from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from api.dependencies import verify_password, create_access_token, hash_password
from api.models import Token

router = APIRouter()

# One hardcoded user for now
FAKE_USER = {
    "username": "analyst",
    "hashed_password": hash_password("healthtrack123")
}

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # TODO: verify username exists
    # TODO: verify password with verify_password()
    # TODO: create and return token with create_access_token()
    ...