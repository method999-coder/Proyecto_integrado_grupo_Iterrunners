import os, django, json, sys
# Ensure project root is on sys.path so Django settings can be imported
if '__file__' in globals():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
else:
    # When piping into manage.py shell, __file__ may not be defined; fall back to cwd
    project_root = os.path.abspath(os.path.join(os.getcwd(), ''))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iterrunners.settings')
django.setup()
from django.db.models import Count
from users.models import CumplimientoEntrenamiento, EntrenamientoDiario, Perfil, Grupo, StravaActividad

out = {}
out['counts'] = {
    'cumplimientos_total': CumplimientoEntrenamiento.objects.count(),
    'cumplimientos_publicados': CumplimientoEntrenamiento.objects.filter(publicar_ranking=True).count(),
    'entrenamientos_total': EntrenamientoDiario.objects.count(),
    'grupos_total': Grupo.objects.count(),
}

# Top perfiles with published rankings
top = list(CumplimientoEntrenamiento.objects.filter(publicar_ranking=True).values('perfil_id').annotate(count=Count('id')).order_by('-count')[:30])
profiles_top = []
from users.models import Perfil
for row in top:
    try:
        p = Perfil.objects.get(id=row['perfil_id'])
        profiles_top.append({'perfil_id': p.id, 'nombre': p.nombre, 'apellido': p.apellido, 'count': row['count']})
    except Perfil.DoesNotExist:
        profiles_top.append({'perfil_id': row['perfil_id'], 'missing_perfil': True, 'count': row['count']})
out['top_perfiles_publicados'] = profiles_top

# Perfiles sin grupo pero con actividades Strava
perfiles_no_grupo = []
qs = Perfil.objects.filter(grupo__isnull=True).annotate(strava_count=Count('strava_actividades')).filter(strava_count__gt=0)[:100]
for p in qs:
    perfiles_no_grupo.append({'perfil_id': p.id, 'nombre': p.nombre, 'apellido': p.apellido, 'strava_count': p.strava_count})
out['perfiles_no_grupo_con_strava'] = perfiles_no_grupo

# Discrepancias: cumplimiento.entrenamiento.grupo != perfil.grupo
mismatches = []
cc = CumplimientoEntrenamiento.objects.select_related('entrenamiento__grupo', 'perfil__grupo').all()[:1000]
for c in cc:
    try:
        ent_grupo_id = c.entrenamiento.grupo_id
    except Exception:
        ent_grupo_id = None
    perfil_grupo_id = getattr(c.perfil, 'grupo_id', None)
    if ent_grupo_id != perfil_grupo_id:
        mismatches.append({
            'cumplimiento_id': c.id,
            'perfil_id': c.perfil_id,
            'perfil_grupo_id': perfil_grupo_id,
            'entrenamiento_id': c.entrenamiento_id,
            'entrenamiento_grupo_id': ent_grupo_id,
            'fecha': str(c.fecha),
        })
    if len(mismatches) >= 50:
        break
out['mismatches_sample'] = mismatches

# Some example Strava actividad counts per perfil
sa = list(StravaActividad.objects.values('perfil_id').annotate(count=Count('id')).order_by('-count')[:20])
out['strava_counts_top'] = sa

print(json.dumps(out, ensure_ascii=False, indent=2))
