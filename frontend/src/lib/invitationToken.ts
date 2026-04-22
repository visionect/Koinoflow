const INVITATION_TOKEN_KEY = "kf_invitation_token"

export function storeInvitationToken(token: string) {
  sessionStorage.setItem(INVITATION_TOKEN_KEY, token)
}

export function consumeInvitationToken(): string | null {
  const token = sessionStorage.getItem(INVITATION_TOKEN_KEY)
  if (token) {
    sessionStorage.removeItem(INVITATION_TOKEN_KEY)
  }
  return token
}
