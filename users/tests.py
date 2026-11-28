from datetime import date, datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import requests

from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.models import Group, User
# INICIO - Probar ambos estados de Strava con configuración explícita
from django.core.management import call_command
from django.test import TestCase, override_settings
# FIN - Probar ambos estados de Strava con configuración explícita
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone

from .models import CumplimientoEntrenamiento, EntrenamientoDiario, Grupo, Perfil, StravaActividad, Club


class CriticalViewsTests(TestCase):
	@override_settings(
		EMAIL_BACKEND="users.email_backend.BrevoEmailBackend",
		BREVO_API_KEY="fake-brevo-key",
		DEFAULT_FROM_EMAIL="Iter Runners <academico@example.com>",
	)
	def test_password_reset_sends_django_link_via_brevo(self):
		User.objects.create_user("runner_email", email="runner@example.com", password="testpass123")
		reset_url = reverse("password_reset")

		with patch("users.email_backend.requests.post") as post:
			post.return_value.status_code = 201
			response = self.client.post(reset_url, {"email": "runner@example.com"})
			self.assertRedirects(response, reverse("password_reset_done"))
			self.assertRedirects(
				self.client.post(reset_url, {"email": "unknown@example.com"}),
				reverse("password_reset_done"),
			)
			post.assert_called_once()

		request = post.call_args
		self.assertEqual(request.args, ("https://api.brevo.com/v3/smtp/email",))
		self.assertEqual(request.kwargs["headers"]["api-key"], "fake-brevo-key")
		self.assertFalse(request.kwargs["allow_redirects"])
		payload = request.kwargs["json"]
		self.assertEqual(payload["sender"], {"name": "Iter Runners", "email": "academico@example.com"})
		self.assertEqual(payload["to"], [{"email": "runner@example.com"}])
		reset_link = next(line.strip() for line in payload["textContent"].splitlines() if line.startswith("http"))
		reset_page = self.client.get(urlsplit(reset_link).path, follow=True)
		self.assertTemplateUsed(reset_page, "users/password_reset_confirm.html")
		self.assertTrue(reset_page.context["validlink"])

	@override_settings(
		EMAIL_BACKEND="users.email_backend.BrevoEmailBackend",
		BREVO_API_KEY="fake-brevo-key",
		DEFAULT_FROM_EMAIL="academico@example.com",
	)
	def test_password_reset_keeps_generic_response_on_brevo_error(self):
		User.objects.create_user("runner_mail_error", email="runner@example.com", password="testpass123")
		with patch("users.email_backend.requests.post") as post:
			post.return_value.status_code = 503
			with self.assertLogs("django.contrib.auth", level="ERROR") as logs:
				response = self.client.post(reverse("password_reset"), {"email": "runner@example.com"})

		self.assertRedirects(response, reverse("password_reset_done"))
		self.assertIn("HTTP 503", logs.output[0])
		self.assertNotIn("fake-brevo-key", logs.output[0])
		self.assertNotIn("runner@example.com", logs.output[0])

	def _create_user_with_profile(self, username, role, django_group_name, grupo=None, is_superuser=False):
		user = User.objects.create_user(username=username, password="testpass123")
		user.is_superuser = is_superuser
		user.is_staff = is_superuser
		user.save()

		if django_group_name:
			group, _ = Group.objects.get_or_create(name=django_group_name)
			user.groups.add(group)

		perfil, _ = Perfil.objects.get_or_create(usuario=user)
		perfil.nombre = username
		perfil.rol = role
		perfil.grupo = grupo
		perfil.club = grupo.club if grupo and grupo.club else None
		perfil.must_change_password = False
		perfil.save()
		return user, perfil

	def _create_club_and_group(self, club_name, group_name):
		club = Club.objects.create(nombre=club_name)
		grupo = Grupo.objects.create(nombre=group_name, club=club)
		return club, grupo

	def test_staff_puede_restablecer_password_temporal(self):
		club, grupo = self._create_club_and_group("Club Reset", "Grupo Reset")
		staff_user, _ = self._create_user_with_profile(
			username="coach-reset",
			role="profesor",
			django_group_name="Profesor",
			grupo=grupo,
		)
		runner_user, runner_perfil = self._create_user_with_profile(
			username="runner-reset",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo,
		)
		runner_perfil.must_change_password = False
		runner_perfil.save(update_fields=["must_change_password"])

		self.client.login(username=staff_user.username, password="testpass123")
		response = self.client.post(
			reverse("restablecer_password_corredor", args=[runner_perfil.id]),
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Nueva contraseña temporal")
		runner_perfil.refresh_from_db()
		self.assertTrue(runner_perfil.must_change_password)
		runner_user.refresh_from_db()
		self.assertFalse(runner_user.check_password("testpass123"))

	def test_staff_no_puede_restablecer_password_de_otro_club(self):
		_, grupo_staff = self._create_club_and_group("Club Staff", "Grupo Staff")
		_, grupo_otro = self._create_club_and_group("Club Otro", "Grupo Otro")
		staff_user, _ = self._create_user_with_profile(
			username="coach-club",
			role="profesor",
			django_group_name="Profesor",
			grupo=grupo_staff,
		)
		runner_user, runner_perfil = self._create_user_with_profile(
			username="runner-otro-club",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo_otro,
		)

		self.client.login(username=staff_user.username, password="testpass123")
		response = self.client.post(
			reverse("restablecer_password_corredor", args=[runner_perfil.id]),
		)

		self.assertEqual(response.status_code, 403)
		runner_user.refresh_from_db()
		self.assertTrue(runner_user.check_password("testpass123"))

	def test_staff_puede_asignar_grupo_de_su_club(self):
		_, grupo_staff = self._create_club_and_group("Club Asignar", "Grupo Staff")
		grupo_destino = Grupo.objects.create(nombre="Grupo Destino", club=grupo_staff.club)
		staff_user, _ = self._create_user_with_profile(
			username="coach-asigna",
			role="profesor",
			django_group_name="Profesor",
			grupo=grupo_staff,
		)
		_, runner_perfil = self._create_user_with_profile(
			username="runner-asigna",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo_staff,
		)

		self.client.login(username=staff_user.username, password="testpass123")
		response = self.client.post(
			reverse("asignar_grupo", args=[runner_perfil.id]),
			{"grupo": str(grupo_destino.id)},
		)

		self.assertRedirects(response, reverse("gestion_corredores"))
		runner_perfil.refresh_from_db()
		self.assertEqual(runner_perfil.grupo_id, grupo_destino.id)

	def test_staff_no_puede_asignar_grupo_de_otro_club_manipulando_post(self):
		_, grupo_staff = self._create_club_and_group("Club Asigna Staff", "Grupo Staff")
		_, grupo_otro = self._create_club_and_group("Club Asigna Otro", "Grupo Otro")
		staff_user, _ = self._create_user_with_profile(
			username="coach-asigna-club",
			role="profesor",
			django_group_name="Profesor",
			grupo=grupo_staff,
		)
		_, runner_perfil = self._create_user_with_profile(
			username="runner-asigna-club",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo_staff,
		)

		self.client.login(username=staff_user.username, password="testpass123")
		response = self.client.post(
			reverse("asignar_grupo", args=[runner_perfil.id]),
			{"grupo": str(grupo_otro.id)},
		)

		self.assertEqual(response.status_code, 200)
		runner_perfil.refresh_from_db()
		self.assertEqual(runner_perfil.grupo_id, grupo_staff.id)
		self.assertContains(response, "El grupo seleccionado no existe.")

	def test_crear_corredor_muestra_solo_grupos_del_club(self):
		_, grupo_staff = self._create_club_and_group("Club Form Staff", "Grupo Form Staff")
		_, grupo_otro = self._create_club_and_group("Club Form Otro", "Grupo Form Otro")
		staff_user, _ = self._create_user_with_profile(
			username="coach-form-crea",
			role="profesor",
			django_group_name="Profesor",
			grupo=grupo_staff,
		)

		self.client.login(username=staff_user.username, password="testpass123")
		response = self.client.get(reverse("crear_corredor"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, grupo_staff.nombre)
		self.assertNotContains(response, grupo_otro.nombre)

	def test_editar_corredor_muestra_solo_grupos_del_club(self):
		_, grupo_staff = self._create_club_and_group("Club Edit Staff", "Grupo Edit Staff")
		_, grupo_otro = self._create_club_and_group("Club Edit Otro", "Grupo Edit Otro")
		staff_user, _ = self._create_user_with_profile(
			username="coach-form-edita",
			role="profesor",
			django_group_name="Profesor",
			grupo=grupo_staff,
		)
		_, runner_perfil = self._create_user_with_profile(
			username="runner-form-edita",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo_staff,
		)

		self.client.login(username=staff_user.username, password="testpass123")
		response = self.client.get(reverse("editar_corredor", args=[runner_perfil.id]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, grupo_staff.nombre)
		self.assertNotContains(response, grupo_otro.nombre)

	def test_crear_corredor_no_acepta_grupo_de_otro_club(self):
		_, grupo_staff = self._create_club_and_group("Club Crear Staff", "Grupo Crear Staff")
		_, grupo_otro = self._create_club_and_group("Club Crear Otro", "Grupo Crear Otro")
		staff_user, _ = self._create_user_with_profile(
			username="coach-crea-club",
			role="profesor",
			django_group_name="Profesor",
			grupo=grupo_staff,
		)

		self.client.login(username=staff_user.username, password="testpass123")
		response = self.client.post(
			reverse("crear_corredor"),
			{
				"username": "runner-grupo-otro",
				"first_name": "Runner",
				"last_name": "Otro",
				"email": "runner-grupo-otro@example.com",
				"grupo": str(grupo_otro.id),
				"modalidad_ritmo": "runners",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertFalse(User.objects.filter(username="runner-grupo-otro").exists())

	def test_recuperacion_autonoma_limpia_cambio_obligatorio(self):
		_, grupo = self._create_club_and_group("Club Autonomo", "Grupo Autonomo")
		runner_user, runner_perfil = self._create_user_with_profile(
			username="runner-autonomo",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo,
		)
		runner_user.email = "runner-autonomo@example.com"
		runner_user.save(update_fields=["email"])
		runner_perfil.must_change_password = True
		runner_perfil.save(update_fields=["must_change_password"])
		uid = urlsafe_base64_encode(force_bytes(runner_user.pk))
		token = default_token_generator.make_token(runner_user)

		response = self.client.get(reverse("password_reset_confirm", args=[uid, token]))
		self.assertEqual(response.status_code, 302)
		response = self.client.post(
			response["Location"],
			{
				"new_password1": "NuevaClaveSegura123",
				"new_password2": "NuevaClaveSegura123",
			},
		)

		self.assertRedirects(response, reverse("password_reset_complete"))
		runner_perfil.refresh_from_db()
		runner_user.refresh_from_db()
		self.assertFalse(runner_perfil.must_change_password)
		self.assertTrue(runner_user.check_password("NuevaClaveSegura123"))

	def test_cumplimiento_hoy_shows_totals_for_staff(self):
		club, grupo = self._create_club_and_group("Club 10K", "10K A")
		today = timezone.localdate()

		EntrenamientoDiario.objects.create(
			grupo=grupo,
			fecha=today,
			tipo="entreno",
			titulo="Series",
			descripcion="6x800",
		)

		_, perfil_runner = self._create_user_with_profile(
			username="runner1",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo,
		)
		_, perfil_profesor = self._create_user_with_profile(
			username="coach1",
			role="profesor",
			django_group_name="Profesor",
		)
		perfil_profesor.club = club
		perfil_profesor.save(update_fields=["club"])

		entreno = EntrenamientoDiario.objects.get(grupo=grupo, fecha=today)
		CumplimientoEntrenamiento.objects.create(
			perfil=perfil_runner,
			entrenamiento=entreno,
			fecha=today,
			realizada=True,
		)

		self.client.login(username="coach1", password="testpass123")
		response = self.client.get(reverse("cumplimiento_hoy"), {"fecha": today.isoformat()})

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.context["es_hoy"])
		self.assertEqual(len(response.context["grupos_data"]), 1)
		self.assertEqual(response.context["grupos_data"][0]["total_corredores"], 1)
		self.assertEqual(response.context["grupos_data"][0]["total_realizadas"], 1)

	def test_copiar_mes_copies_only_valid_days(self):
		club, source_group = self._create_club_and_group("Club Calendario", "Origen")
		target_group = Grupo.objects.create(nombre="Destino", club=club)

		self._create_user_with_profile(
			username="admin1",
			role="admin",
			django_group_name="Admin",
			grupo=target_group,
		)

		EntrenamientoDiario.objects.create(
			grupo=source_group,
			fecha=date(2025, 1, 15),
			tipo="entreno",
			titulo="Rodaje",
			descripcion="40 min",
		)
		EntrenamientoDiario.objects.create(
			grupo=source_group,
			fecha=date(2025, 1, 31),
			tipo="entreno",
			titulo="Largo",
			descripcion="90 min",
		)

		self.client.login(username="admin1", password="testpass123")
		url = f"{reverse('copiar_mes')}?grupo={target_group.id}&month=2&year=2025"
		response = self.client.post(
			url,
			{
				"grupo_origen": source_group.id,
				"mes_origen": 1,
				"anio_origen": 2025,
			},
			follow=True,
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(
			EntrenamientoDiario.objects.filter(grupo=target_group, fecha=date(2025, 2, 15)).exists()
		)
		self.assertEqual(
			EntrenamientoDiario.objects.filter(grupo=target_group, fecha__month=2, fecha__year=2025).count(),
			1,
		)

	def test_estadisticas_clamps_future_navigation(self):
		_, grupo = self._create_club_and_group("Club 21K", "21K B")
		user, perfil = self._create_user_with_profile(
			username="runner2",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo,
		)

		today = timezone.localdate()
		week_start = today - timedelta(days=today.weekday())
		EntrenamientoDiario.objects.create(
			grupo=grupo,
			fecha=week_start,
			tipo="entreno",
			titulo="Base",
			descripcion="50 min",
		)
		entreno = EntrenamientoDiario.objects.get(grupo=grupo, fecha=week_start)
		CumplimientoEntrenamiento.objects.create(
			perfil=perfil,
			entrenamiento=entreno,
			fecha=week_start,
			realizada=True,
		)

		future_week = (today + timedelta(days=30)).isoformat()
		future_month = (today.replace(day=1) + timedelta(days=40)).strftime("%Y-%m")

		self.client.login(username=user.username, password="testpass123")
		response = self.client.get(reverse("estadisticas"), {
			"week_start": future_week,
			"month": future_month,
		})

		self.assertEqual(response.status_code, 200)
		self.assertIsNone(response.context["next_week_start"])
		self.assertLessEqual(response.context["inicio_mes"], today.replace(day=1))

	def test_registro_actividad_guarda_cumplimiento_por_tipo(self):
		grupo = Grupo.objects.create(nombre="Grupo de entrenamiento")
		user, perfil = self._create_user_with_profile(
			username="runner3",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo,
		)
		self.client.login(username=user.username, password="testpass123")
		hoy = timezone.localdate()

		for dias, tipo in enumerate(("entreno", "carrera", "control")):
			with self.subTest(tipo=tipo):
				fecha = hoy + timedelta(days=dias)
				entrenamiento = EntrenamientoDiario.objects.create(
					grupo=grupo,
					fecha=fecha,
					tipo=tipo,
					titulo=tipo.capitalize(),
				)
				comentario = f"{tipo} completado"
				response = self.client.post(reverse("registro_actividad"), {
					"fecha": fecha.isoformat(),
					"realizada": "on",
					"comentario": comentario,
				}, follow=True)
				self.assertEqual(response.status_code, 200)

				cumplimiento = CumplimientoEntrenamiento.objects.get(
					perfil=perfil,
					entrenamiento=entrenamiento,
					fecha=fecha,
				)
				self.assertTrue(cumplimiento.realizada)
				self.assertEqual(cumplimiento.comentario, comentario)

	def test_registro_actividad_carga_con_actividad_strava_de_3_km(self):
		grupo = Grupo.objects.create(nombre="Grupo de entrenamiento")
		user, perfil = self._create_user_with_profile(
			username="runner_strava_3k",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo,
		)
		ahora = timezone.now()
		hoy = timezone.localdate(ahora)
		entrenamiento = EntrenamientoDiario.objects.create(
			grupo=grupo,
			fecha=hoy,
			tipo="control",
			titulo="Control 3K",
		)
		StravaActividad.objects.create(
			perfil=perfil,
			strava_id=991999,
			name="Control 3K",
			type="Run",
			start_date=ahora,
			distance_m=3020,
			moving_time_s=780,
		)

		self.client.login(username=user.username, password="testpass123")
		response = self.client.get(reverse("registro_actividad"), {"fecha": hoy.isoformat()})

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "users/registro_actividad.html")
		self.assertEqual(response.context["entreno_registro"], entrenamiento)

	def test_profesor_ve_solo_corredores_de_su_club_incluso_sin_grupo(self):
		club_a, grupo_a = self._create_club_and_group("Club A", "Grupo A")
		club_b, grupo_b = self._create_club_and_group("Club B", "Grupo B")

		profesor_user, profesor_perfil = self._create_user_with_profile(
			username="prof-a",
			role="profesor",
			django_group_name="Profesor",
		)
		profesor_perfil.club = club_a
		profesor_perfil.save(update_fields=["club"])

		_, runner_a_group = self._create_user_with_profile(
			username="runner-a-group",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo_a,
		)
		runner_a_group.refresh_from_db()

		_, runner_a_nogroup = self._create_user_with_profile(
			username="runner-a-nogroup",
			role="corredor",
			django_group_name="Corredor",
		)
		runner_a_nogroup.club = club_a
		runner_a_nogroup.save(update_fields=["club"])

		_, runner_b_nogroup = self._create_user_with_profile(
			username="runner-b-nogroup",
			role="corredor",
			django_group_name="Corredor",
		)
		runner_b_nogroup.club = club_b
		runner_b_nogroup.save(update_fields=["club"])

		self.client.login(username=profesor_user.username, password="testpass123")
		response = self.client.get(reverse("gestion_corredores"))

		self.assertEqual(response.status_code, 200)
		corredores = response.context["corredores"]
		usernames = {c.usuario.username for c in corredores}
		self.assertIn("runner-a-group", usernames)
		self.assertIn("runner-a-nogroup", usernames)
		self.assertNotIn("runner-b-nogroup", usernames)

	def test_profesor_no_puede_editar_corredor_de_otro_club(self):
		club_a, grupo_a = self._create_club_and_group("Club A", "Grupo A")
		club_b, grupo_b = self._create_club_and_group("Club B", "Grupo B")

		profesor_user, profesor_perfil = self._create_user_with_profile(
			username="prof-b",
			role="profesor",
			django_group_name="Profesor",
		)
		profesor_perfil.club = club_a
		profesor_perfil.save(update_fields=["club"])

		_, runner_b = self._create_user_with_profile(
			username="runner-b",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo_b,
		)

		self.client.login(username=profesor_user.username, password="testpass123")
		response = self.client.get(reverse("editar_corredor", args=[runner_b.id]))

		self.assertEqual(response.status_code, 403)

	def test_profesor_ve_solo_grupos_de_su_club_en_gestion_grupos(self):
		club_a, grupo_a = self._create_club_and_group("Club A", "Grupo A")
		club_b, grupo_b = self._create_club_and_group("Club B", "Grupo B")

		profesor_user, profesor_perfil = self._create_user_with_profile(
			username="prof-grupos",
			role="profesor",
			django_group_name="Profesor",
		)
		profesor_perfil.club = club_a
		profesor_perfil.save(update_fields=["club"])

		self.client.login(username=profesor_user.username, password="testpass123")
		response = self.client.get(reverse("gestion_grupos"))

		self.assertEqual(response.status_code, 200)
		grupos = response.context["grupos"]
		self.assertEqual(list(grupos.values_list("nombre", flat=True)), ["Grupo A"])

	def test_signal_assigns_club_on_user_creation(self):
		# If a Club exists, creating a User should create a Perfil and assign the first Club
		club = Club.objects.create(nombre="Signal Club")
		user = User.objects.create_user(username="signal_user", password="pw123")
		perfil = Perfil.objects.get(usuario=user)
		self.assertIsNotNone(perfil.club)
		self.assertEqual(perfil.club.id, club.id)

	def test_crear_corredor_assigns_club_from_profesor(self):
		club, grupo = self._create_club_and_group("Prof Club", "Prof Grupo")
		profesor_user, profesor_perfil = self._create_user_with_profile(
			username="prof-create",
			role="profesor",
			django_group_name="Profesor",
		)
		profesor_perfil.club = club
		profesor_perfil.save(update_fields=["club"])

		self.client.login(username=profesor_user.username, password="testpass123")
		response = self.client.post(reverse("crear_corredor"), {
			"username": "new_runner",
			"first_name": "Nuevo",
			"last_name": "Corredor",
			"email": "new@runner.test",
			"grupo": grupo.id,
			"meta_actual": "Meta",
			"mejor_marca": "00:00",
			"modalidad_ritmo": "runners",
		}, follow=True)
		self.assertEqual(response.status_code, 200)
		perfil = Perfil.objects.get(usuario__username="new_runner")
		self.assertIsNotNone(perfil.club)
		self.assertEqual(perfil.club.id, club.id)

	def test_profesor_no_accede_a_cumplidos_de_otro_club(self):
		club_a, grupo_a = self._create_club_and_group("Club A", "Grupo A")
		club_b, grupo_b = self._create_club_and_group("Club B", "Grupo B")

		profesor_user, profesor_perfil = self._create_user_with_profile(
			username="prof-cumplidos",
			role="profesor",
			django_group_name="Profesor",
		)
		profesor_perfil.club = club_a
		profesor_perfil.save(update_fields=["club"])

		entreno_b = EntrenamientoDiario.objects.create(
			grupo=grupo_b,
			fecha=timezone.localdate(),
			tipo="entreno",
			titulo="Plan B",
			descripcion="test",
		)

		self.client.login(username=profesor_user.username, password="testpass123")
		response = self.client.get(reverse("cumplimiento_cumplidos", args=[grupo_b.id]))

		self.assertEqual(response.status_code, 404)

	# INICIO - Cobertura del aislamiento de Strava
	@override_settings(STRAVA_ENABLED=False)
	def test_strava_disabled_preserves_tokens_and_skips_network_and_auto_marking(self):
		from .views import _strava_refresh_token, _strava_sync_latest_activities

		grupo = Grupo.objects.create(nombre="Strava disabled")
		user, perfil = self._create_user_with_profile(
			username="runner_strava_disabled",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo,
		)
		perfil.strava_access_token = "fake-access-token"
		perfil.strava_refresh_token = "fake-refresh-token"
		perfil.save(update_fields=["strava_access_token", "strava_refresh_token"])
		self.client.force_login(user)
		session = self.client.session
		session["strava_oauth_state"] = "fake-state"
		session.save()

		with (
			patch("users.views.requests.get") as get,
			patch("users.views.requests.post") as post,
			patch("users.views._auto_mark_cumplimiento_from_strava") as home_auto_mark,
			patch("users.management.commands.auto_cumplimiento_strava._auto_mark_cumplimiento_from_strava") as command_auto_mark,
		):
			self.assertFalse(_strava_refresh_token(perfil))
			self.assertFalse(_strava_sync_latest_activities(perfil))

			for route in ("strava_login", "strava_callback", "actividad", "strava_disconnect", "strava_delete_data"):
				with self.subTest(route=route):
					url = reverse(route)
					if route in {"strava_disconnect", "strava_delete_data"}:
						response = self.client.post(url)
					else:
						response = self.client.get(url, {"code": "fake-code", "state": "fake-state"})
					self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

			response = self.client.get(reverse("home"))
			for route in ("strava_login", "actividad", "strava_disconnect", "strava_delete_data"):
				self.assertNotContains(response, f'"{reverse(route)}"')

			call_command("auto_cumplimiento_strava", verbosity=0)

		get.assert_not_called()
		post.assert_not_called()
		home_auto_mark.assert_not_called()
		command_auto_mark.assert_not_called()
		perfil.refresh_from_db()
		self.assertEqual(perfil.strava_access_token, "fake-access-token")
		self.assertEqual(perfil.strava_refresh_token, "fake-refresh-token")

	@override_settings(STRAVA_ENABLED=True)
	def test_strava_disconnect_revokes_token_when_enabled(self):
		user, perfil = self._create_user_with_profile(
			username="runner_strava_disconnect",
			role="corredor",
			django_group_name="Corredor",
		)
		perfil.strava_access_token = "fake-access-token"
		perfil.strava_refresh_token = "fake-refresh-token"
		perfil.strava_athlete_id = 900
		perfil.save(update_fields=["strava_access_token", "strava_refresh_token", "strava_athlete_id"])
		activity = StravaActividad.objects.create(perfil=perfil, strava_id=901)
		self.client.force_login(user)

		with patch("users.views.requests.post") as post:
			post.side_effect = requests.Timeout
			self.client.post(reverse("strava_disconnect"))
			perfil.refresh_from_db()
			self.assertEqual(perfil.strava_access_token, "fake-access-token")
			post.reset_mock(side_effect=True)
			response = self.client.post(reverse("strava_disconnect"))

		self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
		post.assert_called_once()
		self.assertTrue(post.call_args.args[0].endswith("/oauth/revoke"))
		self.assertEqual(post.call_args.kwargs["data"], {"token": "fake-refresh-token"})
		perfil.refresh_from_db()
		self.assertIsNone(perfil.strava_access_token)
		self.assertIsNone(perfil.strava_refresh_token)
		self.assertEqual(perfil.strava_athlete_id, 900)
		self.assertTrue(StravaActividad.objects.filter(pk=activity.pk, perfil=perfil).exists())

	@override_settings(STRAVA_ENABLED=True)
	def test_strava_delete_data_requires_post(self):
		grupo = Grupo.objects.create(nombre="Delete Data Group")
		user, _ = self._create_user_with_profile(
			username="runner_delete_get",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo,
		)

		self.client.login(username=user.username, password="testpass123")
		response = self.client.get(reverse("strava_delete_data"))

		self.assertEqual(response.status_code, 403)

	@override_settings(STRAVA_ENABLED=True)
	def test_strava_delete_data_clears_tokens_and_local_activities(self):
		grupo = Grupo.objects.create(nombre="Delete Data Group 2")
		user, perfil = self._create_user_with_profile(
			username="runner_delete_post",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo,
		)

		perfil.strava_access_token = "access-123"
		perfil.strava_refresh_token = "refresh-123"
		perfil.strava_expires_at = 1893456000
		perfil.strava_athlete_id = 445566
		perfil.save(update_fields=[
			"strava_access_token",
			"strava_refresh_token",
			"strava_expires_at",
			"strava_athlete_id",
		])

		StravaActividad.objects.create(
			perfil=perfil,
			strava_id=993001,
			name="Actividad a borrar",
			type="Run",
			start_date=timezone.now(),
			distance_m=5000,
			moving_time_s=1500,
		)

		self.client.login(username=user.username, password="testpass123")
		with patch("users.views.requests.post") as mock_post:
			response = self.client.post(reverse("strava_delete_data"), follow=True)

		self.assertEqual(response.status_code, 200)
		mock_post.assert_called_once()

		perfil.refresh_from_db()
		self.assertIsNone(perfil.strava_access_token)
		self.assertIsNone(perfil.strava_refresh_token)
		self.assertIsNone(perfil.strava_expires_at)
		self.assertIsNone(perfil.strava_athlete_id)
		self.assertEqual(StravaActividad.objects.filter(perfil=perfil).count(), 0)

	@override_settings(
		STRAVA_ENABLED=True, STRAVA_REDIRECT_URI="http://localhost:8766/strava/callback/",
	)
	def test_strava_login_sets_oauth_state_in_session(self):
		grupo = Grupo.objects.create(nombre="State Group")
		user, _ = self._create_user_with_profile(
			username="runner_state_login",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo,
		)

		self.client.login(username=user.username, password="testpass123")
		response = self.client.get(reverse("strava_login"))

		self.assertEqual(response.status_code, 302)
		params = parse_qs(urlsplit(response.url).query)
		self.assertEqual(params["redirect_uri"], ["http://localhost:8766/strava/callback/"])
		self.assertEqual(params["state"], [self.client.session["strava_oauth_state"]])

	@override_settings(STRAVA_ENABLED=True)
	def test_strava_callback_rejects_invalid_state(self):
		grupo = Grupo.objects.create(nombre="State Group 2")
		user, perfil = self._create_user_with_profile(
			username="runner_state_callback",
			role="corredor",
			django_group_name="Corredor",
			grupo=grupo,
		)

		self.client.login(username=user.username, password="testpass123")
		session = self.client.session
		session["strava_oauth_state"] = "expected-state"
		session.save()

		with patch("users.views.requests.post") as mock_post:
			response = self.client.get(reverse("strava_callback"), {
				"code": "code123",
				"state": "wrong-state",
			})

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse("home"))
		mock_post.assert_not_called()
		perfil.refresh_from_db()
		self.assertIsNone(perfil.strava_access_token)

	@override_settings(STRAVA_ENABLED=True)
	def test_strava_callback_requires_activity_access_and_saves_valid_tokens_once(self):
		user, perfil = self._create_user_with_profile("runner_callback", "corredor", "Corredor")
		self.client.force_login(user)
		url = reverse("strava_callback")
		params = {"code": "fake-code", "state": "expected-state", "scope": "read"}

		with patch("users.views.requests.post") as post:
			session = self.client.session
			session["strava_oauth_state"] = "expected-state"
			session.save()
			self.client.get(url, params)
			post.assert_not_called()
			perfil.refresh_from_db()
			self.assertIsNone(perfil.strava_access_token)

			session = self.client.session
			session["strava_oauth_state"] = "expected-state"
			session.save()
			params["scope"] = "read,activity:read_all"
			post.return_value.status_code = 200
			post.return_value.json.return_value = {
				"access_token": "new-access", "refresh_token": "new-refresh",
				"expires_at": 1893456000, "athlete": {"id": 400},
			}
			self.client.get(url, params)
			self.client.get(url, params)
			post.assert_called_once()

		perfil.refresh_from_db()
		self.assertEqual(perfil.strava_access_token, "new-access")
		self.assertEqual(perfil.strava_refresh_token, "new-refresh")
		self.assertEqual(perfil.strava_expires_at, 1893456000)
		self.assertEqual(perfil.strava_athlete_id, 400)

	@override_settings(STRAVA_ENABLED=True)
	def test_strava_activity_refreshes_imports_idempotently_and_preserves_ownership(self):
		user, perfil = self._create_user_with_profile("runner_import", "corredor", "Corredor")
		_, other = self._create_user_with_profile("other_runner", "corredor", "Corredor")
		perfil.strava_access_token = "expired-access"
		perfil.strava_refresh_token = "old-refresh"
		perfil.strava_expires_at = 1
		perfil.save()
		StravaActividad.objects.create(perfil=other, strava_id=600, name="Actividad ajena")
		self.client.force_login(user)
		url = reverse("actividad")

		with patch("users.views.requests.post") as post, patch("users.views.requests.get") as get:
			post.return_value.status_code = 200
			post.return_value.json.return_value = {
				"access_token": "fresh-access", "refresh_token": "rotated-refresh",
				"expires_at": 1893456000,
			}
			get.return_value.status_code = 200
			get.return_value.json.return_value = [
				{
					"id": 500, "name": "Actividad propia", "distance": 3000,
					"start_date": timezone.now().isoformat(),
				},
				{"id": 600, "name": "Actividad ajena"},
			]
			for _ in range(2):
				response = self.client.get(url)
				self.assertContains(response, 'class="act-card"')
				self.assertEqual([row.strava_id for row in response.context["actividades"]], [500])
			post.assert_called_once()
			self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer fresh-access")
			get.side_effect = requests.Timeout
			response = self.client.get(url)
			self.assertContains(response, 'class="act-card"')
			self.assertEqual([row.strava_id for row in response.context["actividades"]], [500])

		perfil.refresh_from_db()
		self.assertEqual(perfil.strava_refresh_token, "rotated-refresh")
		self.assertEqual(StravaActividad.objects.filter(perfil=perfil, strava_id=500).count(), 1)
		self.assertTrue(StravaActividad.objects.filter(perfil=other, strava_id=600).exists())
	# FIN - Cobertura del aislamiento de Strava

