import factory

from apps.processes.models import Process, ProcessVersion, VersionFile


class ProcessFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Process

    department = factory.SubFactory("apps.orgs.tests.factories.DepartmentFactory")
    title = factory.Sequence(lambda n: f"Process {n}")
    slug = factory.Sequence(lambda n: f"process-{n}")


class ProcessVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProcessVersion

    process = factory.SubFactory(ProcessFactory)
    version_number = factory.Sequence(lambda n: n + 1)
    content_md = "# Sample Process\n\nStep 1: Do the thing."
    change_summary = "Initial version"


class VersionFileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VersionFile

    version = factory.SubFactory(ProcessVersionFactory)
    path = factory.Sequence(lambda n: f"scripts/file_{n}.py")
    content = "# generated"
    file_type = "python"
    size_bytes = factory.LazyAttribute(lambda o: len(o.content.encode()))
    is_deleted = False
