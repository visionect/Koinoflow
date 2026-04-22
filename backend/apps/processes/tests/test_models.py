import pytest
from django.db import IntegrityError

from apps.orgs.tests.factories import DepartmentFactory
from apps.processes.models import ProcessVersion
from apps.processes.tests.factories import ProcessFactory, ProcessVersionFactory


@pytest.mark.django_db
class TestProcess:
    def test_slug_unique_within_department(self):
        dept = DepartmentFactory()
        ProcessFactory(department=dept, slug="onboarding")
        with pytest.raises(IntegrityError):
            ProcessFactory(department=dept, slug="onboarding")

    def test_slug_reusable_across_departments(self):
        p1 = ProcessFactory(slug="onboarding")
        p2 = ProcessFactory(slug="onboarding")
        assert p1.department != p2.department


@pytest.mark.django_db
class TestProcessVersion:
    def test_ordering_by_version_number_desc(self):
        process = ProcessFactory()
        v1 = ProcessVersionFactory(process=process, version_number=1)
        v3 = ProcessVersionFactory(process=process, version_number=3)
        v2 = ProcessVersionFactory(process=process, version_number=2)
        versions = list(ProcessVersion.objects.filter(process=process))
        assert versions == [v3, v2, v1]

    def test_duplicate_version_number_raises(self):
        process = ProcessFactory()
        ProcessVersionFactory(process=process, version_number=1)
        with pytest.raises(IntegrityError):
            ProcessVersionFactory(process=process, version_number=1)
