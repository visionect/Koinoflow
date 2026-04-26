import httpx

from config import API_BASE_URL, logger


class KoinoflowAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"API error {status_code}: {message}")


class KoinoflowAPIClient:
    """
    HTTP client for the Django API.

    The token_data comes from introspecting the user's OAuth access token.
    Since Django is both the authorization server and the resource server for
    the API, we re-use the validated access token for internal API calls.
    Django's OAuthTokenAuthentication resolves the user and workspace context.
    """

    def __init__(self, token_data: dict):
        self.base_url = API_BASE_URL
        self.token_data = token_data

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token_data.get('_raw_token', '')}"}

    async def get_skill(self, slug: str, version: int | None = None) -> dict:
        async with httpx.AsyncClient() as client:
            if version is not None:
                url = f"{self.base_url}/skills/{slug}/versions/{version}"
            else:
                url = f"{self.base_url}/skills/{slug}"
            response = await client.get(url, headers=self._headers())
            if not response.is_success:
                raise KoinoflowAPIError(response.status_code, response.text)
            return response.json()

    async def list_skills(
        self,
        department: str | None = None,
        team: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        async with httpx.AsyncClient() as client:
            params: dict[str, str | int] = {"status": "published", "limit": limit, "offset": offset}
            if department:
                params["department"] = department
            if team:
                params["team"] = team
            if search:
                params["search"] = search
            response = await client.get(
                f"{self.base_url}/skills",
                headers=self._headers(),
                params=params,
            )
            if not response.is_success:
                raise KoinoflowAPIError(response.status_code, response.text)
            return response.json()

    async def discover_skills(
        self,
        query: str,
        department: str | None = None,
        team: str | None = None,
        limit: int = 10,
    ) -> dict:
        async with httpx.AsyncClient() as client:
            params: dict[str, str | int] = {
                "query": query,
                "limit": min(max(limit, 1), 25),
            }
            if department:
                params["department"] = department
            if team:
                params["team"] = team
            response = await client.get(
                f"{self.base_url}/skills/discover",
                headers=self._headers(),
                params=params,
            )
            if not response.is_success:
                raise KoinoflowAPIError(response.status_code, response.text)
            return response.json()

    async def get_effective_settings(self) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/settings",
                headers=self._headers(),
            )
            if not response.is_success:
                raise KoinoflowAPIError(response.status_code, response.text)
            return response.json()

    async def log_usage(
        self,
        skill_id: str,
        version_number: int,
        client_id: str,
        client_type: str,
        tool_name: str = "",
    ) -> None:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.base_url}/usage",
                    headers=self._headers(),
                    json={
                        "skill_id": skill_id,
                        "version_number": version_number,
                        "client_id": client_id,
                        "client_type": client_type,
                        "tool_name": tool_name,
                    },
                )
        except Exception:
            logger.warning("Failed to log usage event", exc_info=True)

    async def get_skill_files(self, slug: str, version: int) -> list[dict]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/skills/{slug}/versions/{version}/files",
                headers=self._headers(),
            )
            if not response.is_success:
                raise KoinoflowAPIError(response.status_code, response.text)
            return response.json()

    async def get_skill_file(self, slug: str, version: int, path: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/skills/{slug}/versions/{version}/files/{path}",
                headers=self._headers(),
            )
            if not response.is_success:
                raise KoinoflowAPIError(response.status_code, response.text)
            return response.json()

    async def create_skill_version(
        self,
        slug: str,
        *,
        content_md: str,
        frontmatter_yaml: str,
        change_summary: str,
    ) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/skills/{slug}/versions",
                headers=self._headers(),
                json={
                    "content_md": content_md,
                    "frontmatter_yaml": frontmatter_yaml,
                    "change_summary": change_summary,
                },
            )
            if not response.is_success:
                raise KoinoflowAPIError(response.status_code, response.text)
            return response.json()
