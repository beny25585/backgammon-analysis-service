from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("analysis", "0003_rollluckanalysis")]
    operations = [migrations.AddField(
        model_name="matchanalysis", name="eval_level",
        field=models.CharField(default="1ply", max_length=10),
    )]
