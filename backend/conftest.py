import pytest
from django.test import Client

from apps.orgs.enums import RoleChoices


@pytest.fixture
def api_client():
    from ninja.testing import TestClient

    from config.api import api

    return TestClient(api)


@pytest.fixture
def auth_client(admin_membership):
    """Django test client logged in as an admin user with workspace context."""
    client = Client()
    client.force_login(admin_membership.user)
    return client


@pytest.fixture
def admin_membership():
    from apps.orgs.tests.factories import MembershipFactory

    return MembershipFactory(role=RoleChoices.ADMIN)


@pytest.fixture
def team_manager_membership(admin_membership):
    from apps.orgs.tests.factories import MembershipFactory, TeamFactory

    team = TeamFactory(workspace=admin_membership.workspace)
    return MembershipFactory(
        role=RoleChoices.TEAM_MANAGER, workspace=admin_membership.workspace, team=team
    )


@pytest.fixture
def member_membership(admin_membership):
    from apps.orgs.tests.factories import DepartmentFactory, MembershipFactory, TeamFactory

    team = TeamFactory(workspace=admin_membership.workspace)
    dept = DepartmentFactory(team=team)
    membership = MembershipFactory(role=RoleChoices.MEMBER, workspace=admin_membership.workspace)
    membership.departments.add(dept)
    return membership
