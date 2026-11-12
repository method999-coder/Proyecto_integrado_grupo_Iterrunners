#!/usr/bin/env python3
import os, sys
if '__file__' in globals():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
else:
    project_root = os.path.abspath(os.path.join(os.getcwd(), ''))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# INICIO - Usar el módulo de esta copia antes de inicializar Django
os.environ['DJANGO_SETTINGS_MODULE'] = 'iterrunners.settings'
# FIN - Usar el módulo de esta copia antes de inicializar Django
import django
django.setup()

from users.models import Perfil, StravaActividad, EntrenamientoDiario, CumplimientoEntrenamiento
from users.views import _sugerencia_ranking_desde_strava
from django.db import transaction
# INICIO - Verificar el destino antes de consultar datos históricos
from django.conf import settings
from pathlib import Path
# FIN - Verificar el destino antes de consultar datos históricos
from datetime import datetime
import argparse

parser = argparse.ArgumentParser(description='Reconstruir cumplimientos a partir de Strava (dry-run por defecto).')
parser.add_argument('--apply', action='store_true', help='Aplicar cambios (crear los CumplimientoEntrenamiento).')
parser.add_argument('--publish', action='store_true', help='Marcar los cumplimientos reconstruidos con publicar_ranking=True.')
parser.add_argument('--max', type=int, default=1000, help='Máximo número de cumplimientos a procesar (para safety).')
parser.add_argument('--fallback-carrera', action='store_true', help='Si no existe EntrenamientoDiario para la fecha, crear CarreraManual como fallback.')
args = parser.parse_args()

# INICIO - Restringir la reconstrucción manual a la SQLite de esta copia
expected_db = Path(project_root).resolve() / "db.sqlite3"
database = settings.DATABASES["default"]
if (
    database["ENGINE"] != "django.db.backends.sqlite3"
    or Path(database["NAME"]).absolute() != expected_db
    or expected_db.resolve() != expected_db
):
    parser.error("La reconstrucción requiere db.sqlite3 en la raíz de Iterrunners-Dev.")
# FIN - Restringir la reconstrucción manual a la SQLite de esta copia

created = []
proposed = []

perfil_qs = Perfil.objects.all().select_related('grupo')
count = 0

for perfil in perfil_qs:
    if perfil.grupo_id is None:
        continue
    actividades = (
        StravaActividad.objects
        .filter(perfil=perfil)
        .exclude(start_date__isnull=True)
        .order_by('start_date')
    )
    # map date -> best activity (max distance)
    best_by_date = {}
    for a in actividades:
        d = a.start_date.date()
        cur = best_by_date.get(d)
        if not cur or ((a.distance_m or 0) > (cur.distance_m or 0)):
            best_by_date[d] = a

    if not best_by_date:
        continue

    fechas = list(best_by_date.keys())
    entrenos = {
        e.fecha: e
        for e in EntrenamientoDiario.objects.filter(grupo=perfil.grupo, fecha__in=fechas)
    }

    for fecha, actividad in best_by_date.items():
        entreno = entrenos.get(fecha)
        # if there is an entreno and no cumplimiento -> candidate
        if entreno:
            exists = CumplimientoEntrenamiento.objects.filter(perfil=perfil, entrenamiento=entreno, fecha=fecha).exists()
            if not exists:
                suger = _sugerencia_ranking_desde_strava(perfil, fecha)
                ranking_dist = suger.get('sugerencia_valor') if suger else None
                proposed.append({
                    'perfil_id': perfil.id,
                    'perfil_nombre': perfil.nombre,
                    'entrenamiento_id': entreno.id,
                    'fecha': str(fecha),
                    'actividad_id': actividad.id,
                    'actividad_dist_m': actividad.distance_m,
                    'actividad_time_s': actividad.moving_time_s,
                    'ranking_distancia_sugerida': ranking_dist,
                })
                count += 1
                if count >= args.max:
                    break
        else:
            # no entreno for that date
            if args.fallback_carrera:
                # create CarreraManual later if apply
                proposed.append({
                    'perfil_id': perfil.id,
                    'perfil_nombre': perfil.nombre,
                    'entrenamiento_id': None,
                    'fecha': str(fecha),
                    'actividad_id': actividad.id,
                    'actividad_dist_m': actividad.distance_m,
                    'actividad_time_s': actividad.moving_time_s,
                    'fallback_carrera': True,
                })
                count += 1
                if count >= args.max:
                    break
    if count >= args.max:
        break

print('Candidates to create:', len(proposed))
if len(proposed) > 0:
    for p in proposed[:50]:
        print(p)

if args.apply and proposed:
    print('\nApplying changes...')
    created_count = 0
    with transaction.atomic():
        for p in proposed:
            if p.get('entrenamiento_id'):
                entreno = EntrenamientoDiario.objects.get(id=p['entrenamiento_id'])
                perfil = Perfil.objects.get(id=p['perfil_id'])
                # create cumplimiento
                c = CumplimientoEntrenamiento(
                    perfil=perfil,
                    entrenamiento=entreno,
                    fecha=entreno.fecha,
                    realizada=True,
                    realizada_at=p.get('actividad_start') or None,
                    comentario='Reconstruido desde Strava (automático)',
                    publicar_ranking=bool(args.publish),
                    ranking_distancia=p.get('ranking_distancia_sugerida')
                )
                c.save()
                created_count += 1
            else:
                if args.fallback_carrera:
                    # create CarreraManual from activity
                    from users.models import CarreraManual
                    perfil = Perfil.objects.get(id=p['perfil_id'])
                    distancia_m = int(p['actividad_dist_m'] or 0)
                    tiempo_s = int(p['actividad_time_s'] or 0)
                    # format time
                    if tiempo_s >= 3600:
                        h = tiempo_s // 3600
                        m = (tiempo_s % 3600) // 60
                        s = tiempo_s % 60
                        tiempo_str = f"{h}:{m:02d}:{s:02d}"
                    else:
                        m = tiempo_s // 60
                        s = tiempo_s % 60
                        tiempo_str = f"{m}:{s:02d}"
                    CarreraManual.objects.create(
                        perfil=perfil,
                        fecha=p['fecha'],
                        distancia_m=distancia_m,
                        tiempo=tiempo_str,
                    )
                    created_count += 1
    print('Created', created_count)
else:
    print('Dry run complete. Use --apply to create records, --publish to mark publishing, --fallback-carrera to create CarreraManual when no entreno.')
