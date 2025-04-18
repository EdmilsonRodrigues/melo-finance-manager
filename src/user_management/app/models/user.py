from dataclasses import dataclass, field
from typing import Self

import bcrypt
from email_validator import validate_email

from app.config import Unset, UnsetType
from app.models.base import BaseClass, BaseModel
from app.models.errors import (
    UnauthorizedException,
    UnprocessableContentException,
)
from app.services.auth_service import AuthService
from app.sessions import db


class User(BaseModel):
    """SQLAlchemy model for the users table."""

    __tablename__ = 'users'

    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)
    full_name = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(10), nullable=False)

    @staticmethod
    def hash_password(password: str) -> bytes:
        """
        Hashes the password using bcrypt.

        :param password: The password to hash.
        :type password: str
        :return: The hashed password.
        :rtype: bytes
        """
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed_password

    def check_password(self, password: str) -> bool:
        """
        Checks if the provided password matches the stored hash.

        :param password: The password to check.
        :type password: str
        :return: True if the password matches, False otherwise.
        :rtype: bool
        """
        return bcrypt.checkpw(
            password.encode('utf-8'), self.password.encode('utf-8')
        )

    @classmethod
    def login(cls, email: str, password: str) -> tuple[str, str]:
        """
        Logs in a user.

        :param email: The email of the user.
        :type email: str
        :param password: The password of the user.
        :type password: str
        :return: A tuple containing the JWT token and the expiration time.
        :rtype: tuple[str, str]
        """
        try:
            # breakpoint()
            user = cls.query.filter_by(email=email).first()
            if user is None:
                raise UnauthorizedException('User not found')
            if user.check_password(password):
                return AuthService.generate_token(user.id)
            raise UnauthorizedException('Password is incorrect')
        except Exception as exc:
            raise UnauthorizedException('Invalid credentials') from exc

    @classmethod
    def authenticate(cls, token: str) -> Self:
        """
        Authenticates a user.

        :param token: The JWT token.
        :type token: str
        :return: The user if the authentication is successful,
        raises an exception otherwise.
        :rtype: User
        """
        try:
            match token.split(' '):
                case ['Bearer', token]:
                    user_id = AuthService.verify_token(token)
                    return cls.get_one(id=user_id)
                case _:
                    raise UnauthorizedException('Invalid token')
        except Exception as exc:
            raise UnauthorizedException(
                'Invalid Token', headers={'WWW-Authenticate': 'bearer'}
            ) from exc


@dataclass
class UserResponse(BaseClass):
    """Dataclass for the user response serialization."""

    email: str
    full_name: str
    role: str

    def __post_init__(self):
        try:
            self.email = validate_email(self.email).normalized
        except Exception as exc:
            raise UnprocessableContentException(exc) from exc


@dataclass
class CreateUser:
    """Dataclass for the user creation request serialization."""

    email: str
    password: str
    full_name: str
    role: str = field(init=False, default='user')

    def __post_init__(self):
        self.__dict__['role'] = self.role
        try:
            self.email = validate_email(self.email).normalized
            self.password = User.hash_password(self.password).decode('utf-8')
        except Exception as exc:
            raise UnprocessableContentException(exc) from exc


@dataclass
class PatchUser:
    """Dataclass for the user update request serialization."""

    full_name: str | UnsetType = Unset


@dataclass
class PatchUserPassword:
    """Dataclass for the user password update request serialization."""

    old_password: str
    new_password: str

    def __post_init__(self):
        if self.new_password == self.old_password:
            raise UnprocessableContentException(
                'New password must be different from the old password'
            )
        try:
            self.new_password = User.hash_password(self.new_password).decode(
                'utf-8'
            )
        except Exception as exc:
            raise UnprocessableContentException(
                'Passwords are invalid'
            ) from exc


@dataclass
class PatchUserEmail:
    """Dataclass for the user email update request serialization."""

    email: str

    def __post_init__(self):
        try:
            self.email = validate_email(self.email).normalized
        except Exception as exc:
            raise UnprocessableContentException(exc) from exc


def get_patch_fields(
    data: dict,
) -> dict[str, str]:
    """
    Get the fields to patch from the request data.

    :param data: The request data.
    :type data: dict
    :return: The fields to patch.
    :rtype: dict[str, str]
    """

    match data:
        case {'email': email}:
            return vars(PatchUserEmail(email=email))

        case {'old_password': old_password, 'new_password': new_password}:
            return vars(
                PatchUserPassword(
                    old_password=old_password, new_password=new_password
                )
            )

        case {}:
            try:
                return {
                    key: value
                    for key, value in vars(PatchUser(**data)).items()
                    if value is not Unset
                }
            except TypeError as exc:
                raise UnprocessableContentException('Invalid data') from exc

    raise UnprocessableContentException('Invalid data')
