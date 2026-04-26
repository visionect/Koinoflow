import factory

from apps.skills.models import Skill, SkillVersion, VersionFile


class SkillFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Skill

    department = factory.SubFactory("apps.orgs.tests.factories.DepartmentFactory")
    title = factory.Sequence(lambda n: f"Skill {n}")
    slug = factory.Sequence(lambda n: f"skill-{n}")


class SkillVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SkillVersion

    skill = factory.SubFactory(SkillFactory)
    version_number = factory.Sequence(lambda n: n + 1)
    content_md = "# Sample Skill\n\nStep 1: Do the thing."
    change_summary = "Initial version"


class VersionFileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VersionFile

    version = factory.SubFactory(SkillVersionFactory)
    path = factory.Sequence(lambda n: f"scripts/file_{n}.py")
    content = "# generated"
    file_type = "python"
    size_bytes = factory.LazyAttribute(lambda o: len(o.content.encode()))
    is_deleted = False
