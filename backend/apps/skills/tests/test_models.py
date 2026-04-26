import pytest
from django.db import IntegrityError

from apps.orgs.tests.factories import DepartmentFactory
from apps.skills.models import SkillVersion
from apps.skills.tests.factories import SkillFactory, SkillVersionFactory


@pytest.mark.django_db
class TestSkill:
    def test_slug_unique_within_department(self):
        dept = DepartmentFactory()
        SkillFactory(department=dept, slug="onboarding")
        with pytest.raises(IntegrityError):
            SkillFactory(department=dept, slug="onboarding")

    def test_slug_reusable_across_departments(self):
        p1 = SkillFactory(slug="onboarding")
        p2 = SkillFactory(slug="onboarding")
        assert p1.department != p2.department


@pytest.mark.django_db
class TestSkillVersion:
    def test_ordering_by_version_number_desc(self):
        skill = SkillFactory()
        v1 = SkillVersionFactory(skill=skill, version_number=1)
        v3 = SkillVersionFactory(skill=skill, version_number=3)
        v2 = SkillVersionFactory(skill=skill, version_number=2)
        versions = list(SkillVersion.objects.filter(skill=skill))
        assert versions == [v3, v2, v1]

    def test_duplicate_version_number_raises(self):
        skill = SkillFactory()
        SkillVersionFactory(skill=skill, version_number=1)
        with pytest.raises(IntegrityError):
            SkillVersionFactory(skill=skill, version_number=1)
