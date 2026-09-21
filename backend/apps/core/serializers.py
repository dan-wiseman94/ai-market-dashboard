"""Response serializers for ``GET /api/features/``.

These exist so ``@extend_schema`` can hand drf-spectacular a real shape: the endpoint
is read-only, so they are never used to validate input. The payload is split into four
typed arrays instead of one polymorphic list — a single array would force ``value`` to
a JSON field, which lands in the generated TypeScript as ``unknown`` and forces casts
on the page (the frontend's type-coverage floor does not allow that).

``label`` and ``source`` shadow attributes on DRF's ``Field`` base class, hence the
``type: ignore[assignment]`` on those declarations. There is no runtime conflict —
``SerializerMetaclass`` pops declared fields out of the class namespace — and the two
names are part of the response contract the page reads, so they stay.
"""

from __future__ import annotations

from rest_framework import serializers


class FeatureGroupSerializer(serializers.Serializer):
    """A rendered section of the Features page."""

    key = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    blurb = serializers.CharField()
    order = serializers.IntegerField()


class ChoiceSerializer(serializers.Serializer):
    value = serializers.CharField(allow_blank=True)
    label = serializers.CharField()  # type: ignore[assignment]


class RequirementSerializer(serializers.Serializer):
    """An external precondition (today: a connected data source).

    ``satisfied`` is nullable on purpose: the probe touches Redis and the provider
    health marker, so a failure degrades to "unknown" rather than claiming "not
    connected" and inviting the user to re-authorise something that is fine.
    """

    id = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    satisfied = serializers.BooleanField(allow_null=True)
    manage_path = serializers.CharField()


class _FeatureRowSerializer(serializers.Serializer):
    """Fields every row carries, whatever its control."""

    key = serializers.CharField()
    label = serializers.CharField()  # type: ignore[assignment]
    summary = serializers.CharField()
    help = serializers.CharField()
    group = serializers.CharField()
    order = serializers.IntegerField()
    scope = serializers.CharField()
    backing = serializers.CharField()
    value_type = serializers.CharField()
    editable = serializers.BooleanField()
    # Where a write goes, and the field name to send. Empty write_path = not writable.
    write_path = serializers.CharField(allow_blank=True)
    field = serializers.CharField(allow_blank=True)
    env_var = serializers.CharField(allow_blank=True)
    env_only_reason = serializers.CharField(allow_blank=True)
    costs_money = serializers.BooleanField()
    cost_note = serializers.CharField(allow_blank=True)
    retroactive = serializers.BooleanField()
    requires = serializers.ListField(child=serializers.CharField())
    requirement = RequirementSerializer(allow_null=True)
    provider_only = serializers.CharField(allow_blank=True)
    deep_link = serializers.CharField(allow_blank=True)


class FeatureToggleSerializer(_FeatureRowSerializer):
    """A boolean row.

    ``source`` is the provenance tri-state made visible: "override" when the singleton
    column holds an explicit value, "env" when the environment names it, "default"
    otherwise. ``default_value`` is what "Reset to default" actually restores (the
    env-or-shipped value), which is why it can differ from ``shipped_default``.
    """

    value = serializers.BooleanField()
    default_value = serializers.BooleanField()
    shipped_default = serializers.BooleanField(allow_null=True)
    override = serializers.BooleanField(allow_null=True)
    source = serializers.CharField()  # type: ignore[assignment]


class FeatureNumberSerializer(_FeatureRowSerializer):
    value = serializers.FloatField()
    default_value = serializers.FloatField()
    shipped_default = serializers.FloatField(allow_null=True)
    override = serializers.FloatField(allow_null=True)
    source = serializers.CharField()  # type: ignore[assignment]
    min_value = serializers.FloatField(allow_null=True)
    max_value = serializers.FloatField(allow_null=True)
    unit = serializers.CharField(allow_blank=True)
    is_float = serializers.BooleanField()


class FeatureTextSerializer(_FeatureRowSerializer):
    value = serializers.CharField(allow_blank=True)
    default_value = serializers.CharField(allow_blank=True)
    shipped_default = serializers.CharField(allow_blank=True, allow_null=True)
    override = serializers.CharField(allow_blank=True, allow_null=True)
    source = serializers.CharField()  # type: ignore[assignment]
    choices = ChoiceSerializer(many=True)
    max_length = serializers.IntegerField()


class PerObjectFeatureSerializer(_FeatureRowSerializer):
    """A setting that lives on individual rows, never globally.

    The page renders a rollup and a deep link rather than a switch: a disabled switch
    reports ``aria-checked="false"``, which states "this is off" — factually wrong when
    four of thirteen profiles have it on.

    ``on``/``total`` are nullable and paired with ``degraded``. A failed aggregate must
    not fall back to ``0 of 0``: that renders as a confident lie the user would act on.
    ``on`` is also null for non-boolean fields, where "how many are on" is meaningless.
    """

    on = serializers.IntegerField(allow_null=True)
    total = serializers.IntegerField(allow_null=True)
    degraded = serializers.BooleanField()
    noun = serializers.CharField()


class FeatureRegistrySerializer(serializers.Serializer):
    groups = FeatureGroupSerializer(many=True)
    toggles = FeatureToggleSerializer(many=True)
    numbers = FeatureNumberSerializer(many=True)
    texts = FeatureTextSerializer(many=True)
    per_object = PerObjectFeatureSerializer(many=True)
