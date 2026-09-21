from typing import ClassVar

from rest_framework import serializers

from apps.book.models import BookSnapshot


class BookSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookSnapshot
        fields: ClassVar = [
            "id",
            "created_at",
            "as_of_date",
            "exposures",
            "concentration",
            "clusters",
            "regime_fit",
            "near_invalidation",
            "narrative",
            "var_beta",
        ]
        read_only_fields: ClassVar = fields


def _scalar(source: str) -> serializers.FloatField:
    """A number lifted out of one of the stored JSON blobs.

    ``allow_null`` covers both a null in the blob and the key being absent
    altogether (an early row written before a metric existed, or a day where VaR
    was unavailable) — the point on the curve is then a gap, not a zero.
    """
    return serializers.FloatField(source=source, allow_null=True, read_only=True)


class BookSnapshotTrendSerializer(serializers.ModelSerializer):
    """One point on the book's history curve.

    The detail serializer's per-position arrays (exposures, clusters, VaR
    positions) are what make a row heavy and none of them plot, so this flattens
    the scalars a trend/sparkline reads and leaves the arrays to
    ``GET /api/book/<id>/``. Every metric is nullable: a day with no priceable
    position has no VaR, and plotting a zero there would invent a reading.
    """

    hhi = _scalar("concentration.hhi")
    top_n_share = _scalar("concentration.top_n_share")
    total_abs = _scalar("concentration.total_abs")
    net_long = _scalar("concentration.net_long")
    net_short = _scalar("concentration.net_short")
    gross_dollar = _scalar("var_beta.portfolio.gross_dollar")
    net_dollar = _scalar("var_beta.portfolio.net_dollar")
    diversified_var_usd = _scalar("var_beta.portfolio.diversified_var_usd")
    undiversified_var_usd = _scalar("var_beta.portfolio.undiversified_var_usd")
    beta_adjusted_net_exposure_usd = _scalar("var_beta.portfolio.beta_adjusted_net_exposure_usd")
    regime = serializers.CharField(
        source="regime_fit.regime", allow_null=True, read_only=True, default=None
    )
    alignment = serializers.CharField(
        source="regime_fit.alignment", allow_null=True, read_only=True, default=None
    )
    position_count = serializers.SerializerMethodField()
    cluster_count = serializers.SerializerMethodField()
    near_invalidation_count = serializers.SerializerMethodField()

    class Meta:
        model = BookSnapshot
        fields: ClassVar = [
            "id",
            "created_at",
            "as_of_date",
            "hhi",
            "top_n_share",
            "total_abs",
            "net_long",
            "net_short",
            "gross_dollar",
            "net_dollar",
            "diversified_var_usd",
            "undiversified_var_usd",
            "beta_adjusted_net_exposure_usd",
            "regime",
            "alignment",
            "position_count",
            "cluster_count",
            "near_invalidation_count",
        ]
        read_only_fields: ClassVar = fields

    def get_position_count(self, obj: BookSnapshot) -> int:
        return len(obj.exposures or [])

    def get_cluster_count(self, obj: BookSnapshot) -> int:
        return len(obj.clusters or [])

    def get_near_invalidation_count(self, obj: BookSnapshot) -> int:
        return len(obj.near_invalidation or [])
