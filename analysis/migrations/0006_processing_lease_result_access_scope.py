import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("analysis", "0005_alter_matchanalysis_source_type_and_more")]

    operations = [
        migrations.AddField(
            model_name="matchanalysis", name="processing_token",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="matchanalysis", name="lease_expires_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.CreateModel(
            name="ResultAccessScope",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("binding", models.CharField(max_length=64)),
                ("expected_count", models.PositiveIntegerField()),
                ("received_count", models.PositiveIntegerField(default=0)),
                ("finalized_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name="ResultAccessRoom",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("room_id", models.UUIDField()),
                ("scope", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rooms", to="analysis.resultaccessscope")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("scope", "room_id"), name="unique_result_scope_room")]},
        ),
    ]
