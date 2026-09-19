from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("secrets_app", "0007_alter_apicredential_provider"),
    ]

    operations = [
        migrations.AlterField(
            model_name="apicredential",
            name="provider",
            field=models.CharField(
                choices=[
                    ("schwab", "Charles Schwab"),
                    ("finnhub", "Finnhub"),
                    ("marketaux", "Marketaux"),
                    ("alpaca", "Alpaca"),
                    ("tiingo", "Tiingo"),
                    ("twelvedata", "Twelve Data"),
                    ("polygon", "Polygon.io"),
                    ("tradier", "Tradier"),
                    ("fred", "FRED (St. Louis Fed)"),
                    ("tradingview", "TradingView"),
                ],
                max_length=32,
                unique=True,
            ),
        ),
    ]
