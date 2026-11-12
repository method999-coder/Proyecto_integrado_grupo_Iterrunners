from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0040_add_perfil_club"),
    ]

    operations = [
        migrations.AddField(
            model_name='cumplimientoentrenamiento',
            name='audit_meta',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='cumplimientoentrenamiento',
            name='entrenamiento',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='cumplimientos', to='users.entrenamientodiario'),
        ),
        migrations.CreateModel(
            name='RankingEntry',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ranking_distancia', models.PositiveSmallIntegerField(choices=[(3, '3000m'), (5, '5K'), (10, '10K'), (21, '21K'), (42, '42K')])),
                ('time_seconds', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('cumplimiento', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='as_ranking_entry', to='users.cumplimientoentrenamiento')),
                ('perfil', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ranking_entries', to='users.perfil')),
            ],
        ),
        migrations.AddConstraint(
            model_name='rankingentry',
            constraint=models.UniqueConstraint(fields=('perfil', 'ranking_distancia'), name='unique_perfil_ranking'),
        ),
        migrations.CreateModel(
            name='RankingAudit',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('reconstruir', 'Reconstruir'), ('subir_al_ranking', 'Subir al ranking'), ('auto_feed', 'Publicación automática en feed')], max_length=40)),
                ('origin', models.CharField(blank=True, max_length=40)),
                ('distance_m', models.IntegerField(blank=True, null=True)),
                ('km', models.DecimalField(blank=True, decimal_places=3, max_digits=6, null=True)),
                ('suggested_ranking', models.PositiveSmallIntegerField(blank=True, null=True, choices=[(3, '3000m'), (5, '5K'), (10, '10K'), (21, '21K'), (42, '42K')])),
                ('accepted', models.BooleanField(default=False)),
                ('published_ranking', models.BooleanField(default=False)),
                ('snapshot', models.JSONField(blank=True, null=True)),
                ('comment', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('perfil', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='users.perfil')),
                ('club', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='users.club')),
                ('cumplimiento', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='users.cumplimientoentrenamiento')),
                ('entrenamiento', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='users.entrenamientodiario')),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='auth.user')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
