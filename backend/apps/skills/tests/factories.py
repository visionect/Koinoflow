import factory

from apps.skills.models import (
    Skill,
    SkillExecutionSpec,
    SkillSecretDeclaration,
    SkillSecretValue,
    SkillVersion,
    VersionFile,
)
from apps.skills.secret_crypto import encrypt_secret_value


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


class SkillExecutionSpecFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SkillExecutionSpec

    skill = factory.SubFactory(SkillFactory)
    version = factory.SubFactory(SkillVersionFactory, skill=factory.SelfAttribute("..skill"))


class SkillSecretDeclarationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SkillSecretDeclaration

    spec = factory.SubFactory(SkillExecutionSpecFactory)
    name = factory.Sequence(lambda n: f"SECRET_{n}")
    scope = "workspace"
    required = True
    description = ""


class SkillSecretValueFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SkillSecretValue

    skill = factory.SubFactory(SkillFactory)
    workspace = factory.LazyAttribute(lambda o: o.skill.department.team.workspace)
    name = factory.Sequence(lambda n: f"SECRET_{n}")
    scope = "workspace"
    last_set_by = None
    kms_key_version = ""
    wrapped_dek = b""
    ciphertext = b""

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        obj = super()._create(model_class, *args, **kwargs)
        encrypted = encrypt_secret_value("test-secret-value")
        obj.wrapped_dek = encrypted.wrapped_dek
        obj.ciphertext = encrypted.ciphertext
        obj.kms_key_version = encrypted.kms_key_version
        obj.save(update_fields=["wrapped_dek", "ciphertext", "kms_key_version", "updated_at"])
        return obj
