from ninja import Schema


class SignInRequest(Schema):
    access_token: str


class LocalUserOut(Schema):
    id: str
    email: str
    username: str
    is_new_user: bool


class ExternalIdentityOut(Schema):
    provider: str
    provider_user_id: str
    email: str
    email_verified: bool


class SignInResponse(Schema):
    user: LocalUserOut
    external_identity: ExternalIdentityOut