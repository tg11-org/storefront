from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0005_productvariant_max_order_quantity'),
    ]

    operations = [
        migrations.AddField(
            model_name='storepage',
            name='hero_image',
            field=models.ImageField(blank=True, upload_to='pages/heroes/'),
        ),
    ]
