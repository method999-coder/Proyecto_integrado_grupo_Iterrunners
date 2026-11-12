#!/usr/bin/env python3
"""Backfill script: genera RankingEntry a partir de datos existentes.

Dry-run por defecto: muestra acciones propuestas. Usar --apply para insertar.

Estrategia:
 - Para cada `Perfil`, para cada distancia (3,5,10,21,42):
   - buscar `CumplimientoEntrenamiento` publicado (`publicar_ranking=True`) con esa `ranking_distancia` y tomar el mejor `time_seconds` si existe en `audit_meta` o en snapshot.
   - si no existe, buscar `StravaActividad` del perfil con distancia cercana (usar _sugerencia_ranking_desde_strava si disponible) y tomar `moving_time_s` mínimo.
   - si no, buscar `CarreraManual` para esa distancia y tomar `tiempo` convertido.
   - proponer la mejor opción encontrada.

Genera también un `RankingAudit` por cada creación o reemplazo.
"""
import os, sys
if '__file__' in globals():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
else:
    project_root = os.path.abspath(os.path.join(os.getcwd(), ''))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'iterrunners.settings')
import django
django.setup()

from users.models import (
    Perfil, CumplimientoEntrenamiento, StravaActividad, CarreraManual,
    RankingEntry, RankingAudit
)
from django.db import transaction
import argparse

DISTANCES = [3,5,10,21,42]


def _sugerir_distancia_desde_m(distance_m):
    if not distance_m:
        return None

    distancia_km = float(distance_m) / 1000.0
    opciones = [
        (3, 3.0, 0.35),
        (5, 5.0, 0.60),
        (10, 10.0, 1.00),
        (21, 21.0, 1.50),
        (42, 42.0, 3.00),
    ]

    mejor_valor = None
    mejor_diferencia = None
    for valor, referencia_km, tolerancia_km in opciones:
        diferencia = abs(distancia_km - referencia_km)
        if diferencia <= tolerancia_km:
            if mejor_diferencia is None or diferencia < mejor_diferencia:
                mejor_diferencia = diferencia
                mejor_valor = valor

    return mejor_valor

parser = argparse.ArgumentParser(description='Backfill RankingEntry from existing data (dry-run).')
parser.add_argument('--apply', action='store_true', help='Aplicar cambios (crear RankingEntry y RankingAudit).')
parser.add_argument('--max-profiles', type=int, default=0, help='Limitar número de perfiles procesados (0 = todos).')
args = parser.parse_args()

proposals = []

profiles = Perfil.objects.all().select_related('club')
if args.max_profiles > 0:
    profiles = profiles[:args.max_profiles]

for perfil in profiles:
    for dist in DISTANCES:
        best = None
        source = None
        # 1) check published cumplimientos with ranking_distancia == dist
        qs = CumplimientoEntrenamiento.objects.filter(perfil=perfil, publicar_ranking=True, ranking_distancia=dist)
        for c in qs:
            # try audit_meta
            t = None
            if c.audit_meta and isinstance(c.audit_meta, dict):
                t = c.audit_meta.get('time_seconds')
            # fallback: check comentario for pattern 'tiempo' not implemented
            if t is None:
                # can't extract time, skip
                continue
            if best is None or (t is not None and t < best['time_seconds']):
                best = {'type':'cumplimiento','obj':c,'time_seconds':t}
                source = 'cumplimiento'
        if best is None:
            # 2) look at Strava activities
            actividades = StravaActividad.objects.filter(perfil=perfil).exclude(moving_time_s__isnull=True)
            # use suggestion function to filter activities that map to dist
            candidates = []
            for a in actividades:
                suger_val = _sugerir_distancia_desde_m(a.distance_m)
                if suger_val == dist and a.moving_time_s:
                    candidates.append(a)
            if candidates:
                a_best = min(candidates, key=lambda x: x.moving_time_s or 10**9)
                best = {'type':'strava','obj':a_best,'time_seconds':int(a_best.moving_time_s or 0)}
                source = 'strava'
        if best is None:
            # 3) manual races
            carreras = CarreraManual.objects.filter(perfil=perfil, distancia_m=dist*1000)
            if carreras.exists():
                # convert tiempo string to seconds
                def tiempo_to_s(t):
                    parts = t.split(':')
                    parts = [int(p) for p in parts]
                    if len(parts) == 2:
                        return parts[0]*60 + parts[1]
                    elif len(parts) == 3:
                        return parts[0]*3600 + parts[1]*60 + parts[2]
                    return None
                c_best = min(carreras, key=lambda x: tiempo_to_s(x.tiempo) or 10**9)
                ts = tiempo_to_s(c_best.tiempo)
                if ts:
                    best = {'type':'carrera_manual','obj':c_best,'time_seconds':ts}
                    source = 'carrera_manual'
        if best:
            proposals.append({'perfil_id':perfil.id,'perfil_nombre':perfil.nombre,'dist':dist,'source':source,'obj_id':best['obj'].id,'time_seconds':best['time_seconds']})

print('Proposals:', len(proposals))
for p in proposals[:100]:
    print(p)

if args.apply and proposals:
    created = 0
    with transaction.atomic():
        for p in proposals:
            perfil = Perfil.objects.get(id=p['perfil_id'])
            dist = p['dist']
            time_s = p['time_seconds']
            # lock existing entry
            from django.db import connection
            existing = RankingEntry.objects.select_for_update().filter(perfil=perfil, ranking_distancia=dist).first()
            snapshot = {'source':p['source'],'obj_id':p['obj_id'],'time_seconds':time_s}
            if existing is None:
                re = RankingEntry.objects.create(perfil=perfil, ranking_distancia=dist, time_seconds=time_s)
                RankingAudit.objects.create(perfil=perfil, club=getattr(perfil,'club',None), action='reconstruir', origin=p['source'], km=None, distance_m=None, suggested_ranking=dist, accepted=True, published_ranking=False, snapshot=snapshot, comment='Backfill')
                created += 1
            else:
                # if new is better, replace
                if existing.time_seconds is None or (time_s is not None and time_s < existing.time_seconds):
                    prev = {'cumplimiento_id': existing.cumplimiento.id if existing.cumplimiento else None, 'time_seconds': existing.time_seconds}
                    existing.cumplimiento = None
                    existing.time_seconds = time_s
                    existing.save()
                    RankingAudit.objects.create(perfil=perfil, club=getattr(perfil,'club',None), action='reconstruir', origin=p['source'], km=None, distance_m=None, suggested_ranking=dist, accepted=True, published_ranking=False, snapshot={'prev':prev,'new':snapshot}, comment='Backfill replace')
                    created += 1
                else:
                    RankingAudit.objects.create(perfil=perfil, club=getattr(perfil,'club',None), action='reconstruir', origin=p['source'], km=None, distance_m=None, suggested_ranking=dist, accepted=False, published_ranking=False, snapshot=snapshot, comment='Backfill skipped: not better')
    print('Applied, entries created/updated:', created)
else:
    print('Dry run complete. Use --apply to create entries.')
