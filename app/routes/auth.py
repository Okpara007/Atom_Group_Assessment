from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import JWT_SECRET_KEY, JWT_EXPIRY

router = APIRouter()
security = HTTPBearer(auto_error=False)

class LoginRequest(BaseModel):
    username: str
    password: str

fake_users_db = {
    "user1": {
        "username": "user1",
        "password": "password123",
    }
}

def create_access_token(data: dict, expires_delta: timedelta = timedelta(minutes=JWT_EXPIRY)):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm="HS256")
    return encoded_jwt


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    return username

@router.post("/login")
async def login(request: LoginRequest):
    user = fake_users_db.get(request.username)
    if user is None or user["password"] != request.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(data={"sub": request.username})

    return {"access_token": access_token, "token_type": "bearer"}
